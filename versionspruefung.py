#!/usr/bin/env python3
"""(c) Oliver Bedernik · Terra-Kit · Versionswarnung

Vergleicht die Version dieses Kits mit dem neuesten Release auf GitHub.
Releases entstehen nur nach grüner Testreihe (.github/workflows/pruefung.yml),
daher gilt als „neueste Version“ ausschließlich ein geprüfter Release.
Bricht nie ab: ohne Netz oder bei API-Fehlern genügt ein Hinweis.

    python3 versionspruefung.py
"""
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = "Yelloww2773/terra-kit"
HIER = Path(__file__).resolve().parent
RE_SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def zerlege(v):
    """„v3.3.0“ oder „3.3.0“ → (3, 3, 0); alles andere → None."""
    m = RE_SEMVER.match((v or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def bewerte(lokal, entfernt):
    """Liefert (Stufe, Meldung); Stufe ist „aktuell“, „veraltet“, „neuer“ oder „unklar“."""
    a, b = zerlege(lokal), zerlege(entfernt)
    if not a or not b:
        return "unklar", f"Versionsvergleich nicht möglich (lokal {lokal}, GitHub {entfernt})"
    if a < b:
        return "veraltet", (f"ACHTUNG: Neuere Kit-Version verfügbar: {entfernt} (verwendet: v{lokal}). "
                            "Werk-Prompt und Download-Befehl auf die neue Version heben.")
    if a > b:
        return "neuer", f"Kit v{lokal} ist neuer als der letzte Release {entfernt} (Entwicklungsstand)"
    return "aktuell", f"Kit v{lokal} ist die neueste freigegebene Version"


class _KeineWeiterleitung(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def neuester_release(timeout=6):
    """Liest den Tag des neuesten Release aus der Weiterleitung von /releases/latest.

    Bewusst nicht über api.github.com: Die API erlaubt ohne Anmeldung nur 60 Abfragen
    je Stunde und IP; in geteilten Sandboxen ist das Kontingent regelmäßig erschöpft.
    """
    url = f"https://github.com/{REPO}/releases/latest"
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "terra-kit-versionspruefung"})
    try:
        urllib.request.build_opener(_KeineWeiterleitung).open(req, timeout=timeout)
    except urllib.error.HTTPError as ex:
        ziel = ex.headers.get("Location", "")
        if ex.code in (301, 302) and "/releases/tag/" in ziel:
            return ziel.rsplit("/", 1)[-1]
        if ex.code in (301, 302):
            raise urllib.error.HTTPError(url, 404, "kein Release", ex.headers, None)
        raise
    raise urllib.error.HTTPError(url, 404, "kein Release", {}, None)


def main():
    lokal = (HIER / "VERSION").read_text(encoding="utf-8").strip()
    try:
        entfernt = neuester_release()
    except urllib.error.HTTPError as ex:
        if ex.code == 404:
            print(f"Noch kein geprüfter Release auf GitHub; Kit v{lokal}")
            return 0
        print(f"Versionsprüfung übersprungen (HTTP {ex.code}); Kit v{lokal}")
        return 0
    except Exception as ex:  # kein Netz, Zeitüberschreitung
        print(f"Versionsprüfung übersprungen ({type(ex).__name__}); Kit v{lokal}")
        return 0
    print(bewerte(lokal, entfernt)[1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
