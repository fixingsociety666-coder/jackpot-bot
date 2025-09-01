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

# Read secrets from env (preferred).
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

BARCHART_API_KEY = os.getenv("BARCHART_API_KEY")
POLYGON_API_KEY  = os.getenv("POLYGON_API_KEY")
FINNHUB_API_KEY  = os.getenv("FINNHUB_API_KEY")
ALPHAVANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY")
APIFY_API_TOKEN  = os.getenv("APIFY_API_TOKEN")

# Optional testing limit
MAX_TICKERS_PER_RUN = None  # set to int for testing small batches

# ---------------------------
# Utilities
# ---------------------------
TELEGRAM_MAX = 3900  # chunk size limit for telegram messages

def send_telegram(text):
    """Send text to Telegram (split into chunks). If not configured, prints instead."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured; skipping send. (Message preview below)\n")
        print(text[:4000] + ("\n...[truncated]" if len(text) > 4000 else ""))
        return

    # chunk smartly
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
            resp = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": chunk},
                timeout=15
            )
            if resp.status_code != 200:
                print("Telegram send error:", resp.status_code, resp.text)
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
# (Kept intact)
# ---------------------------

# ... [All your existing fetch_from_* functions here, unchanged] ...

# ---------------------------
# Live price helper
# ---------------------------
def get_live_price_yahoo(ticker):
    try:
        url = "https://query1.finance.yahoo.com/v7/finance/quote"
        params = {"symbols": ticker}
        j = safe_request_json(url, params=params)
        q = j.get("quoteResponse", {}).get("result", [{}])[0]
        price = q.get("regularMarketPrice")
        if price is None:
            return None
        return float(price)
    except Exception:
        return None

# ---------------------------
# Historical price fetcher & trend signal
# ---------------------------
def get_historical_prices(ticker, period="1y", interval="1d"):
    """
    Fetch historical OHLC prices for a ticker.
    Returns DataFrame with columns: ['date','open','high','low','close','volume'].
    Tries Yahoo -> Polygon -> AlphaVantage.
    """
    df = None
    # --- Yahoo ---
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        params = {"range": period, "interval": interval}
        j = safe_request_json(url, params=params)
        res = j.get("chart", {}).get("result", [{}])[0]
        ts = res.get("timestamp", [])
        indicators = res.get("indicators", {}).get("quote", [{}])[0]
        if ts and indicators:
            df = pd.DataFrame({
                "date": pd.to_datetime(ts, unit="s"),
                "open": indicators.get("open", []),
                "high": indicators.get("high", []),
                "low": indicators.get("low", []),
                "close": indicators.get("close", []),
                "volume": indicators.get("volume", [])
            })
            return df.dropna()
    except Exception:
        pass

    # --- Polygon.io ---
    if POLYGON_API_KEY:
        try:
            url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/2022-01-01/2025-12-31"
            params = {"adjusted": "true", "sort": "asc", "apiKey": POLYGON_API_KEY}
            j = safe_request_json(url, params=params)
            results = j.get("results", [])
            if results:
                df = pd.DataFrame([{
                    "date": pd.to_datetime(r["t"], unit="ms"),
                    "open": r["o"], "high": r["h"], "low": r["l"], "close": r["c"], "volume": r["v"]
                } for r in results])
                return df
        except Exception:
            pass

    # --- AlphaVantage ---
    if ALPHAVANTAGE_KEY:
        try:
            url = "https://www.alphavantage.co/query"
            params = {"function": "TIME_SERIES_DAILY_ADJUSTED", "symbol": ticker, "outputsize": "full", "apikey": ALPHAVANTAGE_KEY}
            j = safe_request_json(url, params=params)
            ts_data = j.get("Time Series (Daily)", {})
            if ts_data:
                df = pd.DataFrame([{
                    "date": pd.to_datetime(d),
                    "open": float(v["1. open"]),
                    "high": float(v["2. high"]),
                    "low": float(v["3. low"]),
                    "close": float(v["4. close"]),
                    "volume": float(v["6. volume"])
                } for d,v in ts_data.items()])
                return df.sort_values("date")
        except Exception:
            pass

    return pd.DataFrame()

def historical_trend_signal(df):
    """
    Simple MA crossover trend:
    Returns 1 = bullish, -1 = bearish, 0 = neutral
    """
    if df.empty or len(df) < 50:
        return 0
    df = df.sort_values("date")
    df["MA20"] = df["close"].rolling(20).mean()
    df["MA50"] = df["close"].rolling(50).mean()
    if df["MA20"].iloc[-1] > df["MA50"].iloc[-1]:
        return 1
    elif df["MA20"].iloc[-1] < df["MA50"].iloc[-1]:
        return -1
    return 0

# ---------------------------
# Parallel news fetching helper
# ---------------------------
# ... [Your fetch_news_for_ticker function unchanged] ...

# ---------------------------
# ChatGPT sanity check, bot fallback, DeepSeek
# ... [All unchanged] ...

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

    os.makedirs("signals", exist_ok=True)
    os.makedirs("news", exist_ok=True)

    # 1) Generate initial signals list
    signals_list = [{"Ticker": t} for t in tickers]

    # 2) Parallel news fetching
    news_store = {}
    with ThreadPoolExecutor(max_workers=12) as executor:
        for t, snippets in executor.map(fetch_news_for_ticker, tickers):
            news_store[t] = snippets

    # save news snapshot
    news_file = f"news/latest_news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(news_file, "w") as f:
        json.dump(news_store, f, indent=2)

    # 3) Parallel live + historical price fetching
    prices_store = {}
    hist_store = {}

    def fetch_prices(ticker):
        live = get_live_price_yahoo(ticker)
        hist = get_historical_prices(ticker)
        return live, hist

    with ThreadPoolExecutor(max_workers=6) as price_executor:
        futures = {price_executor.submit(fetch_prices, t): t for t in tickers}
        for fut in futures:
            tkr = futures[fut]
            try:
                live_price, hist_df = fut.result()
                prices_store[tkr] = live_price
                hist_store[tkr] = hist_df
            except Exception:
                prices_store[tkr] = None
                hist_store[tkr] = pd.DataFrame()

    # 4) Loop over tickers
    final_signals = []
    for rec in signals_list:
        t = rec["Ticker"]
        snippets = news_store.get(t, {})

        # flatten headlines
        headlines_flat = []
        for src, arr in snippets.items():
            if isinstance(arr, list):
                headlines_flat.extend([str(x) for x in arr[:6]])
            elif isinstance(arr, dict):
                headlines_flat.extend([str(v) for v in list(arr.values())[:6]])
            else:
                headlines_flat.append(str(arr))

        # bot fallback
        bot = bot_fallback_score_and_trailing_offset(headlines_flat)

        # live price
        price = prices_store.get(t)
        historical_df = hist_store.get(t)
        trend_signal = historical_trend_signal(historical_df)  # 1=up, -1=down, 0=neutral

        # DeepSeek
        try:
            ds = call_deepseek(t, headlines_flat)
            if isinstance(ds, dict):
                ds_score = ds.get("score")
                ds_action = ds.get("recommendation") or ds.get("action") or None
                ds_trailing = ds.get("trailing_pct") or ds.get("trailing") or ds.get("trailingPercent")
                ds_offset = ds.get("offset_pct") or ds.get("offset") or ds.get("offsetPercent")
            else:
                ds_score = None; ds_action = None; ds_trailing = None; ds_offset = None
        except Exception as e:
            ds = f"DeepSeek exception: {e}"
            ds_score = ds_action = ds_trailing = ds_offset = None

        # ChatGPT sanity
        try:
            gpt = chatgpt_sanity({"Ticker": t, "BotAction": bot["action"], "BotScore": bot["score"], "Price": price}, headlines_flat)
            if isinstance(gpt, dict):
                gpt_ok = gpt.get("action_ok")
                gpt_trailing = gpt.get("trailing_pct") or gpt.get("trailing")
                gpt_offset = gpt.get("offset_pct") or gpt.get("offset")
                gpt_note = gpt.get("note")
            else:
                gpt_ok = None; gpt_trailing = None; gpt_offset = None; gpt_note = str(gpt)
        except Exception as e:
            gpt = f"ChatGPT exception: {e}"
            gpt_ok = None; gpt_trailing = None; gpt_offset = None; gpt_note = str(e)

        final = {
            "Ticker": t,
            "Price": price,
            "TrendSignal": trend_signal,  # optional internal use
            "Bot": {"score": bot["score"], "action": bot["action"], "trailing_pct": bot["trailing_pct"], "offset_pct": bot["offset_pct"]},
            "DeepSeek": {"raw": ds, "score": ds_score, "action": ds_action, "trailing_pct": ds_trailing, "offset_pct": ds_offset},
            "GPT": {"raw": gpt, "ok": gpt_ok, "trailing_pct": gpt_trailing, "offset_pct": gpt_offset, "note": gpt_note},
            "Headlines": headlines_flat[:20]
        }
        final_signals.append(final)

    # 5) Save signals CSV
    signals_out = []
    for f in final_signals:
        row = {
            "Ticker": f["Ticker"],
            "Price": f.get("Price"),
            "BotScore": f["Bot"]["score"],
            "BotAction": f["Bot"]["action"],
            "Bot_Trailing_pct": f["Bot"]["trailing_pct"],
            "Bot_Offset_pct": f["Bot"]["offset_pct"],
            "DeepSeek_raw": json.dumps(f["DeepSeek"]["raw"]) if f["DeepSeek"]["raw"] else "",
            "GPT_raw": json.dumps(f["GPT"]["raw"]) if f["GPT"]["raw"] else ""
        }
        signals_out.append(row)
    signals_df = pd.DataFrame(signals_out)
    signals_file = f"signals/trading_signals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    signals_df.to_csv(signals_file, index=False)

    # 6) Build clean Telegram message
    lines = []
    lines.append(f"📊 Jackpot Bot run at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n")

    final_signals_filtered = [f for f in final_signals if f["Bot"]["action"] in ["STRONG BUY", "STRONG SELL"]]
    order_priority = {"STRONG BUY": 0, "STRONG SELL": 1}
    final_signals_sorted = sorted(
        final_signals_filtered,
        key=lambda x: order_priority.get(x["Bot"]["action"], 99)
    )

    if not final_signals_sorted:
        lines.append("No STRONG BUY or STRONG SELL signals this run.")
    else:
        for f in final_signals_sorted:
            t = f["Ticker"]
            bot = f["Bot"]
            ds = f["DeepSeek"]
            gpt = f["GPT"]
            price = f.get("Price")

            icon = "🟢" if bot["action"] == "STRONG BUY" else "🔴"
            price_str = f"${price:.2f}" if isinstance(price, (int, float)) else "Price N/A"
            lines.append(f"{icon} {t} — {bot['action']} (bot score {bot['score']}) — {price_str}")

            lines.append(f"   🛠 Bot → Trailing: {bot['trailing_pct']}% | Offset: {bot['offset_pct']}%")

            if isinstance(ds["raw"], dict):
                ds_tr = ds.get("trailing_pct")
                ds_off = ds.get("offset_pct")
                lines.append(f"   🔍 DeepSeek → rec: {ds.get('action')} | trailing: {ds_tr}% | offset: {ds_off}%")
            else:
                lines.append(f"   🔍 DeepSeek → {ds['raw']}")

            if isinstance(gpt["raw"], dict):
                g_tr = gpt.get("trailing_pct")
                g_off = gpt.get("offset_pct")
                lines.append(f"   🤖 GPT → ok: {gpt.get('ok')} | trailing: {g_tr}% | offset: {g_off}% — {gpt.get('note')}")
            else:
                lines.append(f"   🤖 GPT → {gpt['raw']}")

            lines.append("")

    message = "\n".join(lines)
    send_telegram(message)

    print("✅ Run complete. Telegram sent (if configured).")
    print(f"Signals -> {signals_file}, News -> {news_file}")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        tb = traceback.format_exc()
        print(tb)
        send_telegram(f"🚨 Bot crashed:\n{tb}")
