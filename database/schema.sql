-- Basic DDL for a forecasts table (for SQL engines via SQLAlchemy)
CREATE TABLE IF NOT EXISTS forecasts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker TEXT NOT NULL,
  horizon INTEGER NOT NULL,
  forecast_json TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


