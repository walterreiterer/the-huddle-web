#!/usr/bin/env python3
"""THE HUDDLE 1.2: NFL relevance filtering and targeted Austrian Watch research. No AI calls."""
import datetime as dt
import hashlib
import json
import re
import urllib.parse
from pathlib import Path

import feedparser
import requests
import trafilatura
from googlenewsdecoder import gnewsdecoder

# Keep existing international sources and add Austrian/German-language outlets.
SOURCES = {
    'Yahoo Sports': 'sports.yahoo.com',
    'NBC Sports': 'nbcsports.com',
    'FOX Sports': 'foxsports.com',
    'NFL.com': 'nfl.com',
    'ORF Sport': 'orf.at',
    'Sky Sport Austria': 'skysportaustria.at',
    'Kronen Zeitung': 'krone.at',
    'Kurier': 'kurier.at',
    'Der Standard': 'derstandard.at',
    'LAOLA1': 'laola1.at',
    'Kleine Zeitung': 'kleinezeitung.at',
    'Heute': 'heute.at',
    'Die Presse': 'diepresse.com',
    'Tiroler Tageszeitung': 'tt.com',
    'Kicker': 'kicker.de',
}
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; TheHuddle/1.1; editorial source test)'}
EXCLUDE = re.compile(r'\b(betting|sportsbook|odds|parlay|prop bets?|gambling|fantasy|mock draft|how to watch|watch live|streaming guide|picks against the spread)\b', re.I)
# Strong football context is required for German-language articles.
NFL_CONTEXT = re.compile(
    r"\b(?:NFL|National Football League|American Football|Super Bowl|"
    r"Quarterback|Touchdown|Raimann|Valentin Senn|"
    r"Colts|Cardinals|Chiefs|Bears|Seahawks|Ravens|Bills|"
    r"Broncos|Patriots|Packers|Steelers|49ers|Eagles|"
    r"Cowboys|Vikings|Lions|Jaguars|Jets|Raiders|"
    r"Dolphins|Titans|Texans|Chargers|Bengals|"
    r"Commanders|Buccaneers|Falcons|Panthers|Giants|"
    r"Saints|Browns|Rams)\b", re.I
)
# NFL can mean 'Nutzfläche' in property listings.
PROPERTY = re.compile(
    r"\b(?:Immobilie|Wohnung|Maisonette|Grundstück|"
    r"Gartenwohnung|Nutzfläche|Wohnfläche|Tiefgarage|"
    r"Sanierungsbedürftig|Zimmer|WFL|NFL\s*[:=]?\s*\d+)\b|"
    r"\b(?:m²|qm)\b", re.I
)
GENERIC_TITLE = re.compile(
    r"^(?:Sport|Lifestyle|Zeitgeist|Startseite|News|Aktuelles|"
    r"Übersicht|Home|Fußball|Fussball)(?:\s*[-|:]\s*.*)?$", re.I
)
PLAYER = re.compile(r"\b(?:Bernhard Raimann|Valentin Senn)\b", re.I)

def relevant_title(title, german):
    # For German-language media, an explicit football clue in the headline
    # prevents general category pages and unrelated sports from entering.
    headline = re.sub(r"\s+[-|]\s+[^-|]+$", "", title).strip()
    if GENERIC_TITLE.fullmatch(headline):
        return False
    if german and (PROPERTY.search(headline) or not NFL_CONTEXT.search(headline)):
        return False
    return True

def relevant_article(title, article, german):
    if not relevant_title(title, german):
        return False
    if german:
        # An NFL headline is insufficient when the article is actually
        # a real-estate listing or uses NFL in another sense.
        if PROPERTY.search(title):
            return False
        lead = article[:1600]
        if not NFL_CONTEXT.search(lead):
            return False
    return True

MAX_PER_SOURCE = 4
MAX_PER_AUSTRIAN_QUERY = 5
MIN_WORDS = 120

# Queries are restricted to NFL context to avoid unrelated names and topics.
AUSTRIAN_QUERIES = (
    '"Bernhard Raimann" NFL when:3d',
    '"Valentin Senn" NFL when:3d',
    '("Österreicher" OR "österreichischer") NFL when:3d',
)


def resolve(url):
    if urllib.parse.urlparse(url).hostname != 'news.google.com':
        return url
