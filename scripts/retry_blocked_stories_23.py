#!/usr/bin/env python3
"""THE HUDDLE 2.3: einmaliger, konservativer Wiederholungsversuch für gesperrte Stories.

Nur vollständig geprüfte, einzeln gesperrte STORY-Einträge dürfen entfernt werden.
Lead, Brief, Austrian Watch, Game Center und globale Sperren bleiben unangetastet.
Keine Veröffentlichung; bei jedem Fehler bleibt die Sperre bestehen.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

D = Path("drafts")
PREVIEW = D / "morning-preview.json"
REVIEW = D / "gegenpruefung-195.json"
REPORT = D / "retry-blocked-23.json"

def write_report(status, reason, **extra):
    REPORT.write_text(json.dumps({"status": status, "grund": reason,
        "freigabe": False, "veroeffentlicht": False, **extra},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def plan(preview, review):
    meta = review.get("metadaten", {})
    if not isinstance(meta, dict) or meta.get("vollstaendig") is not True:
        return None, "Gegenprüfung nicht vollständig"
    if review.get("gesamtstatus") != "SPERREN":
        return [], "Keine gesperrte Ausgabe"
    if not isinstance(preview.get("edition"), dict):
        return None, "Ausgabe fehlt"
    edition = preview["edition"]
    stories = edition.get("stories")
    entries = review.get("meldungen")
    if not isinstance(stories, list) or not isinstance(entries, list):
        return None, "Stories oder Einzelbewertungen fehlen"
    blocked = [x for x in entries if isinstance(x, dict) and x.get("status") == "SPERREN"]
    if not blocked:
        return None, "Gesamtsperre ohne gesperrte Einzelmeldung"
    ids = []
    for item in blocked:
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier.startswith("STORY-"):
            return None, "Sperre außerhalb der Top Stories: " + str(identifier)
        try:
            index = int(identifier.split("-", 1)[1])
        except ValueError:
            return None, "Ungültige Story-ID"
        if not (1 <= index <= len(stories)) or identifier != f"STORY-{index}":
            return None, "Story-ID passt nicht zur Ausgabe"
        ids.append(index)
    if len(set(ids)) != len(ids) or len(stories) - len(ids) < 1:
        return None, "Doppelte Sperre oder keine Top Story übrig"
    # Keine ungeklärte globale Sperre übergehen.
    cross = review.get("uebergreifend", [])
    if not isinstance(cross, list):
        return None, "Übergreifende Prüfung ungültig"
    if any(str(x).strip() for x in cross):
        return None, "Übergreifende Prüfhinweise: manuelle Klärung erforderlich"
    return sorted(ids), "Einzelne Top Stories können entfernt werden"

def main():
    if not PREVIEW.is_file() or not REVIEW.is_file():
        print("Retry 2.3: Eingabedateien fehlen; Sperre bleibt bestehen.")
        return 0
    try:
        preview = json.loads(PREVIEW.read_text(encoding="utf-8"))
        review = json.loads(REVIEW.read_text(encoding="utf-8"))
        ids, reason = plan(preview, review)
        if ids is None:
            write_report("NICHT_WIEDERHOLT", reason)
            print("Retry 2.3:", reason)
            return 0
        if not ids:
            write_report("NICHT_NOETIG", reason)
            print("Retry 2.3:", reason)
            return 0
        # Originale zur Nachvollziehbarkeit sichern.
        for path in (PREVIEW, REVIEW, D / "gegenpruefung-195.md"):
            if path.is_file():
                shutil.copy2(path, D / (path.stem + "-vor-retry-23" + path.suffix))
        edition = preview["edition"]
        edition["stories"] = [x for i, x in enumerate(edition["stories"], 1) if i not in ids]
        preview["status"] = "draft"
        preview["published_at"] = None
        preview["editorial_review"] = {"version": "2.3", "status": "SPERREN",
            "approved": False, "message": "Erneute Gegenprüfung erforderlich"}
        PREVIEW.write_text(json.dumps(preview, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        write_report("WIEDERHOLUNG_GESTARTET", reason, entfernte_story_ids=[f"STORY-{i}" for i in ids])
        proc = subprocess.run([sys.executable, "scripts/review_independent_195.py"], check=False)
        try:
            updated = json.loads(REVIEW.read_text(encoding="utf-8"))
            ok = updated.get("metadaten", {}).get("vollstaendig") is True and updated.get("gesamtstatus") in ("UNAUFFAELLIG", "MANUELL_PRUEFEN")
        except (ValueError, OSError, AttributeError):
            ok = False
        if proc.returncode or not ok:
            # Keine unzureichend geprüfte, gekürzte Ausgabe als zulässigen Entwurf behandeln.
            write_report("WEITER_GESPERRT", "Erneute Gegenprüfung nicht erfolgreich",
                         entfernte_story_ids=[f"STORY-{i}" for i in ids])
        else:
            write_report("INTERNER_ENTWURF", "Erneut geprüft; weiterhin keine Freigabe",
                         entfernte_story_ids=[f"STORY-{i}" for i in ids],
                         gegenpruefung=updated["gesamtstatus"])
        print("Retry 2.3:", json.loads(REPORT.read_text(encoding="utf-8"))["status"])
    except (OSError, ValueError, TypeError, KeyError) as exc:
        write_report("FEHLER", str(exc)[:300])
        print("Retry 2.3 Fehler:", exc, file=sys.stderr)
    return 0  # Verbindliche Sperre erfolgt im bestehenden check_editorial_status.py

if __name__ == "__main__":
    sys.exit(main())
