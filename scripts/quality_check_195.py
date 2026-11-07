#!/usr/bin/env python3
"""THE HUDDLE 1.9.5: reproducible editorial quality signals, no AI/API calls."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, unquote

D = Path('drafts')
DRAFT = D / 'the-huddle-probeausgabe-193.md'
TOPICS = D / 'themenauswahl-193.md'
GAMES = D / 'nfl-spiele-08.md'
REVIEW = D / 'gegenpruefung-194.json'
OUTPUT = D / 'qualitaetskontrolle-195.md'
JSON_OUTPUT = D / 'qualitaetskontrolle-195.json'


def canonical_url(url):
    p = urlsplit(url.rstrip(').,;'))
    return (p.netloc.lower().removeprefix('www.') + unquote(p.path).rstrip('/')).lower()


def section(text, start, end=None):
    pattern = r'(?im)^##\s+' + re.escape(start) + r'\s*$'
    m = re.search(pattern, text)
    if not m:
        return ''
    tail = text[m.end():]
    if end:
        n = re.search(r'(?im)^##\s+' + re.escape(end) + r'\s*$', tail)
    else:
        n = re.search(r'(?m)^##\s+', tail)
    return tail[:n.start()] if n else tail


def selected_topics(text):
    part = section(text, 'Ausgewählt', 'Zurückgestellt')
    out = []
    for line in part.splitlines():
        m = re.match(r'^\s*\d+\.\s+(.+?)\s+—\s+(\d+)\s+Punkte\s+—\s+(https?://\S+)', line)
        if m:
            out.append({'title': m.group(1), 'points': int(m.group(2)), 'url': m.group(3)})
    return out


def message_blocks(draft):
    parts = []
    for label in ('THE LEAD', 'AROUND THE LEAGUE'):
        sec = section(draft, label)
        for block in re.split(r'\n\s*\n', sec):
            if 'http' not in block:
                continue
            links = re.findall(r'https?://[^\s)]+', block)
            if links:
                parts.append({'section': label, 'text': block, 'links': links})
    return parts


def main():
    for path in (DRAFT, TOPICS, GAMES, REVIEW):
        if not path.exists():
            raise SystemExit(f'Pflichtdatei fehlt: {path}')
    draft = DRAFT.read_text(encoding='utf-8')
    topics = selected_topics(TOPICS.read_text(encoding='utf-8'))
    if not topics:
        raise SystemExit('Themenauswahl konnte nicht gelesen werden: Format prüfen')
    games = GAMES.read_text(encoding='utf-8')
    review = json.loads(REVIEW.read_text(encoding='utf-8'))
    blocks = message_blocks(draft)
    used = {canonical_url(url) for b in blocks for url in b['links']}
    missing = [{**t, 'rank': i} for i, t in enumerate(topics, 1) if canonical_url(t['url']) not in used]
    # These are heuristic editorial prompts, not confirmed mistakes.
    language_patterns = [
        (r'\bReinstattung\b', '„Reinstattung“: vermutlich „Wiederaufnahme“ oder „Wiedereinsetzung“'),
        (r'\bnicht-divisionär\w*\b', 'Ungebräuchliche Formulierung: „außerhalb der Division“ prüfen'),
        (r'\bfluid\b', 'Englisches Wort „fluid“: als Zitat kenntlich machen oder übersetzen'),
    ]
    language = []
    for pattern, hint in language_patterns:
        for match in re.finditer(pattern, draft, flags=re.I):
            language.append({'term': match.group(), 'hint': hint})
    game_center = section(draft, 'GAME CENTER', 'AROUND THE LEAGUE')
    league = section(draft, 'AROUND THE LEAGUE')
    # Detect repeated score pairs, not merely team mentions.
    scores = re.findall(r'\b(\d{1,2})\s*[:–-]\s*(\d{1,2})\b', game_center)
    duplicates = []
    for a, b in set(scores):
        if re.search(r'(?<!\d)' + re.escape(a) + r'\s*[:–-]\s*' + re.escape(b) + r'(?!\d)', league):
            duplicates.append({'score': f'{a}:{b}', 'hint': 'Ergebnis erscheint auch in AROUND THE LEAGUE: Zusatznutzen der Meldung prüfen'})
    # Reflect independent review warnings without claiming the underlying facts are true.
    open_reviews = [{'title': m.get('titel', ''), 'status': m.get('status', '')}
                    for m in review.get('meldungen', []) if m.get('status') not in ('UNAUFFAELLIG', 'BELEGT')]
    result = {
        'version': '1.9.5', 'status': 'MANUELL_PRUEFEN' if (language or missing or duplicates or open_reviews) else 'KEINE_HEURISTISCHEN_TREFFER',
        'selected_topics': len(topics), 'draft_message_blocks': len(blocks),
        'missing_selected_topics': missing, 'language_flags': language,
        'game_center_overlap': duplicates, 'independent_review_open': open_reviews,
        'note': 'Heuristische Hinweise, keine eigenständige Faktenprüfung und keine Veröffentlichungsfreigabe.'
    }
    lines = [
        '# THE HUDDLE – Qualitätskontrolle 1.9.5', '',
        '**KEINE VERÖFFENTLICHUNGSFREIGABE – menschliche Redaktion entscheidet.**', '',
        f"**Status:** {result['status']}",
        f"**Ausgewählte Themen:** {len(topics)} · **Nachrichtenblöcke:** {len(blocks)}", '',
        '## Sprachliche Auffälligkeiten', ''
    ]
    lines += [f"- **{x['term']}** – {x['hint']}" for x in language] or ['- Keine Treffer in der aktuellen kleinen Prüfliste.']
    lines += ['', '## Ausgewählte Themen ohne direkten Quellenlink im Nachrichtenteil', '']
    lines += [f"- **Rang {x['rank']} ({x['points']} Punkte):** {x['title']} – {x['url']}" for x in missing] or ['- Alle ausgewählten Themen haben einen Quellenlink im Nachrichtenteil.']
    lines += ['', '## Mögliche Überschneidungen mit dem Game Center', '']
    lines += [f"- **{x['score']}** – {x['hint']}" for x in duplicates] or ['- Keine identischen Ergebniszahlen im Nachrichtenteil erkannt.']
    lines += ['', '## Offene Hinweise aus der Gegenprüfung 1.9.4', '']
    lines += [f"- **{x['status']}:** {x['title']}" for x in open_reviews] or ['- Keine offenen Statusmeldungen im Prüfbericht.']
    lines += ['', '## Grenzen', '',
              '- Fehlende Themen können redaktionell bewusst ausgelassen sein; es ist kein automatischer Fehler.',
              '- Ein wiederholtes Ergebnis ist nicht automatisch eine überflüssige Nachricht.',
              '- Sprachmuster erkennen nur definierte Auffälligkeiten, keine vollständige Rechtschreibprüfung.',
              '- Der Abgleich erfolgt anhand von Quellenlinks; die tatsächliche Verwendung des Inhalts wird nicht semantisch bewertet.',
              '- Diese Prüfung verwendet keine API und veröffentlicht nichts.', '']
    D.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text('\n'.join(lines), encoding='utf-8')
    JSON_OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"Qualitätskontrolle 1.9.5 erstellt: {result['status']} – {len(language)} Sprache, {len(missing)} Themen, {len(duplicates)} Überschneidungen")


if __name__ == '__main__':
    main()
