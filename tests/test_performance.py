import time
import numpy as np
import pandas as pd
from ML_models.traditional_models import ARIMAModel


def test_arima_training_time_under_limit():
    n = 180
    idx = pd.date_range('2024-01-01', periods=n, freq='D')
    y = pd.Series(np.sin(np.linspace(0, 20, n)) + np.linspace(10, 11, n), index=idx)
    model = ARIMAModel(seasonal=False, max_p=2, max_q=2)
    t0 = time.time()
    model.fit(y)
    elapsed = time.time() - t0
    assert elapsed < 15.0


