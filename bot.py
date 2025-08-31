import os
import time
import pandas as pd
import yfinance as yf
import feedparser
import requests
from telegram import Bot, constants

# -----------------------------
# CONFIG
# -----------------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")

bot = Bot(token=TELEGRAM_TOKEN)

# Portfolio tickers
portfolio_stocks = ["AAPL", "TSLA", "GOOG"]  # Replace with your Quest Trade portfolio
# Potential breakout stocks
potential_stocks = ["NVDA", "AMD", "MSFT"]

# All tickers to monitor
all_stocks = portfolio_stocks + potential_stocks

# News RSS URLs
rss_feeds = {
    "SeekingAlpha": "https://seekingalpha.com/market-news.rss",
    "MotleyFool": "https://www.fool.com/feeds/rss.aspx",
    "MarketWatch": "https://www.marketwatch.com/rss/topstories",
    "TipsRank": "https://www.tipranks.com/rss/stocks",
    "Barrons": "https://www.barrons.com/xml/rss/market-brief",
}

# -----------------------------
# FUNCTIONS
# -----------------------------

def get_price(symbol):
    """Get last close price using Yahoo Finance"""
    data = yf.Ticker(symbol)
    hist = data.history(period="1d")
    if hist.empty:
        return 0
    return round(hist["Close"][-1], 2)

def calculate_tp_sl(price):
    """Calculate take profit / stop loss"""
    tp = round(price * 1.05, 2)  # +5%
    sl = round(price * 0.97, 2)  # -3%
    return tp, sl

def fetch_news():
    """Fetch latest news from all sources"""
    news_items = []
    for source, url in rss_feeds.items():
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:  # Latest 5 items per source
            news_items.append({
                "source": source,
                "title": entry.title,
                "link": entry.link
            })
    return news_items

def fetch_polygon_news(symbol):
    """Fetch Polygon news for a stock"""
    if not POLYGON_API_KEY:
        return []
    url = f"https://api.polygon.io/v2/reference/news?ticker={symbol}&limit=3&apiKey={POLYGON_API_KEY}"
    resp = requests.get(url).json()
    news_items = []
    if "results" in resp:
        for n in resp["results"]:
            news_items.append({
                "source": "Polygon",
                "title": n["title"],
                "link": n["article_url"]
            })
    return news_items

def send_signal(stock, price, tp, sl, news):
    """Send Telegram alert"""
    message = f"💹 Signal for {stock} (BUY)\n"
    message += f"Price: {price}, TP: {tp}, SL: {sl}\n"
    message += f"News source: {news['source']}\n"
    message += f"Headline: {news['title']}\n"
    message += f"Link: {news['link']}"
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode=constants.ParseMode.HTML)

# -----------------------------
# MAIN LOOP
# -----------------------------
def main():
    while True:
        print("Fetching prices and news...")
        news_items = fetch_news()

        for stock in all_stocks:
            price = get_price(stock)
            if price == 0:
                continue
            tp, sl = calculate_tp_sl(price)

            # Include Polygon news
            polygon_news = fetch_polygon_news(stock)
            combined_news = news_items + polygon_news

            # Filter news containing stock symbol
            relevant_news = [n for n in combined_news if stock.upper() in n["title"].upper()]
            if not relevant_news:
                relevant_news = [{"source": "No recent news", "title": "-", "link": "-"}]

            # Send signals
            for news in relevant_news:
                send_signal(stock, price, tp, sl, news)

        print("Waiting 1 hour before next scan...")
        time.sleep(3600)

if __name__ == "__main__":
    main()
