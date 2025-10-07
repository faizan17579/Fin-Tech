from __future__ import annotations

from typing import Dict

import pandas as pd

from backend.data_pipeline import build_feature_pipeline, FetchParams


def create_curator_dataset(exchange: str, symbol: str, days: int) -> Dict:
    # Build feature dataset using existing pipeline (structured)
    params = FetchParams(symbol=symbol, interval="1d", period=f"{max(days, 5)}d")
    feats = build_feature_pipeline(params)

    # Minimal metadata to keep compatible with FinTechDataCurator expectations
    metadata = {
        "symbol": symbol,
        "exchange": exchange,
        "asset_type": "crypto" if exchange.upper() == "CRYPTO" else "stocks",
        "days_collected": int(min(len(feats), days)),
    }

    # Convert to list of dicts
    feats = feats.tail(days).reset_index(drop=True)
    data_records = feats.rename(columns={"timestamp": "Date", "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}).to_dict(orient="records")

    dataset = {"metadata": metadata, "data": data_records, "news_summary": "news collection disabled in UI"}
    return dataset


