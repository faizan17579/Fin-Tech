from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from numpy.typing import ArrayLike
from pandas import DataFrame
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import TimeSeriesSplit


def _metrics(y_true: ArrayLike, y_pred: ArrayLike) -> Dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mae = float(mean_absolute_error(y_true, y_pred))
    eps = 1e-8
    mape = float(np.mean(np.abs((y_true - y_pred) / (np.abs(y_true) + eps))) * 100.0)
    return {"rmse": rmse, "mae": mae, "mape": mape}


@dataclass
class EnsembleConfig:
    method: str = "weighted"  # weighted|stacking|voting
    # initial weights for weighted averaging; if None, equal weights
    weights: Optional[List[float]] = None
    # meta-learner for stacking
    meta_learner: Any = field(default_factory=lambda: LinearRegression(positive=True))
    # rolling window for dynamic weight updates
    recent_window: int = 100
    # confidence interval z-score (approx 95% ~ 1.96)
    ci_z: float = 1.96


class EnsembleModel:
    """Flexible ensemble for time series forecasts supporting weighted, stacking, and voting.

    - Weighted: uses weights (learned or provided) to average per-horizon predictions.
    - Stacking: trains a meta-learner on base predictions to produce final forecast.
    - Voting: median (robust) across models.
    - Dynamic weights: adjusted inversely to recent RMSE per model.
    - Confidence intervals: empirical using base-model prediction dispersion.
    """

    def __init__(self, config: Optional[EnsembleConfig] = None) -> None:
        self.config = config or EnsembleConfig()
        self.models: List[Any] = []
        self.model_names: List[str] = []
        self.learned_weights_: Optional[np.ndarray] = None
        self.meta_learner_ = None
        self.contributions_: Optional[Dict[str, float]] = None

    def add_model(self, model: Any, name: Optional[str] = None) -> None:
        self.models.append(model)
        self.model_names.append(name or model.__class__.__name__)

    # ---------------------- Fit ----------------------
    def fit(self, X: DataFrame, y: ArrayLike) -> "EnsembleModel":
        # X: DataFrame with columns per model prediction at each time point (horizon 1 training)
        # y: true values aligned to rows of X
        if self.config.method == "stacking":
            self.meta_learner_ = self.config.meta_learner
            self.meta_learner_.fit(X.values, np.asarray(y))
        elif self.config.method == "weighted":
            # Learn non-negative weights by solving least-squares with positivity via LinearRegression positive
            reg = LinearRegression(positive=True)
            reg.fit(X.values, np.asarray(y))
            w = np.abs(reg.coef_)
            if w.sum() == 0:
                w = np.ones_like(w)
            self.learned_weights_ = (w / w.sum()).astype(float)
        # Voting needs no training
        return self

    # ---------------------- Predict ----------------------
    def predict(
        self,
        base_predictions: List[np.ndarray],
        dynamic_recent_true: Optional[np.ndarray] = None,
        dynamic_recent_preds: Optional[List[np.ndarray]] = None,
    ) -> Tuple[np.ndarray, Tuple[np.ndarray, np.ndarray], Dict[str, float]]:
        """Combine base model predictions.

        - base_predictions: list of arrays shaped (horizon,) from each model
        - dynamic_recent_true: recent true values (n_recent,)
        - dynamic_recent_preds: list of arrays (n_recent,) per model for dynamic weighting

        Returns: (yhat, (lower, upper), contributions)
        """
        if not base_predictions:
            raise ValueError("No base predictions provided")
        horizon = int(base_predictions[0].shape[0])
        P = np.stack(base_predictions, axis=0)  # (n_models, horizon)

        if self.config.method == "voting":
            yhat = np.median(P, axis=0)
        elif self.config.method == "stacking":
            if self.meta_learner_ is None:
                raise RuntimeError("Meta-learner not fitted")
            # Build features: columns per model for each horizon position
            # Predict horizon independently using the same meta-learner per step
            yhat = np.zeros(horizon)
            for h in range(horizon):
                Xh = P[:, h].reshape(1, -1)
                yhat[h] = float(self.meta_learner_.predict(Xh))
        else:  # weighted
            weights = self._get_weights(P, dynamic_recent_true, dynamic_recent_preds)
            yhat = weights @ P  # (n_models,) @ (n_models, horizon) -> (horizon,)

        # Confidence intervals from empirical dispersion across models
        mu = np.mean(P, axis=0)
        std = np.std(P, axis=0, ddof=1) if P.shape[0] > 1 else np.zeros_like(mu)
        lower = mu - self.config.ci_z * std
        upper = mu + self.config.ci_z * std

        # Contributions (Shapley-like via weighted share or median proximity)
        contributions = self._compute_contributions(P, yhat)
        return yhat, (lower, upper), contributions

    # ---------------------- Dynamic Weights ----------------------
    def _get_weights(
        self,
        P: np.ndarray,
        recent_true: Optional[np.ndarray],
        recent_preds: Optional[List[np.ndarray]],
    ) -> np.ndarray:
        n_models = P.shape[0]
        if self.config.weights is not None:
            w = np.asarray(self.config.weights, dtype=float)
        elif self.learned_weights_ is not None:
            w = np.asarray(self.learned_weights_, dtype=float)
        else:
            w = np.ones(n_models, dtype=float) / n_models

        # Adjust weights based on recent performance (inverse RMSE)
        if recent_true is not None and recent_preds is not None and len(recent_preds) == n_models:
            rmses = []
            for i in range(n_models):
                if len(recent_true) != len(recent_preds[i]):
                    continue
                rmse = float(np.sqrt(mean_squared_error(recent_true, recent_preds[i])))
                rmses.append(rmse if rmse > 1e-8 else 1e-8)
            if rmses:
                inv = 1.0 / np.asarray(rmses)
                inv = inv / inv.sum()
                # blend learned/provided weights with performance-based weights
                w = 0.5 * w / w.sum() + 0.5 * inv

        w = np.clip(w, 1e-8, None)
        w = w / w.sum()
        self.contributions_ = {name: float(wi) for name, wi in zip(self.model_names, w)}
        return w

    def _compute_contributions(self, P: np.ndarray, yhat: np.ndarray) -> Dict[str, float]:
        if self.config.method == "voting":
            # distance to median
            med = np.median(P, axis=0)
            d = np.mean(np.abs(P - med[None, :]), axis=1)
            s = d.sum() or 1.0
            contrib = 1.0 - d / s
            contrib = contrib / contrib.sum()
        elif self.config.method == "stacking":
            # approximate by correlation with yhat
            corr = []
            for i in range(P.shape[0]):
                if np.std(P[i]) < 1e-8 or np.std(yhat) < 1e-8:
                    corr.append(0.0)
                else:
                    corr.append(float(np.corrcoef(P[i], yhat)[0, 1]))
            contrib = np.maximum(0.0, np.asarray(corr))
            s = contrib.sum() or 1.0
            contrib = contrib / s
        else:
            # weighted averaging: contributions equal to weights
            w = np.asarray(list(self.contributions_.values())) if self.contributions_ else np.ones(P.shape[0]) / P.shape[0]
            contrib = w
        return {name: float(v) for name, v in zip(self.model_names, contrib)}


__all__ = ["EnsembleConfig", "EnsembleModel"]


