import requests
import pandas as pd
from telegram import Bot
import os
import openai

# Environment variables from GitHub secrets
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

bot = Bot(token=TELEGRAM_TOKEN)
openai.api_key = OPENAI_API_KEY

# CSV with tickers you want to track
TICKERS_CSV = "tickers.csv"
tickers_df = pd.read_csv(TICKERS_CSV)
tracked_tickers = tickers_df['Ticker'].tolist()

# News sources
NEWS_SOURCES = {
    "MotleyFool": "https://api.mock-motleyfool.com/top-picks",
    "SeekingAlpha": "https://api.mock-seekingalpha.com/top-picks",
    "MarketWatch": "https://api.mock-marketwatch.com/top-stocks",
    "Barchart": "https://api.mock-barchart.com/top-stocks",
    "TipsRank": "https://api.mock-tipsrank.com/top-picks",
    "Barrons": "https://api.mock-barrons.com/top-stocks",
    "YahooFinance": "https://api.mock-yahoo.com/top-stocks"
}

def fetch_source(source_name, url):
    """Fetch data from one news source"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()  # Replace with parsing logic if RSS
        return data
    except Exception as e:
        return {"error": f"Failed to fetch {source_name}: {str(e)}"}

def chatgpt_sanity_check(signals):
    """Ask ChatGPT to review signals for sanity"""
    if not signals:
        return "No signals to check."
    prompt = f"Review these stock signals for sanity and give feedback:\n{signals}"
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5
        )
        feedback = response['choices'][0]['message']['content']
        return feedback
    except Exception as e:
        return f"ChatGPT sanity check failed: {str(e)}"

def compile_alert():
    alert_lines = []
    matched_signals = []

    for source_name, url in NEWS_SOURCES.items():
        source_data = fetch_source(source_name, url)
        if "error" in source_data:
            alert_lines.append(source_data["error"])
            continue

        for item in source_data.get("top_picks", []):
            ticker = item.get("ticker")
            if ticker in tracked_tickers:
                price = item.get("price", 0)
                tp = item.get("take_profit", 0.0)
                sl = item.get("stop_loss", 0.0)
                signal_text = f"{ticker} | Price: {price}, TP: {tp}, SL: {sl} | Source: {source_name}"
                matched_signals.append(signal_text)

    if matched_signals:
        feedback = chatgpt_sanity_check("\n".join(matched_signals))
        alert_lines.append("💡 Signals & ChatGPT feedback:\n")
        alert_lines.extend(matched_signals)
        alert_lines.append("\n📝 ChatGPT Feedback:\n" + feedback)
    else:
        alert_lines.append("No signals found.")

    return "\n\n".join(alert_lines)

def send_telegram_alert():
    alert_message = compile_alert()
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=alert_message)

if __name__ == "__main__":
    send_telegram_alert()
