import logging
import feedparser
import requests
import yfinance as yf
from telegram import Bot
from sentiment import analyze_sentiment

# Telegram Bot Token & Chat ID
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

bot = Bot(token=TELEGRAM_TOKEN)

logging.basicConfig(level=logging.INFO)

NEWS_SOURCES = {
    "Yahoo Finance": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=AAPL,TSLA,MSFT&region=US&lang=en-US",
    "MarketWatch": "https://www.marketwatch.com/rss/topstories",
    "CNBC": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
}

def fetch_news():
    headlines = []
    for source, url in NEWS_SOURCES.items():
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            headlines.append((source, entry.title))
    return headlines

def fetch_stock_price(ticker):
    try:
        stock = yf.Ticker(ticker)
        price = stock.history(period="1d")["Close"].iloc[-1]
        return price
    except Exception as e:
        logging.error(f"Error fetching price for {ticker}: {e}")
        return None

def send_signal(message):
    try:
        bot.send_message(chat_id=CHAT_ID, text=message)
        logging.info(f"Sent signal: {message}")
    except Exception as e:
        logging.error(f"Error sending Telegram message: {e}")

def main():
    headlines = fetch_news()

    for source, headline in headlines:
        sentiment = analyze_sentiment(headline)

        if sentiment != "neutral":  # send everything, no threshold
            ticker = None
            if "Tesla" in headline or "TSLA" in headline:
                ticker = "TSLA"
            elif "Apple" in headline or "AAPL" in headline:
                ticker = "AAPL"
            elif "Microsoft" in headline or "MSFT" in headline:
                ticker = "MSFT"

            if ticker:
                price = fetch_stock_price(ticker)
                if price:
                    # Dummy TP/SL for demo
                    tp = round(price * 1.05, 2)
                    sl = round(price * 0.95, 2)

                    signal = (
                        f"📢 *Trading Signal* 📢\n\n"
                        f"📰 Source: {source}\n"
                        f"🧾 Headline: {headline}\n"
                        f"📈 Stock: {ticker}\n"
                        f"💵 Current Price: ${price:.2f}\n"
                        f"🎯 Take Profit: ${tp}\n"
                        f"🛑 Stop Loss: ${sl}\n"
                        f"📊 Sentiment: {sentiment.capitalize()}"
                    )
                    send_signal(signal)

if __name__ == "__main__":
    main()
