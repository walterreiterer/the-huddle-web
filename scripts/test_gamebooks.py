"""THE HUDDLE: isolated ESPN -> NFL Game Book research test.

Writes only data/gamebooks-preview.json locally. Does not publish or change production feeds.
"""
import json
import re
from pathlib import Path
from html import unescape
from html.parser import HTMLParser
from io import BytesIO
from urllib.parse import urljoin, urlparse

import requests
from pypdf import PdfReader

TEST_DATE = "20261101"  # A known completed NFL Sunday; change only for later tests.
ESPN_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
    f"?dates={TEST_DATE}&limit=100"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; HuddleGameBookResearch/3.0)",
    "Accept": "text/html,application/xhtml+xml,application/json",
}

# NFL game URLs use team nicknames, not necessarily ESPN abbreviations.
TEAM_SLUGS = {
    "ARI": "cardinals", "ATL": "falcons", "BAL": "ravens", "BUF": "bills",
    "CAR": "panthers", "CHI": "bears", "CIN": "bengals", "CLE": "browns",
    "DAL": "cowboys", "DEN": "broncos", "DET": "lions", "GB": "packers",
    "HOU": "texans", "IND": "colts", "JAX": "jaguars", "JAC": "jaguars",
    "KC": "chiefs", "LV": "raiders", "LAC": "chargers", "LAR": "rams",
    "LA": "rams", "MIA": "dolphins", "MIN": "vikings", "NE": "patriots",
    "NO": "saints", "NYG": "giants", "NYJ": "jets", "PHI": "eagles",
    "PIT": "steelers", "SEA": "seahawks", "SF": "49ers", "TB": "buccaneers",
    "TEN": "titans", "WSH": "commanders", "WAS": "commanders",
}


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.current = None
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.current = {"href": dict(attrs).get("href", ""), "text": ""}

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"] += data

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            self.links.append(self.current)
            self.current = None


def normalize_html(html):
    return unescape(
        html.replace("\\u002F", "/")
        .replace("\\/", "/")
        .replace("\\u003A", ":")
    )


def is_official_pdf(url):
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname == "static.www.nfl.com"
        and parsed.path.lower().endswith(".pdf")
        and "/gamecenter/" in parsed.path.lower()
    )


def labeled_gamebook_links(html, game_url):
    parser = LinkParser()
    parser.feed(html)
    urls = []
    for link in parser.links:
        if re.search(r"game\s*book", link["text"], re.I):
            url = urljoin(game_url, link["href"])
            if is_official_pdf(url) and url not in urls:
                urls.append(url)
    return urls


def verify_pdf(session, url, team_slugs):
    try:
        response = session.get(url, timeout=35)
        response.raise_for_status()
        if not response.content.startswith(b"%PDF-"):
            return False, "PDF-Signatur fehlt"
        reader = PdfReader(BytesIO(response.content))
