# portfolio.py
import requests
import os

QUESTRADE_CLIENT_ID = os.getenv("QUESTRADE_CLIENT_ID")
QUESTRADE_REFRESH_TOKEN = os.getenv("QUESTRADE_REFRESH_TOKEN")

def get_questrade_access_token():
    url = f"https://login.questrade.com/oauth2/token?grant_type=refresh_token&refresh_token={QUESTRADE_REFRESH_TOKEN}&client_id={QUESTRADE_CLIENT_ID}"
    resp = requests.post(url).json()
    return resp.get("access_token")

def get_questrade_portfolio():
    access_token = get_questrade_access_token()
    if not access_token:
        return []
    headers = {"Authorization": f"Bearer {access_token}"}
    accounts = requests.get("https://api.questrade.com/v1/accounts", headers=headers).json().get("accounts", [])
    tickers = []
    for acct in accounts:
        acct_id = acct["number"]
        positions = requests.get(f"https://api.questrade.com/v1/accounts/{acct_id}/positions", headers=headers).json().get("positions", [])
        for pos in positions:
            if pos["openQuantity"] > 0:
                tickers.append(pos["symbol"])
    return tickers
