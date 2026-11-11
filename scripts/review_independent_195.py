#!/usr/bin/env python3
"""THE HUDDLE 1.9.5: unabhängige Prüfung der täglichen JSON-Vorschau.

Liest drafts/morning-preview.json, drafts/quellen-10.json und
 drafts/nfl-spiele-08.md. Schreibt Prüfberichte und ergänzt den Prüfstatus
 in drafts/morning-preview.json. Keine Veröffentlichung, kein Git-Push.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

D = Path('drafts')
DRAFT = D / 'morning-preview.json'
SOURCES = D / 'quellen-10.json'
GAMES = D / 'nfl-spiele-08.md'
OUT = D / 'gegenpruefung-195.md'
JSON_OUT = D / 'gegenpruefung-195.json'
MODEL = os.getenv('HUDDLE_REVIEW_MODEL', 'gpt-5-mini')
STATUSES = {'SPERREN', 'MANUELL_PRUEFEN', 'UNAUFFAELLIG'}


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def safe_preview_update(status, message, counts=None):
    if not DRAFT.is_file():
        return
    try:
        obj = json.loads(DRAFT.read_text(encoding='utf-8'))
        if not isinstance(obj, dict):
            return
        obj['status'] = 'draft'
        obj['published_at'] = None
        obj['editorial_review'] = {
            'version': '1.9.5', 'status': status,
            'approved': False, 'message': message,
            'report': 'gegenpruefung-195.md',
            'checked_at_utc': datetime.now(timezone.utc).isoformat(),
            **(counts or {}),
        }
        write_json(DRAFT, obj)
    except (OSError, ValueError, TypeError) as exc:
        print(f'Warnung: Vorschau-Prüfstatus konnte nicht geschrieben werden: {exc}', file=sys.stderr)


def blocked(message):
    report = {'gesamtstatus': 'SPERREN', 'meldungen': [],
              'uebergreifend': [message], 'grenzen': ['Prüfung nicht vollständig.'],
              'metadaten': {'version': '1.9.5', 'modell': MODEL,
                            'zeit_utc': datetime.now(timezone.utc).isoformat(),
                            'freigabe': False, 'vollstaendig': False}}
    write_json(JSON_OUT, report)
    OUT.write_text('# THE HUDDLE – Gegenprüfung 1.9.5\n\n'
                   '**GESPERRT – KEINE FREIGABE**\n\n' + message + '\n', encoding='utf-8')
    safe_preview_update('SPERREN', message)
    print('GEGENPRÜFUNG GESPERRT: ' + message, file=sys.stderr)
    # Redaktionelle Sperre ist ein Bericht, kein technischer Workflow-Abbruch.
    return


def extract_text(data):
    return '\n'.join(part.get('text', '') for item in data.get('output', [])
                     for part in item.get('content', [])
                     if part.get('type') == 'output_text').strip()


def call_api(payload):
    request = urllib.request.Request(
        'https://api.openai.com/v1/responses',
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY'],
                 'Content-Type': 'application/json'}, method='POST')
    
    try:
        with urllib.request.urlopen(request, timeout=150) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')[:2000]
        raise ValueError(f'OpenAI API HTTP {exc.code}: {detail}') from exc



def collect_items(edition):
    items = []
    def add(kind, obj, index=None):
        if not isinstance(obj, dict):
            return
        title = str(obj.get('title') or kind)
        body = str(obj.get('summary') or obj.get('text') or '')
        url = str(obj.get('source_url') or '')
        item_id = kind if index is None else f'{kind}-{index}'
        items.append({'id': item_id, 'rubrik': kind, 'titel': title,
                      'text': body, 'source_url': url})
    add('LEAD', edition.get('lead'))
    for i, item in enumerate(edition.get('brief') or [], 1):
        add('BRIEF', item, i)
    for i, item in enumerate(edition.get('stories') or [], 1):
        add('STORY', item, i)
    add('AUSTRIAN_WATCH', edition.get('austria'))
    for i, item in enumerate(edition.get('game_center') or [], 1):
        if not isinstance(item, dict):
            continue
        items.append({'id': f'GAME-{i}', 'rubrik': 'GAME_CENTER',
                      'titel': str(item.get('matchup') or f'Spiel {i}'),
                      'text': str(item.get('status', '')) + ' | ' + str(item.get('date_label', '')),
                      'source_url': str(item.get('source_url') or '')})
    return items


def render_report(review, items, evidence_count, missing):
    lines = ['# THE HUDDLE – Unabhängige Gegenprüfung 1.9.5', '',
             '**KEINE VERÖFFENTLICHUNGSFREIGABE – menschliche Redaktion entscheidet.**', '',
             f'**Gesamtstatus:** {review["gesamtstatus"]}',
             f'**Erwartete Einträge:** {len(items)}',
             f'**Geprüfte Einträge:** {len(review.get("meldungen", []))}',
             f'**Abgeglichene Quellentexte:** {evidence_count}',
             f'**Prüfmodell:** {MODEL}', '']
    if missing:
        lines += ['## Nicht vollständig geprüft', ''] + [f'- {x}' for x in missing] + ['']
    lines += ['## Einzelprüfung', '']
    for item in review.get('meldungen', []):
        lines += [f'### {item.get("id", "?")} – {item.get("titel", "Ohne Titel")}', '',
                  f'**Status:** {item.get("status", "MANUELL_PRUEFEN")}', '']
        for claim in item.get('behauptungen', []):
            lines += [f'- **{claim.get("bewertung", "nicht belegt")}** – {claim.get("aussage", "")}',
                      f'  - Quelle: {claim.get("quelle", "")}',
                      f'  - Beleg: {claim.get("beleg", "") or "Keine eindeutige Belegstelle"}',
                      f'  - Hinweis: {claim.get("hinweis", "")}', '']
        if item.get('korrekturen'):
            lines += ['**Korrekturen:**'] + ['- ' + str(x) for x in item['korrekturen']] + ['']
    for title, key in [('Übergreifende Auffälligkeiten', 'uebergreifend'),
                       ('Grenzen', 'grenzen')]:
        lines += ['## ' + title, ''] + ['- ' + str(x) for x in review.get(key, [])] + ['']
    lines += ['---', 'Geprüft wurde nur gegen zugelieferte Quellentexte und ESPN-Daten.',
              'Eine unauffällige Prüfung ist keine redaktionelle Freigabe.']
    OUT.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    D.mkdir(parents=True, exist_ok=True)
    missing_files = [str(p) for p in (DRAFT, SOURCES, GAMES) if not p.is_file()]
    if missing_files:
        blocked('Pflichtdateien fehlen: ' + ', '.join(missing_files))
        return
    if not os.getenv('OPENAI_API_KEY'):
        blocked('OPENAI_API_KEY fehlt. Gegenprüfung nicht möglich.')
        return
    try:
        preview = json.loads(DRAFT.read_text(encoding='utf-8'))
        source_data = json.loads(SOURCES.read_text(encoding='utf-8'))
        games = GAMES.read_text(encoding='utf-8')
        edition = preview['edition']
        if not isinstance(edition, dict) or not isinstance(source_data.get('articles'), list):
            raise ValueError('Ungültige Vorschau oder Quellenstruktur')
        items = collect_items(edition)
        if not items or not any(x['id'] == 'LEAD' for x in items) or not any(x['rubrik'] == 'GAME_CENTER' for x in items):
            raise ValueError('Lead oder Game Center fehlt')
        if not games.strip():
            raise ValueError('ESPN-Rohdaten sind leer')
        articles = source_data['articles']
        # Quellen nach Verwendung im JSON sammeln. Für alle Nachrichten mit fehlendem
        # Quellentext muss die Prüfung ausdrücklich eine Evidenzlücke markieren.
        requested_urls = {x['source_url'].rstrip('.,') for x in items
                          if x['rubrik'] != 'GAME_CENTER' and x['source_url']}
        evidence = []
        for article in articles:
            if not isinstance(article, dict):
                continue
            url = str(article.get('url') or '').rstrip('.,')
            if url in requested_urls:
                evidence.append({k: article.get(k, '') for k in
                                 ('title', 'source', 'url', 'published', 'text')})
        # Nicht stillschweigend nur die ersten zwölf Quellen überprüfen.
        # Bei zu vielen Quellen bleibt die Ausgabe gesperrt, bis der Umfang
        # in einer späteren Version kontrolliert aufgeteilt werden kann.
        if len(evidence) > 12:
            blocked(f'{len(evidence)} Quellentexte erforderlich, aber höchstens 12 je Prüfung vorgesehen. Keine unvollständige Prüfung.')
            return
        for article in evidence:
            article['text'] = str(article.get('text') or '')[:15000]
        evidence_urls = {str(x['url']).rstrip('.,') for x in evidence}
        without_evidence = [x['id'] for x in items if x['rubrik'] != 'GAME_CENTER'
                            and x['source_url'].rstrip('.,') not in evidence_urls]
        instructions = '''Du bist ein unabhängiger, skeptischer NFL-Faktenredakteur. Prüfe
AUSSCHLIESSLICH die gelieferten Quellentexte und ESPN-Spielzeilen, kein Weltwissen.
Prüfe JEDEN Eintrag aus "meldungen" separat, auch ALLE Game-Center-Spiele.
Übernimm für jeden Eintrag seine id EXAKT. Keine id auslassen oder doppelt verwenden.
Prüfe Namen, Teams, Datum, Ergebnis, Verletzungen, Trades, Status, Zitate,
Quellenattribution und ob ältere Ereignisse als aktuelle Nachricht ausgegeben werden.
AKTUALITÄTSPRÜFUNG:
Vergleiche für jede Nachricht drei Zeitpunkte:
1. Ausgabedatum des Morgenjournals.
2. Veröffentlichungsdatum der Quelle, sofern vorhanden.
3. Datum des beschriebenen Ereignisses, sofern erkennbar.
Ein aktuelles Veröffentlichungsdatum beweist nicht, dass das Ereignis aktuell ist.
Prüfe, ob die Nachricht eine neue Entwicklung enthält oder nur ein älteres
Ereignis wiederholt. Kennzeichne veraltete Meldungen und empfehle eine
aktuelle Einordnung oder den Austausch der Geschichte.
Fehlen Ereignisdatum oder ausreichende Angaben, markiere die Aktualität
als nicht überprüfbar. Erfinde keine Datumsangaben.
Eine ältere Meldung ist nicht automatisch falsch.
SPERREN nur bei schwerwiegender irreführender Aktualitätsdarstellung,
sonst MANUELL_PRUEFEN und eine konkrete Korrekturempfehlung.
Unterscheide Quellenbehauptung von unabhängig bestätigter Wahrheit.
Wenn Quellentext fehlt: "nicht belegt"; keine erfundenen Belegstellen.
Game-Center-Angaben ausschließlich mit beigefügten ESPN-Zeilen vergleichen.
Ein bloßer Link ist kein Beleg. Bei Widersprüchen oder schwerwiegenden ungestützten
Behauptungen SPERREN, bei offenen Fragen MANUELL_PRUEFEN.
Gib ausschließlich gültiges JSON zurück:
{"gesamtstatus":"SPERREN|MANUELL_PRUEFEN|UNAUFFAELLIG",
"meldungen":[{"id":"EXAKTE ID","titel":"...","status":"SPERREN|MANUELL_PRUEFEN|UNAUFFAELLIG",
"behauptungen":[{"aussage":"...","bewertung":"belegt|teilweise belegt|nicht belegt|widersprochen",
"quelle":"URL oder ESPN","beleg":"kurze genaue Textstelle oder leer","hinweis":"..."}],
"korrekturen":["..."]}],"uebergreifend":["..."],"grenzen":["..."]}.
Keine Veröffentlichung oder Freigabe.
Prüfe sämtliche konkreten Tatsachenbehauptungen einer Meldung, insbesondere
Zahlen, Namen, Teamwechsel, Verletzungen und personelle Konsequenzen.
Fasse zusammengehörige Aussagen zusammen, aber lasse keine überprüfbare
Tatsachenbehauptung ungeprüft. Halte die Begründungen kurz.'''
        payload = {'model': MODEL, 'instructions': instructions,
                   'input': 'Antworte ausschließlich mit einem gültigen JSON-Objekt.\n' + json.dumps({
                       'meldungen': items, 'quellen': evidence,
                       'espn_rohdaten': games,
                       'ausgabe_datum': edition.get('date')
                   }, ensure_ascii=False),

                   'max_output_tokens': 16000, 'store': False,
                   'text': {'format': {'type': 'json_object'}}}
        review = None
        for attempt in (1, 2):
            try:
                result = call_api(payload)
                if result.get('status') == 'incomplete':
                    raise ValueError('KI-Antwort unvollständig')
                review = json.loads(extract_text(result))
                break
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
                if attempt == 2:
                    blocked(f'KI-Gegenprüfung fehlgeschlagen: {type(exc).__name__}: {str(exc)[:250]}')
                    return
                payload['instructions'] += '\nAntworte noch knapper, aber prüfe alle IDs.'
        if not isinstance(review, dict) or not isinstance(review.get('meldungen'), list):
            blocked('KI-Bericht hat keine gültige Meldungsliste.')
            return
        expected = {x['id'] for x in items}
        seen = [x.get('id') for x in review['meldungen'] if isinstance(x, dict)]
        missing = sorted(expected - set(seen))
        extra = sorted(set(seen) - expected, key=str)
        duplicate = sorted({x for x in seen if seen.count(x) > 1}, key=str)
        invalid = [x.get('id') if isinstance(x, dict) else '(kein Objekt)' for x in review['meldungen']
                   if not isinstance(x, dict) or x.get('status') not in STATUSES
                   or not isinstance(x.get('behauptungen'), list) or not x['behauptungen']]
        gaps = ([f'Fehlende IDs: {missing}'] if missing else []) + \
               ([f'Unerwartete IDs: {extra}'] if extra else []) + \
               ([f'Doppelte IDs: {duplicate}'] if duplicate else []) + \
               ([f'Unvollständig bewertete IDs: {invalid}'] if invalid else []) + \
               ([f'Quellentext fehlt für: {without_evidence}'] if without_evidence else [])
        if review.get('gesamtstatus') not in STATUSES:
            gaps.append('Ungültiger KI-Gesamtstatus')
        statuses = [x.get('status') for x in review['meldungen'] if isinstance(x, dict)]
        if gaps or 'SPERREN' in statuses or review.get('gesamtstatus') == 'SPERREN':
            final = 'SPERREN'
        elif 'MANUELL_PRUEFEN' in statuses or review.get('gesamtstatus') == 'MANUELL_PRUEFEN':
            final = 'MANUELL_PRUEFEN'
        else:
            final = 'UNAUFFAELLIG'
        review['gesamtstatus'] = final
        review.setdefault('uebergreifend', [])
        review.setdefault('grenzen', [])
        review['uebergreifend'] += gaps
        review['metadaten'] = {'version': '1.9.5', 'modell': MODEL,
                              'zeit_utc': datetime.now(timezone.utc).isoformat(),
                              'quellen_abgeglichen': len(evidence),
                              'eintraege_erwartet': len(items),
                              'eintraege_geprueft': len(seen),
                              'vollstaendig': not gaps,
                              'freigabe': False}
        write_json(JSON_OUT, review)
        render_report(review, items, len(evidence), gaps)
        safe_preview_update(final, 'Unabhängige Prüfung abgeschlossen; keine Veröffentlichungsfreigabe.',
                            {'items_expected': len(items), 'items_checked': len(seen)})
        print(f'Gegenprüfung 1.9.5: {final}; {len(seen)}/{len(items)} Einträge; NICHT veröffentlicht')
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        blocked(f'Prüfung konnte nicht vollständig durchgeführt werden: {type(exc).__name__}: {str(exc)[:250]}')


if __name__ == '__main__':
    main()
