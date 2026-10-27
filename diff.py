#!/usr/bin/env python3
"""(c) Oliver Bedernik · Terra-Kit · Diff-Bericht für „neu setzen“

Vergleicht zwei Fassungen eines Werks und fasst die inhaltlichen Änderungen
zusammen: Kacheln neu, entfernt, umbenannt, geändert (je Bausteintyp), dazu
Quellen, Lexicon, Selbsttest und Quellenkritik. Mit --eintragen wird der
Bericht als Eintrag ins Änderungsprotokoll (aenderungen) der neuen Fassung
geschrieben; Versionsnummer und Datum kommen aus meta bzw. dem heutigen Tag.

    python3 diff.py alt.json neu.json [--eintragen]
"""
import datetime as dt
import json
import sys
from pathlib import Path

NAMEN = {"definition": "Definition", "kern": "Kern", "formel": "Formel", "rechenweg": "Rechenweg",
         "schema": "Schema", "beispiel": "Beispiel", "merke": "Merke", "feinheit": "Feinheit",
         "klausurfalle": "Klausurfalle", "austriacum": "Austriacum", "aktualisierung": "Aktualisierung",
         "latinum": "Latinum", "luecke": "Lücke"}


def kacheln(werk):
    return {k["code"]: k for p in werk.get("provinzen", []) for k in p.get("kacheln", [])}


def j(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True)


def geaenderte_bausteine(a, b):
    """Typnamen der Bausteine, die hinzukamen, wegfielen oder sich änderten."""
    alt, neu = {}, {}
    for z, k in ((alt, a), (neu, b)):
        for x in k.get("bausteine", []):
            z.setdefault(x["typ"], []).append(j(x))
    typen = [t for t in sorted(set(alt) | set(neu), key=lambda t: list(NAMEN).index(t) if t in NAMEN else 99)
             if alt.get(t) != neu.get(t)]
    rest = {key for key in set(a) | set(b) if key not in ("bausteine", "code", "titel") and a.get(key) != b.get(key)}
    return [NAMEN.get(t, t) for t in typen] + sorted(rest)


def vergleiche(alt, neu):
    ka, kn = kacheln(alt), kacheln(neu)
    bericht = {"neu": sorted(set(kn) - set(ka)), "entfernt": sorted(set(ka) - set(kn)),
               "umbenannt": [], "geaendert": []}
    for c in sorted(set(ka) & set(kn)):
        if ka[c].get("titel") != kn[c].get("titel"):
            bericht["umbenannt"].append((c, ka[c].get("titel"), kn[c].get("titel")))
        teile = geaenderte_bausteine(ka[c], kn[c])
        if teile:
            bericht["geaendert"].append((c, teile))
    bericht["teile"] = []
    for teil, name in (("quellen", "Quellen"), ("lexicon", "Lexicon"), ("selbsttest", "Selbsttest"),
                       ("quellenkritik", "Quellenkritik"), ("modul", "Domänenmodul"), ("motto", "Motto")):
        a, b = alt.get(teil), neu.get(teil)
        if j(a) != j(b):
            if isinstance(a, list) and isinstance(b, list):
                d = len(b) - len(a)
                bericht["teile"].append(f"{name} ({'+' if d > 0 else ''}{d} Einträge)" if d else f"{name} überarbeitet")
            else:
                bericht["teile"].append(f"{name} geändert")
    return bericht


def als_text(b):
    """Ein Satz je Änderungsart; Gedankenstriche vermieden, Satzzeichen wie im Werk."""
    teile = []
    if b["neu"]:
        teile.append("neue Kacheln " + ", ".join(b["neu"]))
    if b["entfernt"]:
        teile.append("entfernt " + ", ".join(b["entfernt"]))
    if b["umbenannt"]:
        teile.append("umbenannt " + ", ".join(f"{c} („{n}“)" for c, _, n in b["umbenannt"]))
    if b["geaendert"]:
        teile.append("überarbeitet " + ", ".join(f"{c} ({', '.join(t)})" for c, t in b["geaendert"]))
    teile += b["teile"]
    if not teile:
        return ""
    s = "; ".join(teile)
    return s[0].upper() + s[1:]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        sys.exit("Aufruf: python3 diff.py alt.json neu.json [--eintragen]")
    alt, neu = (json.loads(Path(a).read_text(encoding="utf-8")) for a in args)
    b = vergleiche(alt, neu)
    text = als_text(b)
    va, vn = alt["meta"]["version"], neu["meta"]["version"]
    print(f"Diff {neu['meta']['titel']}: Version {va} → {vn}")
    print(text or "keine inhaltlichen Änderungen")
    if vn == va and text:
        print("WARNUNG  meta.version unverändert, obwohl sich der Inhalt geändert hat")
    if "--eintragen" in sys.argv and text:
        protokoll = neu.setdefault("aenderungen", [])
        if any(e["version"] == vn for e in protokoll):
            sys.exit(f"Für Version {vn} besteht bereits ein Eintrag; Version erhöhen oder Eintrag von Hand ergänzen")
        protokoll.append({"version": vn, "datum": dt.date.today().isoformat(), "text": text})
        Path(args[1]).write_text(json.dumps(neu, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"Eingetragen in {args[1]}: Version {vn}")


if __name__ == "__main__":
    main()
