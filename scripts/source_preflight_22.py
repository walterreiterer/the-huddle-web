#!/usr/bin/env python3
"""Konservative Quellen-Vorprüfung; keine semantische Behauptungs-Verifikation."""
import json, re, sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path('drafts')
IN=ROOT/'quellen-10.json'
OUT=ROOT/'quellen-geprueft-22.json'
REPORT=ROOT/'quellenkontrolle-22.json'
MIN_WORDS=120
MAX_AGE_HOURS=48

def run(now=None):
    now=now or datetime.now(timezone.utc)
    data=json.loads(IN.read_text(encoding='utf-8'))
    articles=data.get('articles')
    if not isinstance(articles,list): raise ValueError('Quellenliste fehlt')
    accepted=[]; rejected=[]; flagged=[]; seen=set()
    for i,a in enumerate(articles):
        if not isinstance(a,dict):
            rejected.append({'index':i,'reason':'Kein Artikelobjekt'});continue
        title=str(a.get('title') or '').strip()
        url=str(a.get('url') or '').strip()
        text=str(a.get('text') or '').strip()
        reasons=[]
        parsed=urlparse(url)
        if parsed.scheme!='https' or not parsed.hostname: reasons.append('Ungültige HTTPS-Quellen-URL')
        if url in seen: reasons.append('Doppelte Quellen-URL')
        seen.add(url)
        if len(title)<12: reasons.append('Titel fehlt/zu kurz')
        if len(text.split())<MIN_WORDS: reasons.append('Zu wenig Originaltext')
        published=a.get('published')
        try:
            date=parsedate_to_datetime(str(published))
            if date.tzinfo is None: date=date.replace(tzinfo=timezone.utc)
            age=(now-date.astimezone(timezone.utc)).total_seconds()/3600
            if age>MAX_AGE_HOURS: reasons.append('Quelle älter als 48 Stunden')
            if age < -2: reasons.append('Quellendatum liegt in der Zukunft')
        except (TypeError, ValueError, OverflowError):
            reasons.append('Veröffentlichungsdatum nicht überprüfbar')
        if reasons:
            rejected.append({'index':i,'title':title,'url':url,'reasons':reasons})
            continue
        # Der Wortlaut einer Überschrift beweist nicht, dass der Artikel jede Behauptung trägt.
        # Statusmeldungen sind zeitkritisch und müssen vor Veröffentlichung überprüft werden.
        if re.search(r'(?i)\b(ruled out|questionable|doubtful|will start|set to start|surgery|operat(?:ion|ed)|expected|reportedly|könnte|droht|fällt aus|startet)\b',title):
            flagged.append({'index':i,'title':title,'reason':'Zeitkritische Statusmeldung: Originaltext und neuere Updates prüfen'})
        accepted.append(a)
    report={'version':'2.2','input_count':len(articles),'accepted_count':len(accepted),
            'rejected_count':len(rejected),'rejected':rejected,'manual_checks':flagged,
            'claim_verification':'NICHT AUTOMATISCH DURCHGEFÜHRT',
            'publication_approved':False}
    ROOT.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    OUT.write_text(json.dumps({**data,'articles':accepted},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Quellenkontrolle 2.2: {len(accepted)} akzeptiert, {len(rejected)} aussortiert, {len(flagged)} manuelle Hinweise')
    if not accepted: raise ValueError('Keine verwendbaren Quellen: Ausgabe stoppen')
    return report

if __name__=='__main__':
    try: run()
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print('Quellenkontrolle gesperrt:',exc,file=sys.stderr)
        sys.exit(1)
