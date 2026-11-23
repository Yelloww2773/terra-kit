#!/usr/bin/env python3
"""(c) Oliver Bedernik · Terra-Kit 4.0 · Testreihe

1. Beide Referenzwerke und das Referenzexam sind sauber (0 Fehler, 0 Warnungen).
2. Validator: Jeder Test beschädigt eine Kopie des Referenzwerks gezielt und prüft, ob genau dieser Fehler gemeldet wird.
3. Exam: eingeschleuste Fehler werden erkannt.
4. Werkzeuge: Umsetzer 3.x → 4.0 (Werk und Exam), Kachelsicht, Karte, Anki, Prüfliste, Diff, Rechenprobe, Bilder, Version, Workflow.
Der Buchsatz (Paged.js in Chromium) hat eine eigene Reihe: python3 tests/buch_test.py

    python3 tests/run_tests.py
"""
import copy
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
from validate import validiere, validiere_exam  # noqa: E402

BASIS = json.loads((KIT / "referenzwerk.json").read_text(encoding="utf-8"))
HIC = json.loads((KIT / "referenz_historica.json").read_text(encoding="utf-8"))
EXAM = json.loads((KIT / "exam_historica.json").read_text(encoding="utf-8"))
STRICHE = ("‒", "–", "—", "―")


def ab(w, code):
    for k in w["kapitel"] + [w.get("repetitorium") or {"abschnitte": []}]:
        for a in k["abschnitte"]:
            if a["code"] == code:
                return a
    raise KeyError(code)


def bs(w, code, typ, art=None):
    for b in ab(w, code)["bloecke"]:
        if b["typ"] == typ and (art is None or b.get("variante") == art or b.get("art") == art):
            return b
    raise KeyError((code, typ, art))


def _kleinbild(breite):
    import base64
    import io
    from PIL import Image
    puffer = io.BytesIO()
    Image.new("RGB", (breite, breite // 2), (200, 190, 170)).save(puffer, "JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(puffer.getvalue()).decode()


# (Name, Mutation, erwartete Meldung, Stufe F = Fehler, W = Warnung, H = Hinweis)
TESTS = [
    # Struktur und Standard
    ("Standard 3.x abgewiesen", lambda w: w.__setitem__("standard", "3.7"), "umsetzen.py", "F"),
    ("unbekanntes Feld im Abschnitt", lambda w: ab(w, "A1").__setitem__("kacheltitel", "x"), "was unexpected", "F"),
    ("unbekannter Bausteintyp", lambda w: ab(w, "A1")["bloecke"].append({"typ": "notiz", "text": "x"}), "is not one of", "F"),
    ("relevanz abgeschafft", lambda w: ab(w, "A1").__setitem__("relevanz", "kern"), "„relevanz“ gibt es im Standard 4.0 nicht", "F"),
    ("Urheber verändert", lambda w: w["meta"].__setitem__("urheber", "anonym"), "(c) Oliver Bedernik", "F"),
    # Typografie
    ("Geviertstrich", lambda w: bs(w, "A1", "definition").__setitem__("text", "Text — mit Strich."), "Geviertstrich", "F"),
    ("Halbgeviertstrich im Titel", lambda w: ab(w, "B1").__setitem__("titel", "Barwert – Grundlagen"), "Halbgeviertstrich", "F"),
    ("Bindestrich als Gedankenstrich", lambda w: bs(w, "A3", "spitzmarke", "feinheit").__setitem__("text", "Das gilt - meistens."), "Bindestrich als Gedankenstrich", "F"),
    ("gerade Anführungszeichen", lambda w: bs(w, "B2", "spitzmarke", "merke").__setitem__("text", 'Der "Kunde" zahlt.'), "gerades Anführungszeichen", "F"),
    ("Fettung offen", lambda w: bs(w, "A2", "spitzmarke", "klausurhinweis").__setitem__("text", "Nur **zulasten des Täters."), "unpaariges **", "F"),
    ("Textmarker ohne Wirkung", lambda w: bs(w, "B2", "spitzmarke", "merke").__setitem__("text", "Die ==Vorsteuer== ist eine Forderung."), "ohne Wirkung", "W"),
    ("§ ohne Leerzeichen", lambda w: bs(w, "A3", "spitzmarke", "feinheit").__setitem__("text", "Siehe §7 ABGB."), "§ ohne Leerzeichen", "W"),
    ("Art mit Punkt", lambda w: bs(w, "A3", "spitzmarke", "feinheit").__setitem__("text", "Siehe Art. 7 EMRK."), "ohne Punkt", "W"),
    ("Rechtsprechung ohne Geschäftszahl", lambda w: bs(w, "A3", "spitzmarke", "feinheit").__setitem__("text", "So entschied der OGH."), "keine Geschäftszahl", "W"),
    ("Normzitat ohne Gesetzesangabe", lambda w: bs(w, "A3", "spitzmarke", "feinheit").__setitem__("text", "Das folgt aus § 7 und ist anerkannt."), "Normzitat ohne Gesetzesangabe", "F"),
    ("Gerüstwort fett", lambda w: bs(w, "A3", "spitzmarke", "feinheit").__setitem__("text", "**Ziel:** Klarheit."), "Gerüstwort fett", "F"),
    # Kapitel, Codes, Verweise
    ("Abschnitt im falschen Kapitel", lambda w: ab(w, "B3").__setitem__("code", "A9"), "passt nicht zu Kapitel", "F"),
    ("Abschnittscode doppelt", lambda w: ab(w, "A4").__setitem__("code", "A3"), "doppelt vergeben", "F"),
    ("Abschnitte nicht aufsteigend", lambda w: w["kapitel"][0]["abschnitte"].reverse(), "nicht aufsteigend", "F"),
    ("Kapitelcode nicht lückenlos", lambda w: w["kapitel"][1].__setitem__("code", "C"), "lückenlos ab A", "F"),
    ("toter Verweis", lambda w: bs(w, "A3", "spitzmarke", "feinheit").__setitem__("text", "Siehe [[A9]]."), "zeigt auf keinen Abschnitt", "F"),
    ("kaputter Verweis", lambda w: bs(w, "A3", "spitzmarke", "feinheit").__setitem__("text", "Siehe [[a1]]."), "fehlerhaft", "F"),
    ("Register weicht ab", lambda w: w["meta"]["provinzen"][0].__setitem__("name_de", "Anders"), "Register weicht von Kapiteln ab", "F"),
    ("Kontrollfrage auf fehlenden Abschnitt", lambda w: w["kapitel"][0]["kontrollfragen"][0].__setitem__("abschnitt", "A9"), "unbekannten Abschnitt", "F"),
    ("Lexicon auf fehlenden Abschnitt", lambda w: w.setdefault("lexicon", []).append({"begriff": "x", "bedeutung": "y", "abschnitt": "C1"}), "existiert nicht", "F"),
    ("Protokoll hinkt nach", lambda w: w["meta"].__setitem__("version", "9.9"), "letzter Eintrag gilt Version", "W"),
    # Satzregeln des Buchsatzes
    ("Abbildung ohne vorherigen Verweis", lambda w: bs(w, "B3", "absatz").__setitem__("text", "Auf der Zeitachse liegen die Zahlungen."), "nicht vorher im Text angesprochen", "F"),
    ("Verweis auf unbekannte Abbildung", lambda w: bs(w, "B3", "absatz").__setitem__("text", "Siehe {{abb:gibt_es_nicht}} und {{abb:zahlungsstrom}}."), "unbekannte Abbildung", "F"),
    ("Abschnitt beginnt mit Kernsatz", lambda w: ab(w, "A4")["bloecke"].insert(0, {"typ": "kernsatz", "text": "Die **Geschichte** zählt."}), "beginnt mit „kernsatz“", "F"),
    ("Kernsatz ohne Fett", lambda w: bs(w, "B1", "kernsatz").__setitem__("text", "Der Barwert ist der heutige Wert."), "ohne fett gesetzten Fachbegriff", "F"),
    ("mehr als drei Kernsätze", lambda w: ab(w, "B1")["bloecke"].__setitem__(slice(1, 1), [{"typ": "kernsatz", "text": "Ein **Satz**."}] * 2), "mehr als drei Kernsätze", "F"),
    ("zweite Abbildung im Abschnitt", lambda w: ab(w, "A6")["bloecke"].append(copy.deepcopy({**bs(w, "A5", "abbildung"), "id": "zweite"})), "mehr als eine Abbildung", "F"),
    ("Randbeleg auf unbekannte Quelle", lambda w: bs(w, "A3", "spitzmarke", "feinheit").__setitem__("text", "Text.^[@Niemand (5).]"), "unbekannte Quelle @Niemand", "F"),
    ("Rolle fehlt im Farbschlüssel", lambda w: bs(w, "A1", "merkband")["schritte"][0].__setitem__("rolle", "unbekannt"), "fehlt im Farbschlüssel", "F"),
    ("anspruchsvolle Grafik ohne Lesehilfe", lambda w: w["kapitel"][0]["einleitung"][1].pop("lesehilfe"), "ohne Lesehilfe", "W"),
    ("Lesehilfe überflüssig", lambda w: bs(w, "A6", "abbildung").__setitem__("lesehilfe", "Von oben nach unten."), "Lesehilfe bei", "W"),
    ("zwei Einbettungen ohne Text", lambda w: ab(w, "B3")["bloecke"].pop(4), "zwei Einbettungen ohne Text", "W"),
    ("Kerninhalt zu häufig", lambda w: [a.__setitem__("wichtig", True) for a in w["kapitel"][0]["abschnitte"]], "entwertet die Marke", "W"),
    ("Kernsatz ohne Kontrollfrage", lambda w: w["kapitel"][1].__setitem__("kontrollfragen", []), "Kernsätze ohne Kontrollfrage", "H"),
    # Bausteine
    ("Austriacum im Recht", lambda w: w["modul"].__setitem__("domaene", "recht"), "Austriacum in der Rechtsdomäne", "F"),
    ("T-Konto unausgeglichen", lambda w: bs(w, "B2", "abbildung")["konten"][0]["soll"][0].__setitem__("betrag", 999), "≠ Haben", "F"),
    ("Tabellenzeile kurz", lambda w: bs(w, "L3", "tabelle")["zeilen"][0].pop(), "Zellen, Kopf hat", "F"),
    ("Spaltenrollen passen nicht", lambda w: bs(w, "A3", "tabelle").__setitem__("spalten", ["begriff"]), "Einträge in „spalten“", "F"),
    ("Kurve unsortiert", lambda w: bs(w, "B1", "abbildung")["reihen"][0]["punkte"].reverse(), "nicht streng aufsteigend", "F"),
    ("Markierung außerhalb der Achse", lambda w: bs(w, "B1", "abbildung")["markierungen"][0].__setitem__("x", 99), "außerhalb der x-Achse", "F"),
    ("SVG mit fester Farbe", lambda w: bs(w, "A5", "abbildung").__setitem__("svg", bs(w, "A5", "abbildung")["svg"].replace('class="t-akzent"', 'fill="#c00"', 1)), "fester Farbe", "F"),
    ("Baum: Elternknoten fehlt", lambda w: bs(w, "A6", "abbildung")["knoten"][3].__setitem__("eltern", "x"), "Elternknoten „x“ fehlt", "F"),
    ("Baum: zwei Wurzeln", lambda w: bs(w, "A6", "abbildung")["knoten"][1].pop("eltern"), "2 Wurzeln", "F"),
    ("Diagramm: Kante auf unbekannten Knoten", lambda w: bs(w, "A2", "abbildung")["kanten"].append({"von": "gibtsnicht", "nach": bs(w, "A2", "abbildung")["knoten"][0]["id"]}), "gibtsnicht", "F"),
    ("Bild ohne Lizenz", lambda w: bs(w, "L4", "abbildung").pop("lizenz"), "'lizenz' is a required property", "F"),
    ("Bild: CC BY ohne Urheber", lambda w: bs(w, "L4", "abbildung").__setitem__("lizenz", "CC BY 4.0"), "Namensnennung", "F"),
    ("Bild: Lizenz unbekannt", lambda w: bs(w, "L4", "abbildung").__setitem__("lizenz", "aus dem Internet"), "nicht erkannt", "W"),
    ("Bild: zu gering aufgelöst", lambda w: bs(w, "L4", "abbildung").__setitem__("daten", _kleinbild(300)), "Auflösung", "F"),
    ("Abbildung ohne Nachweis", lambda w: bs(w, "B3", "abbildung").__setitem__("nachweis", " "), "ohne Nachweis", "F"),
    ("Formel nicht setzbar", lambda w: bs(w, "B1", "formel").__setitem__("tex", "PV = \\frac{C_n}{"), "Formel nicht setzbar", "F"),
    ("Rechenprobe: falsches Ergebnis", lambda w: bs(w, "B1", "rechenweg")["probe"]["rechnung"][2].__setitem__("ergebnis", "8638.39"), "Rechenprobe Zeile 3", "F"),
    ("Rechenprobe: Python statt Rechnung", lambda w: bs(w, "B1", "rechenweg")["probe"]["rechnung"][0].__setitem__("ausdruck", "__import__('os')"), "nicht erlaubt", "F"),
    ("Rechenprobe: Ergebnistext ohne Wert", lambda w: bs(w, "B1", "rechenweg").__setitem__("ergebnis", "rund 8.600 €"), "nennt den nachgerechneten Wert", "W"),
    # Quellen
    ("Kurzzitat doppelt", lambda w: w["quellen"].append(dict(w["quellen"][0])), "doppelt vergeben", "F"),
    ("Pflichtangabe fehlt", lambda w: next(q for q in w["quellen"] if q.get("gattung") == "literatur" and not q.get("voll")).pop("jahr"), "Pflichtangabe jahr fehlt", "F"),
    ("Quelle nirgends belegt", lambda w: w["quellen"].append({"kurz": "Waise", "gattung": "literatur", "autoren": ["Waise, W."], "titel": "T", "jahr": "2020"}), "„Waise“ wird nirgends belegt", "W"),
    # Abdeckung des Referenzwerks
    ("Abdeckung: Merkband fehlt", lambda w: ab(w, "A1")["bloecke"].remove(bs(w, "A1", "merkband")), "Baustein „merkband“ fehlt", "F"),
    ("Abdeckung: Zeitstrahl fehlt", lambda w: bs(w, "B3", "abbildung").__setitem__("variante", "zeitleiste") or bs(w, "B3", "abbildung").update({"ereignisse": [{"datum": "2026", "text": "a"}, {"datum": "2029", "text": "b"}]}) or [bs(w, "B3", "abbildung").pop(k) for k in ("von", "bis")], "Variante „zeitstrahl“ fehlt", "F"),
    ("Abdeckung: keine lange Tabelle", lambda w: bs(w, "L3", "tabelle").__setitem__("zeilen", bs(w, "L3", "tabelle")["zeilen"][:5]), "mehr als 14 Zeilen", "F"),
    ("Abdeckung: kein Randbeleg mit Fundstelle", lambda w: [x.__setitem__("text", re.sub(r"\s*\([^)]*\)(?=[;\]])", "", x["text"])) for _, x in __import__("validate").bloecke(w) if "text" in x], "kein Randbeleg mit Fundstelle", "F"),
    ("Abdeckung: kein Kapitelabschluss", lambda w: w["kapitel"][0].pop("abschluss"), "kein Kapitelabschluss", "F"),
]

EXAMTESTS = [
    ("Einfachauswahl mit zwei richtigen", lambda e: next(f for f in e["fragen"] if f["typ"] == "einfach")["optionen"][1].__setitem__("richtig", True), "genau eine verlangt"),
    ("Abschnitt fehlt im Werk", lambda e: e["fragen"][0]["abschnitte"].append("C9"), "existiert im Werk nicht"),
    ("Fallquote zu niedrig", lambda e: [f.pop("sachverhalt", None) for f in e["fragen"][:12]], "mindestens zwei Drittel"),
    ("Kapitel unterabgedeckt", lambda e: [f.__setitem__("provinz", "D") for f in e["fragen"] if f["provinz"] == "F"], "Kapitel F nur 0-mal"),
    ("Dimension unbekannt", lambda e: e["fragen"][0].__setitem__("dimension", "Bauchgefühl"), "nicht im Domänenmodul"),
    ("Gedankenstrich im Exam", lambda e: e["fragen"][0].__setitem__("frage", "Welche — Aussagen?"), "Gedankenstrich"),
    ("Standard 3.x", lambda e: e.__setitem__("standard", "3.1"), "umsetzen.py --exam"),
    ("altes Feld kacheln", lambda e: e["fragen"][0].__setitem__("kacheln", e["fragen"][0].pop("abschnitte")), "'abschnitte' is a required property"),
    ("Grafik ohne Sachverhalt", lambda e: e["fragen"][2].pop("sachverhalt", None) or e["fragen"][2].__setitem__("grafik", {"variante": "zeitleiste", "titel": "T", "nachweis": "Eigene Darstellung", "ereignisse": [{"datum": "1848", "text": "a"}, {"datum": "1849", "text": "b"}]}), "Grafik ohne Sachverhalt"),
    ("Grafik fehlerhaft", lambda e: e["fragen"][3].__setitem__("grafik", {"variante": "baum", "titel": "T", "nachweis": "Eigene Darstellung", "knoten": [{"id": "a", "text": "A"}, {"id": "b", "text": "B", "eltern": "zz"}]}), "Elternknoten „zz“ fehlt"),
]


def melde(ok, name, rest=""):
    print(("✓ " if ok else "✗ ") + name + ("" if ok else f"  → {rest}"))
    return 0 if ok else 1


def main():
    fehl = 0
    for datei, w in (("referenzwerk.json", BASIS), ("referenz_historica.json", HIC)):
        b = validiere(copy.deepcopy(w), KIT)
        n = len(b.codes)
        fehl += melde(not b.fehler and not b.warnungen, f"{datei}: 0 Fehler, 0 Warnungen ({n} Abschnitte)", (b.fehler + b.warnungen)[:4])
    b = validiere_exam(copy.deepcopy(EXAM), HIC, KIT)
    fehl += melde(not b.fehler and not b.warnungen, "exam_historica.json: 0 Fehler, 0 Warnungen", (b.fehler + b.warnungen)[:4])

    for name, mutation, erwartet, stufe in TESTS:
        w = copy.deepcopy(BASIS)
        try:
            mutation(w)
            b = validiere(w, KIT)
        except Exception as e:  # ein Absturz des Validators ist ein Fehlschlag
            fehl += melde(False, name, repr(e))
            continue
        liste = {"F": b.fehler, "W": b.warnungen, "H": b.hinweise}[stufe]
        fehl += melde(any(erwartet in z for z in liste), f"Validator: {name}", (b.fehler + b.warnungen + b.hinweise)[:3])

    for name, mutation, erwartet in EXAMTESTS:
        e = copy.deepcopy(EXAM)
        mutation(e)
        b = validiere_exam(e, HIC, KIT)
        fehl += melde(any(erwartet in z for z in b.fehler), f"Exam: {name}", b.fehler[:3])

    # ── Werkzeuge ──────────────────────────────────────────────────────────
    import umsetzen as U
    import sicht as SI
    import karte as KA
    import pruefliste as PL
    import diff as DF
    import rechenprobe as RP
    import skript as SK
    import validate as VA
    alt = json.loads((KIT / "tests/daten/referenzwerk_3.json").read_text(encoding="utf-8"))
    u = U.Umsetzer(alt)
    neu = u.werk()
    sb = VA.Bericht()
    VA.pruefe_struktur(neu, sb)
    codes_alt = [k["code"] for p in alt["provinzen"] for k in p["kacheln"]]
    codes_neu = [a["code"] for _, a in VA.abschnitte(neu)]
    fehl += melde(not sb.fehler and codes_alt == codes_neu and u.liste, "Umsetzer: Werk 3.x schemagültig im Standard 4.0, Codes unverändert, Nacharbeitsliste",
                  sb.fehler[:3])
    texte = " ".join(t for _, t in SK.texte(neu))
    fehl += melde("^[@ABGB; @Bydlinski; @Kodek]" in texte and any(q.get("sigle") == "Bydlinski" for q in neu["quellen"]),
                  "Umsetzer: Kachelquellen werden Randbelege, Quellen erhalten eine Sigle")
    fehl += melde(texte.count("{{abb:waage_als_sinnbild}}") == 1, "Umsetzer: Einbettung wird genau einmal angekündigt")
    ex3 = json.loads((KIT / "tests/daten/exam_historica_3.json").read_text(encoding="utf-8"))
    ex4, _ = U.exam_umsetzen(ex3)
    fehl += melde(ex4["standard"] == "4.0" and all("abschnitte" in f and "kacheln" not in f for f in ex4["fragen"]), "Umsetzer: Exam 3.x → 4.0")

    s = SI.kachelsicht(BASIS, KIT)
    k = {kk["code"]: kk for p in s["provinzen"] for kk in p["kacheln"]}
    fehl += melde(set(k) == set(codes_neu) and k["A1"].get("merkhilfe") and k["B1"].get("kernfakten") and k["A1"]["relevanz"] == "kern"
                  and not any("^[" in json.dumps(x, ensure_ascii=False) or "{{" in json.dumps(x, ensure_ascii=False) for x in k.values()),
                  "Kachelsicht: jeder Abschnitt ein Feld, Kernsätze, Merkhilfe, Kerninhalt; keine Randbelege oder Verweismarken")
    fehl += melde(any(b["typ"] == "schema" and b["variante"] == "svg" for b in k["A2"]["bausteine"]) and
                  any(b["typ"] == "schema" and b["variante"] == "zeitleiste" for b in k["B3"]["bausteine"]),
                  "Kachelsicht: Diagramm als Grafik, Zeitstrahl als Zeitleiste")
    for name, w in (("Referenzwerk", BASIS), ("Historica", HIC)):
        h = KA.baue(copy.deepcopy(w), lokal=True, ordner=KIT)
        n = h.count('class="kachel karte-kachel')
        striche = len(re.findall("[‒–—―]", KA.klartext(h)))
        soll = len([a for _, a in VA.abschnitte(w)])
        fehl += melde(n >= soll and not striche and "(c) Oliver Bedernik" in h, f"Karte {name}: {n} Felder, Vermerk, keine Gedankenstriche", f"{n} statt {soll}, {striche} Striche")

    import anki
    for name, w in (("Referenzwerk", BASIS), ("Historica", HIC)):
        with tempfile.TemporaryDirectory() as tmp:
            pfad, notizen, zaehler, bilder = anki.baue(SI.kachelsicht(w, KIT), Path(tmp), KIT)
            bf = anki.pruefe(pfad, notizen)
        tags = {t for n in notizen for t in n["tags"]}
        fehl += melde(not bf["fehler"] and bf["notizen"] > 50 and zaehler["Kernfakt"] >= 3 and any(t.startswith("Abschnitt::") for t in tags),
                      f"Anki {name}: {bf['notizen']} Karten, Kernsätze als Lücken, Schlagwort Abschnitt", bf["fehler"])
    js = (KIT / "vorlage/exam.js").read_text(encoding="utf-8")
    fehl += melde("tag:Abschnitt::" in js, "Brücke Exam zu Anki: Schlagwort wie im Deck")

    pl = PL.eintraege(HIC)
    kat = {x["kategorie"] for x in pl}
    fehl += melde({"Norm", "Datum", "Beleg", "Rechtsprechung"} <= kat and any(x["ort"].endswith("Einleitung") for x in pl),
                  "Prüfliste: Normen, Daten, Belege, auch aus Kapiteleinleitungen")
    n = copy.deepcopy(BASIS)
    ab(n, "A1")["titel"] += " X"
    ab(n, "A2")["bloecke"][0]["text"] = "y"
    weg = n["kapitel"][1]["abschnitte"].pop()["code"]
    d = DF.vergleiche(BASIS, n)
    fehl += melde(d["entfernt"] == [weg] and d["umbenannt"][0][0] == "A1" and d["geaendert"][0][0] == "A2" and DF.als_text(DF.vergleiche(BASIS, BASIS)) == "",
                  "Diff: neu, entfernt, umbenannt, geändert")
    auto = RP.kritik(BASIS)
    fehl += melde(len(auto) == 1 and auto[0]["abschnitt"] == "B1" and "8.638,37" in auto[0]["befund"], "Rechenprobe: automatische Quellenkritik je Abschnitt")
    abgewiesen = 0
    for a in ("__import__('os')", "open('x')", "(1).real", "[1][0]", "lambda: 1"):
        try:
            RP.werte_aus(a, {})
        except RP.ProbeFehler:
            abgewiesen += 1
    fehl += melde(abgewiesen == 5 and RP.werte_aus("0.1 + 0.2", {}) == RP.dez("0.3"), "Rechenprobe: nur Arithmetik, exakt dezimal")
    ver = (KIT / "VERSION").read_text(encoding="utf-8").strip()
    import exam as EX
    fehl += melde({VA.VERSION, EX.VERSION, KA.VERSION, anki.VERSION} == {ver} and ver.startswith("4."), f"Version einheitlich {ver}")
    y = (KIT / ".github/workflows/pruefung.yml").read_text(encoding="utf-8")
    fehl += melde("needs: testreihe" in y and "buch_test.py" in y and "run_tests.py" in y and "v$(cat VERSION)" in y, "Workflow: Release nur nach beiden grünen Testreihen")
    r = subprocess.run([sys.executable, str(KIT / "validate.py"), str(KIT / "referenzwerk.json"), "--streng"], capture_output=True, text=True)
    fehl += melde(r.returncode == 0, "validate.py --streng: Referenzwerk", r.stdout[-300:])

    print(f"Ergebnis: {fehl} Fehlschläge" if fehl else "Ergebnis: alle Tests bestanden")
    sys.exit(1 if fehl else 0)


if __name__ == "__main__":
    main()
