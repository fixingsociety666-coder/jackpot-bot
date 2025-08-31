import streamlit as st
import pandas as pd
import json, os
from datetime import date

st.set_page_config(page_title="Jackpot Signals", layout="wide")
st.title("📈 Jackpot Signals — Stocks + Crypto + News")

BASE = os.path.dirname(__file__)
signals_folder = os.path.join(BASE, "signals")
news_file = os.path.join(BASE, "news", "latest_news.json")

files = sorted([f for f in os.listdir(signals_folder) if f.endswith(".json")])
latest = files[-1] if files else None

if latest:
    with open(os.path.join(signals_folder, latest), "r") as f:
        data = json.load(f)
    df = pd.DataFrame(data).T

    st.subheader("🔥 Top GREEN Stock Picks")
    greens = df[df["color"]=="GREEN"]
    if not greens.empty:
        st.dataframe(greens[["ticker","close","score","confidence","rationale"]].fillna(""))
    else:
        st.write("No GREEN stocks today.")

    st.subheader("🪙 Crypto Signals")
    cryptos = df[df["market"]=="crypto"]
    if not cryptos.empty:
        st.dataframe(cryptos[["ticker","close","score","confidence","rationale"]].fillna(""))
    else:
        st.write("No crypto signals today.")

    st.subheader("📰 Latest Market News")
    if os.path.exists(news_file):
        with open(news_file,"r") as f:
            news = json.load(f)
        for n in news[:10]:
            st.markdown(f"**{n['source']}** — {n['title']}\n\n{n['summary']}\n---")
    else:
        st.write("No news available.")
else:
    st.warning("No signals found. Run the backend bot to produce signals.")
