"""Isolated, read-only research: identify official NFL game-book links.

No guessed PDF URLs are ever treated as verified.
"""
import json
import re
from html import unescape
from html.parser import HTMLParser
from io import BytesIO
from urllib.parse import urljoin, urlparse

import requests
from pypdf import PdfReader

GAMES = [
    ("Panthers @ Packers", "panthers-at-packers-2026-reg-8", ("panthers", "packers")),
    ("Ravens @ Bills", "ravens-at-bills-2026-reg-8", ("ravens", "bills")),
    ("Titans @ Bengals", "titans-at-bengals-2026-reg-8", ("titans", "bengals")),
    ("Colts @ Jaguars", "colts-at-jaguars-2026-reg-8", ("colts", "jaguars")),
]
REFERENCE_PDF = "https://static.www.nfl.com/image/upload/v1793361096/gamecenter/aaf70a66-4feb-11f1-abca-2c54536568a9.pdf"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; HuddleGameBookResearch/2.0)", "Accept": "text/html,application/xhtml+xml"}

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

def normalize_html(s):
    return unescape(s.replace("\\u002F", "/").replace("\\/", "/").replace("\\u003A", ":"))

def is_official_pdf(url):
    p = urlparse(url)
    return p.scheme == "https" and p.hostname == "static.www.nfl.com" and p.path.lower().endswith(".pdf") and "/gamecenter/" in p.path.lower()

def pdf_candidates(html, game_url):
    parser = LinkParser()
    parser.feed(html)
    linked = []
    for link in parser.links:
        if re.search(r"game\s*book", link["text"], re.I):
            url = urljoin(game_url, link["href"])
            if is_official_pdf(url):
                linked.append(url)
    # Only inspect the immediate neighborhood of a Game Book label;
    # page-wide PDF lists may include unrelated games and record books.
    nearby = []
    for match in re.finditer(r"(?:download\s+)?game\s*book", html, re.I):
        snippet = html[max(0, match.start()-1200):match.end()+1200]
        for raw in re.findall(r"https://static\.www\.nfl\.com/[^\s\"'<>\\]+?\.pdf", snippet, re.I):
            url = unescape(raw)
            if is_official_pdf(url):
                nearby.append(url)
    return list(dict.fromkeys(linked)), list(dict.fromkeys(nearby))

def verify_pdf(session, url, teams):
    try:
        r = session.get(url, timeout=30)
        r.raise_for_status()
        if not r.content.startswith(b"%PDF-"):
            return "KEIN PDF", "Signatur fehlt"
        reader = PdfReader(BytesIO(r.content))
        text = " ".join((page.extract_text() or "") for page in reader.pages[:3]).lower()
        if all(team in text for team in teams):
            return "PDF + TEAMNAMEN BESTÄTIGT", f"{len(reader.pages)} Seiten"
        return "PDF ERREICHBAR, ZUORDNUNG OFFEN", f"{len(reader.pages)} Seiten; Teamnamen nicht beide auf Seiten 1–3 gefunden"
    except Exception as e:
        return "PDF-PRÜFUNG FEHLGESCHLAGEN", str(e)[:180]

def main():
    session = requests.Session()
    session.headers.update(HEADERS)
    print("THE HUDDLE – NFL Game Book Recherchetest Phase 2", flush=True)
    for name, slug, teams in GAMES:
        url = f"https://www.nfl.com/games/{slug}?tab=recap"
        print(f"\n=== {name} ===\nSpielseite: {url}", flush=True)
        try:
            response = session.get(url, timeout=30)
            print("HTTP:", response.status_code)
            response.raise_for_status()
            html = normalize_html(response.text)
            linked, nearby = pdf_candidates(html, url)
            print("Direkt mit 'Game Book' beschriftete PDF-Links:", len(linked))
            print("PDFs in Textnähe der Beschriftung (unbestätigt):", len(nearby))
            candidates = linked or nearby
            if name == "Panthers @ Packers":
                print("Bekannte Referenz-PDF im HTML:", "JA" if REFERENCE_PDF in html else "NEIN")
                if REFERENCE_PDF not in candidates:
                    print("Hinweis: Referenz-PDF nicht eindeutig am Download-Element erkannt.")
                    candidates = [REFERENCE_PDF] + candidates
            if not candidates:
                print("ERGEBNIS: KEINE EINDEUTIGE PDF-ZUORDNUNG; nichts wird geraten.")
                continue
            for pdf in candidates[:3]:
                print("Kandidat:", pdf)
                outcome, detail = verify_pdf(session, pdf, teams)
                print("Prüfung:", outcome, "|", detail)
            if len(candidates) > 3:
                print(f"Weitere {len(candidates)-3} Kandidaten nicht geprüft (Sicherheitslimit).")
        except requests.RequestException as e:
            print("SPIELSEITE NICHT ERREICHBAR:", str(e)[:180])
    print("\nTest abgeschlossen. Keine Veröffentlichung, keine Datenänderung.")

if __name__ == "__main__":
    main()
