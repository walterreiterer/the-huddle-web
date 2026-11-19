#!/usr/bin/env python3
"""One-run editorial draft. Consumes freshly collected local files; no GitHub artifact chain."""
import json
import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from openai import OpenAI

ROOT = Path('drafts')
NOW = datetime.now(timezone.utc)
MODEL = os.getenv('HUDDLE_EDITORIAL_MODEL', 'gpt-5-mini')


def published(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)
    except (ValueError, AttributeError):
        try:
            return parsedate_to_datetime(value).astimezone(timezone.utc)
        except (ValueError, TypeError, IndexError):
            return None


def main():
    raw = json.loads((ROOT / 'quellen-10.json').read_text(encoding='utf-8'))
    articles = []
    seen = set()
    for item in raw.get('articles', []):
        stamp = published(item.get('published'))
        if stamp is None or not NOW - timedelta(hours=72) <= stamp <= NOW + timedelta(hours=2):
            continue
        title = item.get('title', '').strip()
        url = item.get('url', '')
        body = item.get('text', '').strip()
        if not title or not url.startswith('https://') or len(body.split()) < 120:
            continue
        key = re.sub(r'[^\w]', '', title.casefold())
        if key in seen:
            continue
        seen.add(key)
        articles.append({
            'source': item.get('source'), 'title': title, 'url': url,
            'published_utc': stamp.isoformat(), 'text': body[:3400]
        })
    articles.sort(key=lambda a: a['published_utc'], reverse=True)
    # Cap by source so that the brief has a usable mix rather than a single outlet.
    selected, counts = [], {}
    for item in articles:
        src = item['source']
        if counts.get(src, 0) >= 3:
            continue
        selected.append(item)
        counts[src] = counts.get(src, 0) + 1
        if len(selected) >= 15:
            break
    if not selected:
        raise RuntimeError('Keine aktuellen, ausreichend belegten NFL-Artikel gesammelt. Keine KI-Ausgabe erzeugt.')

    game_center = (ROOT / 'nfl-spiele-08.md').read_text(encoding='utf-8')
    # Game Center is deterministic ESPN output; AI may only reproduce it, not fill gaps.
    context = {
        'stand_wien': NOW.astimezone(ZoneInfo('Europe/Vienna')).strftime('%d.%m.%Y %H:%M'),
        'articles': selected,
        'game_center_espn': game_center[:13000],
    }
    instructions = '''Du bist die Redaktion von THE HUDDLE, dem deutschsprachigen NFL-Morgenjournal von Football-Austria.com.
Erstelle einen lesbaren, präzisen journalistischen MARKDOWN-ENTWURF auf Deutsch mit:
# THE HUDDLE – Datum (Wien)
## Die NFL in 60 Sekunden (ca. 90–130 Wörter)
## Top Stories (bis zu 4 eigenständige Meldungen, je ca. 70–110 Wörter)
## Austrian Watch (nur wenn Quellen konkrete, belegte Neuigkeiten zu österreichischen NFL-Spielern enthalten; andernfalls ehrlich „Keine neue belegte Meldung“)
## Game Center (relevante ESPN-Spielstände mit Datum; nur als ENDE markierte Resultate als Endstand ausgeben, geplante und laufende Spiele getrennt kennzeichnen)
## Quellen und Redaktionshinweise
Schreibe ausschließlich Fakten, die im gelieferten Quellenmaterial stehen. Keine erfundenen Details, Verletzungsfolgen, Zitate, Transfers, Spielstände oder Quellen. Meldungen aus verschiedenen Artikeln zum selben Ereignis zusammenführen. Bei schwacher Nachrichtenlage lieber kürzer schreiben. Jede Top Story braucht einen direkten Quellenlink. Behandle unbestätigte Aussagen als solche. Datumsangaben beachten. Austrian Watch ist kein Pflichtfüller: Bernhard Raimann oder Valentin Senn nur mit konkretem Quellenbeleg nennen. Im Game Center nur die gelieferten ESPN-Daten wiedergeben, keine Resultate ergänzen. Keine automatische Veröffentlichung. Abschließen mit „ENTWURF – journalistische Prüfung und Freigabe ausständig.“'''
    client = OpenAI(api_key=os.environ['OPENAI_API_KEY'], timeout=120, max_retries=1)
    response = client.responses.create(
        model=MODEL, instructions=instructions,
        input=json.dumps(context, ensure_ascii=False),
        max_output_tokens=3500, store=False,
    )
    draft = (response.output_text or '').strip()
    if response.status != 'completed' or len(draft) < 600:
        raise RuntimeError(f'KI-Entwurf nicht vollständig: {response.status}; {len(draft)} Zeichen')
    if 'ENTWURF' not in draft:
        draft += '\n\n**ENTWURF – journalistische Prüfung und Freigabe ausständig.**'
    ROOT.mkdir(exist_ok=True)
    (ROOT / 'the-huddle-erstausgabe.md').write_text(draft + '\n', encoding='utf-8')
    meta = {
        'generated_utc': NOW.isoformat(), 'model': MODEL,
        'sources_eligible': len(articles), 'sources_passed_to_model': len(selected),
        'source_urls': [a['url'] for a in selected],
        'response_status': response.status,
        'approved': False, 'published': False,
        'input_tokens': getattr(response.usage, 'input_tokens', None),
        'output_tokens': getattr(response.usage, 'output_tokens', None),
    }
    (ROOT / 'the-huddle-erstausgabe-meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Entwurf erzeugt: {len(selected)} aktuelle Quellen, {len(draft)} Zeichen, Modell {MODEL}')


if __name__ == '__main__':
    main()
