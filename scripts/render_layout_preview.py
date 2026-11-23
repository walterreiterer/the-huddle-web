#!/usr/bin/env python3
"""THE HUDDLE: ausschließlich interne HTML-Vorschau; keine Veröffentlichung."""
import argparse
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from bs4 import BeautifulSoup
import mistune

VIDEOS = [
    ("San Francisco 49ers vs. Minnesota Vikings", "GB-Z_Z8I2S0"),
    ("Kansas City Chiefs vs. Arizona Cardinals", "TkeWhgqe9BY"),
    ("Denver Broncos vs. Las Vegas Raiders", "-cd4u0-TuUI"),
    ("New York Giants vs. Jacksonville Jaguars", "pSWxdYxFkm0"),
    ("Tampa Bay Buccaneers vs. Detroit Lions", "UMX8nztxkd0"),
    ("Houston Texans vs. Indianapolis Colts", "bsE4-g21YwQ"),
    ("Los Angeles Chargers vs. New York Jets", "0_GUgVFQ-wA"),
]

def sections(text):
    hits = list(re.finditer(r'(?m)^##\s+(.+?)\s*$', text))
    return {m.group(1).strip().lower(): text[m.end():hits[i+1].start() if i+1<len(hits) else len(text)].strip()
            for i,m in enumerate(hits)}

def fragment(md):
    return list(BeautifulSoup(mistune.create_markdown(escape=True)(md), "html.parser").contents)

def replace_children(node, children):
    node.clear()
    for child in children:
        node.append(child)

def add_text(soup, parent, tag, value, cls=None):
    el = soup.new_tag(tag, attrs={"class": cls} if cls else {})
    el.string = str(value)
    parent.append(el)
    return el

def game_card(soup, game):
    card = soup.new_tag("article", attrs={"class":"game-card"})
    top = soup.new_tag("div", attrs={"class":"game-card-top"})
    add_text(soup, top, "span", game.get("status") or "STATUS UNBEKANNT")
    label = re.sub(r'\s*\(Wien\)', '', str(game.get("date_label") or ""))
    add_text(soup, top, "span", label)
    card.append(top)
    matchup = str(game.get("matchup") or "")
    # ESPN-Konverter liefert "Team 12 – 24 Team"; nur bei eindeutigem Muster zerlegen.
    m = re.fullmatch(r'(.+?)\s+(\d+)\s+[–-]\s+(\d+)\s+(.+)', matchup)
    if m:
        teams = soup.new_tag("div", attrs={"class":"teams"})
        for name, score in ((m.group(1),m.group(2)), (m.group(4),m.group(3))):
            row = soup.new_tag("div", attrs={"class":"team"})
            add_text(soup,row,"span",name)
            add_text(soup,row,"strong",score)
            teams.append(row)
        card.append(teams)
    else:
        add_text(soup, card, "p", matchup or "Spielinformationen fehlen")
    url = str(game.get("source_url") or "")
    if url.startswith(("https://www.espn.com/","https://espn.com/")):
        links = soup.new_tag("div",attrs={"class":"game-links"})
        a=soup.new_tag("a",href=url,target="_blank",rel="noopener noreferrer")
        a.string="ESPN Spielbericht ↗"
        links.append(a)
        gamebook=str(game.get("gamebook_url") or "")
        if gamebook.startswith("https://static.www.nfl.com/"):
            a2=soup.new_tag("a",href=gamebook,target="_blank",rel="noopener noreferrer")
            a2.string="NFL Gamebook (PDF) ↗"
            links.append(a2)
        card.append(links)
    return card

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--template",default="index.html")
    ap.add_argument("--draft",default="drafts/leserfassung-20.md")
    ap.add_argument("--preview-json",default="drafts/morning-preview.json")
    ap.add_argument("--standings",default="data/standings.json")
    ap.add_argument("--output",default="drafts/the-huddle-layout-vorschau.html")
    args=ap.parse_args()
    text=Path(args.draft).read_text(encoding="utf-8")
    data=json.loads(Path(args.preview_json).read_text(encoding="utf-8"))
    edition=data["edition"]
    ss=sections(text)
    def pick(*keys):
        return next((ss[k] for k in keys if ss.get(k)), "")
    brief=pick("60-sekunden-brief","die nfl in 60 sekunden")
    stories=pick("top stories")
    austria=pick("austrian watch")
    if not brief or not stories:
        raise SystemExit("60-Sekunden-Brief oder Top Stories fehlen")
    soup=BeautifulSoup(Path(args.template).read_text(encoding="utf-8"),"html.parser")
    hero=soup.find(id="morning")
    story_section=soup.find(id="stories")
    if not hero or not story_section:
        raise SystemExit("Template ohne #morning oder #stories")
    lead=hero.select_one(".lead-text")
    container=story_section.select_one(".stories")
    if not lead or not container:
        raise SystemExit("Template ohne .lead-text oder .stories")
    replace_children(lead,fragment(brief))
    parts=re.split(r'(?m)^###\s+(.+?)\s*$',stories)
    items=[(parts[i].strip(),parts[i+1].strip()) for i in range(1,len(parts)-1,2)]
    if not items:
        raise SystemExit("Keine Top Stories im Entwurf")
    container.clear()
    aside=hero.select_one("aside.sidebar ol")
    if aside: aside.clear()
    for i,(title,body) in enumerate(items,1):
        article=soup.new_tag("article",attrs={"class":"story","id":f"story-{i}"})
        add_text(soup,article,"div","TOP STORY","kicker")
        add_text(soup,article,"h3",title)
        for child in fragment(body): article.append(child)
        container.append(article)
        if aside:
            li=soup.new_tag("li")
            a=soup.new_tag("a",href=f"#story-{i}")
            a.string=title
            li.append(a);aside.append(li)
    counter=story_section.select_one(".section-head small")
    if counter: counter.string=f"{len(items)} Meldungen"
    story_section.extract()
    hero.insert_after(story_section)

    # Die alte Titelgeschichte einschließlich ihrer Links komplett ersetzen.
    lead_article=hero.find("article")
    current=edition.get("lead") or {}
    if not lead_article or not isinstance(current,dict) or not current.get("title"):
        raise SystemExit("Aktuelle Titelgeschichte fehlt – alte Geschichte wird nicht übernommen")
    h1=lead_article.find("h1")
    if h1: h1.string=str(current["title"])
    # .lead-text wird bewusst aus dem geprüften 60-Sekunden-Brief befüllt.
    for old in list(lead_article.select("a.source, p.source-link")):
        old.decompose()
    source=str(current.get("source_url") or "")
    if source.startswith("https://"):
        a=soup.new_tag("a",attrs={"class":"source","href":source,
            "target":"_blank","rel":"noopener noreferrer"})
        a.string="Originalquelle ansehen ↗"
        lead_article.append(a)
    # Veralteter Ausgaben-Link aus der Testvorlage entfernen.
    for old in list(soup.select('main > div')):
        if old.find("a",href=re.compile(r"ausgaben/2026-11-15\.html")):
            old.decompose()
    aust=soup.find(id="austria")
    if aust:
        if austria:
            for node in list(aust.children):
                if getattr(node,"name",None) not in ("div","h2"):
                    node.extract()
            for node in fragment(austria): aust.append(node)
        else:
            aust.decompose()

    games=soup.find(id="games")
    if games:
        game_list=edition.get("game_center") or []
        try:
            edition_day=datetime.fromisoformat(str(edition.get("date"))).date()
            # Die letzte NFL-Nacht und das unmittelbar anstehende MNF,
            # nicht schon die Spiele der Folgewoche anzeigen.
            game_list=[g for g in game_list if isinstance(g,dict) and
                       edition_day-timedelta(days=2) <=
                       datetime.strptime(str(g.get("date_label",""))[:10],"%d.%m.%Y").date()
                       <= edition_day+timedelta(days=1)]
        except (ValueError, TypeError):
            raise SystemExit("Ungültiges Ausgabedatum oder Spieldatum – keine alten Ergebnisse übernehmen")
        grid=games.select_one("#game-results")
        if grid:
            grid.clear()
            for game in game_list:
                if isinstance(game,dict):
                    grid.append(game_card(soup,game))
        count=games.select_one(".section-head small")
        if count: count.string=f"{len(game_list)} Spiele"
        note=games.select_one(".preview-note")
        if note: note.string="Spielstände und Termine aus dem aktuellen Redaktions-JSON. Noch nicht redaktionell freigegeben."

    # Tabellen nicht aus der alten Vorlage übernehmen. Nur lokale Daten verwenden.
    standings=soup.find(id="standings")
    standings_note="Tabellen nicht aktualisiert"
    if standings:
        snap_path=Path(args.standings)
        snapshot=None
        if snap_path.is_file():
            try:
                candidate=json.loads(snap_path.read_text(encoding="utf-8"))
                if all(candidate.get("conferences",{}).get(c) for c in ("AFC","NFC")):
                    snapshot=candidate
            except (ValueError, OSError, TypeError):
                pass
        status=standings.find(id="standings-status")
        root=standings.find(id="standings-divisions")
        if root: root.clear()
        if snapshot:
            stamp=str(snapshot.get("results_through") or "")
            standings_note=f"Tabellenstand nach Spielen bis {stamp or 'unbekannt'}"
            if status: status.string=standings_note
            # Statische AFC- und NFC-Tabellen, auch offline in der HTML-Datei sichtbar.
            if root:
                for conf in ("AFC","NFC"):
                    wrap=soup.new_tag("div",attrs={"class":"standings-static-conference","data-static-conference":conf})
                    for div in snapshot["conferences"][conf]:
                        block=soup.new_tag("div",attrs={"class":"standings-division"})
                        add_text(soup,block,"h3",div.get("name",conf))
                        scroll=soup.new_tag("div",attrs={"class":"standings-scroll"})
                        table=soup.new_tag("table",attrs={"class":"standings-table"})
                        head=soup.new_tag("thead");tr=soup.new_tag("tr")
                        for col in ("Team","W","L","T","PCT"): add_text(soup,tr,"th",col)
                        head.append(tr);table.append(head)
                        tbody=soup.new_tag("tbody")
                        for team in div.get("teams",[]):
                            tr=soup.new_tag("tr")
                            for key in ("name","wins","losses","ties","pct"):
                                add_text(soup,tr,"td",team.get(key,"–"))
                            tbody.append(tr)
                        table.append(tbody);scroll.append(table);block.append(scroll);wrap.append(block)
                    root.append(wrap)
            # Template-JS mit eingebauten alten Tabellen entfernen, sonst überschreibt es neue.
        else:
            if status: status.string="Keine verlässlichen aktuellen Tabellendaten vorhanden."
            standings_note="Tabellen fehlen – keine alten Beispieldaten angezeigt"
            source_note=standings.select_one(".standings-source")
            if source_note:
                source_note.string="Tabellen werden erst angezeigt, wenn ein geprüfter aktueller Datenstand vorliegt."
        old_standings_script=soup.find("script",id="huddle-standings-script")
        if old_standings_script:
            old_standings_script.decompose()
        js=soup.new_tag("script")
        js.string="""document.addEventListener('DOMContentLoaded',function(){
          const buttons=[...document.querySelectorAll('[data-conference]')];
          const groups=[...document.querySelectorAll('[data-static-conference]')];
          function show(c){buttons.forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.conference===c)));
            groups.forEach(g=>{g.hidden=g.dataset.staticConference!==c;});}
          buttons.forEach(b=>b.addEventListener('click',()=>show(b.dataset.conference)));
          show('AFC');
        });"""
        standings.append(js)

    # Vom Nutzer geprüfte Videos; vorhandene datenschutzfreundliche Klick-Aktivierung bleibt.
    video_section=soup.find(id="videos")
    if video_section:
        grid=video_section.select_one(".huddle-video-grid")
        if grid:
            grid.clear()
            for title,vid in VIDEOS:
                card=soup.new_tag("article",attrs={"class":"huddle-video-card"})
                frame=soup.new_tag("div",attrs={"class":"huddle-video-frame"})
                button=soup.new_tag("button",attrs={
                    "type":"button","class":"video-activate",
                    "aria-label":f"Video abspielen: {title}",
                    "style":f"background-image:linear-gradient(transparent,rgba(0,0,0,.18)),url(https://i.ytimg.com/vi/{vid}/hqdefault.jpg)"})
                button.string="▶";frame.append(button)
                iframe=soup.new_tag("iframe",attrs={
                    "data-src":f"https://www.youtube-nocookie.com/embed/{vid}?autoplay=1",
                    "title":title,"loading":"lazy","hidden":"",
                    "allow":"accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share",
                    "allowfullscreen":"","referrerpolicy":"strict-origin-when-cross-origin"})
                frame.append(iframe)
                link=soup.new_tag("a",attrs={"class":"video-fallback-link",
                    "href":f"https://www.youtube.com/watch?v={vid}","target":"_blank","rel":"noopener noreferrer"})
                link.string="Video direkt auf YouTube ansehen ↗";frame.append(link)
                card.append(frame)
                caption=soup.new_tag("div",attrs={"class":"huddle-video-caption"})
                add_text(soup,caption,"span",title)
                link2=soup.new_tag("a",href=f"https://www.youtube.com/watch?v={vid}",target="_blank",rel="noopener noreferrer")
                link2.string="Auf YouTube öffnen ↗";caption.append(link2)
                card.append(caption);grid.append(card)

    notice=soup.select_one(".draft-notice")
    if notice:
        notice.string=("INTERNE LAYOUT-VORSCHAU – NICHT VERÖFFENTLICHEN. "
                       "Nachrichten und Spiele aus dem Redaktionsentwurf; "
                       +standings_note+". Videos manuell auf Einbettbarkeit getestet.")
    # Vorhandene Game-Center- und Datenschutzfunktionen bleiben unverändert.
    if soup.head:
        meta=soup.new_tag("meta",attrs={"name":"robots","content":"noindex,nofollow"})
        soup.head.append(meta)
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(str(soup),encoding="utf-8")
    print(f"Interne Layout-Vorschau: {out} ({len(items)} Top Stories, {len(game_list) if games else 0} Spiele), keine Veröffentlichung")

if __name__=="__main__":
    main()
