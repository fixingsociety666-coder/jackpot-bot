import os
import requests
import yfinance as yf
import pandas as pd
from telegram import Bot
from bs4 import BeautifulSoup
import feedparser
from datetime import datetime

# -------------------------------
# Environment / Secrets
# -------------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")
QUESTRADE_CLIENT_ID = os.getenv("QUESTRADE_CLIENT_ID")
QUESTRADE_REFRESH_TOKEN = os.getenv("QUESTRADE_REFRESH_TOKEN")

bot = Bot(token=TELEGRAM_TOKEN)

# -------------------------------
# Helper functions
# -------------------------------
def get_stock_price(ticker):
    """Get stock price from yfinance"""
    try:
        stock = yf.Ticker(ticker)
        price = stock.history(period="1d")['Close'][0]
        return price
    except Exception as e:
        print(f"Error fetching {ticker} price: {e}")
        return None

def fetch_polygon_price(ticker):
    """Get stock price from Polygon.io"""
    try:
        url = f"https://api.polygon.io/v1/last/stocks/{ticker}?apiKey={POLYGON_API_KEY}"
        resp = requests.get(url).json()
        return resp['last']['price']
    except Exception as e:
        print(f"Polygon error for {ticker}: {e}")
        return None

def fetch_news_rss(url):
    try:
        feed = feedparser.parse(url)
        articles = []
        for entry in feed.entries[:5]:
            title = entry.title
            link = entry.link
            articles.append({'title': title, 'link': link})
        return articles
    except Exception as e:
        print(f"RSS fetch error {url}: {e}")
        return []

def sentiment_score(title):
    buy_keywords = ["upgrade", "breakout", "rally", "strong buy", "surge"]
    sell_keywords = ["downgrade", "sell", "drop", "decline"]
    score = 0
    title_lower = title.lower()
    if any(word in title_lower for word in buy_keywords):
        score = 1
    elif any(word in title_lower for word in sell_keywords):
        score = -1
    return score

def calculate_tp_sl(price, score):
    if score > 0:
        tp = price * 1.05
        sl = price * 0.98
    elif score < 0:
        tp = price * 0.98
        sl = price * 1.05
    else:
        tp = sl = price
    return round(tp,2), round(sl,2)

def send_telegram(message):
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as e:
        print(f"Telegram send error: {e}")

# -------------------------------
# Sources
# -------------------------------
rss_feeds = {
    "Yahoo Finance": "https://finance.yahoo.com/news/rssindex",
    "Seeking Alpha": "https://seekingalpha.com/market-news.xml",
    "Motley Fool": "https://www.fool.com/feeds/",
    "MarketWatch": "https://www.marketwatch.com/rss/topstories",
    "Barchart": "https://www.barchart.com/rss/news",
    "TipsRank": "https://www.tipsranks.com/rss/news",
    "Barrons": "https://www.barrons.com/xml/rss/2_7761.xml"
}

# -------------------------------
# Portfolio (placeholder for QuestTrade API fetch)
# -------------------------------
# You can extend this to pull real portfolio tickers via QuestTrade OAuth
portfolio_tickers = ["AAPL","TSLA","GOOG","AMZN"]  # Your portfolio + top potential stocks

# -------------------------------
# Main Bot Logic
# -------------------------------
for ticker in portfolio_tickers:
    # Get price from yfinance
    price = get_stock_price(ticker)
    # Fall back to Polygon if yfinance fails
    if not price:
        price = fetch_polygon_price(ticker)
    if not price:
        print(f"No price data for {ticker}, skipping.")
        continue

    signals = []

    # Loop through all news sources
    for source_name, rss_url in rss_feeds.items():
        articles = fetch_news_rss(rss_url)
        for article in articles:
            score = sentiment_score(article['title'])
            if score == 0:
                continue  # skip neutral
            tp, sl = calculate_tp_sl(price, score)
            signals.append({
                'ticker': ticker,
                'source': source_name,
                'title': article['title'],
                'link': article['link'],
                'price': price,
                'TP': tp,
                'SL': sl,
                'signal': "BUY" if score>0 else "SELL"
            })

    # Send Telegram messages
    for sig in signals:
        message = (
            f"💹 {sig['source']} Signal ({sig['signal']}) for {sig['ticker']}:\n"
            f"Title: {sig['title']}\n"
            f"Price: {sig['price']}\n"
            f"TP: {sig['TP']} | SL: {sig['SL']}\n"
            f"Link: {sig['link']}"
        )
        send_telegram(message)

print(f"Bot run completed at {datetime.now()}")
