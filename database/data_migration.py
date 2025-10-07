from __future__ import annotations

import logging
from datetime import datetime

from .db_manager import DatabaseManager


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_initial_setup() -> None:
    db = DatabaseManager()
    db.create_indexes()
    logger.info("Indexes created for mode=%s", db.mode)

    # Seed minimal demo data to validate schema
    now = datetime.utcnow()
    db.create_historical_price(
        symbol="AAPL",
        timestamp=now,
        open=100.0,
        high=110.0,
        low=95.0,
        close=105.0,
        volume=1_000_000,
    )

    db.create_forecast(
        symbol="AAPL",
        timestamp=now,
        forecast_horizon=7,
        predicted_values=[101.0, 102.0, 103.5, 104.0, 104.5, 105.0, 105.5],
        model_used="baseline-naive",
        metrics={"mae": 1.23},
    )

    db.upsert_model_metadata(
        model_name="baseline-naive",
        training_date=now,
        parameters={"lookback": 1},
        performance_metrics={"mae": 1.23},
    )

    logger.info("Initial data seeded.")


if __name__ == "__main__":
    run_initial_setup()


