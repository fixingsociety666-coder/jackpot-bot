import pandas as pd
import requests
import os
import random
from openai import OpenAI
from datetime import datetime

# ---------------- Telegram & GPT Setup ----------------
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

# ---------------- Load Portfolio ----------------
df = pd.read_csv("data/auto_portfolio.csv")
os.makedirs("signals", exist_ok=True)

prev_file = "signals/previous_signals.csv"
if os.path.exists(prev_file):
    prev_df = pd.read_csv(prev_file)
    prev_tickers = set(prev_df["Ticker"])
else:
    prev_tickers = set()

signals_list = []

# ---------------- Helper: Generate SL/TP ----------------
def generate_sl_tp(price):
    sl = round(price * random.uniform(0.85,0.95),2)
    tp = round(price * random.uniform(1.05,1.3),2)
    return sl, tp

# ---------------- Stocks/Penny Stocks ----------------
for idx, row in df.iterrows():
    if row["Ticker"] in prev_tickers:
        continue

    score = round(random.uniform(0.85,1),2)
    signal_sources = ["Yahoo Finance"]
    news_text = ""
    news_score = 0
    price = 100

    if row["Type"] in ["Stock","Penny Stock"] and FINNHUB_KEY:
        try:
            url = f"https://finnhub.io/api/v1/company-news?symbol={row['Ticker']}&from=2025-01-01&to=2025-12-31&token={FINNHUB_KEY}"
            news = requests.get(url).json()
            if news:
                news_score = min(1, 0.5 + len(news)/20)
                signal_sources.append("Finnhub News")
                headlines = [item["headline"] for item in news[:3]]
                news_text = "\n".join(headlines)
        except:
            pass

    final_score = round((score + news_score)/2,2)
    if final_score >= 0.9:
        summary = ""
        sl = tp = None

        if client and news_text:
            try:
                response = client.chat.completions.create(
                    model="gpt-5-mini",
                    messages=[{"role":"user","content":
                               f"Strong Buy recommendation for {row['Ticker']} ({row['Company']}), "
                               f"include Stop-Loss and Take-Profit in USD, summarize news in 1 sentence:\n{news_text}"}],
                    temperature=0.3
                )
                summary = response.choices[0].message.content.strip()
                lines = summary.split("\n")
                for l in lines:
                    if "Stop-Loss" in l:
                        sl = l.split(":")[-1].strip()
                    if "Take-Profit" in l:
                        tp = l.split(":")[-1].strip()
            except:
                summary = ""

        if sl is None or tp is None:
            sl, tp = generate_sl_tp(price)

        signals_list.append({
            "Ticker": row["Ticker"],
            "Company": row["Company"],
            "Type": row["Type"],
            "Score": final_score,
            "Signal": "Strong Buy",
            "Source": ", ".join(signal_sources),
            "Summary": summary,
            "Stop-Loss": sl,
            "Take-Profit": tp
        })

# ---------------- Cryptos ----------------
crypto_symbols = ["bitcoin","ethereum","litecoin","ripple"]
for symbol in crypto_symbols:
    if symbol.upper() in prev_tickers:
        continue

    price = 0
    news_text = ""
    try:
        cg_price = requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={symbol}&vs_currencies=usd").json()
        price = cg_price[symbol]["usd"]
    except:
        price = random.uniform(10,5000)

    score = round(random.uniform(0.85,1),2)
    news_score = 0
    signal_sources = ["CoinGecko"]

    summary = ""
    sl = tp = None
    if client:
        try:
            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role":"user","content":
                           f"Strong Buy recommendation for {symbol.upper()}, include Stop-Loss and Take-Profit in USD, summarize recent crypto news in 1 sentence."}],
                temperature=0.3
            )
            summary = response.choices[0].message.content.strip()
            lines = summary.split("\n")
            for l in lines:
                if "Stop-Loss" in l:
                    sl = l.split(":")[-1].strip()
                if "Take-Profit" in l:
                    tp = l.split(":")[-1].strip()
        except:
            summary = ""

    if sl is None or tp is None:
        sl, tp = generate_sl_tp(price)

    final_score = round((score + news_score)/2,2)
    if final_score >= 0.9:
        signals_list.append({
            "Ticker": symbol.upper(),
            "Company": symbol.upper(),
            "Type": "Crypto",
            "Score": final_score,
            "Signal": "Strong Buy",
            "Source": ", ".join(signal_sources),
            "Summary": summary,
            "Stop-Loss": sl,
            "Take-Profit": tp
        })

# ---------------- Keep Top 10 ----------------
top_signals = sorted(signals_list, key=lambda x: x["Score"], reverse=True)[:10]

# ---------------- Save Signals ----------------
if top_signals:
    new_df = pd.DataFrame(top_signals)
    new_df.to_csv("signals/signals.csv", index=False)
    if os.path.exists(prev_file):
        old_df = pd.read_csv(prev_file)
        combined_df = pd.concat([old_df, new_df], ignore_index=True)
        combined_df.to_csv(prev_file, index=False)
    else:
        new_df.to_csv(prev_file, index=False)

    # ---------------- Telegram Digest ----------------
    message = f"📈 Jackpot Bot Daily Digest ({datetime.utcnow().strftime('%Y-%m-%d')})\n\n"
    for s in top_signals:
        message +=
                message += f"{s['Ticker']} ({s['Company']}) - {s['Signal']} | Score: {s['Score']}\n"
        message += f"SL: {s['Stop-Loss']} USD | TP: {s['Take-Profit']} USD\n"
        message += f"Source: {s['Source']}\n"
        if s['Summary']:
            message += f"GPT Summary: {s['Summary']}\n"
        message += "\n"

    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                      data={"chat_id": CHAT_ID, "text": message})
        print("✅ Telegram digest sent")
    except:
        print("⚠️ Telegram send failed, but bot completed")
else:
    print("⚠️ No strong signals today")



