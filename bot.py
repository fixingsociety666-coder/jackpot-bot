# bot.py
import os
import json
import traceback
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

import requests
import pandas as pd
import numpy as np
from bs4 import BeautifulSoup
import feedparser
import yfinance as yf
from sklearn.linear_model import LinearRegression  # Added for forecast

# ---------------------------
# Config / Environment names
# ---------------------------
TICKER_CSV = "tickers.csv"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
BARCHART_API_KEY = os.getenv("BARCHART_API_KEY")
POLYGON_API_KEY  = os.getenv("POLYGON_API_KEY")
FINNHUB_API_KEY  = os.getenv("FINNHUB_API_KEY")
ALPHAVANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY")
APIFY_API_TOKEN  = os.getenv("APIFY_API_TOKEN")
MAX_TICKERS_PER_RUN = None
TELEGRAM_MAX = 3900

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
            if price > last_price * 1.01:
                icons.append("🟢")
            elif price < last_price * 0.99:
                icons.append("🔴")
            else:
                icons.append("⚪")
            last_price = price
        
        return [{"day": i+1, "forecast": round(forecast_prices[i],2), "icon": icons[i]} for i in range(days_ahead)]
    except Exception:
        return [{"day": i+1, "forecast": None, "icon": "⚪"} for i in range(days_ahead)]

# ---------------------------
# News fetchers
# ---------------------------
def fetch_from_yahoo_per_ticker(ticker):
    try:
        url = "https://query1.finance.yahoo.com/v7/finance/quote"
        params = {"symbols": ticker}
        j = safe_request_json(url, params=params)
        q = j.get("quoteResponse", {}).get("result", [{}])[0]
        snippets = []
        price = q.get("regularMarketPrice")
        if price is not None:
            snippets.append(f"Price: {price}")
        if q.get("longName"):
            snippets.append(q.get("longName"))
        try:
            page = safe_request_text(f"https://finance.yahoo.com/quote/{ticker}")
            soup = BeautifulSoup(page, "html.parser")
            headlines = [a.get_text(strip=True) for a in soup.select("h3 a")][:3]
            snippets.extend(headlines)
        except Exception:
            pass
        return snippets or ["No Yahoo data"]
    except Exception as e:
        return [f"Yahoo error: {e}"]

def fetch_from_barchart(ticker):
    if BARCHART_API_KEY:
        try:
            url = "https://marketdata.websol.barchart.com/getNews.json"
            params = {"apikey": BARCHART_API_KEY, "symbols": ticker}
            j = safe_request_json(url, params=params)
            return [it.get("headline") or str(it) for it in j.get("news", [])[:5]] or ["No Barchart news"]
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
        return [it.get("title") or it.get("summary") for it in j.get("results", [])][:3] or ["No Polygon news"]
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
        return [it.get("headline") or str(it) for it in j][:3] or ["No Finnhub news"]
    except Exception as e:
        return [f"Finnhub error: {e}"]

def fetch_from_alpha_vantage(ticker):
    if not ALPHAVANTAGE_KEY:
        return ["AlphaVantage not configured"]
    try:
        url = "https://www.alphavantage.co/query"
        params = {"function": "NEWS_SENTIMENT", "tickers": ticker, "apikey": ALPHAVANTAGE_KEY}
        j = safe_request_json(url, params=params)
        return [it.get("title") if isinstance(it, dict) and it.get("title") else str(it) for it in j.get("feed", [])[:3]] or ["No AlphaVantage news"]
    except Exception as e:
        return [f"AlphaVantage error: {e}"]

def fetch_from_marketwatch(ticker):
    try:
        url = f"https://www.marketwatch.com/investing/stock/{ticker}"
        txt = safe_request_text(url)
        soup = BeautifulSoup(txt, "html.parser")
        headlines = [el.get_text(strip=True) for el in soup.select("div.article__content a")] or [el.get_text(strip=True) for el in soup.select("h3 a")]
        return headlines[:4] if headlines else ["No MarketWatch headlines"]
    except Exception as e:
        return [f"MarketWatch error: {e}"]

def fetch_from_seekingalpha_rss():
    try:
        candidate_feeds = ["https://seekingalpha.com/market-news.rss","https://seekingalpha.com/feed.xml","https://seekingalpha.com/market-news.xml"]
        for feed in candidate_feeds:
            f = feedparser.parse(feed)
            if f and getattr(f, "entries", None):
                return [entry.get("title", "") for entry in f.entries[:6]]
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

def fetch_from_barrons_rss():
    try:
        feed = feedparser.parse("https://www.barrons.com/rss")
        if feed and getattr(feed, "entries", None):
            return [e.get("title","") for e in feed.entries[:6]]
        return ["No Barron's RSS (try other source)"]
    except Exception as e:
        return [f"Barrons error: {e}"]

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
            return [item.get("title") or item.get("ticker") or str(item) for item in d][:6] or ["No TipRanks results from Apify"]
        return ["TipRanks Apify run started but no dataset id"]
    except Exception as e:
        return [f"TipRanks/Apify error: {e}"]

# ---------------------------
# Parallel news fetching helper
# ---------------------------
def fetch_news_for_ticker(ticker):
    snippets = {}
    try: snippets["Yahoo"] = fetch_from_yahoo_per_ticker(ticker)
    except Exception as e: snippets["Yahoo"] = [f"Yahoo error wrapper: {e}"]
    snippets["Barchart"] = fetch_from_barchart(ticker)
    snippets["Polygon"] = fetch_from_polygon(ticker)
    snippets["Finnhub"] = fetch_from_finnhub(ticker)
    snippets["AlphaVantage"] = fetch_from_alpha_vantage(ticker)
    snippets["MarketWatch"] = fetch_from_marketwatch(ticker)
    try:
        url = f"https://www.cnbc.com/quotes/{ticker}"
        txt = safe_request_text(url)
        soup = BeautifulSoup(txt, "html.parser")
        cnbc_head = [a.get_text(strip=True) for a in soup.select("a.Card-title")][:3] or []
        snippets["CNBC"] = cnbc_head or ["No CNBC headlines"]
    except Exception as e: snippets["CNBC"] = [f"CNBC error: {e}"]
    try: snippets["SeekingAlpha"] = fetch_from_seekingalpha_rss()
    except Exception as e: snippets["SeekingAlpha"] = [f"SeekingAlpha wrapper error: {e}"]
    snippets["MotleyFool"] = fetch_from_motleyfool_rss()
    snippets["Barrons"] = fetch_from_barrons_rss()
    snippets["TipRanks"] = fetch_from_tipranks_via_apify()
    return ticker, snippets

# ---------------------------
# Bot scoring: news + technical analysis
# ---------------------------
def bot_score_with_tech(headlines, ticker):
    text = " ".join([str(h).lower() for h in headlines])
    if not text.strip(): score = 0.5
    else:
        buy_k=["upgrade","buy","strong buy","outperform","beats","beat","surge","gain","record"]
        sell_k=["downgrade","sell","strong sell","miss","misses","loss","fall","decline","bearish"]
        b=sum(text.count(k) for k in buy_k)
        s=sum(text.count(k) for k in sell_k)
        t=b+s
        score=0.5 if t==0 else float(b)/float(t)
        score = max(0.0, min(1.0, round(0.75*score + 0.25*float(np.random.rand()),3)))
    # Add technical analysis contribution
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
        if price_tag:
            return float(price_tag.get_text(strip=True).replace(',','')), "MarketWatch"
    except: pass
    try:
        url="https://query1.finance.yahoo.com/v7/finance/quote"
        params={"symbols":ticker}
        j=safe_request_json(url,params=params)
        q=j.get("quoteResponse",{}).get("result",[{}])[0]
        price=q.get("regularMarketPrice")
        if price is not None: return float(price), "Yahoo"
    except: pass
    try:
        for ex in ["NASDAQ","NYSE","OTC"]:
            url = f"https://www.google.com/finance/quote/{ticker}:{ex}"
            txt = safe_request_text(url)
            soup = BeautifulSoup(txt, "html.parser")
            price_tag = soup.select_one("div.YMlKec.fxKbKc")
            if price_tag:
                return float(price_tag.get_text(strip=True).replace(',','').replace('$','')), f"Google Finance ({ex})"
    except: pass
    return None,None

# ---------------------------
# Main
# ---------------------------
def main():
    try:
        df = pd.read_csv(TICKER_CSV)
    except Exception as e:
        send_telegram(f"🚨 ERROR reading {TICKER_CSV}: {e}")
        return

    tickers=list(df["Ticker"].dropna().astype(str).unique())
    if MAX_TICKERS_PER_RUN: tickers=tickers[:MAX_TICKERS_PER_RUN]

    os.makedirs("signals",exist_ok=True)
    os.makedirs("news",exist_ok=True)

    signals_list=[{"Ticker":t} for t in tickers]

    news_store={}
    with ThreadPoolExecutor(max_workers=12) as executor:
        for t,snippets in executor.map(fetch_news_for_ticker,tickers):
            news_store[t]=snippets

    news_file=f"news/latest_news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(news_file,"w") as f: json.dump(news_store,f,indent=2)

    final_signals=[]
    for rec in signals_list:
        t=rec["Ticker"]
        snippets=news_store.get(t,{})
        headlines_flat=[]
        for src,arr in snippets.items():
            if isinstance(arr,list): headlines_flat.extend([str(x) for x in arr[:6]])
            elif isinstance(arr,dict): headlines_flat.extend([str(v) for v in list(arr.values())[:6]])
            else: headlines_flat.append(str(arr))
        bot=bot_score_with_tech(headlines_flat,t)
        price, price_source = get_live_price_multi_source(t)
        final_signals.append({"Ticker":t,"Price":price,"PriceSource":price_source,"Bot":bot,"Headlines":headlines_flat[:20]})

    est_now = datetime.utcnow() - timedelta(hours=4)
    lines=[f"📊 Jackpot Bot run at {est_now.strftime('%Y-%m-%d %H:%M:%S EST')}\n"]
    final_signals_filtered=[f for f in final_signals if f["Bot"]["action"] in ["STRONG BUY","STRONG SELL"]]
    final_signals_sorted=sorted(final_signals_filtered,key=lambda x:x["Bot"]["score"],reverse=True)

    if not final_signals_sorted:
        lines.append("No STRONG BUY or STRONG SELL signals this run.")
    else:
        for f in final_signals_sorted:
            t=f["Ticker"]
            bot=f["Bot"]
            price=f.get("Price")
            source=f.get("PriceSource")
            icon = "💹" if bot["action"]=="STRONG BUY" else "📉"
            price_str=f"${price:.2f} ({source})" if isinstance(price,(int,float)) else "Price N/A"
            forecast=forecast_trend(t)
            forecast_str=" | ".join([f"{f['icon']}{f['forecast'] if f['forecast'] else 'N/A'}" for f in forecast])
            first = forecast[0]['forecast']
            last = forecast[-1]['forecast']
            if first is not None and last is not None:
                if last>first: overall_trend="📈 Uptrend"
                elif last<first: overall_trend="📉 Downtrend"
                else: overall_trend="➖ Neutral"
            else: overall_trend="➖ Neutral"
            lines.append(
                f"────────────\n"
                f"{icon} {t} | {bot['action']} | Score: {bot['score']*100:.1f}% | "
                f"Trailing: {bot['trailing_pct']}% | Offset: {bot['offset_pct']}% | {price_str}\n"
                f"Forecast: {forecast_str}\n"
                f"Trend: {overall_trend}"
            )

    text="\n".join(lines)
    send_telegram(text)
    print("✅ Bot run complete, Telegram sent.")

if __name__=="__main__":
    main()
