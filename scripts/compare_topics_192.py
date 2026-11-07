#!/usr/bin/env python3
"""THE HUDDLE 1.9.2 – Themenvergleich, Revision B. Kein KI-Aufruf, keine Veröffentlichung."""
import importlib.util
import json
import re
from pathlib import Path

BASE = Path('scripts/compare_topics_18.py')
SRC = Path('drafts/quellen-10.json')
OUT = Path('drafts/themenvergleich-192.md')
OLD = Path('drafts/themenauswahl-191.md')
LIFESTYLE = re.compile(r'\b(?:bartenders?|bar owners?|museums?|normal person|cocktails?|restaurants?|fashion|outfits?|vacations?|tourists?|sightseeing|celebrity gossip|dating|nightlife)\b', re.I)
OPINION = re.compile(r'\b(?:power rankings?|mock drafts?|fantasy|betting|odds|predictions?|picks for|what we learned|hot takes?|mailbag|asking price|trade targets?|insider reveals|potential trade|could be traded)\b', re.I)
NEWS = re.compile(r'\b(?:nfl|super bowl|playoffs?|teams?|quarterbacks?|\bqb\b|coach(?:es)?|trades?|traded|signed|signing|released|fired|hired|injur(?:y|ies|ed)|surgery|return(?:s|ing)?|suspended|suspension|contract|record|touchdown|game|win(?:s|ning)?|beat(?:s|en)?|defeat(?:s|ed)?|victory|loss|loses|ruled out|practice|roster|starter|starting|start|draft pick|reinstat(?:ed|ement)|concussion|sieg(?:t|e)?|besiegt|schlägt|gewinnt|niederlagen?|verliert|unterliegt|verletz(?:t|ung)|ausfall|rückkehr)\b', re.I)


def load_topics():
    spec = importlib.util.spec_from_file_location('huddle_topics_18', BASE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def event_key(article, topics):
    """Only merge known event types; do not collapse distinct Aiyuk developments."""
    title = str(article.get('title') or '').lower()
    if 'aiyuk' in title:
        if re.search(r'\b(?:owe|owes|bonus|bonuses|million|\$13)\b', title):
            return 'aiyuk-bonus-dispute'
        if re.search(r'\b(?:not yet reinstated|reinstat(?:ed|ement)|reserve/left)\b', title):
            return 'aiyuk-roster-status'
        if re.search(r'\b(?:meeting|to be continued)\b', title):
            return 'aiyuk-meeting'
        return None
    return topics.event_key(article)


def same_event(a, b, topics):
    ak, bk = event_key(a, topics), event_key(b, topics)
    if ak and bk:
        return ak == bk
    # Compare only when neither has a known event type; prevents unrelated
    # developments about the same player from being suppressed.
    return not ak and not bk and topics.same_story(a, b)


def main():
    topics = load_topics()
    data = json.loads(SRC.read_text(encoding='utf-8'))
    articles = data.get('articles', [])
    if not isinstance(articles, list):
        raise SystemExit('articles muss eine Liste sein')
    eligible, excluded = [], []
    for a in articles:
        if not isinstance(a, dict):
            continue
        title, url, body = (str(a.get(k) or '') for k in ('title', 'url', 'text'))
        age = topics.age_hours(a.get('published'))
        reason = None
        if topics.BAD.search(title + ' ' + url):
            reason = 'Service/Wetten/Fantasy'
        elif age is None or not (-2 <= age <= 48):
            reason = 'Datum außerhalb 48 Stunden/ungültig'
        elif len(body.split()) < 120 or not url.startswith('https://'):
            reason = 'Text zu kurz oder URL ungültig'
        elif topics.EUROPE.search(title + ' ' + url):
            reason = 'Europäischer Football statt NFL'
        elif LIFESTYLE.search(title):
            reason = 'Lifestyle/Prominenz (Titel)'
        elif OPINION.search(title):
            reason = 'Meinung/Prognose (Titel)'
        elif not (NEWS.search(title) or ('aiyuk' in title.lower() and re.search(r'\bmeeting\b', title, re.I))):
            reason = 'Kein klarer NFL-Nachrichtenanker im Titel – manuell prüfen'
        if reason:
            excluded.append((a, reason))
        else:
            eligible.append(a)
    ranked = sorted(eligible, key=lambda a: (topics.score(a)[0], topics.source_priority(a)), reverse=True)
    selected, publishers = [], {}
    for a in ranked:
        points, _ = topics.score(a)
        if points < max(3, topics.MIN_SCORE):
            excluded.append((a, f'Punktzahl zu niedrig ({points})'))
            continue
        duplicate = next((b for b in selected if same_event(a, b, topics)), None)
        if duplicate:
            excluded.append((a, 'Dublette zu: ' + str(duplicate.get('title', ''))))
            continue
        pub = str(a.get('source') or 'Unbekannt')
        if publishers.get(pub, 0) >= 4:
            excluded.append((a, 'Quellenlimit (maximal 4 je Verlag)'))
            continue
        if len(selected) >= 12:
            excluded.append((a, 'Auswahlgrenze (maximal 12)'))
            continue
        selected.append(a)
        publishers[pub] = publishers.get(pub, 0) + 1
    lines = ['# THE HUDDLE – Themenvergleich 1.9.2 (Revision B)', '',
             'Nur Themenauswahl, kein KI-Aufruf, keine Veröffentlichung.', '',
             f'Quellen insgesamt: {len(articles)}',
             f'Nach Basis- und Nachrichtenwertfilter: {len(eligible)}',
             f'Neue Auswahl: {len(selected)}', '', '## Auswahl 1.9.2', '']
    lines += [f'{i}. {a.get("title", "")} — {topics.score(a)[0]} Punkte — {a.get("url", "")}' for i, a in enumerate(selected, 1)]
    lines += ['', '## Ausgeschlossene / zurückgestellte Artikel', '']
    lines += [f'- {a.get("title", "")} — {reason}' for a, reason in excluded]
    if OLD.is_file():
        lines += ['', '## Bisherige Themenauswahl 1.9.1 (Referenz)', '', OLD.read_text(encoding='utf-8')]
    else:
        lines += ['', 'Hinweis: themenauswahl-191.md nicht vorhanden; direkter Vergleich entfällt.']
    lines += ['', 'Hinweis: Heuristische Vorauswahl. Keine Faktenprüfung und keine Freigabe. Zeitfenster-Ausschlüsse bleiben bestehen.', '']
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text('\n'.join(lines), encoding='utf-8')
    print(f'THE HUDDLE 1.9.2 Revision B: {len(selected)} ausgewählt; {len(excluded)} zurückgestellt; {OUT}')


if __name__ == '__main__':
    main()
