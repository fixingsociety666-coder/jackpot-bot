import os
import feedparser
import yfinance as yf
from telegram import Bot

# Environment variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = Bot(token=TELEGRAM_TOKEN)

# List of news RSS feeds / sources
NEWS_SOURCES = {
    "Seeking Alpha": "https://seekingalpha.com/market-news.rss",
    "Motley Fool": "https://www.fool.com/feeds/all.xml",
    "MarketWatch": "https://www.marketwatch.com/rss/topstories",
    "Barchart": "https://www.barchart.com/rss/top-stocks.xml",
    "TipsRank": "https://www.tipsranks.com/rss",
    "Barron's": "https://www.barrons.com/xml/rss/1_2.xml",
    "Yahoo Finance": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=yhoo&region=US&lang=en-US"
}

# Function to fetch latest news and extract stock symbols
def fetch_stock_signals():
    signals = []
    for source_name, rss_url in NEWS_SOURCES.items():
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:5]:  # Get top 5 articles per source
            title = entry.get("title", "")
            link = entry.get("link", "")
            # Extract ticker from title using yfinance (very basic)
            words = title.split()
            for word in words:
                if word.isupper() and len(word) <= 5:
                    try:
                        stock = yf.Ticker(word)
                        price = stock.info.get("regularMarketPrice", 0)
                        signals.append({
                            "source": source_name,
                            "ticker": word,
                            "title": title,
                            "link": link,
                            "price": price,
                            "tp": round(price * 1.05, 2) if price else 0.0,  # Take Profit 5% above
                            "sl": round(price * 0.97, 2) if price else 0.0   # Stop Loss 3% below
                        })
                    except:
                        continue
    return signals

# Send signals to Telegram
def send_telegram_signals(signals):
    for s in signals:
        message = (
            f"💹 {s['source']} Signal (BUY)\n"
            f"{s['ticker']} - {s['title']}\n"
            f"Link: {s['link']}\n"
            f"Price: {s['price']}, TP: {s['tp']}, SL: {s['sl']}"
        )
        try:
            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        except Exception as e:
            print(f"Error sending Telegram message: {e}")

if __name__ == "__main__":
    stock_signals = fetch_stock_signals()
    if stock_signals:
        send_telegram_signals(stock_signals)
    else:
        print("No signals found.")
