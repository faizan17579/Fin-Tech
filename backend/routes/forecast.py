from flask import Blueprint, request, jsonify

from ..services.model_service import generate_forecast


forecast_bp = Blueprint("forecast", __name__)


@forecast_bp.post("/")
def forecast_root():
    payload = request.get_json(silent=True) or {}
    ticker = payload.get("ticker", "AAPL")
    horizon = int(payload.get("horizon", 7))

    forecast_values = generate_forecast(ticker=ticker, horizon=horizon)
    return jsonify({"ticker": ticker, "horizon": horizon, "forecast": forecast_values})


