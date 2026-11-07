#!/usr/bin/env python3
"""THE HUDDLE 1.9 – isolierte KI-Probeausgabe, keine Veröffentlichung."""
import importlib.util
import json
import re
from pathlib import Path
from urllib.parse import urlparse


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Zusätzliche Regeln nur für den isolierten Redaktionstest 1.9.1.
GERMAN_RESULT = re.compile(r'\b(?:sieg|siegt|besiegt|schlägt|schlagen|gewinnt|gewannen|niederlage|verliert|unterliegt|endstand|\d{1,2}\s*[:–-]\s*\d{1,2})\b', re.I)
SPORT_CONTEXT = re.compile(r'\b(?:jaguars|ravens|browns|saints|bills|vikings|colts|chiefs|eagles|packers|steelers|49ers|cowboys|dolphins|broncos|bengals|falcons|rams|seahawks|chargers|raiders|jets|giants|patriots|texans|titans|panthers|bears|lions|buccaneers|commanders|cardinals|nfl|football)\b', re.I)
LIFESTYLE = re.compile(r'\b(?:museum|museums|museo|vacation|holiday|fashion|outfit|celebrity|sightseeing|tourist|normal person|family trip)\b', re.I)
SPECULATION_EXTRA = re.compile(r'\b(?:asking price|trade target|trade targets|trade rumors?|potential trade|could be traded|insider reveals|trade speculation|might trade|may trade|would trade|possible deal)\b', re.I)
OPINION_EXTRA = re.compile(r'\b(?:top \d+|mvp candidates|favorites|rankings|power rankings|prediction|predicts|best season|opinion|takeaways)\b', re.I)


def editorial_score(article, topics):
    title = str(article.get('title') or '')
    score, _ = topics.score(article)
    if GERMAN_RESULT.search(title) and SPORT_CONTEXT.search(title):
        score = max(score, 22 + (9 if (topics.age_hours(article.get('published')) or 999) <= 12 else 7 if (topics.age_hours(article.get('published')) or 999) <= 24 else 3))
    if LIFESTYLE.search(title):
        score -= 25
    if SPECULATION_EXTRA.search(title):
        score -= 24
    if OPINION_EXTRA.search(title):
        score -= 12
    return score


def normalized_event(article):
    title = str(article.get('title') or '').lower()
    if ('aiyuk' in title):
        return 'aiyuk-status'
    if (('jaguars' in title and 'ravens' in title) or ('jacksonville' in title and 'baltimore' in title)) and (GERMAN_RESULT.search(title) or re.search(r'\b(?:beat|defeat|win|rout|crush|final)\b', title)):
        return 'jaguars-ravens-result'
    return None


def espn_warning(games):
    # Fehlende Spielzeilen sind keine Bestätigung, dass tatsächlich spielfrei war.
    empty = len(re.findall(r'Keine NFL-Spiele für dieses Datum gemeldet', games, re.I))
    if empty:
        return ('WARNUNG: ESPN lieferte für ' + str(empty) + ' abgefragte(n) Tag(e) keine Spiele. '
                'Datenlücke möglich; NICHT als bestätigten spielfreien Tag darstellen. '
                'Keine Ergebnisse oder Spielverläufe aus Artikeln in das GAME CENTER übernehmen.')
    return ''


def main():
    topics = load_module('huddle_topics_18', 'scripts/compare_topics_18.py')
    morning = load_module('huddle_morning_13', 'scripts/build_morning_13.py')
    if not topics.SRC.is_file() or not morning.GAMES.is_file():
        raise SystemExit('THE HUDDLE 1.9: Quellen oder ESPN-Daten fehlen')
    raw = json.loads(topics.SRC.read_text(encoding='utf-8'))
    articles = raw.get('articles', [])
    if not isinstance(articles, list):
        raise SystemExit('THE HUDDLE 1.9: Artikelstruktur ungueltig')
    eligible = []
    for a in articles:
        if not isinstance(a, dict):
            continue
        title, url, body = (str(a.get(k) or '') for k in ('title', 'url', 'text'))
        age = topics.age_hours(a.get('published'))
        if topics.BAD.search(title + ' ' + url) or age is None or not (-2 <= age <= 48):
            continue
        if len(body.split()) < 120 or not url.startswith('https://'):
            continue
        if topics.EUROPE.search(title + ' ' + url):
            continue
        eligible.append(a)
    ranked = sorted(eligible, key=lambda a: (editorial_score(a, topics), topics.source_priority(a)), reverse=True)
    selected, seen_events, publishers = [], set(), {}
    for a in ranked:
        pts = editorial_score(a, topics)
        if pts < max(3, topics.MIN_SCORE):
            continue
        pub = str(a.get('source') or 'Unbekannt')
        event = normalized_event(a) or topics.event_key(a)
        if publishers.get(pub, 0) >= 4 or (event and event in seen_events) or any(topics.same_story(a, b) for b in selected):
            continue
        selected.append(a)
        if event:
            seen_events.add(event)
        publishers[pub] = publishers.get(pub, 0) + 1
        if len(selected) >= 12:
            break
    if not selected:
        raise SystemExit('THE HUDDLE 1.9: Keine geeigneten Nachrichten, kein KI-Aufruf')

    games = morning.GAMES.read_text(encoding='utf-8')
    # Originale 1.3-Ausgaben bleiben unangetastet.
    morning.OUTPUT = Path('drafts/the-huddle-probeausgabe-191.md')
    morning.AUDIT = Path('drafts/redaktionspruefung-191.md')
    warning = espn_warning(games)
    morning.INSTRUCTIONS += (chr(10) + '''THE HUDDLE 1.9.1: Die Artikel sind redaktionell neu gewichtet. 
Nur ausreichend belegte sportliche Nachrichten aufnehmen. Lifestyle, Meinungen und Trade-Spekulationen nicht als Top-Meldungen.
Wenn ein Artikel eine überraschende Spieler-Team-Zuordnung enthält, nicht ungeprüft als Tatsache wiedergeben; bei Unsicherheit weglassen.
Bei fehlenden ESPN-Daten NICHT behaupten, es habe keine NFL-Spiele gegeben. Stattdessen schreiben: ESPN-Spielinformationen konnten nicht zuverlässig abgerufen werden; Game Center unvollständig.
Keine Veröffentlichung.''')
    if warning:
        morning.INSTRUCTIONS += chr(10) + warning

    def test_sources():
        undated = sum(1 for a in articles if isinstance(a, dict) and topics.age_hours(a.get('published')) is None)
        out_of_window = sum(1 for a in articles if isinstance(a, dict) and (age := topics.age_hours(a.get('published'))) is not None and not (-2 <= age <= 48))
        return articles, selected, games, undated, out_of_window

    morning.load_sources = test_sources
    morning.main()
    report = Path('drafts/themenauswahl-191.md')
    if warning:
        with morning.AUDIT.open('a', encoding='utf-8') as audit:
            audit.write('\n## ESPN-Datenqualität\n\n- ' + warning + '\n')
    lines = ['# THE HUDDLE 1.9.1 – Themenauswahl', '',
             'Isolierter Test mit zusätzlichen journalistischen Regeln; keine Veröffentlichung.',
             f'Geeignete Kandidaten: {len(eligible)}; ausgewaehlt: {len(selected)}', '']
    for i, a in enumerate(selected, 1):
        points = editorial_score(a, topics)
        lines.append(f'{i}. {a.get("title", "")} — {points} Punkte — {a.get("url", "")}')
    report.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('THE HUDDLE 1.9.1: Probeausgabe und Pruefbericht erstellt, nicht veroeffentlicht')


if __name__ == '__main__':
    main()
