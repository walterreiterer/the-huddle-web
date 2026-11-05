
#!/usr/bin/env python3
"""THE HUDDLE – KI-Testvorschau mit Datums- und Redaktionsregeln."""

import json
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path("drafts")
ARTICLES = ROOT / "quellen-10.json"
GAMES = ROOT / "nfl-spiele-08.md"
OUTPUT = ROOT / "the-huddle-morgenausgabe-13.md"
AUDIT = ROOT / "redaktionspruefung-13.md"

NOW = datetime.now(ZoneInfo("Europe/Vienna"))
MAX_ARTICLE_AGE_HOURS = 48
FUTURE_TOLERANCE_HOURS = 2

BAD = re.compile(
    r"\b(fantasy|dfs|draftkings|fanduel|sportsbook|betting|"
    r"odds|parlay|prop bets?|mock draft|waiver wire|"
    r"how to watch|streaming|start.?sit|tv schedule)\b",
    re.I
)

HIGH = re.compile(
    r"\b(injury|injured|trade|traded|fired|hired|"
    r"suspended|playoff|quarterback|record|coach|"
    r"season-ending|extension|contract|released|waived|"
    r"signed|signing|ruled out|out for season|"
    r"season-ending|head coach|general manager)\b",
    re.I
)

LOW_NEWS_VALUE = re.compile(
    r"\b(podcast|interview|columnist|reporter|journalist|"
    r"broadcast|broadcaster|tv host|media personality|"
    r"social media|celebrity|fashion|merchandise|"
    r"power rankings|opinion|mailbag|recap show)\b",
    re.I
)


def fail(message):
    raise SystemExit("THE HUDDLE: " + message)


def age_hours(value):
    if not value:
        return None
    try:
        d = parsedate_to_datetime(str(value))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return (
            NOW - d.astimezone(ZoneInfo("Europe/Vienna"))
        ).total_seconds() / 3600
    except (ValueError, TypeError, OverflowError):
        return None


def priority(article):
    title = str(article.get("title", ""))
    age = age_hours(article.get("published"))
    points = 5 if HIGH.search(title) else 0
    if LOW_NEWS_VALUE.search(title):
        points -= 10

    if age is not None:
        if 0 <= age <= 18:
            points += 7
        elif 0 <= age <= 36:
            points += 4
        elif 0 <= age <= 48:
            points += 1
        else:
            points -= 5

    return points


def load_sources():
    if not ARTICLES.is_file() or not GAMES.is_file():
        fail("Quellen oder ESPN-Spielbericht fehlen.")

    source_data = json.loads(
        ARTICLES.read_text(encoding="utf-8")
    )
    articles = source_data.get("articles", [])
