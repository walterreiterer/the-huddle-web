
#!/usr/bin/env python3
"""THE HUDDLE – Qualitätsprüfung der unveröffentlichten Testvorschau."""

import json
import re
from pathlib import Path
from urllib.parse import urlparse

FILE = Path("drafts/morning-preview.json")

def fail(message):
    raise SystemExit("QUALITAETSPRUEFUNG FEHLGESCHLAGEN: " + message)

if not FILE.is_file():
    fail("Vorschau-JSON fehlt.")

try:
    data = json.loads(FILE.read_text(encoding="utf-8"))
except (ValueError, OSError) as exc:
    fail(f"JSON nicht lesbar: {exc}")

if data.get("status") != "draft":
    fail("Ausgabe ist nicht als Entwurf gekennzeichnet.")

edition = data.get("edition")
if not isinstance(edition, dict):
    fail("Ausgabedaten fehlen.")

brief = edition.get("brief", [])
stories = edition.get("stories", [])

if not isinstance(brief, list) or not isinstance(stories, list):
    fail("Meldungen haben ein ungueltiges Format.")

print(f"Morning Brief: {len(brief)} Meldungen")
print(f"Top Stories: {len(stories)} Meldungen")

if not 3 <= len(brief) <= 5:
    fail(f"Unzulaessige Anzahl Kurzmeldungen: {len(brief)}")

if not 2 <= len(stories) <= 6:
    fail(f"Unzulaessige Anzahl Top Stories: {len(stories)}")

if len(brief) < 5:
    print("HINWEIS: Weniger als fuenf Kurzmeldungen; im Test erlaubt.")

def check_item(item, number, kind):
    if not isinstance(item, dict):
        fail(f"{kind} {number}: ungueltiges Format")

    body = str(
        item.get("text") if kind == "Brief"
        else item.get("summary", "")
    ).strip()

    url = str(item.get("source_url", "")).strip()
    parsed = urlparse(url)

    if len(body) < 65 or len(body) > 1500:
        fail(f"{kind} {number}: ungueltige Textlaenge ({len(body)})")

    if parsed.scheme != "https" or not parsed.netloc:
        fail(f"{kind} {number}: Quellenlink fehlt oder ist ungueltig")

    if re.search(r"(?:\.{3}|…)\s*$", body):
        fail(f"{kind} {number}: Text endet mit Auslassungspunkten")

    if body.endswith((",", ";", ":")):
        fail(f"{kind} {number}: Satz unvollstaendig")

    if not re.search(r'[.!?]["”\']?$', body):
        fail(f"{kind} {number}: kein vollstaendiger Schlusssatz")

    if kind == "Story":
        title = str(item.get("title", "")).strip()

        if not 15 <= len(title) <= 110:
            fail(f"Story {number}: schlechte Titel-Laenge ({len(title)})")

        if title.endswith(("…", "...", ",", ";", ":", " an")):
            fail(f"Story {number}: abgeschnittene Ueberschrift")

    print(f"OK: {kind} {number} – {parsed.netloc}")

for number, item in enumerate(brief, 1):
    check_item(item, number, "Brief")

for number, item in enumerate(stories, 1):
    check_item(item, number, "Story")

# Nur innerhalb derselben Rubrik exakte Doppelungen verhindern.
for kind, items, field in (
    ("Brief", brief, "text"),
    ("Story", stories, "summary"),
):
    seen = set()
    for item in items:
        normalized = re.sub(
            r"\W+", "", str(item.get(field, "")).lower()
        )
        if normalized in seen:
            fail(f"Doppelte Meldung in {kind}")
        seen.add(normalized)

date = str(edition.get("date", "")).strip()
if not date:
    fail("Ausgabedatum fehlt.")

print("")
print("QUALITAETSPRUEFUNG BESTANDEN.")
print("Status: unveroeffentlichte Testvorschau.")
print("Hinweis: Kein journalistischer Faktencheck.")
