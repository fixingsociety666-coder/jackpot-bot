import os
import requests
from telegram import Bot
from sentiment import analyze_sentiment
import feedparser
import yfinance as yf
from datetime import datetime

# Telegram
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
bot = Bot(token=TELEGRAM_TOKEN)

# News sources RSS feeds
NEWS_SOURCES = {
    "Motley Fool": "https://www.fool.com/rss/foolfeed.aspx",
    "Seeking Alpha": "https://seekingalpha.com/market-news.xml",
    "MarketWatch": "https://www.marketwatch.com/rss/topstories",
    "Barchart": "https://www.barchart.com/rss/top-stocks",
    "TipsRank": "https://www.tipranks.com/rss/stocks",
    "Barrons": "https://www.barrons.com/xml/rss/market-highlights.xml"
}

def get_news():
    signals = []
    for source, url in NEWS_SOURCES.items():
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:  # last 5 articles
            title = entry.title
            link = entry.link
            sentiment_score = analyze_sentiment(title)
            # Generate TP/SL (placeholder logic, can be enhanced)
            tp = round(sentiment_score * 1.1, 2)
            sl = round(sentiment_score * 0.9, 2)
            signals.append({
                "source": source,
                "title": title,
                "link": link,
                "tp": tp,
                "sl": sl,
                "score": sentiment_score
            })
    return signals

def send_telegram(signals):
    for s in signals:
        message = f"💹 {s['source']} Signal:\nTitle: {s['title']}\nLink: {s['link']}\nTP: {s['tp']}, SL: {s['sl']}, Score: {s['score']}"
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)

if __name__ == "__main__":
    signals = get_news()
    if signals:
        send_telegram(signals)
    else:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="No new signals found at this time.")
