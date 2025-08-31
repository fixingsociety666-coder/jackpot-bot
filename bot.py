import pandas as pd
import random
import os

# Read portfolio CSV
df = pd.read_csv("sample_portfolio.csv")

# Directory for signals
os.makedirs("signals", exist_ok=True)

signals = []

# Simulate analysis: assign a score to each ticker
for idx, row in df.iterrows():
    score = round(random.uniform(0, 1), 2)
    if score >= 0.8:  # only very strong buy
        signals.append({
            "Ticker": row["Ticker"],
            "Company": row["Company"],
            "Type": row["Type"],
            "Score": score,
            "Signal": "Strong Buy"
        })

# Save signals
signals_df = pd.DataFrame(signals)
signals_df.to_csv("signals/signals.csv", index=False)

print(f"✅ Generated {len(signals)} strong buy signals")

