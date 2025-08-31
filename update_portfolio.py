import os
import pandas as pd
from openai import OpenAI

# Initialize OpenAI client
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# Prompt to generate portfolio CSV
prompt = """
Generate a CSV with columns: Ticker, Company, Type.
Include:
- Top 100 penny stocks over the past 2 years
- Top 50 consistent performers over the past 5 years
- Top 10 cryptocurrencies
Return CSV only, no extra text.
"""

# Call GPT-5 model via new OpenAI API
response = client.chat.completions.create(
    model="gpt-5-mini",
    messages=[{"role": "user", "content": prompt}],
    temperature=0.2
)

csv_text = response.choices[0].message.content

# Save CSV
with open("sample_portfolio.csv", "w") as f:
    f.write(csv_text)

print("✅ CSV automatically generated via ChatGPT API")


