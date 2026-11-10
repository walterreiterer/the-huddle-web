#!/usr/bin/env python3
"""THE HUDDLE 0.9: fail-closed editorial overlap check on unpublished JSON."""
import json
import re
from pathlib import Path

FILE = Path('drafts/morning-preview.json')
REPORT = Path('drafts/editorial-gate-09.txt')
STOP = {'der','die','das','und','von','mit','für','auf','bei','nach','gegen','nfl','eine','einen','ein','den','dem','des','the','in','zu','im','am'}

def words(s):
    return {w for w in re.findall(r'[a-zäöüß0-9]+', str(s).lower()) if len(w) > 2 and w not in STOP}

def overlap(a,b):
    a,b=words(a),words(b)
    return len(a & b)/max(1,min(len(a),len(b))) if a and b else 0

def main():
    data=json.loads(FILE.read_text(encoding='utf-8'))
    edition=data['edition']
    lead=edition.get('lead') or {}
    title=lead.get('title','')
    errors=[]
    if not title:
        errors.append('Lead-Titel fehlt')
    if not edition.get('brief'):
        errors.append('Morning Brief fehlt oder ist leer')
    for i, story in enumerate(edition.get('stories') or [],1):
        if (overlap(title,story.get('title','')) >= .75 or
            (lead.get('source_url') and lead.get('source_url') == story.get('source_url'))):
            errors.append(f'Lead-Dublette in Around the League #{i}: {story.get("title", "")}')
    brief=edition.get('brief') or []
    for i, item in enumerate(brief,1):
        if (overlap(title,item.get('title','')) >= .75 or
            (lead.get('source_url') and lead.get('source_url') == item.get('source_url'))):
            errors.append(f'Lead-Dublette im Morning Brief #{i}')
    for i, item in enumerate(brief,1):
        text=(item.get('title','')+' '+item.get('text','')).lower()
        if ('nfl-nacht' in text or 'vergangenen nacht' in text) and ('london' in text or 'sonntagnachmittag' in text):
            errors.append(f'Moegliche falsche Nacht-Zuordnung in Brief #{i}; manuell pruefen')
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(('BESTANDEN' if not errors else 'NICHT BESTANDEN')+'\n'+'\n'.join(errors)+'\n',encoding='utf-8')
    print(REPORT.read_text(encoding='utf-8'))
    if errors:
        raise SystemExit('Redaktionelle Testvorschau nicht uebernehmen; erst pruefen')

if __name__=='__main__':
    main()
