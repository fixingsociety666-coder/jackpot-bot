import os
import pandas as pd
import yfinance as yf
import requests
from telegram import Bot
from datetime import datetime
import openai

# Environment variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")

openai.api_key = OPENAI_API_KEY
bot = Bot(token=TELEGRAM_TOKEN)

# CSV file
TICKER_FILE = "tickers.csv"

# News sources (dummy endpoints for demo, replace with actual API endpoints)
NEWS_SOURCES = {
    "MotleyFool": "https://api.mock-motleyfool.com/top-picks",
    "SeekingAlpha": "https://api.mock-seekingalpha.com/top-picks",
    "MarketWatch": "https://api.mock-marketwatch.com/top-stocks"
}

def fetch_news_top_picks():
    results = {}
    for name, url in NEWS_SOURCES.items():
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                results[name] = r.json()  # Expecting JSON with ticker symbols
            else:
                results[name] = []
        except Exception as e:
            results[name] = f"Error fetching {name}: {e}"
    return results

def fetch_stock_price(ticker):
    try:
        stock = yf.Ticker(ticker)
        price = stock.history(period="1d")["Close"].iloc[-1]
        return price
    except Exception as e:
        return f"Error fetching price: {e}"

def chatgpt_sanity_check(ticker, price, sources):
    prompt = f"Check the stock {ticker} at price {price}. Sources: {sources}. Suggest TP/SL."
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"ChatGPT error: {e}"

def send_telegram_message(message):
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as e:
        print(f"Telegram send error: {e}")

def main():
    df = pd.read_csv(TICKER_FILE)
    news_data = fetch_news_top_picks()

    for _, row in df.iterrows():
        ticker = row['Ticker']
        price = fetch_stock_price(ticker)
        sources_found = []

        # Check news sources
        for source, tickers in news_data.items():
            if isinstance(tickers, list) and ticker in tickers:
                sources_found.append(source)
            elif isinstance(tickers, str):
                # Error message
                send_telegram_message(tickers)

        # Build alert message
        msg = f"💹 Stock Alert: {ticker}\n"
        msg += f"Price: {price}\n"
        msg += f"Sources: {', '.join(sources_found) if sources_found else 'No source recommendation'}\n"

        # ChatGPT sanity check
        chatgpt_msg = chatgpt_sanity_check(ticker, price, sources_found)
        msg += f"ChatGPT Check: {chatgpt_msg}"

        send_telegram_message(msg)

if __name__ == "__main__":
    main()
