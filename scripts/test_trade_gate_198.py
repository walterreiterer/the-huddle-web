#!/usr/bin/env python3
"""THE HUDDLE 1.9.8 – isolierter Regressionstest für Trade-Sperre 1.9.7."""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

MARKER = 'TESTENTWURF – AUTOMATISCH ERSTELLT, NICHT VERÖFFENTLICHEN'
FIXTURE = f'''{MARKER}

# THE HUDDLE – künstlicher Funktionstest

## THE LEAD

**Trade-Deadline: Team könnte Quarterback traden**

Vor der Trade-Deadline könnte ein Team einen Trade erwägen. Dies ist eine erfundene Testmeldung.

**Team bestätigt neuen Trainer**

Eine erfundene, unproblematische Testmeldung ohne Trade-Bezug.

## AROUND THE LEAGUE

**Weitere Meldung ohne Wechselgerüchte**

Nur Testdaten.

## GAME CENTER

Keine echten Ergebnisse – nur ein Funktionstest.
'''


def run_case(script, cutoff, expected_status, expected_blocked):
    with tempfile.TemporaryDirectory(prefix='huddle-198-') as tmp:
        root = Path(tmp)
        drafts = root / 'drafts'
        drafts.mkdir()
        original = drafts / 'the-huddle-probeausgabe-193.md'
        original.write_text(FIXTURE, encoding='utf-8')
        env = dict(os.environ, NFL_TRADE_DEADLINE_UTC=cutoff)
        proc = subprocess.run([sys.executable, str(script)], cwd=root, env=env,
                              text=True, capture_output=True, timeout=30)
        if proc.returncode:
            raise AssertionError(f'Gate fehlgeschlagen: {proc.stderr or proc.stdout}')
        result = json.loads((drafts / 'trade-sperre-197.json').read_text(encoding='utf-8'))
        safe = (drafts / 'the-huddle-gefilterter-testentwurf-197.md').read_text(encoding='utf-8')
        assert result['status'] == expected_status, result
        assert result['blocked_count'] == expected_blocked, result
        assert result['publication_approved'] is False, result
        assert MARKER in safe, 'Testentwurf-Kennzeichnung fehlt'
        assert original.read_text(encoding='utf-8') == FIXTURE, 'Original wurde verändert'
        assert '**Team bestätigt neuen Trainer**' in safe, 'Unproblematische Meldung entfernt'
        assert ('**Trade-Deadline: Team könnte Quarterback traden**' in safe) == (expected_blocked == 0), 'Trade-Filter wirkt nicht wie erwartet'
        return result


def main():
    script = Path(__file__).resolve().parent / 'scripts' / 'trade_deadline_gate_197.py'
    if not script.is_file():
        raise SystemExit(f'Benötigtes Originalskript fehlt: {script}')
    now = datetime.now(timezone.utc)
    future = (now + timedelta(days=30)).isoformat()
    past = (now - timedelta(days=30)).isoformat()
    cases = [('Vor Fristablauf', future, 'FRIST_NOCH_NICHT_ERREICHT', 0),
             ('Nach Fristablauf', past, 'MELDUNGEN_GESPERRT', 1)]
    lines = ['# THE HUDDLE – isolierter Härtetest 1.9.8', '',
             '**Nur künstliche Testmeldungen. Keine Veröffentlichung.**', '']
    errors = []
    for name, cutoff, status, blocked in cases:
        try:
            run_case(script, cutoff, status, blocked)
            lines.append(f'- PASS: {name} – Status `{status}`, zurückgestellt: {blocked}')
            print(f'PASS: {name}')
        except Exception as exc:
            errors.append(f'{name}: {exc}')
            lines.append(f'- FAIL: {name} – {exc}')
            print(f'FAIL: {name}: {exc}', file=sys.stderr)
    lines += ['', 'Die konfigurierte echte NFL-Deadline wurde nicht geändert.',
              'Die bestehenden Entwürfe wurden nicht verändert.',
              'Der Test bewertet nur die hier definierten Muster, keinen vollständigen Faktencheck.', '']
    out = Path('drafts') / 'haertetest-198.md'
    out.parent.mkdir(exist_ok=True)
    out.write_text('\n'.join(lines), encoding='utf-8')
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
