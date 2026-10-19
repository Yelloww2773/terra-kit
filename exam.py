#!/usr/bin/env python3
"""(c) Oliver Bedernik · Terra-Kit · exam.py (Standard 3.1)

Erzeugt aus einer exam.json und dem zugehörigen werk.json
  1. die interaktive Prüfung (eine selbstständige HTML-Datei zur Veröffentlichung) und
  2. mit --pdf den A4-Prüfungsbogen mit Lösungsteil (Seitenmontage wie das Skript).

Aufruf:  python3 exam.py exam.json werk.json [--aus ORDNER] [--pdf] [--lokal]
"""
import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

KIT = Path(__file__).resolve().parent
sys.path.insert(0, str(KIT))
import skript as S  # noqa: E402
import karte as K  # noqa: E402
from validate import validiere_exam  # noqa: E402

VERSION = "3.1.1"
esc = S.esc
TYP = {"einfach": "Einfachauswahl", "mehrfach": "Mehrfachauswahl"}


def daten(exam, werk):
    m = exam["meta"]
    prov = {p["code"]: {"nr": p["nr"], "name": esc(p["name_lat"]), "farbe": p["farbe"]} for p in werk["provinzen"]}
    kacheln = {k["code"]: esc(k["titel"]) for p in werk["provinzen"] for k in p["kacheln"]}
    fragen = []
    for f in exam["fragen"]:
        fragen.append({"id": f["id"], "typ": f["typ"], "provinz": f["provinz"], "kacheln": f["kacheln"],
                       "sv": S.md(f["sachverhalt"]) if f.get("sachverhalt") else None, "frage": S.md(f["frage"]),
                       "optionen": [{"id": o["id"], "text": S.md(o["text"]), "richtig": o["richtig"], "beg": S.md(o["begruendung"]),
                                     "norm": S.typo(esc(o.get("norm", "")))} for o in f["optionen"]],
                       "merke": ({"text": S.md(f["merke"]["text"]), "lat": esc(f["merke"].get("lat", "")), "de": S.md(f["merke"].get("de", ""))}
                                 if f.get("merke") else None)})
    return {"titel": m["titel"], "schluessel": f'{m["titel"]}:{m["version"]}', "minuten": m["minuten"],
            "karte_url": m.get("karte_url", ""), "provinzen": prov, "kacheln": kacheln, "fragen": fragen}


def html_interaktiv(exam, werk, lokal=False):
    S._HYPH = None
    S.farben_zuweisen(werk)
    m, wm = exam["meta"], werk["meta"]
    n = len(exam["fragen"])
    fall = sum(1 for f in exam["fragen"] if f.get("sachverhalt"))
    mehr = sum(1 for f in exam["fragen"] if f["typ"] == "mehrfach")
    pv = m["proverbium"]
    d = json.dumps(daten(exam, werk), ensure_ascii=False).replace("</", "<\\/")
    css = (K.css_basis() + "\n" + S.palette_css() + "\n" + (KIT / "vorlage" / "farben.css").read_text(encoding="utf-8") + "\n"
           + (KIT / "vorlage" / "exam.css").read_text(encoding="utf-8") + "\n" + K.palette_dunkel_css())
    js = (KIT / "vorlage" / "exam.js").read_text(encoding="utf-8")
    thema = f'<button class="knopf k-thema" aria-label="Darstellung">{K.ICON["thema"]}</button>'
    return f"""<!DOCTYPE html>
<html lang="de-AT">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="author" content="(c) Oliver Bedernik">
<title>{esc(m["titel"])} · Prüfung zu {esc(wm["titel"])}</title>
{K.schriften(lokal)}
<style>
{css}
</style>
</head>
<body>
{K.wasserzeichen()}
<header class="ekopf" id="ekopf" hidden>
  <div class="reihe"><span class="titel">{esc(m["titel"])}</span><span class="uhr" id="uhr" aria-live="off" title="Restzeit"></span>
    <button class="knopf" id="b-uebersicht">{K.ICON["ganz"]}<span class="lbl">Übersicht</span></button>
    <button class="knopf haupt" id="b-abgeben">Abgeben</button>{thema}</div>
  <div class="balken" id="balken" role="progressbar" aria-valuemin="0" aria-valuemax="{n}" aria-label="Beantwortete Fragen"><i></i></div>
</header>
<main>
<section class="schirm" id="s-start" hidden>
  <div class="startblatt">
    <div class="reihe">Prüfung zu {esc(wm["titel"])}</div>
    <h1>{esc(m["titel"])}</h1>
    <div class="zu">{S.md(wm["untertitel"], latein=True)}</div>
    <div class="box latinum"><span class="lat">{S.md(pv["lat"], latein=True)}</span><span class="de">{S.md(pv["de"])}</span><span class="stelle">{S.md(pv["stelle"], latein=True)}</span></div>
    <table class="eck"><tr><td>Fragen</td><td>{n}</td></tr><tr><td>davon mit Sachverhalt</td><td>{fall}</td></tr>
      <tr><td>davon Mehrfachauswahl</td><td>{mehr}</td></tr><tr><td>Bearbeitungszeit</td><td>{m["minuten"]} Minuten</td></tr></table>
    <ul class="regeln">
      <li>Jede Frage hat vier Antworten. Bei <b>Einfachauswahl</b> ist genau eine richtig, bei <b>Mehrfachauswahl</b> eine oder mehrere.</li>
      <li>Einen Punkt gibt es nur für die vollständig richtige Auswahl; keine Teilpunkte, keine Minuspunkte.</li>
      <li>Fragen lassen sich markieren und in beliebiger Reihenfolge bearbeiten. Der Fortschritt wird in diesem Browser gespeichert.</li>
      <li>Läuft die Zeit ab, wird automatisch abgegeben.</li></ul>
    <label class="wahl"><input type="checkbox" id="o-zeit" checked><div><b>Zeitlimit {m["minuten"]} Minuten</b><span>Ausschalten zum Üben ohne Zeitdruck.</span></div></label>
    <label class="wahl"><input type="checkbox" id="o-durum"><div><b>Modus Durum</b><span>Der Fragetyp bleibt verborgen; alle Fragen erscheinen als Mehrfachauswahl.</span></div></label>
    <div class="startknoepfe"><button class="knopf haupt" id="b-beginnen">Prüfung beginnen</button>
      <button class="knopf" id="b-fortsetzen" hidden>Fortsetzen</button><button class="knopf" id="b-ergebnis" hidden>Letztes Ergebnis ansehen</button>{thema}</div>
    <p class="gespeichert" id="gespeichert" hidden></p>
    <p class="gespeichert">Version {esc(m["version"])} · {esc(S.stand_text(werk))} · (c) Oliver Bedernik</p>
  </div>
</section>
<section class="schirm" id="s-frage" hidden>
  <article class="fkarte" id="fkarte"></article>
  <div class="fnav"><button class="knopf" id="b-zurueck">Zurück</button><button class="knopf" id="b-markieren" aria-pressed="false">Markieren</button>
    <div class="rechts"><button class="knopf haupt weiter" id="b-weiter"><span class="lbl">Weiter</span></button></div></div>
</section>
<section class="schirm" id="s-ergebnis" hidden>
  <div class="urteil" id="urteil"></div>
  <h2 style="font:600 22px var(--f-titel);margin:26px 0 8px">Ergebnis nach Provinzen</h2>
  <div class="provinzwertung" id="provinzwertung"></div>
  <div class="filter"><button class="knopf" id="f-alle" aria-pressed="true">Alle Fragen</button><button class="knopf" id="f-falsch" aria-pressed="false">Nur falsche</button>
    <button class="knopf" id="b-nochmal" style="margin-left:auto">Neuer Versuch</button>{thema}</div>
  <div class="durchsicht" id="durchsicht"></div>
</section>
</main>
<dialog id="d-uebersicht"><header><h2>Übersicht</h2><button class="knopf schliessen" aria-label="Schließen">✕</button></header>
  <div class="inhalt"><div class="raster" id="raster"></div>
  <div class="legende"><span class="l-b">beantwortet</span><span class="l-m">markiert</span><span class="l-a">aktuelle Frage</span></div></div></dialog>
<dialog id="d-abgabe"><header><h2>Prüfung abgeben?</h2><button class="knopf schliessen" aria-label="Schließen">✕</button></header>
  <div class="inhalt"><div id="abgabe-text"></div><div class="dknoepfe"><button class="knopf schliessen">Weiter bearbeiten</button>
  <button class="knopf haupt" id="b-abgabe-ok">Jetzt abgeben</button></div></div></dialog>
<div class="signet" aria-hidden="true">(c) Oliver Bedernik</div>
<script id="exam-daten" type="application/json">{d}</script>
<script>
{js}
</script>
</body>
</html>"""


# ── A4-Prüfungsbogen ─────────────────────────────────────────────────────
def einheiten_pdf(exam, werk):
    m, wm = exam["meta"], werk["meta"]
    prov = {p["code"]: p for p in werk["provinzen"]}
    titel_k = {k["code"]: k["titel"] for p in werk["provinzen"] for k in p["kacheln"]}
    n = len(exam["fragen"])
    fall = sum(1 for f in exam["fragen"] if f.get("sachverhalt"))
    mehr = sum(1 for f in exam["fragen"] if f["typ"] == "mehrfach")
    pv = m["proverbium"]
    out = [S.einheit(
        f'<div class="tp-band"><div class="tp-reihe">Prüfungsbogen zu {esc(wm["titel"])}</div><div class="tp-autor">Oliver Bedernik</div></div>'
        f'<div class="tp-mitte" style="top:84mm"><h1 class="tp-titel" style="font-size:44pt">{esc(m["titel"])}</h1>'
        f'<div class="tp-unter">{S.md(wm["untertitel"], latein=True)}</div><div class="tp-linie"></div>'
        f'<div class="box latinum" style="margin:0 0 4mm"><span class="lat">{S.md(pv["lat"], latein=True)}</span><span class="de">{S.md(pv["de"])}</span>'
        f'<span class="stelle">{S.md(pv["stelle"], latein=True)}</span></div>'
        f'<table class="eck-tab"><tr><td>Fragen</td><td>{n}</td></tr><tr><td>davon mit Sachverhalt</td><td>{fall}</td></tr>'
        f'<tr><td>davon Mehrfachauswahl</td><td>{mehr}</td></tr><tr><td>Bearbeitungszeit</td><td>{m["minuten"]} Minuten</td></tr></table>'
        '<ul class="regeln-d"><li>Einfachauswahl (Kreis): genau eine Antwort richtig. Mehrfachauswahl (Quadrat): eine oder mehrere richtig.</li>'
        '<li>Ein Punkt nur für die vollständig richtige Auswahl; keine Teilpunkte, keine Minuspunkte.</li>'
        '<li>Die Lösungen mit Begründung stehen am Ende des Bogens; erst nach der Bearbeitung aufschlagen.</li></ul>'
        '<div class="namensfeld"><div><span>Name</span><i></i></div><div><span>Datum</span><i></i></div><div><span>Erreichte Punkte</span><i></i></div></div></div>'
        f'<div class="tp-fuss"><span>Version {esc(m["version"])} · {esc(S.stand_text(werk))}</span></div>',
        seite="deck", name="Deckblatt")]
    for i, f in enumerate(exam["fragen"], 1):
        p = prov[f["provinz"]]
        rund = f["typ"] == "einfach"
        opts = "".join(f'<div class="ef-opt"><span class="kast{" rund" if rund else ""}"></span><span class="bu">{o["id"]}</span>{S.md(o["text"])}</div>'
                       for o in f["optionen"])
        sv = f'<div class="fallbeispiel"><div class="fb-kopf">Sachverhalt</div><div class="fb-teil">{S.md(f["sachverhalt"])}</div></div>' if f.get("sachverhalt") else ""
        inhalt = (f'<div class="ef farbe-{p["farbe"]}"><div class="ef-kopf"><span class="ef-nr">Frage {i}</span><span class="ef-typ">{TYP[f["typ"]]}</span>'
                  f'<span class="ef-prov">Provinz {p["nr"]} ({p["code"]})</span></div>{sv}<p class="ef-frage">{S.md(f["frage"])}</p>{opts}</div>')
        out.append(S.einheit(inhalt, name=f'Frage {i}', **({"neue_seite": "1"} if i == 1 else {})))
    out.append(S.einheit('<div class="titelzeile"><div class="tz-ober">Lösungsteil</div><h1 class="teil" id="t-loesung">Lösungen und Begründungen</h1>'
                         '<div class="teil-unter">Je Antwort: richtig oder falsch, Begründung und Fundstelle; dazu der Verweis auf die Kachel der Wissenslandkarte.</div></div>',
                         neue_seite="1", name="Lösungsteil"))
    for i, f in enumerate(exam["fragen"], 1):
        p = prov[f["provinz"]]
        richtig = ", ".join(o["id"] for o in f["optionen"] if o["richtig"])
        zeilen = "".join(f'<tr><td class="bu">{o["id"]}</td><td class="w {"ja" if o["richtig"] else "nein"}">{"richtig" if o["richtig"] else "falsch"}</td>'
                         f'<td>{S.md(o["begruendung"])}{f"<span class=norm>{S.typo(esc(o[chr(110)+chr(111)+chr(114)+chr(109)]))}</span>" if o.get("norm") else ""}</td></tr>'
                         for o in f["optionen"])
        merke = f'<div class="box merke"><div class="lbl">Merke</div>{S.md(f["merke"]["text"])}</div>' if f.get("merke") else ""
        verweis = " · ".join(f'Karte: {c} {esc(titel_k.get(c, ""))}' for c in f["kacheln"])
        out.append(S.einheit(f'<div class="el farbe-{p["farbe"]}"><div class="el-kopf">Frage {i}<b>richtig: {richtig}</b></div><table>{zeilen}</table>'
                             f'{merke}<div class="verweis">{verweis}</div></div>', name=f'Lösung {i}'))
    return out


def pdf(exam, werk, aus, name):
    S.farben_zuweisen(werk)
    m = exam["meta"]
    meta = {"kopf_links": f'<b>{esc(m["titel"])}</b> · Prüfungsbogen zu {esc(werk["meta"]["titel"])}',
            "fuss_links": esc(S.stand_text(werk)), "provinzen": []}
    druck = (KIT / "vorlage" / "exam_druck.css").as_uri()
    html_doc = f"""<!DOCTYPE html>
<html lang="de-AT"><head><meta charset="utf-8"><title>{esc(m["titel"])} · Prüfungsbogen</title>
<meta name="author" content="(c) Oliver Bedernik">{S.schrift_links()}
<link rel="stylesheet" href="{(KIT / 'vorlage' / 'skript.css').as_uri()}"><link rel="stylesheet" href="{druck}">
<style>{S.palette_css()}</style>
<script id="meta" type="application/json">{json.dumps(meta, ensure_ascii=False)}</script></head>
<body class="schema-nacht"><main id="buch"></main><div id="quelle">{"".join(einheiten_pdf(exam, werk))}</div>
<script src="{(KIT / 'vorlage' / 'montage.js').as_uri()}"></script></body></html>"""
    hp, pp = aus / f"{name}.html", aus / f"{name}.pdf"
    hp.write_text(html_doc, encoding="utf-8")
    bericht = S.montiere(hp, pp, werk)
    from pypdf import PdfReader, PdfWriter
    w = PdfWriter(clone_from=PdfReader(str(pp)))
    w.add_metadata({"/Title": f'{m["titel"]} · Prüfungsbogen zu {werk["meta"]["titel"]}', "/Author": "(c) Oliver Bedernik",
                    "/Subject": f'Prüfung, Version {m["version"]}', "/Creator": f"Terra-Kit {VERSION}"})
    with open(pp, "wb") as fh:
        w.write(fh)
    n = S.pruefe_pdf(pp, bericht, {"exam": exam, "werk": werk})
    S.kontaktabzug(pp, aus / f"{name}_kontakt.png")
    return pp, n, bericht


def main():
    ap = argparse.ArgumentParser(description="Terra-Exam")
    ap.add_argument("exam"); ap.add_argument("werk")
    ap.add_argument("--aus", default="."); ap.add_argument("--pdf", action="store_true"); ap.add_argument("--lokal", action="store_true")
    a = ap.parse_args()
    exam = json.loads(Path(a.exam).read_text(encoding="utf-8"))
    werk = json.loads(Path(a.werk).read_text(encoding="utf-8"))
    v = validiere_exam(exam, werk)
    print(f"Validierung: {len(v.fehler)} Fehler, {len(v.warnungen)} Warnungen")
    if v.fehler:
        print("\n".join(v.fehler)); sys.exit("Abbruch: exam.json fehlerhaft")
    aus = Path(a.aus).resolve(); aus.mkdir(parents=True, exist_ok=True)
    name = "Examen_" + "_".join(exam["meta"]["titel"].split()[1:]) + f'_v{exam["meta"]["version"]}_{exam["meta"]["stand"]}'
    datei = aus / (name + ("_lokal.html" if a.lokal else ".html"))
    inhalt = html_interaktiv(exam, json.loads(json.dumps(werk)), a.lokal)
    datei.write_text(inhalt, encoding="utf-8")
    striche = len(re.findall("[\u2012\u2013\u2014\u2015]", K.klartext(inhalt)))
    print(f"Prüfung: {datei.name} · {len(inhalt) // 1024} KB · Gedankenstriche: {striche}")
    if a.pdf:
        pp, n, b = pdf(exam, json.loads(json.dumps(werk)), aus, name + "_Bogen")
        print(f"Bogen: {pp.name} · {n} Seiten")
        for z in b["fehler"]: print("FEHLER  ", z)
        for z in b["warnungen"]: print("WARNUNG ", z)
        print(f"Ergebnis: {len(b['fehler'])} Fehler, {len(b['warnungen'])} Warnungen")
        sys.exit(1 if b["fehler"] or striche else 0)
    sys.exit(1 if striche else 0)


if __name__ == "__main__":
    main()
