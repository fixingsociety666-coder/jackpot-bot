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
        headlines = [h.text.strip() for h in soup.select("a.news-headline, .article__headline")][:5]
        return headlines or ["No Barchart headlines (scrape)"]
    except Exception as e:
        return [f"Barchart scrape error: {e}"]

def fetch_from_polygon(ticker):
    if not POLYGON_API_KEY:
        return ["Polygon not configured"]
    try:
        url = f"https://api.polygon.io/v2/reference/news"
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
        url = f"https://finnhub.io/api/v1/company-news"
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
            "https://seekingalpha.com/market-news.xml",
            "https://seekingalpha.com/author/feeds"
        ]
        for feed in candidate_feeds:
            try:
                f = feedparser.parse(feed)
                if f and f.entries:
                    return [entry.get("title", "") for entry in f.entries[:6]]
            except Exception:
                continue
        return ["No SeekingAlpha RSS found"]
    except Exception as e:
        return [f"SeekingAlpha error: {e}"]

def fetch_from_motleyfool_rss():
    try:
        feed = feedparser.parse("https://www.fool.com/feeds/all.xml")
        if feed and feed.entries:
            return [e.get("title", "") for e in feed.entries[:6]]
        return ["No Motley Fool RSS"]
    except Exception as e:
        return [f"MotleyFool error: {e}"]

def fetch_from_tipranks_via_apify():
    if not APIFY_API_TOKEN:
        return ["TipRanks (Apify) not configured"]
    try:
        api_url = f"https://api.apify.com/v2/acts/scraped~analysts-top-rated-stocks-tipranks/runs"
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
        if feed and feed.entries:
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
            snippets.append(f"Quote: {q.get('regularMarketPrice')}")
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
    for rec in signals_list:
        t = rec['Ticker']
        action = rec['Action']
        score = rec['Score']

        # Visual differentiation
        if action == "STRONG BUY":
            lines.append(f"🔥➡️ {t}: {action} (score {score}) — HIGH ALERT")
        elif action == "BUY":
            lines.append(f"✅➡️ {t}: {action} (score {score})")
        elif action == "STRONG SELL":
            lines.append(f"💀➡️ {t}: {action} (score {score}) — DANGER")
        elif action == "SELL":
            lines.append(f"⚠️➡️ {t}: {action} (score {score})")
        else:  # HOLD
            lines.append(f"⏸️➡️ {t}: {action} (score {score})")

        # Headlines
        snippets = news_store.get(t, {})
        for src in ["Polygon","Barchart","Finnhub","Yahoo","MotleyFool","SeekingAlpha","MarketWatch","Barrons","TipRanks","CNBC","AlphaVantage"]:
            if src in snippets:
                s = snippets[src]
                if isinstance(s, list):
                    excerpt = s[0] if s else "no headlines"
                elif isinstance(s, dict):
                    v = next(iter(s.values()), "no headlines")
                    excerpt = (v[:120] if isinstance(v, str) else str(v))
                else:
                    excerpt = str(s)[:120]
                lines.append(f"   📰 {src}: {excerpt}")

        # GPT sanity
        if t in sanity_results:
            fr = sanity_results[t]
            if isinstance(fr, dict):
                lines.append(f"   🤖 GPT: ok={fr.get('action_ok')}, tp={fr.get('tp_pct')}%, sl={fr.get('sl_pct')}% — {fr.get('note')}")
            else:
                lines.append(f"   🤖 GPT: {fr}")
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
