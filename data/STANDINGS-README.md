# NFL Tabellen – Datenanbindung

Die Startseite liest `data/standings.json`. Bis eine verlässliche automatische Datenquelle angeschlossen ist, zeigt sie einen ehrlichen Hinweis und verlinkt auf https://www.nfl.com/standings/ – keine erfundenen Tabellenwerte.

Erwartetes JSON-Format:

```json
{
  "updated_at": "2026-11-19 08:00 MEZ",
  "conferences": {
    "AFC": [
      {"name": "AFC East", "teams": [
        {"name": "Teamname", "wins": 0, "losses": 0, "ties": 0, "pct": ".000"}
      ]}
    ],
    "NFC": []
  }
}
```

Produktiv: vier Divisionen pro Conference mit vier Teams pro Division, aus einer verifizierten NFL-Standings-Datenquelle; JSON beim automatischen Build aktualisieren. Kein clientseitiges Auslesen von Google-Suchergebnissen.
