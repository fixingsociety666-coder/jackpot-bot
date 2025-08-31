from polygon_data import get_current_price
from news_scraper import fetch_google_news, fetch_analyst_news
from sentiment import analyze_sentiment

def generate_entry_signal(symbol, price):
    tp = price*1.10
    sl = price*0.95
    return {"symbol": symbol, "entry": price, "take_profit": tp, "stop_loss": sl, "signal":"BUY"}

def check_exit_signal(symbol, entry_price):
    price = get_current_price(symbol)
    if not price:
        return False, ""
    # Exit logic
    if price >= entry_price*1.08:
        return True, "Take Profit"
    elif price <= entry_price*0.95:
        return True, "Stop Loss"
    # News-driven exit
    news_list = fetch_google_news(symbol) + fetch_analyst_news()
    for n in news_list:
        sentiment, score = analyze_sentiment(n["title"])
        if sentiment == "Bearish" and score < -0.4:
            return True, "Negative News Exit"
    return False, ""
