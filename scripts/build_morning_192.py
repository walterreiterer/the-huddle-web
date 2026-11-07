#!/usr/bin/env python3
"""THE HUDDLE 1.9.2: isolated AI editorial test using topic selection Revision B."""
import importlib.util
import json
from pathlib import Path

ROOT = Path('drafts')
OUT = ROOT / 'the-huddle-probeausgabe-192.md'
AUDIT = ROOT / 'redaktionspruefung-192.md'
SELECTION = ROOT / 'themenauswahl-192.md'

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def main():
    topics = load('huddle_topics_18_for_192', 'scripts/compare_topics_18.py')
    selector = load('huddle_selector_192', 'scripts/compare_topics_192.py')
    morning = load('huddle_morning_13_for_192', 'scripts/build_morning_13.py')
    if not topics.SRC.is_file() or not morning.GAMES.is_file():
        raise SystemExit('THE HUDDLE 1.9.2: Quellen oder ESPN-Bericht fehlen')
    raw = json.loads(topics.SRC.read_text(encoding='utf-8'))
    articles = raw.get('articles', [])
    if not isinstance(articles, list):
        raise SystemExit('THE HUDDLE 1.9.2: Ungültige Artikelstruktur')
    eligible, excluded = [], []
    undated = out_of_window = 0
    for a in articles:
        if not isinstance(a, dict):
            continue
        title, url, body = (str(a.get(k) or '') for k in ('title', 'url', 'text'))
        age = topics.age_hours(a.get('published'))
        reason = None
        if topics.BAD.search(title + ' ' + url):
            reason = 'Service/Wetten/Fantasy'
        elif age is None:
            undated += 1
            reason = 'Datum ungültig'
        elif not (-2 <= age <= 48):
            out_of_window += 1
            reason = 'Datum außerhalb 48 Stunden'
        elif len(body.split()) < 120 or not url.startswith('https://'):
            reason = 'Text zu kurz oder URL ungültig'
        elif topics.EUROPE.search(title + ' ' + url):
            reason = 'Europäischer Football statt NFL'
        elif selector.LIFESTYLE.search(title):
            reason = 'Lifestyle/Prominenz'
        elif selector.OPINION.search(title):
            reason = 'Meinung/Prognose'
        elif not (selector.NEWS.search(title) or ('aiyuk' in title.lower() and 'meeting' in title.lower())):
            reason = 'Kein klarer NFL-Nachrichtenanker – manuell prüfen'
        if reason:
            excluded.append((a, reason))
        else:
            eligible.append(a)

    ranked = sorted(eligible, key=lambda a: (topics.score(a)[0], topics.source_priority(a)), reverse=True)
    selected, publishers, clusters = [], {}, {}
    for a in ranked:
        points = topics.score(a)[0]
        if points < max(3, topics.MIN_SCORE):
            reason = f'Punktzahl zu niedrig ({points})'
        elif any(selector.same_event(a, b, topics) for b in selected):
            reason = 'Dublette eines ausgewählten Ereignisses'
        else:
            title = str(a.get('title') or '').lower()
            cluster = 'brandon-aiyuk' if 'aiyuk' in title else None
            pub = str(a.get('source') or 'Unbekannt')
            if cluster and clusters.get(cluster, 0) >= 2:
                reason = 'Themenkomplex-Limit (maximal 2): Brandon Aiyuk'
            elif publishers.get(pub, 0) >= 4:
                reason = 'Quellenlimit (maximal 4 je Verlag)'
            elif len(selected) >= 12:
                reason = 'Auswahlgrenze (maximal 12)'
            else:
                selected.append(a)
                publishers[pub] = publishers.get(pub, 0) + 1
                if cluster:
                    clusters[cluster] = clusters.get(cluster, 0) + 1
                continue
        excluded.append((a, reason))
    ROOT.mkdir(parents=True, exist_ok=True)
    report = ['# THE HUDDLE – Themenauswahl 1.9.2', '',
              'Revision B mit maximal zwei Brandon-Aiyuk-Themen; keine Veröffentlichung.', '',
              f'Gesammelt: {len(articles)}; geeignet: {len(eligible)}; ausgewählt: {len(selected)}', '',
              '## Ausgewählt', '']
    report += [f'{i}. {a.get("title", "")} — {topics.score(a)[0]} Punkte — {a.get("url", "")}' for i, a in enumerate(selected, 1)]
    report += ['', '## Zurückgestellt', '']
    report += [f'- {a.get("title", "")} — {reason}' for a, reason in excluded]
    SELECTION.write_text('\n'.join(report) + '\n', encoding='utf-8')
    if not selected:
        raise SystemExit('THE HUDDLE 1.9.2: Keine geeigneten Nachrichten; kein KI-Aufruf')

    games = morning.GAMES.read_text(encoding='utf-8')
    morning.OUTPUT = OUT
    morning.AUDIT = AUDIT
    morning.INSTRUCTIONS += '''
THE HUDDLE 1.9.2 – ZUSATZREGELN:
Die Themen wurden mit Revision B redaktionell vorgefiltert.
Höchstens eine Brandon-Aiyuk-Meldung in der fertigen Ausgabe, sofern nicht zwei
unabhängige, außergewöhnlich wichtige Entwicklungen klar getrennt belegbar sind.
Lifestyle, Spekulationen und bloße Meinungen nicht als Nachrichten ausgeben.
Fehlende oder fehlgeschlagene ESPN-Abfragen NICHT als spielfreie Tage ausgeben.
Bei ESPN-Datenlücken den Game Center ausdrücklich als unvollständig kennzeichnen.
Keine Veröffentlichung. Keine Fakten oder Quellen erfinden.
'''
    if 'Datenabruf fehlgeschlagen' in games or 'Datenlücke' in games or 'Abruf fehlgeschlagen' in games:
        morning.INSTRUCTIONS += '\nWARNUNG: ESPN-Abruf möglicherweise unvollständig. Keine Spielfreiheit behaupten.\n'
    def test_sources():
        return articles, selected, games, undated, out_of_window
    morning.load_sources = test_sources
    morning.main()
    with AUDIT.open('a', encoding='utf-8') as f:
        f.write('\n## Themenfilter 1.9.2\n\n')
        f.write(f'- Ausgewählt: {len(selected)}; zurückgestellt: {len(excluded)}\n')
        f.write('- Strukturprüfung ist kein unabhängiger Faktencheck.\n')
    print('THE HUDDLE 1.9.2: Testentwurf, Prüfreport und Themenauswahl erstellt; NICHT veröffentlicht')

if __name__ == '__main__':
    main()
