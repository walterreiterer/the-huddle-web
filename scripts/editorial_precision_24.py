#!/usr/bin/env python3
"""Konservative, nachvollziehbare Korrektur bekannter Quellenüberdehnungen.

Keine Freigabe, keine Veröffentlichung. Korrigiert nur eine genau definierte
Formulierung, falls die zugehörige offizielle Quelle verwendet wird.
"""
import json
from pathlib import Path

P = Path('drafts/morning-preview.json')
REPORT = Path('drafts/praezisierung-24.json')
SOURCE = 'https://www.nfl.com/news/nfl-announces-changes-to-officiating-assignments-impacted-air-travel'
OLD = 'und danach per Auto (~110 Meilen) nach Cincinnati fahren, um dort das Sunday-Night-Game'
NEW = 'und später für das rund 110 Meilen entfernte Sunday-Night-Game in Cincinnati vorgesehen sein, um dort das Spiel'

def revise(preview):
    lead = preview.get('edition', {}).get('lead')
    if not isinstance(lead, dict) or lead.get('source_url') != SOURCE:
        return False
    summary = lead.get('summary')
    if not isinstance(summary, str) or OLD not in summary:
        return False
    lead['summary'] = summary.replace(OLD, NEW, 1)
    return True

def main():
    if not P.exists():
        raise SystemExit('Präzisierung 2.4: Vorschau fehlt')
    preview = json.loads(P.read_text(encoding='utf-8'))
    changed = revise(preview)
    if changed:
        P.write_text(json.dumps(preview, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    REPORT.write_text(json.dumps({'status': 'KORRIGIERT' if changed else 'KEINE_AENDERUNG',
        'regel': 'NFL-Officiating: unbelegte Autofahrt nicht behaupten',
        'freigabe': False}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Präzisierung 2.4:', '1 Formulierung korrigiert' if changed else 'kein Treffer')

if __name__ == '__main__':
    main()
