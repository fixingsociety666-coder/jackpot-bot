import os
import pandas as pd
import numpy as np
import requests
import json
from datetime import datetime

# =========================
# Load portfolio
# =========================
df = pd.read_csv("sample_portfolio.csv")

signals = []

# Simple scoring logic (placeholder for AI/momentum later)
for ticker in df["Ticker"]:
    score = round(np.random.rand(), 2)
    if score > 0.7:
        action = "BUY"
    elif score < 0.3:
        action = "SELL"
    else:
        action = "HOLD"
    signals.append({"Ticker": ticker, "Action": action, "Score": score})

signals_df = pd.DataFrame(signals)

# Save signals
os.makedirs("signals", exist_ok=True)
signals_file = f"signals/trading_signals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
signals_df.to_csv(signals_file, index=False)

# =========================
# NEWS SOURCES
# =========================
os.makedirs("news", exist_ok=True)
news_data = {}

# 1. Yahoo Finance (HTML scrape fallback)
for ticker in df["Ticker"]:
    try:
        url = f"https://finance.yahoo.com/quote/{ticker}"
        r = requests.get(url, timeout=5)
        news_data[f"Yahoo_{ticker}"] = r.text[:500] if r.status_code == 200 else "No news"
    except Exception as e:
        news_data[f"Yahoo_{ticker}"] = f"Error: {e}"

# 2. Barchart (requires free API key)
BARCHART_API_KEY = os.getenv("BARCHART_API_KEY")
if BARCHART_API_KEY:
    for ticker in df["Ticker"]:
        try:
            url = f"https://marketdata.websol.barchart.com/getNews.json?apikey={BARCHART_API_KEY}&symbols={ticker}"
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                news_data[f"Barchart_{ticker}"] = r.json()
            else:
                news_data[f"Barchart_{ticker}"] = "No news"
        except Exception as e:
            news_data[f"Barchart_{ticker}"] = f"Error: {e}"

# 3. Polygon.io
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")
if POLYGON_API_KEY:
    for ticker in df["Ticker"]:
        try:
            url = f"https://api.polygon.io/v2/reference/news?ticker={ticker}&limit=3&apiKey={POLYGON_API_KEY}"
            r = requests.get(url, timeout=5)
            news_data[f"Polygon_{ticker}"] = r.json() if r.status_code == 200 else "No news"
        except Exception as e:
            news_data[f"Polygon_{ticker}"] = f"Error: {e}"

# 4. Finnhub.io
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
if FINNHUB_API_KEY:
    for ticker in df["Ticker"]:
        try:
            url = f"https://finnhub.io/api/v1/company-news?symbol={ticker}&from=2024-01-01&to=2024-12-31&token={FINNHUB_API_KEY}"
            r = requests.get(url, timeout=5)
            news_data[f"Finnhub_{ticker}"] = r.json() if r.status_code == 200 else "No news"
        except Exception as e:
            news_data[f"Finnhub_{ticker}"] = f"Error: {e}"

# 5. Alpha Vantage (free but limited)
ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY")
if ALPHA_VANTAGE_KEY:
    for ticker in df["Ticker"]:
        try:
            url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={ticker}&apikey={ALPHA_VANTAGE_KEY}"
            r = requests.get(url, timeout=5)
            news_data[f"AlphaVantage_{ticker}"] = r.json() if r.status_code == 200 else "No news"
        except Exception as e:
            news_data[f"AlphaVantage_{ticker}"] = f"Error: {e}"

# Save news
news_file = f"news/latest_news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
with open(news_file, "w") as f:
    json.dump(news_data, f, indent=2)

# =========================
# OPTIONAL: ChatGPT sanity check
# =========================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

sanity_summary = None
if OPENAI_API_KEY:
    try:
        gpt_payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "You are a financial assistant. Summarize and sanity check stock signals."},
                {"role": "user", "content": f"Signals: {signals}\nNews: {list(news_data.keys())[:5]} ..."}
            ],
            "max_tokens": 150
        }
        gpt_headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        gpt_response = requests.post("https://api.openai.com/v1/chat/completions",
                                     headers=gpt_headers, json=gpt_payload, timeout=15)
        if gpt_response.status_code == 200:
            sanity_summary = gpt_response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        sanity_summary = f"Sanity check error: {e}"

# =========================
# Telegram Alerts
# =========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    messages = [f"{row['Ticker']} → {row['Action']} (Score {row['Score']})" for _, row in signals_df.iterrows()]
    text = "📈 Jackpot Bot Signals:\n" + "\n".join(messages)
    if sanity_summary:
        text += f"\n\n🤖 GPT Sanity Check:\n{sanity_summary}"

    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                      data={"chat_id": TELEGRAM_CHAT_ID, "text": text})
    except Exception as e:
        print(f"Telegram error: {e}")

print(f"✅ Signals saved: {signals_file}")
print(f"✅ News saved: {news_file}")
