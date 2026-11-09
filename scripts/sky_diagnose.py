#!/usr/bin/env python3
"""Isolierter, schonender Sky-Sport-Austria-Zugriffstest. Keine Pipeline-Aenderung."""
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

BASE = 'https://www.skysportaustria.at'
INDEX = BASE + '/american-football/'
OUT = Path('sky-diagnose.json')
HEADERS = {'User-Agent': 'TheHuddleEditorialDiagnostic/1.0 (public-page-access-check)', 'Accept': 'text/html,application/xhtml+xml'}

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.href = None
        self.text = []
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.href = dict(attrs).get('href')
            self.text = []
    def handle_data(self, data):
        if self.href is not None:
            self.text.append(data)
    def handle_endtag(self, tag):
        if tag == 'a' and self.href is not None:
            title = re.sub(r'\s+', ' ', ''.join(self.text)).strip()
            if title:
                self.links.append((title, self.href))
            self.href = None
            self.text = []

def probe(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read(800_000)
            encoding = resp.headers.get_content_charset() or 'utf-8'
            return {'status': resp.status, 'final_url': resp.geturl(), 'content_type': resp.headers.get('Content-Type', ''), 'bytes_read': len(data)}, data.decode(encoding, errors='replace')
    except urllib.error.HTTPError as exc:
        return {'status': exc.code, 'error': 'HTTPError', 'reason': exc.reason}, ''
    except Exception as exc:
        return {'error': type(exc).__name__, 'detail': str(exc)[:180]}, ''

def main():
    report = {'checked_utc': datetime.now(timezone.utc).isoformat(), 'index_url': INDEX}
    index_result, html = probe(INDEX)
    report['index'] = index_result
    print('Sky-Uebersicht:', index_result)
    if html:
        parser = LinkParser()
        parser.feed(html)
        candidates = []
        seen = set()
        for title, href in parser.links:
            url = urllib.parse.urljoin(INDEX, href)
            parts = urllib.parse.urlparse(url)
            if parts.netloc not in ('www.skysportaustria.at', 'skysportaustria.at'):
                continue
            if not parts.path.strip('/') or parts.path.rstrip('/') == '/american-football':
                continue
            if not re.search(r'raimann|colts|nfl|football|bengals|chiefs|quarterback|super-bowl|international', title + ' ' + url, re.I):
                continue
            url = urllib.parse.urlunparse(parts._replace(fragment='', query=''))
            if url not in seen:
                seen.add(url)
                candidates.append({'title': title, 'url': url})
        report['candidate_links'] = candidates[:15]
        print('Passende Links auf der Uebersicht:', len(candidates))
        for candidate in candidates[:8]:
            print('-', candidate['title'][:90], candidate['url'])
        if candidates:
            result, article_html = probe(candidates[0]['url'])
            result['title'] = candidates[0]['title']
            result['url'] = candidates[0]['url']
            result['html_title_found'] = bool(re.search(r'<title\b', article_html, re.I))
            report['sample_article'] = result
            print('Einzelartikel:', result)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Diagnose gespeichert:', OUT)
    print('Keine Artikeltexte gespeichert; keine Zugangssperren umgangen.')

if __name__ == '__main__':
    main()
