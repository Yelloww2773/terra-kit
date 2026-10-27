#!/usr/bin/env python3
"""(c) Oliver Bedernik · Terra-Kit · Testreihe für validate.py

Jeder Test beschädigt eine Kopie des Referenzwerks gezielt und prüft, ob der
Validator genau diesen Fehler meldet. Zusätzlich muss das unveränderte
Referenzwerk fehlerfrei sein. Vor jeder Freigabe einer Kit-Version ausführen:

    python3 tests/run_tests.py
"""
import copy
import json
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
from validate import validiere  # noqa: E402

STRICHE_TEST = ("\u2012", "\u2013", "\u2014", "\u2015")
BASIS = json.loads((KIT / "referenzwerk.json").read_text(encoding="utf-8"))


def kachel(w, code):
    for p in w["provinzen"]:
        for k in p["kacheln"]:
            if k["code"] == code:
                return k
    raise KeyError(code)


def baustein(w, code, typ, variante=None):
    for b in kachel(w, code)["bausteine"]:
        if b["typ"] == typ and (variante is None or b.get("variante") == variante):
            return b
    raise KeyError((code, typ, variante))


# (Name, Mutation, erwartete Meldung, Stufe F = Fehler / W = Warnung)
TESTS = [
    ("Geviertstrich", lambda w: baustein(w, "A1", "definition").__setitem__("text", "Text \u2014 mit Strich."), "Geviertstrich", "F"),
    ("Halbgeviertstrich", lambda w: kachel(w, "B1").__setitem__("titel", "Barwert \u2013 Grundlagen"), "Halbgeviertstrich", "F"),
    ("Bindestrich als Gedankenstrich", lambda w: baustein(w, "A3", "feinheit").__setitem__("text", "Das gilt - meistens."), "Bindestrich als Gedankenstrich", "W"),
    ("gerade Anführungszeichen", lambda w: baustein(w, "B2", "merke").__setitem__("text", 'Der "Kunde" zahlt.'), "gerades Anführungszeichen", "W"),
    ("Fettung offen", lambda w: baustein(w, "A2", "klausurfalle").__setitem__("text", "Nur **zulasten des Täters."), "unpaariges **", "F"),
    ("Marker offen", lambda w: baustein(w, "B2", "merke").__setitem__("text", "Die ==Vorsteuer ist eine Forderung."), "unpaariges ==", "F"),
    ("§ ohne Leerzeichen", lambda w: baustein(w, "A3", "feinheit").__setitem__("text", "Siehe §7 ABGB."), "§ ohne Leerzeichen", "W"),
    ("Art mit Punkt", lambda w: baustein(w, "A3", "feinheit").__setitem__("text", "Siehe Art. 7 EMRK."), "ohne Punkt", "W"),
    ("Rsp ohne GZ", lambda w: baustein(w, "A3", "feinheit").__setitem__("text", "So entschied der OGH."), "keine Geschäftszahl", "W"),
    ("toter Verweis", lambda w: baustein(w, "A3", "feinheit").__setitem__("text", "Siehe [[A9]]."), "zeigt auf keine Kachel", "F"),
    ("kaputter Verweis", lambda w: baustein(w, "A3", "feinheit").__setitem__("text", "Siehe [[a1]]."), "fehlerhaft", "F"),
    ("Kachelcode falsche Provinz", lambda w: kachel(w, "B3").__setitem__("code", "A6"), "passt nicht zu Provinz", "F"),
    ("Kachelcode doppelt", lambda w: kachel(w, "A4").__setitem__("code", "A3"), "doppelt vergeben", "F"),
    ("L nicht zuletzt", lambda w: w["provinzen"].reverse(), "Code L", "F"),
    ("Reihenfolge", lambda w: kachel(w, "A1")["bausteine"].reverse(), "Bausteinreihenfolge", "F"),
    ("zu viele Rahmen", lambda w: kachel(w, "B1")["bausteine"].append({"typ": "luecke", "text": "x", "grund": "y"}), "gerahmte Bausteine", "F"),
    ("Textmarker ohne Wirkung", lambda w: baustein(w, "A1", "kern")["punkte"].append("==a=="), "ohne Wirkung", "W"),
    ("Austriacum in Recht", lambda w: w["modul"].__setitem__("domaene", "recht"), "Austriacum in der Rechtsdomäne", "F"),
    ("auslassbar ohne Beleg", lambda w: kachel(w, "A5").pop("beleg_auslassbar"), "beleg_auslassbar", "F"),
    ("unbekanntes Feld", lambda w: baustein(w, "A1", "definition").__setitem__("txt", "Tippfehler"), "'txt' was unexpected", "F"),
    ("unbekannter Bausteintyp", lambda w: kachel(w, "A1")["bausteine"].append({"typ": "notiz", "text": "x"}), "is not one of", "F"),
    ("T-Konto unausgeglichen", lambda w: baustein(w, "B2", "schema", "tkonto")["konten"][0]["soll"][0].__setitem__("betrag", 999), "≠ Haben", "F"),
    ("Tabellenzeile kurz", lambda w: baustein(w, "L3", "schema", "tabelle")["zeilen"][0].pop(), "Zellen, Kopf hat", "F"),
    ("Kurve unsortiert", lambda w: baustein(w, "B1", "schema", "kurve")["reihen"][0]["punkte"].reverse(), "nicht streng aufsteigend", "F"),
    ("Fluss Aufwärtskante", lambda w: baustein(w, "A2", "schema", "fluss")["kanten"].append({"von": "e4", "nach": "f1"}), "nicht abwärts", "F"),
    ("Fluss unerreichbar", lambda w: baustein(w, "A2", "schema", "fluss")["kanten"].pop(), "nicht erreichbar", "F"),
    ("Fluss Frage ohne Label", lambda w: baustein(w, "A2", "schema", "fluss")["kanten"][1].pop("label"), "ohne Beschriftung", "F"),
    ("SVG feste Farbe", lambda w: baustein(w, "A5", "schema", "svg").__setitem__("svg", baustein(w, "A5", "schema", "svg")["svg"].replace('class="t-akzent"', 'fill="#c00"')), "fester Farbe", "F"),
    ("SVG ohne Beschreibung", lambda w: baustein(w, "A5", "schema", "svg").pop("beschreibung"), "beschreibung", "F"),
    ("Formel kaputt", lambda w: baustein(w, "B1", "formel").__setitem__("tex", "PV = \\frac{C_n}{"), "Formel nicht setzbar", "F"),
    ("Selbsttest auf fehlende Kachel", lambda w: w["selbsttest"][0].__setitem__("kachel", "C1"), "existiert nicht", "F"),
    ("Abdeckung SVG fehlt", lambda w: kachel(w, "A5")["bausteine"].pop(1), "Schemavariante „svg“ fehlt", "F"),
    ("VfGH als Institution ohne Warnung", lambda w: baustein(w, "A3", "feinheit").__setitem__("text", "Der VfGH ist das Hüter der Verfassung."), "__keine__", "N"),
    ("Protokoll hinkt nach", lambda w: w["meta"].__setitem__("version", "9.9"), "letzter Eintrag gilt Version", "W"),
    ("Urheber verändert", lambda w: w["meta"].__setitem__("urheber", "anonym"), "(c) Oliver Bedernik", "F"),
]


def main():
    fehlschlaege = 0
    basis = validiere(copy.deepcopy(BASIS))
    if basis.fehler or basis.warnungen:
        print("✗ Referenzwerk ist nicht sauber:")
        for z in basis.fehler + basis.warnungen:
            print("   ", z)
        fehlschlaege += 1
    else:
        print("✓ Referenzwerk: 0 Fehler, 0 Warnungen")
    # Zweites Referenzwerk: acht Provinzen, mehrseitiges Verzeichnis, Bestandsüberführung
    hic = validiere(json.loads((KIT / "referenz_historica.json").read_text(encoding="utf-8")))
    if hic.fehler or hic.warnungen:
        print("✗ Referenz Historica ist nicht sauber:")
        for z in hic.fehler + hic.warnungen:
            print("   ", z)
        fehlschlaege += 1
    else:
        print("✓ Referenz Historica (8 Provinzen, 39 Kacheln): 0 Fehler, 0 Warnungen")

    for name, mutation, erwartet, stufe in TESTS:
        w = copy.deepcopy(BASIS)
        mutation(w)
        b = validiere(w)
        if stufe == "N":
            ok = not any("Geschäftszahl" in z for z in b.warnungen)
            print(("✓ " if ok else "✗ ") + name)
            fehlschlaege += 0 if ok else 1
            continue
        zeilen = b.fehler if stufe == "F" else b.warnungen
        if any(erwartet in z for z in zeilen):
            print(f"✓ {name}")
        else:
            fehlschlaege += 1
            print(f"✗ {name}: erwartet „{erwartet}“ als {'Fehler' if stufe == 'F' else 'Warnung'}")
            for z in (b.fehler + b.warnungen)[:4]:
                print("     gemeldet:", z)
    # Exam: Referenzexam sauber, eingeschleuste Fehler erkannt
    from validate import validiere_exam
    hic_w = json.loads((KIT / "referenz_historica.json").read_text(encoding="utf-8"))
    ex = json.loads((KIT / "exam_historica.json").read_text(encoding="utf-8"))
    b = validiere_exam(copy.deepcopy(ex), hic_w)
    ok = not b.fehler and not b.warnungen
    print(("✓ " if ok else "✗ ") + "Referenzexam: 0 Fehler, 0 Warnungen"); fehlschlaege += 0 if ok else 1
    EXAMTESTS = [
        ("Einfachauswahl mit zwei richtigen", lambda e: e["fragen"][1]["optionen"][1].__setitem__("richtig", True), "genau eine verlangt"),
        ("Kachel fehlt im Werk", lambda e: e["fragen"][0]["kacheln"].append("C9"), "existiert im Werk nicht"),
        ("Fallquote zu niedrig", lambda e: [f.pop("sachverhalt", None) for f in e["fragen"][:12]], "mindestens zwei Drittel"),
        ("Provinz unterabgedeckt", lambda e: [f.__setitem__("provinz", "D") for f in e["fragen"] if f["provinz"] == "F"], "Provinz F nur 0-mal"),
        ("Dimension unbekannt", lambda e: e["fragen"][0].__setitem__("dimension", "Bauchgefühl"), "nicht im Domänenmodul"),
        ("Gedankenstrich im Exam", lambda e: e["fragen"][0].__setitem__("frage", "Welche \u2014 Aussagen?"), "Gedankenstrich"),
    ]
    for name, mut, erw in EXAMTESTS:
        e = copy.deepcopy(ex); mut(e); bb = validiere_exam(e, hic_w)
        ok = any(erw in z for z in bb.fehler)
        print(("✓ " if ok else "✗ ") + "Exam: " + name); fehlschlaege += 0 if ok else 1
    # Anki: beide Prüfwerke als Deck bauen und wie Anki öffnen
    import tempfile, anki
    for datei in ("referenzwerk.json", "referenz_historica.json"):
        w = json.loads((KIT / datei).read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            pfad, notizen, zaehler, bilder = anki.baue(w, Path(tmp))
            bf = anki.pruefe(pfad, notizen)
        ok = not bf["fehler"] and bf["notizen"] > 50
        print(("✓ " if ok else "✗ ") + f"Anki {datei}: {bf['notizen']} Karten, {len(bilder)} Abbildungen" + ("" if ok else f" {bf['fehler']}"))
        fehlschlaege += 0 if ok else 1
    # Quellen (3.2): Verwendungsnachweis, Pflichtfelder, Zitierformen
    import skript as SK
    from validate import validiere as _val
    ex_w = json.loads((KIT / "referenzwerk.json").read_text(encoding="utf-8"))
    def _mut(fn):
        w = copy.deepcopy(ex_w); fn(w); return _val(w)
    QTESTS = [
        ("Kachel zitiert unbekannte Quelle", lambda: _mut(lambda w: w["provinzen"][0]["kacheln"][0]["quellen"].append("Unbekannt 1999")).fehler, "im Quellenverzeichnis fehlt"),
        ("Kurzzitat doppelt", lambda: _mut(lambda w: w["quellen"].append(dict(w["quellen"][0]))).fehler, "doppelt vergeben"),
        ("Pflichtangabe fehlt", lambda: _mut(lambda w: next(q for q in w["quellen"] if q.get("gattung") == "literatur").pop("jahr")).fehler, "Pflichtangabe jahr fehlt"),
        ("Quelle von keiner Kachel zitiert", lambda: _mut(lambda w: w["quellen"].append({"kurz": "Waise 2020", "gattung": "literatur", "autoren": ["Waise, W."], "titel": "T", "jahr": "2020"})).warnungen, "von keiner Kachel zitiert"),
        ("APA: zwei Autoren mit Komma und &", lambda: [SK.zitat_text({"gattung": "literatur", "autoren": ["Fouquin, Michel", "Hugot, Jules"], "titel": "T", "jahr": "2016", "verlag": "V", "kurz": "x"}, "APA")], "Fouquin, M., & Hugot, J. (2016). T. V."),
        ("APA: Zeitschriftenaufsatz", lambda: [SK.zitat_text({"gattung": "aufsatz", "autoren": ["Markowitz, Harry"], "titel": "Portfolio selection", "in": "The Journal of Finance", "band": "7", "heft": "1", "seiten": "77 bis 91", "jahr": "1952", "kurz": "x"}, "APA")], "Markowitz, H. (1952). Portfolio selection. The Journal of Finance, 7(1), 77 bis 91."),
        ("AZR: Kommentar mit Auflage", lambda: [SK.zitat_voll({"gattung": "kommentar", "autoren": ["Kodek, Georg"], "hrsg": ["Rummel, Peter", "Lukas, Meinhard"], "in": "ABGB", "auflage": 4, "fundstelle": "§§ 6, 7", "jahr": "2015", "kurz": "x"}, "AZR")], "ABGB<sup>4</sup> §§\u00a06, 7 (2015)"),
        ("Entscheidung mit Sammlung und ECLI", lambda: [SK.zitat_text({"gattung": "entscheidung", "gericht": "EuGH", "datum": "2010-12-22", "gz": "C-208/09", "name": "Sayn-Wittgenstein", "ecli": "ECLI:EU:C:2010:806", "kurz": "x"}, "AZR")], "EuGH 22.12.2010, C-208/09, Sayn-Wittgenstein, ECLI:EU:C:2010:806"),
        ("Hochzahlen als echte Hochstellung", lambda: [SK.md("ABGB⁴")], '<sup class="hz">4</sup>'),
    ]
    for name, fn, erw in QTESTS:
        try:
            ergebnis = fn(); ok = any(erw in z for z in ergebnis)
        except Exception as ex:
            ok = False; ergebnis = [repr(ex)]
        print(("✓ " if ok else "✗ ") + "Quellen: " + name + ("" if ok else f"  → {ergebnis[:2]}")); fehlschlaege += 0 if ok else 1
    # Werkzeuge 3.3: Version, Versionswarnung, Ausgewogenheit, Prüfliste, Diff, Workflow
    import re as _re, versionspruefung as VP, pruefliste as PL, diff as DF
    hic_x = json.loads((KIT / "referenz_historica.json").read_text(encoding="utf-8"))
    ver = (KIT / "VERSION").read_text(encoding="utf-8").strip()
    def _version_einheitlich():
        import validate, exam as EX, karte as KA
        return {validate.VERSION, EX.VERSION, KA.VERSION, SK.VERSION, anki.VERSION} == {ver} and _re.fullmatch(r"\d+\.\d+\.\d+", ver)
    def _ausgewogen():
        e = copy.deepcopy(ex)
        for d in ("Kontinuität und Rezeption", "Fundstelle und Status"):
            next(f for f in e["fragen"] if f["dimension"] == d)["dimension"] = "Abgrenzung"
        return any("Ausgewogenheit" in z for z in validiere_exam(e, hic_w).warnungen)
    def _pruefliste():
        z = PL.eintraege(json.loads((KIT / "referenzwerk.json").read_text(encoding="utf-8")))
        h = PL.eintraege(hic_x)
        kat = {x["kategorie"] for x in z}
        return ({"Norm", "Zahl", "Datum", "Auflage"} <= kat and any(x["wert"] == "5 %" for x in z)
                and any(x["wert"] == "1814/15" and x["kategorie"] == "Datum" for x in h)
                and not any(x["kategorie"] == "Rechtsprechung" and x["wert"] == "1814/15" for x in h))
    def _diff():
        n = copy.deepcopy(BASIS); n["provinzen"][0]["kacheln"][0]["titel"] += " X"
        n["provinzen"][0]["kacheln"][1]["bausteine"][0]["text"] = "y"; weg = n["provinzen"][1]["kacheln"].pop()["code"]
        b = DF.vergleiche(BASIS, n); t = DF.als_text(b)
        return (b["entfernt"] == [weg] and b["umbenannt"][0][0] == "A1" and b["geaendert"][0][0] == "A2"
                and DF.als_text(DF.vergleiche(BASIS, BASIS)) == "" and not any(c in t for c in STRICHE_TEST))
    def _workflow():
        y = (KIT / ".github/workflows/pruefung.yml").read_text(encoding="utf-8")
        return "needs: testreihe" in y and "v$(cat VERSION)" in y and "run_tests.py" in y
    NEU = [
        ("Version einheitlich aus Datei VERSION", _version_einheitlich),
        ("Versionswarnung: Vergleich", lambda: [VP.bewerte("3.3.0", t)[0] for t in ("v3.4.0", "v3.3.0", "v3.2.0", "v3.3.a")] == ["veraltet", "aktuell", "neuer", "unklar"]
                                                and VP.bewerte("3.10.0", "v3.9.0")[0] == "neuer"),
        ("Exam: Ausgewogenheit gewarnt", _ausgewogen),
        ("Prüfliste: Kategorien und Jahresspannen", _pruefliste),
        ("Diff: neu, entfernt, umbenannt, geändert", _diff),
        ("Workflow: Release nur nach grüner Testreihe", _workflow),
    ]
    # Bedienung am Bildschirm (3.4)
    import exam as EXM
    def _seitenverweis():
        ohne = SK.md("Siehe [[A1]].")
        SK.SEITENVERWEIS = True
        try:
            mit = SK.md("Siehe [[A1]].")
        finally:
            SK.SEITENVERWEIS = False
        return "data-ziel" not in ohne and 'data-ziel="k-A1"' in mit and "S\u00a0" in mit
    def _register():
        beg, nor = SK.register_eintraege(hic_x)
        reihe = [n for n in sorted(nor, key=SK._normschluessel) if n.endswith("B-VG") and n.count(" ") == 2]
        zahlen = [int(_re.match(r"\d+", n.split()[1]).group()) for n in reihe]
        return beg and all(c for c in beg.values()) and "Art 149 Abs 1 B-VG" in nor and zahlen == sorted(zahlen)
    def _lesezeichen():
        alle = {f"k-{k['code']}": 1 for p in BASIS["provinzen"] for k in p["kacheln"]}
        alle.update({f"p-{p['code']}": 1 for p in BASIS["provinzen"]}); alle.update({"t-quellen": 1, "t-inhalt": 1})
        alle.update({f"k-{c}": 1 for c, _, _ in SK.l_generiert(BASIS)})
        plan, fehlend = SK.lesezeichen_plan(BASIS, alle)
        titel = [x[1] for x in plan]
        _, fehlt = SK.lesezeichen_plan(BASIS, {k: v for k, v in alle.items() if k != "k-A2"})
        return not fehlend and any(x.startswith("A1 ") for x in titel) and fehlt == ["k-A2"]
    def _anki_bruecke():
        wk = copy.deepcopy(hic_w); SK.farben_zuweisen(wk)
        d = EXM.daten(copy.deepcopy(ex), wk)
        js = (KIT / "vorlage/exam.js").read_text(encoding="utf-8")
        return d["anki_tag"] == "Terra::" + hic_w["meta"]["titel"].replace(" ", "_") and "tag:Kachel::" in js
    def _release_knopf():
        y = (KIT / ".github/workflows/pruefung.yml").read_text(encoding="utf-8")
        return "workflow_dispatch" in y and "--notes-file notizen.md" in y and "--clobber" in y
    NEU += [
        ("Seitenverweis nur im Lernskript", _seitenverweis),
        ("Sachregister: Begriffe und Normen, numerisch sortiert", _register),
        ("Lesezeichen: jede Kachel mit Code, fehlendes Ziel gemeldet", _lesezeichen),
        ("Brücke Exam zu Anki: Schlagwort wie im Deck", _anki_bruecke),
        ("Workflow: Release-Knopf, README als Beschreibung", _release_knopf),
    ]
    for name, fn in NEU:
        try:
            ok = bool(fn())
        except Exception as ex_:
            ok = False; print("     Ausnahme:", repr(ex_)[:160])
        print(("✓ " if ok else "✗ ") + name); fehlschlaege += 0 if ok else 1
    gesamt = len(TESTS) + 5 + len(EXAMTESTS) + len(QTESTS) + len(NEU)
    print(f"\n{gesamt - fehlschlaege} von {gesamt} Tests bestanden")
    sys.exit(1 if fehlschlaege else 0)


if __name__ == "__main__":
    main()
