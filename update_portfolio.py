import pandas as pd
import requests
from bs4 import BeautifulSoup
import time

CSV_FILE = "sample_portfolio.csv"
NUM_PENNY = 100
NUM_CONSISTENT = 50

CRYPTOS = [
    {"Ticker":"BTC","Company":"Bitcoin","Type":"Crypto"},
    {"Ticker":"ETH","Company":"Ethereum","Type":"Crypto"},
    {"Ticker":"BNB","Company":"Binance Coin","Type":"Crypto"},
    {"Ticker":"SOL","Company":"Solana","Type":"Crypto"},
    {"Ticker":"ADA","Company":"Cardano","Type":"Crypto"}
]

def fetch_penny_stocks():
    penny_stocks = []
    url = "https://finance.yahoo.com/screener/predefined/most_actives?count=100&offset=0"
    try:
        r = requests.get(url)
        soup = BeautifulSoup(r.text, 'html.parser')
        table = soup.find_all('tr')
        for row in table[1:NUM_PENNY+1]:
            cols = row.find_all('td')
            if len(cols) >= 2:
                ticker = cols[0].text.strip()
                company = cols[1].text.strip()
                penny_stocks.append({"Ticker": ticker, "Company": company, "Type":"Penny"})
            if len(penny_stocks) >= NUM_PENNY:
                break
    except Exception as e:
        print(f"Penny stock fetch error: {e}")
    return penny_stocks

def fetch_consistent_stocks():
    consistent = []
    url = "https://finance.yahoo.com/gainers"
    try:
        r = requests.get(url)
        soup = BeautifulSoup(r.text, 'html.parser')
        table = soup.find_all('tr')
        for row in table[1:NUM_CONSISTENT+1]:
            cols = row.find_all('td')
            if len(cols) >= 2:
                ticker = cols[0].text.strip()
                company = cols[1].text.strip()
                consistent.append({"Ticker": ticker, "Company": company, "Type":"Stock"})
            if len(consistent) >= NUM_CONSISTENT:
                break
    except Exception as e:
        print(f"Consistent stock fetch error: {e}")
    return consistent

all_tickers = []

print("Fetching top penny stocks...")
penny_list = fetch_penny_stocks()
all_tickers.extend(penny_list)
time.sleep(2)

print("Fetching top consistent performers...")
consistent_list = fetch_consistent_stocks()
all_tickers.extend(consistent_list)

print("Adding cryptocurrencies...")
all_tickers.extend(CRYPTOS)

df = pd.DataFrame(all_tickers)
df.to_csv(CSV_FILE, index=False)
print(f"CSV saved: {CSV_FILE}")
