#!/usr/bin/env python3
"""(c) Oliver Bedernik · Terra-Kit 4.0 · sicht.py

Kachelsicht eines Werks im Standard 4.0: verdichtet jeden Abschnitt zu einer Kachel, wie sie Karte, Exam und
Anki zeigen. Der Fließtext (Absätze, Überleitungen, Einleitungen) bleibt dem Lernskript vorbehalten; die Karte
zeigt, was man aus dem Abschnitt mitnehmen muss:

  Abschnitt → Kachel (Code, Titel, Anker, Fundstelle; „wichtig“ → Kernstoff)
  definition (+ folgendes zitat) → Definition mit Normwortlaut; fehlt sie, trägt der erste Absatz die Kachel
  kernsatz → Kernsatz (Anki-Lücken aus dem Fett); merkband → Merkhilfe
  kern, aufzaehlung → Kernliste; formel, rechenweg, latinum → unverändert
  spitzmarke → Merke, Feinheit, Klausurfalle (Cave), Austriacum, Aktualisierung, Lücke
  tabelle, steckbrief, glossar, akteure → Tabelle; abbildung → Schema (Zeitstrahl als Zeitleiste,
  Diagramm als fertige Grafik); fallbeispiel → Beispiel mit Lösung
  Randbelege ^[@Sigle …] → Quellen der Kachel; {{abb:…}} und {{tab:…}} → Wortverweis
  Kontrollfragen → Selbsttest; lexicon und quellenkritik: abschnitt → kachel

Die Sicht ist ein Zwischenformat im Speicher (nicht gegen schema_3.json geprüft); geprüft wird das Werk selbst.
"""
import copy
import datetime as dt
import re

import skript
import diagramm

REIHENFOLGE = ["definition", "kern", "formel", "rechenweg", "schema", "beispiel", "merke", "feinheit", "klausurfalle",
               "austriacum", "aktualisierung", "latinum", "luecke"]
SPITZ = {"klausurhinweis": "klausurfalle", "merke": "merke", "feinheit": "feinheit", "austriacum": "austriacum",
         "aktualisierung": "aktualisierung", "luecke": "luecke"}
RE_REF_KLAMMER = re.compile(r"\s?\((?:siehe |vgl )?\{\{(abb|tab):[a-z0-9_]+\}\}\)")
RE_REF = re.compile(r"\{\{(abb|tab):[a-z0-9_]+\}\}")


def text(t):
    """Text für die Kachel: Randbelege weg, Verweise auf Abbildung oder Tabelle als Wort."""
    t = skript.fussnoten_zerlegen(t)[0]
    t = re.sub(r"\x00F\d+\x00", "", t)
    t = RE_REF_KLAMMER.sub("", t)
    t = RE_REF.sub(lambda m: "die Abbildung" if m.group(1) == "abb" else "die Tabelle", t)
    return re.sub(r"^die ", "Die ", t)


def belege(t, schluessel):
    """Kurzzitate der Quellen, die ein Text als Randbeleg nennt."""
    try:
        _, fns = skript.fussnoten_zerlegen(t)
    except ValueError:
        return []
    return [schluessel.get(s, s) for fn in fns for s in re.findall(r"@([A-Za-z0-9ÄÖÜäöü]+)", fn)]


def _datum(iso):
    j, m, t = iso.split("-")
    return f"{int(t)}.{int(m)}.{j}"


def kachel(a, werk, rollen, wichtig_default=False):
    schluessel = {x: q["kurz"] for q in werk["quellen"] for x in skript.quell_schluessel(q)}
    quellen = list(a.get("quellen", []))
    for b in a["bloecke"]:
        for t in skript.block_texte(b):
            for q in belege(t, schluessel):
                if q not in quellen:
                    quellen.append(q)
    bs, kernfakten, merkhilfe = [], [], None
    bl = a["bloecke"]
    for i, b in enumerate(bl):
        t = b["typ"]
        if t == "definition":
            x = {"typ": "definition", "text": text(b["text"])}
            if i + 1 < len(bl) and bl[i + 1]["typ"] == "zitat":
                x["zitat"] = {"text": text(bl[i + 1]["text"]), "quelle": text(bl[i + 1]["quelle"])}
            bs.append(x)
        elif t == "zitat":
            if i and bl[i - 1]["typ"] == "definition":
                continue
            bs.append({"typ": "merke", "text": f'„{text(b["text"]).strip("„“")}“ ({text(b["quelle"])})'})
        elif t == "kernsatz":
            kernfakten.append(text(b["text"]))
        elif t in ("kern", "aufzaehlung"):
            x = {"typ": "kern", "punkte": [text(skript.punkt_text(p)) for p in b["punkte"]]}
            if b.get("titel"):
                x["titel"] = b["titel"]
            bs.append(x)
        elif t in ("formel", "rechenweg", "latinum"):
            bs.append({k: copy.deepcopy(v) for k, v in b.items() if k != "wichtig"})
        elif t == "spitzmarke":
            x = {"typ": SPITZ[b["art"]], "text": text(b["text"])}
            if b["art"] == "austriacum":
                x["norm"] = b.get("norm", "")
            if b["art"] == "aktualisierung":
                x["datum"], x["quelle"] = b.get("datum", ""), b.get("quelle", "")
            if b["art"] == "luecke":
                x["grund"] = b.get("grund", "sinngemäß ergänzt")
            bs.append(x)
        elif t == "merkband":
            merkhilfe = f'{b["titel"]}: ' + " · ".join(f'{s["kopf"]} {s["text"]}' for s in b["schritte"])
        elif t == "fallbeispiel":
            bs.append({"typ": "beispiel", "sachverhalt": text(b["sachverhalt"]), "loesung": text(b["loesung"])})
        elif t == "tabelle":
            x = {"typ": "schema", "variante": "tabelle", "titel": text(b["titel"]), "kopf": [text(c) for c in b["kopf"]],
                 "zeilen": [[text(c) for c in z] for z in b["zeilen"]]}
            for f in ("spalten", "art"):
                if b.get(f):
                    x[f] = b[f]
            if b.get("aussage"):
                x["aussage"] = text(b["aussage"])
            bs.append(x)
        elif t in ("steckbrief", "glossar"):
            paare = b.get("felder") or b.get("eintraege")
            bs.append({"typ": "schema", "variante": "tabelle", "titel": text(b["titel"]),
                       "kopf": ["Merkmal", "Angabe"] if t == "steckbrief" else ["Begriff", "Bedeutung"],
                       "spalten": ["begriff", "text"], "zeilen": [[text(x), text(y)] for x, y in paare]})
        elif t == "akteure":
            bs.append({"typ": "schema", "variante": "tabelle", "titel": text(b["titel"]), "kopf": ["Person", "Funktion"],
                       "spalten": ["begriff", "text"], "zeilen": [[p["name"], text(p["funktion"])] for p in werk.get("personen", [])]})
        elif t == "abbildung":
            bs.append(schema(b, rollen))
        # absatz: Fließtext bleibt dem Lernskript vorbehalten
    if not any(x["typ"] == "definition" for x in bs):
        erster = next((b for b in bl if b["typ"] == "absatz"), None)
        if erster:
            saetze = re.split(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ„])", text(erster["text"]))
            kurz = saetze[0] + (" " + saetze[1] if len(saetze) > 1 and len(saetze[0]) < 140 else "")
            bs.insert(0, {"typ": "definition", "text": kurz})
    bs.sort(key=lambda x: REIHENFOLGE.index(x["typ"]))
    k = {"code": a["code"], "titel": a["titel"], "anker": a.get("anker", ""), "relevanz": "kern" if a.get("wichtig", wichtig_default) else "vertiefung",
         "bausteine": bs}
    if a.get("fundstelle"):
        k["seite"] = a["fundstelle"]
    if quellen:
        k["quellen"] = quellen
    if kernfakten:
        k["kernfakten"] = kernfakten[:3]
    if merkhilfe:
        k["merkhilfe"] = merkhilfe
    return k


def schema(b, rollen):
    """Abbildung → Schema der Kachel."""
    v = b["variante"]
    if v == "zeitstrahl":
        return {"typ": "schema", "variante": "zeitleiste", "titel": text(b["titel"]),
                "ereignisse": [{"datum": (e.get("etikett") or _datum(e["datum"])) + (f' bis {_datum(e["bis"])}' if e.get("bis") and not e.get("etikett") else ""),
                                "text": text(e.get("text") or e.get("kurz", ""))} for e in b["ereignisse"]]}
    if v == "diagramm":
        dg = diagramm.Diagramm(b, {**rollen, "kapitel": {"name": "Kapitel", "farbe": "petrol"}})
        return {"typ": "schema", "variante": "svg", "titel": text(b["titel"]), "svg": dg.svg(), "beschreibung": dg.klartext()}
    x = {k: copy.deepcopy(w) for k, w in b.items() if k not in ("typ", "id", "nachweis", "lesehilfe", "wichtig")}
    x["typ"] = "schema"
    x["titel"] = text(b["titel"])
    if v == "bild":
        x.setdefault("quelle", b.get("nachweis", ""))
    return x


def kachelsicht(werk, ordner=None):
    """Werk 4.0 → Kachelsicht (Provinzen mit Kacheln) für Karte, Exam und Anki."""
    w = copy.deepcopy(werk)
    skript.vorbereiten(w, ordner)
    rollen = w.get("rollen", {})
    provinzen = []
    for k in w["kapitel"]:
        provinzen.append({"code": k["code"], "nr": k["nr"], "name_lat": k.get("name_lat", k["name_de"]), "name_de": k["name_de"],
                          "leitfrage": k["leitfrage"], "kompakt": k["kompakt"], "anker": k.get("anker", []), "seiten": k.get("seiten", ""),
                          "kacheln": [kachel(a, w, rollen) for a in k["abschnitte"]]})
    r = w.get("repetitorium")
    if r:
        provinzen.append({"code": "L", "nr": r["nr"], "name_lat": r.get("name_lat", "Repetitorium"), "name_de": r["name_de"],
                          "leitfrage": r["leitfrage"], "kompakt": r["kompakt"], "anker": [], "seiten": "",
                          "kacheln": [kachel(a, w, rollen) for a in r.get("abschnitte", [])]})
    m = dict(w["meta"])
    m.setdefault("typ", "werk")
    sicht = {"standard": "4.0", "meta": m, "modul": w["modul"], "quellen": w["quellen"], "provinzen": provinzen,
             "motto": w.get("motto") or {"lat": "Festina lente.", "de": "Eile mit Weile.", "stelle": "Rechtssprichwort"},
             "selbsttest": [{"frage": text(q["frage"]), "antwort": text(q["antwort"]), "kachel": q["abschnitt"]}
                            for k in w["kapitel"] for q in k.get("kontrollfragen", [])],
             "aenderungen": w.get("aenderungen", [])}
    for feld in ("lexicon", "quellenkritik"):
        if w.get(feld):
            sicht[feld] = [{**{x: (text(y) if isinstance(y, str) else y) for x, y in e.items() if x != "abschnitt"}, "kachel": e["abschnitt"]} for e in w[feld]]
    return sicht


def exam_sicht(exam, werk):
    """Exam 4.0 → interne Sicht des Exam-Renderers: abschnitte → kacheln, Grafik (Abbildung) → Schema."""
    e = copy.deepcopy(exam)
    for f in e["fragen"]:
        f["kacheln"] = f.pop("abschnitte")
        if f.get("grafik"):
            f["grafik"] = schema({"typ": "abbildung", **f["grafik"]}, werk.get("rollen", {}))
    return e


if __name__ == "__main__":
    import json
    import sys
    w = json.load(open(sys.argv[1], encoding="utf-8"))
    s = kachelsicht(w)
    print(json.dumps({p["code"]: [(k["code"], [b["typ"] for b in k["bausteine"]], len(k.get("kernfakten", []))) for k in p["kacheln"]]
                      for p in s["provinzen"]}, ensure_ascii=False))
