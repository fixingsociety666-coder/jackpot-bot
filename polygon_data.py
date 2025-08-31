import requests
from config import POLYGON_API_KEY

def get_current_price(symbol):
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev?apiKey={POLYGON_API_KEY}"
    r = requests.get(url).json()
    if "results" in r:
        return r["results"][0]["c"]
    return None
