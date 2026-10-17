#!/usr/bin/env bash
# (c) Oliver Bedernik · Terra-Kit · einrichten.sh
# Richtet das Kit in einer frischen Umgebung ein und prüft es vollständig.
# Aufruf im Kit-Ordner:  bash einrichten.sh
set -euo pipefail
cd "$(dirname "$0")"
echo "Terra-Kit: Python-Abhängigkeiten"
pip install -q -r requirements.txt --break-system-packages 2>/dev/null || pip install -q -r requirements.txt
echo "Terra-Kit: Schriften und Formelsatz (fest versioniert)"
npm ci --silent --no-audit --no-fund 2>/dev/null || npm install --silent --no-audit --no-fund
echo "Terra-Kit: Testreihe"
python3 tests/run_tests.py | tail -1
python3 skript.py referenzwerk.json --aus /tmp/terra-pruefung | tail -1
python3 skript.py referenz_historica.json --aus /tmp/terra-pruefung | tail -1
echo "Terra-Kit bereit."
