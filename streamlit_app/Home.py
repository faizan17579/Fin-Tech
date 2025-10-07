import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime


st.set_page_config(page_title="FinTech Dashboard", page_icon="📈", layout="wide")

if "selected_symbol" not in st.session_state:
    st.session_state.selected_symbol = None

st.title("📈 Live Markets")
st.caption("Select an instrument to generate a dataset and train models")

col1, col2 = st.columns([2, 1])

with col1:
    search = st.text_input("Search ticker (e.g., AAPL, TSLA, MSFT, BTC-USD)")
    default_list = [
        ("NASDAQ", "AAPL"),
        ("NASDAQ", "TSLA"),
        ("NASDAQ", "MSFT"),
        ("NASDAQ", "GOOGL"),
        ("CRYPTO", "BTC-USD"),
        ("CRYPTO", "ETH-USD"),
    ]

    tickers = [t for _, t in default_list]
    live = {}
    if search.strip():
        tickers = list({search.strip().upper(), *tickers})

    # Fetch live prices
    try:
        df = yf.download(tickers=tickers, period="1d", interval="1m", progress=False, group_by="ticker")
        now_prices = []
        for t in tickers:
            try:
                data = df[t] if isinstance(df.columns, pd.MultiIndex) else df
                price = float(data["Close"].dropna().iloc[-1])
                now_prices.append({"Symbol": t, "Price": price})
            except Exception:
                now_prices.append({"Symbol": t, "Price": float("nan")})
        price_df = pd.DataFrame(now_prices)
    except Exception:
        price_df = pd.DataFrame({"Symbol": tickers, "Price": [float("nan")] * len(tickers)})

    st.subheader("Watchlist")
    st.dataframe(price_df, use_container_width=True, hide_index=True)

with col2:
    st.subheader("Select Instrument")
    symbol = st.selectbox("Choose from list", options=[t for t in tickers])
    st.markdown("Or type a custom ticker below")
    custom = st.text_input("Custom ticker", value="")
    days = st.number_input("Days of history", min_value=5, max_value=3650, value=30, step=5)

    if st.button("Proceed to Dataset Builder", type="primary"):
        chosen = custom.strip().upper() if custom.strip() else symbol
        st.session_state.selected_symbol = chosen
        st.session_state.selected_days = int(days)
        st.switch_page("pages/2_Dataset_Builder.py")

st.markdown("---")
st.info("Tip: Use standard Yahoo tickers (e.g., 'RELIANCE.NS' for NSE India, 'BTC-USD' for Bitcoin)")


