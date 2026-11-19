#!/usr/bin/env python3
"""One-run editorial draft. Consumes freshly collected local files; no GitHub artifact chain."""
import json
import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from openai import OpenAI

ROOT = Path('drafts')
NOW = datetime.now(timezone.utc)
MODEL = os.getenv('HUDDLE_EDITORIAL_MODEL', 'gpt-5-mini')


def published(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)
    except (ValueError, AttributeError):
        try:
            return parsedate_to_datetime(value).astimezone(timezone.utc)
        except (ValueError, TypeError, IndexError):
            return None


def current_austrian_status():
    """Best-effort current ESPN team injury report, never infer from old articles."""
    import requests
    url = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/ind/injuries'
    try:
        response = requests.get(url, timeout=12, headers={'User-Agent': 'THE HUDDLE editorial research/1.0'})
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        print(f'INFO: ESPN Injury Report nicht erreichbar: {exc}')
        return []
    results = []
    def scan(node, depth=0):
        if depth > 12:
            return
        if isinstance(node, list):
            for child in node:
                scan(child, depth+1)
        elif isinstance(node, dict):
            blob = json.dumps(node, ensure_ascii=False)
            # Match a single player entry, not a parent object containing the entire roster.
            athlete = node.get('athlete') or node.get('player') or {}
            if isinstance(athlete, dict):
                name = athlete.get('displayName') or athlete.get('fullName') or athlete.get('name') or ''
            else:
                name = str(athlete)
            if name == 'Bernhard Raimann':
                status = node.get('status') or node.get('type') or node.get('gameStatus') or ''
                if isinstance(status, dict):
                    status = status.get('description') or status.get('displayName') or status.get('name') or ''
                if status:
                    results.append({'player': name, 'reported_status': str(status), 'source': url,
                                    'retrieved_utc': NOW.isoformat(),
                                    'caution': 'ESPN-Teamverletzungsseite; Spielbezug und Aktualität vor Veröffentlichung prüfen.'})
            for child in node.values():
                if isinstance(child, (dict, list)):
                    scan(child, depth+1)
    scan(payload)
    return results[:3]


def verified_one_game_update():
    """Explicit official team announcement; only relevant before this specific kickoff."""
    cutoff = datetime(2026, 11, 20, 1, 15, tzinfo=timezone.utc)
    earliest = datetime(2026, 11, 18, 18, 30, tzinfo=timezone.utc)
    if not earliest <= NOW < cutoff:
        return []
    url = 'https://www.colts.com/news/colts-rule-out-5-players-for-week-11-thursday-night-football-game-vs-houston-texans'
    import requests
    try:
        r = requests.get(url, timeout=12, headers={'User-Agent': 'Mozilla/5.0'})
        r.raise_for_status()
        page = re.sub(r'<[^>]*>', ' ', r.text)
        page = re.sub(r'\s+', ' ', page)
        if not re.search(r'ruled out.{0,260}Bernhard Raimann|Bernhard Raimann.{0,100}concussion', page, re.I):
            return []
        return [{'player': 'Bernhard Raimann', 'game': 'Indianapolis Colts @ Houston Texans, 19.11.2026',
                 'status': 'OUT (spielt nicht)', 'announced': '18.11.2026',
                 'source': url, 'authority': 'Offizielle Indianapolis Colts',
                 'note': 'Diese Meldung betrifft ausschließlich das Spiel am 19.11.2026.'}]
    except requests.RequestException as exc:
        print(f'INFO: Colts-Originalmeldung nicht abrufbar: {exc}')
        return []


def main():
    raw = json.loads((ROOT / 'quellen-10.json').read_text(encoding='utf-8'))
    articles = []
    seen = set()
    for item in raw.get('articles', []):
        stamp = published(item.get('published'))
        is_austrian = bool(re.search(r'\b(?:Bernhard\s+Raimann|Valentin\s+Senn)\b', (item.get('title', '') + ' ' + item.get('text', ''))[:6500], re.I))
        max_age = timedelta(days=7) if is_austrian else timedelta(hours=72)
        if stamp is None or not NOW - max_age <= stamp <= NOW + timedelta(hours=2):
            continue
        title = item.get('title', '').strip()
        url = item.get('url', '')
        body = item.get('text', '').strip()
        if not title or not url.startswith('https://') or len(body.split()) < 120:
            continue
        if re.search(r'\b(?:Immobilie|Wohnung|Wohnfläche|Nutzfläche|Maisonette|Grundstück|m²)\b', title + ' ' + body[:500], re.I):
            continue
        key = re.sub(r'[^\w]', '', title.casefold())
        if key in seen:
            continue
        seen.add(key)
        articles.append({
            'source': item.get('source'), 'title': title, 'url': url,
            'published_utc': stamp.isoformat(), 'text': body[:3400],
            'austrian_watch': is_austrian
        })
    # Relevance first, rather than blindly passing the newest 18 items.
    # Reserve Austrian coverage, but avoid passing multiple near-identical
    # reports about the same player and event.
    def relevance(item):
        t = item['title'].lower()
        source = (item.get('source') or '').lower()
        score = 0
        if item['austrian_watch']: score += 35
        if any(w in t for w in ('injury', 'injured', 'concussion', 'out for', 'ruled out', 'inactive', 'verletzt', 'gehirnerschütterung', 'fällt aus', 'ausfall')): score += 16
        if any(w in t for w in ('texans', 'colts', 'thursday night', 'preview', 'vorschau', 'week 11')): score += 10
        if any(w in t for w in ('trade', 'signed', 'fired', 'suspended', 'release', 'entlassen', 'vertrag')): score += 9
        if any(w in t for w in ('power ranking', 'rankings', 'picks', 'predictions', 'hot seat', 'radio show', 'kicker')): score -= 14
        if 'nfl.com' in item['url'] or 'espn.com' in item['url']: score += 5
        if 'football-austria.com' in item['url']: score += 4
        age_h = max(0, (NOW - datetime.fromisoformat(item['published_utc'])).total_seconds()/3600)
        score -= min(age_h/24, 7)
        return score

    articles.sort(key=lambda a: (relevance(a), a['published_utc']), reverse=True)
    selected, counts = [], {}
    def add(item):
        src = item['source'] or 'Unbekannt'
        if item in selected or counts.get(src, 0) >= 4 or len(selected) >= 18:
            return
        selected.append(item)
        counts[src] = counts.get(src, 0) + 1
    # Only two distinct Austrian-player source reports in the prompt;
    # additional sources remain in the collected JSON for later verification.
    for item in articles:
        if item['austrian_watch']:
            add(item)
            if sum(a['austrian_watch'] for a in selected) >= 2:
                break
    for item in articles:
        add(item)
        if len(selected) >= 18:
            break
    if not selected:
        raise RuntimeError('Keine aktuellen, ausreichend belegten NFL-Artikel gesammelt. Keine KI-Ausgabe erzeugt.')

    game_center = (ROOT / 'nfl-spiele-08.md').read_text(encoding='utf-8')
    # Game Center is deterministic ESPN output; AI may only reproduce it, not fill gaps.
    # Older injury reports cannot establish the next game's current status.
    austrian_latest = max((datetime.fromisoformat(a['published_utc']) for a in selected if a['austrian_watch']), default=None)
    status_note = ('Die neueste österreichische Quelle ist älter als 24 Stunden. '
                   'Sie belegt keinen aktuellen Status für das nächste Spiel. '
                   'Als offenen Recherchepunkt kennzeichnen; keine Vermutung über Einsatzfähigkeit.') if austrian_latest and NOW - austrian_latest > timedelta(hours=24) else ''
    status_updates = verified_one_game_update() + current_austrian_status()
    context = {
        'stand_wien': NOW.astimezone(ZoneInfo('Europe/Vienna')).strftime('%d.%m.%Y %H:%M'),
        'articles': selected,
        'austrian_status_editorial_note': status_note if not status_updates else '',
        'verified_status_updates': status_updates,
        'game_center_espn': game_center[:23000],
    }
    instructions = '''Du bist die Schlussredaktion von THE HUDDLE, dem deutschsprachigen NFL-Morgenjournal von Football-Austria.com. Erstelle einen journalistisch gewichteten Markdown-ENTWURF, keine Veröffentlichung.

VERBINDLICHE REDAKTIONSREGELN:
0. PRIORITÄT: 'verified_status_updates' enthält zusätzliche zeitlich begrenzte, ausdrücklich belegte Statusinformationen. Falls eine offizielle Teammitteilung für ein bestimmtes Spiel OUT bestätigt, muss Austrian Watch das nennen und direkt verlinken. Ältere Artikel dürfen dem nicht widersprechen. Gilt ausschließlich für das bezeichnete Spiel, niemals als allgemeiner Gesundheitszustand. Bei fehlenden Updates keine neue Sicherheit behaupten.
1. Der Zeitstempel "stand_wien" ist der Zeitpunkt des Entwurfs, NICHT das Erscheinungsdatum einer Quelle. Keine alten Meldungen als neu ausgeben. Bei medizinischen Statusmeldungen ausschließlich den letzten ausdrücklich belegten Status nennen, mit Datum der Quelle. Aus "fraglich" niemals "OUT" oder umgekehrt ableiten. Wenn Quellen widersprüchlich oder veraltet sind: "Ein aktueller Einsatzstatus ist aus den vorliegenden Quellen nicht gesichert." Niemals behaupten, die Situation sei noch offen, wenn die Quelle das nur zu einem früheren Zeitpunkt sagt.
2. Nachrichtenwert priorisieren: echte aktuelle Entwicklungen, Spielausgänge, Verletzungen, Kaderentscheidungen, unmittelbar bevorstehende Spiele. Meinungsrankings, Rekordvorschauen und TV-Kommentatoren-Streit nur bei tatsächlich dünner Nachrichtenlage. Keine Top Story aus einer einzelnen nackten Score-Zeile machen, wenn die Quellen keine zusätzliche Geschichte hergeben.
3. Deduplizieren: Dasselbe Ereignis ist genau EINE ausführliche Geschichte. Ein mehrere Tage alter Verletzungsbericht ohne neues Update gehört in Austrian Watch, nicht als aktuelle Top Story. Eine knappe Erwähnung im 60-Sekunden-Überblick ist erlaubt; wenn Raimann Top Story ist, darf Austrian Watch nur ein kurzes, ergänzendes Status-/Termin-Update mit Verweis auf die Top Story enthalten (max. 45 Wörter), keine zweite Nacherzählung.
4. Quellenhierarchie: NFL-/Team-Originalmeldung vor Sekundärquelle, wenn beide vorhanden. Ein Artikel kann mehrere Quellen haben. Belege immer direkt verlinken. Keine Aussagen über aktuellere Statusänderungen, wenn diese NICHT im übergebenen Material enthalten sind.
5. Die ESPN-Daten im Feld game_center_espn sind autoritativ für den Game Center dieses Entwurfs. Den Game Center NICHT durch freie KI-Auswahl verkürzen. Kopiere alle darin enthaltenen Spiele und Uhrzeiten vollständig und unverändert, sofern sie im Text stehen. Endstände nur für ENDE, geplante Spiele als GEPLANT. Keine erfundenen Ergebnisse oder Spieltermine.
6. Außergewöhnliche historische Aussagen (z.B. 'erster Saisonsieg seit Dezember 2025') nur bei Beleg durch mehrere unabhängige Quellen oder eindeutige Spielhistorie; sonst neutral nur das Ergebnis nennen.
7. Widersprüchliche Week-Nummern, Termine oder Rekorde nicht ungeprüft behaupten. Wenn ein Datum und die behauptete Week-Nummer nicht zusammenpassen, die Week-Nummer weglassen. Keine falsche Sicherheit.

AUSGABESTRUKTUR:
# THE HUDDLE – [Datum aus stand_wien]
## Die NFL in 60 Sekunden (ca. 90–125 Wörter; wichtigste Meldung zuerst, mit kurzem Ausblick)
## Top Stories (2–4 eigenständige Geschichten, jeweils ca. 75–115 Wörter, Titel und direkte Quellenlinks; nicht künstlich auffüllen)
## Austrian Watch (kurzes, eigenständiges Update zu österreichischen NFL-Spielern, wenn belegt; alte Statusangaben datieren; keine Dublette)
## Game Center (hier nur [GAME_CENTER_WIRD_AUTOMATISCH_EINGEFUEGT] schreiben; der Abschnitt wird nachträglich mit den ESPN-Originaldaten befüllt)
## Quellen und Redaktionshinweise (maximal fünf Sätze, nur konkrete offene Punkte)
Am Ende exakt: ENTWURF – journalistische Prüfung und Freigabe ausständig.
Schreibe nur aus übergebenen Quellen. Keine erfundenen Zitate, Verletzungsfolgen, Statistiken, Spielstände oder Links. Bei wenig Material lieber kurz.'''
    client = OpenAI(api_key=os.environ['OPENAI_API_KEY'], timeout=120, max_retries=1)
    response = client.responses.create(
        model=MODEL, instructions=instructions,
        input=json.dumps(context, ensure_ascii=False),
        max_output_tokens=6500, store=False,
    )
    draft = (response.output_text or '').strip()
    if response.status != 'completed' or len(draft) < 600:
        raise RuntimeError(f'KI-Entwurf nicht vollständig: {response.status}; {len(draft)} Zeichen')
    # Never let the language model invent, omit or rewrite game scores.
    if '## Game Center' in draft:
        head, tail = draft.split('## Game Center', 1)
        next_heading = re.search(r'(?m)^## Quellen und Redaktionshinweise', tail)
        remainder = tail[next_heading.start():] if next_heading else ''
        draft = head.rstrip() + '\n\n## Game Center\n\n' + game_center.strip() + '\n\n' + remainder.lstrip()
    else:
        draft += '\n\n## Game Center\n\n' + game_center.strip()
    draft = draft.replace('[GAME_CENTER_WIRD_AUTOMATISCH_EINGEFUEGT]', '')
    if 'ENTWURF' not in draft:
        draft += '\n\n**ENTWURF – journalistische Prüfung und Freigabe ausständig.**'
    ROOT.mkdir(exist_ok=True)
    (ROOT / 'the-huddle-erstausgabe.md').write_text(draft + '\n', encoding='utf-8')
    meta = {
        'generated_utc': NOW.isoformat(), 'model': MODEL,
        'sources_eligible': len(articles), 'austrian_candidates': sum(a['austrian_watch'] for a in articles), 'sources_passed_to_model': len(selected),
        'source_urls': [a['url'] for a in selected],
        'response_status': response.status,
        'verified_status_updates': status_updates,
        'approved': False, 'published': False,
        'input_tokens': getattr(response.usage, 'input_tokens', None),
        'output_tokens': getattr(response.usage, 'output_tokens', None),
    }
    (ROOT / 'the-huddle-erstausgabe-meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Entwurf erzeugt: {len(selected)} aktuelle Quellen, {len(draft)} Zeichen, Modell {MODEL}')


if __name__ == '__main__':
    main()
