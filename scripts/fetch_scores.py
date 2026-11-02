"""THE HUDDLE 0.8: NFL scoreboard from ESPN, with explicit statuses and source links."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

OUT = Path('drafts/nfl-spiele-08.md')
now = datetime.now(ZoneInfo('Europe/Vienna'))
# Two days in Vienna time cover overnight games, including the early-morning window.
dates = [(now - timedelta(days=i)).strftime('%Y%m%d') for i in (1, 0)]
lines = ['# THE HUDDLE – NFL Game Center (0.8)', '', f'Abrufzeit Wien: {now.isoformat(timespec="minutes")}', '',
         '> ESPN-Spielstandsdaten; vor Veröffentlichung bei Bedarf gegenprüfen. Keine Ergebnisse ergänzen.', '']
seen = set()
for day in dates:
    url = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=' + day
    try:
        req = Request(url, headers={'User-Agent': 'Mozilla/5.0 (TheHuddleEditorial/0.8)', 'Accept': 'application/json'})
        with urlopen(req, timeout=18) as response:
            payload = json.load(response)
    except Exception as exc:
        lines.extend([f'## {day}: Datenabruf fehlgeschlagen ({type(exc).__name__})', ''])
        continue
    lines.extend([f'## Spieltag {day}', '', f'Datenquelle: {url}', ''])
    count = 0
    for event in payload.get('events', []):
        event_id = str(event.get('id', ''))
        if event_id in seen:
            continue
        seen.add(event_id)
        competitions = event.get('competitions') or []
        if not competitions:
            continue
        competitors = competitions[0].get('competitors') or []
        teams = {c.get('homeAway'): c for c in competitors}
        if not all(k in teams for k in ('home', 'away')):
            continue
        home, away = teams['home'], teams['away']
        hn = home.get('team', {}).get('displayName') or home.get('team', {}).get('name') or 'Heimteam unbekannt'
        an = away.get('team', {}).get('displayName') or away.get('team', {}).get('name') or 'Auswärtsteam unbekannt'
        status = event.get('status', {}).get('type', {})
        label = status.get('description') or status.get('name') or 'Unbekannt'
        completed = status.get('completed') is True
        game_url = f'https://www.espn.com/nfl/game/_/gameId/{event_id}' if event_id else url
        if completed and str(home.get('score', '')).isdigit() and str(away.get('score', '')).isdigit():
            detail = f'ENDE: {an} {away["score"]} – {home["score"]} {hn}'
        elif status.get('state') == 'in':
            detail = f'LIVE (Zwischenstand, NICHT Endergebnis): {an} {away.get("score", "?")} – {home.get("score", "?")} {hn}'
        else:
            detail = f'NOCH NICHT BEENDET ({label}): {an} bei {hn}; Spielbeginn UTC: {event.get("date", "unbekannt")}'
        lines.extend([f'- {detail} | [ESPN-Spielseite]({game_url})'])
        count += 1
    if count == 0:
        lines.append('Keine NFL-Spiele für dieses Datum gemeldet.')
    lines.append('')
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text('\n'.join(lines) + '\n', encoding='utf-8')
print(f'Spielbericht erstellt: {OUT}; {len(seen)} unterschiedliche Spiele erfasst.')
