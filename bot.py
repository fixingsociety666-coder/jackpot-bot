import os
import requests
import pandas as pd
from telegram import Bot
from datetime import datetime
from polygon import RESTClient

# ----------------------------
# Environment variables
# ----------------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")
QUESTRADE_CLIENT_ID = os.environ.get("QUESTRADE_CLIENT_ID")
QUESTRADE_REFRESH_TOKEN = os.environ.get("QUESTRADE_REFRESH_TOKEN")

# ----------------------------
# Validate environment variables
# ----------------------------
if not all([TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, POLYGON_API_KEY, QUESTRADE_CLIENT_ID, QUESTRADE_REFRESH_TOKEN]):
    raise ValueError("One or more required environment variables are missing!")

# ----------------------------
# Initialize Telegram bot
# ----------------------------
bot = Bot(token=TELEGRAM_TOKEN)

def send_telegram_message(message: str):
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        print(f"[{datetime.now()}] Sent: {message}")
    except Exception as e:
        print(f"[{datetime.now()}] Telegram error: {e}")

# ----------------------------
# Polygon.io client
# ----------------------------
polygon_client = RESTClient(POLYGON_API_KEY)

def get_stock_price(ticker):
    try:
        resp = polygon_client.stocks_equities_last_quote(ticker)
        return resp.last.price
    except Exception as e:
        print(f"Error fetching {ticker} price: {e}")
        return None

# ----------------------------
# QuestTrade API (OAuth)
# ----------------------------
def get_questrade_access_token():
    url = "https://login.questrade.com/oauth2/token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": QUESTRADE_REFRESH_TOKEN,
        "client_id": QUESTRADE_CLIENT_ID
    }
    try:
        r = requests.post(url, data=data)
        r.raise_for_status()
        return r.json()["access_token"]
    except Exception as e:
        print(f"Error getting QuestTrade token: {e}")
        return None

def get_portfolio_positions(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        url = "https://api.questrade.com/v1/accounts"
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        accounts = r.json()["accounts"]
        # Take first account as example
        account_id = accounts[0]["accountId"]
        positions_url = f"https://api.questrade.com/v1/accounts/{account_id}/positions"
        r2 = requests.get(positions_url, headers=headers)
        r2.raise_for_status()
        return r2.json()["positions"]
    except Exception as e:
        print(f"Error fetching QuestTrade portfolio: {e}")
        return []

# ----------------------------
# Google News RSS
# ----------------------------
import feedparser

NEWS_FEEDS = [
    "https://news.google.com/rss/search?q=stocks",
    "https://news.google.com/rss/search?q=cryptocurrency"
]

def get_latest_news():
    articles = []
    for feed in NEWS_FEEDS:
        d = feedparser.parse(feed)
        for entry in d.entries[:5]:  # Only latest 5 per feed
            articles.append({
                "title": entry.title,
                "link": entry.link,
                "published": entry.published
            })
    return articles

# ----------------------------
# Placeholder: Social Sentiment Analysis
# ----------------------------
def analyze_sentiment(text):
    # Placeholder: Replace with real sentiment analysis
    # Return "strong_buy", "buy", "hold", "sell", "strong_sell"
    text_lower = text.lower()
    if any(word in text_lower for word in ["breakthrough", "all-time high", "record"]):
        return "strong_buy"
    elif any(word in text_lower for word in ["gain", "uptrend"]):
        return "buy"
    elif any(word in text_lower for word in ["loss", "downtrend"]):
        return "sell"
    else:
        return "hold"

# ----------------------------
# Bot Logic: Generate Signals
# ----------------------------
def check_signals():
    # 1. Portfolio positions
    token = get_questrade_access_token()
    positions = get_portfolio_positions(token) if token else []

    for pos in positions:
        ticker = pos["symbol"]
        price = get_stock_price(ticker)
        if not price:
            continue

        # Example: simple placeholder for exit signal
        if price >= pos["averageEntryPrice"] * 1.2:  # 20% gain
            send_telegram_message(f"📈 Exit Alert: {ticker} has reached +20%. Consider selling.")
        elif price <= pos["averageEntryPrice"] * 0.9:  # 10% loss
            send_telegram_message(f"⚠️ Stop Loss Alert: {ticker} has dropped 10%. Consider exiting.")

    # 2. News signals
    news_items = get_latest_news()
    for article in news_items:
        sentiment = analyze_sentiment(article["title"])
        if sentiment in ["strong_buy", "buy"]:
            send_telegram_message(f"📰 News Signal ({sentiment.upper()}): {article['title']} \n{article['link']}")

# ----------------------------
# Main
# ----------------------------
if __name__ == "__main__":
    send_telegram_message("✅ Jackpot Bot started successfully!")
    check_signals()

