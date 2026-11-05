#!/usr/bin/env python3
"""THE HUDDLE 1.8 – isolierter, kostenfreier Vergleich der Themenauswahl.
Aufruf im Repository: python scripts/compare_topics_18.py
Liest drafts/quellen-10.json, schreibt nur drafts/themenvergleich-18.md.
"""
import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SRC = Path('drafts/quellen-10.json')
OUT = Path('drafts/themenvergleich-18.md')
NOW = datetime.now(ZoneInfo('Europe/Vienna'))
BAD = re.compile(r'\b(fantasy|dfs|draftkings|fanduel|sportsbook|betting|odds|parlay|prop bets?|mock draft|waiver wire|how to watch|streaming|start.?sit|tv schedule)\b', re.I)
SPORT = [
    (r'\b(final score|defeats?|beats?|wins?|victory|overtime|touchdown|game[- ]winning|shutout|upset)\b', 9, 'Spielergebnis'),
    (r'\b(ruled out|out for season|season[- ]ending|injury report|injured reserve|torn acl|concussion|will miss|sidelined)\b', 8, 'Ausfall/Verletzung'),
    (r'\b(traded?|trade agreement|signs?|signed|released|waived|acquired|contract extension|fired|hired|head coach|general manager)\b', 7, 'Kader/Personal'),
    (r'\b(playoff|division lead|clinches?|record[- ]breaking|nfl record|suspension|suspended)\b', 6, 'Wettbewerb/Regel'),
    (r'\b(starting quarterback|starter|bench(?:ed|ing)?|depth chart|questionable|doubtful)\b', 4, 'Spielrelevanz'),
]
LOW = [
    (r'\b(mock draft|draft rankings?|big board|power rankings?|top prospects?|draft grades?)\b', -14, 'Draft-Ranking'),
    (r'\b(opinion|column|mailbag|podcast|recap show|analysis|predictions?|grades?)\b', -8, 'Kommentar/Meinung'),
    (r'\b(owner|ownership|billionaire|celebrity|fashion|merchandise|tv host|broadcaster|media personality)\b', -9, 'Randthema'),
    (r'\b(how to watch|streaming|fantasy|betting|odds|parlay)\b', -15, 'Service/Wetten'),
]

def age_hours(value):
    try:
        if not value:
            return None
        d = parsedate_to_datetime(str(value))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return (NOW - d.astimezone(ZoneInfo('Europe/Vienna'))).total_seconds()/3600
    except (TypeError, ValueError, OverflowError):
        return None

def score(a):
    title = str(a.get('title') or '')
    age = age_hours(a.get('published'))
    points = 0
    reasons = []
    for pattern, value, reason in SPORT + LOW:
        if re.search(pattern, title, re.I):
            points += value
            reasons.append(f'{reason} {value:+d}')
    if age is not None:
        freshness = 9 if age <= 12 else 7 if age <= 24 else 3 if age <= 36 else 0
        points += freshness
        reasons.append(f'Aktualität +{freshness}')
    return points, reasons

def main():
    if not SRC.is_file():
        raise SystemExit('Quellen fehlen: ' + str(SRC))
    articles = json.loads(SRC.read_text(encoding='utf-8')).get('articles', [])
    if not isinstance(articles, list):
        raise SystemExit('articles ist keine Liste')
    eligible = []
    for a in articles:
        if not isinstance(a, dict):
            continue
        title, url, body = (str(a.get(k) or '') for k in ('title', 'url', 'text'))
        age = age_hours(a.get('published'))
        if BAD.search(title + ' ' + url) or age is None or not (-2 <= age <= 48):
            continue
        if len(body.split()) < 120 or not url.startswith('https://'):
            continue
        eligible.append(a)
    # Gleicher Basisfilter für beide Listen; Vergleich isoliert ausschließlich die Gewichtung.
    def old_score(a):
        title = str(a.get('title') or '')
        pts = 5 if re.search(r'\b(injury|injured|trade|traded|fired|hired|suspended|playoff|quarterback|record|coach|season-ending|extension|contract|released|waived|signed|signing|ruled out|out for season|head coach|general manager)\b', title, re.I) else 0
        if re.search(r'\b(podcast|interview|columnist|reporter|journalist|broadcast|broadcaster|tv host|media personality|social media|celebrity|fashion|merchandise|power rankings|opinion|mailbag|recap show)\b', title, re.I):
            pts -= 10
        age = age_hours(a.get('published'))
        pts += 7 if age <= 18 else 4 if age <= 36 else 1
        return pts
    def pick(ranked):
        out, seen, publishers = [], set(), {}
        for a in ranked:
            title = str(a.get('title') or '')
            key = re.sub(r'[^a-z0-9]+', '', title.lower())
            pub = str(a.get('source') or 'Unbekannt')
            if key in seen or publishers.get(pub, 0) >= 4:
                continue
            seen.add(key)
            publishers[pub] = publishers.get(pub, 0) + 1
            out.append(a)
            if len(out) == 12:
                break
        return out
    old = pick(sorted(eligible, key=old_score, reverse=True))
    new = pick(sorted(eligible, key=lambda a: score(a)[0], reverse=True))
    lines = ['# THE HUDDLE – Themenvergleich 1.8', '',
             f'Prüfzeit Wien: {NOW.isoformat(timespec="minutes")}',
             'Nur Simulation, keine KI, keine Veröffentlichung.', '',
             f'Geeignete Quellen: {len(eligible)}', '',
             '## Bisherige Gewichtung (Simulation)', '']
    for i,a in enumerate(old,1):
        lines.append(f'{i}. {a.get("title", "")} — {old_score(a)} Punkte — {a.get("url", "")}')
    lines += ['', '## Neue Gewichtung 1.8 (Simulation)', '']
    for i,a in enumerate(new,1):
        pts, why = score(a)
        lines.append(f'{i}. {a.get("title", "")} — {pts} Punkte ({", ".join(why) or "neutral"}) — {a.get("url", "")}')
    old_urls = {a.get('url') for a in old}
    new_urls = {a.get('url') for a in new}
    lines += ['', '## Neu in der Auswahl', '']
    lines += [f'- {a.get("title", "")}' for a in new if a.get('url') not in old_urls] or ['- Keine']
    lines += ['', '## Entfallen', '']
    lines += [f'- {a.get("title", "")}' for a in old if a.get('url') not in new_urls] or ['- Keine']
    lines += ['', 'Hinweis: Titel-Schlüsselwörter ersetzen keine journalistische Einzelfallprüfung.', '']
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text('\n'.join(lines), encoding='utf-8')
    print(f'THE HUDDLE 1.8: {OUT}; {len(eligible)} Kandidaten; keine Veröffentlichung')

if __name__ == '__main__':
    main()
