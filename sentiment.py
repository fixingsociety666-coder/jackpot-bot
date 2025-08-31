# sentiment.py
def sentiment_score(title):
    score = 0
    buy_kw = {"upgrade":0.3, "breakout":0.4, "rally":0.3, "strong buy":0.6, "surge":0.5}
    sell_kw = {"downgrade":0.3, "sell":0.3, "drop":0.4, "decline":0.3}
    t = title.lower()
    for w,v in buy_kw.items():
        if w in t: score += v
    for w,v in sell_kw.items():
        if w in t: score -= v
    return score

def calculate_tp_sl(price, score):
    if price == 0:
        return 0,0
    if score > 0: tp, sl = price*1.05, price*0.98
    elif score < 0: tp, sl = price*0.98, price*1.05
    else: tp = sl = price
    return round(tp,2), round(sl,2)
