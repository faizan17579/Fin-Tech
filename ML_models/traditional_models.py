from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

import joblib
import numpy as np
import pandas as pd
from numpy.typing import ArrayLike
from pandas import DataFrame, Series
from sklearn.base import BaseEstimator, RegressorMixin, clone
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit

# ARIMA (optional)
try:
    from pmdarima.arima import auto_arima  # type: ignore
except Exception:  # pragma: no cover - allow environments without pmdarima compiled
    auto_arima = None  # type: ignore

# VAR
from statsmodels.tsa.api import VAR

# Holt-Winters
from statsmodels.tsa.holtwinters import ExponentialSmoothing

# Prophet
try:
    from prophet import Prophet
except Exception:  # pragma: no cover - allow environments without prophet installed
    Prophet = None  # type: ignore


# ------------------------------ Utilities ------------------------------


def _to_series(data: Union[Series, DataFrame, ArrayLike]) -> Series:
    if isinstance(data, Series):
        return data
    if isinstance(data, DataFrame):
        if data.shape[1] != 1:
            raise ValueError("Expected single-column DataFrame for univariate series")
        return data.iloc[:, 0]
    return pd.Series(np.asarray(data))


def _to_frame(data: Union[DataFrame, Series, ArrayLike], columns: Optional[List[str]] = None) -> DataFrame:
    if isinstance(data, DataFrame):
        return data
    if isinstance(data, Series):
        return data.to_frame(name=columns[0] if columns else data.name)
    arr = np.asarray(data)
    if arr.ndim == 1:
        return pd.DataFrame(arr, columns=columns or ["y"])
    return pd.DataFrame(arr, columns=columns)


def _compute_metrics(y_true: ArrayLike, y_pred: ArrayLike) -> Dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mae = float(mean_absolute_error(y_true, y_pred))
    # MAPE with epsilon to avoid div by zero
    eps = 1e-8
    mape = float(np.mean(np.abs((y_true - y_pred) / (np.abs(y_true) + eps))) * 100.0)
    return {"rmse": rmse, "mae": mae, "mape": mape}


# ------------------------------ Base Class ------------------------------


class TimeSeriesModel:
    """Base interface for time series models."""

    def fit(self, train_data: Union[Series, DataFrame]) -> "TimeSeriesModel":  # noqa: D401
        raise NotImplementedError

    def predict(self, horizon: int) -> Union[Series, DataFrame]:  # noqa: D401
        raise NotImplementedError

    def evaluate(self, test_data: Union[Series, DataFrame]) -> Dict[str, float]:  # noqa: D401
        raise NotImplementedError

    def save(self, file_path: str) -> None:  # noqa: D401
        joblib.dump(self, file_path)

    @staticmethod
    def load(file_path: str) -> "TimeSeriesModel":  # noqa: D401
        return joblib.load(file_path)


# ------------------------------ ARIMA (auto-ARIMA) ------------------------------


@dataclass
class ARIMAModel(TimeSeriesModel):
    seasonal: bool = False
    m: int = 1  # season length if seasonal
    information_criterion: str = "aic"
    max_p: int = 5
    max_q: int = 5
    max_d: int = 2
    max_P: int = 2
    max_Q: int = 2
    max_D: int = 1
    trace: bool = False

    _fitted_: Any = None
    _train_index_: Optional[pd.Index] = None

    def fit(self, train_data: Union[Series, DataFrame]) -> "ARIMAModel":
        if auto_arima is None:
            raise RuntimeError("pmdarima is not installed or incompatible with current numpy")
        y = _to_series(train_data).astype(float)
        self._train_index_ = y.index
        self._fitted_ = auto_arima(
            y,
            seasonal=self.seasonal,
            m=self.m,
            information_criterion=self.information_criterion,
            max_p=self.max_p,
            max_q=self.max_q,
            max_d=self.max_d,
            max_P=self.max_P,
            max_Q=self.max_Q,
            max_D=self.max_D,
            trace=self.trace,
            suppress_warnings=True,
            stepwise=True,
        )
        return self

    def predict(self, horizon: int) -> Series:
        if self._fitted_ is None:
            raise RuntimeError("Model is not fitted")
        fc = self._fitted_.predict(n_periods=horizon)
        return pd.Series(np.asarray(fc, dtype=float), name="yhat")

    def evaluate(self, test_data: Union[Series, DataFrame]) -> Dict[str, float]:
        y = _to_series(test_data).astype(float)
        yhat = self.predict(len(y))
        return _compute_metrics(y, yhat.values)


# ------------------------------ Moving Averages ------------------------------


@dataclass
class SMAModel(TimeSeriesModel):
    window: int = 10
    _last_train_: Optional[Series] = None

    def fit(self, train_data: Union[Series, DataFrame]) -> "SMAModel":
        y = _to_series(train_data).astype(float)
        self._last_train_ = y
        return self

    def predict(self, horizon: int) -> Series:
        if self._last_train_ is None:
            raise RuntimeError("Model is not fitted")
        rolling_mean = self._last_train_.rolling(self.window, min_periods=1).mean().iloc[-1]
        return pd.Series([float(rolling_mean)] * horizon, name="yhat")

    def evaluate(self, test_data: Union[Series, DataFrame]) -> Dict[str, float]:
        y = _to_series(test_data).astype(float)
        yhat = self.predict(len(y))
        return _compute_metrics(y, yhat.values)


@dataclass
class EMAModel(TimeSeriesModel):
    span: int = 10
    _last_train_: Optional[Series] = None

    def fit(self, train_data: Union[Series, DataFrame]) -> "EMAModel":
        y = _to_series(train_data).astype(float)
        self._last_train_ = y
        return self

    def predict(self, horizon: int) -> Series:
        if self._last_train_ is None:
            raise RuntimeError("Model is not fitted")
        ema = self._last_train_.ewm(span=self.span, adjust=False).mean().iloc[-1]
        return pd.Series([float(ema)] * horizon, name="yhat")

    def evaluate(self, test_data: Union[Series, DataFrame]) -> Dict[str, float]:
        y = _to_series(test_data).astype(float)
        yhat = self.predict(len(y))
        return _compute_metrics(y, yhat.values)


@dataclass
class WMAModel(TimeSeriesModel):
    window: int = 10
    _last_train_: Optional[Series] = None

    def fit(self, train_data: Union[Series, DataFrame]) -> "WMAModel":
        y = _to_series(train_data).astype(float)
        self._last_train_ = y
        return self

    def predict(self, horizon: int) -> Series:
        if self._last_train_ is None:
            raise RuntimeError("Model is not fitted")
        w = np.arange(1, self.window + 1)
        window_vals = self._last_train_.iloc[-self.window :].values
        if len(window_vals) < len(w):
            # pad on the left
            pad = np.full(len(w) - len(window_vals), window_vals[0])
            window_vals = np.concatenate([pad, window_vals])
        value = float(np.dot(window_vals, w) / w.sum())
        return pd.Series([value] * horizon, name="yhat")

    def evaluate(self, test_data: Union[Series, DataFrame]) -> Dict[str, float]:
        y = _to_series(test_data).astype(float)
        yhat = self.predict(len(y))
        return _compute_metrics(y, yhat.values)


# ------------------------------ VAR ------------------------------


class _VAREstimator(BaseEstimator, RegressorMixin):
    def __init__(self, lags: int = 1):
        self.lags = lags
        self.model_ = None
        self.results_ = None

    def fit(self, X: DataFrame, y: Optional[ArrayLike] = None):  # y unused; kept for API
        model = VAR(endog=X)
        self.results_ = model.fit(maxlags=self.lags)
        self.model_ = model
        return self

    def predict(self, X: DataFrame) -> np.ndarray:
        if self.results_ is None:
            raise RuntimeError("Model not fitted")
        steps = len(X)
        fc = self.results_.forecast(self.results_.y, steps=steps)
        return fc


@dataclass
class VARModel(TimeSeriesModel):
    lags: int = 1
    grid_search: bool = True
    param_grid: Optional[Dict[str, List[int]]] = None
    _fitted_: Optional[_VAREstimator] = None
    _columns_: Optional[List[str]] = None

    def fit(self, train_data: Union[DataFrame, Series]) -> "VARModel":
        X = _to_frame(train_data)
        self._columns_ = list(X.columns)
        if self.grid_search:
            estimator = _VAREstimator()
            grid = self.param_grid or {"lags": [1, 2, 3, 4, 5]}
            cv = TimeSeriesSplit(n_splits=min(5, len(X) // 10 or 2))
            gscv = GridSearchCV(estimator, grid, cv=cv, scoring="neg_mean_squared_error")
            gscv.fit(X, None)
            self.lags = int(gscv.best_params_["lags"])  # type: ignore[index]
        est = _VAREstimator(lags=self.lags)
        self._fitted_ = est.fit(X)
        return self

    def predict(self, horizon: int) -> DataFrame:
        if self._fitted_ is None or self._columns_ is None:
            raise RuntimeError("Model is not fitted")
        # Forecast based on last y values
        fc = self._fitted_.results_.forecast(self._fitted_.results_.y, steps=horizon)
        return pd.DataFrame(fc, columns=self._columns_)

    def evaluate(self, test_data: Union[DataFrame, Series]) -> Dict[str, float]:
        X = _to_frame(test_data)
        yhat = self.predict(len(X))
        # Use first column for metrics to keep consistent scalar metrics
        return _compute_metrics(X.iloc[:, 0].values, yhat.iloc[:, 0].values)


# ------------------------------ Holt-Winters (Exponential Smoothing) ------------------------------


@dataclass
class HoltWintersModel(TimeSeriesModel):
    trend: Optional[str] = "add"
    seasonal: Optional[str] = "add"
    seasonal_periods: Optional[int] = None
    grid_search: bool = True
    param_grid: Optional[Dict[str, List[Any]]] = None

    _fitted_: Any = None
    _train_index_: Optional[pd.Index] = None

    def fit(self, train_data: Union[Series, DataFrame]) -> "HoltWintersModel":
        y = _to_series(train_data).astype(float)
        self._train_index_ = y.index
        if self.grid_search:
            grid = self.param_grid or {
                "trend": [None, "add", "mul"],
                "seasonal": [None, "add", "mul"],
                "seasonal_periods": [None, 7, 12, 24],
            }
            best_score = math.inf
            best_params = {"trend": self.trend, "seasonal": self.seasonal, "seasonal_periods": self.seasonal_periods}
            tscv = TimeSeriesSplit(n_splits=min(5, len(y) // 10 or 2))
            for trend in grid["trend"]:
                for seasonal in grid["seasonal"]:
                    for sp in grid["seasonal_periods"]:
                        if seasonal is None and sp is not None:
                            continue
                        try:
                            scores: List[float] = []
                            for train_idx, val_idx in tscv.split(y):
                                yt, yv = y.iloc[train_idx], y.iloc[val_idx]
                                model = ExponentialSmoothing(yt, trend=trend, seasonal=seasonal, seasonal_periods=sp)
                                fit = model.fit(optimized=True)
                                yhat = fit.forecast(len(yv))
                                scores.append(mean_squared_error(yv, yhat))
                            score = float(np.mean(scores))
                            if score < best_score:
                                best_score = score
                                best_params = {"trend": trend, "seasonal": seasonal, "seasonal_periods": sp}
                        except Exception:
                            continue
            self.trend = best_params["trend"]
            self.seasonal = best_params["seasonal"]
            self.seasonal_periods = best_params["seasonal_periods"]
        model = ExponentialSmoothing(y, trend=self.trend, seasonal=self.seasonal, seasonal_periods=self.seasonal_periods)
        self._fitted_ = model.fit(optimized=True)
        return self

    def predict(self, horizon: int) -> Series:
        if self._fitted_ is None:
            raise RuntimeError("Model is not fitted")
        yhat = self._fitted_.forecast(horizon)
        return pd.Series(np.asarray(yhat, dtype=float), name="yhat")

    def evaluate(self, test_data: Union[Series, DataFrame]) -> Dict[str, float]:
        y = _to_series(test_data).astype(float)
        yhat = self.predict(len(y))
        return _compute_metrics(y, yhat.values)


# ------------------------------ Prophet ------------------------------


@dataclass
class ProphetModel(TimeSeriesModel):
    daily_seasonality: bool = True
    weekly_seasonality: bool = True
    yearly_seasonality: bool = True
    seasonality_mode: str = "additive"  # or "multiplicative"

    _model_: Any = None
    _last_train_: Optional[pd.DataFrame] = None

    def fit(self, train_data: Union[Series, DataFrame]) -> "ProphetModel":
        if Prophet is None:
            raise ImportError("prophet library is not installed")
        y = _to_series(train_data).astype(float)
        df = pd.DataFrame({"ds": y.index if isinstance(y.index, pd.DatetimeIndex) else pd.date_range(start=pd.Timestamp.today(), periods=len(y)), "y": y.values})
        self._model_ = Prophet(daily_seasonality=self.daily_seasonality, weekly_seasonality=self.weekly_seasonality, yearly_seasonality=self.yearly_seasonality, seasonality_mode=self.seasonality_mode)
        self._model_.fit(df)
        self._last_train_ = df
        return self

    def predict(self, horizon: int) -> Series:
        if self._model_ is None or self._last_train_ is None:
            raise RuntimeError("Model is not fitted")
        future = self._model_.make_future_dataframe(periods=horizon, include_history=False)
        forecast = self._model_.predict(future)
        return pd.Series(forecast["yhat"].values.astype(float), name="yhat")

    def evaluate(self, test_data: Union[Series, DataFrame]) -> Dict[str, float]:
        y = _to_series(test_data).astype(float)
        yhat = self.predict(len(y))
        return _compute_metrics(y, yhat.values)


__all__ = [
    "ARIMAModel",
    "SMAModel",
    "EMAModel",
    "WMAModel",
    "VARModel",
    "HoltWintersModel",
    "ProphetModel",
]


