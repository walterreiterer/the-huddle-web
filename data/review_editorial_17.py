#!/usr/bin/env python3
"""THE HUDDLE 1.7: eigenständige redaktionelle Gegenprüfung.
Nur Bericht unter drafts/; keine Veröffentlichung oder Änderungen an Entwürfen.
Aufruf: python scripts/review_editorial_17.py [--ai]
"""
import argparse
import json
import os
import re
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

ROOT = Path("drafts")
DRAFT = ROOT / "the-huddle-morgenausgabe-13.md"
SOURCES = ROOT / "quellen-10.json"
GAMES = ROOT / "nfl-spiele-08.md"
REPORT = ROOT / "redaktionelle-gegenpruefung-17.md"
MODEL = os.getenv("HUDDLE_REVIEW_MODEL", "gpt-5-mini")
URL_RE = re.compile(r"https?://[^\s<>\])}\"']+", re.I)

def norm_url(url):
    try:
        u = urlsplit(url.strip().rstrip(".,;"))
        return urlunsplit((u.scheme.lower(), u.netloc.lower(), u.path.rstrip("/"), "", ""))
    except ValueError:
        return url.strip()

def source_context(draft):
    if not SOURCES.is_file():
        return "Quellen-JSON fehlt; Beleglage NICHT ÜBERPRÜFBAR.", 0
    data = json.loads(SOURCES.read_text(encoding="utf-8"))
    articles = data.get("articles", [])
    if not isinstance(articles, list):
        raise ValueError("articles muss eine Liste sein")
    urls = {norm_url(u) for u in URL_RE.findall(draft)}
    matched, remaining = [], []
    for article in articles:
        if not isinstance(article, dict):
            continue
        (matched if norm_url(str(article.get("url", ""))) in urls else remaining).append(article)
    # Verlinkte Originalquellen zuerst; übrige nur als zusätzlicher Kontext,
    # ausdrücklich NICHT als Beleg einer bestimmten Aussage.
    selected = matched[:20]
    extra = remaining[:5]
    def compact(a, limit):
        return {"title": str(a.get("title", ""))[:220],
                "url": str(a.get("url", ""))[:500],
                "published": str(a.get("published", ""))[:100],
                "text_excerpt": str(a.get("text", ""))[:limit]}
    context = {
        "matched_sources": [compact(a, 1800) for a in selected],
        "unmatched_background_sources_not_evidence": [compact(a, 450) for a in extra],
        "matched_count": len(matched),
        "matched_included": len(selected),
        "notice": "Auszüge sind unvollständig. Nicht enthalten bedeutet nicht widerlegt."
    }
    return json.dumps(context, ensure_ascii=False, indent=2), len(matched)

def basic_flags(draft):
    flags = []
    if not draft.startswith("TESTENTWURF – AUTOMATISCH ERSTELLT, NICHT VERÖFFENTLICHEN"):
        flags.append("Entwurfskennzeichnung fehlt oder weicht ab.")
    if not re.search(r"^# THE HUDDLE", draft, re.M):
        flags.append("THE HUDDLE-Hauptüberschrift fehlt.")
    if re.search(r"\b(heute|morgen|gestern|am Wochenende)\b", draft, re.I):
        flags.append("Relative Zeitangaben: mit Datum und Wiener Uhrzeit prüfen.")
    if re.search(r"\b(trade|wechsel|transfer)\b", draft, re.I):
        flags.append("Transferstatus anhand einer Originalquelle prüfen.")
    # Harte Warnung bei vollendeter Transfer-Headline und gleichzeitig offenem Status.
    if re.search(r'(?im)^\*\*[^\n]*(?:holen|verpflichten|wechselt zu|trade perfekt)[^\n]*\*\*', draft) and re.search(r'(?i)\b(?:soll|angeblich|offenbar|voraussichtlich|noch nicht bestätigt|formalisiert werden)\b', draft):
        flags.append('PRÜFPFLICHT: Transfer-Headline klingt abgeschlossen, während der Text Vorbehalte enthält. Status pro Meldung abgleichen.')
    return flags

def request_review(draft, sources, games, now):
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY fehlt.")
    instructions = (
        "Du bist eine STRIKTE, skeptische unabhängige Qualitätskontrolle eines deutschen NFL-Briefs. "
        "Schreibe nur einen Markdown-Prüfbericht, keine korrigierte Ausgabe. "
        "Prüfe JEDE einzelne Tatsachenbehauptung in Überschrift und Text getrennt, "
        "einschließlich Verletzungsdetails, Namen, Zitaten, Personalstatus und rechtlich sensiblen Behauptungen. "
        "Eine Quelle zum selben Thema genügt NICHT für BELEGT. BELEGT nur, wenn die konkrete "
        "Behauptung im zugeordneten Quellenauszug ausdrücklich steht; zitiere dazu eine kurze "
        "stützende Passage aus dem übergebenen Auszug (maximal 15 Wörter) und die URL. "
        "Unterscheide BELEGT, WIDERSPRUCH, NICHT BELEGT, NICHT ÜBERPRÜFBAR und EMPFEHLUNG. "
        "WIDERSPRUCH nur bei konkretem Gegenbeleg oder internem Konflikt. "
        "NICHT BELEGT heißt: vorliegender Auszug enthält keinen Beleg, nicht dass die Aussage falsch ist. "
        "NICHT ÜBERPRÜFBAR heißt: entscheidende Quelle fehlt, ist gekürzt oder der Sachstand kann sich "
        "seit dem Abruf geändert haben. Fehlende Belege NIEMALS als BELEGT deklarieren. "
        "Prüfe besonders abgeschlossene Transfer-Überschriften gegen geplante oder nur berichtete Deals. "
        "Prüfe absolute und relative Zeitangaben anhand der Wiener Prüfzeit und der Spiel-UTC-Zeit. "
        "Unterscheide ausdrücklich: Quelle belegt Stand bei Abruf vs. aktueller Stand nicht überprüfbar. "
        "Bei rechtlich sensiblen Vorwürfen: jede Zuschreibung, Ermittlungs- und Verfahrensbehauptung "
        "separat prüfen; keine ungeprüften juristischen Ergänzungen empfehlen. "
        "Prüfe Dopplungen, Nachrichtenwert und Spielstatus. "
        "Gliedere in 'Sperrgründe vor Veröffentlichung', 'Einzelprüfung nach Meldung', "
        "'Zeit- und Spielstatus' und 'Redaktionelle Prioritäten'. "
        "Für jeden kritischen Befund nenne die genaue Textstelle, Kategorie, Grund, URL wenn vorhanden "
        "und eine konkrete Handlung. Keine Live-Recherche behaupten, keine Fakten erfinden, "
        "keine automatische Freigabe. Bei Zweifel NICHT ÜBERPRÜFBAR. "
        "Beginne mit '# THE HUDDLE – Redaktionelle Gegenprüfung 1.7' und "
        "ende mit 'Status: manuelle Freigabe weiterhin erforderlich.'"
    )
    body = (f"Prüfzeit Wien: {now}\n\nENTWURF:\n{draft[:26000]}\n\n"
            f"ZUORDNUNG DER QUELLENAUSZÜGE:\n{sources[:30000]}\n\n"
            f"SPIELDATEN (gegebenenfalls unvollständig):\n{games[:12000]}")
    payload = {"model": MODEL, "instructions": instructions, "input": body,
               "max_output_tokens": 12000, "store": False}
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            response = json.load(resp)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"OpenAI HTTP {exc.code}: {exc.read(500).decode('utf-8', 'replace')}") from exc
    if response.get("status") != "completed":
        raise RuntimeError("KI-Antwort nicht vollständig: " + str(response.get("status")) +
                           "; Details: " + json.dumps(response.get("incomplete_details"), ensure_ascii=False))
    chunks = [c.get("text", "") for item in response.get("output", [])
              if item.get("type") == "message"
              for c in item.get("content", []) if c.get("type") == "output_text"]
    result = "\n".join(chunks).strip()
    if not result.startswith("# THE HUDDLE – Redaktionelle Gegenprüfung 1.7") or \
       "Status: manuelle Freigabe weiterhin erforderlich." not in result:
        raise RuntimeError("KI-Prüfbericht unvollständig oder im falschen Format.")
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ai", action="store_true", help="Kostenpflichtige KI-Gegenprüfung")
    args = parser.parse_args()
    if not DRAFT.is_file():
        raise SystemExit("Entwurf fehlt: " + str(DRAFT))
    draft = DRAFT.read_text(encoding="utf-8")
    now = datetime.now(ZoneInfo("Europe/Vienna")).isoformat(timespec="minutes")
    sources, matched = source_context(draft)
    games = GAMES.read_text(encoding="utf-8") if GAMES.is_file() else \
        "Spieldatei fehlt; Spielstatus NICHT ÜBERPRÜFBAR."
    flags = basic_flags(draft)
    lines = ["# THE HUDDLE – Redaktionelle Gegenprüfung 1.7", "",
             f"Prüfzeit Wien: {now}", f"Passende Quelleneinträge: {matched}", "",
             "Status: UNVERÖFFENTLICHT – keine automatische Freigabe.", "",
             "## Lokale Hinweise"]
    lines += ["- " + f for f in flags] if flags else ["- Keine einfachen Auffälligkeiten gefunden."]
    if args.ai:
        lines += ["", "## KI-Gegenprüfung", "",
                  request_review(draft, sources, games, now)]
    else:
        lines += ["", "## KI-Gegenprüfung", "",
                  "- Nicht ausgeführt; optional mit `--ai` starten."]
    lines += ["", "Status: manuelle Freigabe weiterhin erforderlich.", ""]
    ROOT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Bericht erstellt: {REPORT}; passende Quellen: {matched}; KI: {args.ai}")
    print("Entwurf, Vorschau und Website unverändert.")

if __name__ == "__main__":
    main()
