from textblob import TextBlob

def analyze_sentiment(text: str) -> float:
    """
    Analyze sentiment of a given text and return polarity score.
    Polarity ranges from -1 (negative) to +1 (positive).
    """
    try:
        blob = TextBlob(text)
        return round(blob.sentiment.polarity, 2)
    except Exception as e:
        print(f"Sentiment analysis error: {e}")
        return 0.0
