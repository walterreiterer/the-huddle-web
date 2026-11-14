#!/usr/bin/env python3
"""Fail-closed status check for THE HUDDLE preview; never publishes."""
import json
import sys
from pathlib import Path


def validate(root: Path):
    draft = root / 'drafts/morning-preview.json'
    report = root / 'drafts/gegenpruefung-195.json'
    if not draft.is_file() or not report.is_file():
        return False, 'Vorschau oder Gegenprüfbericht fehlt'
    try:
        preview = json.loads(draft.read_text(encoding='utf-8'))
        review = json.loads(report.read_text(encoding='utf-8'))
    except (ValueError, OSError) as exc:
        return False, 'JSON unlesbar: ' + str(exc)
    if not isinstance(preview, dict) or not isinstance(review, dict):
        return False, 'JSON-Objekt erwartet'
    if preview.get('status') != 'draft' or preview.get('published_at') is not None:
        return False, 'Vorschau ist nicht eindeutig unveröffentlicht'
    editorial = preview.get('editorial_review')
    meta = review.get('metadaten')
    if not isinstance(editorial, dict) or not isinstance(meta, dict):
        return False, 'Prüfmetadaten fehlen'
    if editorial.get('approved') is not False or meta.get('freigabe') is not False:
        return False, 'Unerwartete Freigabekennzeichnung'
    status = review.get('gesamtstatus')
    if status not in ('SPERREN', 'MANUELL_PRUEFEN', 'UNAUFFAELLIG'):
        return False, 'Unbekannter Prüfstatus'
    if editorial.get('status') != status:
        return False, 'Widersprüchlicher Prüfstatus'
    if meta.get('vollstaendig') is not True:
        return False, 'Gegenprüfung unvollständig'
    if status == 'SPERREN':
        return False, 'Redaktionell gesperrt'
    if status == 'MANUELL_PRUEFEN':
        return True, 'Nur interner Entwurf; manuelle Prüfung erforderlich'
    return True, 'Interner Entwurf geprüft; keine Veröffentlichungsfreigabe'


if __name__ == '__main__':
    ok, reason = validate(Path('.'))
    print(('STATUS OK: ' if ok else 'STATUS GESPERRT: ') + reason)
    sys.exit(0 if ok else 1)
