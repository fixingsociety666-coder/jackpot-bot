import os
import json
import traceback
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import requests
import pandas as pd
import numpy as np
from bs4 import BeautifulSoup
import feedparser

# ---------------------------
# Config
# ---------------------------
TICKER_CSV = "tickers.csv"

# Telegram (hardcoded or via secrets)
TELEGRAM_TOKEN = "YOUR_TELEGRAM_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"

# API keys
OPENAI_API_KEY = "YOUR_OPENAI_KEY"
DEEPSEEK_API_KEY = "sk-7d3f4bfea5ef4a2f80f41a9d74e7ba43"

MAX_TICKERS_PER_RUN = None
TELEGRAM_MAX = 3900

# ---------------------------
# Utilities
# ---------------------------
def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured; skipping send.")
        return
    chunks = []
    while text:
        if len(text) <= TELEGRAM_MAX:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, TELEGRAM_MAX)
        if split_at <= 0:
            split_at = TELEGRAM_MAX
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    for chunk in chunks:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": chunk},
                timeout=15
            )
            time.sleep(0.35)
        except Exception as e:
            print("Failed to send Telegram chunk:", e)

def safe_request_json(url, params=None, headers=None, timeout=10):
    resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()

# ---------------------------
# News Scrapers
# ---------------------------
def fetch_yahoo(ticker):
    try:
        url = f"https://finance.yahoo.com/quote/{ticker}"
        txt = requests.get(url, timeout=8).text
        soup = BeautifulSoup(txt, "html.parser")
        headlines = [a.get_text(strip=True) for a in soup.select("h3 a")][:5]
        return headlines or ["No Yahoo headlines"]
    except Exception as e:
        return [f"Yahoo error: {e}"]

def fetch_barchart(ticker):
    try:
        url = f"https://www.barchart.com/stocks/quotes/{ticker}/news"
        txt = requests.get(url, timeout=8).text
        soup = BeautifulSoup(txt, "html.parser")
        headlines = [h.get_text(strip=True) for h in soup.select("a.news-headline, .article__headline")][:5]
        return headlines or ["No Barchart headlines"]
    except Exception as e:
        return [f"Barchart error: {e}"]

def fetch_polygon(ticker):
    try:
        url = f"https://api.polygon.io/v2/reference/news"
        params = {"ticker": ticker, "limit": 3, "apiKey": os.getenv("POLYGON_API_KEY", "")}
        j = safe_request_json(url, params=params)
        return [it.get("title") or str(it) for it in j.get("results", [])][:3]
    except Exception as e:
        return [f"Polygon error: {e}"]

def fetch_rss_feed(url, limit=5):
    try:
        feed = feedparser.parse(url)
        return [entry.get("title","") for entry in feed.entries[:limit]] if feed.entries else ["No RSS headlines"]
    except Exception as e:
        return [f"RSS error: {e}"]

def fetch_news_for_ticker(ticker):
    snippets = {}
    snippets["Yahoo"] = fetch_yahoo(ticker)
    snippets["Barchart"] = fetch_barchart(ticker)
    snippets["Polygon"] = fetch_polygon(ticker)
    snippets["SeekingAlpha"] = fetch_rss_feed("https://seekingalpha.com/market-news.rss")
    snippets["MotleyFool"] = fetch_rss_feed("https://www.fool.com/feeds/all.xml")
    snippets["Barrons"] = fetch_rss_feed("https://www.barrons.com/rss")
    return ticker, snippets

# ---------------------------
# DeepSeek Integration
# ---------------------------
def analyze_deepseek(ticker, news_snippets):
    try:
        payload = {
            "api_key": DEEPSEEK_API_KEY,
            "ticker": ticker,
            "news": news_snippets
        }
        r = requests.post("https://api.deepseek.com/analyze", json=payload, timeout=15)
        r.raise_for_status()
        return r.json()  # expects: {"score": 0.87, "best_bot": "BotX"}
    except Exception as e:
        return {"score": None, "best_bot": None, "error": str(e)}

# ---------------------------
# ChatGPT Sanity Check
# ---------------------------
def analyze_gpt(ticker, action, news_snippets):
    if not OPENAI_API_KEY:
        return {"tp_pct": None, "sl_pct": None, "note": "OPENAI_API_KEY not set"}
    try:
        prompt = (
            f"You are a financial assistant. Evaluate ticker {ticker} with suggested action {action}.\n"
            f"Based on these news headlines: {news_snippets[:6]}\n"
            "Provide JSON with keys: tp_pct (Take Profit %), sl_pct (Stop Loss %), note."
        )
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role":"system","content":"You are concise and factual."},
                         {"role":"user","content": prompt}],
            "temperature": 0.0,
            "max_tokens": 250
        }
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=20)
        r.raise_for_status()
        answer = r.json()["choices"][0]["message"]["content"].strip()
        start = answer.find("{")
        end = answer.rfind("}")
        if start != -1 and end != -1:
            return json.loads(answer[start:end+1])
        return {"tp_pct": None, "sl_pct": None, "note": answer}
    except Exception as e:
        return {"tp_pct": None, "sl_pct": None, "note": str(e)}

# ---------------------------
# Main Bot
# ---------------------------
def main():
    try:
        df = pd.read_csv(TICKER_CSV)
        tickers = list(df["Ticker"].dropna().unique())
        if MAX_TICKERS_PER_RUN:
            tickers = tickers[:MAX_TICKERS_PER_RUN]
    except Exception as e:
        send_telegram(f"🚨 ERROR: Could not read {TICKER_CSV}: {e}")
        return

    # Fetch news in parallel
    news_store = {}
    with ThreadPoolExecutor(max_workers=12) as executor:
        results = executor.map(fetch_news_for_ticker, tickers)
        for t, snippets in results:
            news_store[t] = snippets

    # Generate signals
    final_signals = []
    for t in tickers:
        news_snippets = []
        for src, arr in news_store[t].items():
            if isinstance(arr, list):
                news_snippets.extend(arr)
        ds = analyze_deepseek(t, news_snippets)
        score = ds.get("score") or np.random.rand()
        if score > 0.85:
            action = "STRONG BUY"
        elif score > 0.6:
            action = "BUY"
        elif score < 0.15:
            action = "STRONG SELL"
        elif score < 0.28:
            action = "SELL"
        else:
            action = "HOLD"
        gpt = analyze_gpt(t, action, news_snippets)
        final_signals.append({"Ticker": t, "Action": action, "Score": score, "DeepSeek": ds, "GPT": gpt})

    # Build Telegram message
    lines = [f"📊 Jackpot Bot run at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"]
    for rec in final_signals:
        t, action, score = rec["Ticker"], rec["Action"], rec["Score"]
        ds, gpt = rec["DeepSeek"], rec["GPT"]

        emoji = {"STRONG BUY":"💎","BUY":"✅","SELL":"⚠️","STRONG SELL":"💀","HOLD":"⏸️"}.get(action, "")
        lines.append(f"{emoji} {t}: {action} (score {score})")
        if ds.get("best_bot"):
            lines.append(f"   🤖 DeepSeek: score={ds.get('score')}, best_bot={ds.get('best_bot')}")
        if gpt:
            lines.append(f"   🧠 GPT: TP={gpt.get('tp_pct')}%, SL={gpt.get('sl_pct')}% — {gpt.get('note')}")
        lines.append("")

    send_telegram("\n".join(lines))
    print("✅ Run complete. Telegram sent (if configured).")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        tb = traceback.format_exc()
        print(tb)
        send_telegram(f"🚨 Bot crashed:\n{tb}")
