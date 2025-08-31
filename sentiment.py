from nltk.sentiment.vader import SentimentIntensityAnalyzer
import nltk
nltk.download("vader_lexicon", quiet=True)
analyzer = SentimentIntensityAnalyzer()

def analyze_sentiment(text):
    score = analyzer.polarity_scores(text)["compound"]
    if score > 0.3: return "Bullish", score
    elif score < -0.3: return "Bearish", score
    else: return "Neutral", score
