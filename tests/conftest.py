import os
import types
import pytest
import pandas as pd


@pytest.fixture(autouse=True)
def _force_sqlite(monkeypatch):
    os.environ["MONGO_URI"] = "mongodb://invalid:27017/finforecast"
    os.environ["SQLITE_URI"] = "sqlite:///:memory:"
    yield


@pytest.fixture()
def app_client():
    from backend.app import create_app

    test_app = create_app()
    test_app.config.update(TESTING=True)
    return test_app.test_client()


@pytest.fixture()
def yf_mock_df():
    idx = pd.date_range("2024-01-01", periods=10, freq="D")
    df = pd.DataFrame(
        {
            "Open": [100 + i for i in range(10)],
            "High": [102 + i for i in range(10)],
            "Low": [99 + i for i in range(10)],
            "Close": [101 + i for i in range(10)],
            "Volume": [1000 + 10 * i for i in range(10)],
        },
        index=idx,
    )
    return df


@pytest.fixture()
def patch_yfinance(monkeypatch, yf_mock_df):
    import yfinance as yf

    def fake_download(*args, **kwargs):
        return yf_mock_df

    monkeypatch.setattr(yf, "download", fake_download)
    yield


