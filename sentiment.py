from textblob import TextBlob

def analyze_sentiment(text):
    blob = TextBlob(text)
    return round(blob.sentiment.polarity, 2)
