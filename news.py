# news.py
import feedparser

rss_feeds = {
    "Yahoo Finance": "https://finance.yahoo.com/news/rssindex",
    "Seeking Alpha": "https://seekingalpha.com/market-news.xml",
    "Motley Fool": "https://www.fool.com/feeds/",
    "MarketWatch": "https://www.marketwatch.com/rss/topstories",
    "Barchart": "https://www.barchart.com/rss/news",
    "TipsRank": "https://www.tipsranks.com/rss/news",
    "Barrons": "https://www.barrons.com/xml/rss/2_7761.xml"
}

def fetch_news_rss(url):
    feed = feedparser.parse(url)
    articles = []
    for entry in feed.entries[:5]:
        articles.append({'title': entry.title, 'link': entry.link})
    return articles
