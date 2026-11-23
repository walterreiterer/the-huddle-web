#!/usr/bin/env python3
"""Internal preview: place the approved-to-review Markdown into existing site shell.
Never publishes or overwrites index.html. Game/standings/video data stay as template examples.
"""
import argparse
import re
from pathlib import Path
from bs4 import BeautifulSoup
import mistune


def split_draft(text):
    headings = list(re.finditer(r'(?m)^##\s+(.+?)\s*$', text))
    sections = {}
    for i, match in enumerate(headings):
        sections[match.group(1).strip().lower()] = text[match.end():headings[i + 1].start() if i + 1 < len(headings) else len(text)].strip()
    def pick(*names):
        for name in names:
            if name in sections:
                return sections[name]
        return ''
    return pick('60-sekunden-brief', 'die nfl in 60 sekunden'), pick('top stories'), pick('austrian watch')


def nodes(soup, markdown):
    fragment = BeautifulSoup(mistune.create_markdown(escape=True)(markdown), 'html.parser')
    return list(fragment.contents)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--template', default='index.html')
    p.add_argument('--draft', default='drafts/leserfassung-20.md')
    p.add_argument('--output', default='drafts/the-huddle-layout-vorschau.html')
    args = p.parse_args()
    original = Path(args.template).read_text(encoding='utf-8')
    text = Path(args.draft).read_text(encoding='utf-8')
    brief, stories, austria = split_draft(text)
    if not brief or not stories:
        raise SystemExit('Fehlende Pflichtabschnitte: 60-Sekunden-Brief / Top Stories')
    soup = BeautifulSoup(original, 'html.parser')
    hero = soup.find(id='morning')
    story_section = soup.find(id='stories')
    if hero is None or story_section is None:
        raise SystemExit('Website-Vorlage ohne #morning oder #stories')
    lead = hero.select_one('.lead-text')
    if lead is None:
        raise SystemExit('Website-Vorlage ohne .lead-text')
    lead.clear()
    for n in nodes(soup, brief):
        lead.append(n)
    container = story_section.select_one('.stories')
    if container is None:
        raise SystemExit('Website-Vorlage ohne .stories')
    container.clear()
    parts = re.split(r'(?m)^###\s+(.+?)\s*$', stories)
    items = [(parts[i].strip(), parts[i + 1].strip()) for i in range(1, len(parts)-1, 2)]
    if not items:
        raise SystemExit('Keine Top Stories mit ### Überschrift')
    aside = hero.select_one('aside.sidebar ol')
    if aside:
        aside.clear()
    for i, (title, body) in enumerate(items, 1):
        article = soup.new_tag('article', attrs={'class':'story', 'id':f'story-{i}'})
        kicker = soup.new_tag('div', attrs={'class':'kicker'})
        kicker.string = 'TOP STORY'
        article.append(kicker)
        heading = soup.new_tag('h3')
        heading.string = title
        article.append(heading)
        for n in nodes(soup, body):
            article.append(n)
        container.append(article)
        if aside:
            li = soup.new_tag('li')
            a = soup.new_tag('a', href=f'#story-{i}')
            a.string = title
            li.append(a)
            aside.append(li)
    count = story_section.select_one('.section-head small')
    if count:
        count.string = f'{len(items)} Meldungen'
    austrian = soup.find(id='austria')
    if austrian and austria:
        for n in list(austrian.children):
            if getattr(n, 'name', None) not in ('div', 'h2'):
                n.decompose() if hasattr(n, 'decompose') else n.extract()
        for n in nodes(soup, austria):
            austrian.append(n)
    # Editorially requested order: top stories above game center.
    story_section.extract()
    hero.insert_after(story_section)
    notice = soup.select_one('.draft-notice')
    if notice:
        notice.string = ('INTERNE LAYOUT-VORSCHAU – NICHT VERÖFFENTLICHEN. '
                         'Nachrichten aus der neuen Leserfassung; Game Center, Tabellen und Videos '
                         'sind unveränderte Beispieldaten der Website-Vorlage und NICHT aktualisiert.')
    if soup.head:
        meta = soup.new_tag('meta', attrs={'name':'robots','content':'noindex,nofollow'})
        soup.head.append(meta)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(str(soup), encoding='utf-8')
    print(f'Interne Layout-Vorschau: {out} ({len(items)} Top Stories), keine Veröffentlichung')

if __name__ == '__main__':
    main()
