import os
import pandas as pd
import requests
from telegram import Bot
from datetime import datetime

# --- ENV VARIABLES ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")  # for ChatGPT sanity check

bot = Bot(token=TELEGRAM_TOKEN)

# --- CSV TICKERS ---
TICKER_CSV = "tickers.csv"  # Must exist in repo
try:
    df_tickers = pd.read_csv(TICKER_CSV)
    tickers = df_tickers['Ticker'].dropna().tolist()
except Exception as e:
    bot.send_message(chat_id=TELEGRAM_CHAT_ID,
                     text=f"❌ Error reading tickers.csv: {e}")
    tickers = []

# --- NEWS SOURCES ---
NEWS_SOURCES = {
    "MotleyFool": "https://api.mock-motleyfool.com/top-picks",
    "SeekingAlpha": "https://api.mock-seekingalpha.com/top-picks",
    "MarketWatch": "https://api.mock-marketwatch.com/top-stocks",
    "YahooFinance": "https://api.mock-yahoo.com/top-stocks",
    "TipRanks": "https://api.mock-tipranks.com/top-stocks",
}

# --- FUNCTION TO FETCH NEWS ---
def fetch_news(source_name, url):
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("top_stocks", [])
    except Exception as e:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID,
                         text=f"⚠️ Failed to fetch {source_name}: {e}")
        return []

# --- COLLECT SIGNALS ---
signals = []

for source, url in NEWS_SOURCES.items():
    top_stocks = fetch_news(source, url)
    for stock in top_stocks:
        if stock["ticker"] in tickers:
            # Example TP/SL calculation
            price = stock.get("price", 0.0)
            signals.append({
                "Ticker": stock["ticker"],
                "Source": source,
                "Price": price,
                "TP": price * 1.05 if price else 0.0,
                "SL": price * 0.95 if price else 0.0
            })

# --- CHATGPT SANITY CHECK ---
def chatgpt_sanity_check(signal):
    try:
        # Simple placeholder: replace with OpenAI API call if needed
        return f"✅ {signal['Ticker']} sanity check passed"
    except Exception as e:
        return f"⚠️ {signal['Ticker']} sanity check failed: {e}"

# --- BUILD MESSAGE ---
if signals:
    messages = []
    for sig in signals:
        sanity = chatgpt_sanity_check(sig)
        messages.append(f"💹 {sig['Ticker']} (BUY) from {sig['Source']}\n"
                        f"Price: {sig['Price']}, TP: {sig['TP']}, SL: {sig['SL']}\n"
                        f"{sanity}\n")
    final_message = f"🕒 Signals for {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}:\n\n"
    final_message += "\n".join(messages)
else:
    final_message = f"⚠️ No signals found for your tickers at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

# --- SEND TELEGRAM ---
try:
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=final_message)
except Exception as e:
    print(f"❌ Failed to send Telegram message: {e}")
