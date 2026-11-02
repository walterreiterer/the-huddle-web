#!/usr/bin/env python3
"""THE HUDDLE 1.0: collect attributed, extractable NFL reporting. No AI calls."""
import datetime as dt
import hashlib
import json
import re
import urllib.parse
from pathlib import Path
import feedparser
import requests
import trafilatura
from googlenewsdecoder import gnewsdecoder

SOURCES = {'Yahoo Sports': 'sports.yahoo.com', 'NBC Sports': 'nbcsports.com',
           'FOX Sports': 'foxsports.com', 'NFL.com': 'nfl.com'}
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; TheHuddle/1.0; editorial source test)'}
EXCLUDE = re.compile(r'\b(betting|sportsbook|odds|parlay|prop bets?|gambling|fantasy|mock draft|how to watch|watch live|streaming guide|picks against the spread)\b', re.I)
MAX_PER_SOURCE = 4
MIN_WORDS = 120

def resolve(url):
    if urllib.parse.urlparse(url).hostname != 'news.google.com':
        return url
    result = gnewsdecoder(url, interval=1)
    return result.get('decoded_url') if (result.get('status') or result.get('success')) else None

def host_matches(url, domain):
    host = (urllib.parse.urlparse(url).hostname or '').lower()
    return host == domain or host.endswith('.' + domain)

def get_feed(domain):
    query = urllib.parse.quote(f'site:{domain} NFL when:3d')
    url = f'https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en'
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    return feedparser.parse(r.content).entries

def main():
    now = dt.datetime.now(dt.timezone.utc)
    items, audit, seen_urls, seen_titles = [], [], set(), set()
    for source, domain in SOURCES.items():
        good = attempted = 0
        try:
            entries = get_feed(domain)
        except Exception as exc:
            audit.append(f'- {source}: Feedfehler {type(exc).__name__}: {str(exc)[:100]}')
            continue
        for entry in entries:
            if good >= MAX_PER_SOURCE or attempted >= 12:
                break
            title = re.sub(r'\s+', ' ', entry.get('title', '')).strip()
            if not title or EXCLUDE.search(title):
                continue
            normalized = re.sub(r'[^a-z0-9]+', '', title.lower())
            if normalized in seen_titles:
                continue
            attempted += 1
            try:
                url = resolve(entry.get('link', ''))
                if not url or not host_matches(url, domain):
                    continue
                response = requests.get(url, headers=HEADERS, timeout=22)
                response.raise_for_status()
                final_url = response.url
                if not host_matches(final_url, domain) or final_url in seen_urls:
                    continue
                article = trafilatura.extract(response.text, include_comments=False, include_tables=False) or ''
                words = len(article.split())
                if words < MIN_WORDS:
                    continue
                seen_urls.add(final_url)
                seen_titles.add(normalized)
                good += 1
                items.append({'source': source, 'title': title, 'url': final_url,
                              'published': entry.get('published', ''), 'words': words,
                              'text': article[:9500]})
            except Exception:
                continue
        audit.append(f'- {source}: {good} Artikel extrahiert ({attempted} Kandidaten geprüft)')
    Path('drafts').mkdir(exist_ok=True)
    Path('drafts/quellen-10.json').write_text(json.dumps({'collected_utc': now.isoformat(), 'articles': items}, ensure_ascii=False, indent=2), encoding='utf-8')
    Path('drafts/quellenbericht-10.md').write_text('# THE HUDDLE 1.0 – Quellenbericht\n\n' + '\n'.join(audit) + f'\n\nInsgesamt: {len(items)} Artikel.\n', encoding='utf-8')
    print('\n'.join(audit))
    print(f'Gesammelt: {len(items)} Artikel')

if __name__ == '__main__':
    main()
