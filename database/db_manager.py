from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pymongo import ASCENDING, DESCENDING, MongoClient, errors as mongo_errors
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker


logger = logging.getLogger(__name__)


Base = declarative_base()


class HistoricalPrice(Base):
    __tablename__ = "historical_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(32), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)


Index("ix_hist_symbol_ts", HistoricalPrice.symbol, HistoricalPrice.timestamp)


class Forecast(Base):
    __tablename__ = "forecasts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(32), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    forecast_horizon = Column(Integer, nullable=False)
    predicted_values = Column(JSON, nullable=False)
    model_used = Column(String(128), nullable=False)
    metrics = Column(JSON, nullable=True)


Index("ix_forecast_symbol_ts", Forecast.symbol, Forecast.timestamp)


class ModelMetadata(Base):
    __tablename__ = "model_metadata"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String(128), nullable=False, index=True)
    training_date = Column(DateTime, nullable=False, index=True)
    parameters = Column(JSON, nullable=True)
    performance_metrics = Column(JSON, nullable=True)


Index(
    "ix_model_metadata_name_date",
    ModelMetadata.model_name,
    ModelMetadata.training_date.desc(),
)


class DatabaseManager:
    """Database manager with MongoDB primary and SQLite fallback.

    Provides CRUD operations for historical_prices, forecasts, and model_metadata,
    with connection pooling and index management.
    """

    def __init__(
        self,
        mongo_uri: Optional[str] = None,
        sqlite_uri: Optional[str] = None,
        mongo_db_name: str = "finforecast",
    ) -> None:
        self.mongo_uri = mongo_uri or os.getenv("MONGO_URI", "mongodb://localhost:27017/finforecast")
        self.sqlite_uri = sqlite_uri or os.getenv("SQLITE_URI", "sqlite:///finforecast.db")
        self.mongo_db_name = mongo_db_name

        self.mode: str = "sqlite"
        self.mongo_client: Optional[MongoClient] = None
        self.mongo_db = None
        self.engine = None
        self.SessionLocal = None

        self._connect()

    def _connect(self) -> None:
        # Try MongoDB first
        try:
            self.mongo_client = MongoClient(
                self.mongo_uri,
                serverSelectionTimeoutMS=2000,
                maxPoolSize=50,
                connectTimeoutMS=2000,
            )
            # Force server selection
            self.mongo_client.admin.command("ping")
            self.mongo_db = self.mongo_client.get_database(self.mongo_db_name)
            self.mode = "mongo"
            logger.info("Connected to MongoDB: %s", self.mongo_uri)
            return
        except mongo_errors.PyMongoError as exc:
            logger.warning("MongoDB not available, falling back to SQLite: %s", exc)

        # Fallback to SQLite via SQLAlchemy
        try:
            self.engine = create_engine(
                self.sqlite_uri,
                echo=False,
                pool_size=10,
                max_overflow=20,
                future=True,
            )
            self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)
            Base.metadata.create_all(self.engine)
            self.mode = "sqlite"
            logger.info("Connected to SQLite: %s", self.sqlite_uri)
        except SQLAlchemyError as exc:
            logger.error("Failed to initialize SQLite engine: %s", exc)
            raise

    # ------------------ Index Management ------------------
    def create_indexes(self) -> None:
        if self.mode == "mongo" and self.mongo_db is not None:
            self.mongo_db["historical_prices"].create_index([("symbol", ASCENDING), ("timestamp", ASCENDING)], name="ix_hist_symbol_ts")
            self.mongo_db["forecasts"].create_index([("symbol", ASCENDING), ("timestamp", ASCENDING)], name="ix_forecast_symbol_ts")
            self.mongo_db["forecasts"].create_index([("forecast_horizon", ASCENDING)], name="ix_forecast_horizon")
            self.mongo_db["model_metadata"].create_index([("model_name", ASCENDING), ("training_date", DESCENDING)], name="ix_model_name_date")
        elif self.mode == "sqlite":
            # Indexes are declared above and created with metadata.create_all
            pass

    # ------------------ Context Manager for Sessions ------------------
    @contextmanager
    def session_scope(self):
        if self.mode != "sqlite":
            # Mongo operations don't need SQLAlchemy session
            yield None
            return
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ------------------ CRUD: Historical Prices ------------------
    def create_historical_price(
        self,
        symbol: str,
        timestamp: datetime,
        open: float,
        high: float,
        low: float,
        close: float,
        volume: float,
    ) -> Any:
        doc = {
            "symbol": symbol,
            "timestamp": timestamp,
            "open": float(open),
            "high": float(high),
            "low": float(low),
            "close": float(close),
            "volume": float(volume),
        }
        if self.mode == "mongo":
            return self.mongo_db["historical_prices"].insert_one(doc).inserted_id
        with self.session_scope() as s:
            row = HistoricalPrice(**doc)
            s.add(row)
            s.flush()
            return row.id

    def get_historical_prices(self, symbol: str, start: Optional[datetime] = None, end: Optional[datetime] = None, limit: int = 1000) -> List[Dict[str, Any]]:
        if self.mode == "mongo":
            query: Dict[str, Any] = {"symbol": symbol}
            if start or end:
                ts: Dict[str, Any] = {}
                if start:
                    ts["$gte"] = start
                if end:
                    ts["$lte"] = end
                query["timestamp"] = ts
            cursor = self.mongo_db["historical_prices"].find(query).sort("timestamp", ASCENDING).limit(limit)
            return [self._convert_mongo_doc(d) for d in cursor]
        with self.session_scope() as s:
            q = s.query(HistoricalPrice).filter(HistoricalPrice.symbol == symbol)
            if start:
                q = q.filter(HistoricalPrice.timestamp >= start)
            if end:
                q = q.filter(HistoricalPrice.timestamp <= end)
            rows = q.order_by(HistoricalPrice.timestamp.asc()).limit(limit).all()
            return [self._row_to_dict(r) for r in rows]

    def delete_historical_prices_older_than(self, symbol: str, threshold: datetime) -> int:
        if self.mode == "mongo":
            res = self.mongo_db["historical_prices"].delete_many({"symbol": symbol, "timestamp": {"$lt": threshold}})
            return res.deleted_count
        with self.session_scope() as s:
            q = s.query(HistoricalPrice).filter(HistoricalPrice.symbol == symbol, HistoricalPrice.timestamp < threshold)
            count = q.count()
            q.delete(synchronize_session=False)
            return count

    # ------------------ CRUD: Forecasts ------------------
    def create_forecast(
        self,
        symbol: str,
        timestamp: datetime,
        forecast_horizon: int,
        predicted_values: List[float],
        model_used: str,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> Any:
        doc = {
            "symbol": symbol,
            "timestamp": timestamp,
            "forecast_horizon": int(forecast_horizon),
            "predicted_values": [float(v) for v in predicted_values],
            "model_used": model_used,
            "metrics": metrics or {},
        }
        if self.mode == "mongo":
            return self.mongo_db["forecasts"].insert_one(doc).inserted_id
        with self.session_scope() as s:
            row = Forecast(**doc)
            s.add(row)
            s.flush()
            return row.id

    def get_forecasts(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        if self.mode == "mongo":
            cursor = self.mongo_db["forecasts"].find({"symbol": symbol}).sort("timestamp", DESCENDING).limit(limit)
            return [self._convert_mongo_doc(d) for d in cursor]
        with self.session_scope() as s:
            rows = (
                s.query(Forecast)
                .filter(Forecast.symbol == symbol)
                .order_by(Forecast.timestamp.desc())
                .limit(limit)
                .all()
            )
            return [self._row_to_dict(r) for r in rows]

    def update_forecast_metrics(self, forecast_id: Any, metrics: Dict[str, Any]) -> bool:
        if self.mode == "mongo":
            res = self.mongo_db["forecasts"].update_one({"_id": forecast_id}, {"$set": {"metrics": metrics}})
            return res.modified_count > 0
        with self.session_scope() as s:
            row = s.query(Forecast).get(forecast_id)
            if not row:
                return False
            row.metrics = metrics
            return True

    def delete_forecast(self, forecast_id: Any) -> bool:
        if self.mode == "mongo":
            res = self.mongo_db["forecasts"].delete_one({"_id": forecast_id})
            return res.deleted_count > 0
        with self.session_scope() as s:
            row = s.query(Forecast).get(forecast_id)
            if not row:
                return False
            s.delete(row)
            return True

    # ------------------ CRUD: Model Metadata ------------------
    def upsert_model_metadata(
        self,
        model_name: str,
        training_date: datetime,
        parameters: Optional[Dict[str, Any]] = None,
        performance_metrics: Optional[Dict[str, Any]] = None,
    ) -> Any:
        doc = {
            "model_name": model_name,
            "training_date": training_date,
            "parameters": parameters or {},
            "performance_metrics": performance_metrics or {},
        }
        if self.mode == "mongo":
            return self.mongo_db["model_metadata"].update_one(
                {"model_name": model_name, "training_date": training_date},
                {"$set": doc},
                upsert=True,
            ).upserted_id
        with self.session_scope() as s:
            # Simple strategy: insert a new row
            row = ModelMetadata(**doc)
            s.add(row)
            s.flush()
            return row.id

    def get_latest_model_metadata(self, model_name: str) -> Optional[Dict[str, Any]]:
        if self.mode == "mongo":
            doc = self.mongo_db["model_metadata"].find_one(
                {"model_name": model_name}, sort=[("training_date", DESCENDING)]
            )
            return self._convert_mongo_doc(doc) if doc else None
        with self.session_scope() as s:
            row = (
                s.query(ModelMetadata)
                .filter(ModelMetadata.model_name == model_name)
                .order_by(ModelMetadata.training_date.desc())
                .first()
            )
            return self._row_to_dict(row) if row else None

    # ------------------ Utilities ------------------
    @staticmethod
    def _row_to_dict(row: Any) -> Dict[str, Any]:
        if row is None:
            return {}
        result: Dict[str, Any] = {}
        for col in row.__table__.columns:  # type: ignore[attr-defined]
            value = getattr(row, col.name)
            # SQLAlchemy JSON already yields Python objects
            result[col.name] = value
        return result

    @staticmethod
    def _convert_mongo_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
        if not doc:
            return {}
        d = dict(doc)
        # Convert ObjectId to str for portability
        _id = d.get("_id")
        if _id is not None:
            d["_id"] = str(_id)
        return d


__all__ = [
    "DatabaseManager",
]


