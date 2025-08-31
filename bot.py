import os
import pandas as pd
import numpy as np
import requests
from datetime import datetime

# Load portfolio (preloaded penny stocks + crypto)
df = pd.read_csv("sample_portfolio.csv")

# Prepare signals list
signals = []

# Simple scoring logic (placeholder, can integrate AI/momentum later)
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

# Ensure signals folder exists
os.makedirs("signals", exist_ok=True)
signals_file = f"signals/trading_signals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
signals_df.to_csv(signals_file, index=False)

# Fetch latest news for each ticker (free Yahoo Finance RSS)
os.makedirs("news", exist_ok=True)
news_data = {}
for ticker in df["Ticker"]:
    try:
        url = f"https://finance.yahoo.com/quote/{ticker}?p={ticker}"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            news_data[ticker] = r.text[:500]  # store snippet of page as placeholder
        else:
            news_data[ticker] = "No news found"
    except Exception as e:
        news_data[ticker] = f"Error: {e}"

news_file = f"news/latest_news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
import json
with open(news_file, "w") as f:
    json.dump(news_data, f, indent=2)

# Optional Telegram alerts
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    messages = [f"{row['Ticker']} → {row['Action']} (Score {row['Score']})" for _, row in signals_df.iterrows()]
    text = "📈 Jackpot Bot Signals:\n" + "\n".join(messages)
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                      data={"chat_id": TELEGRAM_CHAT_ID, "text": text})
    except Exception as e:
        print(f"Telegram error: {e}")

print(f"✅ Signals saved: {signals_file}")
print(f"✅ News saved: {news_file}")
