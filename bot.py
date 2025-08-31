import pandas as pd
import requests
from bs4 import BeautifulSoup

# ----------------------
# User Config
# ----------------------
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"
CSV_FILE = "sample_portfolio.csv"

# ----------------------
# Helper Functions
# ----------------------

positive_keywords_news = ["surge", "upgrade", "bullish", "record", "strong", "beat expectations"]
positive_keywords_announcement = ["earnings beat", "new contract", "partnership", "guidance increase", "dividend increase"]
negative_keywords = ["downgrade", "sell", "weak", "loss", "fall", "decline", "lawsuit", "guidance cut"]

def news_sentiment(headlines):
    score = 0
    for h in headlines:
        h_lower = h.lower()
        if any(word in h_lower for word in positive_keywords_news):
            score += 1
        if any(word in h_lower for word in negative_keywords):
            score -= 1
    return score

def announcement_sentiment(headlines):
    score = 0
    for h in headlines:
        h_lower = h.lower()
        if any(word in h_lower for word in positive_keywords_announcement):
            score += 2  # stronger weight for official announcements
        if any(word in h_lower for word in negative_keywords):
            score -= 2
    return score

def get_news(ticker):
    # Simple Yahoo Finance scraper for news headlines
    url = f"https://finance.yahoo.com/quote/{ticker}?p={ticker}&.tsrc=fin-srch"
    headlines = []
    try:
        r = requests.get(url)
        soup = BeautifulSoup(r.text, 'html.parser')
        for item in soup.find_all('h3'):
            headlines.append(item.text.strip())
    except:
        pass
    return headlines[:5]  # top 5 headlines

# ----------------------
# Main Bot Logic
# ----------------------

df = pd.read_csv(CSV_FILE)

signals = []

for index, row in df.iterrows():
    ticker = row["Ticker"]

    # Generate fake score for demonstration (replace with real calculation)
    score = round(pd.np.random.rand(), 2) if hasattr(pd, 'np') else round((0.7 + 0.3 * pd.np.random.rand()) if hasattr(pd, 'np') else 0.85,2)

    news_headlines = get_news(ticker)
    news_score = news_sentiment(news_headlines)
    
    # For demonstration, assume company announcements are same as news
    announce_score = announcement_sentiment(news_headlines)

    # Strong buy filter
    if score >= 0.85 and news_score > 0 and announce_score > 0:
        signals.append({
            "Ticker": ticker,
            "Score": score,
            "NewsScore": news_score,
            "AnnounceScore": announce_score
        })

# ----------------------
# Send Telegram Alert
# ----------------------
if signals and TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    messages = [
        f"{s['Ticker']} → BUY (Score {s['Score']}, News {s['NewsScore']}, Announce {s['AnnounceScore']})"
        for s in signals
    ]
    text = "📈 Jackpot Bot Strong Buys + Positive News & Announcements:\n" + "\n".join(messages)
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": text}
        )
    except Exception as e:
        print(f"Telegram error: {e}")

# ----------------------
# Save signals CSV
# ----------------------
if signals:
    signals_df = pd.DataFrame(signals)
    signals_df.to_csv("signals/signals.csv", index=False)
