from textblob import TextBlob

def analyze_sentiment(text):
    """
    Returns sentiment polarity:
    >0 positive, <0 negative, 0 neutral
    """
    blob = TextBlob(text)
    polarity = blob.sentiment.polarity
    return polarity
