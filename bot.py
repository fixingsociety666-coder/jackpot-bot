# bot.py
import os
import json
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

import requests
import pandas as pd
import numpy as np
from bs4 import BeautifulSoup
import feedparser
import yfinance as yf
from sklearn.linear_model import LinearRegression

# ---------------------------
# Config / Environment names
# ---------------------------
TICKER_CSV = "tickers.csv"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BARCHART_API_KEY = os.getenv("BARCHART_API_KEY")
POLYGON_API_KEY  = os.getenv("POLYGON_API_KEY")
FINNHUB_API_KEY  = os.getenv("FINNHUB_API_KEY")
ALPHAVANTAGE_KEY = os.getenv("ALPHAVANTAGE_KEY")
APIFY_API_TOKEN  = os.getenv("APIFY_API_TOKEN")
MAX_TICKERS_PER_RUN = None
TELEGRAM_MAX = 3900
MAX_WORKERS = 12

# ---------------------------
# Utilities
# ---------------------------
def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured. Preview:\n", text[:4000])
        return
    chunks = []
    while text:
        if len(text) <= TELEGRAM_MAX:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, TELEGRAM_MAX)
        if split_at <= 0: split_at = TELEGRAM_MAX
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
# Forecast function
# ---------------------------
def forecast_trend(ticker, days_ahead=5):
    try:
        data = yf.Ticker(ticker).history(period="60d")['Close']
        if len(data) < 10:
            return [{"day": i+1, "forecast": None, "icon": "⚪"} for i in range(days_ahead)]
        X = np.arange(len(data)).reshape(-1, 1)
        y = data.values
        model = LinearRegression().fit(X, y)
        future_X = np.arange(len(data), len(data)+days_ahead).reshape(-1, 1)
        forecast_prices = model.predict(future_X)
        icons = []
        last_price = data.values[-1]
        for price in forecast_prices:
            if price > last_price * 1.01: icons.append("🟢")
            elif price < last_price * 0.99: icons.append("🔴")
            else: icons.append("⚪")
            last_price = price
        return [{"day": i+1, "forecast": round(forecast_prices[i],2), "icon": icons[i]} for i in range(days_ahead)]
    except Exception:
        return [{"day": i+1, "forecast": None, "icon": "⚪"} for i in range(days_ahead)]

# ---------------------------
# Bot scoring
# ---------------------------
def bot_score_with_tech(headlines, ticker):
    text = " ".join([str(h).lower() for h in headlines])
    if not text.strip(): score = 0.5
    else:
        buy_k = ["upgrade","buy","strong buy","outperform","beats","beat","surge","gain","record"]
        sell_k = ["downgrade","sell","strong sell","miss","misses","loss","fall","decline","bearish"]
        b = sum(text.count(k) for k in buy_k)
        s = sum(text.count(k) for k in sell_k)
        t = b+s
        score = 0.5 if t==0 else float(b)/float(t)
        score = max(0.0, min(1.0, round(0.75*score + 0.25*float(np.random.rand()),3)))
    try:
        data = yf.Ticker(ticker).history(period="20d")
        if len(data)>=5:
            close = data['Close']
            ma5 = close[-5:].mean()
            ma10 = close[-10:].mean()
            rsi = 100 - (100 / (1 + (close.diff().clip(lower=0).sum() / abs(close.diff().clip(upper=0)).sum())))
            if close.iloc[-1] > ma5 > ma10: score += 0.05
            if close.iloc[-1] < ma5 < ma10: score -= 0.05
            if rsi > 70: score -= 0.05
            if rsi < 30: score += 0.05
            score = max(0.0, min(1.0, score))
    except Exception:
        pass
    if score>=0.85: action="STRONG BUY"
    elif score<=0.15: action="STRONG SELL"
    else: action="HOLD"
    trailing_pct = round(2.0 + score*18.0,2)
    offset_pct = round(max(0.5,(1.2-score)*6.0),2)
    return {"score": score,"action": action,"trailing_pct": trailing_pct,"offset_pct": offset_pct}

# ---------------------------
# Multi-source live price
# ---------------------------
def get_live_price_multi_source(ticker):
    ticker = ticker.strip().upper()
    try:
        url = f"https://www.marketwatch.com/investing/stock/{ticker}"
        txt = safe_request_text(url)
        soup = BeautifulSoup(txt, "html.parser")
        price_tag = soup.select_one('bg-quote.value, h2.intraday__price span')
        if price_tag: return float(price_tag.get_text(strip=True).replace(',','')), "MarketWatch"
    except: pass
    try:
        url = "https://query1.finance.yahoo.com/v7/finance/quote"
        params = {"symbols":ticker}
        j = safe_request_json(url, params=params)
        q = j.get("quoteResponse",{}).get("result",[{}])[0]
        price = q.get("regularMarketPrice")
        if price is not None: return float(price), "Yahoo"
    except: pass
    try:
        for ex in ["NASDAQ","NYSE","OTC"]:
            url = f"https://www.google.com/finance/quote/{ticker}:{ex}"
            txt = safe_request_text(url)
            soup = BeautifulSoup(txt, "html.parser")
            price_tag = soup.select_one("div.YMlKec.fxKbKc")
            if price_tag: return float(price_tag.get_text(strip=True).replace(',','').replace('$','')), f"Google Finance ({ex})"
    except: pass
    return None, None

# ---------------------------
# Fetch news + price in one go
# ---------------------------
def fetch_news_and_price(ticker):
    snippets = {}
    ticker = ticker.upper()
    try:
        # Yahoo
        url = f"https://query1.finance.yahoo.com/v7/finance/quote"
        params = {"symbols": ticker}
        j = safe_request_json(url, params=params)
        q = j.get("quoteResponse", {}).get("result", [{}])[0]
        snippets["Yahoo"] = [q.get("longName") or "", f"Price: {q.get('regularMarketPrice')}" if q.get("regularMarketPrice") else ""]
    except: snippets["Yahoo"] = ["No Yahoo data"]

    # MarketWatch
    try:
        url = f"https://www.marketwatch.com/investing/stock/{ticker}"
        txt = safe_request_text(url)
        soup = BeautifulSoup(txt, "html.parser")
        headlines = [el.get_text(strip=True) for el in soup.select("div.article__content a")][:4]
        snippets["MarketWatch"] = headlines or ["No MarketWatch headlines"]
    except: snippets["MarketWatch"] = ["MarketWatch error"]

    # Google News
    try:
        url = f"https://news.google.com/rss/search?q={ticker}"
        feed = feedparser.parse(url)
        snippets["GoogleNews"] = [entry.get("title","") for entry in feed.entries[:5]] or ["No Google News"]
    except: snippets["GoogleNews"] = ["Google News error"]

    # Barchart
    try:
        if BARCHART_API_KEY:
            url = "https://marketdata.websol.barchart.com/getNews.json"
            params = {"apikey": BARCHART_API_KEY, "symbols": ticker}
            j = safe_request_json(url, params=params)
            snippets["Barchart"] = [it.get("headline") or str(it) for it in j.get("news", [])[:5]] or ["No Barchart news"]
        else: snippets["Barchart"] = ["Barchart not configured"]
    except: snippets["Barchart"] = ["Barchart error"]

    # Polygon
    try:
        if POLYGON_API_KEY:
            url = "https://api.polygon.io/v2/reference/news"
            params = {"ticker": ticker, "limit": 3, "apiKey": POLYGON_API_KEY}
            j = safe_request_json(url, params=params)
            snippets["Polygon"] = [it.get("title") or it.get("summary") for it in j.get("results", [])][:3] or ["No Polygon news"]
        else: snippets["Polygon"] = ["Polygon not configured"]
    except: snippets["Polygon"] = ["Polygon error"]

    # Finnhub
    try:
        if FINNHUB_API_KEY:
            today = datetime.utcnow().date()
            frm = (today.replace(year=today.year-1)).isoformat()
            to = today.isoformat()
            url = "https://finnhub.io/api/v1/company-news"
            params = {"symbol": ticker, "from": frm, "to": to, "token": FINNHUB_API_KEY}
            j = safe_request_json(url, params=params)
            snippets["Finnhub"] = [it.get("headline") for it in j][:3] or ["No Finnhub news"]
        else: snippets["Finnhub"] = ["Finnhub not configured"]
    except: snippets["Finnhub"] = ["Finnhub error"]

    # AlphaVantage
    try:
        if ALPHAVANTAGE_KEY:
            url = "https://www.alphavantage.co/query"
            params = {"function": "NEWS_SENTIMENT", "tickers": ticker, "apikey": ALPHAVANTAGE_KEY}
            j = safe_request_json(url, params=params)
            snippets["AlphaVantage"] = [it.get("title") for it in j.get("feed", [])[:3]] or ["No AlphaVantage news"]
        else: snippets["AlphaVantage"] = ["AlphaVantage not configured"]
    except: snippets["AlphaVantage"] = ["AlphaVantage error"]

    # CNBC
    try:
        url = f"https://www.cnbc.com/quotes/{ticker}"
        txt = safe_request_text(url)
        soup = BeautifulSoup(txt, "html.parser")
        snippets["CNBC"] = [a.get_text(strip=True) for a in soup.select("a.Card-title")][:3] or ["No CNBC headlines"]
    except: snippets["CNBC"] = ["CNBC error"]

    # SeekingAlpha RSS
    try:
        feeds = ["https://seekingalpha.com/market-news.rss","https://seekingalpha.com/feed.xml","https://seekingalpha.com/market-news.xml"]
        for feed_url in feeds:
            f = feedparser.parse(feed_url)
            if f and getattr(f, "entries", None):
                snippets["SeekingAlpha"] = [e.get("title","") for e in f.entries[:6]]
                break
        if "SeekingAlpha" not in snippets: snippets["SeekingAlpha"] = ["No SeekingAlpha RSS"]
    except: snippets["SeekingAlpha"] = ["SeekingAlpha error"]

    # MotleyFool RSS
    try:
        feed = feedparser.parse("https://www.fool.com/feeds/all.xml")
        snippets["MotleyFool"] = [e.get("title","") for e in feed.entries[:6]] if getattr(feed,"entries",None) else ["No Motley Fool RSS"]
    except: snippets["MotleyFool"] = ["MotleyFool error"]

    # Barrons RSS
    try:
        feed = feedparser.parse("https://www.barrons.com/rss")
        snippets["Barrons"] = [e.get("title","") for e in feed.entries[:6]] if getattr(feed,"entries",None) else ["No Barron's RSS"]
    except: snippets["Barrons"] = ["Barrons error"]

    # TipRanks via Apify
    try:
        if APIFY_API_TOKEN:
            url = "https://api.apify.com/v2/acts/scraped~analysts-top-rated-stocks-tipranks/runs"
            params = {"token": APIFY_API_TOKEN, "waitForFinish": "true"}
            r = requests.post(url, params=params, timeout=30)
            r.raise_for_status()
            run = r.json()
            dataset_url = run.get("defaultDatasetId") and f"https://api.apify.com/v2/datasets/{run['defaultDatasetId']}/items?token={APIFY_API_TOKEN}"
            if dataset_url:
                d = requests.get(dataset_url, timeout=20).json()
                snippets["TipRanks"] = [item.get("title") or item.get("ticker") for item in d][:6] or ["No TipRanks results"]
            else:
                snippets["TipRanks"] = ["TipRanks run started but no dataset"]
        else:
            snippets["TipRanks"] = ["TipRanks not configured"]
    except: snippets["TipRanks"] = ["TipRanks error"]

    # Flatten headlines
    headlines_flat = []
    for arr in snippets.values():
        if isinstance(arr,list): headlines_flat.extend([str(x) for x in arr if x])
    bot = bot_score_with_tech(headlines_flat, ticker)

    # Get live price
    price, source = get_live_price_multi_source(ticker)

    return {
        "Ticker": ticker,
        "Bot": bot,
        "Headlines": headlines_flat[:20],
        "Price": price,
        "PriceSource": source
    }

# ---------------------------
# Main
# ---------------------------
def main():
    try:
        df = pd.read_csv(TICKER_CSV)
    except Exception as e:
        send_telegram(f"🚨 ERROR reading {TICKER_CSV}: {e}")
        return

    tickers = list(df["Ticker"].dropna().astype(str).unique())
    if MAX_TICKERS_PER_RUN: tickers = tickers[:MAX_TICKERS_PER_RUN]

    os.makedirs("signals", exist_ok=True)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        results = list(executor.map(fetch_news_and_price, tickers))

    final_signals = [r for r in results if r["Bot"]["action"]=="STRONG BUY"]
    final_signals_sorted = sorted(final_signals, key=lambda x:x["Bot"]["score"], reverse=True)[:4]

    est_now = datetime.utcnow() - timedelta(hours=4)
    lines = [f"📊 Jackpot Bot Top STRONG BUY Alerts at {est_now.strftime('%Y-%m-%d %H:%M:%S EST')}\n"]

    if not final_signals_sorted:
        lines.append("No STRONG BUY signals today.")
    else:
        for f in final_signals_sorted:
            t = f["Ticker"]
            bot = f["Bot"]
            price = f.get("Price")
            source = f.get("PriceSource")
            price_str = f"${price:.2f} ({source})" if isinstance(price,(int,float)) else "Price N/A"
            forecast = forecast_trend(t)
            forecast_str = " | ".join([f"{f['icon']}{f['forecast'] if f['forecast'] else 'N/A'}" for f in forecast])
            first = forecast[0]['forecast']
            last = forecast[-1]['forecast']
            overall_trend = "📈 Uptrend" if first and last and last>first else "📉 Downtrend" if first and last and last<first else "➖ Neutral"
            lines.append(
                f"────────────\n"
                f"🟢 {t} | {bot['action']} | Score: {bot['score']*100:.1f}% | "
                f"Trailing: {bot['trailing_pct']}% | Offset: {bot['offset_pct']}% | {price_str}\n"
                f"Forecast: {forecast_str}\n"
                f"Trend: {overall_trend}"
            )

    text = "\n".join(lines)
    send_telegram(text)
    print("✅ Bot run complete, Telegram sent.")

if __name__=="__main__":
    main()
