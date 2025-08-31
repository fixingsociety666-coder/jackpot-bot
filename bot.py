import os, json, requests
import pandas as pd
from datetime import date
import yaml

with open("config.yml") as f:
    cfg = yaml.safe_load(f)

def send_telegram(msg):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id: return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id":chat_id,"text":msg,"parse_mode":"Markdown"})

signals = {}
for t in cfg["stock_universe"]:
    score = round(pd.np.random.rand(),2)
    color = "GREEN" if score>=cfg["signals"]["strong_buy"] else "YELLOW" if score>=cfg["signals"]["weak_buy"] else "RED"
    signals[t] = {"ticker":t,"close":100,"score":score,"color":color,"confidence":int(score*100),"market":"stocks","rationale":"Simulated signal."}

for c in cfg["crypto_universe"]:
    score = round(pd.np.random.rand(),2)
    color = "GREEN" if score>=cfg["signals"]["strong_buy"] else "YELLOW" if score>=cfg["signals"]["weak_buy"] else "RED"
    signals[c] = {"ticker":c,"close":1000,"score":score,"color":color,"confidence":int(score*100),"market":"crypto","rationale":"Simulated crypto signal."}

os.makedirs("signals", exist_ok=True)
today = str(date.today())
with open(f"signals/{today}.json","w") as f:
    json.dump(signals,f,indent=2)

for s in signals.values():
    if s["color"]=="GREEN":
        send_telegram(f"🚀 {s['ticker']} {s['market'].upper()} GREEN Signal ({s['confidence']}%)")
