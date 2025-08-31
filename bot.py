import os
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import pandas as pd
import feedparser
from sentiment import analyze_sentiment
from telegram import Bot

# Environment variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")

bot = Bot(token=TELEGRAM_TOKEN)

# Portfolio tickers and potential top-performing stocks
portfolio_tickers = ["AAPL", "TSLA", "AMZN"]
potential_stocks = ["NVDA", "MSFT", "GOOGL"]  # Example; extend later

# News sources
news_sources = {
    "Seeking Alpha": "https://seekingalpha.com/market-news",
    "Motley Fool": "https://www.fool.com/investing/",
    "MarketWatch": "https://www.marketwatch.com/latest-news",
    "Yahoo Finance": "https://finance.yahoo.com/topic/stock-market-news",
    "Barchart": "https://www.barchart.com/stocks/news",
    "TipsRank": "https://www.tipranks.com/news",
    "Barrons": "https://www.barrons.com/market-data",
}

def fetch_stock_data(ticker):
    data = yf.Ticker(ticker).info
    return data.get("regularMarketPrice", 0)

def calculate_tp_sl(price):
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
    message = f"💹 {source} Signal for {ticker}:\n"
    message += f"{headline}\nPrice: {price}, TP: {tp}, SL: {sl}"
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)

def process_stocks(tickers):
    for ticker in tickers:
        price = fetch_stock_data(ticker)
        if price == 0:
            continue
        tp, sl = calculate_tp_sl(price)
        for source, url in news_sources.items():
            headlines = scrape_news(url)
            for headline in headlines[:3]:  # Top 3 headlines
                sentiment = analyze_sentiment(headline)
                send_signal(ticker, source, price, tp, sl, headline)

# Run bot for portfolio + potential stocks
process_stocks(portfolio_tickers)
process_stocks(potential_stocks)
