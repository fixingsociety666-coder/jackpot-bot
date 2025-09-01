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

# Read secrets from env (preferred). If you truly want hardcoded keys, replace the os.getenv(...) below.
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
# News fetchers (APIs, RSS, scraping)
# Each returns a list of short strings (headlines/snippets) or an error string list
# ---------------------------

def fetch_from_barchart(ticker):
    if BARCHART_API_KEY:
        try:
            url = "https://marketdata.websol.barchart.com/getNews.json"
            params = {"apikey": BARCHART_API_KEY, "symbols": ticker}
            j = safe_request_json(url, params=params)
            items = []
            for it in j.get("news", [])[:5]:
                title = it.get("headline") or it.get("title") or str(it)
                items.append(title)
            return items or ["No Barchart news"]
        except Exception as e:
            return [f"Barchart API error: {e}"]
    try:
        url = f"https://www.barchart.com/stocks/quotes/{ticker}/news"
        text = safe_request_text(url)
        soup = BeautifulSoup(text, "html.parser")
        headlines = [h.get_text(strip=True) for h in soup.select("a.news-headline, .article__headline")][:5]
        return headlines or ["No Barchart headlines (scrape)"]
    except Exception as e:
        return [f"Barchart scrape error: {e}"]

def fetch_from_polygon(ticker):
    if not POLYGON_API_KEY:
        return ["Polygon not configured"]
    try:
        url = "https://api.polygon.io/v2/reference/news"
        params = {"ticker": ticker, "limit": 3, "apiKey": POLYGON_API_KEY}
        j = safe_request_json(url, params=params)
        items = [it.get("title") or it.get("summary") for it in j.get("results", [])][:3]
        return items or ["No Polygon news"]
    except Exception as e:
        return [f"Polygon error: {e}"]

def fetch_from_finnhub(ticker):
    if not FINNHUB_API_KEY:
        return ["Finnhub not configured"]
    try:
        today = datetime.utcnow().date()
        frm = (today.replace(year=today.year - 1)).isoformat()
        to = today.isoformat()
        url = "https://finnhub.io/api/v1/company-news"
        params = {"symbol": ticker, "from": frm, "to": to, "token": FINNHUB_API_KEY}
        j = safe_request_json(url, params=params)
        items = [it.get("headline") or str(it) for it in j][:3]
        return items or ["No Finnhub news"]
    except Exception as e:
        return [f"Finnhub error: {e}"]

def fetch_from_alpha_vantage(ticker):
    if not ALPHAVANTAGE_KEY:
        return ["AlphaVantage not configured"]
    try:
        url = "https://www.alphavantage.co/query"
        params = {"function": "NEWS_SENTIMENT", "tickers": ticker, "apikey": ALPHAVANTAGE_KEY}
        j = safe_request_json(url, params=params)
        items = []
        for it in j.get("feed", [])[:3]:
            items.append(it.get("title") if isinstance(it, dict) and it.get("title") else str(it))
        return items or ["No AlphaVantage news"]
    except Exception as e:
        return [f"AlphaVantage error: {e}"]

def fetch_from_seekingalpha_rss():
    try:
        candidate_feeds = [
            "https://seekingalpha.com/market-news.rss",
            "https://seekingalpha.com/feed.xml",
            "https://seekingalpha.com/market-news.xml"
        ]
        for feed in candidate_feeds:
            try:
                f = feedparser.parse(feed)
                if f and getattr(f, "entries", None):
                    return [entry.get("title", "") for entry in f.entries[:6]]
            except Exception:
                continue
        return ["No SeekingAlpha RSS found"]
    except Exception as e:
        return [f"SeekingAlpha error: {e}"]

def fetch_from_motleyfool_rss():
    try:
        feed = feedparser.parse("https://www.fool.com/feeds/all.xml")
        if feed and getattr(feed, "entries", None):
            return [e.get("title", "") for e in feed.entries[:6]]
        return ["No Motley Fool RSS"]
    except Exception as e:
        return [f"MotleyFool error: {e}"]

def fetch_from_tipranks_via_apify():
    if not APIFY_API_TOKEN:
        return ["TipRanks (Apify) not configured"]
    try:
        api_url = "https://api.apify.com/v2/acts/scraped~analysts-top-rated-stocks-tipranks/runs"
        params = {"token": APIFY_API_TOKEN, "waitForFinish": "true"}
        r = requests.post(api_url, params=params, timeout=30)
        r.raise_for_status()
        run = r.json()
        dataset_url = run.get("defaultDatasetId") and f"https://api.apify.com/v2/datasets/{run['defaultDatasetId']}/items?token={APIFY_API_TOKEN}"
        if dataset_url:
            d = requests.get(dataset_url, timeout=20).json()
            titles = [item.get("title") or item.get("ticker") or str(item) for item in d][:6]
            return titles or ["No TipRanks results from Apify"]
        return ["TipRanks Apify run started but no dataset id"]
    except Exception as e:
        return [f"TipRanks/Apify error: {e}"]

def fetch_from_marketwatch(ticker):
    try:
        url = f"https://www.marketwatch.com/investing/stock/{ticker}"
        txt = safe_request_text(url)
        soup = BeautifulSoup(txt, "html.parser")
        headlines = [el.get_text(strip=True) for el in soup.select("div.article__content a")] or \
                    [el.get_text(strip=True) for el in soup.select("h3 a")]
        return headlines[:4] if headlines else ["No MarketWatch headlines"]
    except Exception as e:
        return [f"MarketWatch error: {e}"]

def fetch_from_barrons_rss():
    try:
        feed = feedparser.parse("https://www.barrons.com/rss")
        if feed and getattr(feed, "entries", None):
            return [e.get("title","") for e in feed.entries[:6]]
        return ["No Barron's RSS (try other source)"]
    except Exception as e:
        return [f"Barrons error: {e}"]

def fetch_from_yahoo_per_ticker(ticker):
    try:
        url = "https://query1.finance.yahoo.com/v7/finance/quote"
        params = {"symbols": ticker}
        j = safe_request_json(url, params=params)
        q = j.get("quoteResponse", {}).get("result", [{}])[0]
        snippets = []
        if q:
            snippets.append(f"Price: {q.get('regularMarketPrice')}")
            if q.get("longName"):
                snippets.append(q.get("longName"))
        page = safe_request_text(f"https://finance.yahoo.com/quote/{ticker}")
        soup = BeautifulSoup(page, "html.parser")
        headlines = [a.get_text(strip=True) for a in soup.select("h3 a")] or []
        if headlines:
            snippets.extend(headlines[:3])
        return snippets or ["No Yahoo data"]
    except Exception as e:
        return [f"Yahoo error: {e}"]

# ---------------------------
# Parallel news fetching helper
# ---------------------------
def fetch_news_for_ticker(t):
    """Fetch news from all sources for a single ticker safely."""
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
# ChatGPT sanity check (OpenAI)
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
# Bot fallback scoring (always runs)
# ---------------------------
def bot_fallback_score_and_tp_sl(headlines):
    """
    Always-run fallback algorithm:
    - simple keyword sentiment across headlines
    - base score in [0,1]
    - map to action, produce bot TP (aggressive) and SL (conservative)
    """
    text = " ".join([str(h).lower() for h in headlines])
    if not text.strip():
        # no data: neutral
        score = 0.5
    else:
        buy_keywords = ["upgrade", "buy", "strong buy", "outperform", "beats", "beat", "surge", "gain", "record"]
        sell_keywords = ["downgrade", "sell", "strong sell", "miss", "misses", "loss", "fall", "decline", "bearish"]
        buy_hits = sum(text.count(k) for k in buy_keywords)
        sell_hits = sum(text.count(k) for k in sell_keywords)
        total = buy_hits + sell_hits
        if total == 0:
            # neutral baseline but slightly biased to 0.5
            score = 0.5
        else:
            # scale to [0,1] where buys increase score
            score = float(buy_hits) / float(total)

        # blend with small random to avoid ties and add variety
        score = max(0.0, min(1.0, round(0.85*score + 0.15*float(np.random.rand()), 3)))

    # Map to actions
    if score >= 0.85:
        action = "STRONG BUY"
    elif score >= 0.6:
        action = "BUY"
    elif score <= 0.15:
        action = "STRONG SELL"
    elif score <= 0.28:
        action = "SELL"
    else:
        action = "HOLD"

    # Bot-suggested TP/SL logic (always available)
    # TP: larger for higher score, SL: smaller for higher score
    tp_pct = round( (0.5 + score*2.5) * 10, 2 )  # roughly maps score->TP in a wider scale
    sl_pct = round( max(0.5, (1.2 - score)*5 ), 2 )  # maps inverse to score
    return {"score": score, "action": action, "tp_pct": tp_pct, "sl_pct": sl_pct}

# ---------------------------
# DeepSeek integration (optional, may fail)
# ---------------------------
def call_deepseek(ticker, headlines):
    """
    Example DeepSeek call. Replace endpoint/path if DeepSeek provides different API.
    Returns dict or error-string.
    """
    if not DEEPSEEK_API_KEY:
        return "DeepSeek skipped (no API key)"
    try:
        # hypothetical endpoint - adjust if actual DeepSeek endpoint is different
        url = "https://api.deepseek.com/analyze"
        payload = {"api_key": DEEPSEEK_API_KEY, "ticker": ticker, "news": headlines[:20]}
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        j = r.json()
        # expect something like: {"score":0.87, "recommendation":"BUY", "take_profit":20, "stop_loss":5}
        return j
    except Exception as e:
        return f"DeepSeek error: {e}"

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

    # create folders
    os.makedirs("signals", exist_ok=True)
    os.makedirs("news", exist_ok=True)

    # 1) Generate initial signals list (we'll always compute bot fallback per ticker)
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

    # 3) For each ticker: bot fallback (always), then attempt DeepSeek + ChatGPT
    final_signals = []
    for rec in signals_list:
        t = rec["Ticker"]
        snippets = news_store.get(t, {})
        # flatten headlines for analysis
        headlines_flat = []
        for src, arr in snippets.items():
            if isinstance(arr, list):
                headlines_flat.extend([str(x) for x in arr[:6]])
            elif isinstance(arr, dict):
                headlines_flat.extend([str(v) for v in list(arr.values())[:6]])
            else:
                headlines_flat.append(str(arr))

        # ALWAYS compute bot fallback
        bot = bot_fallback_score_and_tp_sl(headlines_flat)

        # try DeepSeek
        try:
            ds = call_deepseek(t, headlines_flat)
            if isinstance(ds, dict):
                # if deepseek returned its own score/TP/SL, keep them
                ds_score = ds.get("score")
                ds_action = ds.get("recommendation") or ds.get("action") or None
                ds_tp = ds.get("take_profit") or ds.get("tp") or ds.get("TP")
                ds_sl = ds.get("stop_loss") or ds.get("sl") or ds.get("SL")
            else:
                ds_score = None
                ds_action = None
                ds_tp = None
                ds_sl = None
        except Exception as e:
            ds = f"DeepSeek exception: {e}"
            ds_score = ds_action = ds_tp = ds_sl = None

        # try ChatGPT sanity
        try:
            gpt = chatgpt_sanity({"Ticker": t, "BotAction": bot["action"], "BotScore": bot["score"]}, headlines_flat)
            # if gpt returned dict parse keys
            if isinstance(gpt, dict):
                gpt_ok = gpt.get("action_ok")
                gpt_tp = gpt.get("tp_pct") or gpt.get("tp") or None
                gpt_sl = gpt.get("sl_pct") or gpt.get("sl") or None
                gpt_note = gpt.get("note")
            else:
                gpt_ok = None; gpt_tp = None; gpt_sl = None; gpt_note = str(gpt)
        except Exception as e:
            gpt = f"ChatGPT exception: {e}"
            gpt_ok = None; gpt_tp = None; gpt_sl = None; gpt_note = str(e)

        # Consolidate: Always include bot TP/SL; include DeepSeek/GPT where available
        final = {
            "Ticker": t,
            "Bot": {"score": bot["score"], "action": bot["action"], "tp_pct": bot["tp_pct"], "sl_pct": bot["sl_pct"]},
            "DeepSeek": {"raw": ds, "score": ds_score, "action": ds_action, "tp": ds_tp, "sl": ds_sl},
            "GPT": {"raw": gpt, "ok": gpt_ok, "tp": gpt_tp, "sl": gpt_sl, "note": gpt_note},
            "Headlines": headlines_flat[:20]  # limit saving
        }
        final_signals.append(final)

    # 4) Save signals csv (bot baseline + deepseek/gpt presence)
    signals_out = []
    for f in final_signals:
        row = {
            "Ticker": f["Ticker"],
            "BotScore": f["Bot"]["score"],
            "BotAction": f["Bot"]["action"],
            "Bot_TP_pct": f["Bot"]["tp_pct"],
            "Bot_SL_pct": f["Bot"]["sl_pct"],
            "DeepSeek_raw": json.dumps(f["DeepSeek"]["raw"]) if f["DeepSeek"]["raw"] else "",
            "GPT_raw": json.dumps(f["GPT"]["raw"]) if f["GPT"]["raw"] else ""
        }
        signals_out.append(row)
    signals_df = pd.DataFrame(signals_out)
    signals_file = f"signals/trading_signals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    signals_df.to_csv(signals_file, index=False)

    # 5) Build clean Telegram message
    lines = []
    lines.append(f"📊 Jackpot Bot run at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
    # Order: STRONG BUY -> STRONG SELL -> BUY -> SELL -> HOLD (user requested order)
    order_priority = {"STRONG BUY": 0, "BUY": 1, "SELL": 3, "STRONG SELL": 2, "HOLD": 4}
    # sort by bot score descending primarily, then action priority
    final_signals_sorted = sorted(final_signals, key=lambda x: ( -x["Bot"]["score"], order_priority.get(x["Bot"]["action"], 5) ))

    for f in final_signals_sorted:
        t = f["Ticker"]
        bot = f["Bot"]
        ds = f["DeepSeek"]
        gpt = f["GPT"]

        # Icon mapping (visual differentiation)
        icon = "⏸️"
        if bot["action"] == "STRONG BUY":
            icon = "💎"
        elif bot["action"] == "BUY":
            icon = "✅"
        elif bot["action"] == "SELL":
            icon = "⚠️"
        elif bot["action"] == "STRONG SELL":
            icon = "💀"

        lines.append(f"{icon} {t}: {bot['action']} (bot score {bot['score']})")
        # Bot suggested TP/SL (always present)
        lines.append(f"   🛠 Bot (fallback) → TP: {bot['tp_pct']}% | SL: {bot['sl_pct']}%")

        # DeepSeek info (if available)
        if isinstance(ds["raw"], dict):
            ds_score = ds.get("score")
            ds_action = ds.get("action") or ds.get("raw", {}).get("recommendation")
            ds_tp = ds.get("tp") or ds.get("raw", {}).get("take_profit")
            ds_sl = ds.get("sl") or ds.get("raw", {}).get("stop_loss")
            lines.append(f"   🔍 DeepSeek → score: {ds_score} action: {ds_action} TP: {ds_tp}% SL: {ds_sl}%")
        else:
            lines.append(f"   🔍 DeepSeek → {ds['raw']}")

        # ChatGPT info (if available)
        if isinstance(gpt["raw"], dict):
            lines.append(f"   🤖 GPT → ok: {gpt.get('ok')} TP: {gpt.get('tp')}% SL: {gpt.get('sl')}% — {gpt.get('note')}")
        else:
            lines.append(f"   🤖 GPT → {gpt['raw']}")

        # Headlines (one-liners — keep short)
        headlines = f.get("Headlines", [])[:6]
        for h in headlines:
            snippet = (h[:140] + "...") if len(h) > 140 else h
            lines.append(f"   📰 {snippet}")
        lines.append("")  # blank separator

    # Footer with file paths
    lines.append(f"📂 Signals saved: {signals_file}")
    lines.append(f"📂 News saved: {news_file}")

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
