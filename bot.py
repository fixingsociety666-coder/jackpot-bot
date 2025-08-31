import os
import pandas as pd
import numpy as np
from datetime import datetime

# Load portfolio (example CSV with tickers)
portfolio_file = "sample_portfolio.csv"
if os.path.exists(portfolio_file):
    df = pd.read_csv(portfolio_file)
else:
    df = pd.DataFrame({"Ticker": ["AAPL", "MSFT", "TSLA"]})

signals = []

for ticker in df["Ticker"]:
    # Generate random score for demo (replace later with real API logic)
    score = round(np.random.rand(), 2)   # ✅ FIXED: use numpy directly
    action = "BUY" if score > 0.7 else "SELL" if score < 0.3 else "HOLD"
    signals.append({"Ticker": ticker, "Score": score, "Action": action})

signals_df = pd.DataFrame(signals)
print("Generated Signals:")
print(signals_df)

# Save signals to file
os.makedirs("signals", exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
signals_file = f"signals/signals_{timestamp}.csv"
signals_df.to_csv(signals_file, index=False)

print(f"Signals saved to {signals_file}")

# Telegram alert (optional, only if secrets are set)
import requests
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    message = "📈 Jackpot Bot Signals:\n\n" + signals_df.to_string(index=False)
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})
