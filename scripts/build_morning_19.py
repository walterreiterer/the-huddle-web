#!/usr/bin/env python3
"""THE HUDDLE 1.9 – isolierte KI-Probeausgabe, keine Veröffentlichung."""
import importlib.util
import json
from pathlib import Path


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    ranked = sorted(eligible, key=lambda a: (topics.score(a)[0], topics.source_priority(a)), reverse=True)
    selected, seen_events, publishers = [], set(), {}
    for a in ranked:
        pts, _ = topics.score(a)
        if pts < topics.MIN_SCORE:
            continue
        pub = str(a.get('source') or 'Unbekannt')
        event = topics.event_key(a)
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
    morning.OUTPUT = Path('drafts/the-huddle-probeausgabe-19.md')
    morning.AUDIT = Path('drafts/redaktionspruefung-19.md')
    morning.INSTRUCTIONS += chr(10) + 'THE HUDDLE 1.9: Die Artikel sind nach 1.8.4 gewichtet. Nur ausreichend belegte sportliche Nachrichten aufnehmen. Keine Veroeffentlichung.'

    def test_sources():
        undated = sum(1 for a in articles if isinstance(a, dict) and topics.age_hours(a.get('published')) is None)
        out_of_window = sum(1 for a in articles if isinstance(a, dict) and (age := topics.age_hours(a.get('published'))) is not None and not (-2 <= age <= 48))
        return articles, selected, games, undated, out_of_window

    morning.load_sources = test_sources
    morning.main()
    report = Path('drafts/themenauswahl-19.md')
    lines = ['# THE HUDDLE 1.9 – Themenauswahl', '',
             'Isolierter Test mit Themengewichtung 1.8.4; keine Veröffentlichung.',
             f'Geeignete Kandidaten: {len(eligible)}; ausgewaehlt: {len(selected)}', '']
    for i, a in enumerate(selected, 1):
        points, reasons = topics.score(a)
        lines.append(f'{i}. {a.get("title", "")} — {points} Punkte — {a.get("url", "")}')
    report.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('THE HUDDLE 1.9: Probeausgabe und Pruefbericht erstellt, nicht veroeffentlicht')


if __name__ == '__main__':
    main()
