import pandas as pd
import requests
import yfinance as yf
from telegram import Bot
import openai
import os

# Environment variables from GitHub secrets
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize Telegram bot
bot = Bot(token=TELEGRAM_TOKEN)

# Initialize OpenAI client
openai.api_key = OPENAI_API_KEY

# CSV file with tickers
TICKER_CSV = "tickers.csv"

# News sources (replace with actual API endpoints or RSS feeds)
NEWS_SOURCES = {
    "MotleyFool": "https://api.mock-motleyfool.com/top-picks",
    "SeekingAlpha": "https://api.mock-seekingalpha.com/top-picks",
    "MarketWatch": "https://api.mock-marketwatch.com/top-stocks",
    "TipsRank": "https://api.mock-tipsrank.com/top-stocks",
    "Barrons": "https://api.mock-barrons.com/top-stocks",
    "Barchart": "https://api.mock-barchart.com/top-stocks"
}

# Function to fetch news source recommendations
def fetch_news_recommendations():
    recommendations = []
    for source, url in NEWS_SOURCES.items():
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            for stock in data.get("stocks", []):
                recommendations.append({
                    "ticker": stock["ticker"],
                    "source": source,
                    "price": stock.get("price", 0.0),
                    "take_profit": stock.get("take_profit", 0.0),
                    "stop_loss": stock.get("stop_loss", 0.0)
                })
        except Exception as e:
            # Send Telegram alert if source fails
            bot.send_message(chat_id=TELEGRAM_CHAT_ID,
                             text=f"⚠️ Failed to fetch data from {source}: {e}")
    return recommendations

# ChatGPT sanity check
def chatgpt_sanity_check(ticker, reason):
    prompt = f"Analyze this stock pick: {ticker}. Reason: {reason}. Is this a strong buy? Provide suggested take profit and stop loss."
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        content = response.choices[0].message.content
        return content
    except Exception as e:
        return f"ChatGPT sanity check failed: {e}"

# Read tickers
df_tickers = pd.read_csv(TICKER_CSV)
tickers = df_tickers['Ticker'].tolist()

# Fetch recommendations
recommendations = fetch_news_recommendations()

# Filter only tickers in our CSV
final_recommendations = [r for r in recommendations if r["ticker"] in tickers]

# Prepare Telegram message
for rec in final_recommendations:
    sanity_result = chatgpt_sanity_check(rec["ticker"], f"Recommendation from {rec['source']}")
    message = f"💹 Signal from {rec['source']}:\nTicker: {rec['ticker']}\nPrice: {rec['price']}\nTP: {rec['take_profit']}\nSL: {rec['stop_loss']}\nChatGPT Feedback:\n{sanity_result}"
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
