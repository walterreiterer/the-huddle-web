#!/usr/bin/env python3
"""THE HUDDLE: Quellen-Inventur (keine inhaltliche Verifikation, keine Veröffentlichung)."""
import json
import re
from pathlib import Path
from urllib.parse import urlparse

SOURCE = Path('drafts/morning-preview.json')
TARGET = Path('drafts/quellen-audit-093.md')
RISK = re.compile(r'\b(trade|wechsel|verletz|saison|operation|operiert|ausfall|gesperrt|entlassen|reinstat|ir\b|injured reserve|draftpick|draft-pick|tod|stirbt)\w*', re.I)


def main():
    if not SOURCE.is_file():
        raise SystemExit('QUELLEN-AUDIT: drafts/morning-preview.json fehlt')
    data = json.loads(SOURCE.read_text(encoding='utf-8'))
    if data.get('status') != 'draft':
        raise SystemExit('QUELLEN-AUDIT: nur für unveröffentlichte Entwürfe')
    edition = data.get('edition', {})
    records = []
    for label, value in [('Lead', edition.get('lead')), ('Morning Brief', edition.get('brief', [])),
                         ('Around the League', edition.get('stories', [])), ('Austrian Watch', edition.get('austria'))]:
        items = value if isinstance(value, list) else [value] if value else []
        for i, item in enumerate(items, 1):
            if not isinstance(item, dict):
                continue
            title = str(item.get('title') or f'{label} {i}').replace('\n', ' ')
            summary = str(item.get('summary') or item.get('text') or '')
            url = str(item.get('source_url') or '')
            parsed = urlparse(url)
            structurally_valid = parsed.scheme == 'https' and bool(parsed.netloc) and not parsed.username
            flags = []
            if not structurally_valid:
                flags.append('KEINE GÜLTIGE HTTPS-QUELLE')
            if RISK.search(title + ' ' + summary):
                flags.append('SENSIBLE BEHAUPTUNG: Originaltext gegenprüfen')
            if not flags:
                flags.append('INHALTLICH NICHT GEPRÜFT')
            records.append((label, title, url, ', '.join(flags)))
    lines = ['# THE HUDDLE – Quellen-Audit 0.9.3', '',
             '**Status: MANUELLE PRÜFUNG ERFORDERLICH.** Dieses Skript lädt keine Websites,',
             'bestätigt keine Behauptungen und erteilt niemals eine Veröffentlichungsfreigabe.', '',
             'Prüfschritte: Link öffnen; Datum und Artikelidentität prüfen; zentrale Aussage',
             'im Originaltext belegen; bei Trades, Verletzungen und Sperren offizielle',
             'Team-/Ligaquelle oder zweite unabhängige Quelle hinzuziehen.', '']
    for label, title, url, flags in records:
        lines += [f'## {label}: {title}', f'- Quelle: {url or "FEHLT"}',
                  f'- Automatischer Hinweis: {flags}',
                  '- Redaktioneller Befund: **OFFEN**', '']
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text('\n'.join(lines), encoding='utf-8')
    print(f'Quellen-Audit geschrieben: {TARGET} ({len(records)} Meldungen). KEINE Freigabe.')

if __name__ == '__main__':
    main()
