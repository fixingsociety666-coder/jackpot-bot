import openai
import os

# Get API key from environment variable (set in GitHub secrets)
openai.api_key = os.environ["OPENAI_API_KEY"]

prompt = """
Generate a CSV with columns: Ticker, Company, Type.
Include:
- Top 100 penny stocks over the past 2 years
- Top 50 consistent performers over the past 5 years
- Top 10 cryptocurrencies
Return CSV only, no extra text.
"""

response = openai.ChatCompletion.create(
    model="gpt-5-mini",
    messages=[{"role": "user", "content": prompt}],
    temperature=0.2
)

csv_text = response.choices[0].message.content

# Save CSV
with open("sample_portfolio.csv", "w") as f:
    f.write(csv_text)

print("CSV automatically generated via ChatGPT API")

