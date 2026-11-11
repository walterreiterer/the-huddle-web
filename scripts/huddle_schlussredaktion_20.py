#!/usr/bin/env python3
"""THE HUDDLE 2.0 – interne Schlussredaktion; niemals automatische Veröffentlichung."""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('drafts')
PREVIEW = ROOT / 'morning-preview.json'
REVIEW = ROOT / 'gegenpruefung-195.json'
OUTPUT = ROOT / 'leserfassung-20.md'
REPORT = ROOT / 'schlussredaktion-20.json'
MODEL = os.getenv('HUDDLE_EDITOR_MODEL', 'gpt-4.1-mini')


def save_report(status, reason, **extra):
    ROOT.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps({
        'version': '2.0', 'status': status, 'grund': reason,
        'freigabe': False, 'veroeffentlicht': False,
        'zeit_utc': datetime.now(timezone.utc).isoformat(), **extra
    }, ensure_ascii=False, indent=2), encoding='utf-8')


def fail(message):
    save_report('NICHT_ERSTELLT', message)
    print('SCHLUSSREDAKTION: ' + message, file=sys.stderr)
    return 1


def response_text(obj):
    chunks = []
    for item in obj.get('output', []):
        for part in item.get('content', []):
            if part.get('type') == 'output_text':
                chunks.append(part.get('text', ''))
    return ''.join(chunks)


def main():
    if not PREVIEW.is_file() or not REVIEW.is_file():
        return fail('Entwurf oder Gegenprüfung fehlt.')
    try:
        preview = json.loads(PREVIEW.read_text(encoding='utf-8'))
        review = json.loads(REVIEW.read_text(encoding='utf-8'))
        edition = preview['edition']
        entries = review['meldungen']
        if not isinstance(entries, list) or not entries or not review.get('metadaten', {}).get('vollstaendig'):
            return fail('Gegenprüfung ist unvollständig.')
        if review.get('gesamtstatus') not in ('UNAUFFAELLIG', 'MANUELL_PRUEFEN', 'SPERREN'):
            return fail('Ungültiger Gesamtstatus der Gegenprüfung.')
        if not os.getenv('OPENAI_API_KEY'):
            return fail('OPENAI_API_KEY fehlt.')

        instructions = '''Du bist die Schlussredaktion des deutschsprachigen NFL-Morgenjournals THE HUDDLE.
Erstelle eine gut lesbare, lebendige, aber sachliche INTERNE LESERFASSUNG aus dem gelieferten
Rechercheentwurf und dem unabhängigen Prüfbericht. Keine Ich-Form, keine Clickbait-Titel.
Die Zielgröße sind 650 bis 750 Wörter, soweit ausreichend geprüfter Stoff vorliegt.
Struktur: THE HUDDLE / Datum, 60-Sekunden-Brief (3–4 kurze Meldungen),
Top Stories (2–4, jeweils circa 80–120 Wörter), Austrian Watch nur bei echtem
aktuellem Nachrichtenwert, Game Center mit knappen Ergebnissen.
Priorisiere wichtige aktuelle Nachrichten, streiche Wiederholungen, entferne interne
Rubriken wie 'Belegte Fakten', 'Einschätzung' und 'Offene Fragen'.
Die Leserfassung darf keine internen Prüfhinweise, Warnlisten oder Arbeitsaufträge
enthalten; diese gehören ausschließlich in redaktionelle_hinweise.
AKTUALITÄT: Das Ausgabedatum ist der zeitliche Bezugspunkt. Prüfe beim Formulieren,
ob genannte Saisonbilanzen, Tabellenstände, Serien, Spielwochen, Ankündigungen und
Ausblicke zum Ausgabedatum passen. Eine ältere Quelle darf als Hintergrund dienen,
aber ein darin genannter früherer Zwischenstand darf nicht als aktueller Stand
übernommen werden. Wenn der aktuelle Stand aus den gelieferten Daten nicht sicher
hervorgeht, lasse die konkrete Zahl weg oder ordne sie eindeutig zeitlich ein.
WICHTIG: Ein alter Saisonstand wie 'aktuell 2:3' darf NICHT einfach aus einer
älteren Quelle in eine November-Ausgabe übernommen werden. Entferne den alten
Stand aus dem Lesertext, wenn keine aktuelle, zeitlich passende Zahl vorliegt.
Auch Formulierungen wie 'kommenden Sonntag' oder 'in Week 10' nur verwenden,
wenn sie relativ zum Ausgabedatum tatsächlich noch in der Zukunft liegen.
Keine neuen Ergebnisse, Datumsangaben oder Statistiken errechnen oder erfinden.
THEMENVIELFALT: Wähle unterschiedliche wichtige Entwicklungen aus dem gelieferten
Material. Bündle eng zusammenhängende Nachrichten zu Team, Spieler oder Trade
in einer Geschichte, statt mehrere Top Stories mit nahezu gleichem Kern zu schreiben.
Konkret: Wenn Lead und mehrere Top Stories denselben Trade, dieselbe QB-Situation
oder denselben Klub behandeln, fasse sie zu EINER Hauptgeschichte zusammen.
Fülle freie Plätze nur mit tatsächlich vorhandenen, eigenständigen Nachrichten;
notfalls sind zwei oder drei Top Stories besser als vier Wiederholungen.
Bevorzuge bei ähnlichem Nachrichtenwert verschiedene Teams und Themenfelder.
Eine besonders bedeutende Entwicklung darf trotzdem mehrere Aspekte erhalten,
wenn jeder einen eigenständigen Nachrichtenwert besitzt. Keine Themenvielfalt durch
erfundene oder unwichtige Meldungen erzwingen.
Bewahre Football-Fachbegriffe; schreibe natürliches Deutsch mit sportlicher Einordnung.
KEINE neuen Tatsachen, Statistiken, Spielstände, Zitate, Namen oder Quellen hinzufügen.
Nenne bei jeder Meldung ihre bereits vorhandene Quellen-URL. Nutze nur zugelieferte URLs.
Ein Prüfstatus MANUELL_PRUEFEN oder SPERREN ist keine Freigabe. Beanstandete
Tatsachenbehauptungen dürfen nicht als gesicherte Fakten erscheinen: lasse sie weg
oder markiere sie klar als ungeklärt. Veraltete Meldungen nicht als neu darstellen.
Bei schwerwiegenden Beanstandungen keine glatte Leserfassung vortäuschen;
benenne offene redaktionelle Entscheidungen im separaten Prüfhinweis.
VERBINDLICHER LETZTER REDAKTIONSDURCHGANG:
Prüfe die fertig geschriebene Leserfassung vor der Ausgabe erneut.
1. Kommen zwei Top Stories zum selben Trade oder zur selben
   Entwicklung vor? Dann führe sie zusammen und überarbeite
   die Leserfassung tatsächlich.
2. Enthält der Text Saisonbilanzen oder zeitliche Aussagen,
   deren Aktualität zum Ausgabedatum nicht belegt ist?
   Entferne diese Angaben direkt aus dem Lesertext.
3. Enthält die Leserfassung interne Prüfhinweise, Warnungen
   oder Arbeitsaufträge? Entferne sie aus dem Markdown und
   übertrage sie in redaktionelle_hinweise.
4. Prüfe, ob jede verbleibende Top Story einen eigenständigen
   Nachrichtenwert hat.
WICHTIG: Beschreibe erkannte Probleme nicht nur im Bericht.
Korrigiere zuerst den Markdown-Text. Melde in
redaktionelle_hinweise nur Probleme, die danach noch offen sind.
Antworte ausschließlich als JSON-Objekt mit Schlüsseln:
"markdown" (vollständige interne Leserfassung als Markdown),
"redaktionelle_hinweise" (Liste kurzer Hinweise),
"verwendete_quellen" (Liste der tatsächlich verwendeten Quell-URLs).
Niemals eine Veröffentlichung oder Freigabe behaupten.'''
        payload = {
            'model': MODEL,
            'instructions': instructions,
            'input': 'Erstelle ausschließlich ein gültiges JSON-Objekt.\n' + json.dumps({
                'ausgabe': edition,
                'gegenpruefung': review,
                'hinweis': 'Interner Entwurf; keine Veröffentlichung.'
            }, ensure_ascii=False),
            'max_output_tokens': 7000,
            'store': False,
            'text': {'format': {'type': 'json_object'}}
        }
        request = urllib.request.Request(
            'https://api.openai.com/v1/responses',
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY'],
                     'Content-Type': 'application/json'},
            method='POST'
        )
        try:
            with urllib.request.urlopen(request, timeout=100) as resp:
                raw = json.load(resp)
        except urllib.error.HTTPError as exc:
            return fail(f'API HTTP {exc.code}: {exc.read(600).decode("utf-8", errors="replace")}')
        if raw.get('status') == 'incomplete':
            return fail('API-Ausgabe unvollständig.')
        result = json.loads(response_text(raw))
        markdown = result.get('markdown')
        urls = result.get('verwendete_quellen')
        hints = result.get('redaktionelle_hinweise')
        if not isinstance(markdown, str) or len(markdown.strip()) < 500:
            return fail('Leserfassung fehlt oder ist zu kurz.')
        if not isinstance(urls, list) or not isinstance(hints, list):
            return fail('Quellenliste oder redaktionelle Hinweise fehlen.')
        allowed = set()
        for key in ('lead',):
            obj = edition.get(key)
            if isinstance(obj, dict) and obj.get('source_url'):
                allowed.add(obj['source_url'])
        for key in ('brief', 'stories', 'game_center'):
            for obj in edition.get(key, []):
                if isinstance(obj, dict) and obj.get('source_url'):
                    allowed.add(obj['source_url'])
        for key in ('austria', 'austrian_watch'):
            obj = edition.get(key)
            if isinstance(obj, dict) and obj.get('source_url'):
                allowed.add(obj['source_url'])
            elif isinstance(obj, list):
                allowed.update(x['source_url'] for x in obj if isinstance(x, dict) and x.get('source_url'))
        unknown = sorted({u for u in urls if not isinstance(u, str) or u not in allowed}, key=str)
        if unknown:
            return fail('Nicht zugelassene Quellen-URLs in Leserfassung: ' + repr(unknown[:4]))
        # No publishing step. Even a technically valid reader draft remains unapproved.
        count = len(re.findall(r'\b[\wÄÖÜäöüß]+\b', markdown))
        heading = ('> **INTERNE TESTFASSUNG – NICHT VERÖFFENTLICHEN**  \n'
                   f'> Gegenprüfung: **{review["gesamtstatus"]}** · Keine redaktionelle Freigabe.\n\n')
        # Hinweise bleiben ausschließlich im JSON-Bericht, nie in der Leserfassung.
        OUTPUT.write_text(heading + markdown.strip() + '\n', encoding='utf-8')
        save_report('ENTWURF_ERSTELLT', 'Nur intern, manuelle Freigabe erforderlich.',
                    wortzahl=count, gegenpruefung_status=review['gesamtstatus'],
                    hinweise=hints, quellen=urls)
        print(f'Schlussredaktion 2.0: interne Leserfassung erstellt ({count} Wörter), KEINE Freigabe')
        return 0
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, urllib.error.URLError) as exc:
        return fail(f'{type(exc).__name__}: {str(exc)[:300]}')


if __name__ == '__main__':
    sys.exit(main())
