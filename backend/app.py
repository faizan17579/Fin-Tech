import os
from pathlib import Path
import json
import time
from datetime import datetime, timedelta, timezone
import numpy as np
from typing import Any, Dict, List, Optional

import pandas as pd

import yfinance as yf
from flask import Flask, jsonify, request
from flask_cors import CORS

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_socketio import SocketIO, emit, join_room, leave_room
from marshmallow import Schema, ValidationError, fields

from database.db_manager import DatabaseManager
from backend.data_pipeline import build_feature_pipeline, FetchParams
from backend.fintech_curator import FinTechDataCurator
from backend.training_service import TrainingConfig, TrainingService

from .services.model_service import generate_forecast


class MongoCache:
    """MongoDB-based cache replacement for Redis"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        
    def get(self, key: str) -> Optional[str]:
        """Get cached value by key"""
        if self.db.mode == "mongo" and self.db.mongo_db is not None:
            doc = self.db.mongo_db["cache"].find_one({"key": key})
            if doc:
                expires_at = doc.get("expires_at")
                now = datetime.now(timezone.utc)
                
                # Handle timezone-aware vs naive datetime comparison
                if expires_at:
                    if expires_at.tzinfo is None:
                        # If stored datetime is naive, make it UTC
                        expires_at = expires_at.replace(tzinfo=timezone.utc)
                    
                    if expires_at > now:
                        return doc.get("value")
                    else:
                        # Expired, delete it
                        self.db.mongo_db["cache"].delete_one({"key": key})
        return None
    
    def setex(self, key: str, expiration: timedelta, value: str) -> None:
        """Set cached value with expiration"""
        if self.db.mode == "mongo" and self.db.mongo_db is not None:
            expires_at = datetime.now(timezone.utc) + expiration
            self.db.mongo_db["cache"].replace_one(
                {"key": key},
                {"key": key, "value": value, "expires_at": expires_at},
                upsert=True
            )

try:
    from celery import Celery as _Celery
except Exception:  # pragma: no cover
    _Celery = None  # type: ignore


def make_celery(app: Flask) -> Optional[object]:
    # Disabled Celery since we removed Redis dependency
    # Background tasks will run synchronously
    app.logger.warning("Celery disabled - running tasks synchronously")
    return None


class ForecastRequestSchema(Schema):
    symbol = fields.String(required=True)
    horizon = fields.Integer(required=True, validate=lambda x: 1 <= x <= 365)
    # marshmallow>=3 uses `load_default` instead of the older `missing` kwarg
    model_type = fields.String(required=False, load_default="baseline")


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        ENV=os.getenv("FLASK_ENV", "development"),
        DEBUG=os.getenv("FLASK_DEBUG", "1") == "1",
        SECRET_KEY=os.getenv("SECRET_KEY", "change-me"),
        RATELIMIT_DEFAULT="60 per minute",
    )

    # Extensions
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    limiter = Limiter(get_remote_address, app=app, default_limits=[app.config["RATELIMIT_DEFAULT"]])

    socketio = SocketIO(app, cors_allowed_origins="*")

    # Database and Cache
    db = DatabaseManager()
    cache = MongoCache(db)

    # Celery
    celery = make_celery(app)

    # Error handling
    @app.errorhandler(ValidationError)
    def handle_validation_error(err: ValidationError):
        return jsonify({"error": "validation_error", "messages": err.messages}), 400

    @app.errorhandler(429)
    def ratelimit_handler(e):
        return jsonify({"error": "rate_limited", "message": "Too many requests"}), 429

    @app.errorhandler(Exception)
    def handle_unexpected_error(err: Exception):  # pragma: no cover (generic safeguard)
        app.logger.exception("Unhandled error: %s", err)
        return jsonify({"error": "internal_error"}), 500

    # Extended instrument database
    INSTRUMENTS_DB = {
        "stocks": [
            # Tech stocks
            {"symbol": "AAPL", "name": "Apple Inc.", "sector": "Technology"},
            {"symbol": "MSFT", "name": "Microsoft Corporation", "sector": "Technology"},
            {"symbol": "GOOG", "name": "Alphabet Inc.", "sector": "Technology"},
            {"symbol": "GOOGL", "name": "Alphabet Inc. Class A", "sector": "Technology"},
            {"symbol": "AMZN", "name": "Amazon.com Inc.", "sector": "Technology"},
            {"symbol": "TSLA", "name": "Tesla Inc.", "sector": "Automotive"},
            {"symbol": "META", "name": "Meta Platforms Inc.", "sector": "Technology"},
            {"symbol": "NFLX", "name": "Netflix Inc.", "sector": "Entertainment"},
            {"symbol": "NVDA", "name": "NVIDIA Corporation", "sector": "Technology"},
            {"symbol": "CRM", "name": "Salesforce Inc.", "sector": "Technology"},
            # Financial stocks
            {"symbol": "JPM", "name": "JPMorgan Chase & Co.", "sector": "Financial"},
            {"symbol": "BAC", "name": "Bank of America Corp.", "sector": "Financial"},
            {"symbol": "WFC", "name": "Wells Fargo & Co.", "sector": "Financial"},
            {"symbol": "GS", "name": "Goldman Sachs Group Inc.", "sector": "Financial"},
            {"symbol": "MS", "name": "Morgan Stanley", "sector": "Financial"},
            # Healthcare stocks
            {"symbol": "JNJ", "name": "Johnson & Johnson", "sector": "Healthcare"},
            {"symbol": "PFE", "name": "Pfizer Inc.", "sector": "Healthcare"},
            {"symbol": "UNH", "name": "UnitedHealth Group Inc.", "sector": "Healthcare"},
            {"symbol": "ABBV", "name": "AbbVie Inc.", "sector": "Healthcare"},
            # Energy stocks
            {"symbol": "XOM", "name": "Exxon Mobil Corporation", "sector": "Energy"},
            {"symbol": "CVX", "name": "Chevron Corporation", "sector": "Energy"},
        ],
        "crypto": [
            {"symbol": "BTC-USD", "name": "Bitcoin", "sector": "Cryptocurrency"},
            {"symbol": "ETH-USD", "name": "Ethereum", "sector": "Cryptocurrency"},
            {"symbol": "BNB-USD", "name": "Binance Coin", "sector": "Cryptocurrency"},
            {"symbol": "ADA-USD", "name": "Cardano", "sector": "Cryptocurrency"},
            {"symbol": "DOGE-USD", "name": "Dogecoin", "sector": "Cryptocurrency"},
            {"symbol": "XRP-USD", "name": "Ripple", "sector": "Cryptocurrency"},
            {"symbol": "DOT-USD", "name": "Polkadot", "sector": "Cryptocurrency"},
        ],
        "forex": [
            {"symbol": "EURUSD=X", "name": "EUR/USD", "sector": "Forex"},
            {"symbol": "USDJPY=X", "name": "USD/JPY", "sector": "Forex"},
            {"symbol": "GBPUSD=X", "name": "GBP/USD", "sector": "Forex"},
            {"symbol": "USDCHF=X", "name": "USD/CHF", "sector": "Forex"},
            {"symbol": "AUDUSD=X", "name": "AUD/USD", "sector": "Forex"},
            {"symbol": "USDCAD=X", "name": "USD/CAD", "sector": "Forex"},
        ]
    }

    # Instruments
    @app.get("/api/instruments")
    def list_instruments():
        cached = cache.get("instruments")
        if cached:
            return jsonify(json.loads(cached))
        
         # ✅ Return full objects (symbol, name, sector)
        instruments = INSTRUMENTS_DB 
        cache.setex("instruments", timedelta(minutes=60), json.dumps(instruments))
        return jsonify(instruments)

    # New search/suggestion endpoint
    @app.get("/api/instruments/search")
    def search_instruments():
        query = request.args.get('q', '').lower().strip()
        if not query:
            return jsonify([])
        
        suggestions = []
        for category, instruments in INSTRUMENTS_DB.items():
            for instrument in instruments:
                # Search in symbol, name, and sector
                if (query in instrument["symbol"].lower() or 
                    query in instrument["name"].lower() or 
                    query in instrument.get("sector", "").lower()):
                    suggestions.append({
                        **instrument,
                        "type": category.rstrip('s')  # Remove 's' from category name
                    })
        
        # Limit results and sort by relevance (symbol matches first)
        suggestions.sort(key=lambda x: (
            0 if x["symbol"].lower().startswith(query) else 1,
            x["symbol"]
        ))
        
        return jsonify(suggestions[:20])  # Limit to 20 suggestions

    # Historical data
    @app.get("/api/historical/<symbol>")
    @limiter.limit("30 per minute")
    def historical(symbol: str):
        cache_key = f"hist:{symbol}"
        if (val := cache.get(cache_key)) is not None:
            return jsonify(json.loads(val))
        rows = db.get_historical_prices(symbol, limit=5000)
        if not rows:
            # fallback fetch
            try:
                df = yf.download(tickers=symbol, period="1y", interval="1d", progress=False, auto_adjust=False)
                
                # Handle multi-level columns if they exist
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.droplevel(1)  # Remove symbol level
                
                # Ensure column names are strings and lowercase
                df.columns = [str(col).lower() for col in df.columns]
                
                # Reset index to get date as a column
                df = df.reset_index()
                
                # Find the date column (could be 'Date', 'date', or index name)
                date_col = None
                for col in df.columns:
                    if str(col).lower() in ['date', 'datetime', 'timestamp'] or col == df.index.name:
                        date_col = col
                        break
                
                # If no date column found, use the first column (likely the index)
                if date_col is None and len(df.columns) > 0:
                    date_col = df.columns[0]
                
                # Ensure we have the required columns
                required_cols = ["open", "high", "low", "close", "volume"]
                available_cols = [col for col in required_cols if col in df.columns]
                
                if not available_cols or date_col is None:
                    data = []
                else:
                    # Select only the columns we need, plus date
                    cols_to_select = [date_col] + available_cols
                    df = df[cols_to_select].rename(columns={date_col: "timestamp"})
                    
                    # Convert timestamp to string for JSON serialization
                    if pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
                        df["timestamp"] = df["timestamp"].dt.strftime("%Y-%m-%d")
                    else:
                        df["timestamp"] = df["timestamp"].astype(str)
                    
                    # Fill NaN values with 0
                    df = df.fillna(0)
                    
                    data = df.to_dict(orient="records")
                    # Persist into DB for future training (best-effort)
                    for row in data:
                        try:
                            ts_val = row.get("timestamp")
                            if ts_val:
                                # Parse date string (YYYY-MM-DD)
                                dt_obj = datetime.strptime(str(ts_val), "%Y-%m-%d")
                                db.create_historical_price(
                                    symbol=symbol,
                                    timestamp=dt_obj,
                                    open=float(row.get("open", 0.0)),
                                    high=float(row.get("high", 0.0)),
                                    low=float(row.get("low", 0.0)),
                                    close=float(row.get("close", 0.0)),
                                    volume=float(row.get("volume", 0.0)),
                                )
                        except Exception:
                            pass
            except Exception as e:
                app.logger.error(f"Error fetching data for {symbol}: {e}")
                data = []
        else:
            data = rows
        
        # Safely cache the data
        try:
            cache.setex(cache_key, timedelta(minutes=10), json.dumps(data, default=str))
        except Exception as e:
            app.logger.warning(f"Failed to cache data for {symbol}: {e}")
        
        return jsonify(data)

    # Forecast creation (async)
    forecast_schema = ForecastRequestSchema()

    def _perform_forecast(symbol: str, horizon: int, model_type: str) -> Dict[str, Any]:
        # Run real model
        values, used, metrics = generate_forecast(symbol=symbol, horizon=horizon, model_type=model_type, db=db)
        doc = {
            "symbol": symbol,
            "timestamp": datetime.now(timezone.utc),
            "forecast_horizon": horizon,
            "predicted_values": values,
            "model_used": used,
            "metrics": metrics or {},
        }
        forecast_id = db.create_forecast(**doc)
        return {"forecast_id": str(forecast_id), **doc}

    if celery is not None:
        @celery.task(name="tasks.run_forecast")
        def run_forecast_task(symbol: str, horizon: int, model_type: str) -> Dict[str, Any]:
            return _perform_forecast(symbol, horizon, model_type)

    @app.post("/api/forecast")
    @limiter.limit("10 per minute")
    def create_forecast_api():
        payload = request.get_json(silent=True) or {}
        data = forecast_schema.load(payload)
        symbol = data["symbol"]
        horizon = int(data["horizon"])
        model_type = data.get("model_type", "baseline")

        if celery is None:
            result = _perform_forecast(symbol, horizon, model_type)
            return jsonify({"status": "completed", **result})

        task = run_forecast_task.delay(symbol, horizon, model_type)
        return jsonify({"status": "queued", "task_id": task.id})

    @app.get("/api/forecast/<forecast_id>")
    def get_forecast(forecast_id: str):
        # Try to fetch by DB id; for Celery task id, return status only
        try:
            # naive attempt for Mongo _id (string) already stored as string in our helper
            forecasts = db.get_forecasts(symbol="*")  # not ideal; for demo, fetch recent and match
            for f in forecasts:
                if str(f.get("_id", f.get("id"))) == forecast_id:
                    return jsonify(f)
        except Exception:
            pass
        if celery is not None:
            async_res = celery.AsyncResult(forecast_id)
            if async_res:
                return jsonify({"task_id": forecast_id, "state": async_res.state, "result": async_res.result if async_res.successful() else None})
        return jsonify({"error": "not_found"}), 404

    # Model performance (toy aggregation)
    @app.get("/api/models/performance")
    def model_performance():
        """Return latest performance metrics for models.

        Optional query params:
          symbol: if provided, only return models tagged with "symbol:MODEL" (strip prefix in response)
        """
        symbol = request.args.get("symbol", "").strip()
        models: List[Dict[str, Any]] = []
        try:
            # Strategy: list recent model_metadata entries (DB-specific). For simplicity, attempt to infer common models.
            base_models = ["SMA20", "EMA20", "ARIMA", "LSTM", "ENSEMBLE"]
            for m in base_models:
                key = f"{symbol}:{m}" if symbol else m
                meta = db.get_latest_model_metadata(key) or {}
                metrics = meta.get("performance_metrics", {}) if meta else {}
                if not metrics:
                    # Skip entirely if no metrics for symbol-specific query
                    if symbol:
                        continue
                models.append({"model": m, "metrics": metrics})
            return jsonify(models)
        except Exception as e:  # pragma: no cover
            app.logger.warning("model_performance failed: %s", e)
            return jsonify([])

    # Live price via Socket.IO
    @socketio.on("subscribe_price")
    def handle_subscribe(data):
        symbol = (data or {}).get("symbol")
        if not symbol:
            emit("error", {"message": "symbol required"})
            return
        join_room(symbol)
        emit("subscribed", {"symbol": symbol})

    @socketio.on("unsubscribe_price")
    def handle_unsubscribe(data):
        symbol = (data or {}).get("symbol")
        if symbol:
            leave_room(symbol)
            emit("unsubscribed", {"symbol": symbol})

    @app.get("/api/live-price/<symbol>")
    def live_price(symbol: str):
        # Short TTL cache (5s) to avoid hammering yfinance
        cache_key = f"live:{symbol}"
        if (cached := cache.get(cache_key)) is not None:
            try:
                return jsonify(json.loads(cached))
            except Exception:
                pass
        try:
            ticker = yf.Ticker(symbol)
            price = ticker.fast_info.last_price  # type: ignore[attr-defined]
            payload = {"symbol": symbol, "price": float(price), "cached": False}
            cache.setex(cache_key, timedelta(seconds=5), json.dumps(payload))
            return jsonify(payload)
        except Exception:
            return jsonify({"error": "unavailable"}), 503

    @app.get("/api/quotes")
    def batch_quotes():
        symbols = request.args.get("symbols", "").split(",")
        symbols = [s.strip() for s in symbols if s.strip()]
        if not symbols:
            return jsonify([])
        # Cache by sorted symbol list (15s TTL)
        cache_key = f"quotes:{','.join(sorted(symbols))}"
        if (cached := cache.get(cache_key)) is not None:
            try:
                return jsonify(json.loads(cached))
            except Exception:
                pass
        out: List[Dict[str, Any]] = []
        download_syms = list(dict.fromkeys(symbols))  # dedupe preserving order
        try:
            # Attempt batch download (1 day daily data)
            df = yf.download(tickers=download_syms, period="1d", interval="1d", progress=False, group_by='ticker', auto_adjust=False, threads=True)
            if isinstance(df.columns, pd.MultiIndex):
                # Multi-ticker frame
                for sym in download_syms:
                    try:
                        close_series = df[sym]['Close'] if 'Close' in df[sym] else None  # type: ignore[index]
                        price = float(close_series.dropna().iloc[-1]) if close_series is not None and not close_series.dropna().empty else None
                        out.append({"symbol": sym, "price": price})
                    except Exception:
                        out.append({"symbol": sym, "price": None})
            else:
                # Single ticker case
                try:
                    close_series = df['Close'] if 'Close' in df else None
                    price_single = float(close_series.dropna().iloc[-1]) if close_series is not None and not close_series.dropna().empty else None
                    out.append({"symbol": download_syms[0], "price": price_single})
                except Exception:
                    out.append({"symbol": download_syms[0], "price": None})
            # If some symbols missing (e.g., forex/crypto edge cases), fill via fallback
            got_set = {o['symbol'] for o in out}
            for sym in download_syms:
                if sym not in got_set:
                    try:
                        t = yf.Ticker(sym)
                        price = float(t.fast_info.last_price)  # type: ignore[attr-defined]
                        out.append({"symbol": sym, "price": price})
                    except Exception:
                        out.append({"symbol": sym, "price": None})
        except Exception:
            # Complete fallback: per-symbol
            out = []
            for sym in download_syms:
                try:
                    t = yf.Ticker(sym)
                    price = float(t.fast_info.last_price)  # type: ignore[attr-defined]
                    out.append({"symbol": sym, "price": price})
                except Exception:
                    out.append({"symbol": sym, "price": None})
        # Cache result
        try:
            cache.setex(cache_key, timedelta(seconds=15), json.dumps(out))
        except Exception:
            pass
        return jsonify(out)

    @app.get("/api/latest/<symbol>")
    def latest(symbol: str):
        """Return latest daily OHLC for symbol with caching and DB persistence."""
        cache_key = f"latest:{symbol}"
        if (cached := cache.get(cache_key)) is not None:
            try:
                return jsonify(json.loads(cached))
            except Exception:
                pass
        # Try DB (Mongo optimized path)
        latest_doc: Optional[Dict[str, Any]] = None
        try:
            if db.mode == 'mongo' and db.mongo_db is not None:
                doc = db.mongo_db['historical_prices'].find({"symbol": symbol}).sort("timestamp", -1).limit(1)
                docs = list(doc)
                if docs:
                    d = docs[0]
                    ts = d.get('timestamp')
                    if ts and isinstance(ts, datetime):
                        # If within 26 hours treat as fresh
                        if ts > datetime.now(timezone.utc) - timedelta(hours=26):
                            latest_doc = {
                                "symbol": symbol,
                                "timestamp": ts.isoformat(),
                                "open": d.get('open'),
                                "high": d.get('high'),
                                "low": d.get('low'),
                                "close": d.get('close'),
                                "volume": d.get('volume')
                            }
            else:
                # SQLite: fetch some rows and take last
                rows = db.get_historical_prices(symbol, limit=5)
                if rows:
                    r = rows[-1]
                    ts_raw = r.get('timestamp')
                    if ts_raw:
                        try:
                            parsed = ts_raw if isinstance(ts_raw, datetime) else datetime.fromisoformat(str(ts_raw))
                        except Exception:
                            parsed = None
                    else:
                        parsed = None
                    if parsed and parsed > datetime.now(timezone.utc) - timedelta(hours=26):
                        latest_doc = {
                            "symbol": symbol,
                            "timestamp": str(ts_raw),
                            "open": r.get('open'),
                            "high": r.get('high'),
                            "low": r.get('low'),
                            "close": r.get('close'),
                            "volume": r.get('volume')
                        }
        except Exception:
            pass
        if latest_doc is None:
            # Fetch minimal historical (5d daily) and persist
            try:
                df = yf.download(tickers=symbol, period='5d', interval='1d', progress=False, auto_adjust=False)
                if not df.empty:
                    if isinstance(df.index, pd.DatetimeIndex):
                        for dt, row in df.iterrows():
                            try:
                                # Extract scalars safely (avoid float(single-element Series) deprecation)
                                def _scalar(v):
                                    try:
                                        if hasattr(v, 'item'):
                                            return float(v.item())
                                        return float(v)
                                    except Exception:
                                        return 0.0
                                db.create_historical_price(
                                    symbol=symbol,
                                    timestamp=dt.tz_localize(None) if hasattr(dt, 'tzinfo') and dt.tzinfo else dt,
                                    open=_scalar(row.get('Open', row.get('open', 0.0)) or 0.0),
                                    high=_scalar(row.get('High', row.get('high', 0.0)) or 0.0),
                                    low=_scalar(row.get('Low', row.get('low', 0.0)) or 0.0),
                                    close=_scalar(row.get('Close', row.get('close', 0.0)) or 0.0),
                                    volume=_scalar(row.get('Volume', row.get('volume', 0.0)) or 0.0),
                                )
                            except Exception:
                                # Ignore duplicates or insertion errors
                                pass
                        last_row = df.iloc[-1]
                        last_dt = df.index[-1]
                        def _get(row, key):
                            v = row.get(key, 0.0)
                            try:
                                if hasattr(v, 'item'):
                                    return float(v.item())
                                return float(v)
                            except Exception:
                                return 0.0
                        latest_doc = {
                            "symbol": symbol,
                            "timestamp": (last_dt.tz_localize(None).isoformat() if hasattr(last_dt, 'tzinfo') else str(last_dt)),
                            "open": _get(last_row, 'Open'),
                            "high": _get(last_row, 'High'),
                            "low": _get(last_row, 'Low'),
                            "close": _get(last_row, 'Close'),
                            "volume": _get(last_row, 'Volume'),
                        }
            except Exception as e:
                app.logger.warning(f"latest fetch failed for {symbol}: {e}")
        if latest_doc is None:
            return jsonify({"error": "unavailable"}), 503
        try:
            cache.setex(cache_key, timedelta(seconds=60), json.dumps(latest_doc))
        except Exception:
            pass
        return jsonify(latest_doc)

    @app.post("/api/dataset")
    def create_dataset():
        payload = request.get_json(silent=True) or {}
        symbol = str(payload.get("symbol", "")).strip()
        days = int(payload.get("days", 30))
        include_news = bool(payload.get("include_news", False))
        quick = bool(payload.get("quick", False))
        if not symbol:
            return jsonify({"error": "symbol_required"}), 400
        try:
            effective_days = max(days, 5)
            period = f"{effective_days if quick else max(effective_days, 90)}d" if quick else f"{max(effective_days, 365)}d"
            # In quick mode we only fetch minimal window and skip heavy indicators by setting use_talib False
            params = FetchParams(symbol=symbol, interval="1d", period=period)
            try:
                feats = build_feature_pipeline(params, use_talib=not quick)
            except ValueError as ve:
                # Surface data unavailability clearly
                return jsonify({"error": "no_data", "message": str(ve)}), 502
            if feats is None or feats.empty:
                return jsonify({"error": "no_data", "message": "No historical data received for symbol."}), 502
            feats = feats.tail(days).reset_index(drop=True)
            feats.rename(columns={"timestamp": "Date", "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}, inplace=True)

            data_records = feats.to_dict(orient="records")
            dataset = {"metadata": {"symbol": symbol, "days": days}, "data": data_records}

            if include_news and not quick:
                # Wrap news in timeout to avoid blocking
                import concurrent.futures, threading
                curator = FinTechDataCurator()
                exchange = "CRYPTO" if symbol.endswith("-USD") else "NASDAQ"
                news_summary = ""
                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                        fut = ex.submit(curator.collect_comprehensive_data, exchange, symbol, days)
                        curated = fut.result(timeout=6)  # seconds
                    news_by_date = {row["Date"]: row for row in curated.get("data", [])}
                    merged = []
                    for row in data_records:
                        news = news_by_date.get(str(row.get("Date"))) or {}
                        row.update({
                            "news_headlines": news.get("news_headlines", "No major news"),
                            "news_count": news.get("news_count", 0),
                            "news_sentiment_score": news.get("news_sentiment_score", 0.0),
                        })
                        merged.append(row)
                    dataset["data"] = merged
                    dataset["news_summary"] = curated.get("news_summary", "")
                except concurrent.futures.TimeoutError:
                    dataset["metadata"]["news_timeout"] = True
                except Exception as e:  # pragma: no cover
                    dataset["metadata"]["news_error"] = str(e)[:160]

            # Save
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            out_dir = os.path.join("datasets")
            os.makedirs(out_dir, exist_ok=True)
            csv_path = os.path.join(out_dir, f"fintech_dataset_{symbol}_{ts}.csv")
            json_path = os.path.join(out_dir, f"fintech_dataset_{symbol}_{ts}.json")
            pd.DataFrame(dataset["data"]).to_csv(csv_path, index=False)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(dataset, f, default=str, indent=2)
            return jsonify({
                "symbol": symbol,
                "days": days,
                "rows": int(len(dataset["data"])),
                "files": {"csv": csv_path, "json": json_path},
                "preview": dataset["data"][-10:],
            })
        except Exception as e:
            app.logger.exception("Failed to create dataset: %s", e)
            return jsonify({"error": "dataset_failed"}), 500

    @app.post("/api/train")
    def train_models():
        payload = request.get_json(silent=True) or {}
        symbol = str(payload.get("symbol", "")).strip()
        models = payload.get("models") or ["ARIMA", "LSTM"]
        horizon = int(payload.get("horizon", 24))
        window = int(payload.get("window_size", 48))
        if not symbol:
            return jsonify({"error": "symbol_required"}), 400
        try:
            cfg = TrainingConfig(symbols=[symbol], window_size=window, horizon=horizon)
            svc = TrainingService(cfg, db=db)
            series = svc._load_series(symbol)
            train = series.iloc[:-cfg.horizon]
            test = series.iloc[-cfg.horizon:]
            # Prepare run directory
            run_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            run_dir = Path("artifacts") / symbol / f"train_{run_ts}"
            run_dir.mkdir(parents=True, exist_ok=True)
            results = []
            summary_metrics = {}
            for name in models:
                name_str = str(name)
                lname = name_str.lower()
                try:
                    m = svc._instantiate_model(lname)
                except ValueError:
                    results.append({"model": name_str, "error": "unknown_model"})
                    continue
                if lname == "lstm":
                    m.fit(train, epochs=payload.get("epochs", 10), batch_size=32, validation_split=0.1)  # type: ignore[attr-defined]
                else:
                    m.fit(train)
                metrics = m.evaluate(test)
                # Upsert model metadata (namespaced)
                try:
                    db.upsert_model_metadata(
                        model_name=f"{symbol}:{name_str.upper()}",
                        training_date=datetime.now(timezone.utc),
                        parameters={"window_size": window, "horizon": horizon},
                        performance_metrics=metrics,
                    )
                except Exception:  # pragma: no cover
                    pass
                # Save artifact
                artifact_path = None
                try:
                    if lname == "lstm":
                        artifact_path = run_dir / f"{name_str.upper()}.keras"
                        m.model.save(str(artifact_path))  # type: ignore[attr-defined]
                    else:
                        import pickle
                        artifact_path = run_dir / f"{name_str.upper()}.pkl"
                        with open(artifact_path, 'wb') as f:
                            pickle.dump(m, f)
                except Exception as art_err:  # pragma: no cover
                    app.logger.warning("Artifact save failed for %s: %s", name_str, art_err)
                result_entry = {"model": name_str.upper(), "metrics": metrics, "artifact_path": str(artifact_path) if artifact_path else None}
                results.append(result_entry)
                summary_metrics[name_str.upper()] = metrics
            # Write metrics summary
            try:
                with open(run_dir / "metrics.json", 'w', encoding='utf-8') as f:
                    json.dump({"symbol": symbol, "horizon": horizon, "models": summary_metrics}, f, indent=2)
            except Exception:  # pragma: no cover
                pass
            return jsonify({"symbol": symbol, "horizon": horizon, "results": results, "run_dir": str(run_dir)})
        except Exception as e:
            app.logger.exception("Training failed: %s", e)
            return jsonify({"error": "training_failed"}), 500

    @app.post("/api/train-ensemble")
    def train_ensemble():
        """Train multiple models (traditional + neural) and persist forecasts + metrics.

        Request JSON:
        {
          symbol: str,
          horizon: int,
          models: ["SMA","EMA","ARIMA","LSTM"...],
          window_size: int (for LSTM),
          epochs: int (optional, LSTM),
          include_baselines: bool (optional)
        }
        """
        payload = request.get_json(silent=True) or {}
        symbol = str(payload.get("symbol", "")).strip()
        if not symbol:
            return jsonify({"error": "symbol_required"}), 400
        horizon = int(payload.get("horizon", 24))
        window_size = int(payload.get("window_size", 48))
        epochs = int(payload.get("epochs", 20))
        requested_models = payload.get("models") or ["SMA", "EMA", "ARIMA", "LSTM"]
        include_baselines = bool(payload.get("include_baselines", True))
        include_ensemble = bool(payload.get("include_ensemble", True))
        # Normalize & dedupe model names
        norm_models = []
        for m in requested_models:
            mm = str(m).strip()
            if not mm:
                continue
            if mm.upper() == "SMA":
                mm = "SMA20"
            if mm.upper() == "EMA":
                mm = "EMA20"
            if mm not in norm_models:
                norm_models.append(mm)
        try:
            cfg = TrainingConfig(symbols=[symbol], window_size=window_size, horizon=horizon)
            svc = TrainingService(cfg, db=db)
            series = svc._load_series(symbol)
            if len(series) < window_size + horizon + 5:
                return jsonify({"error": "insufficient_history", "have": int(len(series)), "need": int(window_size + horizon + 5)}), 400
            train = series.iloc[:-horizon]
            test = series.iloc[-horizon:]
            responses = []
            # Helper to persist
            def _persist(model_name: str, preds, metrics: dict):
                forecast_id = db.create_forecast(
                    symbol=symbol,
                    timestamp=datetime.now(timezone.utc),
                    forecast_horizon=horizon,
                    predicted_values=[float(v) for v in preds],
                    model_used=model_name,
                    metrics=metrics,
                )
                return str(forecast_id)
            run_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            artifacts_dir = Path("artifacts") / symbol / f"ensemble_{run_ts}"
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            for model_name in norm_models:
                lname = model_name.lower()
                try:
                    model = svc._instantiate_model(lname)
                except ValueError:
                    responses.append({"model": model_name, "skipped": True, "reason": "unknown_model"})
                    continue
                try:
                    if lname == "lstm":
                        model.fit(train, epochs=epochs, batch_size=32, validation_split=0.1)  # type: ignore[attr-defined]
                        # Provide last window + horizon metrics (same logic as earlier)
                        test_window_start = len(series) - (window_size + horizon)
                        eval_segment = series.iloc[test_window_start:]
                        metrics = model.evaluate(eval_segment)  # type: ignore[attr-defined]
                        # Build prediction using last window
                        recent_window = series.iloc[-window_size:]
                        preds = model.predict(horizon=horizon, recent_window=recent_window)  # type: ignore[attr-defined]
                        preds_list = [float(v) for v in preds]
                    else:
                        model.fit(train)
                        metrics = model.evaluate(test)
                        preds_series = model.predict(horizon)  # type: ignore[attr-defined]
                        # Ensure iterable
                        if hasattr(preds_series, 'values'):
                            preds_list = [float(v) for v in list(getattr(preds_series, 'values', preds_series))]
                        else:
                            preds_list = [float(v) for v in list(preds_series)]
                    # Truncate or pad predictions to horizon
                    if len(preds_list) > horizon:
                        preds_list = preds_list[:horizon]
                    if len(preds_list) < horizon:
                        preds_list.extend([preds_list[-1]] * (horizon - len(preds_list)))
                    # Persist model metadata for performance aggregation (namespaced by symbol)
                    try:
                        db.upsert_model_metadata(
                            model_name=f"{symbol}:{model_name.upper()}",
                            training_date=datetime.now(timezone.utc),
                            parameters={"window_size": window_size, "horizon": horizon},
                            performance_metrics=metrics,
                        )
                    except Exception as meta_err:  # pragma: no cover
                        app.logger.warning("Failed to persist model metadata %s: %s", model_name, meta_err)
                    # Save artifact
                    artifact_path = None
                    try:
                        if lname == "lstm":  # keras model
                            artifact_path = artifacts_dir / f"{model_name.upper()}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.keras"
                            # type: ignore[attr-defined]
                            model.model.save(str(artifact_path))  # type: ignore[attr-defined]
                        else:
                            import pickle  # local import
                            artifact_path = artifacts_dir / f"{model_name.upper()}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.pkl"
                            with open(artifact_path, 'wb') as f:
                                pickle.dump(model, f)
                    except Exception as art_err:  # pragma: no cover
                        app.logger.warning("Failed saving artifact for %s: %s", model_name, art_err)
                        artifact_path = None

                    forecast_id = _persist(model_name.upper(), preds_list, metrics)
                    responses.append({
                        "model": model_name.upper(),
                        "forecast_id": forecast_id,
                        "predicted_values": preds_list,
                        "metrics": metrics,
                        "horizon": horizon,
                        "artifact_path": str(artifact_path) if artifact_path else None,
                    })
                except Exception as me:  # pragma: no cover (robustness)
                    app.logger.warning("Model %s failed: %s", model_name, me)
                    responses.append({"model": model_name.upper(), "error": str(me)})
            # Optional simple ensemble average
            if include_ensemble and len([r for r in responses if r.get("predicted_values")]) >= 2:
                valid_preds = [r["predicted_values"] for r in responses if r.get("predicted_values")]
                # element-wise mean
                ens = [float(sum(vals)/len(vals)) for vals in zip(*valid_preds)]
                # Compute metrics against test
                y_true = test.values.astype(float)
                y_pred = np.array(ens[:horizon], dtype=float)
                eps = 1e-8
                rmse = float(np.sqrt(np.mean((y_true - y_pred)**2)))
                mae = float(np.mean(np.abs(y_true - y_pred)))
                mape = float(np.mean(np.abs((y_true - y_pred)/(np.abs(y_true)+eps)))*100.0)
                metrics_ens = {"rmse": rmse, "mae": mae, "mape": mape}
                ens_artifact = None
                try:
                    import json as _json
                    ens_artifact = artifacts_dir / f"ENSEMBLE_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.json"
                    with open(ens_artifact, 'w', encoding='utf-8') as f:
                        _json.dump({"component_models": [r["model"] for r in responses], "weights": "equal", "metrics": metrics_ens}, f)
                except Exception as ens_err:  # pragma: no cover
                    app.logger.warning("Failed saving ensemble artifact: %s", ens_err)
                forecast_id = db.create_forecast(
                    symbol=symbol,
                    timestamp=datetime.now(timezone.utc),
                    forecast_horizon=horizon,
                    predicted_values=ens,
                    model_used="ENSEMBLE",
                    metrics=metrics_ens,
                )
                responses.append({
                    "model": "ENSEMBLE",
                    "forecast_id": str(forecast_id),
                    "predicted_values": ens,
                    "metrics": metrics_ens,
                    "horizon": horizon,
                    "artifact_path": str(ens_artifact) if ens_artifact else None,
                })
            # Write run-level metrics summary
            try:
                metrics_summary = {r["model"]: r.get("metrics", {}) for r in responses if r.get("metrics")}
                with open(artifacts_dir / "metrics.json", 'w', encoding='utf-8') as f:
                    json.dump({
                        "symbol": symbol,
                        "horizon": horizon,
                        "models": metrics_summary,
                        "generated_at": datetime.now(timezone.utc).isoformat()
                    }, f, indent=2)
            except Exception:  # pragma: no cover
                pass
            return jsonify({
                "symbol": symbol,
                "horizon": horizon,
                "results": responses,
                "run_dir": str(artifacts_dir)
            })
        except Exception as e:
            app.logger.exception("train_ensemble failed: %s", e)
            return jsonify({"error": "training_failed"}), 500

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/api/export-model")
    def export_model():
        """Upload a saved model artifact to Hugging Face Hub.

        Request JSON:
          artifact_path: local path produced by /api/train-ensemble
          repo_id: target like username/repo_name (created if not exists)
          token: (optional) HF token; otherwise uses HF_TOKEN env var
          commit_message: optional commit message
        """
        payload = request.get_json(silent=True) or {}
        artifact_path = payload.get("artifact_path")
        repo_id = payload.get("repo_id")
        commit_message = payload.get("commit_message", "Add model artifact")
        token = payload.get("token") or os.getenv("HF_TOKEN")
        if not artifact_path or not os.path.exists(artifact_path):
            return jsonify({"error": "artifact_not_found"}), 400
        if not repo_id:
            return jsonify({"error": "repo_id_required"}), 400
        if not token:
            return jsonify({"error": "token_required"}), 400
        try:
            from huggingface_hub import HfApi, create_repo, upload_file
            api = HfApi()
            # Create repo if missing
            try:
                create_repo(repo_id, token=token, private=False, exist_ok=True)
            except Exception:  # pragma: no cover
                pass
            filename = os.path.basename(artifact_path)
            upload_file(
                path_or_fileobj=artifact_path,
                path_in_repo=filename,
                repo_id=repo_id,
                repo_type="model",
                token=token,
                commit_message=commit_message,
            )
            # Basic model card update if missing
            model_card = Path(artifact_path).parent / "README.md"
            if not model_card.exists():
                with open(model_card, "w", encoding="utf-8") as f:
                    f.write(f"# Model Export for {repo_id}\n\nUploaded artifact: `{filename}` on {datetime.now(timezone.utc).isoformat()}\n")
                try:
                    upload_file(
                        path_or_fileobj=str(model_card),
                        path_in_repo="README.md",
                        repo_id=repo_id,
                        repo_type="model",
                        token=token,
                        commit_message="Add autogenerated model card",
                    )
                except Exception:  # pragma: no cover
                    pass
            return jsonify({"status": "uploaded", "repo_id": repo_id, "filename": filename})
        except Exception as e:
            app.logger.exception("export_model failed: %s", e)
            return jsonify({"error": "export_failed", "detail": str(e)}), 500

    # Expose socketio for running
    app.extensions["socketio_instance"] = socketio
    return app


app = create_app()


if __name__ == "__main__":
    # Prefer SocketIO runner to support websockets
    socketio = app.extensions.get("socketio_instance")
    if isinstance(socketio, SocketIO):
        socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
    else:
        app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))


