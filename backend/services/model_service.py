from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from database.db_manager import DatabaseManager
from ML_models.traditional_models import (
    ARIMAModel,
    SMAModel,
    EMAModel,
    WMAModel,
    VARModel,
    HoltWintersModel,
)
from ML_models.neural_models import LSTMConfig, LSTMForecaster


def _load_series(symbol: str, db: DatabaseManager, limit: int = 5000) -> pd.Series:
    rows = db.get_historical_prices(symbol, limit=limit)
    if rows:
        df = pd.DataFrame(rows)
        # normalize timestamp
        ts_col = "timestamp"
        if ts_col in df.columns:
            df[ts_col] = pd.to_datetime(df[ts_col])
            df = df.sort_values(ts_col)
            return pd.Series(df["close"].astype(float).values, index=df[ts_col], name="close")
    # fallback to yfinance 1y 1d
    data = yf.download(tickers=symbol, period="1y", interval="1d", progress=False)
    if data is None or data.empty:
        raise ValueError(f"No historical data available for {symbol}")
    # Handle possible MultiIndex columns returned by yfinance
    if isinstance(data.columns, pd.MultiIndex):
        # Normalize levels to lowercase
        levels = [list(map(lambda v: str(v).lower(), lvl)) for lvl in data.columns.levels]
        data.columns = pd.MultiIndex.from_product(levels, names=data.columns.names)
        if "close" in data.columns.get_level_values(0):
            df_close = data.xs("close", axis=1, level=0)
            close_series = df_close.iloc[:, 0] if df_close.shape[1] >= 1 else pd.Series(dtype=float)
        else:
            # Fallback: take first top-level column
            first_top = data.columns.levels[0][0]
            df_first = data.xs(first_top, axis=1, level=0)
            close_series = df_first.iloc[:, 0]
    else:
        data = data.rename(columns=str.lower)
        if "close" in data.columns:
            close_series = data["close"]
        else:
            # Fallback to first column if 'close' missing
            close_series = data.iloc[:, 0]
    close_series.index = pd.to_datetime(close_series.index)
    close_series = pd.to_numeric(close_series, errors="coerce")
    return pd.Series(close_series.values, index=close_series.index, name="close")


def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    eps = 1e-8
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    mae = float(np.mean(np.abs(y_true - y_pred)))
    mape = float(np.mean(np.abs((y_true - y_pred) / (np.abs(y_true) + eps))) * 100.0)
    return {"rmse": rmse, "mae": mae, "mape": mape}


def _backtest_and_predict_univariate(model: Any, series: pd.Series, horizon: int) -> Tuple[List[float], Dict[str, float]]:
    if len(series) <= horizon:
        # not enough data for backtest; fit on all and no metrics
        model.fit(series)
        preds = model.predict(horizon)
        return [float(v) for v in np.asarray(preds)], {}
    train = series.iloc[:-horizon]
    test = series.iloc[-horizon:]
    model.fit(train)
    yhat_test = model.predict(len(test))
    metrics = _metrics(test.values, np.asarray(yhat_test))
    preds = model.predict(horizon)
    return [float(v) for v in np.asarray(preds)], metrics


def generate_forecast(symbol: str, horizon: int, model_type: str, db: Optional[DatabaseManager] = None) -> Tuple[List[float], str, Dict[str, float]]:
    """Run a real forecasting model and return predictions and metrics.

    Returns (predicted_values, model_used, metrics)
    """
    db = db or DatabaseManager()
    try:
        series = _load_series(symbol, db)
        mt = (model_type or "baseline").lower()

        if mt in ("baseline", "naive"):
            last = float(series.iloc[-1])
            preds = [last for _ in range(horizon)]
            return preds, "baseline-naive", {}

        if mt == "arima":
            try:
                model = ARIMAModel(seasonal=False)
                preds, metrics = _backtest_and_predict_univariate(model, series, horizon)
                return preds, "ARIMA", metrics
            except Exception:
                last = float(series.iloc[-1])
                return [last for _ in range(horizon)], "baseline-naive", {"warning": "ARIMA unavailable; fell back to baseline"}

        if mt == "sma":
            model = SMAModel(window=20)
            preds, metrics = _backtest_and_predict_univariate(model, series, horizon)
            return preds, "SMA20", metrics

        if mt == "ema":
            model = EMAModel(span=20)
            preds, metrics = _backtest_and_predict_univariate(model, series, horizon)
            return preds, "EMA20", metrics

        if mt == "wma":
            model = WMAModel(window=20)
            preds, metrics = _backtest_and_predict_univariate(model, series, horizon)
            return preds, "WMA20", metrics

        if mt == "holtwinters":
            model = HoltWintersModel(seasonal="add", seasonal_periods=7, grid_search=False)
            preds, metrics = _backtest_and_predict_univariate(model, series, horizon)
            return preds, "HoltWinters", metrics

        if mt == "var":
            df = pd.DataFrame({"close": series.values}, index=series.index)
            df["close_lag1"] = df["close"].shift(1).bfill()
            model = VARModel(lags=2, grid_search=False)
            if len(df) <= horizon:
                model.fit(df)
                fc = model.predict(horizon)
                preds = [float(v) for v in fc.iloc[:, 0].values]
                return preds, "VAR(lags=2)", {}
            train = df.iloc[:-horizon]
            test = df.iloc[-horizon:]
            model.fit(train)
            yhat_test = model.predict(len(test)).iloc[:, 0].values
            metrics = _metrics(test.iloc[:, 0].values, yhat_test)
            fc = model.predict(horizon)
            preds = [float(v) for v in fc.iloc[:, 0].values]
            return preds, "VAR(lags=2)", metrics

        if mt == "lstm":
            cfg = LSTMConfig(window_size=min(60, max(10, len(series) // 5)), horizon=horizon, use_attention=True)
            forecaster = LSTMForecaster(cfg)
            if len(series) <= cfg.window_size + horizon:
                forecaster.fit(series, epochs=10, batch_size=32, validation_split=0.1)
                recent_window = series.iloc[-cfg.window_size:]
                preds = forecaster.predict(horizon, recent_window=recent_window)
                return [float(v) for v in preds], "LSTM", {}
            train = series.iloc[: -(cfg.window_size + horizon)]
            forecaster.fit(train, epochs=10, batch_size=32, validation_split=0.1)
            eval_slice = series.iloc[-(cfg.window_size + horizon) :]
            metrics = forecaster.evaluate(eval_slice)
            recent_window = series.iloc[-cfg.window_size:]
            preds = forecaster.predict(horizon, recent_window=recent_window)
            return [float(v) for v in preds], "LSTM", metrics

        if mt == "ensemble":
            preds_list: List[List[float]] = []
            names: List[str] = []
            for sub in ["arima", "sma", "lstm"]:
                try:
                    p, name, _m = generate_forecast(symbol, horizon, sub, db)
                    preds_list.append(p)
                    names.append(name)
                except Exception:
                    continue
            if not preds_list:
                last = float(series.iloc[-1])
                return [last for _ in range(horizon)], "ensemble-fallback", {"warning": "all base models failed; baseline returned"}
            P = np.asarray(preds_list, dtype=float)
            yhat = np.mean(P, axis=0)
            return [float(v) for v in yhat], f"Ensemble[{'+'.join(names)}]", {}

        # Unknown model -> baseline
        last = float(series.iloc[-1])
        return [last for _ in range(horizon)], "baseline-naive", {"warning": f"unknown model_type: {model_type}"}
    except Exception as exc:
        # Global safety: never fail the endpoint; return baseline with error info
        last = float(series.iloc[-1]) if 'series' in locals() and len(series) else 0.0
        return [last for _ in range(horizon)], "baseline-naive", {"error": str(exc)}

