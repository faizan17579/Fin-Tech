import pandas as pd
from backend.data_pipeline import fetch_market_data, validate_and_clean, add_technical_indicators, timeseries_train_test_split, FetchParams


def test_fetch_and_process(monkeypatch, patch_yfinance):
    df = fetch_market_data(FetchParams(symbol="AAPL", period="1mo", interval="1d"))
    assert not df.empty
    assert set(["timestamp", "open", "high", "low", "close", "volume"]).issubset(df.columns)

    clean = validate_and_clean(df)
    assert not clean.isna().any().any()

    feats = add_technical_indicators(clean, use_talib=False)
    assert "rsi_14" in feats.columns

    train, test = timeseries_train_test_split(feats, test_size=0.2)
    assert len(train) + len(test) == len(feats)


