#!/usr/bin/env python3
"""THE HUDDLE – Markdown-Entwurf in unveröffentlichte JSON-Testvorschau umwandeln.

Aufruf: python scripts/convert_morning_14.py
Schreibt ausschließlich drafts/morning-preview.json, niemals ins öffentliche Repo.
"""
import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path('drafts')
SOURCE = ROOT / 'the-huddle-morgenausgabe-13.md'
AUDIT = ROOT / 'redaktionspruefung-13.md'
TARGET = ROOT / 'morning-preview.json'

URL = re.compile(r'https://[^\s)<>\],;]+')
SOURCE_NOTE = re.compile(r'\s*\((?:Quellen?|Zwischenstand, ESPN-Spielseite):\s*[^)]*\)', re.I)


def links_in(text):
    return list(dict.fromkeys(u.rstrip('.,;') for u in URL.findall(text)))


def clean(text):
    text = SOURCE_NOTE.sub('', text)
    # Auch frei stehende Quellen-URLs entfernen; sie werden separat verlinkt.
    text = URL.sub('', text)
    text = re.sub(r'\s+([,.;:!?])', r'\1', text)
    text = re.sub(r'\(\s*\)', '', text)
    return ' '.join(text.split()).strip(' ,;')


def entry(text, *, title=None, category=None):
    urls = [u for u in links_in(text) if urlparse(u).scheme == 'https' and urlparse(u).netloc]
    result = {'text': clean(text)} if title is None else {
        'title': title, 'summary': clean(text), 'category': category or 'AROUND THE LEAGUE'
    }
    if urls:
        result['source_url'] = urls[0]
        result['source_name'] = urlparse(urls[0]).netloc.removeprefix('www.')
    return result


def paragraphs(section):
    items = []
    for part in re.split(r'\n\s*\n', section.strip()):
        part = part.strip()
        if not part or re.match(r'^vor veröffentlichung redaktionell prüfen\.?$', part, re.I):
            continue
        # Einzelne Bulletpoints sind ebenfalls zulässig, sofern das Modell sie liefert.
        if part.startswith('- '):
            items.extend(line[2:].strip() for line in part.splitlines() if line.startswith('- '))
        else:
            items.append(part)
    return items


def first_sentence(text):
    # Nicht bei Abkürzungen oder Datumsangaben blind am ersten Punkt abschneiden.
    match = re.search(r'(?<=[.!?])\s+(?=[A-ZÄÖÜ])', text)
    return text[:match.start()].strip() if match else text.strip()


def brief_text(text):
    sentence = first_sentence(clean(text))
    # Keine Satzfragmente erzeugen. Lange Sätze bleiben vollständig und werden markiert.
    return sentence


def headline(text):
    body = clean(text)
    lower = body.lower()
    # Faktennahe Schlagzeilen aus eindeutig vorhandenen Aussagen, ohne Zusatzbehauptungen.
    patterns = (
        (('daniel jones', 'bank'), 'Colts setzen Daniel Jones auf die Bank'),
        (('jack campbell', 'krankenhaus'), 'Jack Campbell nach Tackle ins Krankenhaus gebracht'),
        (('buccaneers', 'ohne', 'pass'), 'Buccaneers gewinnen ohne vollständigen Pass'),
        (('zach charbonnet', 'verletztenbericht'), 'Zach Charbonnet vor Seahawks-Saisondebüt'),
        (('dylan laube', 'kickoff'), 'Dylan Laube erzielt Kickoff-Return-Touchdown'),
        (('wu-tang', 'halbzeit'), 'Wu-Tang Clan für Thanksgiving-Halbzeitshow angekündigt'),
        (('saquon barkley', 'gehandelt'), 'Bericht: Eagles wollen Saquon Barkley behalten'),
    )
    for terms, title in patterns:
        if all(term in lower for term in terms):
            return title
    sentence = first_sentence(body)
    # Bestehende redaktionelle Überschriften respektieren, wenn sie als **Titel** beginnen.
    explicit = re.match(r'^\*\*(.{8,110}?)\*\*\s*', body)
    if explicit:
        return explicit.group(1).strip()
    # Eine kurze, vollständige erste Teilaussage; nie mitten im Wort abschneiden.
    clause = re.split(r'[,;—–]\s+', sentence, maxsplit=1)[0]
    if len(clause) <= 105:
        return clause.rstrip(' .,:;')
    # Nur als letzte Rückfallebene: lesbar am Wortende mit Auslassungszeichen.
    return clause[:101].rsplit(' ', 1)[0].rstrip(' .,:;') + ' …'


def topic_key(text):
    s = clean(text).lower()
    # Nur bei klar erkennbaren gemeinsamen Akteuren zusammenführen.
    for name in ('lamar jackson', 'daniel jones', 'jack campbell', 'zach charbonnet',
                 'saquon barkley', 'dylan laube', 'wu-tang clan'):
        if name in s:
            return name
    return ' '.join(re.findall(r'[a-zäöüß]{4,}', s)[:9])


def sections_of(md):
    """Accept headings with optional Markdown decoration and explanatory suffixes."""
    aliases = {'THE LEAD': 'THE LEAD', 'LEAD': 'THE LEAD',
               'GAME CENTER': 'GAME CENTER', 'GAMECENTER': 'GAME CENTER',
               'AROUND THE LEAGUE': 'AROUND THE LEAGUE',
               'TOP STORIES': 'AROUND THE LEAGUE',
               'AUSTRIAN WATCH': 'AUSTRIAN WATCH'}
    sections, current = {}, None
    for line in md.splitlines():
        match = re.match(r'^\s*(?:#{1,6}\s*|\*\*\s*)(THE LEAD|LEAD|GAME CENTER|GAMECENTER|AROUND THE LEAGUE|TOP STORIES|AUSTRIAN WATCH)\b', line, re.I)
        if match:
            current = aliases[match.group(1).upper()]
            sections.setdefault(current, [])
        elif current:
            sections[current].append(line)
    return {name: '\n'.join(lines).strip() for name, lines in sections.items()}


def main():
    if not SOURCE.is_file() or not AUDIT.is_file():
        raise SystemExit('Entwurf oder Prüfbericht fehlt. Keine Vorschau erstellt.')
    md = SOURCE.read_text(encoding='utf-8')
    audit = AUDIT.read_text(encoding='utf-8')
    if not md.startswith('TESTENTWURF – AUTOMATISCH ERSTELLT, NICHT VERÖFFENTLICHEN'):
        raise SystemExit('Testentwurf-Kennzeichnung fehlt. Abbruch.')
    if '## Vor Veröffentlichung manuell prüfen' not in audit:
        raise SystemExit('Prüfbericht nicht erkannt. Abbruch.')
    sections = sections_of(md)
    if not sections.get('THE LEAD') or not sections.get('AROUND THE LEAGUE'):
        print('WARNUNG: Rubriken fehlen; Testvorschau bleibt unvollständig.')

    lead = paragraphs(sections.get('THE LEAD', ''))
    around = paragraphs(sections.get('AROUND THE LEAGUE', ''))
    # Ein Lead-Thema, dann unterschiedliche Liga-Themen; niemals denselben Akteur doppelt.
    candidates = lead[:1] + around
    brief, seen = [], set()
    for paragraph in candidates:
        key = topic_key(paragraph)
        if key in seen:
            continue
        seen.add(key)
        item = entry(paragraph)
        item['text'] = brief_text(paragraph)
        brief.append(item)
        if len(brief) == 5:
            break

    stories = [entry(p, title=headline(p), category='AROUND THE LEAGUE') for p in around[:6]]
    austrian = paragraphs(sections.get('AUSTRIAN WATCH', ''))
    date_match = re.search(r'^# THE HUDDLE – (.+)$', md, re.M)
    game_section = sections.get('GAME CENTER', '')
    game_count = sum(1 for line in game_section.splitlines()
                     if re.match(r'^\s*(?:-\s*)?(?:ENDE:|LIVE\s*\(|NOCH NICHT BEENDET)', line))
    warnings = [
        'Nicht veröffentlichen: Keine redaktionelle Freigabe.',
        'Alle Aussagen, Verletzungen, Zahlen und Quellen manuell prüfen.',
        'LIVE-Spielstände vor Veröffentlichung neu abrufen.',
        'Überschriften und Kurzmeldungen redaktionell prüfen.',
    ]
    if not sections.get('THE LEAD') or not sections.get('AROUND THE LEAGUE'):
        warnings.append('Pflichtrubriken fehlen: Originalentwurf manuell prüfen; nicht freigeben.')
    if len(brief) < 5:
        warnings.append(f'Nur {len(brief)} unterschiedliche Brief-Themen vorhanden; keine Meldungen erfunden.')
    if any(len(item['text']) > 250 for item in brief):
        warnings.append('Mindestens ein Brief-Satz ist länger als 250 Zeichen; redaktionell kürzen.')
    if any('source_url' not in item for item in brief + stories):
        warnings.append('Mindestens eine Meldung ohne erkannten Originalquellenlink.')
    if game_count:
        warnings.append(f'{game_count} Game-Center-Zeilen bewusst nicht als statische Ergebnisse übernommen.')

    result = {
        'version': '1.0', 'status': 'draft', 'published_at': None,
        'message': 'Nur interne Testvorschau – nicht veröffentlichen.',
        'edition': {
            'date': date_match.group(1) if date_match else 'Datum prüfen',
            'headline': 'THE HUDDLE – Redaktionelle Testvorschau',
            'intro': 'Unveröffentlichter Entwurf. Sämtliche Meldungen vor Freigabe prüfen.',
            'brief': brief, 'stories': stories,
            'austria': entry(austrian[0]) if austrian else None,
        },
        'review_required': warnings,
    }
    ROOT.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Vorschau: {TARGET}; {len(brief)} Brief-Themen, {len(stories)} Stories; NICHT veröffentlicht.')


if __name__ == '__main__':
    main()
