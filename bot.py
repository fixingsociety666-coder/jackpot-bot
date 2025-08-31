# bot.py
import os
import yfinance as yf
from datetime import datetime
from sentiment import sentiment_score, calculate_tp_sl
from portfolio import get_questrade_portfolio
from news import rss_feeds, fetch_news_rss
from telegram_bot import send_telegram

# -------------------------------
send_telegram("✅ Jackpot Bot started. Telegram alerts live!")

portfolio_tickers = get_questrade_portfolio() or ["AAPL","TSLA","GOOG"]

for ticker in portfolio_tickers:
    try:
        price = yf.Ticker(ticker).history(period="1d")['Close'][0]
    except:
        price = 0

    for source_name, rss_url in rss_feeds.items():
        articles = fetch_news_rss(rss_url)
        for article in articles:
            score = sentiment_score(article['title'])
            tp, sl = calculate_tp_sl(price, score)
            signal_type = "BUY" if score>0 else "SELL" if score<0 else "NEUTRAL"
            message = f"💹 {source_name} Signal ({signal_type}) for {ticker}:\nTitle: {article['title']}\nPrice: {price}\nTP: {tp} | SL: {sl}\nLink: {article['link']}"
            send_telegram(message)

print(f"Bot run completed at {datetime.now()}")
