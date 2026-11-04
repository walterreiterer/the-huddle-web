
#!/usr/bin/env python3
"""THE HUDDLE – KI-Entwurf mit strenger Datumsprüfung (Testvorschau)."""

import json
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path("drafts")
ARTICLES = ROOT / "quellen-10.json"
GAMES = ROOT / "nfl-spiele-08.md"
OUTPUT = ROOT / "the-huddle-morgenausgabe-13.md"
AUDIT = ROOT / "redaktionspruefung-13.md"

NOW = datetime.now(ZoneInfo("Europe/Vienna"))
MAX_ARTICLE_AGE_HOURS = 48
FUTURE_TOLERANCE_HOURS = 2

BAD = re.compile(
    r"\b(fantasy|dfs|draftkings|fanduel|sportsbook|betting|"
    r"odds|parlay|prop bets?|mock draft|waiver wire|"
    r"how to watch|streaming|start.?sit|tv schedule)\b",
    re.I
)

HIGH = re.compile(
    r"\b(injury|injured|trade|traded|fired|hired|"
    r"suspended|playoff|quarterback|record|coach|"
    r"season-ending)\b",
    re.I
)


def fail(message):
    raise SystemExit("THE HUDDLE: " + message)


def age_hours(value):
    if not value:
        return None
    try:
        d = parsedate_to_datetime(str(value))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return (
            NOW - d.astimezone(ZoneInfo("Europe/Vienna"))
        ).total_seconds() / 3600
    except (ValueError, TypeError, OverflowError):
        return None


def priority(article):
    title = str(article.get("title", ""))
    age = age_hours(article.get("published"))
    points = 5 if HIGH.search(title) else 0

    if age is not None:
        if 0 <= age <= 18:
            points += 7
        elif 0 <= age <= 36:
            points += 4
        elif 0 <= age <= 48:
            points += 1
        else:
            points -= 5

    return points


def load_sources():
    if not ARTICLES.is_file() or not GAMES.is_file():
        fail("Quellen oder ESPN-Spielbericht fehlen.")

    source_data = json.loads(
        ARTICLES.read_text(encoding="utf-8")
    )
    articles = source_data.get("articles", [])

    if not isinstance(articles, list):
        fail("Ungueltige Artikelstruktur.")

    filtered = []
    undated = 0
    out_of_window = 0

    for article in articles:
        title = str(article.get("title", ""))
        url = str(article.get("url", ""))
        body = str(article.get("text", ""))
        age = age_hours(article.get("published"))

        if BAD.search(title + " " + url):
            continue

        # Ohne belastbares Datum keine Aufnahme in den Morgenbrief.
        if age is None:
            undated += 1
            continue
        if not (-FUTURE_TOLERANCE_HOURS <= age <= MAX_ARTICLE_AGE_HOURS):
            out_of_window += 1
            continue

        if len(body.split()) < 120:
            continue

        if not url.startswith("https://"):
            continue

        filtered.append(article)

    print(f"Datumsfilter: {undated} ohne gueltiges Datum, "
          f"{out_of_window} ausserhalb von {MAX_ARTICLE_AGE_HOURS} Stunden; "
          f"{len(filtered)} Kandidaten verbleiben.")
    filtered.sort(key=priority, reverse=True)

    selected = []
    seen = set()
    per_source = {}

    for article in filtered:
        title = str(article.get("title", ""))
        norm = re.sub(r"[^a-z0-9]+", "", title.lower())
        publisher = str(article.get("source", "Unbekannt"))

        if norm in seen:
            continue

        if per_source.get(publisher, 0) >= 4:
            continue

        selected.append(article)
        seen.add(norm)
        per_source[publisher] = per_source.get(publisher, 0) + 1

        if len(selected) >= 12:
            break

    if not selected:
        fail("Keine geeigneten Nachrichtenquellen.")

    games = GAMES.read_text(encoding="utf-8")
    return articles, selected, games, undated, out_of_window


def make_material(selected):
    blocks = []

    for article in selected:
        blocks.append(
            "QUELLE: " + str(article.get("source", "")) +
            "\nTITEL: " + str(article.get("title", "")) +
            "\nURL: " + str(article.get("url", "")) +
            "\nVEROEFFENTLICHT: " +
            str(article.get("published", "unbekannt")) +
            "\nARTIKELAUSZUG:\n" +
            str(article.get("text", ""))[:4400]
        )

    return "\n\n---\n\n".join(blocks)[:35000]


INSTRUCTIONS = """
Du bist die deutschsprachige NFL-Redaktion von THE HUDDLE.
Erstelle einen unveroeffentlichten journalistischen Testentwurf.

Beginne EXAKT mit:
TESTENTWURF – AUTOMATISCH ERSTELLT, NICHT VERÖFFENTLICHEN

Danach:
# THE HUDDLE – [Datum und Uhrzeit Wien]

Verwende diese Abschnittsueberschriften:
## THE LEAD
## GAME CENTER
## AROUND THE LEAGUE

Optional:
## AUSTRIAN WATCH

WICHTIG: VERBINDLICHES NACHRICHTENFORMAT

Jede Nachricht in THE LEAD und AROUND THE LEAGUE
besteht aus genau zwei Zeilen:

**Kurze, eigenstaendige und vollstaendige Ueberschrift**
Ein zusammenhaengender Nachrichtenabsatz mit vollstaendigen
Saetzen. (Quelle: https://originalquelle.example/artikel)

Zwischen zwei Nachrichten steht eine Leerzeile.

Die URL im Beispiel ist nur ein Platzhalter!
Verwende ausschliesslich tatsaechliche URLs aus den
uebergebenen Quellen. Niemals example-URLs ausgeben.

UEBERSCHRIFTEN:
- Maximal 100 Zeichen, mindestens 15 Zeichen.
- Eigenstaendige journalistische Aussage.
- Keine abgebrochenen Saetze oder Satzteile.
- Keine Ueberschrift aus dem Fliesstext abschneiden.
- Keine Auslassungspunkte.
- Kein abschliessendes "an", "nach dem" oder "wegen der".
- Keine erfundenen Tatsachen.
- Keine Markdown-Ueberschrift mit # fuer Einzelmeldungen.
- Verwende genau **Fettschrift** fuer Einzelueberschriften.

THE LEAD:
Ein relevantes belegtes NFL-Thema, 80 bis 130 Woerter.
Ein Absatz mit einer Originalquelle.

AROUND THE LEAGUE:
Idealerweise vier weitere unterschiedliche Nachrichten.
Mindestens zwei, wenn ausreichend belegte Themen vorliegen.
Pro Meldung 45 bis 75 Woerter.
Keine Wiederholung des THE-LEAD-Themas.

QUELLEN:
Jede Nachricht braucht am Ende ihres Absatzes:
(Quelle: https://...)
Verwende nur die vorgegebenen Originalquellenlinks.
Keine erfundenen Links oder Fakten.
Keine Quellen ohne inhaltliche Uebereinstimmung.
Unbestaetigte Meldungen als solche kennzeichnen.
Keine Fantasy-, Wett- oder belanglosen Randmeldungen.

 AKTUALITAET UND ZEITLICHE PLAUSIBILITAET:
 - Der Zeitpunkt ZEIT WIEN ist der verbindliche Redaktionsstand.
 - Jeder Artikel hat ein VEROEFFENTLICHT-Datum; dieses ist nicht
   automatisch der Zeitpunkt des beschriebenen Ereignisses.
 - Unterscheide konsequent zwischen bereits geschehen, laufend und
   bevorstehend. Schreibe keine Vorschau auf ein bereits beendetes Spiel.
 - Die ESPN-Spielinformationen haben bei Spielstatus und Ergebnissen
   Vorrang vor aelteren Formulierungen in Nachrichtenartikeln.
 - Wenn der Spielstatus oder Ereigniszeitpunkt unklar ist, verzichte
   auf zeitbezogene Behauptungen und kennzeichne die Unsicherheit.
 - Keine alten Zukunftsformulierungen aus Quellen ungeprueft uebernehmen.
 - Bei Konflikten zwischen Quellen oder unsicherer zeitlicher Lage:
   Thema weglassen, statt eine vermeintlich aktuelle Meldung zu erfinden.

GAME CENTER:
Nur Daten aus dem uebergebenen ESPN-Bericht verwenden.
ENDE bedeutet Endstand.
LIVE bedeutet Zwischenstand.
NOCH NICHT BEENDET bedeutet kein Ergebnis.
Maximal vier relevante Spiele.
Keine Ergebnisse erfinden.

AUSTRIAN WATCH:
Nur bei einer aktuellen relevanten Nachricht
zu Bernhard Raimann oder Valentin Senn.
Falls vorhanden, dieselbe Nachrichtenformatierung
mit Fettschrift-Ueberschrift und Quellenlink verwenden.

Beende den gesamten Entwurf EXAKT mit:
Vor Veröffentlichung redaktionell prüfen.

Die Ausgabe ist ausschliesslich ein TESTENTWURF.
Keine Veroeffentlichung oder redaktionelle Freigabe.
Antworte ausschliesslich in Markdown.
"""


def call_openai(selected, games):
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        fail("OPENAI_API_KEY fehlt.")

    allowed = "\n".join(
        "- " + str(a["url"]) for a in selected
    )

    payload = {
        "model": "gpt-5-mini",
        "store": False,
        "max_output_tokens": 8000,
        "instructions": INSTRUCTIONS,
        "input": (
            f"ZEIT WIEN (verbindlicher Redaktionsstand): {NOW.isoformat(timespec='minutes')}\n"
            f"ARTIKELFENSTER: maximal {MAX_ARTICLE_AGE_HOURS} Stunden; "
            "Ereigniszeitpunkte gesondert pruefen.\n\n"
            f"ESPN GAME CENTER:\n{games[:14000]}\n\n"
            f"ERLAUBTE QUELLEN:\n{allowed}\n\n"
            f"ARTIKELMATERIAL:\n{make_material(selected)}"
        ),
    }

    request = Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=180) as response:
            result = json.load(response)
    except HTTPError as exc:
        fail(f"OpenAI HTTP-Fehler {exc.code}")
    except (URLError, TimeoutError) as exc:
        fail(f"OpenAI-Verbindungsfehler: {type(exc).__name__}")

    status = result.get("status", "unbekannt")
    reason = (
        result.get("incomplete_details") or {}
    ).get("reason")

    print(f"OpenAI-Status: {status}; Grund: {reason}")

    content = "\n".join(
        part.get("text", "")
        for item in result.get("output", [])
        if item.get("type") == "message"
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    ).strip()

    if status != "completed" or len(content) < 300:
        fail(
            f"KI-Entwurf unvollstaendig: "
            f"{status}, {reason}, {len(content)} Zeichen"
        )

    marker = (
        "TESTENTWURF – AUTOMATISCH ERSTELLT, "
        "NICHT VERÖFFENTLICHEN"
    )

    if not content.startswith(marker):
        fail("Testentwurf-Kennzeichnung fehlt.")

    return content


def main():
    articles, selected, games, undated, out_of_window = load_sources()
    content = call_openai(selected, games)

    ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content + "\n", encoding="utf-8")

    allowed_urls = {
        str(article["url"]) for article in selected
    }

    source_links = re.findall(
        r"\(Quelle:\s*(https://[^)\s]+)\)",
        content,
        re.I
    )

    unknown = sorted(
        set(source_links) - allowed_urls
    )

    flags = []

    if unknown:
        flags.append(
            "Nicht erlaubte Quellenlinks: " +
            ", ".join(unknown[:5])
        )

    for heading in ("THE LEAD", "AROUND THE LEAGUE"):
        if not re.search(
            rf"(?m)^## {heading}\s*$",
            content
        ):
            flags.append(f"Rubrik {heading} fehlt")

    if not re.search(
        r"(?m)^\*\*[^*\n]{15,100}\*\*\s*$",
        content
    ):
        flags.append(
            "Keine gueltig markierte Einzelueberschrift gefunden"
        )

    report = [
        "# THE HUDDLE – Redaktioneller Prüfbericht",
        "",
        f"Erstellt Wien: {NOW.isoformat(timespec='minutes')}",
        "",
        "Automatischer Check, kein journalistischer Faktencheck.",
        "",
        "## Eingaben",
        "",
        f"- Verfügbare Artikel: {len(articles)}",
        f"- Ausgewählte Artikel: {len(selected)}",
        f"- Artikel ohne gueltiges Datum verworfen: {undated}",
        f"- Artikel ausserhalb des Zeitfensters verworfen: {out_of_window}",
        "",
        "## Automatische Prüfflaggen",
        "",
    ]

    if flags:
        report.extend("- " + flag for flag in flags)
    else:
        report.append("- Keine strukturellen Auffälligkeiten erkannt.")

    report.extend([
        "",
        "## Verwendbare Quellen (Vorauswahl)",
        "",
    ])

    for article in selected:
        report.append(
            f"- {article.get('title', '')}: "
            f"{article.get('url', '')}"
        )

    report.extend([
        "",
        "## Vor Veröffentlichung manuell prüfen",
        "",
        "- Alle Aussagen mit Originalquellen abgleichen.",
        "- Zeitbezug jeder Meldung gegen Spielstatus und Ereignisdatum pruefen.",
        "- Verletzungen, Zahlen und Spielstände prüfen.",
        "- Überschriften und Nachrichtenwert prüfen.",
        "- Keine Veröffentlichung ohne Freigabe.",
        "- Weniger als fünf Themen sind im Test zulässig.",
        "",
    ])

    AUDIT.write_text(
        "\n".join(report),
        encoding="utf-8"
    )

    print(
        f"Entwurf erstellt: {OUTPUT}; "
        f"{len(selected)} Quellen; "
        f"{len(flags)} Prüfflaggen."
    )


if __name__ == "__main__":
    main()