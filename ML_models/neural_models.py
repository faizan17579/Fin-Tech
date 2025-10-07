from __future__ import annotations

import json
import math
import os
import pathlib
import warnings
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple, Union

import joblib
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from numpy.typing import ArrayLike
from pandas import DataFrame, Series
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.preprocessing import MinMaxScaler, StandardScaler

import tensorflow as tf
from tensorflow.keras import Model
from tensorflow.keras.layers import LSTM, Dense, Dropout, Input, Layer, LayerNormalization
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint

try:
    import shap  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    shap = None  # type: ignore


def _to_frame(data: Union[Series, DataFrame, ArrayLike]) -> DataFrame:
    if isinstance(data, DataFrame):
        return data
    if isinstance(data, Series):
        return data.to_frame(name=data.name or "y")
    arr = np.asarray(data)
    if arr.ndim == 1:
        return pd.DataFrame(arr, columns=["y"])
    return pd.DataFrame(arr)


def _metrics(y_true: ArrayLike, y_pred: ArrayLike) -> Dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mae = float(mean_absolute_error(y_true, y_pred))
    eps = 1e-8
    mape = float(np.mean(np.abs((y_true - y_pred) / (np.abs(y_true) + eps))) * 100.0)
    return {"rmse": rmse, "mae": mae, "mape": mape}


class TemporalAttention(Layer):
    """Simple additive attention over time steps."""

    def __init__(self, units: int = 32, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.units = units
        self.W = Dense(units)
        self.v = Dense(1)

    def call(self, inputs: tf.Tensor) -> tf.Tensor:  # inputs: (batch, time, features)
        score = tf.nn.tanh(self.W(inputs))  # (batch, time, units)
        attention_weights = tf.nn.softmax(self.v(score), axis=1)  # (batch, time, 1)
        context_vector = tf.reduce_sum(attention_weights * inputs, axis=1)  # (batch, features)
        return context_vector

    def get_config(self) -> Dict[str, Any]:
        cfg = super().get_config()
        cfg.update({"units": self.units})
        return cfg


@dataclass
class LSTMConfig:
    window_size: int = 48
    horizon: int = 24
    lstm_layers: int = 2
    units: int = 64
    dropout: float = 0.2
    activation: str = "tanh"
    learning_rate: float = 1e-3
    use_attention: bool = True
    scaler: str = "standard"  # standard|minmax
    loss: str = "mse"
    metrics: Tuple[str, ...] = ("mae",)
    checkpoints: bool = True
    early_stopping_patience: int = 10


class LSTMForecaster:
    """LSTM-based time series forecaster with optional attention and SHAP analysis."""

    def __init__(self, config: Optional[LSTMConfig] = None) -> None:
        self.config = config or LSTMConfig()
        self.model: Optional[Model] = None
        self.scaler: Optional[Union[StandardScaler, MinMaxScaler]] = None
        self.feature_names: Optional[List[str]] = None
        self._history: Optional[tf.keras.callbacks.History] = None

    # -------------------- Preprocessing --------------------
    def _fit_scaler(self, X: DataFrame) -> None:
        if self.config.scaler == "minmax":
            self.scaler = MinMaxScaler()
        else:
            self.scaler = StandardScaler()
        self.scaler.fit(X.values)

    def _transform(self, X: DataFrame) -> np.ndarray:
        if self.scaler is None:
            self._fit_scaler(X)
        assert self.scaler is not None
        return self.scaler.transform(X.values)

    @staticmethod
    def _make_supervised(
        data: np.ndarray, window: int, horizon: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        X_list: List[np.ndarray] = []
        y_list: List[np.ndarray] = []
        for i in range(len(data) - window - horizon + 1):
            X_list.append(data[i : i + window, :])
            # Predict main target as the first feature by default
            y_list.append(data[i + window : i + window + horizon, 0])
        if not X_list:
            raise ValueError("Not enough data to create supervised windows")
        X = np.stack(X_list, axis=0)
        y = np.stack(y_list, axis=0)
        return X, y

    # -------------------- Model --------------------
    def _build_model(self, num_features: int) -> Model:
        cfg = self.config
        inputs = Input(shape=(cfg.window_size, num_features))

        x = inputs
        for i in range(cfg.lstm_layers):
            return_sequences = cfg.use_attention or (i < cfg.lstm_layers - 1)
            x = LSTM(cfg.units, activation=cfg.activation, return_sequences=return_sequences)(x)
            x = Dropout(cfg.dropout)(x)

        if cfg.use_attention:
            x = TemporalAttention(units=max(16, cfg.units // 2))(x)  # (batch, features)
        else:
            # If no attention and last layer returned sequences, take last timestep
            if len(x.shape) == 3:
                x = x[:, -1, :]

        x = LayerNormalization()(x)
        outputs = Dense(cfg.horizon, activation="linear")(x)

        model = tf.keras.models.Model(inputs=inputs, outputs=outputs)
        model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=cfg.learning_rate),
            loss=cfg.loss,
            metrics=list(cfg.metrics),
        )
        return model

    # -------------------- Public API --------------------
    def fit(
        self,
        train_data: Union[Series, DataFrame],
        epochs: int = 50,
        batch_size: int = 32,
        validation_split: float = 0.1,
        checkpoint_dir: str = "checkpoints",
    ) -> "LSTMForecaster":
        df = _to_frame(train_data)
        self.feature_names = list(df.columns)
        scaled = self._transform(df)
        X, y = self._make_supervised(scaled, self.config.window_size, self.config.horizon)

        self.model = self._build_model(num_features=scaled.shape[1])

        callbacks: List[tf.keras.callbacks.Callback] = [
            EarlyStopping(monitor="val_loss", patience=self.config.early_stopping_patience, restore_best_weights=True)
        ]
        if self.config.checkpoints:
            os.makedirs(checkpoint_dir, exist_ok=True)
            ckpt_path = os.path.join(checkpoint_dir, "lstm_best.keras")
            callbacks.append(ModelCheckpoint(ckpt_path, monitor="val_loss", save_best_only=True))

        self._history = self.model.fit(
            X,
            y,
            epochs=epochs,
            batch_size=batch_size,
            validation_split=validation_split,
            callbacks=callbacks,
            verbose=0,
        )
        return self

    def predict(self, horizon: Optional[int] = None, recent_window: Optional[Union[Series, DataFrame]] = None) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Model is not fitted")
        horizon = horizon or self.config.horizon
        if recent_window is None:
            raise ValueError("recent_window (last window segment) must be provided for prediction")
        dfw = _to_frame(recent_window)
        if dfw.shape[0] < self.config.window_size:
            raise ValueError("recent_window length is smaller than window_size")
        dfw = dfw.iloc[-self.config.window_size :]
        scaled = self._transform(dfw)
        X = np.expand_dims(scaled, axis=0)
        yhat_scaled = self.model.predict(X, verbose=0)[0]
        # Inverse transform only the target dimension (first feature)
        assert self.scaler is not None
        # Build a dummy array to inverse transform
        target_col = 0
        dummy = np.zeros((horizon, scaled.shape[1]))
        dummy[:, target_col] = yhat_scaled[:horizon]
        inv = self.scaler.inverse_transform(dummy)[:, target_col]
        return inv

    def evaluate(self, test_data: Union[Series, DataFrame]) -> Dict[str, float]:
        df = _to_frame(test_data)
        if self.scaler is None:
            self._fit_scaler(df)
        scaled = self._transform(df)
        X, y_true = self._make_supervised(scaled, self.config.window_size, self.config.horizon)
        if self.model is None:
            raise RuntimeError("Model is not fitted")
        y_pred_scaled = self.model.predict(X, verbose=0)
        # Compare only first horizon for each sample (flatten)
        target_col = 0
        # Inverse transform
        inv_true_list: List[np.ndarray] = []
        inv_pred_list: List[np.ndarray] = []
        for i in range(len(y_true)):
            dummy_true = np.zeros((self.config.horizon, scaled.shape[1]))
            dummy_pred = np.zeros((self.config.horizon, scaled.shape[1]))
            dummy_true[:, target_col] = y_true[i]
            dummy_pred[:, target_col] = y_pred_scaled[i]
            inv_true = self.scaler.inverse_transform(dummy_true)[:, target_col]
            inv_pred = self.scaler.inverse_transform(dummy_pred)[:, target_col]
            inv_true_list.append(inv_true)
            inv_pred_list.append(inv_pred)
        inv_true_arr = np.concatenate(inv_true_list)
        inv_pred_arr = np.concatenate(inv_pred_list)
        return _metrics(inv_true_arr, inv_pred_arr)

    # -------------------- Persistence --------------------
    def save(self, directory: str) -> None:
        if self.model is None:
            raise RuntimeError("Model is not fitted")
        path = pathlib.Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        # Save model
        self.model.save(path / "model.keras")
        # Save scaler
        if self.scaler is not None:
            joblib.dump(self.scaler, path / "scaler.pkl")
        # Save config and metadata
        meta = {"config": asdict(self.config), "feature_names": self.feature_names}
        with open(path / "meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f)

    @staticmethod
    def load(directory: str) -> "LSTMForecaster":
        path = pathlib.Path(directory)
        cfg_path = path / "meta.json"
        with open(cfg_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        config = LSTMConfig(**meta.get("config", {}))
        model = tf.keras.models.load_model(path / "model.keras", custom_objects={"TemporalAttention": TemporalAttention})
        inst = LSTMForecaster(config)
        inst.model = model
        scaler_path = path / "scaler.pkl"
        if scaler_path.exists():
            inst.scaler = joblib.load(scaler_path)
        inst.feature_names = meta.get("feature_names")
        return inst

    # -------------------- Visualization --------------------
    def plot_history(self) -> Optional[go.Figure]:
        if self._history is None:
            warnings.warn("No training history available")
            return None
        hist = self._history.history
        fig = go.Figure()
        if "loss" in hist:
            fig.add_trace(go.Scatter(y=hist["loss"], name="loss"))
        if "val_loss" in hist:
            fig.add_trace(go.Scatter(y=hist["val_loss"], name="val_loss"))
        fig.update_layout(title="Training History", xaxis_title="Epoch", yaxis_title="Loss")
        return fig

    # -------------------- Interpretability --------------------
    def shap_values(
        self,
        background_data: Union[Series, DataFrame],
        sample_data: Optional[Union[Series, DataFrame]] = None,
        max_background: int = 200,
        max_samples: int = 200,
    ) -> Optional[np.ndarray]:
        if shap is None:
            warnings.warn("shap is not installed; cannot compute SHAP values")
            return None
        if self.model is None:
            raise RuntimeError("Model is not fitted")
        bg_df = _to_frame(background_data)
        bg_scaled = self._transform(bg_df)
        X_bg, _ = self._make_supervised(bg_scaled, self.config.window_size, self.config.horizon)
        X_bg = X_bg[:max_background]

        if sample_data is None:
            X_samples = X_bg[:max_samples]
        else:
            sm_df = _to_frame(sample_data)
            sm_scaled = self._transform(sm_df)
            X_samples, _ = self._make_supervised(sm_scaled, self.config.window_size, self.config.horizon)
            X_samples = X_samples[:max_samples]

        try:
            explainer = shap.DeepExplainer(self.model, X_bg)
            sv = explainer.shap_values(X_samples)
            # sv can be a list for multi-output; return first output's SHAP values
            if isinstance(sv, list):
                return sv[0]
            return sv
        except Exception as exc:  # pragma: no cover - backend-specific
            warnings.warn(f"Failed to compute SHAP values: {exc}")
            return None


__all__ = [
    "LSTMConfig",
    "LSTMForecaster",
    "TemporalAttention",
]


