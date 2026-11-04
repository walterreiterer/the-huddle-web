#!/usr/bin/env python3
"""THE HUDDLE: attributed NFL reporting and targeted Austrian Watch research. No AI calls."""
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

# Keep existing international sources and add Austrian/German-language outlets.
SOURCES = {
    'Yahoo Sports': 'sports.yahoo.com',
    'NBC Sports': 'nbcsports.com',
    'FOX Sports': 'foxsports.com',
    'NFL.com': 'nfl.com',
    'ORF Sport': 'orf.at',
    'Sky Sport Austria': 'skysportaustria.at',
    'Kronen Zeitung': 'krone.at',
    'Kurier': 'kurier.at',
    'Der Standard': 'derstandard.at',
    'LAOLA1': 'laola1.at',
    'Kleine Zeitung': 'kleinezeitung.at',
    'Heute': 'heute.at',
    'Die Presse': 'diepresse.com',
    'Tiroler Tageszeitung': 'tt.com',
    'Kicker': 'kicker.de',
}
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; TheHuddle/1.1; editorial source test)'}
EXCLUDE = re.compile(r'\b(betting|sportsbook|odds|parlay|prop bets?|gambling|fantasy|mock draft|how to watch|watch live|streaming guide|picks against the spread)\b', re.I)
AUSTRIAN_TERMS = re.compile(r'\b(raimann|senn|österreich(?:isch(?:e[rsnm]?)?)?|austrian|colts|cardinals)\b', re.I)
MAX_PER_SOURCE = 4
MAX_PER_AUSTRIAN_QUERY = 5
MIN_WORDS = 120

# Queries are restricted to NFL context to avoid unrelated names and topics.
AUSTRIAN_QUERIES = (
    '"Bernhard Raimann" NFL when:3d',
    '"Valentin Senn" NFL when:3d',
    '("Österreicher" OR "österreichischer") NFL when:3d',
)


def resolve(url):
    if urllib.parse.urlparse(url).hostname != 'news.google.com':
        return url
    result = gnewsdecoder(url, interval=1)
    return result.get('decoded_url') if (result.get('status') or result.get('success')) else None


def host_matches(url, domain):
    host = (urllib.parse.urlparse(url).hostname or '').lower()
    return host == domain or host.endswith('.' + domain)


def get_feed(query, german=False):
    encoded = urllib.parse.quote(query)
    locale = 'hl=de-AT&gl=AT&ceid=AT:de' if german else 'hl=en-US&gl=US&ceid=US:en'
    url = f'https://news.google.com/rss/search?q={encoded}&{locale}'
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    return feedparser.parse(r.content).entries


def clean_title(title):
    return re.sub(r'\s+', ' ', title or '').strip()


def title_key(title):
    return re.sub(r'[^\w]+', '', title.casefold(), flags=re.UNICODE)


def canonical_url(url):
    parts = urllib.parse.urlsplit(url)
    path = parts.path.rstrip('/') or '/'
    return urllib.parse.urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, '', ''))


def main():
    now = dt.datetime.now(dt.timezone.utc)
    items, audit, seen_urls, seen_titles = [], [], set(), set()
    session = requests.Session()
    session.headers.update(HEADERS)

    def collect(entries, source, domain, limit, label, austrian_watch=False):
        good = attempted = 0
        for entry in entries:
            if good >= limit or attempted >= 12:
                break
            title = clean_title(entry.get('title', ''))
            if not title or EXCLUDE.search(title):
                continue
            normalized = title_key(title)
            if normalized in seen_titles:
                continue
            attempted += 1
            try:
                url = resolve(entry.get('link', ''))
                if not url or not host_matches(url, domain):
                    continue
                response = session.get(url, timeout=22)
                response.raise_for_status()
                final_url = response.url
                if not host_matches(final_url, domain):
                    continue
                key = canonical_url(final_url)
                if key in seen_urls:
                    continue
                article = trafilatura.extract(response.text, include_comments=False, include_tables=False) or ''
                words = len(article.split())
                if words < MIN_WORDS:
                    continue
                # Do not alter the fields expected by downstream scripts.
                items.append({'source': source, 'title': title, 'url': final_url,
                              'published': entry.get('published', ''), 'words': words,
                              'text': article[:9500]})
                seen_urls.add(key)
                seen_titles.add(normalized)
                good += 1
            except Exception:
                continue
        audit.append(f'- {label}: {good} Artikel extrahiert ({attempted} Kandidaten geprüft)')

    for source, domain in SOURCES.items():
        german = source not in ('Yahoo Sports', 'NBC Sports', 'FOX Sports', 'NFL.com')
        query = f'site:{domain} NFL when:3d'
        try:
            entries = get_feed(query, german=german)
            collect(entries, source, domain, MAX_PER_SOURCE, source)
        except Exception as exc:
            audit.append(f'- {source}: Feedfehler {type(exc).__name__}: {str(exc)[:100]}')

    # Dedicated cross-publication search for Austrian players.
    # Restrict results to known domains, preserving source attribution.
    for query in AUSTRIAN_QUERIES:
        try:
            entries = get_feed(query, german=True)
        except Exception as exc:
            audit.append(f'- Austrian Watch ({query}): Feedfehler {type(exc).__name__}: {str(exc)[:100]}')
            continue
        count = 0
        for source, domain in SOURCES.items():
            if count >= MAX_PER_AUSTRIAN_QUERY:
                break
            before = len(items)
            collect(entries, source, domain, MAX_PER_AUSTRIAN_QUERY - count,
                    f'Austrian Watch / {source} / {query}')
            count += len(items) - before

    Path('drafts').mkdir(exist_ok=True)
    Path('drafts/quellen-10.json').write_text(
        json.dumps({'collected_utc': now.isoformat(), 'articles': items}, ensure_ascii=False, indent=2),
        encoding='utf-8')
    Path('drafts/quellenbericht-10.md').write_text(
        '# THE HUDDLE 1.1 – Quellenbericht\n\n' + '\n'.join(audit) +
        f'\n\nInsgesamt: {len(items)} Artikel.\n'
        '\nHinweis: Google-News-Suchtreffer sind Kandidaten, keine journalistische Bestätigung. '
        'Fehlende Volltexte (z. B. Paywalls) werden übersprungen.\n',
        encoding='utf-8')
    print('\n'.join(audit))
    print(f'Gesammelt: {len(items)} Artikel')


if __name__ == '__main__':
    main()
