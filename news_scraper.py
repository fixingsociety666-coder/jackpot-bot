import feedparser
import requests
from bs4 import BeautifulSoup
from config import SCRAPER_SITES

def fetch_google_news(query="stocks"):
    url = f"https://news.google.com/rss/search?q={query}+when:1h&hl=en-US&gl=US&ceid=US:en"
    feed = feedparser.parse(url)
    return [{"title": e.title, "link": e.link} for e in feed.entries]

def scrape_site(url, selector, prefix=""):
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        items = soup.select(selector)[:5]
        return [{"title": i.text.strip(), "link": prefix+i.get("href","")} for i in items]
    except:
        return []

def fetch_analyst_news():
    news = []
    news += scrape_site(SCRAPER_SITES[0], "h2 a", "https://www.fool.com")
    news += scrape_site(SCRAPER_SITES[1], "li div a", "https://seekingalpha.com")
    news += scrape_site(SCRAPER_SITES[2], "div.bc-table-scrollable-inner a", "https://barchart.com")
    return news
