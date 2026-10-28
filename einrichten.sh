#!/usr/bin/env bash
# (c) Oliver Bedernik · Terra-Kit · einrichten.sh
# Richtet das Kit in einer frischen Umgebung ein und prüft es vollständig.
# Aufruf im Kit-Ordner:  bash einrichten.sh
set -euo pipefail
cd "$(dirname "$0")"
echo "Terra-Kit v$(cat VERSION)"
python3 versionspruefung.py || true
echo "Terra-Kit: Systemwerkzeuge"
# Vorabprüfung (3.5): Die PDF-Prüfungen brauchen poppler-utils, die Symbolschrift DejaVu Sans.
fehlt=""
for w in pdftotext pdffonts pdfimages pdftoppm; do command -v "$w" >/dev/null 2>&1 || fehlt="$fehlt $w"; done
[ -f /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf ] || fehlt="$fehlt DejaVuSans"
if [ -n "$fehlt" ]; then
  echo "Es fehlt:$fehlt; Installation wird versucht (poppler-utils, fonts-dejavu-core)"
  SUDO=""; if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi
  { $SUDO apt-get update -q && $SUDO apt-get install -y -q poppler-utils fonts-dejavu-core; } >/tmp/terra-apt.log 2>&1 || true
  for w in pdftotext pdffonts pdfimages pdftoppm; do
    command -v "$w" >/dev/null 2>&1 || { echo "FEHLER: $w fehlt und ließ sich nicht installieren:"; tail -5 /tmp/terra-apt.log; exit 1; }
  done
  [ -f /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf ] || { echo "FEHLER: DejaVu Sans fehlt (fonts-dejavu-core)"; exit 1; }
fi
echo "Terra-Kit: Python-Abhängigkeiten"
if ! pip install -q -r requirements.txt --break-system-packages 2>/tmp/terra-pip.log; then
  pip install -q -r requirements.txt 2>>/tmp/terra-pip.log || { echo "FEHLER: pip-Installation gescheitert:"; tail -5 /tmp/terra-pip.log; exit 1; }
fi
echo "Terra-Kit: Schriften und Formelsatz (fest versioniert)"
npm ci --silent --no-audit --no-fund 2>/tmp/terra-npm.log || npm install --silent --no-audit --no-fund 2>>/tmp/terra-npm.log || { echo "FEHLER: npm gescheitert:"; tail -5 /tmp/terra-npm.log; exit 1; }
echo "Terra-Kit: Testreihe"
python3 tests/run_tests.py | tail -1
python3 skript.py referenzwerk.json --aus /tmp/terra-pruefung | tail -1
python3 skript.py referenz_historica.json --aus /tmp/terra-pruefung | tail -1
echo "Terra-Kit bereit."
