import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime

from utils.curator import create_curator_dataset


st.set_page_config(page_title="Dataset Builder", page_icon="🗃️", layout="wide")

st.title("🗃️ Dataset Builder")
symbol = st.session_state.get("selected_symbol")
days = st.session_state.get("selected_days", 30)

colA, colB = st.columns(2)
with colA:
    st.write("Selected symbol:", symbol or "—")
with colB:
    days = st.number_input("Days of history", min_value=5, max_value=3650, value=int(days), step=5)

if not symbol:
    st.warning("Go back to Home and select a ticker first.")
    st.stop()

exchange = "CRYPTO" if symbol.endswith("-USD") else "NASDAQ"

if st.button("Generate Dataset", type="primary"):
    with st.spinner("Collecting market data and news, please wait..."):
        dataset = create_curator_dataset(exchange=exchange, symbol=symbol, days=int(days))
    st.success("Dataset created!")

    df = pd.DataFrame(dataset.get("data", []))
    st.subheader("Preview")
    st.dataframe(df.tail(30), use_container_width=True)

    # Save files
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("datasets")
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"fintech_dataset_{symbol}_{timestamp}.csv"
    json_path = out_dir / f"fintech_dataset_{symbol}_{timestamp}.json"
    df.to_csv(csv_path, index=False)
    (out_dir / f"meta_{symbol}_{timestamp}.json").write_text(
        __import__("json").dumps(dataset, indent=2, default=str), encoding="utf-8"
    )

    st.success(f"Saved CSV: {csv_path}")
    st.success(f"Saved JSON: {json_path}")

    st.download_button("Download CSV", data=csv_path.read_bytes(), file_name=csv_path.name, mime="text/csv")
    st.download_button("Download JSON", data=json_path.read_bytes(), file_name=json_path.name, mime="application/json")

st.markdown("---")
st.caption("Data is automatically passed through the feature pipeline for basic cleaning and indicators.")


