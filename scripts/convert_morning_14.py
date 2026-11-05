
#!/usr/bin/env python3
"""THE HUDDLE – Markdown in unveröffentlichte JSON-Testvorschau.

Aufruf: python scripts/convert_morning_14.py
Schreibt ausschließlich drafts/morning-preview.json.
"""

import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path("drafts")
SOURCE = ROOT / "the-huddle-morgenausgabe-13.md"
AUDIT = ROOT / "redaktionspruefung-13.md"
TARGET = ROOT / "morning-preview.json"

URL = re.compile(r"https://[^\s)<>\],;]+")
SOURCE_NOTE = re.compile(
    r"\s*\((?:Quellen?|Zwischenstand, ESPN-Spielseite):"
    r"\s*[^)]*\)",
    re.I
)

TITLE_LINE = re.compile(r"^\*\*(.+?)\*\*\s*$")

FALLBACK_TITLE = "NFL-Meldung: Überschrift redaktionell prüfen"


def fail(message):
    raise SystemExit("KONVERTER: " + message)


def links_in(text):
    return list(dict.fromkeys(
        u.rstrip(".,;") for u in URL.findall(text)
    ))


def clean(text):
    text = SOURCE_NOTE.sub("", text)
    text = URL.sub("", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"\(\s*\)", "", text)
    return " ".join(text.split()).strip(" ,;")


def valid_url(url):
    parsed = urlparse(url)
    return parsed.scheme == "https" and bool(parsed.netloc)


def entry(text, *, title=None, category=None):
    urls = [
        u for u in links_in(text)
        if valid_url(u)
    ]

    body = clean(text)

    if title is None:
        result = {"text": body}
    else:
        result = {
            "title": title,
            "summary": body,
            "category": category or "AROUND THE LEAGUE",
        }

    # Keine unsichere Quellenzuordnung durch Textähnlichkeit.
    # Ohne explizite Originalquelle bleibt die Meldung ungeprüft.
    if urls:
        result["source_url"] = urls[0]
        result["source_name"] = (
            urlparse(urls[0]).netloc.removeprefix("www.")
        )

    return result


def sections_of(md):
    aliases = {
        "THE LEAD": "THE LEAD",
        "LEAD": "THE LEAD",
        "GAME CENTER": "GAME CENTER",
        "GAMECENTER": "GAME CENTER",
        "AROUND THE LEAGUE": "AROUND THE LEAGUE",
        "TOP STORIES": "AROUND THE LEAGUE",
        "AUSTRIAN WATCH": "AUSTRIAN WATCH",
    }

    sections = {}
    current = None

    pattern = (
        r"^\s*#{1,6}\s*"
        r"(THE LEAD|LEAD|GAME CENTER|GAMECENTER|"
        r"AROUND THE LEAGUE|TOP STORIES|AUSTRIAN WATCH)"
        r"\s*$"
    )

    for line in md.splitlines():
        match = re.match(pattern, line, re.I)

        if match:
            current = aliases[match.group(1).upper()]
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)

    return {
        name: "\n".join(lines).strip()
        for name, lines in sections.items()
    }


def paragraphs(section):
    items = []

    for part in re.split(r"\n\s*\n", section.strip()):
        part = part.strip()

        if not part:
            continue

        if re.match(
            r"^vor veröffentlichung redaktionell prüfen\.?$",
            part,
            re.I
        ):
            continue

        items.append(part)

    return items


def parse_news(paragraph):
    """Liest eine markierte Überschrift und den zugehörigen Text."""
    lines = paragraph.strip().splitlines()

    if not lines:
        return None

    first = lines[0].strip()
    match = TITLE_LINE.fullmatch(first)

    if match:
        title = match.group(1).strip()
        body = "\n".join(lines[1:]).strip()
        title_marked = True
    else:
        title = FALLBACK_TITLE
        body = paragraph.strip()
        title_marked = False

    # Titel wird nicht aus dem Fließtext herausgeschnitten.
    if not 15 <= len(title) <= 110:
        title = FALLBACK_TITLE

    if title.endswith(
        ("…", "...", ",", ";", ":", " an", " nach dem", " wegen der")
    ):
        title = FALLBACK_TITLE

    if not body:
        return None

    return {
        "title": title,
        "body": body,
        "title_marked": title_marked,
    }


def first_sentence(text):
    match = re.search(
        r"(?<=[.!?])\s+(?=[A-ZÄÖÜ])",
        text
    )

    return (
        text[:match.start()].strip()
        if match
        else text.strip()
    )


def brief_text(text):
    return first_sentence(clean(text))


def topic_key(text):
    body = clean(text).lower()

    # Exakte Doppelungen vermeiden.
    words = re.findall(r"[a-zäöüß0-9]{4,}", body)
    return " ".join(words[:12])


def main():
    if not SOURCE.is_file() or not AUDIT.is_file():
        fail("Entwurf oder Prüfbericht fehlt.")

    md = SOURCE.read_text(encoding="utf-8")
    audit = AUDIT.read_text(encoding="utf-8")

    marker = (
        "TESTENTWURF – AUTOMATISCH ERSTELLT, "
        "NICHT VERÖFFENTLICHEN"
    )

    if not md.startswith(marker):
        fail("Testentwurf-Kennzeichnung fehlt.")

    if "## Vor Veröffentlichung manuell prüfen" not in audit:
        fail("Prüfbericht nicht erkannt.")

    sections = sections_of(md)

    lead_raw = paragraphs(
        sections.get("THE LEAD", "")
    )

    around_raw = paragraphs(
        sections.get("AROUND THE LEAGUE", "")
    )

    lead = [
        item for part in lead_raw
        if (item := parse_news(part)) is not None
    ]

    around = [
        item for part in around_raw
        if (item := parse_news(part)) is not None
    ]

    if not lead:
        fail("THE LEAD enthält keine lesbare Nachricht.")

    if not around:
        fail("AROUND THE LEAGUE enthält keine lesbare Nachricht.")


    # Kurzmeldungen: nur Nachrichten mit expliziter Originalquelle.
    candidates = lead[:1] + around

    brief = []
    seen = set()

    for news in candidates:
        key = topic_key(news["body"])

        if key in seen:
            continue

        item = entry(news["body"])

        if not item.get("source_url"):
            print("Ohne Quelle übersprungen (Brief):", news["title"])
            continue

        item["text"] = brief_text(news["body"])

        brief.append(item)
        seen.add(key)

        if len(brief) >= 5:
            break

    # Top Stories: nur Meldungen mit Originalquellenlink.
    stories = []

    for news in around:
        item = entry(
            news["body"],
            title=news["title"],
            category="AROUND THE LEAGUE"
        )

        if not item.get("source_url"):
            print("Ohne Quelle übersprungen (Story):", news["title"])
            continue

        stories.append(item)

        if len(stories) >= 6:
            break

    if len(brief) < 3:
        fail("Zu wenige belegte Kurzmeldungen für die Vorschau.")

    if len(stories) < 2:
        fail("Zu wenige belegte Top Stories für die Vorschau.")



    austrian_raw = paragraphs(
        sections.get("AUSTRIAN WATCH", "")
    )

    austrian = None

    if austrian_raw:
        parsed = parse_news(austrian_raw[0])

        if parsed:
            austrian = entry(parsed["body"])

    date_match = re.search(
        r"^# THE HUDDLE – (.+)$",
        md,
        re.M
    )

    game_section = sections.get("GAME CENTER", "")

    game_count = sum(
        1
        for line in game_section.splitlines()
        if re.match(
            r"^\s*(?:-\s*)?"
            r"(?:ENDE:|LIVE\s*\(|NOCH NICHT BEENDET)",
            line
        )
    )

    warnings = [
        "Nicht veröffentlichen: Keine redaktionelle Freigabe.",
        "Alle Aussagen, Zahlen und Originalquellen prüfen.",
        "LIVE-Spielstände vor Veröffentlichung neu abrufen.",
        "Überschriften und Kurzmeldungen redaktionell prüfen.",
    ]

    fallback_count = sum(
        story["title"] == FALLBACK_TITLE
        for story in stories
    )

    if fallback_count:
        warnings.append(
            f"{fallback_count} Story-Überschrift(en) "
            "müssen redaktionell ergänzt werden."
        )

    if len(brief) < 5:
        warnings.append(
            f"Nur {len(brief)} unterschiedliche Brief-Themen "
            "vorhanden; keine Meldungen erfunden."
        )

    if any(
        len(item["text"]) > 250
        for item in brief
    ):
        warnings.append(
            "Mindestens eine Kurzmeldung ist länger "
            "als 250 Zeichen."
        )

    missing_sources = sum(
        "source_url" not in item
        for item in brief + stories
    )

    if missing_sources:
        warnings.append(
            f"{missing_sources} Meldung(en) ohne "
            "ausdrücklichen Originalquellenlink."
        )

    if game_count:
        warnings.append(
            f"{game_count} Game-Center-Zeilen bewusst "
            "nicht als statische Ergebnisse übernommen."
        )

    result = {
        "version": "1.0",
        "status": "draft",
        "published_at": None,
        "message": (
            "Nur interne Testvorschau – "
            "nicht veröffentlichen."
        ),
        "edition": {
            "date": (
    re.sub(
        r"\s+Wien\s*$",
        "",
        date_match.group(1)
    ) + ":00" if False else (
        re.sub(r"\s+Wien\s*$", "", date_match.group(1))
        if date_match
        else "Datum prüfen"
    )
),
            "headline": (
                "THE HUDDLE – Redaktionelle Testvorschau"
            ),
            "intro": (
                "Unveröffentlichter Entwurf. "
                "Sämtliche Meldungen vor Freigabe prüfen."
            ),
            "brief": brief,
            "stories": stories,
            "austria": austrian,
        },
        "review_required": warnings,
    }

    ROOT.mkdir(
        parents=True,
        exist_ok=True
    )

    TARGET.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2
        ) + "\n",
        encoding="utf-8"
    )

    print(
        f"Vorschau: {TARGET}; "
        f"{len(brief)} Brief-Themen; "
        f"{len(stories)} Stories; "
        f"{fallback_count} Ersatzüberschriften; "
        "NICHT veröffentlicht."
    )


if __name__ == "__main__":
    main()
