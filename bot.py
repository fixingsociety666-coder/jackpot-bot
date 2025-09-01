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
# News fetchers (APIs, RSS, scraping)
# Each returns a list of short strings (headlines/snippets) or an error string list
# (kept as in original)
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
    """
    Returns list where first item is "Price: <value>" when available.
    """
    try:
        url = "https://query1.finance.yahoo.com/v7/finance/quote"
        params = {"symbols": ticker}
        j = safe_request_json(url, params=params)
        q = j.get("quoteResponse", {}).get("result", [{}])[0]
        snippets = []
        if q:
            price = q.get("regularMarketPrice")
            snippets.append(f"Price: {price}")
            if q.get("longName"):
                snippets.append(q.get("longName"))
        # minimal headlines (not used in Telegram)
        try:
            page = safe_request_text(f"https://finance.yahoo.com/quote/{ticker}")
            soup = BeautifulSoup(page, "html.parser")
            headlines = [a.get_text(strip=True) for a in soup.select("h3 a")] or []
            if headlines:
                snippets.extend(headlines[:3])
        except Exception:
            pass
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
# - returns a dict (if parseable) with keys: action_ok, trailing_pct, offset_pct, note
# ---------------------------
def chatgpt_sanity(signals_for_ticker, headlines):
    if not OPENAI_API_KEY:
        return "ChatGPT skipped (OPENAI_API_KEY not set)"
    try:
        # Request trailing% and offset% instead of TP/SL
        prompt = (
            "You are a sober financial assistant. For the ticker below, given headlines and price context, "
            "answer in JSON with keys: action_ok(bool), trailing_pct(number), offset_pct(number), note(str).\n\n"
            f"Ticker data: {json.dumps(signals_for_ticker)}\n\nHeadlines: {json.dumps(headlines[:12])}\n\n"
            "Return only a single JSON object."
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
# Bot fallback scoring (always runs) -> now returns trailing_pct and offset_pct
# ---------------------------
def bot_fallback_score_and_trailing_offset(headlines):
    """
    Always-run fallback algorithm:
    - simple keyword sentiment across headlines
    - base score in [0,1]
    - map to action, produce bot trailing% (aggressive) and offset% (conservative)
    """
    text = " ".join([str(h).lower() for h in headlines])
    if not text.strip():
        score = 0.5
    else:
        buy_keywords = ["upgrade", "buy", "strong buy", "outperform", "beats", "beat", "surge", "gain", "record"]
        sell_keywords = ["downgrade", "sell", "strong sell", "miss", "misses", "loss", "fall", "decline", "bearish"]
        buy_hits = sum(text.count(k) for k in buy_keywords)
        sell_hits = sum(text.count(k) for k in sell_keywords)
        total = buy_hits + sell_hits
        if total == 0:
            score = 0.5
        else:
            score = float(buy_hits) / float(total)
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

    # Bot-suggested trailing% and offset% logic
    # trailing_pct: larger for stronger conviction; offset_pct: smaller for stronger conviction
    trailing_pct = round(2.0 + score * 18.0, 2)   # maps score 0->2% to 1->20%-ish
    offset_pct = round(max(0.5, (1.2 - score) * 6.0), 2)  # maps inverse to score
    return {"score": score, "action": action, "trailing_pct": trailing_pct, "offset_pct": offset_pct}

# ---------------------------
# DeepSeek integration (optional, may fail)
# We'll use a chat-completions style HTTP call to DeepSeek if DEEPSEEK_API_KEY is present.
# Request JSON with trailing_pct and offset_pct keys.
# ---------------------------
def call_deepseek(ticker, headlines):
    if not DEEPSEEK_API_KEY:
        return "DeepSeek skipped (no API key)"
    try:
        # Compose prompt asking for trailing_pct and offset_pct as JSON
        prompt = (
            "You are DeepSeek-like financial assistant. Given the ticker and headlines, "
            "return a single JSON object with keys: recommendation (STRONG BUY/STRONG SELL/BUY/SELL/HOLD), "
            "score (0-1), trailing_pct (number), offset_pct (number), note (string).\n\n"
            f"Ticker: {ticker}\nHeadlines: {json.dumps(headlines[:20])}\n\nReturn only JSON."
        )
        # Many DeepSeek integrations are OpenAI-compatible: try POST to deepseek chat completions endpoint
        url = "https://api.deepseek.com/v1/chat/completions"
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "You are DeepSeek financial assistant."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.0,
            "max_tokens": 300
        }
        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        r = requests.post(url, json=payload, headers=headers, timeout=25)
        r.raise_for_status()
        out = r.json()
        # find content
        content = out.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            # some providers return top-level text
            content = out.get("choices", [{}])[0].get("text", "")
        # parse JSON
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1:
            data = json.loads(content[start:end+1])
            return data
        # otherwise return raw content
        return content
    except Exception as e:
        return f"DeepSeek error: {e}"

# ---------------------------
# Get live price helper (Yahoo)
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

    # 1) Generate initial signals list
    signals_list = [{"Ticker": t} for t in tickers]

    # 2) Parallel news fetching
    news_store = {}
    with ThreadPoolExecutor(max_workers=12) as executor:
        for t, snippets in executor.map(fetch_news_for_ticker, tickers):
            news_store[t] = snippets

    # save news snapshot (kept for debugging/history)
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

        # ALWAYS compute bot fallback (trailing/offset)
        bot = bot_fallback_score_and_trailing_offset(headlines_flat)

        # get live price
        price = get_live_price_yahoo(t)

        # try DeepSeek
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

        # try ChatGPT sanity
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
            "Bot": {"score": bot["score"], "action": bot["action"], "trailing_pct": bot["trailing_pct"], "offset_pct": bot["offset_pct"]},
            "DeepSeek": {"raw": ds, "score": ds_score, "action": ds_action, "trailing_pct": ds_trailing, "offset_pct": ds_offset},
            "GPT": {"raw": gpt, "ok": gpt_ok, "trailing_pct": gpt_trailing, "offset_pct": gpt_offset, "note": gpt_note},
            "Headlines": headlines_flat[:20]
        }
        final_signals.append(final)

    # 4) Save signals csv (bot baseline + deepseek/gpt presence)
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

    # 5) Build clean Telegram message
    lines = []
    lines.append(f"📊 Jackpot Bot run at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n")

    # Only show STRONG BUY and STRONG SELL
    final_signals_filtered = [f for f in final_signals if f["Bot"]["action"] in ["STRONG BUY", "STRONG SELL"]]

    # Order: STRONG BUY first, then STRONG SELL
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

            # Bot fallback suggestions (always present)
            lines.append(f"   🛠 Bot → Trailing: {bot['trailing_pct']}% | Offset: {bot['offset_pct']}%")

            # DeepSeek suggestions
            if isinstance(ds["raw"], dict):
                ds_tr = ds.get("trailing_pct")
                ds_off = ds.get("offset_pct")
                lines.append(f"   🔍 DeepSeek → rec: {ds.get('action')} | trailing: {ds_tr}% | offset: {ds_off}%")
            else:
                # ds['raw'] might be error string
                lines.append(f"   🔍 DeepSeek → {ds['raw']}")

            # ChatGPT suggestions
            if isinstance(gpt["raw"], dict):
                g_tr = gpt.get("trailing_pct")
                g_off = gpt.get("offset_pct")
                lines.append(f"   🤖 GPT → ok: {gpt.get('ok')} | trailing: {g_tr}% | offset: {g_off}% — {gpt.get('note')}")
            else:
                lines.append(f"   🤖 GPT → {gpt['raw']}")

            lines.append("")  # separator

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

