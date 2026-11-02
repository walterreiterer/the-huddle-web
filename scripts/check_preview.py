import json, re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
p=Path('drafts/morning-preview.json')
d=json.loads(p.read_text(encoding='utf-8'))
e=d.get('edition', {})
assert d.get('status') == 'draft', 'Nicht als Entwurf gekennzeichnet'
assert datetime.now(ZoneInfo('Europe/Vienna')).date().isoformat() in str(e.get('date','')), 'Datum nicht aktuell'
brief=e.get('brief', []); stories=e.get('stories', [])
assert len(brief)==5 and len(stories)>=3, 'Zu wenige Themen'
for item in brief+stories:
 t=str(item.get('text') or item.get('summary') or '').strip()
 u=urlparse(str(item.get('source_url') or ''))
 assert len(t)>=65 and u.scheme=='https' and u.netloc, 'Fehlender Text oder Quelle'
 assert not t.endswith(('…','...',',',';',':')), 'Abgeschnittener Text'
for item in stories:
 title=str(item.get('title','')).strip()
 assert 15<=len(title)<=110 and not title.endswith(('…','...',',',';',':',' an')), 'Schlechte Überschrift'
print('Strukturprüfung erfolgreich. KEIN journalistischer Faktencheck.')
