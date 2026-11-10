#!/usr/bin/env python3
"""THE HUDDLE 0.9.4: conservative editorial red flags for internal preview.

Does not verify sources, translate, or authorize publication.
"""
import json
import re
from pathlib import Path

SOURCE = Path('drafts/morning-preview.json')
REPORT = Path('drafts/editorial-safety-094.md')
PLACEHOLDERS = re.compile(r'(?:NFL-Meldung:\s*Überschrift redaktionell prüfen|Überschrift redaktionell prüfen|\b(?:TODO|TBD|Lorem ipsum)\b)', re.I)
LEGAL_ALLEGATIONS = re.compile(r'\b(?:Strafanzeige(?:n)?|strafrechtlich(?:e[rsnm]?)?|Ermittlungsverfahren|Anklage(?:n)?|festgenommen|verhaftet|Haftbefehl|criminal charges?|criminal complaint|arrested|indicted)\b', re.I)

def main():
    if not SOURCE.is_file():
        raise SystemExit('REDAKTIONSSPERRE 0.9.4: Vorschau-JSON fehlt')
    data = json.loads(SOURCE.read_text(encoding='utf-8'))
    edition = data.get('edition', {})
    issues = []
    groups = [('Lead', edition.get('lead')), ('Morning Brief', edition.get('brief')),
              ('Around the League', edition.get('stories')), ('Austrian Watch', edition.get('austria'))]
    for group, value in groups:
        items = value if isinstance(value, list) else [value] if isinstance(value, dict) else []
        for idx, item in enumerate(items, 1):
            if not isinstance(item, dict):
                continue
            title = str(item.get('title') or '')
            body = str(item.get('summary') or item.get('text') or '')
            location = f'{group} {idx}'
            if PLACEHOLDERS.search(title + ' ' + body):
                issues.append((location, 'Platzhalter oder ungeprüfte Überschrift'))
            if LEGAL_ALLEGATIONS.search(title + ' ' + body):
                issues.append((location, 'Möglicher strafrechtlicher Vorwurf – zwingend manuell prüfen'))
    lines = ['# THE HUDDLE – Redaktionelle Sicherheitsschranke 0.9.4', '',
             'Automatische Stichwortprüfung, **keine** inhaltliche Quellenverifikation.', '']
    if issues:
        lines += ['**Status: GESPERRT – keine neue Vorschau ins Repository übernehmen.**', '']
        lines += [f'- {where}: {reason}' for where, reason in issues]
    else:
        lines += ['**Status: Keine der definierten Warnsignale erkannt.**',
                  'Das ist **keine** journalistische Freigabe; Quellen und Fakten weiterhin manuell prüfen.']
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'Redaktionelle Sicherheit 0.9.4: {len(issues)} Warnsignal(e). Bericht: {REPORT}')
    if issues:
        raise SystemExit('REDAKTIONSSPERRE 0.9.4: Problematische Meldung erkannt; keine neue Vorschau speichern.')

if __name__ == '__main__':
    main()
