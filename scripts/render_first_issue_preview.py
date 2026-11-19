#!/usr/bin/env python3
"""Render THE HUDDLE's current Markdown draft as a local, unpublished HTML preview."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import html
import re
import mistune

ROOT = Path('drafts')
DRAFT = ROOT / 'the-huddle-erstausgabe.md'
SITE = Path('index.html')
OUT = ROOT / 'the-huddle-vorschau.html'


def split_sections(markdown):
    parts = re.split(r'(?m)^## (Die NFL in 60 Sekunden|Top Stories|Austrian Watch|Game Center|Quellen und Redaktionshinweise)\s*$', markdown)
    preamble = parts[0]
    sections = {parts[i].strip(): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
    return preamble, sections


def md(value):
    return mistune.create_markdown(escape=True)(value)


def clean_game_center(raw):
    lines = []
    for line in raw.splitlines():
        t = line.strip()
        if not t:
            continue
        if t.startswith('# THE HUDDLE – NFL Game Center') or t.startswith('Abrufzeit Wien:'):
            continue
        if t.startswith('> ESPN-Spielstandsdaten') or t.startswith('Datenquelle:'):
            continue
        if t.startswith('## Spieltag '):
            lines.append(('day', t.removeprefix('## Spieltag ').replace(' (Wien)', '')))
        elif t.startswith('- ENDE:') or t.startswith('- GEPLANT') or t.startswith('- LIVE'):
            lines.append(('game', t[2:]))
    # Only render day headings with at least one game.
    rendered = []
    day = None
    games = []
    def flush():
        if day is not None and games:
            rendered.append('<h3 class="preview-day">' + html.escape(day) + '</h3>')
            rendered.append('<div class="preview-games">' + ''.join(games) + '</div>')
    for kind, value in lines:
        if kind == 'day':
            flush()
            day = value
            games = []
        elif day is not None:
            status = 'ENDE' if value.startswith('ENDE') else ('LIVE' if value.startswith('LIVE') else 'GEPLANT')
            games.append('<article class="preview-game"><span class="game-status">' + status + '</span><div>' + md(value).strip().removeprefix('<p>').removesuffix('</p>') + '</div></article>')
    flush()
    return '\n'.join(rendered) or '<p>Keine Begegnungen im erfassten Zeitraum.</p>'


def main():
    source = DRAFT.read_text(encoding='utf-8')
    _, sections = split_sections(source)
    required = ('Die NFL in 60 Sekunden', 'Top Stories', 'Austrian Watch', 'Game Center')
    missing = [name for name in required if name not in sections]
    if missing:
        raise RuntimeError('Fehlende Entwurfsabschnitte: ' + ', '.join(missing))
    site = SITE.read_text(encoding='utf-8')
    styles = '\n'.join(re.findall(r'<style(?:\s[^>]*)?>(.*?)</style>', site, re.S | re.I))
    title_match = re.search(r'^# THE HUDDLE\s*[–-]\s*(.+)$', source, re.M)
    edition = title_match.group(1).strip() if title_match else datetime.now(ZoneInfo('Europe/Vienna')).strftime('%d.%m.%Y')
    css = '''
    .preview-shell{max-width:1160px;margin:0 auto;padding:0 22px 50px}
    .preview-banner{margin:24px 0;padding:13px 17px;border:1px solid #f47d78;border-radius:9px;color:#fff;background:#192b45;font-size:13px}
    .preview-header{padding:30px 0 16px;border-bottom:1px solid #344863}
    .preview-kicker{color:#f47d78;font-size:11px;font-weight:800;letter-spacing:.2em}
    .preview-logo{font-size:clamp(38px,5vw,62px);font-weight:950;letter-spacing:-.07em;color:white;line-height:1.15}
    .preview-logo span{color:#f47d78}
    .preview-sub{color:#c8d5e9}
    .preview-credit{font-size:12px;color:#aebfda;margin-top:12px}
    .preview-credit a,.preview-shell a{color:#9ed2ff}
    .preview-section{background:#192b45;border:1px solid #344863;border-radius:10px;padding:22px 26px;margin:22px 0}
    .preview-section h2{font-size:23px;color:white;margin:0 0 17px}
    .preview-section h3{font-size:18px;color:#fff;margin:24px 0 9px}
    .preview-section p,.preview-section li{line-height:1.68;color:#e6efff}
    .preview-section p{margin:9px 0 15px}
    .preview-day{padding-top:9px;border-top:1px solid #344863}
    .preview-games{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:10px}
    .preview-game{border:1px solid #425b7c;border-radius:9px;padding:13px 15px;background:#0c1422;line-height:1.5;color:#e6efff;font-size:14px}
    .game-status{display:block;color:#f47d78;font-weight:800;font-size:11px;margin-bottom:6px}
    .preview-game p{margin:0}
    .preview-footer{font-size:12px;color:#aebfda;padding:14px 0 30px}
    @media(max-width:650px){.preview-section{padding:18px 16px}.preview-games{grid-template-columns:1fr}}
    '''
    # No user-controlled HTML is inserted without escaping/markdown safe mode.
    result = f'''<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>THE HUDDLE – Vorschau {html.escape(edition)}</title><style>{styles}\n{css}</style></head><body><main class="preview-shell">
    <header class="preview-header"><div class="preview-kicker">INDEPENDENT NFL MORNING JOURNAL</div><div class="preview-logo">THE HUDDLE<span>.</span></div><p class="preview-sub">Die NFL-Nacht. Auf den Punkt. Für Europa.</p><div class="preview-credit">Ein Projekt von <a href="https://football-austria.com/">Football-Austria.com</a> · Mit journalistischer Erfahrung und ChatGPT entwickelt.</div></header>
    <div class="preview-banner"><strong>INTERNE VORSCHAU</strong> · {html.escape(edition)} · Nicht freigegeben, nicht veröffentlicht.</div>
    <section class="preview-section" id="morning"><h2>Die NFL in 60 Sekunden</h2>{md(sections['Die NFL in 60 Sekunden'])}</section>
    <section class="preview-section" id="stories"><h2>Top Stories</h2>{md(sections['Top Stories'])}</section>
    <section class="preview-section" id="austria"><h2>Austrian Watch</h2>{md(sections['Austrian Watch'])}</section>
    <section class="preview-section" id="games"><h2>Game Center</h2>{clean_game_center(sections['Game Center'])}</section>
    <footer class="preview-footer">INTERNE VORSCHAU – journalistische Freigabe ausständig. Keine öffentliche Veröffentlichung.</footer></main></body></html>'''
    OUT.write_text(result, encoding='utf-8')
    print(f'HTML-Vorschau erstellt: {OUT} ({OUT.stat().st_size} Bytes)')


if __name__ == '__main__':
    main()
