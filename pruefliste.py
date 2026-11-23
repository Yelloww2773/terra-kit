#!/usr/bin/env python3
"""(c) Oliver Bedernik · Terra-Kit 4.0 · Prüfliste für den Advocatus diaboli

Zieht alle angreifbaren Angaben eines Werks (Standard 4.0) in eine Tabelle: Normzitate,
Rechtsprechung, Zahlen, Daten und Auflagen, jeweils mit Abschnitt und Kontext, einschließlich
Fließtext, Randbelegen, Kapiteleinleitungen und Kontrollfragen; dazu jeder Rechenweg mit dem
Stand seiner Rechenprobe, jedes Rasterbild mit Quelle und Lizenz (Rechte und Nachweis prüfen)
und jeder Randbeleg mit Quelle und Fundstelle (Belegstelle aufschlagen).
Die Tabelle ist die Arbeitsgrundlage des Gegenprüfungsdurchgangs (Ablauf 5).

    python3 pruefliste.py werk.json [--aus pruefliste.md]
"""
import json
import re
import sys
from pathlib import Path

from validate import RE_GZ, alle_strings, ist_roh, abschnitte, bloecke

RE_NORM = re.compile(r"(?:§§?|Art)\s?\d+[a-z]?(?:\s?(?:Abs|Z|lit|Satz)\s?[0-9a-z]+)*(?:\s?(?:und|bis|,)\s?\d+[a-z]?)*"
                     r"(?:\s(?:[A-ZÄÖÜ][A-Za-zÄÖÜäöü-]*[A-Z][A-Za-z-]*|StGG|EMRK|AEUV|EUV|GRC))?")
RE_DATUM = re.compile(r"\b\d{1,2}\.\s?\d{1,2}\.\s?(?:1[0-9]|20)\d{2}\b|\b(?:1[0-9]|20)\d{2}\b")
RE_ZAHL = re.compile(r"(?<![\w.§])\d{1,3}(?:\.\d{3})*(?:,\d+)?\s?(?:%|‰|Prozent|EUR|€|Euro|Mio|Mrd|Jahre|Monate|Wochen|Tage|Stunden)"
                     r"|(?<![\w.§/])\d+,\d+(?![\w/])")
RE_HOCHZAHL = re.compile(r"[A-Za-zÄÖÜäöü]+[⁰¹²³⁴⁵⁶⁷⁸⁹]+")
RE_JAHRESSPANNE = re.compile(r"^(?:1[0-9]|20)\d{2}/\d{2}$")
KONTEXT = 45


def fundorte(werk):
    """(Ort, Text) für alle prüfbaren Texte; Ort ist Abschnittscode oder Werkteil."""
    for k in werk.get("kapitel", []):
        for teil in ("einleitung", "abschluss", "kompakt", "kontrollfragen"):
            for pfad, s in alle_strings(k.get(teil, [])):
                if not ist_roh(pfad):
                    yield f'{k["code"]} {teil.capitalize()}', s
    for _, a in abschnitte(werk):
        for pfad, s in alle_strings(a):
            if not ist_roh(pfad) and not pfad.endswith(".code"):
                yield a["code"], s
    for teil in ("lexicon", "quellenkritik", "personen"):
        for pfad, s in alle_strings(werk.get(teil, [])):
            yield teil, s


def eintraege(werk):
    gesehen, zeilen = set(), []

    def neu(kat, ort, wert, text, m):
        a, e = max(0, m.start() - KONTEXT), min(len(text), m.end() + KONTEXT)
        schluessel = (kat, ort, wert.strip())
        if schluessel not in gesehen:
            gesehen.add(schluessel)
            zeilen.append({"kategorie": kat, "ort": ort, "wert": wert.strip(),
                           "kontext": ("…" if a else "") + text[a:e].replace("\n", " ") + ("…" if e < len(text) else "")})

    for ort, s in fundorte(werk):
        normen = list(RE_NORM.finditer(s))
        for m in normen:
            neu("Norm", ort, m.group(), s, m)
        belegt = [range(m.start(), m.end()) for m in normen]
        for m in RE_GZ.finditer(s):
            # Jahresspannen wie 1814/15 sind Daten, keine Geschäftszahlen
            neu("Datum" if RE_JAHRESSPANNE.match(m.group()) else "Rechtsprechung", ort, m.group(), s, m)
        for m in RE_DATUM.finditer(s):
            if not any(m.start() in r for r in belegt):
                neu("Datum", ort, m.group(), s, m)
        for m in RE_ZAHL.finditer(s):
            if not any(m.start() in r for r in belegt) and s[max(0, m.start() - 3):m.start()] != "D. ":
                neu("Zahl", ort, m.group(), s, m)
        for m in RE_HOCHZAHL.finditer(s):
            neu("Auflage", ort, m.group(), s, m)
    import rechenprobe as R  # Rechnungen, Bildrechte und Randbelege
    for ort, b in bloecke(werk):
        k = {"code": ort.split()[0]}
        if True:
            if True:
                if b.get("typ") == "rechenweg":
                    if not b.get("probe"):
                        stand = "ungeprüft: keine Rechenprobe, jeden Schritt von Hand nachrechnen"
                    else:
                        try:
                            zz, (ist, st) = R.pruefe(b["probe"])
                            stand = ("Rechenprobe bestanden" if all(z[4] for z in zz) else "Rechenprobe ABWEICHUNG") + f", Endwert {R.at(ist, st)}"
                            stand += "; Ausgangswerte gegen die Aufgabe prüfen: " + ", ".join(f"{n} = {v}" for n, v in b["probe"].get("werte", {}).items())
                        except R.ProbeFehler as e:
                            stand = f"Rechenprobe nicht berechenbar: {e}"
                    zeilen.append({"kategorie": "Rechnung", "ort": k["code"], "wert": b.get("ergebnis", ""), "kontext": stand})
                if b.get("variante") == "bild":
                    zeilen.append({"kategorie": "Bildrecht", "ort": k["code"], "wert": b.get("lizenz", ""),
                                   "kontext": f"{b.get('titel', '')}: {b.get('quelle', '')}" + (f", {b['urheber']}" if b.get("urheber") else "")})
    import skript
    namen = {x: q["kurz"] for q in werk.get("quellen", []) for x in skript.quell_schluessel(q)}
    for ort, t in skript.texte(werk):
        try:
            _, fns = skript.fussnoten_zerlegen(t)
        except ValueError:
            continue
        for fn in fns:
            for m in re.finditer(r"@([A-Za-z0-9ÄÖÜäöü]+)(?:\s*\(([^)]*)\))?([^;@]*)", fn):
                stelle = (m.group(2) or m.group(3) or "").strip(" .;")
                schl = ("Beleg", ort.split()[0], m.group(1), stelle)
                if schl not in gesehen:
                    gesehen.add(schl)
                    zeilen.append({"kategorie": "Beleg", "ort": ort.split()[0], "wert": f'{namen.get(m.group(1), m.group(1))} {stelle}'.strip(),
                                   "kontext": "Belegstelle aufschlagen: trägt sie die Aussage des Satzes?"})
    for q in werk.get("quellen", []):
        if q.get("auflage"):
            wert = f"{q['kurz']}: {q['auflage']}. Auflage {q.get('jahr', '')}".strip()
            zeilen.append({"kategorie": "Auflage", "ort": "Quellen", "wert": wert, "kontext": q.get("titel", "")})
    reihe = ["Norm", "Rechtsprechung", "Datum", "Zahl", "Rechnung", "Bildrecht", "Beleg", "Auflage"]
    zeilen.sort(key=lambda z: reihe.index(z["kategorie"]))
    return zeilen


def als_markdown(werk, zeilen):
    m = werk["meta"]
    kopf = [f"# Prüfliste {m['titel']} · Version {m['version']}", "",
            "(c) Oliver Bedernik · Terra-Kit 4.0 · Arbeitsgrundlage für den Advocatus diaboli", "",
            "| Nr | Kategorie | Ort | Angabe | Kontext | geprüft |", "|---|---|---|---|---|---|"]
    esc = lambda t: t.replace("|", "\\|")
    return "\n".join(kopf + [f"| {i} | {z['kategorie']} | {z['ort']} | {esc(z['wert'])} | {esc(z['kontext'])} | ☐ |"
                             for i, z in enumerate(zeilen, 1)]) + "\n"


def main():
    argv = sys.argv[1:]
    aus_wert = argv[argv.index("--aus") + 1] if "--aus" in argv else None
    args = [a for a in argv if not a.startswith("--") and a != aus_wert]
    if len(args) != 1:
        sys.exit("Aufruf: python3 pruefliste.py werk.json [--aus pruefliste.md]")
    werk = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    zeilen = eintraege(werk)
    aus = Path(aus_wert) if aus_wert else Path(args[0]).with_name("pruefliste.md")
    aus.write_text(als_markdown(werk, zeilen), encoding="utf-8")
    zahl = {}
    for z in zeilen:
        zahl[z["kategorie"]] = zahl.get(z["kategorie"], 0) + 1
    print(f"Prüfliste: {len(zeilen)} Angaben ({', '.join(f'{k} {v}' for k, v in zahl.items())}) → {aus}")


if __name__ == "__main__":
    main()
