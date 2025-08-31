import os, schedule, time
from telegram import Bot
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from polygon_data import get_current_price
from trade_signals import generate_entry_signal, check_exit_signal
from news_scraper import fetch_google_news, fetch_analyst_news
from sentiment import analyze_sentiment
from oauth_helper import QuestTradeOAuth
from portfolio import QuestTradeAPI

bot = Bot(token=TELEGRAM_TOKEN)

WATCHLIST = ["AAPL", "TSLA", "NVDA", "BTC-USD"]

def send_alert(msg):
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode="Markdown")

def run_entry_signals():
    for sym in WATCHLIST:
        price = get_current_price(sym)
        if price:
            news = fetch_google_news(sym) + fetch_analyst_news()
            positive_sources = 0
            for n in news:
                sentiment, score = analyze_sentiment(n["title"])
                if sentiment=="Bullish": positive_sources+=1
            if positive_sources >= 3:  # 3+ reliable sources
                signal = generate_entry_signal(sym, price)
                msg = f"🚀 *Golden Entry Signal*\nSymbol: {sym}\nEntry: {signal['entry']}\nTP: {signal['take_profit']}\nSL: {signal['stop_loss']}\nSource confirmations: {positive_sources}"
                send_alert(msg)

def run_exit_signals():
    oauth = QuestTradeOAuth()
    token, api_server = oauth.refresh_access_token()
    qt = QuestTradeAPI(token, api_server)
    positions = qt.get_positions()
    for p in positions:
        symbol = p["symbol"]
        entry_price = p["averageEntryPrice"]
        should_exit, reason = check_exit_signal(symbol, entry_price)
        if should_exit:
            msg = f"🚨 *Exit Alert*\nSymbol: {symbol}\nReason: {reason}\nCurrent Price: {get_current_price(symbol)}\nEntry Price: {entry_price}"
            send_alert(msg)

# Schedule
schedule.every(5).minutes.do(run_exit_signals)
schedule.every(15).minutes.do(run_entry_signals)

if __name__ == "__main__":
    send_alert("💹 Jackpot Bot started. Monitoring entries and exits...")
    while True:
        schedule.run_pending()
        time.sleep(5)
