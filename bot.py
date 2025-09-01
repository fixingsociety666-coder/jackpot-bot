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
# News fetchers
# (All existing news fetcher functions remain intact)
# ---------------------------
# ... [Keep all existing fetch_from_* functions unchanged] ...

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
# Technical analysis helpers
# ---------------------------
def fetch_historical_prices(ticker, days=100):
    """
    Returns a pandas Series of closing prices for the past 'days'.
    Tries MarketWatch → Google → Yahoo fallback.
    """
    import yfinance as yf
    try:
        df = yf.download(ticker, period=f"{days}d", interval="1d")
        if not df.empty:
            return df["Close"]
    except Exception as e:
        print(f"DEBUG: Yahoo historical failed {ticker}: {e}")
    return pd.Series()

def compute_technical_score(prices):
    """
    Simple technical score based on RSI & SMA trend.
    Returns 0.0 (very bearish) → 1.0 (very bullish)
    """
    if prices.empty or len(prices) < 14:
        return 0.5
    delta = prices.diff().dropna()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / loss.replace(0, 0.0001)
    rsi = 100 - 100 / (1 + rs)
    rsi_score = 1.0 if rsi.iloc[-1] > 70 else 0.0 if rsi.iloc[-1] < 30 else 0.5
    sma_short = prices[-10:].mean()
    sma_long = prices[-50:].mean() if len(prices) >= 50 else prices.mean()
    trend_score = 1.0 if sma_short > sma_long else 0.0 if sma_short < sma_long else 0.5
    return 0.5 * rsi_score + 0.5 * trend_score

# ---------------------------
# Bot scoring (News + Technical)
# ---------------------------
def bot_combined_score(headlines, ticker):
    # News sentiment
    text = " ".join([str(h).lower() for h in headlines])
    if not text.strip(): news_score = 0.5
    else:
        buy_k=["upgrade","buy","strong buy","outperform","beats","beat","surge","gain","record"]
        sell_k=["downgrade","sell","strong sell","miss","misses","loss","fall","decline","bearish"]
        b=sum(text.count(k) for k in buy_k)
        s=sum(text.count(k) for k in sell_k)
        t=b+s
        news_score = 0.5 if t==0 else float(b)/float(t)
        news_score = max(0.0, min(1.0, round(0.85*news_score + 0.15*float(np.random.rand()),3)))

    # Technical analysis score
    prices = fetch_historical_prices(ticker)
    tech_score = compute_technical_score(prices)

    # Combined score (70% news, 30% technical)
    overall_score = 0.7*news_score + 0.3*tech_score

    # Determine action
    if overall_score >= 0.85: action="STRONG BUY"
    elif overall_score <= 0.15: action="STRONG SELL"
    else: action="HOLD"

    # Trailing & offset adjusted by technicals
    trailing_pct = round(2.0 + overall_score*18.0 + 5*(tech_score-0.5),2)
    offset_pct   = round(max(0.5,(1.2-overall_score)*6.0 - 3*(tech_score-0.5)),2)

    return {"score": round(overall_score,3), "action": action,
            "trailing_pct": trailing_pct, "offset_pct": offset_pct}

# ---------------------------
# Multi-source live price
# ---------------------------
def get_live_price_multi_source(ticker):
    ticker = ticker.strip().upper()
    # MarketWatch
    try:
        url = f"https://www.marketwatch.com/investing/stock/{ticker}"
        txt = safe_request_text(url)
        soup = BeautifulSoup(txt, "html.parser")
        price_tag = soup.select_one('bg-quote.value, h2.intraday__price span')
        if price_tag:
            price_str = price_tag.get_text(strip=True).replace(',','')
            return float(price_str), "MarketWatch"
    except Exception: pass
    # Yahoo
    try:
        import yfinance as yf
        price = yf.Ticker(ticker).info.get("regularMarketPrice")
        if price is not None:
            return float(price), "Yahoo"
    except Exception: pass
    # Google
    try:
        exchanges = ["NASDAQ", "NYSE", "OTC"]
        for ex in exchanges:
            url = f"https://www.google.com/finance/quote/{ticker}:{ex}"
            txt = safe_request_text(url)
            soup = BeautifulSoup(txt, "html.parser")
            price_tag = soup.select_one("div.YMlKec.fxKbKc")
            if price_tag:
                price_str = price_tag.get_text(strip=True).replace(',','').replace('$','')
                return float(price_str), f"Google Finance ({ex})"
    except Exception: pass
    return None, None

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

        bot = bot_combined_score(headlines_flat, t)
        price, price_source = get_live_price_multi_source(t)
        final_signals.append({"Ticker":t,"Price":price,"PriceSource":price_source,"Bot":bot,"Headlines":headlines_flat[:20]})

    # Build Telegram (EST time)
    from pytz import timezone
    est_now = datetime.now(timezone('US/Eastern'))
    lines=[f"📊 Jackpot Bot run at {est_now.strftime('%Y-%m-%d %H:%M:%S EST')}\n"]

    final_signals_filtered=[f for f in final_signals if f["Bot"]["action"] in ["STRONG BUY","STRONG SELL"]]
    order_priority={"STRONG BUY":0,"STRONG SELL":1}
    final_signals_sorted=sorted(final_signals_filtered,key=lambda x: order_priority.get(x["Bot"]["action"],99))

    if not final_signals_sorted:
        lines.append("No STRONG BUY or STRONG SELL signals this run.")
    else:
        for f in final_signals_sorted:
            t=f["Ticker"]
            bot=f["Bot"]
            price=f.get("Price")
            source=f.get("PriceSource")
            icon="🟢" if bot["action"]=="STRONG BUY" else "🔴"
            price_str=f"${price:.2f} ({source})" if isinstance(price,(int,float)) else "Price N/A"
            lines.append(f"{icon} {t} — {bot['action']} (bot score {bot['score']}) — {price_str}")
            lines.append(f"   🛠 Bot → Trailing: {bot['trailing_pct']}% | Offset: {bot['offset_pct']}%")
            lines.append("")

    send_telegram("\n".join(lines))
    print("✅ Run complete. Telegram sent (if configured).")
    print(f"News -> {news_file}")

if __name__=="__main__":
    try: main()
    except Exception:
        tb=traceback.format_exc()
        print(tb)
        send_telegram(f"🚨 Bot crashed:\n{tb}")
