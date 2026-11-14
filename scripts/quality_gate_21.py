#!/usr/bin/env python3
"""Conservative, offline editorial preflight. Never grants publication approval."""
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

# Only unambiguous NFL city/team combinations are checked; no speculative roster validation.
CITY_TEAMS = {
    'miami': {'dolphins'}, 'indianapolis': {'colts'}, 'kansas city': {'chiefs'},
    'buffalo': {'bills'}, 'minnesota': {'vikings'}, 'green bay': {'packers'},
    'seattle': {'seahawks'}, 'las vegas': {'raiders'}, 'atlanta': {'falcons'},
    'chicago': {'bears'}, 'detroit': {'lions'}, 'cleveland': {'browns'},
    'cincinnati': {'bengals'}, 'pittsburgh': {'steelers'}, 'denver': {'broncos'},
    'carolina': {'panthers'}, 'baltimore': {'ravens'}, 'houston': {'texans'},
    'jacksonville': {'jaguars'}, 'tennessee': {'titans'}, 'philadelphia': {'eagles'},
    'washington': {'commanders'}, 'dallas': {'cowboys'}, 'arizona': {'cardinals'},
    'tampa bay': {'buccaneers'}, 'new england': {'patriots'},
    'san francisco': {'49ers'},
}
TEAM_NAMES = set().union(*CITY_TEAMS.values())
TEAM_PATTERN = re.compile(r'(?<![\w-])(' + '|'.join(map(re.escape, sorted(CITY_TEAMS, key=len, reverse=True))) + r')\s+(' + '|'.join(map(re.escape, sorted(TEAM_NAMES, key=len, reverse=True))) + r')(?![\w-])', re.I)
WEEK = re.compile(r'(?i)\bweek[\s-]*(\d{1,2})\b')


def items(edition):
    lead = edition.get('lead')
    if isinstance(lead, dict): yield 'Lead', lead
    for key, label in (('brief', 'Morning Brief'), ('stories', 'Around the League')):
        for i, entry in enumerate(edition.get(key) or [], 1):
            if isinstance(entry, dict): yield f'{label} #{i}', entry
    austria = edition.get('austria')
    if isinstance(austria, dict): yield 'Austrian Watch', austria
    elif isinstance(austria, list):
        for i, entry in enumerate(austria, 1):
            if isinstance(entry, dict): yield f'Austrian Watch #{i}', entry


def inspect(root):
    errors, review = [], []
    file = root / 'drafts/morning-preview.json'
    if not file.is_file(): return ['Vorschaudatei fehlt'], []
    try:
        data = json.loads(file.read_text(encoding='utf-8'))
        edition = data['edition']
        edition_date = datetime.fromisoformat(edition['date'].replace('Z', '+00:00'))
    except (ValueError, KeyError, TypeError) as exc:
        return [f'Vorschau unlesbar/Datum ungueltig: {exc}'], []
    if data.get('status') != 'draft' or data.get('published_at') is not None:
        errors.append('Keine eindeutig unveroeffentlichte Testvorschau')
    for label, entry in items(edition):
        title = str(entry.get('title') or '')
        body = str(entry.get('text') or entry.get('summary') or '')
        content = title + ' ' + body
        for m in TEAM_PATTERN.finditer(content):
            city, team = m.group(1).lower(), m.group(2).lower()
            if team not in CITY_TEAMS[city]:
                errors.append(f'{label}: falsche NFL-Teamkombination "{m.group(0)}"')
        url = str(entry.get('source_url') or '').strip()
        if not url or urlparse(url).scheme not in ('http','https') or not urlparse(url).netloc:
            errors.append(f'{label}: Quellen-URL fehlt oder ist ungueltig')
        else:
            # A URL alone is NOT proof that the claim is supported by that article.
            review.append(f'{label}: Originalartikel und zentrale Aussage gegenpruefen: {url}')
            url_weeks = {int(w) for w in WEEK.findall(url.replace('_', '-'))}
            text_weeks = {int(w) for w in WEEK.findall(content)}
            if url_weeks and text_weeks and url_weeks != text_weeks:
                errors.append(f'{label}: Week-Widerspruch zwischen Text {sorted(text_weeks)} und URL {sorted(url_weeks)}')
            elif url_weeks:
                review.append(f'{label}: Week {sorted(url_weeks)} in Quellen-URL; Bezug zum Ausgabedatum {edition_date.date()} pruefen')
        if re.search(r'(?i)\b(gestern|heute|morgen|vergangene nacht|letzte nacht)\b', content):
            review.append(f'{label}: relative Zeitangabe mit Ausgabedatum {edition_date.date()} abgleichen')
    audit = root / 'drafts/quellen-audit-093.md'
    if not audit.is_file():
        errors.append('Quellen-Audit fehlt')
    else:
        audit_text = audit.read_text(encoding='utf-8')
        if re.search(r'(?i)redaktioneller befund:\s*\*\*OFFEN\*\*', audit_text):
            review.append('Quellen-Audit enthaelt OFFENE Befunde: keine journalistische Freigabe')
        if 'MANUELLE PRÜFUNG ERFORDERLICH' in audit_text:
            review.append('Quellen-Audit fordert manuelle Pruefung')
    return sorted(set(errors)), sorted(set(review))


def main():
    root = Path('.')
    errors, review = inspect(root)
    report = root / 'drafts/qualitaetscheck-21.json'
    report.parent.mkdir(parents=True, exist_ok=True)
    result = {'version':'2.1', 'status':'GESPERRT' if errors else 'MANUELL_PRUEFEN',
              'publication_approved':False, 'errors':errors, 'manual_checks':review}
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if errors else 0

if __name__ == '__main__':
    sys.exit(main())
