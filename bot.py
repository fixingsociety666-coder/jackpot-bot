import os
import requests
import pandas as pd
from bs4 import BeautifulSoup
import feedparser
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
NEWS_FEEDS = [
    "https://news.google.com/rss/search?q=stocks",
    "https://news.google.com/rss/search?q=cryptocurrency"
]

def get_latest_news():
    articles = []
    for feed in NEWS_FEEDS:
        d = feedparser.parse(feed)
        for entry in d.entries[:5]:
            articles.append({
                "title": entry.title,
                "link": entry.link,
                "published": entry.published
            })
    return articles

# ----------------------------
# Scrape top financial websites
# ----------------------------
FINANCIAL_SITES = [
    "https://www.fool.com/market-outlook/",
    "https://seekingalpha.com/market-news",
    "https://www.marketwatch.com/latest-news",
]

def scrape_stock_recommendations():
    signals = []
    for url in FINANCIAL_SITES:
        try:
            r = requests.get(url, timeout=10)
            soup = BeautifulSoup(r.text, "lxml")
            # This is simplified, you can enhance per site structure
            for link in soup.find_all("a", href=True):
                title = link.get_text().strip()
                href = link['href']
                if title and ("buy" in title.lower() or "strong buy" in title.lower()):
                    signals.append({"title": title, "link": href, "source": url})
        except Exception as e:
            print(f"Error scraping {url}: {e}")
    return signals

# ----------------------------
# Simple sentiment filter
# ----------------------------
def analyze_sentiment(text):
    text_lower = text.lower()
    if any(word in text_lower for word in ["breakthrough", "all-time high", "record", "strong buy"]):
        return "strong_buy"
    elif any(word in text_lower for word in ["gain", "uptrend", "buy"]):
        return "buy"
    elif any(word in text_lower for word in ["loss", "downtrend", "sell"]):
        return "sell"
    else:
        return "hold"

# ----------------------------
# Generate signals
# ----------------------------
def check_signals():
    token = get_questrade_access_token()
    positions = get_portfolio_positions(token) if token else []

    # Portfolio exit signals
    for pos in positions:
        ticker = pos["symbol"]
        price = get_stock_price(ticker)
        if not price:
            continue

        avg_price = pos.get("averageEntryPrice", 0)
        # Exit at 20% profit or 10% stop-loss
        if price >= avg_price * 1.2:
            send_telegram_message(f"📈 Exit Alert: {ticker} reached +20% (Price: {price}). Consider selling.")
        elif price <= avg_price * 0.9:
            send_telegram_message(f"⚠️ Stop Loss Alert: {ticker} dropped 10% (Price: {price}). Consider exiting.")

    # News signals
    news_items = get_latest_news()
    for article in news_items:
        sentiment = analyze_sentiment(article["title"])
        if sentiment in ["strong_buy", "buy"]:
            send_telegram_message(f"📰 News Signal ({sentiment.upper()}): {article['title']} \n{article['link']}")

    # Website scraping signals
    website_signals = scrape_stock_recommendations()
    for sig in website_signals:
        sentiment = analyze_sentiment(sig["title"])
        if sentiment in ["strong_buy", "buy"]:
            send_telegram_message(f"💹 Website Signal ({sentiment.upper()}) from {sig['source']}:\n{sig['title']}\n{sig['link']}")

# ----------------------------
# Main
# ----------------------------
if __name__ == "__main__":
    send_telegram_message("✅ Jackpot Bot started successfully!")
    check_signals()
