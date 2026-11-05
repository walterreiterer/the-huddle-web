#!/usr/bin/env python3
"""THE HUDDLE – unabhängige redaktionelle Gegenprüfung (Test).

Aufruf lokal/GitHub: python scripts/review_editorial_15.py
Optional mit KI: python scripts/review_editorial_15.py --ai
Schreibt ausschließlich drafts/redaktionelle-gegenpruefung-15.md.
Ändert weder Ausgabe noch JSON noch Freigabe/Veröffentlichung.
"""
import argparse
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path('drafts')
DRAFT = ROOT / 'the-huddle-morgenausgabe-13.md'
SOURCES = ROOT / 'quellen-10.json'
REPORT = ROOT / 'redaktionelle-gegenpruefung-15.md'
MODEL = os.getenv('HUDDLE_REVIEW_MODEL', 'gpt-5-mini')


def source_context():
    if not SOURCES.is_file():
        return 'Quellen-JSON nicht vorhanden. Quellenabgleich nicht möglich.'
    data = json.loads(SOURCES.read_text(encoding='utf-8'))
    articles = data.get('articles', [])
    if not isinstance(articles, list):
        raise ValueError('articles muss eine Liste sein')
    selected = []
    for article in articles[:26]:
        if not isinstance(article, dict):
            continue
        selected.append({
            'title': str(article.get('title', ''))[:230],
            'url': str(article.get('url', ''))[:500],
            'published': str(article.get('published', ''))[:100],
            'text_excerpt': str(article.get('text', ''))[:1700],
        })
    return json.dumps(selected, ensure_ascii=False, indent=2)


def basic_flags(draft):
    flags = []
    if not draft.startswith('TESTENTWURF – AUTOMATISCH ERSTELLT, NICHT VERÖFFENTLICHEN'):
        flags.append('Entwurfskennzeichnung fehlt oder weicht ab.')
    if not re.search(r'^# THE HUDDLE', draft, re.M):
        flags.append('THE HUDDLE-Hauptüberschrift fehlt.')
    if re.search(r'\b(heute|morgen|gestern|am Wochenende)\b', draft, re.I):
        flags.append('Relative Zeitangaben vorhanden: mit Ausgabedatum und Ereigniszeit abgleichen.')
    if re.search(r'\b(trade|wechsel|transfer)\b', draft, re.I):
        flags.append('Transfermeldung vorhanden: Abschlussstatus gegen Originalquelle prüfen.')
    return flags


def request_review(draft, sources, now):
    key = os.getenv('OPENAI_API_KEY', '').strip()
    if not key:
        raise RuntimeError('OPENAI_API_KEY fehlt; --ai kann nicht ausgeführt werden.')
    instructions = (
        'Du bist unabhängige Qualitätskontrolle eines deutschsprachigen NFL-Morgenbriefs. '
        'Schreibe KEINE korrigierte Ausgabe, sondern nur einen deutschsprachigen Markdown-Prüfbericht. '
        'Prüfe: (1) Widerspruch zwischen Überschrift und Text, insbesondere abgeschlossen vs. geplant/berichtet; '
        '(2) Zeitform relativ zum Wiener Ausgabedatum, Week-/Spielstatus; '
        '(3) doppelte Themen zwischen Lead, Brief und Stories; '
        '(4) Belegbarkeit der konkreten Aussagen durch die beigefügten Quellen-Auszüge; '
        '(5) niedrigen Nachrichtenwert. '
        'Für jeden Verdacht nenne die genaue Textstelle, den Grund, gegebenenfalls eine URL und '
        'eine konkrete redaktionelle Handlung. Trenne BELEGT, WIDERSPRUCH, UNKLAR und EMPFEHLUNG. '
        'Wenn die Quellen nicht reichen, sage UNKLAR. Keine Behauptung, live im Internet recherchiert zu haben. '
        'Keine erfundenen Fakten, keine automatischen Freigaben. '
        'Beginne mit "# THE HUDDLE – Zweite redaktionelle Prüfung" und ende mit '
        '"Status: manuelle Freigabe weiterhin erforderlich."'
    )
    body = ('Prüfzeit Wien: ' + now + '\n\nENTWURF:\n' + draft[:26000] +
            '\n\nQUELLENAUSZÜGE (nicht garantiert vollständig):\n' + sources[:65000])
    payload = {
        'model': MODEL,
        'instructions': instructions,
        'input': body,
        'max_output_tokens': 4000,
        'store': False,
    }
    req = urllib.request.Request(
        'https://api.openai.com/v1/responses',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            response = json.load(resp)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'OpenAI HTTP {exc.code}: {exc.read(500).decode("utf-8", "replace")}') from exc
    if response.get('status') != 'completed':
        raise RuntimeError('KI-Antwort nicht vollständig: ' + str(response.get('status')))
    chunks = []
    for item in response.get('output', []):
        if item.get('type') == 'message':
            for content in item.get('content', []):
                if content.get('type') == 'output_text':
                    chunks.append(content.get('text', ''))
    result = '\n'.join(chunks).strip()
    if not result.startswith('# THE HUDDLE – Zweite redaktionelle Prüfung') or 'manuelle Freigabe weiterhin erforderlich' not in result:
        raise RuntimeError('KI-Prüfbericht unvollständig oder im falschen Format.')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ai', action='store_true', help='Zusätzliche, kostenpflichtige KI-Gegenprüfung')
    args = parser.parse_args()
    if not DRAFT.is_file():
        raise SystemExit('GEGENPRUEFUNG: Entwurf fehlt: ' + str(DRAFT))
    draft = DRAFT.read_text(encoding='utf-8')
    now = datetime.now(ZoneInfo('Europe/Vienna')).isoformat(timespec='minutes')
    flags = basic_flags(draft)
    lines = [
        '# THE HUDDLE – Zweite redaktionelle Prüfung', '',
        f'Prüfzeit Wien: {now}', '',
        'Status: UNVERÖFFENTLICHT – kein journalistischer Faktencheck.', '',
        '## Lokale Hinweise',
    ]
    lines.extend('- ' + f for f in flags) if flags else lines.append('- Keine einfachen Auffälligkeiten gefunden.')
    if args.ai:
        lines.extend(['', '## Unabhängige KI-Gegenprüfung', '', request_review(draft, source_context(), now)])
    else:
        lines.extend(['', '## KI-Gegenprüfung', '',
                      '- Noch nicht ausgeführt. Für einen gesonderten API-Test mit `--ai` starten.'])
    lines.extend(['', 'Status: manuelle Freigabe weiterhin erforderlich.', ''])
    ROOT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text('\n'.join(lines), encoding='utf-8')
    print(f'GEGENPRUEFUNG: Bericht erstellt: {REPORT}; Hinweise: {len(flags)}; KI: {"ja" if args.ai else "nein"}')
    print('Keine Änderung an Entwurf, Vorschau oder Website.')


if __name__ == '__main__':
    main()
