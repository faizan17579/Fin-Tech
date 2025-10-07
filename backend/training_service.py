from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from apscheduler.schedulers.background import BackgroundScheduler

from database.db_manager import DatabaseManager
from ML_models.traditional_models import (
    ARIMAModel,
    HoltWintersModel,
    SMAModel,
    EMAModel,
    WMAModel,
)
from ML_models.neural_models import LSTMForecaster, LSTMConfig


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@dataclass
class TrainingConfig:
    symbols: List[str]
    report_dir: str = "reports"
    window_size: int = 48
    horizon: int = 24
    min_history: int = 300
    alert_threshold_mape: float = 25.0  # percent
    schedule_hour_utc: int = 2


def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    eps = 1e-8
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    mae = float(np.mean(np.abs(y_true - y_pred)))
    mape = float(np.mean(np.abs((y_true - y_pred) / (np.abs(y_true) + eps))) * 100.0)
    return {"rmse": rmse, "mae": mae, "mape": mape}


class TrainingService:
    def __init__(self, config: TrainingConfig, db: Optional[DatabaseManager] = None) -> None:
        self.config = config
        self.db = db or DatabaseManager()
        self.scheduler: Optional[BackgroundScheduler] = None
        Path(self.config.report_dir).mkdir(parents=True, exist_ok=True)

    # ---------------- Scheduling ----------------
    def schedule_daily_retraining(self) -> None:
        if self.scheduler and self.scheduler.running:
            logger.info("Retraining scheduler already running")
            return
        self.scheduler = BackgroundScheduler()
        # Run daily at configured hour UTC
        self.scheduler.add_job(self.retrain_all_symbols, "cron", hour=self.config.schedule_hour_utc)
        self.scheduler.start()
        logger.info("Daily retraining scheduled at %02d:00 UTC", self.config.schedule_hour_utc)

    def retrain_all_symbols(self) -> None:
        for symbol in self.config.symbols:
            try:
                self.retrain_symbol(symbol)
            except Exception:
                logger.exception("Failed retraining for %s", symbol)

    # ---------------- Core Training ----------------
    def _load_series(self, symbol: str) -> pd.Series:
        rows = self.db.get_historical_prices(symbol=symbol, limit=100000)
        if not rows:
            raise RuntimeError(f"No historical data for {symbol}")
        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp")
        series = pd.Series(df["close"].astype(float).values, index=df["timestamp"], name="close")
        return series

    def retrain_symbol(self, symbol: str) -> None:
        series = self._load_series(symbol)
        if len(series) < self.config.min_history:
            logger.warning("Insufficient history for %s (%d < %d)", symbol, len(series), self.config.min_history)
            return

        train = series.iloc[:-self.config.horizon]
        test = series.iloc[-self.config.horizon :]

        # Train candidate models
        candidates: List[Tuple[str, Any, Dict[str, float]]] = []

        arima = ARIMAModel(seasonal=False)
        arima.fit(train)
        metrics_arima = arima.evaluate(test)
        candidates.append(("ARIMA", arima, metrics_arima))

        hw = HoltWintersModel(seasonal="add", seasonal_periods=7, grid_search=False)
        hw.fit(train)
        metrics_hw = hw.evaluate(test)
        candidates.append(("HoltWinters", hw, metrics_hw))

        sma = SMAModel(window=20).fit(train)
        candidates.append(("SMA20", sma, sma.evaluate(test)))
        ema = EMAModel(span=20).fit(train)
        candidates.append(("EMA20", ema, ema.evaluate(test)))
        wma = WMAModel(window=20).fit(train)
        candidates.append(("WMA20", wma, wma.evaluate(test)))

        # LSTM
        cfg = LSTMConfig(window_size=self.config.window_size, horizon=self.config.horizon, use_attention=True)
        lstm = LSTMForecaster(cfg).fit(train, epochs=20, batch_size=32, validation_split=0.1)
        metrics_lstm = lstm.evaluate(series.iloc[-(self.config.window_size + self.config.horizon) :])
        candidates.append(("LSTM", lstm, metrics_lstm))

        # Select best by MAPE
        best_name, best_model, best_metrics = min(candidates, key=lambda x: x[2]["mape"])
        logger.info("Best model for %s: %s (metrics=%s)", symbol, best_name, best_metrics)

        # Persist model metadata and drift tracking
        self._save_model_version(symbol, best_name, best_metrics, parameters={"timestamp": datetime.now(timezone.utc).isoformat()})

        # Drift detection: compare best mape to previous version
        drift = self.detect_drift(symbol, best_name, best_metrics)
        if drift:
            self._send_alert(symbol, best_name, best_metrics)

        # Generate training report
        self._create_report(symbol, candidates, best_name)

    # ---------------- Backtesting ----------------
    def backtest_model(self, symbol: str, model_name: str, splits: int = 5) -> Dict[str, float]:
        series = self._load_series(symbol)
        tscv = TimeSeriesSplit(n_splits=splits)
        errors: List[float] = []
        idx = np.arange(len(series))
        for train_idx, test_idx in tscv.split(idx):
            train = series.iloc[train_idx]
            test = series.iloc[test_idx]
            model = self._instantiate_model(model_name)
            model.fit(train)
            m = model.evaluate(test)
            errors.append(m["mape"])
        return {"avg_mape": float(np.mean(errors)), "std_mape": float(np.std(errors, ddof=1))}

    # ---------------- Drift ----------------
    def detect_drift(self, symbol: str, model_name: str, current_metrics: Dict[str, float]) -> bool:
        prev = self.db.get_latest_model_metadata(f"{symbol}:{model_name}")
        if not prev:
            return False
        prev_mape = float(prev.get("performance_metrics", {}).get("mape", current_metrics["mape"]))
        drift = current_metrics["mape"] - prev_mape
        logger.info("Drift for %s %s: %.3f (prev=%.3f curr=%.3f)", symbol, model_name, drift, prev_mape, current_metrics["mape"])
        return current_metrics["mape"] > self.config.alert_threshold_mape

    def _send_alert(self, symbol: str, model_name: str, metrics: Dict[str, float]) -> None:
        logger.warning("ALERT: %s model %s MAPE %.2f exceeded threshold %.2f", symbol, model_name, metrics["mape"], self.config.alert_threshold_mape)

    # ---------------- A/B Testing ----------------
    def ab_test(self, symbol: str, model_a: str, model_b: str) -> Dict[str, Any]:
        series = self._load_series(symbol)
        train = series.iloc[:-self.config.horizon]
        test = series.iloc[-self.config.horizon :]
        A = self._instantiate_model(model_a).fit(train).evaluate(test)
        B = self._instantiate_model(model_b).fit(train).evaluate(test)
        winner = model_a if A["mape"] <= B["mape"] else model_b
        return {"A": A, "B": B, "winner": winner}

    # ---------------- Versioning ----------------
    def _save_model_version(self, symbol: str, model_name: str, metrics: Dict[str, float], parameters: Dict[str, Any]) -> None:
        tag = f"{symbol}:{model_name}"
        self.db.upsert_model_metadata(model_name=tag, training_date=datetime.now(timezone.utc), parameters=parameters, performance_metrics=metrics)

    # ---------------- Reports ----------------
    def _create_report(self, symbol: str, candidates: List[Tuple[str, Any, Dict[str, float]]], best_name: str) -> None:
        names = [n for n, _, _ in candidates]
        mapes = [m["mape"] for _, _, m in candidates]
        fig = go.Figure([go.Bar(x=names, y=mapes)])
        fig.update_layout(title=f"Model MAPE comparison - {symbol}", xaxis_title="Model", yaxis_title="MAPE (%)")
        out = Path(self.config.report_dir) / f"report_{symbol}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.html"
        fig.write_html(str(out))
        logger.info("Saved report: %s", out)

    # ---------------- Helpers ----------------
    def _instantiate_model(self, name: str):
        name = name.lower()
        if name in ("arima",):
            return ARIMAModel()
        if name in ("holtwinters", "hw", "es"):
            return HoltWintersModel(seasonal="add", seasonal_periods=7, grid_search=False)
        if name.startswith("sma"):
            window = int(name.replace("sma", "") or 20)
            return SMAModel(window=window)
        if name.startswith("ema"):
            span = int(name.replace("ema", "") or 20)
            return EMAModel(span=span)
        if name.startswith("wma"):
            window = int(name.replace("wma", "") or 20)
            return WMAModel(window=window)
        if name in ("lstm",):
            cfg = LSTMConfig(window_size=self.config.window_size, horizon=self.config.horizon, use_attention=True)
            return LSTMForecaster(cfg)
        raise ValueError(f"Unknown model name: {name}")


__all__ = ["TrainingConfig", "TrainingService"]


