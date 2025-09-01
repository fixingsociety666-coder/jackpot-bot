# bot.py
import os
import json
import traceback
from datetime import datetime
import time

import requests
import pandas as pd
import numpy as np
from bs4 import BeautifulSoup
import feedparser
from concurrent.futures import ThreadPoolExecutor  # added for parallel news fetching

# ---------------------------
# Config / Environment names
# ---------------------------
TICKER_CSV = "tickers.csv"

# Telegram (set these in GitHub Secrets / env)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")        # e.g. '123456:ABC...'
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")    # numeric chat id (or group id -100...)

# API keys (optional - set if you have them)
BARCHART_API_KEY = os.getenv("BARCHART_API_KEY")
POLYGON_API_KEY  = os.getenv("POLYGON_API_KEY")
FINNHUB_API_KEY  = os.getenv("FINNHUB_API_KEY")
ALPHAVANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY")
APIFY_API_TOKEN  = os.getenv("APIFY_API_TOKEN")     # for Apify scraping actors
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY")

# DeepSeek
DEESEEK_API_KEY  = "sk-7d3f4bfea5ef4a2f80f41a9d74e7ba43"
DEESEEK_ENDPOINT = "https://api.deepseek.com/signal"

# Optional: limit (in case you want to test quickly)
MAX_TICKERS_PER_RUN = None  # set to int for testing small batches

# ---------------------------
# Utilities
# ---------------------------
TELEGRAM_MAX = 3900  # safe message chunk size

def send_telegram(text):
    """Send text to Telegram, split if too long. Safe no-op if not configured."""
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
# (keeping all original functions as-is)
# ---------------------------

# ...[Keep all your original fetch_from_* functions here]...

# ---------------------------
# DeepSeek API fetch
# ---------------------------
def fetch_deepseek_signal(ticker):
    try:
        payload = {"ticker": ticker}
        headers = {"Authorization": f"Bearer {DEESEEK_API_KEY}", "Content-Type": "application/json"}
        r = requests.post(DEESEEK_ENDPOINT, json=payload, headers=headers, timeout=15)
        r.raise_for_status()
        res = r.json()
        return res  # expected: {"signal":"BUY","confidence":0.85,"tp_pct":5,"sl_pct":2}
    except Exception as e:
        return {"signal":"UNKNOWN","confidence":0,"tp_pct":None,"sl_pct":None,"error":str(e)}

# ---------------------------
# Parallel news fetching
# ---------------------------
def fetch_news_for_ticker(t):
    snippets = {}
    try:
        snippets["Yahoo"] = fetch_from_yahoo_per_ticker(t)
    except Exception as e:
        snippets["Yahoo"] = [f"Yahoo error wrapper: {e}"]

    snippets["Barchart"] = fetch_from_barchart(t)
    snippets["Polygon"] = fetch_from_polygon(t)
    snippets["Finnhub"] = fetch_from_finnhub(t)
    snippets["AlphaVantage"] = fetch_from_alpha_vantage(t)
    snippets["MarketWatch"] = fetch_from_marketwatch(t)

    try:
        url = f"https://www.cnbc.com/quotes/{t}"
        txt = safe_request_text(url)
        soup = BeautifulSoup(txt, "html.parser")
        cnbc_head = [a.get_text(strip=True) for a in soup.select("a.Card-title")][:3] or []
        snippets["CNBC"] = cnbc_head or ["No CNBC headlines"]
    except Exception as e:
        snippets["CNBC"] = [f"CNBC error: {e}"]

    try:
        snippets["SeekingAlpha"] = fetch_from_seekingalpha_rss()
    except Exception as e:
        snippets["SeekingAlpha"] = [f"SeekingAlpha wrapper error: {e}"]

    snippets["MotleyFool"] = fetch_from_motleyfool_rss()
    snippets["Barrons"] = fetch_from_barrons_rss()
    snippets["TipRanks"] = fetch_from_tipranks_via_apify()

    return t, snippets

# ---------------------------
# ChatGPT sanity check
# ---------------------------
def chatgpt_sanity(signals_for_ticker, headlines):
    if not OPENAI_API_KEY:
        return "ChatGPT skipped (OPENAI_API_KEY not set)"
    try:
        prompt = (
            "You are a sober financial assistant. For each ticker below, "
            "answer in 2-4 sentences whether the suggested action seems reasonable "
            "given the headlines. If reasonable, provide a suggested Take Profit and Stop Loss (as percentages), "
            "and one short risk note. Output as JSON with keys: action_ok(bool), tp_pct, sl_pct, note.\n\n"
            f"Ticker data: {json.dumps(signals_for_ticker)}\n\nHeadlines: {json.dumps(headlines[:6])}"
        )

        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": "You are a concise, factual financial assistant."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.0,
            "max_tokens": 250
        }
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=20)
        r.raise_for_status()
        out = r.json()
        answer = out["choices"][0]["message"]["content"].strip()
        try:
            start = answer.find("{")
            end = answer.rfind("}")
            if start != -1 and end != -1:
                parsed = json.loads(answer[start:end+1])
                return parsed
        except Exception:
            pass
        return answer
    except Exception as e:
        return f"ChatGPT error: {e}"

# ---------------------------
# Main
# ---------------------------
def main():
    start_time = datetime.utcnow().isoformat()
    try:
        df = pd.read_csv(TICKER_CSV)
    except Exception as e:
        tb = traceback.format_exc()
        send_telegram(f"🚨 ERROR: could not read {TICKER_CSV}: {e}\n\n{tb}")
        return

    tickers = list(df["Ticker"].dropna().astype(str).unique())
    if MAX_TICKERS_PER_RUN:
        tickers = tickers[:MAX_TICKERS_PER_RUN]

    results = {}
    signals_list = []

    os.makedirs("signals", exist_ok=True)
    os.makedirs("news", exist_ok=True)

    # 1) Generate signals
    for t in tickers:
        score = round(float(np.random.rand()), 2)
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
        signals_list.append({"Ticker": t, "Score": score, "Action": action})

    # Optional: sort signals Strong Buy -> Strong Sell -> Buy -> Sell -> Hold
    order_map = {"STRONG BUY":0,"STRONG SELL":1,"BUY":2,"SELL":3,"HOLD":4}
    signals_list.sort(key=lambda x: order_map.get(x['Action'], 5))

    # Save signals CSV
    signals_df = pd.DataFrame(signals_list)
    signals_file = f"signals/trading_signals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    signals_df.to_csv(signals_file, index=False)

    # 2) Parallel news fetching
    news_store = {}
    with ThreadPoolExecutor(max_workers=12) as executor:
        results = executor.map(fetch_news_for_ticker, tickers)
        for t, snippets in results:
            news_store[t] = snippets

    news_file = f"news/latest_news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(news_file, "w") as f:
        json.dump(news_store, f, indent=2)

    # 3) ChatGPT sanity check
    sanity_results = {}
    for rec in signals_list:
        ticker = rec["Ticker"]
        if rec["Action"] in ("BUY", "STRONG BUY", "SELL", "STRONG SELL"):
            try:
                signal_obj = {"Ticker": ticker, "Action": rec["Action"], "Score": rec["Score"]}
                headlines_flat = []
                for src, arr in news_store.get(ticker, {}).items():
                    if isinstance(arr, list):
                        headlines_flat.extend([str(x) for x in arr[:4]])
                    elif isinstance(arr, dict):
                        headlines_flat.extend([str(v) for v in list(arr.values())[:4]])
                    else:
                        headlines_flat.append(str(arr))
                sanity = chatgpt_sanity(signal_obj, headlines_flat)
                sanity_results[ticker] = sanity
            except Exception as e:
                sanity_results[ticker] = f"Sanity check error: {e}"

    # 4) Build Telegram message
    lines = []
    lines.append(f"📊 Jackpot Bot run at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
    emoji_map = {"STRONG BUY":"💎","BUY":"✅","STRONG SELL":"⚠️","SELL":"❌","HOLD":"✋"}

    for rec in signals_list:
        t = rec['Ticker']
        action = rec['Action']
        score = rec['Score']

        # Visual differentiation
        lines.append(f"{emoji_map.get(action, '')} {t}: {action} (score {score})")

        # DeepSeek
        deep = fetch_deepseek_signal(t)

        # GPT sanity
        fr = sanity_results.get(t, {})
        tp_list = [v for v in [deep.get("tp_pct"), fr.get("tp_pct") if isinstance(fr, dict) else None] if v is not None]
        sl_list = [v for v in [deep.get("sl_pct"), fr.get("sl_pct") if isinstance(fr, dict) else None] if v is not None]
        tp_final = max(tp_list) if tp_list else "N/A"
        sl_final = min(sl_list) if sl_list else "N/A"
        lines.append(f"   💹 TP: {tp_final}% | SL: {sl_final}% | DeepSeek: {deep.get('signal')}, confidence {deep.get('confidence')}")

        lines.append("")

    lines.append(f"📂 Signals saved: {signals_file}")
    lines.append(f"📂 News saved: {news_file}")

    message = "\n".join(lines)
    send_telegram(message)

    print("✅ Run complete. Telegram sent (if configured).")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        tb = traceback.format_exc()
        print(tb)
        send_telegram(f"🚨 Bot crashed:\n{tb}")
