#!/usr/bin/env python3
"""THE HUDDLE 1.9.7: quarantines pre-deadline trade speculation after a configured cutoff.

Conservative, deterministic gate. Does not publish or overwrite the original draft.
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('drafts')
DRAFT = ROOT / 'the-huddle-probeausgabe-193.md'
REPORT = ROOT / 'trade-sperre-197.md'
DATA = ROOT / 'trade-sperre-197.json'
SAFE = ROOT / 'the-huddle-gefilterter-testentwurf-197.md'
MARKER = 'TESTENTWURF – AUTOMATISCH ERSTELLT, NICHT VERÖFFENTLICHEN'

# Only discussions, rumors and projections about trades BEFORE a deadline.
TRADE = re.compile(r'(?i)\b(?:trade|trades|trading|tausch|wechselgespr[aä]ch|handelsgespr[aä]ch)\b')
DEADLINE = re.compile(r'(?i)\b(?:trade[ -]?deadline|trading[ -]?deadline|transferfrist|vor (?:der |dem )?frist|ahead of (?:the )?deadline)\b')
SPECULATION = re.compile(r'(?i)\b(?:m[oö]glich|k[oö]nnte|erw[aä]g|gespr[aä]ch|angebote|interess|soll|reportedly|rumou?r|explor|entertaining|before|ahead of|vor der|vor dem|bis zur)\w*')


def utc_time(value):
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            return None
        return dt.astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return None


def split_sections(text):
    """Preserve original section text, including blank lines and source URLs."""
    parts = re.split(r'(?=^## (?:THE LEAD|AROUND THE LEAGUE|GAME CENTER)\s*$)', text, flags=re.M)
    return parts


def quarantine_section(part, section):
    if section not in ('THE LEAD', 'AROUND THE LEAGUE'):
        return part, []
    lines = part.splitlines(keepends=True)
    heading = lines[0]
    body = ''.join(lines[1:])
    # Each news story begins with a bold headline. Handle multiple stories per section.
    pieces = re.split(r'(?=^\*\*[^\n]+\*\*)', body, flags=re.M)
    kept = []
    blocked = []
    for piece in pieces:
        if not re.match(r'^\*\*[^\n]+\*\*', piece):
            kept.append(piece)
            continue
        if TRADE.search(piece) and DEADLINE.search(piece) and SPECULATION.search(piece):
            title = re.search(r'^\*\*(.*?)\*\*', piece).group(1)
            blocked.append({'section': section, 'title': title, 'reason': 'Spekulative Trade-Meldung mit Fristbezug nach konfigurierter Deadline; aktuellen Stand recherchieren'})
        else:
            kept.append(piece)
    if blocked and not any(re.match(r'^\*\*[^\n]+\*\*', p) for p in kept):
        kept.append('\n*Keine freigegebene Meldung in diesem Abschnitt – redaktionelle Neubewertung erforderlich.*\n\n')
    return heading + ''.join(kept), blocked


def main():
    if not DRAFT.is_file():
        raise SystemExit(f'Pflichtdatei fehlt: {DRAFT}')
    draft = DRAFT.read_text(encoding='utf-8')
    if MARKER not in draft:
        raise SystemExit('Sicherheitsabbruch: Testentwurf-Kennzeichnung fehlt')
    # Require an explicit season-specific, verified cutoff; never silently guess a date.
    cutoff_raw = os.getenv('NFL_TRADE_DEADLINE_UTC: '2026-11-10T21:00:00Z')
    cutoff = utc_time(cutoff_raw)
    now = datetime.now(timezone.utc)
    if not cutoff:
        status = 'FRIST_UNBEKANNT_MANUELL_PRUEFEN'
        reason = 'NFL_TRADE_DEADLINE_UTC fehlt oder ist ungültig. Keine automatische Annahme über den Fristablauf.'
        blocked = []
        safe = draft
    elif now < cutoff:
        status = 'FRIST_NOCH_NICHT_ERREICHT'
        reason = 'Die konfigurierte Trade-Deadline ist noch nicht erreicht; diese Sperre greift noch nicht.'
        blocked = []
        safe = draft
    else:
        blocked = []
        parts = []
        for part in split_sections(draft):
            match = re.match(r'^## (THE LEAD|AROUND THE LEAGUE|GAME CENTER)\s*$', part.split('\n', 1)[0])
            section = match.group(1) if match else ''
            filtered, found = quarantine_section(part, section)
            parts.append(filtered)
            blocked.extend(found)
        safe = ''.join(parts)
        status = 'MELDUNGEN_GESPERRT' if blocked else 'KEIN_TRADE_FRIST_TREFFER'
        reason = 'Konservativer Textfilter: nur spekulative Trade-Meldungen mit Fristbezug; kein Faktencheck.'
    # If cutoff is missing, do not misrepresent an unfiltered draft as a cleared version.
    if not cutoff:
        safe = MARKER + '\n\nFRIST NICHT KONFIGURIERT – KEINE REDAKTIONELLE FREIGABE\n\n' + draft
    result = {'version': '1.9.7', 'status': status, 'checked_at_utc': now.isoformat(),
              'deadline_utc': cutoff.isoformat() if cutoff else None,
              'blocked_count': len(blocked), 'blocked': blocked, 'reason': reason,
              'publication_approved': False}
    ROOT.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    SAFE.write_text(safe, encoding='utf-8')
    report = ['# THE HUDDLE – Trade-Deadline-Sperre 1.9.7', '', '**KEINE VERÖFFENTLICHUNGSFREIGABE.**', '',
              f'**Status:** {status}', f'**Prüfzeitpunkt (UTC):** {now.isoformat()}',
              f'**Konfigurierte Frist (UTC):** {result["deadline_utc"] or "FEHLT"}',
              f'**Zurückgestellte Meldungen:** {len(blocked)}', '', reason, '']
    for item in blocked:
        report.extend([f'- **{item["section"]}: {item["title"]}** – {item["reason"]}'])
    report.extend(['', 'Die Original-Probeausgabe bleibt unverändert. Der gefilterte Testentwurf ist nicht zur Veröffentlichung freigegeben.',
                   'Der Filter kann indirekte oder anders formulierte Spekulationen übersehen und prüft keine Trade-Abschlüsse.', ''])
    REPORT.write_text('\n'.join(report), encoding='utf-8')
    print(f'Trade-Sperre 1.9.7: {status}; zurückgestellt: {len(blocked)}; keine Veröffentlichung')


if __name__ == '__main__':
    main()
