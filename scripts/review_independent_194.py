#!/usr/bin/env python3
"""THE HUDDLE 1.9.4: unabhängige, nicht publizierende Quellen-Gegenprüfung."""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

D = Path('drafts')
DRAFT = D / 'the-huddle-probeausgabe-193.md'
SOURCES = D / 'quellen-10.json'
GAMES = D / 'nfl-spiele-08.md'
OUT = D / 'gegenpruefung-194.md'
JSON_OUT = D / 'gegenpruefung-194.json'
MODEL = os.getenv('HUDDLE_REVIEW_MODEL', 'gpt-5-mini')


def save_error(message):
    D.mkdir(parents=True, exist_ok=True)
    OUT.write_text('# THE HUDDLE – Unabhängige Gegenprüfung 1.9.4\n\n**NICHT BESTANDEN / NICHT FREIGEGEBEN**\n\n' + message + '\n', encoding='utf-8')
    print(message, file=sys.stderr)
    raise SystemExit(1)


def extract_response_text(data):
    parts = []
    for item in data.get('output', []):
        for part in item.get('content', []):
            if part.get('type') == 'output_text':
                parts.append(part.get('text', ''))
    return '\n'.join(parts).strip()


def call_api(payload):
    req = urllib.request.Request(
        'https://api.openai.com/v1/responses',
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY'], 'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=150) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')[:3000]
        raise ValueError(f'OpenAI API HTTP {exc.code}: {detail}') from exc


def main():
    for path in (DRAFT, SOURCES, GAMES):
        if not path.is_file():
            save_error(f'Pflichtdatei fehlt: {path}')
    if not os.getenv('OPENAI_API_KEY'):
        save_error('OPENAI_API_KEY fehlt. Keine Gegenprüfung möglich.')
    draft = DRAFT.read_text(encoding='utf-8')
    games = GAMES.read_text(encoding='utf-8')
    raw = json.loads(SOURCES.read_text(encoding='utf-8'))
    articles = raw.get('articles', [])
    if not isinstance(articles, list) or not articles:
        save_error('Keine verwertbaren Quellenartikel.')
    urls = set(re.findall(r'https?://[^\s)<>]+', draft))
    evidence = []
    for article in articles:
        url = str(article.get('url', ''))
        if url.rstrip('.,') in urls:
            evidence.append({k: article.get(k, '') for k in ('title', 'source', 'url', 'published', 'text')})
    if not evidence:
        save_error('Keine im Entwurf verlinkten Artikel in den gesammelten Quellen gefunden.')
    # Maximal 12 Quellen; Texte gekürzt, damit der Aufruf berechenbar bleibt.
    evidence = evidence[:12]
    for article in evidence:
        article['text'] = str(article.get('text', ''))[:15000]

    instructions = '''Du bist ein unabhängiger, skeptischer NFL-Faktenredakteur. Prüfe ausschließlich
anhand der mitgelieferten ORIGINAL-QUELLENTEXTE und ESPN-ROHDATEN, nicht anhand von Weltwissen.
Du hast den Entwurf nicht geschrieben. Deine Aufgabe ist Gegenprüfung, nicht Umschreiben.

Für jede eigenständige Nachricht einschließlich Lead und Game Center:
- Zerlege die wesentlichen konkreten Behauptungen (Namen, Teams, Zahlen, Daten, Status,
  Verletzungen, Vertragsfragen, Zitate, Attributionen) und gleiche sie mit den Quellen ab.
- Unterscheide: belegt / teilweise belegt / nicht belegt / widersprochen.
- Markiere ausdrücklich, wenn die Quelle selbst unsicher, anonym, sekundär oder spekulativ ist.
- Zitiere kurze genaue BELEGSTELLEN aus dem mitgelieferten Text, maximal 18 Wörter je Stelle.
- Prüfe, ob Überschrift und Lead zu definitiv formuliert sind.
- Verwechsle nicht Quellenbehauptung mit unabhängig bestätigter Wahrheit.
- Der ESPN-Game-Center darf nur durch die beigefügten ESPN-Daten geprüft werden.
- Fehlende Daten sind nicht automatisch falsche Angaben.
- Erfinde weder Zitate noch Quellen. Falls Evidenz fehlt, markiere 'nicht belegt'.
- Gib pro Meldung eine klare Redaktionsentscheidung und konkrete Korrekturempfehlung.
- Prüfe auffällige Sprachfehler und fehlende priorisierte Themen nur, wenn belegt.

Antworte AUSSCHLIESSLICH als JSON-Objekt mit:
{"gesamtstatus":"SPERREN|MANUELL_PRUEFEN|UNAUFFAELLIG",
