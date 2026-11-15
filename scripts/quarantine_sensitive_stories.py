#!/usr/bin/env python3
"""Quarantine legal-allegation stories from an internal preview, never from the source archive.

If fewer than two Around-the-League stories remain, fail rather than weaken
existing structural checks. Other sections remain subject to editorial_safety_094.
"""
import json
from pathlib import Path
from editorial_safety_094 import LEGAL_ALLEGATIONS

PREVIEW = Path('drafts/morning-preview.json')
REPORT = Path('drafts/quarantined-stories.md')


def quarantine(data):
    edition = data['edition']
    stories = edition['stories']
    if not isinstance(stories, list):
        raise ValueError('Around the League ist keine Liste')
    kept, held = [], []
    for story in stories:
        if not isinstance(story, dict):
            kept.append(story)
            continue
        content = str(story.get('title') or '') + ' ' + str(story.get('summary') or '')
        if LEGAL_ALLEGATIONS.search(content):
            held.append(story)
        else:
            kept.append(story)
    if held and len(kept) < 2:
        raise ValueError('Nach Zurueckstellung bleiben weniger als zwei Top Stories; manuelle Redaktion erforderlich')
    edition['stories'] = kept
    return held


def main():
    data = json.loads(PREVIEW.read_text(encoding='utf-8'))
    held = quarantine(data)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = ['# Zurueckgestellte Meldungen (interne Vorschau)', '',
             'Automatisch nur wegen juristischer Stichwoerter zurueckgestellt; keine Faktenbewertung.',
             'Originalentwurf und Quellen bleiben unveraendert.', '']
    lines += [f'- {s.get("title", "Ohne Titel")} — {s.get("source_url", "Quelle unbekannt")}' for s in held]
    if not held:
        lines.append('Keine Meldungen zurueckgestellt.')
    REPORT.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    if held:
        PREVIEW.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Zurueckgestellte Around-the-League-Meldungen: {len(held)}; Bericht: {REPORT}')


if __name__ == '__main__':
    main()
