#!/usr/bin/env python3
"""Enrich THE HUDDLE's unpublished preview with archived official NFL Gamebooks.
Run after convert_morning_14.py. Does not publish or alter other scripts.
"""
import json
import re
from pathlib import Path
from urllib.parse import urlparse

PREVIEW = Path('drafts/morning-preview.json')
ARCHIVES = Path('data/gamebooks')
GAME_ID = re.compile(r'(?<!\d)(\d{9})(?!\d)')

def main():
    if not PREVIEW.is_file():
        raise SystemExit('Preview fehlt: ' + str(PREVIEW))
    data = json.loads(PREVIEW.read_text(encoding='utf-8'))
    if data.get('status') != 'draft' or data.get('published_at') is not None:
        raise SystemExit('Abbruch: Nur unveröffentlichte Entwürfe werden ergänzt.')
    games = data.get('edition', {}).get('game_center')
    if not isinstance(games, list):
        raise SystemExit('Abbruch: game_center fehlt oder ist ungültig.')
    index = {}
    for path in sorted(ARCHIVES.glob('????????.json')):
        archive = json.loads(path.read_text(encoding='utf-8'))
        if archive.get('date') != path.stem or not isinstance(archive.get('gamebooks'), dict):
            raise SystemExit('Ungültiges Archiv: ' + str(path))
        for event_id, url in archive['gamebooks'].items():
            parsed = urlparse(url)
            if parsed.scheme != 'https' or parsed.hostname != 'static.www.nfl.com' or not parsed.path.endswith('.pdf'):
                raise SystemExit('Ungültige NFL-PDF-Adresse: ' + str(url))
            if event_id in index and index[event_id] != url:
                raise SystemExit('Widersprüchliche Gamebook-Links für ESPN-ID ' + event_id)
            index[event_id] = url
    matched = 0
    for game in games:
        source = game.get('source_url', '')
        if urlparse(source).hostname not in ('espn.com', 'www.espn.com'):
            continue
        ids = GAME_ID.findall(source)
        if len(ids) != 1:
            continue
        url = index.get(ids[0])
        if url:
            game['gamebook_url'] = url
            matched += 1
    PREVIEW.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Gamebook-Ergänzung: {matched}/{len(games)} Spiele; nur interne Vorschau aktualisiert.')

if __name__ == '__main__':
    main()
