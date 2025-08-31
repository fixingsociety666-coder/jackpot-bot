import os
import requests
import yfinance as yf
import pandas as pd
from telegram import Bot
import feedparser
from datetime import datetime, timedelta

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
# QuestTrade OAuth helper
# -------------------------------
def get_questrade_access_token():
    """Fetch fresh access token from QuestTrade using refresh token"""
    try:
        url = f"https://login.questrade.com/oauth2/token?grant_type=refresh_token&refresh_token={QUESTRADE_REFRESH_TOKEN}&client_id={QUESTRADE_CLIENT_ID}"
        resp = requests.post(url).json()
        return resp.get("access_token")
    except:
        return None

def get_questrade_portfolio():
    """Fetch current holdings from QuestTrade account"""
    access_token = get_questrade_access_token()
    if not access_token:
        print("Could not get QuestTrade access token.")
        return []

    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        acct_resp = requests.get("https://api.questrade.com/v1/accounts", headers=headers).json()
        accounts = acct_resp.get("accounts", [])
        tickers = []

        for acct in accounts:
            acct_id = acct["number"]
            positions_resp = requests.get(f"https://api.questrade.com/v1/accounts/{acct_id}/positions", headers=headers).json()
            positions = positions_resp.get("positions", [])
            for pos in positions:
                if pos["openQuantity"] > 0:
                    tickers.append(pos["symbol"])
        return tickers
    except Exception as e:
        print(f"Error fetching portfolio: {e}")
        return []

# -------------------------------
# Helper functions
# -------------------------------
def get_stock_price(ticker):
    try:
        stock = yf.Ticker(ticker)
        price = stock.history(period="1d")['Close'][0]
        return price
    except:
        return None

def fetch_polygon_price(ticker):
    try:
        url = f"https://api.polygon.io/v1/last/stocks/{ticker}?apiKey={POLYGON_API_KEY}"
        resp = requests.get(url).json()
        return resp['last']['price']
    except:
        return None

def fetch_news_rss(url):
    try:
        feed = feedparser.parse(url)
        articles = []
        for entry in feed.entries[:5]:
            articles.append({'title': entry.title, 'link': entry.link})
        return articles
    except:
        return []

def sentiment_score(title):
    """Simple sentiment scoring"""
    title_lower = title.lower()
    score = 0
    buy_keywords = {"upgrade":0.3, "breakout":0.4, "rally":0.3, "strong buy":0.6, "surge":0.5}
    sell_keywords = {"downgrade":0.3, "sell":0.3, "drop":0.4, "decline":0.3}
    for word, val in buy_keywords.items():
        if word in title_lower:
            score += val
    for word, val in sell_keywords.items():
        if word in title_lower:
            score -= val
    return score

def calculate_tp_sl(price, score):
    if price == 0:
        return 0,0
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
        print(f"Telegram message sent: {message[:50]}...")
    except Exception as e:
        print(f"Telegram send error: {e}")

# -------------------------------
# News Sources
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
# Main Bot Logic
# -------------------------------
portfolio_tickers = get_questrade_portfolio()
if not portfolio_tickers:
    print("No tickers found in QuestTrade portfolio, defaulting to AAPL, TSLA, GOOG")
    portfolio_tickers = ["AAPL","TSLA","GOOG"]

send_telegram("✅ Jackpot Bot started successfully. Telegram alerts are live!")

for ticker in portfolio_tickers:
    # Get price
    price = get_stock_price(ticker)
    if not price:
        price = fetch_polygon_price(ticker)
    if not price:
        price = 0  # fallback

    # Analyze news from all sources
    for source_name, rss_url in rss_feeds.items():
        articles = fetch_news_rss(rss_url)
        for article in articles:
            score = sentiment_score(article['title'])
            tp, sl = calculate_tp_sl(price, score)
            signal_type = "BUY" if score>0 else "SELL" if score<0 else "NEUTRAL"

            message = (
                f"💹 {source_name} Signal ({signal_type}) for {ticker}:\n"
                f"Title: {article['title']}\n"
                f"Price: {price}\n"
                f"TP: {tp} | SL: {sl}\n"
                f"Link: {article['link']}"
            )
            send_telegram(message)

print(f"Bot run completed at {datetime.now()}")
