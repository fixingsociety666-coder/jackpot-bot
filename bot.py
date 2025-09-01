# bot.py
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
# Config / Environment names
# ---------------------------
TICKER_CSV = "tickers.csv"

# Hardcoded API keys
TELEGRAM_TOKEN = "YOUR_TELEGRAM_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"
OPENAI_API_KEY = "YOUR_OPENAI_KEY"
DEEPSEEK_API_KEY = "sk-7d3f4bfea5ef4a2f80f41a9d74e7ba43"

# Optional: limit for testing
MAX_TICKERS_PER_RUN = None

# ---------------------------
# Telegram utils
# ---------------------------
TELEGRAM_MAX = 3900

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

# ---------------------------
# Safe requests
# ---------------------------
def safe_request_json(url, params=None, headers=None, timeout=8):
    resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()

def safe_request_text(url, params=None, headers=None, timeout=8):
    resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text

# ---------------------------
# News fetchers
# ---------------------------
def fetch_yahoo_news(ticker):
    try:
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={ticker}"
        j = safe_request_json(url)
        q = j.get("quoteResponse", {}).get("result", [{}])[0]
        snippets = []
        if q.get("regularMarketPrice"):
            snippets.append(f"Price: {q['regularMarketPrice']}")
        page = safe_request_text(f"https://finance.yahoo.com/quote/{ticker}")
        soup = BeautifulSoup(page, "html.parser")
        headlines = [a.get_text(strip=True) for a in soup.select("h3 a")][:3]
        snippets.extend(headlines or [])
        return snippets or ["No Yahoo data"]
    except Exception as e:
        return [f"Yahoo error: {e}"]

def fetch_rss(url, limit=5):
    try:
        feed = feedparser.parse(url)
        return [e.get("title","") for e in feed.entries[:limit]] if feed.entries else ["No feed data"]
    except Exception as e:
        return [f"RSS fetch error: {e}"]

def fetch_news_for_ticker(ticker):
    snippets = {}
    snippets["Yahoo"] = fetch_yahoo_news(ticker)
    snippets["SeekingAlpha"] = fetch_rss("https://seekingalpha.com/market-news.rss")
    snippets["MotleyFool"] = fetch_rss("https://www.fool.com/feeds/all.xml")
    snippets["Barrons"] = fetch_rss("https://www.barrons.com/rss")
    return ticker, snippets

# ---------------------------
# Bot fallback signal
# ---------------------------
def bot_signal_calculation(ticker, headlines):
    score = round(np.random.rand(),2)
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
    tp = round(score*20 + 5,1)  # bot suggested take profit %
    sl = round((1-score)*15 + 1,1)  # bot suggested stop loss %
    return {"Score": score, "Action": action, "TP": tp, "SL": sl}

# ---------------------------
# DeepSeek API
# ---------------------------
def deepseek_score(ticker):
    try:
        url = f"https://api.deepseek.com/signal?ticker={ticker}"
        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        j = r.json()
        return {"Score": j.get("score"), "Action": j.get("recommendation"), "TP": j.get("take_profit"), "SL": j.get("stop_loss")}
    except Exception as e:
        return f"DeepSeek error: {e}"

# ---------------------------
# ChatGPT sanity
# ---------------------------
def chatgpt_sanity(signal_obj, headlines):
    if not OPENAI_API_KEY:
        return "ChatGPT skipped"
    try:
        prompt = (
            "You are a sober financial assistant. For the ticker below, "
            "provide a sanity check on the suggested action. Include TP% and SL% suggestions.\n"
            f"Signal: {json.dumps(signal_obj)}\nHeadlines: {json.dumps(headlines[:6])}\n"
            "Output JSON with keys: action_ok(bool), tp_pct, sl_pct, note"
        )
        payload = {
            "model":"gpt-3.5-turbo",
            "messages":[{"role":"system","content":"You are concise and factual."},
                        {"role":"user","content":prompt}],
            "temperature":0.0,
            "max_tokens":250
        }
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}","Content-Type":"application/json"}
        r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=20)
        r.raise_for_status()
        answer = r.json()["choices"][0]["message"]["content"].strip()
        start = answer.find("{")
        end = answer.rfind("}")
        if start != -1 and end != -1:
            return json.loads(answer[start:end+1])
        return answer
    except Exception as e:
        return f"ChatGPT error: {e}"

# ---------------------------
# Main
# ---------------------------
def main():
    try:
        df = pd.read_csv(TICKER_CSV)
    except Exception as e:
        send_telegram(f"🚨 ERROR: Could not read {TICKER_CSV}: {e}")
        return
    tickers = list(df["Ticker"].dropna().unique())
    if MAX_TICKERS_PER_RUN:
        tickers = tickers[:MAX_TICKERS_PER_RUN]

    # Fetch news in parallel
    news_store = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        for t, snippets in executor.map(fetch_news_for_ticker, tickers):
            news_store[t] = snippets

    # Calculate signals
    signals_list = []
    for t in tickers:
        headlines_flat = []
        for src, arr in news_store.get(t, {}).items():
            if isinstance(arr, list):
                headlines_flat.extend([str(x) for x in arr[:4]])
            elif isinstance(arr, dict):
                headlines_flat.extend([str(v) for v in list(arr.values())[:4]])
            else:
                headlines_flat.append(str(arr))

        # 1. Bot fallback
        bot_sig = bot_signal_calculation(t, headlines_flat)

        # 2. DeepSeek
        ds_sig = deepseek_score(t)

        # 3. ChatGPT
        gpt_sig = chatgpt_sanity(bot_sig, headlines_flat)

        signals_list.append({"Ticker": t, "Bot": bot_sig, "DeepSeek": ds_sig, "GPT": gpt_sig})

    # Build Telegram message
    lines = []
    lines.append(f"📊 Jackpot Bot run at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
    for rec in signals_list:
        t = rec["Ticker"]
        bot_sig = rec["Bot"]
        ds_sig = rec["DeepSeek"]
        gpt_sig = rec["GPT"]

        # Visual for bot action
        action = bot_sig["Action"]
        score = bot_sig["Score"]
        if action == "STRONG BUY": icon = "💎"
        elif action == "BUY": icon = "✅"
        elif action == "STRONG SELL": icon = "💀"
        elif action == "SELL": icon = "⚠️"
        else: icon = "⏸️"
        lines.append(f"{icon} {t}: {action} (score {score})")
        lines.append(f"   🛠 Bot TP: {bot_sig['TP']}%, SL: {bot_sig['SL']}%")

        # DeepSeek
        if isinstance(ds_sig, dict):
            lines.append(f"   🔍 DeepSeek: {ds_sig.get('Action')} | TP: {ds_sig.get('TP')}%, SL: {ds_sig.get('SL')}%")
        else:
            lines.append(f"   🔍 DeepSeek: {ds_sig}")

        # ChatGPT
        if isinstance(gpt_sig, dict):
            lines.append(f"   🤖 GPT: ok={gpt_sig.get('action_ok')}, TP={gpt_sig.get('tp_pct')}%, SL={gpt_sig.get('sl_pct')}% — {gpt_sig.get('note')}")
        else:
            lines.append(f"   🤖 GPT: {gpt_sig}")

        # Headlines (first 3 sources)
        snippets = news_store.get(t, {})
        for src in ["Yahoo","SeekingAlpha","MotleyFool","Barrons"]:
            if src in snippets:
                excerpt = snippets[src][0] if snippets[src] else "no headlines"
                lines.append(f"   📰 {src}: {excerpt}")
        lines.append("")

    message = "\n".join(lines)
    send_telegram(message)
    print("✅ Run complete. Telegram sent.")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        tb = traceback.format_exc()
        print(tb)
        send_telegram(f"🚨 Bot crashed:\n{tb}")
