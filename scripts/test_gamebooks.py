"""THE HUDDLE: isolated ESPN -> NFL Game Book research test.

Writes only data/gamebooks-preview.json locally. Does not publish or change production feeds.
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from html import unescape
from html.parser import HTMLParser
from io import BytesIO
from urllib.parse import urljoin, urlparse

import requests
from pypdf import PdfReader

# Manuell vorgegebenes Datum oder automatisch der Vortag (UTC).
# Format: YYYYMMDD
TEST_DATE = os.environ.get("GAMEBOOK_DATE")

if not TEST_DATE:
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    TEST_DATE = yesterday.strftime("%Y%m%d")

if not re.fullmatch(r"\d{8}", TEST_DATE):
    raise ValueError("GAMEBOOK_DATE muss das Format YYYYMMDD haben")
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
        first_pages = " ".join(
            (page.extract_text() or "") for page in reader.pages[:3]
        ).lower()
        missing = [name for name in team_slugs if name.lower() not in first_pages]
        if missing:
            return False, "Teamnamen fehlen auf Seiten 1–3: " + ", ".join(missing)
        return True, f"{len(reader.pages)} Seiten; beide Teams bestätigt"
    except Exception as exc:
        return False, f"PDF-Prüfung fehlgeschlagen: {str(exc)[:150]}"


def find_week(event, scoreboard):
    # Use source data, not an estimated week number.
    for value in (
        event.get("week"),
        scoreboard.get("week"),
    ):
        if isinstance(value, dict):
            number = value.get("number")
            if isinstance(number, int) and 1 <= number <= 22:
                return number
    return None


def main():
    session = requests.Session()
    session.headers.update(HEADERS)
    print("THE HUDDLE – NFL Game Book Recherchetest Phase 3B", flush=True)
    print("ESPN:", ESPN_URL, flush=True)
    try:
        response = session.get(ESPN_URL, timeout=30)
        response.raise_for_status()
        scoreboard = response.json()
    except (requests.RequestException, ValueError) as exc:
        print("ESPN-Abfrage fehlgeschlagen:", exc)
        return

    events = scoreboard.get("events", [])
    print("ESPN-Spiele gefunden:", len(events), flush=True)
    confirmed = 0
    verified_links = {}
    checked = 0
    skipped = 0

    for event in events:
        competition = (event.get("competitions") or [{}])[0]
        competitors = competition.get("competitors") or []
        home = next((x for x in competitors if x.get("homeAway") == "home"), None)
        away = next((x for x in competitors if x.get("homeAway") == "away"), None)
        if not home or not away:
            skipped += 1
            print("\nÜBERSPRUNGEN: Heim-/Auswärtsteam fehlt")
            continue

        home_code = home.get("team", {}).get("abbreviation", "").upper()
        away_code = away.get("team", {}).get("abbreviation", "").upper()
        home_slug = TEAM_SLUGS.get(home_code)
        away_slug = TEAM_SLUGS.get(away_code)
        week = find_week(event, scoreboard)
        status = event.get("status", {}).get("type", {})
        completed = status.get("completed") is True
        print(f"\n=== {away_code} @ {home_code} ===", flush=True)
        print("ESPN-Event:", event.get("id"), "| Abgeschlossen:", completed, "| Woche:", week)

        if not completed:
            skipped += 1
            print("ÜBERSPRUNGEN: Spiel noch nicht abgeschlossen")
            continue
        if not away_slug or not home_slug or week is None:
            skipped += 1
            print("ÜBERSPRUNGEN: Teamkürzel oder Spielwoche nicht eindeutig")
            continue

        year = scoreboard.get("season", {}).get("year") or event.get("season", {}).get("year")
        season_type = scoreboard.get("season", {}).get("type") or event.get("season", {}).get("type")
        if year != 2026 or season_type != 2:
            skipped += 1
            print("ÜBERSPRUNGEN: Saison oder Regular-Season-Typ nicht bestätigt:", year, season_type)
            continue

        game_url = f"https://www.nfl.com/games/{away_slug}-at-{home_slug}-{year}-reg-{week}?tab=recap"
        print("NFL-Spielseite:", game_url)
        checked += 1
        try:
            page = session.get(game_url, timeout=30)
            print("NFL HTTP:", page.status_code)
            page.raise_for_status()
            links = labeled_gamebook_links(normalize_html(page.text), game_url)
            print("Explizite Game-Book-Links:", len(links))
            if len(links) != 1:
                print("KEIN BESTÄTIGTER LINK: erwartete genau einen beschrifteten PDF-Link")
                continue
            valid, detail = verify_pdf(session, links[0], (away_slug, home_slug))
            if valid:
                confirmed += 1
                verified_links[str(event.get("id"))] = links[0]
                print("BESTÄTIGT:", links[0])
                print("Prüfung:", detail)
            else:
                print("NICHT BESTÄTIGT:", detail)
        except requests.RequestException as exc:
            print("NFL-Abfrage fehlgeschlagen:", str(exc)[:180])

        # Sicherheitsregel: Keine vorhandenen Game Books durch
    # einen Spieltag ohne bestätigte PDFs ersetzen.
    if not verified_links:
        print(
            "SICHERHEIT: Keine bestätigten Game Books gefunden. "
            "Vorhandene JSON-Datei bleibt unverändert.",
            flush=True
        )
        return

    output = Path("data/gamebooks-preview.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {"date": TEST_DATE, "gamebooks": verified_links},
            ensure_ascii=False,
            indent=2
        ) + "\n",
        encoding="utf-8"
    )
    print("Test-JSON geschrieben:", output, "| Einträge:", len(verified_links))

    print("\n=== ZUSAMMENFASSUNG ===")
    print("ESPN-Spiele:", len(events))
    print("NFL-Spielseiten geprüft:", checked)
    print("Bestätigte Game Books:", confirmed)
    print("Übersprungene Spiele:", skipped)
    print("Nur Test-JSON im Workflow erstellt. Keine Veröffentlichung und keine Änderung der Website.")


if __name__ == "__main__":
    main()
