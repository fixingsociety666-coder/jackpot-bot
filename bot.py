import os
import requests
from bs4 import BeautifulSoup
import feedparser
import pandas as pd
import yfinance as yf
from telegram import Bot
from sentiment import analyze_sentiment

# --- Telegram Setup ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
bot = Bot(token=TELEGRAM_TOKEN)

# --- News Sources ---
sources = {
    "SeekingAlpha": "https://seekingalpha.com/market-news",
    "MarketWatch": "https://www.marketwatch.com/latest-news",
    "MotleyFool": "https://www.fool.com/market-news/",
    "Barchart": "https://www.barchart.com/stocks/market-performance",
    "YahooFinance": "https://finance.yahoo.com/most-active",
    "TipRanks": "https://www.tipranks.com/stocks",
    "Barrons": "https://www.barrons.com/market-data/stocks"
}

# --- Fetch Functions for Each Source ---
def fetch_yahoo():
    stocks = []
    try:
        tables = pd.read_html(sources["YahooFinance"])
        if tables:
            df = tables[0].head(5)
            for idx, row in df.iterrows():
                symbol = row['Symbol']
                price = float(str(row['Price (Intraday)']).replace(',',''))
                sentiment_score = analyze_sentiment(f"{symbol} news")
                stocks.append({
                    "source": "YahooFinance",
                    "symbol": symbol,
                    "price": price,
                    "tp": round(price * 1.04, 2),
                    "sl": round(price * 0.98, 2),
                    "sentiment": sentiment_score
                })
    except Exception as e:
        print(f"YahooFinance error: {e}")
    return stocks

def fetch_seekingalpha():
    stocks = []
    try:
        r = requests.get(sources["SeekingAlpha"])
        soup = BeautifulSoup(r.text, "html.parser")
        articles = soup.find_all("a", href=True)[:5]
        for art in articles:
            text = art.text.strip()
            if text:
                symbol = text.split()[0]
                sentiment_score = analyze_sentiment(text)
                stocks.append({"source":"SeekingAlpha","symbol":symbol,"price":0,"tp":0.0,"sl":0.0,"sentiment":sentiment_score})
    except Exception as e:
        print(f"SeekingAlpha error: {e}")
    return stocks

def fetch_marketwatch():
    stocks = []
    try:
        r = requests.get(sources["MarketWatch"])
        soup = BeautifulSoup(r.text, "html.parser")
        articles = soup.select("a")[:5]
        for art in articles:
            text = art.text.strip()
            if text:
                symbol = text.split()[0]
                sentiment_score = analyze_sentiment(text)
                stocks.append({"source":"MarketWatch","symbol":symbol,"price":0,"tp":0.0,"sl":0.0,"sentiment":sentiment_score})
    except Exception as e:
        print(f"MarketWatch error: {e}")
    return stocks

def fetch_motleyfool():
    stocks = []
    try:
        r = requests.get(sources["MotleyFool"])
        soup = BeautifulSoup(r.text, "html.parser")
        articles = soup.find_all("a")[:5]
        for art in articles:
            text = art.text.strip()
            if text:
                symbol = text.split()[0]
                sentiment_score = analyze_sentiment(text)
                stocks.append({"source":"MotleyFool","symbol":symbol,"price":0,"tp":0.0,"sl":0.0,"sentiment":sentiment_score})
    except Exception as e:
        print(f"MotleyFool error: {e}")
    return stocks

def fetch_barchart():
    stocks = []
    try:
        r = requests.get(sources["Barchart"])
        soup = BeautifulSoup(r.text, "html.parser")
        articles = soup.find_all("a")[:5]
        for art in articles:
            text = art.text.strip()
            if text:
                symbol = text.split()[0]
                sentiment_score = analyze_sentiment(text)
                stocks.append({"source":"Barchart","symbol":symbol,"price":0,"tp":0.0,"sl":0.0,"sentiment":sentiment_score})
    except Exception as e:
        print(f"Barchart error: {e}")
    return stocks

def fetch_tipranks():
    stocks = []
    try:
        r = requests.get(sources["TipRanks"])
        soup = BeautifulSoup(r.text, "html.parser")
        articles = soup.find_all("a")[:5]
        for art in articles:
            text = art.text.strip()
            if text:
                symbol = text.split()[0]
                sentiment_score = analyze_sentiment(text)
                stocks.append({"source":"TipRanks","symbol":symbol,"price":0,"tp":0.0,"sl":0.0,"sentiment":sentiment_score})
    except Exception as e:
        print(f"TipRanks error: {e}")
    return stocks

def fetch_barrons():
    stocks = []
    try:
        r = requests.get(sources["Barrons"])
        soup = BeautifulSoup(r.text, "html.parser")
        articles = soup.find_all("a")[:5]
        for art in articles:
            text = art.text.strip()
            if text:
                symbol = text.split()[0]
                sentiment_score = analyze_sentiment(text)
                stocks.append({"source":"Barrons","symbol":symbol,"price":0,"tp":0.0,"sl":0.0,"sentiment":sentiment_score})
    except Exception as e:
        print(f"Barrons error: {e}")
    return stocks

# --- Aggregate all top stocks ---
def fetch_top_stocks():
    stocks = []
    stocks.extend(fetch_yahoo())
    stocks.extend(fetch_seekingalpha())
    stocks.extend(fetch_marketwatch())
    stocks.extend(fetch_motleyfool())
    stocks.extend(fetch_barchart())
    stocks.extend(fetch_tipranks())
    stocks.extend(fetch_barrons())
    return stocks

# --- Telegram Notification ---
def send_telegram_signal(stock):
    message = f"💹 {stock['source']} Signal (BUY):\n"
    message += f"Symbol: {stock['symbol']}\n"
    message += f"Price: {stock['price']}\n"
    message += f"TP: {stock['tp']}, SL: {stock['sl']}\n"
    message += f"Sentiment Score: {stock['sentiment']}\n"
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)

# --- Main ---
def main():
    top_stocks = fetch_top_stocks()
    for stock in top_stocks:
        send_telegram_signal(stock)

if __name__ == "__main__":
    main()
