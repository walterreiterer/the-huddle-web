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
    # Markdown-Trennlinien sind Layout, kein Bestandteil der Nachricht.
    text = re.sub(r'(?m)^\s*(?:-{3,}|\*{3,}|_{3,})\s*$', '', text)
    text = re.sub(r'(?:\s+---\s*)+$', '', text.strip())
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


def parse_story_blocks(section):
    """Bindet Folgeabsätze bis zur nächsten fett gesetzten Überschrift ein."""
    stories = []
    title = None
    body_lines = []

    def finish():
        if title is not None and any(line.strip() for line in body_lines):
            stories.append({'title': title, 'body': '\n'.join(body_lines).strip()})

    for line in section.splitlines():
        match = TITLE_LINE.fullmatch(line.strip())
        if match:
            finish()
            title = match.group(1).strip()
            if not 15 <= len(title) <= 110:
                title = FALLBACK_TITLE
            body_lines = []
        elif title is not None:
            body_lines.append(line)
    finish()
    return stories


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
    around = parse_story_blocks(sections.get('AROUND THE LEAGUE', ''))
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

    # Eigenständige Geschichten vollständig erhalten; nicht mehr bei sechs abschneiden.
    stories = []
    for news in around:
        item = entry(news['body'], title=news['title'], category='AROUND THE LEAGUE')
        if item.get('source_url'):
            stories.append(item)
        else:
            print('Ohne Quelle übersprungen (Story):', news['title'])
        if len(stories) >= 8:
            break
    if len(stories) < 2:
        fail('Zu wenige belegte Top Stories.')

    austrian = None
    austrian_raw = paragraphs(sections.get('AUSTRIAN WATCH', ''))
    if austrian_raw and (parsed := parse_news(austrian_raw[0])):
        candidate = entry(parsed['body'])
        if candidate.get('source_url'):
            austrian = candidate

    games = game_center_from_espn()

    def short_brief(body):
        """Nur vollständige Original-Sätze übernehmen, nichts dazuerfinden."""
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-ZÄÖÜ])', body.strip())
        short = ''
        for sentence in sentences:
            candidate = (short + ' ' + sentence).strip()
            if len(candidate) > 280 and len(short) >= 65:
                break
            short = candidate
            if len(short) >= 120:
                break
        if not 65 <= len(short) <= 1500 or not re.search(r"[.!?]$", short):
            return None
        return short

    # Jede Nachricht darf nur in einer redaktionellen Rubrik erscheinen.
    # Der Lead und Austrian Watch sind eigenstaendige Rubriken.
    # Morning Brief und Around the League teilen die vorhandenen Stories auf.
    brief = []
    remaining_stories = []
    reserved_urls = {lead_item['source_url']}
    if austrian:
        reserved_urls.add(austrian['source_url'])
    used_urls = set(reserved_urls)
    used_topics = {topic_key(lead_item['title'])}

    for story in stories:
        url = story.get('source_url', '')
        key = topic_key(story['title'])
        if not url or url in used_urls or key in used_topics:
            print('Doppelte Geschichte uebersprungen:', story['title'])
            continue
        used_urls.add(url)
        used_topics.add(key)
        remaining_stories.append(story)

    # Maximal drei kurze eigenstaendige Brief-Meldungen; mindestens zwei
    # ausfuehrliche Around-the-League-Geschichten bleiben erhalten.
    brief_candidates = remaining_stories[:max(0, min(3, len(remaining_stories) - 2))]
    stories = remaining_stories[len(brief_candidates):]
    for story in brief_candidates:
        short = short_brief(story['summary'])
        if not short:
            # Ungeeignete Kurzmeldung nicht verlieren, sondern als Story behalten.
            stories.insert(0, story)
            continue
        brief.append({
            'title': story['title'],
            'text': short,
            'source_url': story['source_url'],
            'source_name': story.get('source_name', ''),
        })
    if len(stories) < 2:
        fail('Zu wenige eigenstaendige Around-the-League-Geschichten.')
    if not brief:
        print('Hinweis: Keine geeigneten eigenstaendigen Morning-Brief-Meldungen.')

    date_match = re.search(r'^# THE HUDDLE – (.+)$', md, re.M)
    if not date_match:
        fail('Ausgabedatum fehlt.')
    date = date_match.group(1).strip()
    # Das Modell kann den ISO-Zeitstempel in Markdown-Klammern setzen.
    if date.startswith('[') and date.endswith(']'):
        date = date[1:-1].strip()
    # Nur den ISO-Zeitstempel übernehmen; redaktionelle Zusätze wie
    # '(ZEIT WIEN)' oder '(Stand: ...)' sind keine Datumsbestandteile.
    iso_match = re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})?', date)
    if iso_match:
        date = iso_match.group(0)
    try:
        datetime.fromisoformat(date.replace('Z', '+00:00'))
    except ValueError:
        fail('Ausgabedatum nicht im ISO-Format: ' + date)

    warnings = [
        'Nicht veröffentlichen: Keine redaktionelle Freigabe.',
        'Alle Aussagen, Zahlen und Originalquellen prüfen.',
        'LIVE-Spielstände vor Veröffentlichung neu abrufen.',
        'Überschriften und Kurzmeldungen redaktionell prüfen.',
    ]
    fallback_count = sum(s['title'] == FALLBACK_TITLE for s in stories)
    if fallback_count:
        warnings.append(f'{fallback_count} Story-Überschrift(en) redaktionell ergänzen.')
    if len(brief) < 3:
        warnings.append(f'Nur {len(brief)} eigenstaendige Brief-Themen; keine Meldungen erfunden.')
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
