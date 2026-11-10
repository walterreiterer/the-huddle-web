
#!/usr/bin/env python3
"""THE HUDDLE – redaktioneller Testentwurf mit vollständigem ESPN-Game-Center."""

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
    r"season-ending|extension|contract|released|waived|"
    r"signed|signing|ruled out|out for season|"
    r"season-ending|head coach|general manager)\b",
    re.I
)

LOW_NEWS_VALUE = re.compile(
    r"\b(podcast|interview|columnist|reporter|journalist|"
    r"broadcast|broadcaster|tv host|media personality|"
    r"social media|celebrity|fashion|merchandise|"
    r"power rankings|opinion|mailbag|recap show)\b",
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
    """Vorauswahl, keine endgültige journalistische Relevanzentscheidung."""
    title = str(article.get("title", ""))
    age = age_hours(article.get("published"))
    points = 2 if HIGH.search(title) else 0
    if LOW_NEWS_VALUE.search(title):
        points -= 8
    if age is not None:
        if 0 <= age <= 18:
            points += 3
        elif 0 <= age <= 36:
            points += 2
        elif 0 <= age <= 48:
            points += 1
    return points


GAME_LINE = re.compile(
    r"^- (ENDE|LIVE|NOCH NICHT BEENDET):\s*(.+?)\s*\|\s*"
    r"\[ESPN-Spielseite\]\((https://www\.espn\.com/nfl/game/[^)]+)\)\s*$"
)


def extract_games(games):
    """Übernimmt alle ESPN-Spielzeilen, ohne Ergebnisse von KI auswählen zu lassen."""
    entries = []
    seen = set()
    day = None
    for raw in games.splitlines():
        line = raw.strip()
        if line.startswith("## Spieltag "):
            day = line[3:]
        match = GAME_LINE.fullmatch(line)
        if match:
            status, score, url = match.groups()
            if url in seen:
                raise ValueError(f"Doppelte ESPN-Spielseite: {url}")
            seen.add(url)
            entries.append((day, status, score, url))
        elif line.startswith("- ENDE:") or line.startswith("- LIVE:") or line.startswith("- NOCH NICHT BEENDET:"):
            raise ValueError(f"ESPN-Spielzeile nicht erkannt: {line[:140]}")
    if not entries:
        raise ValueError("Keine ESPN-Spielzeilen im Spielbericht gefunden")
    return entries


def render_game_center(entries):
    lines = ["## GAME CENTER", "", "Alle im ESPN-Bericht erfassten Spiele (ungeprüfter Datenstand):", ""]
    previous_day = None
    for day, status, score, url in entries:
        if day != previous_day:
            if previous_day is not None:
                lines.append("")
            if day:
                lines.append(f"**{day}**")
                lines.append("")
            previous_day = day
        lines.append(f"- {status}: {score} | [ESPN-Spielseite]({url})")
    lines += ["", "Datenquelle: [ESPN NFL Scoreboard](https://www.espn.com/nfl/scoreboard)"]
    return "\n".join(lines)


def insert_game_center(content, entries):
    """Entfernt KI-Game-Center und setzt den vollständigen ESPN-Block ein."""
    section = render_game_center(entries)
    pattern = r"(?ms)^## GAME CENTER\s*\n.*?(?=^## (?:AROUND THE LEAGUE|AUSTRIAN WATCH)\s*$)"
    if re.search(pattern, content):
        return re.sub(pattern, lambda _: section + "\n\n", content, count=1)
    # Der Prompt fordert GAME CENTER vor AROUND THE LEAGUE.
    marker = "## AROUND THE LEAGUE"
    if marker not in content:
        raise ValueError("Rubrik AROUND THE LEAGUE fehlt; Game Center nicht sicher einfügbar")
    return content.replace(marker, section + "\n\n" + marker, 1)


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

        # Medien-/Prominenten-Randthemen nicht allein wegen eines neuen Datums bevorzugen.
        if LOW_NEWS_VALUE.search(title) and not HIGH.search(title):
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

        if len(selected) >= 18:
            break

    # Austrian Watch: Mindestens eine geeignete, aktuelle Spielerquelle
    # an die Redaktion weitergeben, ohne den journalistischen Entscheid
    # über die tatsächliche Veröffentlichung vorwegzunehmen.
    player_pattern = re.compile(r"\b(?:Bernhard Raimann|Raimann|Valentin Senn)\b", re.I)
    austrian_candidates = [
        article for article in filtered
        if player_pattern.search(
            str(article.get("title", "")) + " " + str(article.get("text", ""))[:1600]
        )
    ]
    if austrian_candidates:
        candidate = austrian_candidates[0]
        candidate_url = str(candidate.get("url", ""))
        if not any(str(article.get("url", "")) == candidate_url for article in selected):
            # Bei vollem Quellenbudget die letzte Quelle ersetzen.
            # Nur die Vorauswahl ändert sich, nicht die Quellenprüfung.
            if len(selected) >= 18:
                selected[-1] = candidate
            else:
                selected.append(candidate)
        print(f"Austrian Watch: {len(austrian_candidates)} geeignete Spielerquellen; "
              "mindestens eine in der Redaktionsauswahl.")
    else:
        print("Austrian Watch: Keine geeignete aktuelle Spielerquelle im Quellenfenster.")

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

    return "\n\n---\n\n".join(blocks)[:60000]


INSTRUCTIONS = """
Du bist die deutschsprachige NFL-Redaktion von THE HUDDLE.
Erstelle einen UNVEROEFFENTLICHTEN journalistischen Testentwurf.

Beginne EXAKT mit:
TESTENTWURF – AUTOMATISCH ERSTELLT, NICHT VERÖFFENTLICHEN

Danach:
# THE HUDDLE – [Datum und Uhrzeit Wien]

Verwende diese Abschnittsueberschriften in dieser Reihenfolge:
## THE LEAD
## GAME CENTER
## AROUND THE LEAGUE
Optional am Schluss: ## AUSTRIAN WATCH

REDAKTIONELLE GRUNDREGEL: Trenne in jedem Beitrag sauber zwischen
(1) belegten Tatsachen, (2) nachvollziehbarer journalistischer Einordnung
und (3) Geruechten oder offenen Fragen. Eigene Analyse ist erwuenscht,
wenn die zugrunde liegenden Fakten im Material stehen und die Folgerung
als Einschaetzung erkennbar ist (z. B. "das erhoeht den Druck",
"ein Wechsel erscheint moeglich"). Keine Einschaetzung als bestaetigte
Entscheidung oder als Aussage einer Quelle ausgeben. Keine erfundenen
Motive, Trainerzitate, Kaderentscheidungen oder angeblichen Gewissheiten.

THE HUDDLE 0.9 – RESSORTPLAN UND ZEITLOGIK (VERBINDLICH):
Die Lead-Story ist EIN Ereignis und bekommt genau eine Hauptplatzierung.
Nicht als Story 1 des Morning Briefs erneut erzaehlen. Ein Morning Brief
fasst die gesamte Ausgabe mit mehreren VERSCHIEDENEN Ereignissen zusammen;
Lead maximal ein kurzer Satz, andere Nachrichten haben Vorrang.
Keine zweite ausfuehrliche Lead-Erzaehlung in AROUND THE LEAGUE.
Bei gleichwertigen Meldungen Themenvielfalt vor mehrfachen Trades desselben Teams.
Relevante belegte Spielverlegungen/Anstosszeit-Aenderungen aktiv pruefen;
nur bei aktueller Relevanz aufnehmen, mit Quelle, Datum und Europa-Zeit.
Die bekannte Giants-Verschiebung auf 22:25 Uhr ist ein REDAKTIONELLER
TESTFALL, KEINE QUELLE und darf niemals ohne frischen Beleg erzaehlt werden.
Die Bezeichnung 'NFL-Nacht' nur fuer Spiele, die tatsaechlich in der
relevanten europaeischen Nacht stattgefunden haben. London-Spiele am
Sonntagnachmittag sind KEINE Ergebnisse der NFL-Nacht. Kein vergangenes
Spiel als heutiges Nachtresultat ausgeben.

THE LEAD: Waehle das journalistisch wichtigste, nachweislich belegte Thema.
Wichtig sind Auswirkungen auf die Liga, sportliche Bedeutung, Besonderheit
und Interesse fuer ein europaeisches NFL-Publikum. Bevorzuge nicht einfach
Trade-/Injury-Schlagwoerter. Schreibe eine eigenstaendige Hauptgeschichte
mit Kontext und mehreren zusammenhaengenden Absaetzen (ca. 180–300 Woerter,
nur wenn die Quellen das tragen). Verwende einen praezisen fett gesetzten Titel.

GAME CENTER: Schreibe ausschliesslich die Ueberschrift ## GAME CENTER und
in der naechsten Zeile [GAME_CENTER_WIRD_AUS_ESPN_EINGEFUEGT].
KEINE Spiele oder Ergebnisse selbst ausgeben. Die Software setzt ALLE
im ESPN-Bericht vorhandenen Spiele unveraendert ein.

AROUND THE LEAGUE: Strebe sechs bis acht VERSCHIEDENE relevante Geschichten an,
sofern ausreichend belegtes Material vorliegt. Weniger sind ausdruecklich erlaubt,
wenn nicht genug unterschiedliche, belastbare Themen vorhanden sind. Jede Geschichte mit einer
fett gesetzten, aussagekraeftigen Ueberschrift und 1–3 informativen
Absaetzen (ca. 90–160 Woerter, wenn belegbar). Keine Dopplung des Leads,
keine kuenstlichen Fuellthemen, keine Wiederholung derselben Geschichte.
Unterscheide Ereignisse statt nur Artikelueberschriften: Zwei Quellen
ueber dasselbe Ereignis ergeben nur EIN Thema. Waehle bei aehnlichem
Nachrichtenwert unterschiedliche Teams, Themen und Ereignisse.
Nutze das uebergebene Material breit, ohne Informationen zu erfinden.
PRIORISIERUNG: Wichtige Spieler- und Trainerentscheidungen, Verletzungen,
Rekorde, sportliche Folgen und relevante Ergebnisse gehen belanglosen
Randthemen vor. Unklare private Vorfaelle nicht durch Spekulationen
aufblaehen; ohne gesicherte, relevante Details lieber weglassen.
Eine Kicker-Verpflichtung waehrend sportlicher Probleme des bisherigen
Starters darf als Druck auf den Stammspieler eingeordnet werden, aber
nicht als bestaetigte Abloese. Eine offene Quarterback-Frage darf
analysiert werden, ohne einen Starter zu behaupten. MVP-Einschaetzungen
nur mit belastbarer Grundlage, keine voreiligen Kandidaten-Titel.
Spielansetzungen und TV-Zeitverschiebungen sind gegebenenfalls kurze
Servicemeldungen statt langer Hauptgeschichten: aus Sicht der Fans in
Oesterreich lokale Anstosszeit und Datum nur nennen, wenn belegbar,
und US-Zeitzone sowie Sommer-/Winterzeit korrekt beruecksichtigen.

AUSTRIAN WATCH: Pruefe das uebergebene Artikelmaterial ausdruecklich
auf aktuelle, belegte und journalistisch relevante Entwicklungen zu
Bernhard Raimann und Valentin Senn. Oesterreichische Quellen wie ORF Sport,
LAOLA1 oder andere uebergebene Originalquellen sind dabei zu beachten.
Wenn eine aktuelle, belegte Entwicklung Nachrichtenwert hat, schreibe
## AUSTRIAN WATCH mit fett gesetzter Ueberschrift und einem kurzen,
eigenstaendigen Beitrag (ca. 80–150 Woerter, soweit die Quellen tragen).
Bei einer belegten Niederlagenserie der Colts darf eine passende,
sachliche Ueberschrift lauten: "Raimann und Colts weiter in der Krise:
Fuenfte Niederlage in Folge" – aber nur, wenn die Serie tatsaechlich
belegt und aktuell ist. Keine Ueberschrift aus alten Ausgaben uebernehmen.
Eine aktuelle Colts-Partie kann relevant sein, aber Raimanns persoenliche
Beteiligung darf nur behauptet werden, wenn sie belegt ist.
Keine alten Meldungen als neu darstellen, keine unbelegten Behauptungen,
keine Dopplung von THE LEAD oder AROUND THE LEAGUE. Jede Geschichte endet
mit (Quelle: https://...). Ohne relevante belegte Entwicklung weglassen.

REDAKTIONELLE LAENGE: Fuer jedes Thema nur so viel Platz verwenden,
wie Nachrichtenwert und Beleglage rechtfertigen. Sechs starke Meldungen
sind besser als acht, die durch Fuellmaterial erreicht werden. Kurze
Service-Updates duerfen deutlich kuerzer als die Richtwerte sein.

QUELLEN: Jede Geschichte endet mit (Quelle: https://...). Nur exakt
uebergebene Original-URLs verwenden, keine erfundenen Fakten oder Links.
Unbestaetigte Meldungen deutlich kennzeichnen. Geplante, berichtete
und vollzogene Transfers strikt unterscheiden. Behauptungen zu Spielstatus
und Spielausgang muessen mit dem ESPN-Bericht vereinbar sein.

AKTUALITAET: ZEIT WIEN ist der Redaktionsstand. Publikationsdatum einer
Quelle ist nicht automatisch das Datum des Ereignisses. Keine Vorschau
auf ein bereits beendetes Spiel. Bei unklaren Sachverhalten lieber
weglassen oder Unsicherheit explizit kennzeichnen.

THEMENWAHL: Bewerte sportliche Tragweite, Aktualitaet, Belegbarkeit,
Folgen fuer Teams und Liga sowie Nachrichtenwert. Keine Fantasy-,
Wett-, Medienpromi- oder belanglosen Randthemen. Erfinde keinen
Spielverlauf und keine Zahlen, die nicht in den Quellen stehen.

Beende den gesamten Entwurf EXAKT mit:
Vor Veröffentlichung redaktionell prüfen.

Antworte ausschliesslich in Markdown. Keine Veroeffentlichung.
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
        "max_output_tokens": 10000,
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
    try:
        game_entries = extract_games(games)
    except ValueError as exc:
        fail(str(exc))
    content = call_openai(selected, games)
    try:
        content = insert_game_center(content, game_entries)
    except ValueError as exc:
        fail(str(exc))

    ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content + "\n", encoding="utf-8")

    allowed_urls = {
        str(article["url"]) for article in selected
    }

    # ESPN-Spiel-URLs sind eigenständige, strukturierte Quellen.
    # Nur Links zulassen, die im tatsächlich geladenen Spielbericht stehen.
    game_urls = {
        url.rstrip(".,;])")
        for url in re.findall(r"https?://[^\s<>]+", games)
    }
    allowed_urls.update(game_urls)

    source_links = re.findall(
        r"\(Quelle:\s*(https://[^)\s]+)\)",
        content,
        re.I
    )

    unknown = sorted(
        set(source_links) - allowed_urls
    )

    flags = []
    output_game_urls = re.findall(
        r"\[ESPN-Spielseite\]\((https://www\.espn\.com/nfl/game/[^)]+)\)",
        content,
    )
    expected_game_urls = [entry[3] for entry in game_entries]
    if output_game_urls != expected_game_urls:
        flags.append(
            f"GAME CENTER unvollstaendig: {len(output_game_urls)} "
            f"von {len(expected_game_urls)} ESPN-Spielen"
        )
    if content.count("## GAME CENTER") != 1:
        flags.append("GAME CENTER muss genau einmal vorkommen")

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
        f"- ESPN-Spiele im Input: {len(game_entries)}",
        f"- ESPN-Spiele in der Ausgabe: {len(output_game_urls)}",
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
