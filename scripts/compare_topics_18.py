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
# Reihenfolge ist entscheidend: erst redaktionelle Gattung, dann Relevanz.
CATEGORIES = [
    ('Meinung/Kolumne', r'\b(qb notebook|notebook:|opinion|column|hot takes?|mailbag|has erased all doubts|should trade for|what we learned)\b', -17),
    ('Prognose/Service', r'\b(picks?|predictions?|betting|odds|fantasy|how to watch|fact or fiction|mock draft|big board|draft rankings?|power rankings?)\b', -20),
    ('Porträt/Rückblick', r'\b(how .* transformed|best .* ever|hall of fame induction|retrospective|look back|history of)\b', -13),
    ('Randthema', r'\b(owner|ownership|kraft|celebrity|fashion|media personality|back surgery)\b', -12),
    ('Vorwürfe/Untersuchung', r'\b(allegations?|accused|investigation|abuse|lawsuit)\b', -5),
    ('Spielvorschau', r'\b(preview|matchup|ahead of|to start|will start|set to face)\b', 3),
    ('Spielergebnis', r'\b(final score|defeated|defeats|beat the|beats the|won against|wins over|overtime win|game-winning touchdown)\b', 12),
    ('Verletzung/Ausfall', r'\b(ruled out|out for season|season-ending|injured reserve|torn acl|concussion|will miss|sidelined)\b', 10),
    ('Kader/Personal', r'\b(traded|trade|signed|signs with|released|waived|acquired|contract extension|fired|hired|head coach)\b', 9),
    ('Wettbewerb/Regel', r'\b(clinched|clinches|playoff berth|nfl record|suspended|suspension announced)\b', 7),
    ('Spielrelevanz', r'\b(starting quarterback|named starter|benched|questionable|doubtful|injury report)\b', 6),
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

EUROPE = re.compile(r'\b(afle|elf|efa|the league europe|firenze red lions|european league of football)\b', re.I)
STOP = {'the','a','an','and','or','of','to','for','with','after','from','in','on','at','as','is','are','has','have','nfl','star','qb','player','latest','news','football','says','report','update','updates','new','nach','bei','von','der','die','das','und','mit','sich','erstes','schwer','verletztem','verletzung','profi','meldet'}

def topic_tokens(a):
    title = str(a.get('title') or '').lower()
    return {t for t in re.findall(r'[a-zA-Zäöüß]{4,}', title) if t not in STOP}

def same_story(a, b):
    ta, tb = topic_tokens(a), topic_tokens(b)
    common = ta & tb
    # Konservativ: mindestens zwei aussagekräftige gemeinsame Wörter.
    return len(common) >= 2 and len(common) / max(1, min(len(ta), len(tb))) >= .60

def score(a):
    title = str(a.get('title') or '')
    age = age_hours(a.get('published'))
    category, pattern, base = next(
        ((name, regex, points) for name, regex, points in CATEGORIES
         if re.search(regex, title, re.I)),
        ('Sonstige Nachricht', '', 0)
    )
    # Die Einstufung ist exklusiv: 'cheap shot' ist kein Sieg,
    # 'score predictions' kein Spielergebnis, 'suspension' in Vorwürfen
    # keine bereits verhängte Strafe.
    freshness = (9 if age <= 12 else 7 if age <= 24 else 3 if age <= 36 else 0) if age is not None else 0
    points = base + freshness
    reasons = [f'{category} {base:+d}', f'Aktualität +{freshness}']
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
    # Basisfilter bleibt für beide Listen gleich; nur neue Auswahl hat Themenfilter und Cluster.
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
    new_candidates = [a for a in eligible if not EUROPE.search(str(a.get('title') or '') + ' ' + str(a.get('url') or ''))]
    new = []
    publishers_new = {}
    for a in sorted(new_candidates, key=lambda a: score(a)[0], reverse=True):
        pub = str(a.get('source') or 'Unbekannt')
        if publishers_new.get(pub, 0) >= 4 or any(same_story(a, b) for b in new):
            continue
        new.append(a)
        publishers_new[pub] = publishers_new.get(pub, 0) + 1
        if len(new) == 12:
            break
    lines = ['# THE HUDDLE – Themenvergleich 1.8.2', '',
             f'Prüfzeit Wien: {NOW.isoformat(timespec="minutes")}',
             'Nur Simulation, keine KI, keine Veröffentlichung.', 'Themengruppierung heuristisch: unklare Überschriften können weiterhin Dubletten ergeben.', '',
             f'Geeignete Quellen: {len(eligible)}', '',
             '## Bisherige Gewichtung (Simulation)', '']
    for i,a in enumerate(old,1):
        lines.append(f'{i}. {a.get("title", "")} — {old_score(a)} Punkte — {a.get("url", "")}')
    lines += ['', '## Neue Gewichtung 1.8.2 (Simulation)', '']
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
    print(f'THE HUDDLE 1.8.2: {OUT}; {len(eligible)} Kandidaten; keine Veröffentlichung')

if __name__ == '__main__':
    main()
