import os
import requests
import yfinance as yf
from telegram import Bot
from datetime import datetime
from bs4 import BeautifulSoup
import feedparser
import pandas as pd

# --- ENV VARIABLES ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
POLYGON_KEY = os.environ.get("POLYGON_API_KEY")

bot = Bot(token=TELEGRAM_TOKEN)

# --- PORTFOLIO + WATCHLIST ---
# Portfolio tickers + penny stock + consistent gainers will be updated dynamically
portfolio_tickers = ["AAPL", "TSLA", "MSFT"]  # Replace with Quest Trade tickers

# --- FETCH TOP PERFORMING PENNY + CONSISTENT STOCKS FROM BARCHART ---
def fetch_barchart_top_stocks():
    try:
        url = "https://www.barchart.com/stocks/performers/top-performers"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table")
        tickers = []
        if table:
            df = pd.read_html(str(table))[0]
            tickers = df['Symbol'].tolist()[:100]  # Top 100 performers
        return tickers
    except Exception as e:
        print(f"Error fetching Barchart stocks: {e}")
        return []

# --- NEWS SOURCES ---
news_sources = {
    "Seeking Alpha": "https://seekingalpha.com/market-news",
    "Motley Fool": "https://www.fool.com/investing/stock-market/",
    "MarketWatch": "https://www.marketwatch.com/latest-news",
    "TipsRank": "https://www.tipranks.com/stocks",
    "Barrons": "https://www.barrons.com/topics/stocks"
}

# --- GOOGLE NEWS RSS ---
def fetch_google_news(ticker):
    rss_url = f"https://news.google.com/rss/search?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en"
    feed = feedparser.parse(rss_url)
    news_list = []
    for entry in feed.entries[:5]:
        news_list.append({
            "title": entry.title,
            "url": entry.link,
            "source": "Google News"
        })
    return news_list

# --- OTHER NEWS ---
def fetch_other_news():
    all_news = []
    headers = {"User-Agent": "Mozilla/5.0"}
    for source_name, url in news_sources.items():
        try:
            r = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            links = soup.find_all("a", href=True)
            for a in links[:5]:
                all_news.append({
                    "title": a.get_text(strip=True),
                    "url": a["href"],
                    "source": source_name
                })
        except Exception as e:
            print(f"Error fetching news from {source_name}: {e}")
    return all_news

# --- GET STOCK PRICE ---
def get_stock_price(ticker):
    try:
        stock = yf.Ticker(ticker)
        price = stock.history(period="1d")["Close"].iloc[-1]
        if price <= 0:
            url = f"https://api.polygon.io/v1/last/stocks/{ticker}?apiKey={POLYGON_KEY}"
            price_data = requests.get(url).json()
            price = price_data.get("last", 0)
        return round(price, 2)
    except Exception as e:
        print(f"Error getting price for {ticker}: {e}")
        return 0

# --- SENTIMENT ANALYSIS ---
def analyze_sentiment(title):
    positive_keywords = ["buy", "strong", "upgrade", "outperform", "bullish", "growth", "breakout"]
    negative_keywords = ["sell", "downgrade", "underperform", "bearish", "decline"]
    title_lower = title.lower()
    score = 0
    for word in positive_keywords:
        if word in title_lower:
            score += 1
    for word in negative_keywords:
        if word in title_lower:
            score -= 1
    if score > 1:
        return "Strong Positive"
    elif score == 1:
        return "Moderate Positive"
    elif score == 0:
        return "Neutral"
    else:
        return "Negative"

# --- TELEGRAM ALERT ---
def send_signal(ticker, price, tp, sl, news_source, sentiment, url=""):
    message = f"💹 Signal: {sentiment}\nTicker: {ticker}\nPrice: {price}\nTP: {tp}\nSL: {sl}\nSource: {news_source}"
    if url:
        message += f"\nLink: {url}"
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)

# --- MAIN BOT RUN ---
def run_bot():
    print(f"{datetime.now()}: Starting bot run...")

    # 1️⃣ Update tickers with Barchart top performers
    top_stocks = fetch_barchart_top_stocks()
    tickers = list(set(portfolio_tickers + top_stocks))

    # 2️⃣ Fetch news once
    all_news = fetch_other_news()

    for ticker in tickers:
        price = get_stock_price(ticker)
        if price <= 0:
            continue
        TP = round(price * 1.05, 2)  # Take profit
        SL = round(price * 0.97, 2)  # Stop loss

        google_news = fetch_google_news(ticker)
        combined_news = all_news + google_news

        alert_sent = False
        for news in combined_news:
            if ticker.lower() in news["title"].lower():
                sentiment = analyze_sentiment(news["title"])
                if sentiment == "Strong Positive":
                    send_signal(ticker, price, TP, SL, news["source"], sentiment, news["url"])
                    alert_sent = True

        # Fallback alert for Moderate Positive
        if not alert_sent:
            send_signal(ticker, price, TP, SL, "Yahoo Finance / Polygon", sentiment="Moderate Positive")

    print(f"{datetime.now()}: Bot run completed.")

if __name__ == "__main__":
    run_bot()
