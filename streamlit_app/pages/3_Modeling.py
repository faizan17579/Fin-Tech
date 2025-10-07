import streamlit as st
import numpy as np
import pandas as pd
from pathlib import Path
from typing import List

from backend.training_service import TrainingConfig, TrainingService
from database.db_manager import DatabaseManager


st.set_page_config(page_title="Modeling", page_icon="🤖", layout="wide")

st.title("🤖 Modeling")

symbol = st.session_state.get("selected_symbol")
if not symbol:
    st.warning("Go back to Home and select a ticker first.")
    st.stop()

st.write("Selected:", symbol)

db = DatabaseManager()

with st.form("train_form"):
    models = st.multiselect(
        "Select models",
        ["ARIMA", "HoltWinters", "SMA20", "EMA20", "WMA20", "LSTM"],
        default=["ARIMA", "LSTM"],
    )
    horizon = st.slider("Forecast horizon", min_value=5, max_value=60, value=24, step=1)
    window = st.slider("Window size (LSTM)", min_value=24, max_value=256, value=48, step=8)
    submitted = st.form_submit_button("Train & Evaluate")

if submitted:
    cfg = TrainingConfig(symbols=[symbol], window_size=int(window), horizon=int(horizon))
    svc = TrainingService(cfg, db=db)
    series = svc._load_series(symbol)
    train = series.iloc[:-cfg.horizon]
    test = series.iloc[-cfg.horizon :]

    results = []
    for name in models:
        model = svc._instantiate_model(name)
        model.fit(train)
        m = model.evaluate(test)
        results.append({"model": name, **m})

    st.subheader("Metrics (lower is better)")
    st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)

    # Simple comparison chart
    try:
        import plotly.express as px

        df_plot = pd.DataFrame(results)
        fig = px.bar(df_plot, x="model", y="mape", title="MAPE by Model")
        st.plotly_chart(fig, use_container_width=True)
    except Exception:
        pass

st.markdown("---")
st.caption("Models are trained on your database's historical prices for the selected symbol.")


