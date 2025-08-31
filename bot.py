import os
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import pandas as pd
import feedparser
from sentiment import analyze_sentiment
from telegram import Bot

# Load environment variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")

bot = Bot(token=TELEGRAM_TOKEN)

# Example portfolio tickers (replace with your CSV reading if needed)
portfolio_tickers = ["AAPL", "TSLA", "AMZN"]

# Example news sources (URLs)
news_sources = {
    "Seeking Alpha": "https://seekingalpha.com/market-news",
    "Motley Fool": "https://www.fool.com/investing/",
    "MarketWatch": "https://www.marketwatch.com/latest-news",
    "Yahoo Finance": "https://finance.yahoo.com/topic/stock-market-news",
    # Add more sources if needed
}

def fetch_stock_data(ticker):
    data = yf.Ticker(ticker).info
    current_price = data.get("regularMarketPrice", 0)
    return current_price

def calculate_tp_sl(price):
    # Example: TP 5% above, SL 3% below
    tp = round(price * 1.05, 2)
    sl = round(price * 0.97, 2)
    return tp, sl

def scrape_news(url):
    headlines = []
    try:
        r = requests.get(url, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        for item in soup.find_all(["a", "h3"]):
            text = item.get_text(strip=True)
            if text:
                headlines.append(text)
    except:
        pass
    return headlines

def send_signal(ticker, source, price, tp, sl, headline):
    message = f"💹 {source} Signal (BUY) for {ticker}:\n"
    message += f"{headline}\nPrice: {price}, TP: {tp}, SL: {sl}"
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)

# Process portfolio
for ticker in portfolio_tickers:
    price = fetch_stock_data(ticker)
    if price == 0:
        continue
    tp, sl = calculate_tp_sl(price)
    for source, url in news_sources.items():
        headlines = scrape_news(url)
        for headline in headlines[:3]:  # Top 3 headlines per source
            sentiment = analyze_sentiment(headline)
            # Send all signals regardless of threshold
            send_signal(ticker, source, price, tp, sl, headline)
