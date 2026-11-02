import re
import sys
from urllib.parse import urljoin

import requests

GAME_URL = 'https://www.nfl.com/games/panthers-at-packers-2026-reg-8?tab=recap'
EXPECTED = 'https://static.www.nfl.com/image/upload/v1793361096/gamecenter/aaf70a66-4feb-11f1-abca-2c54536568a9.pdf'

session = requests.Session()
session.headers.update({'User-Agent': 'Mozilla/5.0 (compatible; HuddleGameBookResearch/1.0)', 'Accept': 'text/html,application/xhtml+xml'})

print('THE HUDDLE – NFL Game Book Recherchetest', flush=True)
print('Spielseite:', GAME_URL, flush=True)
try:
    response = session.get(GAME_URL, timeout=25)
    print('NFL-Spielseite HTTP:', response.status_code, flush=True)
    response.raise_for_status()
    html = response.text.replace('\\u002F', '/').replace('\\/', '/')
    candidates = set()
    for match in re.findall(r'https?[^\s"\'<>]+?\.pdf(?:\?[^\s"\'<>]*)?', html, flags=re.I):
        candidates.add(match.replace('&amp;', '&'))
    for match in re.findall(r'["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\']', html, flags=re.I):
        candidates.add(urljoin(GAME_URL, match))
    if candidates:
        print('Gefundene PDF-Adressen:')
        for url in sorted(candidates):
            print(' -', url)
    else:
        print('Kein direkter PDF-Link im HTML gefunden. Möglicherweise wird er dynamisch geladen.')
    print('Referenz-PDF im HTML:', 'JA' if EXPECTED in html or EXPECTED in candidates else 'NEIN')
except requests.RequestException as exc:
    print('NFL-Spielseite nicht abrufbar:', exc)

try:
    response = session.get(EXPECTED, timeout=30, stream=True)
    print('Referenz-PDF HTTP:', response.status_code)
    print('Content-Type:', response.headers.get('Content-Type', 'unbekannt'))
    response.raise_for_status()
    first = next(response.iter_content(chunk_size=16), b'')
    print('PDF-Signatur erkannt:', 'JA' if first.startswith(b'%PDF-') else 'NEIN')
except requests.RequestException as exc:
    print('Referenz-PDF nicht abrufbar:', exc)

print('Recherchetest beendet. Es wurde nichts veröffentlicht.')
