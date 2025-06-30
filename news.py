from flask import Blueprint, jsonify
import requests
import re
from bs4 import BeautifulSoup

news_bp = Blueprint("news", __name__)

QUERIES = [
    "us fed rate hike",
    "india inflation",
    "us inflation",
    "oil price",
    "rbi policy",
    "gdp india",
    "china gdp",
    "interest rates",
    "repo rate india",
    "crude oil prices",
    "gold price surge",
    "fii selling",
    "nifty crash",
    "rupee depreciation",
    "usd inr exchange rate",
    "us unemployment rate",
    "federal reserve meeting",
    "bond yield",
    "yield curve inversion",
    "market volatility",
    "vix spike",
    "budget announcement india",
    "gst collection",
    "fiscal deficit",
    "geopolitical tensions",
    "russia ukraine war",
    "iran israel war",
    "taiwan china tensions",
    "china us trade war",
    "sanctions"
]

RSS_BASE_URL = "https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"

def clean_text(text):
    return re.sub(r"[^a-zA-Z0-9\s]", "", text.strip())

def get_final_article_url(link):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(link, headers=headers, timeout=8, allow_redirects=True)
        return res.url
    except:
        return link

def fetch_rss_headline(query):
    try:
        url = RSS_BASE_URL.format(query=query.replace(" ", "+"))
        res = requests.get(url, timeout=10)
        soup = BeautifulSoup(res.content, features="xml")
        item = soup.find("item")
        if item:
            title = clean_text(item.title.text)
            link = item.link.text
            final_url = get_final_article_url(link)
            return {
                "query": query,
                "headline": title,
                "link": final_url
            }
    except Exception as e:
        print(f"⚠️ Error fetching for {query}: {e}")
    return None

def fetch_all_headlines():
    all_headlines = []
    for query in QUERIES:
        result = fetch_rss_headline(query)
        if result:
            all_headlines.append(result)
    return all_headlines

@news_bp.route("/", methods=["GET"])
def news_route():
    return jsonify(fetch_all_headlines())
