#!/usr/bin/env python3
"""THE HUDDLE – Qualitätsprüfung der unveröffentlichten Testvorschau.

Strukturfehler stoppen den Workflow. Inhaltliche Unsicherheiten erzeugen
Warnungen und verlangen weiterhin eine manuelle Quellenprüfung.
"""
import json
import re
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse

FILE = Path('drafts/morning-preview.json')
warnings = []


def fail(message):
    raise SystemExit('QUALITAETSPRUEFUNG FEHLGESCHLAGEN: ' + message)


def warn(message):
    warnings.append(message)
    print('REDAKTIONELL PRUEFEN: ' + message)


def source_url(item, label):
    url = str(item.get('source_url') or '').strip()
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.netloc:
        fail(f'{label}: Quellenlink fehlt oder ist ungueltig')
    return parsed.netloc


def complete_text(body, label, min_length=50, max_length=1500):
    if not min_length <= len(body) <= max_length:
        fail(f'{label}: ungueltige Textlaenge ({len(body)})')
    if re.search(r'(?:\.{3}|…)\s*$', body):
        fail(f'{label}: Text endet mit Auslassungspunkten')
    if body.endswith((',', ';', ':')):
        fail(f'{label}: Satz unvollstaendig')
    if not re.search(r'''[.!?]["”']?(?:\s*\(Quelle:\s*https://[^)\s]+\))?\s*(?:\[Q\d{2}\])?$''', body):
        fail(f'{label}: kein vollstaendiger Schlusssatz')


def check_item(item, number, kind):
    if not isinstance(item, dict):
        fail(f'{kind} {number}: ungueltiges Format')
    label = f'{kind} {number}'
    body = str(item.get('text') if kind == 'Brief' else item.get('summary') or '').strip()
    complete_text(body, label)
    domain = source_url(item, label)
    title = str(item.get('title') or '').strip()
    if kind == 'Story':
        if not 15 <= len(title) <= 110:
            fail(f'{label}: schlechte Titel-Laenge ({len(title)})')
        if title.endswith(('…', '...', ',', ';', ':')):
            fail(f'{label}: abgeschnittene Ueberschrift')
    if title and ('redaktionell prüfen' in title.lower() or 'redaktionell pruefen' in title.lower()):
        fail(f'{label}: Platzhalter-Ueberschrift')
    print(f'OK: {label} – {domain}')


if not FILE.is_file():
    fail('Vorschau-JSON fehlt.')
try:
    data = json.loads(FILE.read_text(encoding='utf-8'))
except (ValueError, OSError) as exc:
    fail(f'JSON nicht lesbar: {exc}')
if data.get('status') != 'draft':
    fail('Ausgabe ist nicht als Entwurf gekennzeichnet.')
edition = data.get('edition')
if not isinstance(edition, dict):
    fail('Ausgabedaten fehlen.')
brief, stories = edition.get('brief', []), edition.get('stories', [])
if not isinstance(brief, list) or not isinstance(stories, list):
    fail('Meldungen haben ein ungueltiges Format.')
print(f'Morning Brief: {len(brief)} Meldungen')
print(f'Top Stories: {len(stories)} Meldungen')
if not 3 <= len(brief) <= 5:
    fail(f'Unzulaessige Anzahl Kurzmeldungen: {len(brief)}')
if not 2 <= len(stories) <= 8:
    fail(f'Unzulaessige Anzahl Top Stories: {len(stories)}')
if len(brief) < 5:
    print('HINWEIS: Weniger als fuenf Kurzmeldungen; im Test erlaubt.')
for n, item in enumerate(brief, 1):
    check_item(item, n, 'Brief')
for n, item in enumerate(stories, 1):
    check_item(item, n, 'Story')

# Lead und Austrian Watch waren bisher nicht Teil dieser strukturellen Prüfung.
lead = edition.get('lead')
if not isinstance(lead, dict):
    fail('THE LEAD fehlt oder hat ein ungueltiges Format.')
complete_text(str(lead.get('summary') or '').strip(), 'THE LEAD', 65, 5000)
source_url(lead, 'THE LEAD')
if not str(lead.get('title') or '').strip():
    fail('THE LEAD: Ueberschrift fehlt.')
if 'redaktionell prüfen' in str(lead.get('title') or '').lower():
    fail('THE LEAD: Platzhalter-Ueberschrift')
print('OK: THE LEAD')
austria = edition.get('austria')
if austria is None:
    warn('Austrian Watch ohne Meldung; prüfen, ob relevante österreichische Nachrichten vorliegen.')
elif not isinstance(austria, dict):
    fail('Austrian Watch: ungueltiges Format')
else:
    complete_text(str(austria.get('text') or '').strip(), 'Austrian Watch', 50, 2500)
    source_url(austria, 'Austrian Watch')
    print('OK: Austrian Watch')

for kind, items, field in (('Brief', brief, 'text'), ('Story', stories, 'summary')):
    seen = set()
    for item in items:
        normalized = re.sub(r'\W+', '', str(item.get(field, '')).lower())
        if normalized in seen:
            fail(f'Doppelte Meldung in {kind}')
        seen.add(normalized)

date = str(edition.get('date') or '').strip()
if not date:
    fail('Ausgabedatum fehlt.')
try:
    edition_date = datetime.fromisoformat(date.replace('Z', '+00:00'))
except ValueError:
    edition_date = None
    warn('Ausgabedatum ist nicht im ISO-Format.')

confirmed = re.compile(r'\b(?:finalisiert|abgeschlossen|perfekt|offiziell|bestätigt|fixiert|unterschrieben)\b', re.I)
pending = re.compile(r'\b(?:verhandelt|verhandeln|arbeitet|arbeiten|geplant|plant|soll|sollen|könnte|könnten|angeblich|berichten zufolge|noch nicht|steht bevor|vor Abschluss)\b', re.I)
transaction = re.compile(r'\b(?:trade|transfer|wechsel|vertrag|verpflichtung)\b', re.I)
relative_time = re.compile(r'\b(?:heute|morgen|gestern|heute Abend|morgen Abend|am kommenden Wochenende)\b', re.I)
for number, item in enumerate(stories, 1):
    title, summary = str(item.get('title', '')), str(item.get('summary', ''))
    if transaction.search(title) and confirmed.search(title) and pending.search(summary):
        warn(f'Story {number}: Titel meldet moeglicherweise vollzogene Transaktion, Text enthaelt Vorbehalte.')
for kind, items, field in (('Brief', brief, 'text'), ('Story', stories, 'summary')):
    for number, item in enumerate(items, 1):
        if relative_time.search(str(item.get(field, ''))):
            warn(f'{kind} {number}: relativer Zeitbezug; Ausgabezeit und Quellenzeit abgleichen.')

def similarity(a, b):
    def normalize(s):
        return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', s.lower())).strip()
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()

for kind, items, field in (('Brief', brief, 'text'), ('Story', stories, 'summary')):
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if similarity(str(items[i].get(field, '')), str(items[j].get(field, ''))) >= 0.86:
                warn(f'{kind} {i+1} und {j+1}: sehr aehnliche Texte; auf Dopplung pruefen.')

# Spielvollständigkeit ist ohne externen NFL-Spielplan nicht beweisbar.
games = edition.get('game_center')
if not isinstance(games, list) or not games:
    fail('Game Center fehlt oder enthaelt keine Spiele.')
seen_game_urls = set()
for n, game in enumerate(games, 1):
    if not isinstance(game, dict):
        fail(f'Game Center {n}: ungueltiges Format')
    source_url(game, f'Game Center {n}')
    url = game['source_url']
    if url in seen_game_urls:
        fail(f'Game Center {n}: doppelte Spielquelle')
    seen_game_urls.add(url)
    if not str(game.get('matchup') or '').strip():
        fail(f'Game Center {n}: Spielpaarung fehlt')
    if str(game.get('status') or '') not in ('ENDE', 'LIVE', 'NOCH NICHT BEENDET'):
        warn(f'Game Center {n}: unbekannter Spielstatus')
print(f'Game Center: {len(games)} Spiele mit eindeutigen Quellen')
if edition_date and edition_date.weekday() == 1:  # Dienstag
    warn('Dienstagsausgabe: Monday Night Game gegen aktuellen NFL-Spielplan und ESPN-Daten abgleichen; aus Spielanzahl allein nicht feststellbar.')
if len(games) < 13:
    warn(f'Game Center: nur {len(games)} Spiele; Vollstaendigkeit gegen NFL-Spielplan pruefen.')

print('')
print('QUALITAETSPRUEFUNG BESTANDEN.')
print('Status: unveroeffentlichte Testvorschau.')
print(f'Redaktionelle Warnungen: {len(warnings)}')
print('Hinweis: Kein journalistischer Faktencheck; keine automatische Freigabe.')
