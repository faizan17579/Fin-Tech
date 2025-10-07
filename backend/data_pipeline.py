from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf
from apscheduler.schedulers.background import BackgroundScheduler
from pandas import DataFrame, Series
from sklearn.preprocessing import MinMaxScaler, StandardScaler

try:
    import talib as ta  # TA-Lib
except Exception:  # pragma: no cover - allow environments without TA-Lib compiled
    ta = None  # type: ignore

from database.db_manager import DatabaseManager


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@dataclass
class FetchParams:
    symbol: str
    interval: str = "1d"
    period: str = "1y"  # e.g., '1mo', '1y', '5y', 'max'
    asset_class: str = "stock"  # stock|crypto|forex (yfinance ticker format varies)


def fetch_market_data(params: FetchParams) -> DataFrame:
    ticker = params.symbol
    logger.info("Fetching data: symbol=%s interval=%s period=%s", ticker, params.interval, params.period)
    try:
        hist = yf.download(tickers=ticker, period=params.period, interval=params.interval, auto_adjust=False, progress=False)
        if hist is None or hist.empty:
            raise ValueError(f"No data returned for {ticker}")
        # Standardize column names
        # If yfinance returns MultiIndex (symbol level), drop the extra level
        if isinstance(hist.columns, pd.MultiIndex):
            try:
                hist.columns = hist.columns.droplevel(1)
            except Exception:
                hist.columns = [str(c) for c in hist.columns]

        hist = hist.rename(columns=str.lower)

        # Ensure index is datetime-like when possible
        try:
            hist.index = pd.to_datetime(hist.index)
        except Exception:
            # leave as-is; we'll attempt to coerce the date column below
            pass
        # Ensure required columns
        required = ["open", "high", "low", "close", "volume"]
        for col in required:
            if col not in hist.columns:
                hist[col] = np.nan
        # Reset index to expose date column, name varies across pandas/yfinance versions
        hist.reset_index(inplace=True)
        # Find the date column and normalize to 'timestamp'
        date_col = None
        # 1) Prefer any datetime-like column
        for col in hist.columns:
            try:
                if pd.api.types.is_datetime64_any_dtype(hist[col]):
                    date_col = col
                    break
            except Exception:
                continue
        # 2) Common name fallbacks (case-insensitive)
        if date_col is None:
            lower_map = {str(c).lower(): c for c in hist.columns}
            for candidate in ["timestamp", "date", "datetime", "index"]:
                if candidate in lower_map:
                    date_col = lower_map[candidate]
                    break
        # 3) Fallback to first column and try coercion to datetime if needed
        if date_col is None and len(hist.columns) > 0:
            candidate = hist.columns[0]
            # Try to coerce the candidate column to datetime in-place
            try:
                coerced = pd.to_datetime(hist[candidate], errors="coerce")
                # If coercion produced many non-nulls, accept it as the date column
                non_null_ratio = coerced.notna().mean()
                if non_null_ratio > 0.5:
                    hist[candidate] = coerced
                    date_col = candidate
                else:
                    # leave as last-resort candidate (will be renamed regardless)
                    date_col = candidate
            except Exception:
                date_col = candidate
        # Rename selected date column to 'timestamp' if needed
        if date_col is None:
            raise ValueError("No date column could be identified in fetched data")

        if str(date_col) != "timestamp":
            hist.rename(columns={date_col: "timestamp"}, inplace=True)

        # If timestamp column isn't datetime yet, try coercing it
        try:
            if not pd.api.types.is_datetime64_any_dtype(hist["timestamp"]):
                hist["timestamp"] = pd.to_datetime(hist["timestamp"], errors="coerce")
        except Exception:
            pass

        # Keep only timestamp + required
        if "timestamp" not in hist.columns:
            raise KeyError("timestamp column missing after processing")
        hist = hist[["timestamp", *required]]
        return hist
    except Exception as exc:
        logger.exception("Failed to fetch market data for %s: %s", ticker, exc)
        raise


def validate_and_clean(df: DataFrame) -> DataFrame:
    if df is None or df.empty:
        raise ValueError("Input DataFrame is empty")
    df = df.copy()
    # Drop duplicates and sort by time
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    # Forward fill missing OHLCV, then backfill remaining
    df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].replace([np.inf, -np.inf], np.nan)
    # Forward then backward fill (replaces deprecated fillna(method="ffill") chain)
    df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].ffill().bfill()
    # Ensure non-negative volume
    df["volume"] = df["volume"].clip(lower=0)
    return df


def add_technical_indicators(df: DataFrame, use_talib: bool = True) -> DataFrame:
    df = df.copy()
    close = df["close"].astype(float).values
    high = df["high"].astype(float).values
    low = df["low"].astype(float).values
    volume = df["volume"].astype(float).values

    if use_talib and ta is not None:
        # RSI, MACD, Bollinger Bands, MAs
        df["rsi_14"] = ta.RSI(close, timeperiod=14)
        macd, macdsignal, macdhist = ta.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
        df["macd"] = macd
        df["macd_signal"] = macdsignal
        df["macd_hist"] = macdhist
        upper, middle, lower = ta.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
        df["bb_upper"] = upper
        df["bb_middle"] = middle
        df["bb_lower"] = lower
        df["sma_20"] = ta.SMA(close, timeperiod=20)
        df["ema_50"] = ta.EMA(close, timeperiod=50)
        # Volume indicators
        df["obv"] = ta.OBV(close, volume)
        # Price patterns (example: candlestick patterns)
        df["cdl_doji"] = ta.CDLDOJI(open=df["open"].values, high=high, low=low, close=close)
    else:
        # Fallback simple implementations
        def rolling_mean(series: Series, window: int) -> Series:
            return series.rolling(window=window, min_periods=1).mean()

        def ema(series: Series, span: int) -> Series:
            return series.ewm(span=span, adjust=False).mean()

        # RSI simple implementation
        delta = pd.Series(close).diff()
        up = delta.clip(lower=0)
        down = -1 * delta.clip(upper=0)
        roll_up = up.rolling(14).mean()
        roll_down = down.rolling(14).mean()
        rs = roll_up / (roll_down.replace(0, np.nan))
        df["rsi_14"] = 100.0 - (100.0 / (1.0 + rs))

        # MACD
        ema12 = pd.Series(close).ewm(span=12, adjust=False).mean()
        ema26 = pd.Series(close).ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        df["macd"] = macd
        df["macd_signal"] = signal
        df["macd_hist"] = macd - signal

        # Bollinger Bands
        mavg = pd.Series(close).rolling(window=20, min_periods=1).mean()
        mstd = pd.Series(close).rolling(window=20, min_periods=1).std(ddof=0)
        df["bb_middle"] = mavg
        df["bb_upper"] = mavg + 2 * mstd
        df["bb_lower"] = mavg - 2 * mstd

        # MAs
        df["sma_20"] = rolling_mean(pd.Series(close), 20)
        df["ema_50"] = ema(pd.Series(close), 50)

        # OBV
        direction = np.sign(np.diff(np.concatenate([[close[0]], close])))
        df["obv"] = (direction * pd.Series(volume)).cumsum()

        # Simple doji detector
        body = (df["open"] - df["close"]).abs()
        range_ = (df["high"] - df["low"]).replace(0, np.nan)
        df["cdl_doji"] = (body / range_ < 0.1).astype(int)

    # Fill initial NaNs introduced by indicators
    # Replace deprecated fillna(method=...) pattern
    df = df.bfill().ffill()
    return df


def scale_features(df: DataFrame, feature_cols: List[str], method: str = "standard") -> Tuple[DataFrame, object]:
    df = df.copy()
    scaler: object
    if method == "minmax":
        scaler = MinMaxScaler()
    else:
        scaler = StandardScaler()
    df[feature_cols] = scaler.fit_transform(df[feature_cols])
    return df, scaler


def timeseries_train_test_split(df: DataFrame, test_size: float = 0.2) -> Tuple[DataFrame, DataFrame]:
    if not 0.0 < test_size < 1.0:
        raise ValueError("test_size must be between 0 and 1")
    n = len(df)
    split = int(n * (1 - test_size))
    train = df.iloc[:split].copy()
    test = df.iloc[split:].copy()
    return train, test


def build_feature_pipeline(params: FetchParams, use_talib: bool = True) -> DataFrame:
    raw = fetch_market_data(params)
    clean = validate_and_clean(raw)
    feats = add_technical_indicators(clean, use_talib=use_talib)
    return feats


_scheduler: Optional[BackgroundScheduler] = None


def _update_symbol(symbol: str, db: DatabaseManager) -> None:
    try:
        params = FetchParams(symbol=symbol, interval="1h", period="90d")
        df = build_feature_pipeline(params)
        for _, row in df.iterrows():
            db.create_historical_price(
                symbol=symbol,
                timestamp=pd.to_datetime(row["timestamp"]).to_pydatetime(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
        logger.info("Updated %s rows for %s", len(df), symbol)
    except Exception:
        logger.exception("Failed to update symbol: %s", symbol)


def start_hourly_updates(symbols: List[str]) -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        logger.info("Scheduler already running")
        return
    db = DatabaseManager()
    _scheduler = BackgroundScheduler()
    for sym in symbols:
        _scheduler.add_job(lambda s=sym: _update_symbol(s, db), "interval", hours=1, id=f"update_{sym}")
    _scheduler.start()
    logger.info("APScheduler started with %d symbols", len(symbols))


__all__ = [
    "FetchParams",
    "fetch_market_data",
    "validate_and_clean",
    "add_technical_indicators",
    "scale_features",
    "timeseries_train_test_split",
    "build_feature_pipeline",
    "start_hourly_updates",
]


