# bot.py
import os
import requests
from telegram import Bot

# Telegram setup
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
bot = Bot(token=TELEGRAM_TOKEN)

def send_telegram(message):
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

# Functions to fetch top stock picks from each source
def fetch_seeking_alpha():
    try:
        # Replace this with actual fetching logic
        # Example placeholder data
        return [{"symbol": "AAPL", "name": "Apple Inc.", "price": 180.5, "take_profit": 200, "stop_loss": 170, "source": "Seeking Alpha"}]
    except Exception as e:
        send_telegram(f"⚠️ Error fetching Seeking Alpha data: {e}")
        return []

def fetch_motley_fool():
    try:
        return [{"symbol": "MSFT", "name": "Microsoft Corp.", "price": 350, "take_profit": 380, "stop_loss": 330, "source": "Motley Fool"}]
    except Exception as e:
        send_telegram(f"⚠️ Error fetching Motley Fool data: {e}")
        return []

def fetch_tipsrank():
    try:
        return [{"symbol": "TSLA", "name": "Tesla Inc.", "price": 720, "take_profit": 780, "stop_loss": 680, "source": "TipsRank"}]
    except Exception as e:
        send_telegram(f"⚠️ Error fetching TipsRank data: {e}")
        return []

def fetch_marketwatch():
    try:
        return [{"symbol": "NVDA", "name": "NVIDIA Corp.", "price": 600, "take_profit": 650, "stop_loss": 570, "source": "MarketWatch"}]
    except Exception as e:
        send_telegram(f"⚠️ Error fetching MarketWatch data: {e}")
        return []

def fetch_yahoo():
    try:
        return [{"symbol": "AMZN", "name": "Amazon.com Inc.", "price": 145, "take_profit": 160, "stop_loss": 135, "source": "Yahoo Finance"}]
    except Exception as e:
        send_telegram(f"⚠️ Error fetching Yahoo Finance data: {e}")
        return []

def fetch_polygon():
    try:
        return [{"symbol": "GOOGL", "name": "Alphabet Inc.", "price": 2800, "take_profit": 3000, "stop_loss": 2700, "source": "Polygon.io"}]
    except Exception as e:
        send_telegram(f"⚠️ Error fetching Polygon.io data: {e}")
        return []

def fetch_finnhub():
    try:
        return [{"symbol": "NFLX", "name": "Netflix Inc.", "price": 500, "take_profit": 550, "stop_loss": 480, "source": "Finnhub"}]
    except Exception as e:
        send_telegram(f"⚠️ Error fetching Finnhub data: {e}")
        return []

# Main aggregation
all_signals = (
    fetch_seeking_alpha() +
    fetch_motley_fool() +
    fetch_tipsrank() +
    fetch_marketwatch() +
    fetch_yahoo() +
    fetch_polygon() +
    fetch_finnhub()
)

if not all_signals:
    send_telegram("⚠️ No stock signals retrieved from any source.")

# Send Telegram messages for each signal
for signal in all_signals:
    message = f"💹 {signal['name']} ({signal['symbol']})\n"
    message += f"Source: {signal['source']}\n"
    message += f"Price: {signal['price']}, TP: {signal['take_profit']}, SL: {signal['stop_loss']}"
    send_telegram(message)

print("All signals processed.")
