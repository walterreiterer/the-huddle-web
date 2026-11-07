"""THE HUDDLE 0.9: ESPN NFL Game Center, editorially safe statuses and Vienna dates."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

OUT = Path('drafts/nfl-spiele-08.md')  # Keep existing downstream workflow contract.
VIENNA = ZoneInfo('Europe/Vienna')
BASE = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates='


def event_time(event):
    try:
        return datetime.fromisoformat(event['date'].replace('Z', '+00:00')).astimezone(VIENNA)
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def format_event(event, source_url):
    competitions = event.get('competitions') or []
    competitors = competitions[0].get('competitors') or [] if competitions else []
    teams = {c.get('homeAway'): c for c in competitors if isinstance(c, dict)}
    if 'home' not in teams or 'away' not in teams:
        return None
    home, away = teams['home'], teams['away']
    hn = (home.get('team') or {}).get('displayName') or 'Heimteam unbekannt'
    an = (away.get('team') or {}).get('displayName') or 'Auswärtsteam unbekannt'
    status = (event.get('status') or {}).get('type') or {}
    state = status.get('state')
    name = str(status.get('name') or '').upper()
    label = status.get('description') or status.get('name') or 'Unbekannt'
    scores = (str(away.get('score', '')), str(home.get('score', '')))
    valid_scores = all(s.isdigit() for s in scores)
    when = event_time(event)
    start = when.strftime('%d.%m.%Y, %H:%M Uhr (Wien)') if when else 'unbekannt'
    event_id = str(event.get('id') or '')
    link = f'https://www.espn.com/nfl/game/_/gameId/{event_id}' if event_id.isdigit() else source_url
    if name in {'STATUS_CANCELED', 'STATUS_CANCELLED'} or 'cancel' in name.lower():
        detail = f'ABGESAGT: {an} bei {hn}'
    elif name in {'STATUS_POSTPONED'} or 'postpon' in name.lower():
        detail = f'VERSCHOBEN: {an} bei {hn}'
    elif status.get('completed') is True and valid_scores:
        detail = f'ENDE: {an} {scores[0]} – {scores[1]} {hn}'
    elif status.get('completed') is True:
        detail = f'ALS BEENDET MARKIERT, ERGEBNIS FEHLT: {an} bei {hn}'
    elif state == 'in':
        score_text = f'{an} {scores[0]} – {scores[1]} {hn}' if valid_scores else f'{an} bei {hn} (Spielstand fehlt)'
        detail = f'LIVE (KEIN Endergebnis): {score_text}'
    elif state == 'pre':
        detail = f'GEPLANT ({label}): {an} bei {hn}; Beginn: {start}'
    else:
        detail = f'STATUS UNGEKLÄRT ({label}): {an} bei {hn}; Beginn: {start}'
    return f'- {detail} | [ESPN-Spielseite]({link})'


def build(now=None, fetch=None):
    now = now or datetime.now(VIENNA)
    fetch = fetch or fetch_json
    local_days = {(now - timedelta(days=1)).date(), now.date()}
    # Query all UTC dates that can overlap the two Vienna calendar dates,
    # plus a safety day for ESPN's date bucketing.
    utc_days = sorted({(datetime.combine(d, datetime.min.time(), VIENNA).astimezone(timezone.utc) + timedelta(days=offset)).strftime('%Y%m%d')
                       for d in local_days for offset in (-1, 0, 1)})
    events = {}
    failures = []
    for day in utc_days:
        url = BASE + day
        try:
            payload = fetch(url)
            for event in payload.get('events', []):
                if not isinstance(event, dict):
                    continue
                eid = str(event.get('id') or '')
                if eid:
                    events[eid] = event
        except Exception as exc:
            failures.append(f'{day}: {type(exc).__name__}')
    lines = ['# THE HUDDLE – NFL Game Center (0.9)', '',
             f'Abrufzeit Wien: {now.isoformat(timespec="minutes")}', '',
             '> ESPN-Spielstandsdaten; vor Veröffentlichung gegenprüfen. Keine Ergebnisse ergänzen.', '']
    if failures:
        lines.extend(['**ACHTUNG: ESPN-Datenabruf teilweise oder vollständig fehlgeschlagen. Ergebnisse können unvollständig sein.**',
                      'Fehler: ' + '; '.join(failures), ''])
    for day in sorted(local_days):
        lines.extend([f'## Spieltag {day.strftime("%d.%m.%Y")} (Wien)', ''])
        selected = sorted((e for e in events.values() if (t := event_time(e)) and t.date() == day),
                          key=lambda e: event_time(e))
        rendered = [r for e in selected if (r := format_event(e, BASE + e['date'][:10].replace('-', '')))]
        if rendered:
            lines.extend(rendered)
        elif failures:
            lines.append('Keine Spiele aus den verfügbaren Daten bestätigt (Abruf unvollständig).')
        else:
            lines.append('Keine NFL-Spiele für dieses Wiener Datum in den ESPN-Daten gemeldet.')
        lines.append('')
    lines.extend(['Datenquelle: [ESPN NFL Scoreboard](https://www.espn.com/nfl/scoreboard)', ''])
    return '\n'.join(lines) + '\n'


def fetch_json(url):
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0 (TheHuddleEditorial/0.9)', 'Accept': 'application/json'})
    with urlopen(req, timeout=18) as response:
        return json.load(response)


if __name__ == '__main__':
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(), encoding='utf-8')
    print(f'Spielbericht erstellt: {OUT}')
