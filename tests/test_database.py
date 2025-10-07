from datetime import datetime, timezone
from database.db_manager import DatabaseManager


def test_db_crud_sqlite():
    db = DatabaseManager(mongo_uri="mongodb://invalid", sqlite_uri="sqlite:///:memory:")
    db.create_indexes()

    ts = datetime.now(timezone.utc)
    hid = db.create_historical_price("AAPL", ts, 1, 2, 0.5, 1.5, 100)
    assert hid is not None

    rows = db.get_historical_prices("AAPL")
    assert len(rows) >= 1

    fid = db.create_forecast("AAPL", ts, 3, [1.0, 1.1, 1.2], "baseline", {"mae": 0.1})
    assert fid is not None

    ok = db.update_forecast_metrics(fid, {"mae": 0.2})
    assert ok is True

    latest = db.get_forecasts("AAPL", limit=1)
    assert latest and latest[0].get("metrics") is not None

    mid = db.upsert_model_metadata("baseline-naive", ts, {"p": 1}, {"mae": 0.2})
    assert mid is not None


