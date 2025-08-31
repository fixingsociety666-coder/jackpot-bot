from textblob import TextBlob

def analyze_sentiment(text: str) -> str:
    """
    Analyze sentiment of given text using TextBlob.
    Returns one of: "positive", "negative", or "neutral".
    Always safe (never crashes).
    """
    if not text or not isinstance(text, str):
        return "neutral"

    try:
        polarity = TextBlob(text).sentiment.polarity
        if polarity > 0.1:
            return "positive"
        elif polarity < -0.1:
            return "negative"
        else:
            return "neutral"
    except Exception as e:
        # Fallback: if TextBlob fails, default to neutral
        return "neutral"


def sentiment_score(text: str) -> float:
    """
    Returns a polarity score between -1.0 and 1.0.
    Useful if you want numeric scoring instead of just categories.
    """
    if not text or not isinstance(text, str):
        return 0.0

    try:
        return TextBlob(text).sentiment.polarity
    except Exception:
        return 0.0
