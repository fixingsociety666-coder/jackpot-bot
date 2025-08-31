import pandas as pd
import yfinance as yf
import os

# Penny stocks + top performers
penny_symbols = ["GME","AMC","BB","NOK","SNDL"]  # replace with actual top performers
top_symbols = ["AAPL","TSLA","MSFT","NVDA","AMZN"]
all_symbols = penny_symbols + top_symbols

portfolio_data = []

for symbol in all_symbols:
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        price = info.get("regularMarketPrice",0)
        stock_type = "Penny Stock" if price < 5 else "Stock"
        portfolio_data.append({
            "Ticker": symbol,
            "Company": info.get("shortName",""),
            "Type": stock_type
        })
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")

os.makedirs("data", exist_ok=True)
df = pd.DataFrame(portfolio_data)
df.to_csv("data/auto_portfolio.csv", index=False)
print(f"✅ Auto portfolio updated with {len(df)} tickers")
