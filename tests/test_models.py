import numpy as np
import pandas as pd
from ML_models.traditional_models import ARIMAModel, SMAModel, EMAModel, WMAModel, HoltWintersModel


def make_series(n=120):
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    y = np.sin(np.linspace(0, 10, n)) * 10 + np.linspace(50, 55, n)
    return pd.Series(y, index=idx)


def _basic_fit_predict_evaluate(model):
    s = make_series()
    train = s.iloc[:-7]
    test = s.iloc[-7:]
    model.fit(train)
    yhat = model.predict(7)
    assert len(yhat) == 7
    metrics = model.evaluate(test)
    assert "rmse" in metrics and metrics["rmse"] >= 0


def test_arima_basic():
    _basic_fit_predict_evaluate(ARIMAModel(seasonal=False, max_p=2, max_q=2))


def test_sma_basic():
    _basic_fit_predict_evaluate(SMAModel(window=10))


def test_ema_basic():
    _basic_fit_predict_evaluate(EMAModel(span=10))


def test_wma_basic():
    _basic_fit_predict_evaluate(WMAModel(window=10))


def test_holtwinters_basic():
    _basic_fit_predict_evaluate(HoltWintersModel(seasonal=None, grid_search=False))


