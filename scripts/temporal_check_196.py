#!/usr/bin/env python3
"""THE HUDDLE 1.9.6: konservative Aktualitätsprüfung; keine Veröffentlichung."""
import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path('drafts')
DRAFT = ROOT / 'the-huddle-probeausgabe-193.md'
SOURCES = ROOT / 'quellen-10.json'
OUT = ROOT / 'aktualitaetskontrolle-196.md'
OUT_JSON = ROOT / 'aktualitaetskontrolle-196.json'

PATTERNS = [
    ('TRADE_DEADLINE', r'(?i)\b(?:trade[ -]?deadline|trading[ -]?deadline|deadline|transferfrist)\b', 'Fristbezug: prüfen, ob die Frist zum Ausgabezeitpunkt noch bevorsteht'),
    ('FUTURE_EVENT', r'(?i)\b(?:morgen|heute|am sonntag|am montag|vor dem spiel|soll starten|wird starten|ahead of|on sunday|on monday|set to start)\b', 'Zeitabhängige Ankündigung: Status und Spieltermin erneut prüfen'),
    ('ONGOING', r'(?i)\b(?:derzeit|aktuell|weiterhin|noch immer|in gesprächen|führt.*gespräche|ongoing|reportedly entertaining)\b', 'Laufender Sachverhalt: prüfen, ob inzwischen eine Entscheidung vorliegt'),
]

def normalize(url):
    p = urlsplit(url.strip().rstrip(').,;'))
    return (p.netloc.lower().removeprefix('www.'), p.path.rstrip('/').lower())

def parse_date(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        try:
            dt = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)

def extract_blocks(text):
    blocks = []
    section = ''
    for chunk in re.split(r'\n\s*\n', text):
        header = re.search(r'(?m)^##\s+(.+)$', chunk)
        if header:
            section = header.group(1)
            chunk = chunk[header.end():].strip()
        urls = re.findall(r'https?://[^\s)]+', chunk)
        if urls and section in ('THE LEAD', 'AROUND THE LEAGUE', 'GAME CENTER'):
            blocks.append((section, chunk, urls))
    return blocks

def main():
    for f in (DRAFT, SOURCES):
        if not f.is_file():
            raise SystemExit(f'Pflichtdatei fehlt: {f}')
    draft = DRAFT.read_text(encoding='utf-8')
    data = json.loads(SOURCES.read_text(encoding='utf-8'))
    collected = parse_date(data.get('collected_utc'))
    if not collected:
        raise SystemExit('Ungültiger Abrufzeitpunkt collected_utc – keine Aktualitätsaussage möglich')
    index = {normalize(a.get('url', '')): a for a in data.get('articles', []) if a.get('url')}
    findings = []
    for section, block, urls in extract_blocks(draft):
        if section == 'GAME CENTER':
            continue  # ESPN hat eigenen Status; hier keine Datumsinterpretation
        title = re.search(r'\*\*(.+?)\*\*', block)
        label = title.group(1) if title else block[:85]
        linked = [index[normalize(u)] for u in urls if normalize(u) in index]
        flags = []
        for code, pattern, hint in PATTERNS:
            if re.search(pattern, block):
                flags.append({'code': code, 'reason': hint})
        if not linked:
            flags.append({'code': 'SOURCE_NOT_IN_COLLECTION', 'reason': 'Quellenlink nicht in der aktuellen Quellensammlung gefunden'})
        for a in linked:
            published = parse_date(a.get('published'))
            if not published:
                flags.append({'code': 'SOURCE_DATE_UNKNOWN', 'reason': 'Veröffentlichungsdatum der Quelle nicht auswertbar'})
            else:
                age = (collected - published).total_seconds() / 3600
                if age < -1:
                    flags.append({'code': 'SOURCE_IN_FUTURE', 'reason': f'Quellendatum liegt {abs(age):.1f} Stunden nach dem Abruf'})
                elif age > 48:
                    flags.append({'code': 'SOURCE_OLDER_48H', 'reason': f'Quelle beim Abruf bereits {age:.1f} Stunden alt'})
        if flags:
            findings.append({'section': section, 'title': label, 'source_urls': urls, 'flags': flags})
    result = {
        'version': '1.9.6', 'status': 'MANUELL_PRUEFEN' if findings else 'KEINE_HEURISTISCHEN_TREFFER',
        'collected_utc': collected.isoformat(), 'reviewed_news_blocks': sum(1 for s, _, _ in extract_blocks(draft) if s != 'GAME CENTER'),
        'flagged_news_blocks': len(findings), 'findings': findings,
        'limitations': 'Fristablauf und Ereignisstatus werden nicht live verifiziert. Ein Treffer ist ein Prüfhinweis, kein nachgewiesener Fehler. Keine Freigabe.'
    }
    ROOT.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = ['# THE HUDDLE – Aktualitätskontrolle 1.9.6', '', '**KEINE VERÖFFENTLICHUNGSFREIGABE.**', '',
             f"**Quellenabruf:** {collected.isoformat()}", f"**Status:** {result['status']}",
             f"**Nachrichtenblöcke geprüft:** {result['reviewed_news_blocks']}; **mit Hinweisen:** {len(findings)}", '']
    for f in findings:
        lines.extend([f"## {f['title']}", '', f"Bereich: {f['section']}", ''])
        lines.extend(f"- **{flag['code']}:** {flag['reason']}" for flag in f['flags'])
        lines.append('')
    if not findings:
        lines.extend(['Keine heuristischen Treffer. Das ist keine Bestätigung der Aktualität.', ''])
    lines.extend(['## Grenzen', '', result['limitations'], ''])
    OUT.write_text('\n'.join(lines), encoding='utf-8')
    print(f"Aktualitätskontrolle 1.9.6: {len(findings)} Meldungen mit Hinweisen; keine Veröffentlichung")

if __name__ == '__main__':
    main()
