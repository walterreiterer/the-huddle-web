#!/usr/bin/env python3
"""THE HUDDLE – sichere Umwandlung des unveröffentlichten Markdown-Entwurfs in JSON.

Aufruf: python scripts/convert_morning_14.py
Schreibt ausschließlich drafts/morning-preview.json. Keine Veröffentlichung.
"""
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path('drafts')
SOURCE = ROOT / 'the-huddle-morgenausgabe-13.md'
AUDIT = ROOT / 'redaktionspruefung-13.md'
GAMES = ROOT / 'nfl-spiele-08.md'
TARGET = ROOT / 'morning-preview.json'
URL = re.compile(r'https://[^\s)<>\],;]+')
SOURCE_NOTE = re.compile(r'\s*\((?:Quellen?|Zwischenstand, ESPN-Spielseite):\s*[^)]*\)', re.I)
TITLE_LINE = re.compile(r'^\*\*(.+?)\*\*\s*$')
GAME_LINE = re.compile(r'^- (ENDE|LIVE|NOCH NICHT BEENDET):\s*(.+?)\s*\|\s*\[ESPN-Spielseite\]\((https://www\.espn\.com/nfl/game/[^)]+)\)\s*$')
FALLBACK_TITLE = 'NFL-Meldung: Überschrift redaktionell prüfen'


def fail(message):
    raise SystemExit('KONVERTER: ' + message)


def links_in(text):
    return list(dict.fromkeys(u.rstrip('.,;') for u in URL.findall(text)))


def clean(text):
    text = SOURCE_NOTE.sub('', text)
    text = URL.sub('', text)
    text = re.sub(r'\s+([,.;:!?])', r'\1', text)
    text = re.sub(r'\(\s*\)', '', text)
    return ' '.join(text.split()).strip(' ,;')


def valid_url(url):
    parsed = urlparse(url)
    return parsed.scheme == 'https' and bool(parsed.netloc)


def entry(text, *, title=None, category=None):
    urls = [u for u in links_in(text) if valid_url(u)]
    body = clean(text)
    result = ({'text': body} if title is None else
              {'title': title, 'summary': body, 'category': category or 'AROUND THE LEAGUE'})
    if urls:
        result['source_url'] = urls[0]
        result['source_name'] = urlparse(urls[0]).netloc.removeprefix('www.')
    return result


def sections_of(md):
    aliases = {'LEAD': 'THE LEAD', 'GAMECENTER': 'GAME CENTER',
               'TOP STORIES': 'AROUND THE LEAGUE'}
    sections, current = {}, None
    pattern = re.compile(r'^\s*#{1,6}\s*(THE LEAD|LEAD|GAME CENTER|GAMECENTER|AROUND THE LEAGUE|TOP STORIES|AUSTRIAN WATCH)\s*$', re.I)
    for line in md.splitlines():
        match = pattern.match(line)
        if match:
            current = aliases.get(match.group(1).upper(), match.group(1).upper())
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    return {name: '\n'.join(lines).strip() for name, lines in sections.items()}


def paragraphs(section):
    return [part.strip() for part in re.split(r'\n\s*\n', section.strip())
            if part.strip() and not re.match(r'^vor veröffentlichung redaktionell prüfen\.?$', part.strip(), re.I)]


def parse_news(paragraph):
    lines = paragraph.strip().splitlines()
    if not lines:
        return None
    match = TITLE_LINE.fullmatch(lines[0].strip())
    title = match.group(1).strip() if match else FALLBACK_TITLE
    body = '\n'.join(lines[1:]).strip() if match else paragraph.strip()
    if not body:
        return None
    if not 15 <= len(title) <= 110 or title.endswith(('…', '...', ',', ';', ':', ' an', ' nach dem', ' wegen der')):
        title = FALLBACK_TITLE
    return {'title': title, 'body': body}


def topic_key(text):
    return ' '.join(re.findall(r'[a-zäöüß0-9]{4,}', clean(text).lower())[:12])


def game_center_from_espn():
    """Liest die vollständigen ESPN-Spielzeilen direkt; KI darf sie nicht kürzen."""
    if not GAMES.is_file():
        fail('ESPN-Spieldatei fehlt; Game Center kann nicht geprüft werden.')
    games, seen, day = [], set(), None
    for raw in GAMES.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if line.startswith('## Spieltag '):
            day = line.removeprefix('## Spieltag ').strip()
        match = GAME_LINE.fullmatch(line)
        if match:
            status, matchup, url = match.groups()
            if url in seen:
                fail('Doppelte ESPN-Spielseite: ' + url)
            seen.add(url)
            games.append({'date_label': day, 'status': status, 'matchup': matchup,
                          'source_url': url, 'source_name': 'espn.com'})
        elif line.startswith(('- ENDE:', '- LIVE:', '- NOCH NICHT BEENDET:')):
            fail('Nicht lesbare ESPN-Spielzeile: ' + line[:140])
    if not games:
        fail('Keine ESPN-Spiele erkannt.')
    return games


def main():
    if not SOURCE.is_file() or not AUDIT.is_file():
        fail('Entwurf oder Prüfbericht fehlt.')
    md = SOURCE.read_text(encoding='utf-8')
    audit = AUDIT.read_text(encoding='utf-8')
    if not md.startswith('TESTENTWURF – AUTOMATISCH ERSTELLT, NICHT VERÖFFENTLICHEN'):
        fail('Testentwurf-Kennzeichnung fehlt.')
    if '## Vor Veröffentlichung manuell prüfen' not in audit:
        fail('Prüfbericht nicht erkannt.')

    sections = sections_of(md)
    lead = [n for p in paragraphs(sections.get('THE LEAD', '')) if (n := parse_news(p))]
    around = [n for p in paragraphs(sections.get('AROUND THE LEAGUE', '')) if (n := parse_news(p))]
    # THE LEAD besteht oft aus einer alleinstehenden Fettschrift-Überschrift
    # und mehreren folgenden Absätzen. Diese als einen Artikel erhalten.
    lead_section = sections.get('THE LEAD', '').strip()
    lead_match = re.match(r'^\*\*(.+?)\*\*\s*\n+([\s\S]+)$', lead_section)
    lead_item = None
    if lead_match:
        lead_title, lead_body = lead_match.group(1).strip(), lead_match.group(2).strip()
        if 15 <= len(lead_title) <= 150:
            candidate = entry(lead_body, title=lead_title, category='THE LEAD')
            if candidate.get('source_url') and len(candidate['summary']) >= 65:
                lead_item = candidate
    if lead_item is None:
        fail('THE LEAD: Überschrift, vollständiger Text oder Quelle fehlt.')
    if not lead or not around:
        fail('THE LEAD oder AROUND THE LEAGUE ohne lesbare Nachricht.')

    brief, seen = [], set()
    for news in lead[:1] + around:
        key = topic_key(news['body'])
        if key in seen:
            continue

        item = entry(news['body'])
        if not item.get('source_url'):
            print('Ohne Quelle übersprungen (Brief):', news['title'])
            continue

        # Morning Brief: kurzer Nachrichtenüberblick statt Volltext.
        body = item['text'].strip()
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-ZÄÖÜ])', body)
        short = ''

        for sentence in sentences:
            candidate = (short + ' ' + sentence).strip()
            if len(candidate) > 280 and len(short) >= 65:
                break
            short = candidate
            if len(short) >= 120:
                break

        if not 65 <= len(short) <= 1500 or not re.search(r'''[.!?]["”']?$''', short):
            print('Ungeeigneter Brief übersprungen:', news['title'], len(short))
            continue

        item['text'] = short
        brief.append(item)
        seen.add(key)

        if len(brief) >= 5:
            break

    stories = []
    for news in around:
        item = entry(news['body'], title=news['title'], category='AROUND THE LEAGUE')
        if item.get('source_url'):
            stories.append(item)
        else:
            print('Ohne Quelle übersprungen (Story):', news['title'])
        if len(stories) >= 6:
            break

    if len(brief) < 3:
        fail('Zu wenige vollständige, belegte Kurzmeldungen.')
    if len(stories) < 2:
        fail('Zu wenige belegte Top Stories.')

    austrian = None
    austrian_raw = paragraphs(sections.get('AUSTRIAN WATCH', ''))
    if austrian_raw and (parsed := parse_news(austrian_raw[0])):
        austrian = entry(parsed['body'])

    date_match = re.search(r'^# THE HUDDLE – (.+)$', md, re.M)
    if not date_match:
        fail('Ausgabedatum fehlt.')
    date = date_match.group(1).strip()
    # Das Modell kann den ISO-Zeitstempel in Markdown-Klammern setzen.
    if date.startswith('[') and date.endswith(']'):
        date = date[1:-1].strip()
    date = re.sub(r'\s*\(?Wien\)?\s*$', '', date, flags=re.I).strip()
    try:
        datetime.fromisoformat(date.replace('Z', '+00:00'))
    except ValueError:
        fail('Ausgabedatum nicht im ISO-Format: ' + date)

    games = game_center_from_espn()
    warnings = [
        'Nicht veröffentlichen: Keine redaktionelle Freigabe.',
        'Alle Aussagen, Zahlen und Originalquellen prüfen.',
        'LIVE-Spielstände vor Veröffentlichung neu abrufen.',
        'Überschriften und Kurzmeldungen redaktionell prüfen.',
    ]
    fallback_count = sum(s['title'] == FALLBACK_TITLE for s in stories)
    if fallback_count:
        warnings.append(f'{fallback_count} Story-Überschrift(en) redaktionell ergänzen.')
    if len(brief) < 5:
        warnings.append(f'Nur {len(brief)} Brief-Themen; keine Meldungen erfunden.')
    warnings.append(f'{len(games)} ESPN-Spiele im strukturierten Game Center; Spielstände vor Veröffentlichung prüfen.')
    result = {
        'version': '1.0', 'status': 'draft', 'published_at': None,
        'message': 'Nur interne Testvorschau – nicht veröffentlichen.',
        'edition': {
            'date': date, 'headline': 'THE HUDDLE – Redaktionelle Testvorschau',
            'intro': 'Unveröffentlichter Entwurf. Sämtliche Meldungen vor Freigabe prüfen.',
            'lead': lead_item, 'brief': brief, 'stories': stories, 'austria': austrian,
            'game_center': games,
        },
        'review_required': warnings,
    }
    ROOT.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Vorschau: {TARGET}; {len(brief)} Brief-Themen; {len(stories)} Stories; {len(games)} ESPN-Spiele; NICHT veröffentlicht.')


if __name__ == '__main__':
    main()
