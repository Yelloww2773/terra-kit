#!/usr/bin/env python3
"""(c) Oliver Bedernik · Terra-Kit 4.0 · umsetzen.py

Setzt ein Werk des Standards 3.x (Provinzen mit Kacheln) in den Standard 4.0 um (Kapitel mit Abschnitten
und Bausteinen). Inhalt und Codes bleiben unverändert; was ein Mensch entscheiden muss, steht in der
Nacharbeitsliste (Überleitungen, Kerninhalte, Lösungen der Fallbeispiele …).

Aufruf:   python3 umsetzen.py alt.json neu.json [--liste nacharbeit.md]
          python3 umsetzen.py --exam exam_alt.json exam_neu.json
Abbildung:
  Provinz → Kapitel (Provinz L → Repetitorium; ihre Kacheln werden eigene Abschnitte L1 …)
  Kachel → Abschnitt (seite → fundstelle; quellen → Randbeleg am ersten Textbaustein, Quellen erhalten bei Bedarf
           eine Sigle; relevanz entfällt, Kerninhalte setzt der Autor mit „wichtig“)
  definition → definition (Normwortlaut → zitat); kern → kern; formel, rechenweg → unverändert
  merke, feinheit, klausurfalle, austriacum, aktualisierung, luecke → spitzmarke
  latinum → latinum; beispiel → fallbeispiel
  schema tabelle → tabelle; abgrenzung → Vergleichstabelle; zeitleiste → Abbildung „zeitleiste“;
  fluss → Abbildung „diagramm“ (Stil fluss); kurve, tkonto, svg, baum, bild → Abbildung gleicher Art
  kernfakten → Kernsätze; merkhilfe → Merke mit „Merkhilfe:“
  selbsttest → Kontrollfragen des Kapitels; lexicon und quellenkritik: kachel → abschnitt
"""
import argparse
import copy
import datetime as dt
import json
import re
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent
ROEMISCH = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]
FARBEN_KAPITEL = ["indigo", "petrol", "moos", "bronze", "terrakotta", "wein", "pflaume"]
SPITZMARKE = {"merke": "merke", "feinheit": "feinheit", "klausurfalle": "klausurhinweis", "austriacum": "austriacum",
              "aktualisierung": "aktualisierung", "luecke": "luecke"}
FLUSS_ART = {"start": "start", "frage": "frage", "station": "zustand", "ergebnis": "ergebnis", "sperre": "abbruch"}


class Umsetzer:
    def __init__(self, alt):
        self.alt = alt
        self.liste = []  # Nacharbeit: (Ort, Hinweis)
        self.ids = set()
        self.quellen = copy.deepcopy(alt.get("quellen", []))

    def notiz(self, ort, text):
        self.liste.append((ort, text))

    def kennung(self, titel, code):
        basis = re.sub(r"[^a-z0-9]+", "_", (titel or code).lower().translate(str.maketrans("äöüß", "aous")))[:18].strip("_") or code.lower()
        k, i = basis, 2
        while k in self.ids:
            k, i = f"{basis}_{i}", i + 1
        self.ids.add(k)
        return k

    def sigle(self, kurz):
        """Schlüssel für @-Verweise: kurz, wenn es schon eine Sigle ist (ABGB), sonst Familienname (Bydlinski, Kelsen2)."""
        q = next((x for x in self.quellen if x["kurz"] == kurz), None)
        if q is None:
            raise SystemExit(f"Kachelquelle „{kurz}“ fehlt im Quellenverzeichnis")
        if q.get("sigle"):
            return q["sigle"]
        if re.fullmatch(r"[A-Za-z0-9ÄÖÜäöü]+", kurz):
            return kurz
        name = re.sub(r"^(?:[A-ZÄÖÜ]\.\s*)+", "", kurz)
        basis = re.sub(r"[^A-Za-z0-9ÄÖÜäöü]", "", re.split(r"[,/ ]", name)[0]) or "Q"
        s, i = basis, 2
        vergeben = {x.get("sigle") or x["kurz"] for x in self.quellen}
        while s in vergeben:
            s, i = f"{basis}{i}", i + 1
        q["sigle"] = s
        return s

    # ── Bausteine ──────────────────────────────────────────────────────────
    def block(self, b, code):
        t = b["typ"]
        if t == "definition":
            aus = [{"typ": "definition", "text": b["text"]}]
            if b.get("zitat"):
                aus.append({"typ": "zitat", "text": b["zitat"]["text"], "quelle": b["zitat"]["quelle"]})
            return aus
        if t == "kern":
            return [{k: v for k, v in b.items() if k in ("typ", "titel", "punkte")}]
        if t in ("formel", "rechenweg"):
            return [copy.deepcopy(b)]
        if t in SPITZMARKE:
            x = {"typ": "spitzmarke", "art": SPITZMARKE[t], "text": b["text"]}
            for f in ("norm", "datum", "quelle", "grund"):
                if b.get(f):
                    x[f] = b[f]
            return [x]
        if t == "latinum":
            return [{"typ": "latinum", "lat": b["lat"], "de": b["de"], "stelle": b["stelle"]}]
        if t == "beispiel":
            if not b.get("loesung"):
                self.notiz(code, "Fallbeispiel ohne Lösungsskizze; 4.0 verlangt eine Lösung (vorläufig „Lösung im Text“)")
            return [{"typ": "fallbeispiel", "sachverhalt": b["sachverhalt"], "loesung": b.get("loesung") or "Die Lösung ergibt sich aus dem Text des Abschnitts."}]
        if t == "schema":
            return [self.schema(b, code)]
        raise ValueError(f"{code}: unbekannter Baustein {t}")

    def schema(self, b, code):
        v = b["variante"]
        nachweis = b.get("nachweis") or "Eigene Darstellung"
        if v == "tabelle":
            x = {"typ": "tabelle", "id": self.kennung(b["titel"], code), "titel": b["titel"], "kopf": b["kopf"], "zeilen": b["zeilen"]}
            for f in ("spalten", "aussage", "art"):
                if b.get(f):
                    x[f] = b[f]
            if b.get("breit"):
                self.notiz(code, f"Tabelle „{b['titel']}“ war breit (Querformat); im Buchsatz auf Satzspiegel geprüft")
            return x
        if v == "abgrenzung":
            return {"typ": "tabelle", "id": self.kennung(b["titel"], code), "titel": b["titel"], "art": "vergleich",
                    "kopf": ["Kriterium", b["links"], b["rechts"]], "spalten": ["begriff", "text", "text"],
                    "zeilen": [[k["kriterium"], k["links"], k["rechts"]] for k in b["kriterien"]]}
        x = {"typ": "abbildung", "id": self.kennung(b["titel"], code), "titel": b["titel"], "nachweis": nachweis}
        if v == "zeitleiste":
            x.update({"variante": "zeitleiste", "ereignisse": b["ereignisse"]})
            return x
        if v == "fluss":
            x.update({"variante": "diagramm", "stil": "fluss",
                      "knoten": [{"id": k["id"], "art": FLUSS_ART[k["art"]], "zeile": k["zeile"] - 1, "spalte": k["spalte"] - 1, "text": k["text"]}
                                 for k in b["knoten"]],
                      "kanten": [{"von": k["von"], "nach": k["nach"], **({"text": k["label"]} if k.get("label") else {})} for k in b["kanten"]]})
            if sum(k["art"] == "frage" for k in b["knoten"]) >= 2:
                self.notiz(code, f"Flussdiagramm „{b['titel']}“ mit zwei oder mehr Entscheidungen: Lesehilfe ergänzen")
            return x
        x["variante"] = v
        for k, w in b.items():
            if k not in ("typ", "variante", "titel", "breit"):
                x[k] = copy.deepcopy(w)
        if v == "bild":
            x["nachweis"] = b.get("nachweis") or f'{b["quelle"]}, {b["lizenz"]}' + (f', {b["urheber"]}' if b.get("urheber") else "")
        return x

    # ── Abschnitte ─────────────────────────────────────────────────────────
    def abschnitt(self, k):
        c = k["code"]
        bl = []
        for b in k["bausteine"]:
            bl += self.block(b, c)
        # Einbettungen brauchen einen Verweis im Text davor ({{abb:…}} / {{tab:…}})
        neu_bl = []
        for b in bl:
            if b["typ"] in ("abbildung", "tabelle"):
                art = "abb" if b["typ"] == "abbildung" else "tab"
                vor = next((x for x in reversed(neu_bl) if x["typ"] in ("definition", "absatz", "kernsatz") and "text" in x), None)
                marke = "{{" + art + ":" + b["id"] + "}}"
                if vor:
                    t = vor["text"].rstrip()
                    vor["text"] = (t[:-1] + f" ({marke})." if t.endswith(".") else t + f" ({marke})")
                else:
                    neu_bl.append({"typ": "absatz", "text": f"Überblick: {marke}."})
                    self.notiz(c, f"Verweis auf {marke} als eigener Satz eingefügt; Überleitung formulieren")
            neu_bl.append(b)
        bl = neu_bl
        # Kernfakten → Kernsätze nach Definition und Kernliste
        kerns = [{"typ": "kernsatz", "text": f} for f in k.get("kernfakten", [])]
        if kerns:
            pos = max((i for i, b in enumerate(bl) if b["typ"] in ("definition", "kern", "zitat")), default=0) + 1
            bl[pos:pos] = kerns
        if k.get("merkhilfe"):
            bl.append({"typ": "spitzmarke", "art": "merke", "text": f"Merkhilfe: {k['merkhilfe']}"})
        if bl and bl[0]["typ"] not in ("absatz", "definition"):
            self.notiz(c, f"beginnt mit „{bl[0]['typ']}“; 4.0 verlangt Überleitung oder Definition am Anfang")
            bl.insert(0, {"typ": "absatz", "text": k["titel"].rstrip(".") + "."})
        a = {"code": c, "titel": k["titel"], "bloecke": bl}
        if k.get("anker"):
            a["anker"] = k["anker"]
        if k.get("seite"):
            a["fundstelle"] = k["seite"]
        if k.get("quellen"):  # Quellen der Kachel → ein Randbeleg am ersten Textbaustein (4.0: Belege stehen am Rand)
            erster = next((x for x in bl if x["typ"] in ("absatz", "definition") and "text" in x), None)
            belege = "; ".join("@" + self.sigle(q) for q in k["quellen"])
            if erster:
                erster["text"] = erster["text"].rstrip() + "^[" + belege + "]"
            else:
                a["quellen"] = k["quellen"]
        if k.get("relevanz") == "kern":
            self.notiz(c, "war Kernstoff (★); Kerninhalt mit „wichtig“ selbst entscheiden (höchstens ein Drittel der Abschnitte)")
        if sum(b["typ"] == "abbildung" for b in bl) > 1:
            self.notiz(c, "mehr als eine Abbildung; im Buchsatz höchstens eine je Abschnitt: teilen")
        return a

    # ── Werk ───────────────────────────────────────────────────────────────
    def werk(self):
        w = self.alt
        if not str(w.get("standard", "")).startswith("3"):
            raise SystemExit(f"Standard {w.get('standard')}: nur Werke des Standards 3.x lassen sich umsetzen")
        m = w["meta"]
        meta = {k: m[k] for k in ("titel", "kurz", "untertitel", "reihe", "lehrveranstaltung", "version", "stand", "urheber", "ort", "typ") if m.get(k)}
        meta.setdefault("urheber", "(c) Oliver Bedernik")
        modul = {k: v for k, v in w["modul"].items() if k in ("domaene", "primaerquelle", "sekundaerquelle", "stand_art", "pruefdimensionen", "anker")}
        modul["zitierstil"] = "APA7" if w["modul"]["domaene"] == "wirtschaft" else "AZR"
        provinzen = [p for p in w["provinzen"] if p["code"] != "L"]
        L = next((p for p in w["provinzen"] if p["code"] == "L"), None)
        meta["provinzen"] = [{"code": p["code"], "nr": p["nr"], "name_de": p["name_de"], "farbe": FARBEN_KAPITEL[i % 7]} for i, p in enumerate(provinzen)]
        if L:
            meta["provinzen"].append({"code": "L", "nr": L["nr"], "name_de": L["name_de"], "farbe": "tinte"})
        kapitel = []
        for p in provinzen:
            k = {"code": p["code"], "nr": p["nr"], "name_lat": p["name_lat"], "name_de": p["name_de"], "leitfrage": p["leitfrage"],
                 "kompakt": p["kompakt"], "einleitung": [p["leitfrage"]], "abschnitte": [self.abschnitt(x) for x in p["kacheln"]]}
            for f in ("anker", "seiten"):
                if p.get(f):
                    k[f] = p[f]
            self.notiz(p["code"], "Einleitung ist vorläufig die Leitfrage; Anschluss an das vorige Kapitel und Wegweiser formulieren")
            kapitel.append(k)
        neu = {"standard": "4.0", "meta": meta, "modul": modul, "quellen": self.quellen, "kapitel": kapitel}
        if w.get("motto"):
            neu["motto"] = w["motto"]
        codes = {a["code"]: k["code"] for k in kapitel for a in k["abschnitte"]}
        if L:
            neu["repetitorium"] = {f: L[f] for f in ("nr", "name_lat", "name_de", "leitfrage", "kompakt")}
            neu["repetitorium"]["code"] = "L"
            if L.get("kacheln"):
                neu["repetitorium"]["abschnitte"] = [self.abschnitt(x) for x in L["kacheln"]]
                codes.update({a["code"]: "L" for a in neu["repetitorium"]["abschnitte"]})
        for q in w.get("selbsttest", []):
            ziel = q["kachel"]
            k = next((x for x in kapitel if x["code"] == codes.get(ziel)), kapitel[-1])
            k.setdefault("kontrollfragen", []).append({"frage": q["frage"], "antwort": q["antwort"], "abschnitt": ziel})
        for feld in ("lexicon", "quellenkritik"):
            if w.get(feld):
                neu[feld] = [{**{k: v for k, v in e.items() if k != "kachel"}, "abschnitt": e["kachel"]} for e in w[feld]]
        prot = list(w.get("aenderungen", []))
        prot.append({"version": m["version"], "datum": dt.date.today().isoformat(), "text": "Umsetzung auf den Standard 4.0 (Buchsatz) mit umsetzen.py"})
        neu["aenderungen"] = prot
        neu["rollen"] = {}
        return neu


def exam_umsetzen(alt):
    """Exam 3.x → 4.0: kacheln → abschnitte (Codes bleiben), Grafik (Schema) → Abbildung ohne typ und id."""
    if not str(alt.get("standard", "")).startswith("3"):
        raise SystemExit(f"Exam im Standard {alt.get('standard')}: nur 3.x lässt sich umsetzen")
    u = Umsetzer({"quellen": []})
    neu = {"standard": "4.0", "meta": copy.deepcopy(alt["meta"]), "fragen": []}
    for f in alt["fragen"]:
        g = {}
        for k, v in f.items():
            if k == "kacheln":
                g["abschnitte"] = v
            elif k == "grafik":
                x = u.schema(v, f["id"])
                g["grafik"] = {k2: v2 for k2, v2 in x.items() if k2 not in ("typ", "id")}
            else:
                g[k] = copy.deepcopy(v)
        neu["fragen"].append(g)
    return neu, u.liste


def main():
    ap = argparse.ArgumentParser(description="Werk oder Exam 3.x → Standard 4.0")
    ap.add_argument("alt")
    ap.add_argument("neu")
    ap.add_argument("--liste", help="Nacharbeitsliste als Markdown schreiben")
    ap.add_argument("--exam", action="store_true", help="ein Exam (exam.json) umsetzen statt eines Werks")
    arg = ap.parse_args()
    if arg.exam:
        neu, liste = exam_umsetzen(json.loads(Path(arg.alt).read_text(encoding="utf-8")))
        Path(arg.neu).write_text(json.dumps(neu, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"Exam umgesetzt: {len(neu['fragen'])} Fragen" + "".join(f"\n  {o}: {t}" for o, t in liste))
        return
    u = Umsetzer(json.loads(Path(arg.alt).read_text(encoding="utf-8")))
    neu = u.werk()
    Path(arg.neu).write_text(json.dumps(neu, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n_ab = sum(len(k["abschnitte"]) for k in neu["kapitel"]) + len(neu.get("repetitorium", {}).get("abschnitte", []))
    print(f"Umgesetzt: {len(neu['kapitel'])} Kapitel, {n_ab} Abschnitte · Nacharbeit: {len(u.liste)} Stellen")
    if arg.liste:
        zeilen = [f"# Nacharbeit nach der Umsetzung · {neu['meta']['titel']}", "", "(c) Oliver Bedernik · Terra-Kit 4.0", ""]
        zeilen += [f"- **{o}**: {t}" for o, t in u.liste]
        Path(arg.liste).write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    for o, t in u.liste[:12]:
        print(f"  {o}: {t}")
    if len(u.liste) > 12:
        print(f"  … {len(u.liste) - 12} weitere")


if __name__ == "__main__":
    main()
