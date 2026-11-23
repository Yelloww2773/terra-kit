#!/usr/bin/env python3
"""(c) Oliver Bedernik · Terra-Kit 4.0 · skript.py

Lernskript im Buchsatz (Standard 4.0): Kapitel mit Abschnitten und Bausteinen, Fließtext mit Randbelegen,
dazu Prozessgrafiken (Fluss, BPMN), Zeitstrahl, Kurve, Organigramm, T-Konto, Formel und Rechenweg, Merkband,
Zitat und Vergleich nach einem Farbschlüssel (Rollen des Werks). Umbruch und Seitenverweise setzt Paged.js
(fest versioniert); Randbelege, Kolumnentitel und Daumen setzt skript.py nach dem Umbruch.
Hilfsfunktionen (Markup, KaTeX, Grafiken, Kontaktabzug) liegen in satz.py.

Ablauf: Prüfung (validate.py: Schema und Regeln) → Nahtliste → HTML → Umbruch in Chromium mit Korrekturläufen
→ Prüfung im Satz → PDF mit Metadaten und Lesezeichen → Vermerkprüfung → Kontaktabzug → Bericht.

Aufruf:  python3 skript.py werk.json [--aus ORDNER] [--nur-pruefen] [--laeufe N]
Ergebnis: Terra_<Name>_Lernskript_v<Version>_<JJJJ-MM>.pdf, dazu _bericht.json, _kontakt.png, nahtliste.md
"""
import argparse
import datetime as dt
import functools
import html
import http.server
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

KIT = Path(__file__).resolve().parent
sys.path.insert(0, str(KIT))
import rechenprobe  # noqa: E402
import satz  # noqa: E402  (Typografie, Trennung, Hochzahlen, Tabellen, Quellenverzeichnis, Kontaktabzug)
from satz import esc, NBSP  # noqa: E402
import diagramm  # noqa: E402
import relief  # noqa: E402  (Höhenlinien der Umschläge)
from diagramm import FARBEN  # noqa: E402

VERMERK = "(c) Oliver Bedernik"
NM = KIT / "node_modules"
ZIEL = "Schlüssel"  # Entwurf 12: Marke für Kerninhalte (Schlüssel, am Rand mit Leiste); ersetzt ☉ und die Relevanzmarken ★ ◆ ○
SCHLUESSEL_SVG = ('<svg viewBox="0 0 26 12" aria-hidden="true"><circle cx="6" cy="6" r="4.1" fill="none" stroke="currentColor" stroke-width="2.3"/>'
                  '<path d="M10.1 6H24.6M20.6 6v4.2M24.4 6v3" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round"/></svg>')
ZIEL_ANTEIL_ABSCHNITTE, ZIEL_ANTEIL_BAUSTEINE = 1 / 3, 1 / 4  # darüber verliert die Marke ihre Aussage (Warnung)
MONATE = ["Jänner", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]
MON_K = ["Jän", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
# Tabellenkopf auf der Folgeseite wiederholen: Beim Aufbau der Fortsetzung (erste Zeile ist nicht die erste des Körpers)
# wird der Kopf der Quelltabelle eingesetzt, bevor Paged.js den Überlauf misst; die Höhe ist damit eingerechnet.
KOPF_JS = """class KopfWiederholen extends Paged.Handler {
  renderNode(clone, node) {
    if (!clone || clone.nodeType !== 1 || clone.tagName !== 'TR') return;
    const tabelle = clone.closest('table'), quelle = node.closest('table');
    if (!tabelle || tabelle.tHead || !quelle || !quelle.tHead) return;
    if (!node.parentElement || node.parentElement.tagName !== 'TBODY' || node === node.parentElement.firstElementChild) return;
    const kopf = quelle.tHead.cloneNode(true);
    kopf.removeAttribute('data-ref'); kopf.querySelectorAll('[data-ref]').forEach(e => e.removeAttribute('data-ref'));
    kopf.classList.add('wiederholt');
    tabelle.insertBefore(kopf, tabelle.firstChild);
  }
}
Paged.registerHandlers(KopfWiederholen);"""
LANGE_TABELLE = 14  # ab so vielen Zeilen darf eine Tabelle geteilt werden (mit wiederholtem Kopf)
KAPITELFARBE = {"A": "indigo", "B": "petrol", "C": "moos", "D": "bronze", "E": "terrakotta", "F": "wein", "G": "pflaume", "L": "tinte"}
EINBETTUNG = ("abbildung", "fallbeispiel", "tabelle", "akteure")

RE_ABB = re.compile(r"\{\{(abb|tab):([a-z0-9_]+)\}\}")
RE_VW = re.compile(r"\[\[(?:[A-Z]{2,5}:)?([A-GL][1-9][0-9]?)\]\]")
RE_NORM = re.compile(r"(?:\bArt|§§?)\s?\d+[a-z]?(?:\s(?:Abs|Z|lit)\s?\w+)*(?:(?:,\s?|\s(?:und|bis)\s)\d+[a-z]?)*(?:\s(?:ff|f))?")
RE_GESETZ = re.compile(r"\s+(?:[A-ZÄÖÜ][A-Za-zÄÖÜäöü]*(?:-[A-Z][A-Za-z]*)?)")
RE_FUNDSTELLE = re.compile(r"\b(RGBl|PGS|StGBl|BGBl(?: I| II| III)?) (\d{4})/(\d+(?:, \d+)*(?: (?:und|bis) \d+)?)")  # AZR: Jahr/Nummer


def als_block(x):
    return x if isinstance(x, dict) else {"typ": "absatz", "text": x}


def punkt_text(p):
    """Listenpunkt als Text oder als {text, wichtig}."""
    return p if isinstance(p, str) else p["text"]


def punkt_wichtig(p):
    return isinstance(p, dict) and bool(p.get("wichtig"))


def anspruchsvoll(b):
    """Entwurf 9: Lesehilfe nur, wo sich die Lesart nicht von selbst ergibt. Anspruchsvoll sind BPMN mit Bahnen,
    Flussdiagramme mit mindestens zwei Entscheidungen und Vergleichstabellen mit mindestens drei Spalten und sechs Zeilen."""
    if b["typ"] == "abbildung" and b.get("variante") == "diagramm":
        return len(b.get("bahnen", [])) >= 2 or sum(k.get("art") == "frage" for k in b.get("knoten", [])) >= 2
    if b["typ"] == "tabelle":
        return b.get("art") == "vergleich" and len(b["kopf"]) - 1 >= 3 and len(b["zeilen"]) >= 6
    return False


def lesehilfe_html(s, b, nachweis=""):
    return f'<div class="abb-lesehilfe"><div class="lbl">Lesehilfe</div><p>{s.md(b["lesehilfe"])}</p>{nachweis}</div>'


def ziel(rand=False, titel="Kerninhalt"):
    """Schlüssel für Kerninhalte, gezeichnet (unabhängig von Schriften); rand=True setzt ihn in die linke Randspalte,
    wo zusätzlich eine Leiste die ganze Stelle begleitet (CSS .wichtig::after)."""
    return f'<span class="ziel{" rand" if rand else ""}" title="{titel}">{SCHLUESSEL_SVG}</span>'


def quell_schluessel(q):
    """Schlüssel einer Quelle für @-Randbelege: Sigle, dazu das Kurzzitat, wenn es nur aus Buchstaben und Ziffern besteht."""
    return [x for x in (q.get("sigle"), q["kurz"]) if x and re.fullmatch(r"[A-Za-z0-9ÄÖÜäöü]+", x)] or [q["kurz"]]


def quell_anker(q):
    """Sprungziel einer Quelle im Quellenverzeichnis (aus dem Kurzzitat, in Adressen zulässige Zeichen)."""
    return re.sub(r"[^A-Za-z0-9ÄÖÜäöü]+", "-", q["kurz"]).strip("-")


def alle_abschnitte(werk):
    """Alle Abschnitte in Lesereihenfolge, einschließlich der eigenen Abschnitte des Repetitoriums."""
    return [a for k in werk["kapitel"] for a in k["abschnitte"]] + list((werk.get("repetitorium") or {}).get("abschnitte", []))


def rep_kapitel(werk):
    """Das Repetitorium als Kapitel ohne Einleitung, wenn es eigene Abschnitte trägt (4.0), sonst None."""
    r = werk.get("repetitorium")
    if not r or not r.get("abschnitte"):
        return None
    return {**r, "code": "L", "einleitung": [], "abschnitte": r["abschnitte"]}


def listen(werk):
    """Alle Blockfolgen in Lesereihenfolge: (Schlüssel, Kapitel, Abschnitt oder None, Blöcke); zuletzt eigene Abschnitte des Repetitoriums."""
    for k in werk["kapitel"]:
        yield f'{k["code"]}E', k, None, [als_block(x) for x in k["einleitung"]]
        for a in k["abschnitte"]:
            yield a["code"], k, a, a["bloecke"]
        if k.get("abschluss"):
            yield f'{k["code"]}S', k, None, k["abschluss"]
    rk = rep_kapitel(werk) if "repetitorium" in werk else None
    if rk:
        for a in rk["abschnitte"]:
            yield a["code"], rk, a, a["bloecke"]


def fussnoten_zerlegen(text):
    """Trennt ^[…]-Fußnoten aus dem Text (verschachtelte [[…]] erlaubt). → (Text mit \x00Fn\x00, [Fußnoten])."""
    aus, fns, i = [], [], 0
    while i < len(text):
        if text.startswith("^[", i):
            tiefe, j = 1, i + 2
            while j < len(text) and tiefe:
                tiefe += {"[": 1, "]": -1}.get(text[j], 0)
                j += 1
            if tiefe:
                raise ValueError("Fußnote ohne schließende Klammer: " + text[i:i + 40])
            fns.append(text[i + 2:j - 1])
            aus.append(f"\x00F{len(fns) - 1}\x00")
            i = j
        else:
            aus.append(text[i])
            i += 1
    return "".join(aus), fns


def block_texte(b):
    for f in ("text", "sachverhalt", "loesung", "aussage", "titel", "nachweis", "quelle"):
        if f in b:
            yield b[f]
    for feld in b.get("felder", []) + b.get("eintraege", []):
        for c in feld:
            yield c
    for f in ("lat", "de", "stelle"):
        if b.get(f):
            yield b[f]
    for p in b.get("punkte", []):
        yield punkt_text(p)
    for z in b.get("zeilen", []):
        for c in z:
            yield c
    for c in b.get("kopf", []) + b.get("unterkopf", []):
        if c:
            yield c
    for s in b.get("schritte", []):  # Merkband (kopf, text) und Rechenweg (text)
        for f in ("kopf", "text"):
            if s.get(f):
                yield s[f]
    for kn in b.get("knoten", []):
        for f in ("text", "unter"):
            if kn.get(f):
                yield kn[f]
        for p in kn.get("liste", []):
            yield p
    for kn in b.get("kanten", []):
        if kn.get("text"):
            yield kn["text"]
    for e in b.get("ereignisse", []):  # Zeitstrahl (kurz) und Zeitleiste (text)
        yield e.get("kurz") or e.get("text", "")
    for f in ("aufgabe", "ergebnis", "beschreibung", "buchungssatz"):  # 4.0: Rechenweg, SVG, Bild, T-Konto
        if b.get(f):
            yield b[f]
    for v in b.get("variablen", []):
        yield v["bedeutung"]
    for k in b.get("konten", []):
        yield k["name"]
        for e in k.get("soll", []) + k.get("haben", []):
            yield e["text"]
    for r in b.get("reihen", []):
        yield r["name"]
    for mk in b.get("markierungen", []):
        if mk.get("text"):
            yield mk["text"]


def kontext(b):
    """Gesetz aus dem Zusammenhang: Titel von Steckbrief und Grafik, Kopf einer Tabelle."""
    return " ".join([b.get("titel", "")] + [c for c in b.get("kopf", []) if c]) if b["typ"] in ("steckbrief", "abbildung", "tabelle") else ""


def texte(werk, mit_kontext=False):
    for schl, k, a, bl in listen(werk):
        for n, b in enumerate(bl, 1):
            for t in block_texte(b):
                yield (f"{schl} Block {n} ({b['typ']})", t, kontext(b)) if mit_kontext else (f"{schl} Block {n} ({b['typ']})", t)
    for k in werk["kapitel"]:
        extra = [(f'{k["code"]} Leitfrage', k["leitfrage"])] + [(f'{k["code"]} Kontrollfrage', t) for q in k.get("kontrollfragen", []) for t in (q["frage"], q["antwort"])]
        extra += [(f'{k["code"]} In 60 Sekunden', t) for t in k.get("kompakt", [])]
        for ort, t in extra:
            yield (ort, t, "") if mit_kontext else (ort, t)
    for p in werk.get("personen", []):
        yield ("Personen", p["funktion"], "") if mit_kontext else ("Personen", p["funktion"])
    for q in werk.get("quellenkritik", []):
        for t in (q["befund"], q["richtig"]):
            yield ("Quellenkritik", t, "") if mit_kontext else ("Quellenkritik", t)


def pruefe(werk, ordner=None):
    """Gesamtprüfung über validate.py (Schema, Typografie, Codes, Bausteine, Quellen, Satzregeln). → (Fehler, Warnungen)"""
    import validate
    b = validate.validiere(werk, ordner)
    return [z.split(None, 1)[1] for z in b.fehler], [z.split(None, 1)[1] for z in b.warnungen]


def regeln(werk):
    """Satzregeln des Buchsatzes (nach bestandener Schemaprüfung; aufgerufen von validate.py). → (Fehler, Warnungen, Hinweise)"""
    fehler, warn, hinweis = [], [], []
    codes = [a["code"] for a in alle_abschnitte(werk)]
    for c in {c for c in codes if codes.count(c) > 1}:
        fehler.append(f"Abschnittscode doppelt: {c}")
    kurz = {x for q in werk["quellen"] for x in quell_schluessel(q)}
    rollen = set(werk.get("rollen", {})) | {"kapitel"}
    dims = set(werk["modul"].get("pruefdimensionen", []))
    zaehl = {d: 0 for d in dims}
    ids, gesehen = {}, set()
    for schl, k, a, bl in listen(werk):
        if a:
            if not a["code"].startswith(k["code"]):
                fehler.append(f'{a["code"]}: Code passt nicht zu Kapitel {k["code"]}')
            if bl[0]["typ"] not in ("absatz", "definition"):
                fehler.append(f'{a["code"]}: Abschnitt beginnt mit „{bl[0]["typ"]}“ statt mit Überleitung oder Definition')
            kerns = [b for b in bl if b["typ"] == "kernsatz"]
            if not kerns and a.get("wichtig"):
                warn.append(f'{a["code"]}: {ZIEL}-Abschnitt ohne Kernsatz')
            if len(kerns) > 3:
                fehler.append(f'{a["code"]}: mehr als drei Kernsätze')
            if sum(b["typ"] == "abbildung" for b in bl) > 1:
                fehler.append(f'{a["code"]}: mehr als eine Abbildung im Abschnitt')
            for d in a.get("dimensionen", []):
                if d not in dims:
                    fehler.append(f'{a["code"]}: Prüfdimension „{d}“ nicht im Modul')
                else:
                    zaehl[d] += 1
            liste = sum(len(" ".join(punkt_text(p) for p in b["punkte"])) for b in bl if b["typ"] == "aufzaehlung")  # Kernlisten (kern) sind die Form der Terrae
            alles = sum(len(b.get("text", "")) for b in bl) + liste
            if alles and liste / alles > 1 / 3:
                warn.append(f'{a["code"]}: Aufzählungen tragen mehr als ein Drittel des Abschnitts')
        for i, b in enumerate(bl):
            for t in [b.get(f, "") for f in ("text", "sachverhalt", "loesung", "aussage")] + [punkt_text(p) for p in b.get("punkte", [])]:
                for m in RE_ABB.finditer(t):
                    gesehen.add((m.group(1), m.group(2)))
            if b["typ"] == "kernsatz" and "**" not in b["text"]:
                fehler.append(f'{schl}: Kernsatz ohne fett gesetzten Fachbegriff (Anki-Lücke fehlt)')
            if b["typ"] in ("abbildung", "tabelle", "akteure"):
                art = "abb" if b["typ"] == "abbildung" else "tab"
                if b["id"] in ids:
                    fehler.append(f'{schl}: {art}-Kennung doppelt: {b["id"]}')
                ids[b["id"]] = art
                uebersicht = schl.endswith("E") and i == 0 and art == "abb"  # Entwurf 11: Übersichtsgrafik eröffnet die Provinz ohne Einleitungstext
                if (art, b["id"]) not in gesehen and not uebersicht:
                    fehler.append(f'{schl}: {"Abbildung" if art == "abb" else "Tabelle"} „{b["id"]}“ wird nicht vorher im Text angesprochen'
                                  f' ({{{{{art}:{b["id"]}}}}})')
            if b["typ"] in EINBETTUNG and i and bl[i - 1]["typ"] in EINBETTUNG:
                warn.append(f'{schl}: zwei Einbettungen ohne Text dazwischen')
            if b.get("variante") == "diagramm":
                fehler += [f'{schl} {b["id"]}: {f}' for f in diagramm.pruefe_diagramm(b)]
            if b["typ"] in ("abbildung", "tabelle") and anspruchsvoll(b) and not b.get("lesehilfe"):
                warn.append(f'{schl}: anspruchsvolle Einbettung „{b["id"]}“ ohne Lesehilfe')
            if b.get("lesehilfe") and not anspruchsvoll(b):
                warn.append(f'{schl}: Lesehilfe bei „{b["id"]}“ überflüssig; sie gehört nur zu anspruchsvollen Grafiken und Tabellen')
            for r in ([kn.get("rolle") for kn in b.get("knoten", [])] + [x["rolle"] for x in b.get("bahnen", [])]
                      + [e.get("rolle") for e in b.get("ereignisse", [])] + [s.get("rolle") for s in b.get("schritte", [])]
                      + [r for r in b.get("spaltenrollen", []) if r]):
                if r and r not in rollen:
                    fehler.append(f'{schl}: Rolle „{r}“ fehlt im Farbschlüssel')
    for k in werk["kapitel"]:  # Zielscheibe sparsam: sonst markiert sie nichts mehr
        ab = k["abschnitte"]
        n_ab = sum(bool(a.get("wichtig")) for a in ab)
        if ab and n_ab > ZIEL_ANTEIL_ABSCHNITTE * len(ab):
            warn.append(f'{k["code"]}: {n_ab} von {len(ab)} Abschnitten mit {ZIEL}; mehr als ein Drittel entwertet die Marke')
        bloecke = [b for a in ab for b in a["bloecke"]]
        punkte = [p for b in bloecke if b["typ"] == "kern" for p in b["punkte"]]
        n_e, n_b = len(bloecke) + len(punkte), sum(bool(b.get("wichtig")) for b in bloecke) + sum(punkt_wichtig(p) for p in punkte)
        if n_e and n_b > ZIEL_ANTEIL_BAUSTEINE * n_e:
            warn.append(f'{k["code"]}: {n_b} von {n_e} Bausteinen und Listenpunkten mit {ZIEL}; mehr als ein Viertel entwertet die Marke')
    if dims and zaehl and any(zaehl.values()):  # nur wenn das Werk Abschnitten Prüfdimensionen zuordnet
        selten, oft = min(zaehl.values()), max(zaehl.values())
        if selten == 0:
            warn.append("Prüfdimension ohne Abschnitt: " + ", ".join(d for d, n in zaehl.items() if not n))
        elif oft > 2 * selten:
            warn.append(f"Prüfdimensionen unausgewogen: {zaehl}")
    for _, t in texte(werk):
        for m in RE_ABB.finditer(t):
            if m.group(2) not in ids:
                fehler.append(f"Verweis auf unbekannte Abbildung oder Tabelle: {m.group(0)}")
    aussen = set()
    for ort, t, kx in texte(werk, True):  # Striche und Anführungszeichen prüft validate.py für alle Felder
        for m in re.finditer(r"\*\*(.+?)\*\*", t):
            if m.group(1).rstrip(":").strip() in satz.GERUEST:
                fehler.append(f"{ort}: Gerüstwort fett: {m.group(1)}")
        try:
            rest, fns = fussnoten_zerlegen(t)
        except ValueError as e:
            fehler.append(f"{ort}: {e}")
            continue
        for fn in fns:
            for q in re.findall(r"@([A-Za-z0-9ÄÖÜäöü]+)", fn):
                if q not in kurz:
                    fehler.append(f"{ort}: Fußnote verweist auf unbekannte Quelle @{q}")
        for m in RE_VW.finditer(t):
            if m.group(1) not in codes:
                aussen.add(m.group(1))
        for m in RE_NORM.finditer(rest):
            nach = rest[m.end():m.end() + 14]
            if not RE_GESETZ.match(nach) and not re.search(r"Verfassung|Entwurf|Gesetz|Patent|B-VG|StGG", kx):
                fehler.append(f"{ort}: Normzitat ohne Gesetzesangabe: {m.group(0)}")
    for c in sorted(aussen):
        hinweis.append(f"Verweis auf {c} außerhalb des Werks: ohne Seitenzahl gesetzt")
    for k in werk["kapitel"]:
        gefragt = {q["abschnitt"] for q in k.get("kontrollfragen", [])}
        for q in k.get("kontrollfragen", []):
            if q["abschnitt"] not in codes:
                fehler.append(f'Kontrollfrage verweist auf unbekannten Abschnitt {q["abschnitt"]}')
        for a in k["abschnitte"]:
            if any(b["typ"] == "kernsatz" for b in a["bloecke"]) and a["code"] not in gefragt:
                hinweis.append(f'{a["code"]}: Kernsätze ohne Kontrollfrage (im Exam abfragen oder Kontrollfrage ergänzen)')
    return fehler, warn, hinweis


def nahtliste(werk):
    """Für jede Naht zwischen zwei Abschnitten: letzter Satz davor, erster Satz danach (Lektorat der Übergänge)."""
    def saetze(t):
        t = fussnoten_zerlegen(t)[0]
        t = re.sub(r"\x00F\d+\x00", "", t)
        t = re.sub(r"\*\*|\*", "", t)
        t = RE_ABB.sub(lambda m: ("Abb" if m.group(1) == "abb" else "Tab") + " " + m.group(2), t)
        t = RE_VW.sub(lambda m: m.group(1), t)
        return [s.strip() for s in re.split(r"(?<!\D\d\.)(?<!\D\d\d\.)(?<=[.!?])\s+(?=[A-ZÄÖÜ„])", t) if s.strip()]

    def letzter_text(bl):
        for b in reversed(bl):
            if b["typ"] in ("absatz", "kernsatz", "spitzmarke"):
                return b["text"]
            if b["typ"] == "tabelle" and b.get("aussage"):
                return b["aussage"]
            if b["typ"] == "fallbeispiel":
                return b["loesung"]
        return ""
    zeilen = ["# Nahtliste", "", f"(c) Oliver Bedernik · Terra-Kit {satz.VERSION}", ""]
    for k in werk["kapitel"]:
        ab = k["abschnitte"]
        einl = [als_block(x) for x in k["einleitung"]]
        if saetze(letzter_text(einl)):  # Einleitung ohne Text (nur Übersichtsgrafik): keine Naht zu prüfen
            zeilen += [f'## Kapitel {k["code"]}: Einleitung → {ab[0]["code"]}', f"> … {saetze(letzter_text(einl))[-1]}",
                       f'> {saetze(ab[0]["bloecke"][0]["text"])[0]} …', ""]
        for x, y in zip(ab, ab[1:]):
            zeilen += [f'## {x["code"]} → {y["code"]}', f"> … {saetze(letzter_text(x['bloecke']))[-1]}", f'> {saetze(y["bloecke"][0]["text"])[0]} …', ""]
    return "\n".join(zeilen)


# ── Inline-Auszeichnung ───────────────────────────────────────────────────
class Satz:
    def __init__(self, werk):
        self.werk = werk
        self.codes = {a["code"] for a in alle_abschnitte(werk)}
        self.quellen = {schluessel: q for q in werk["quellen"] for schluessel in quell_schluessel(q)}
        self.rollen = werk.get("rollen", {})
        m = werk["meta"]
        self.rahmen = {"titel": esc(m["titel"]), "untertitel": esc(m["untertitel"]), "stand": esc(stand_text(werk)),
                       "provinzen": [{**p, "dunkel": FARBEN[p["farbe"]][0]} for p in m.get("provinzen", [])]}
        self.nummer, self.listen = {}, {}
        na = nt = 0
        for schl, k, a, bl in listen(werk):
            self.listen[schl] = bl
            for b in bl:
                if b["typ"] == "abbildung":
                    na += 1
                    self.nummer[("abb", b["id"])] = na
                elif b["typ"] in ("tabelle", "akteure"):
                    nt += 1
                    self.nummer[("tab", b["id"])] = nt
        self.personen = werk.get("personen", [])
        self.reg, self.seiten, self.belege, self.randbelege = [], {}, [], []
        self.kx = satz.katex_alle(werk)  # 4.0: Formeln und Rechenwege, vorab gesetzt

    def farbe(self, rolle, kapitel="petrol"):
        if rolle in (None, "", "kapitel"):
            return FARBEN[kapitel]
        return FARBEN[self.rollen.get(rolle, {}).get("farbe", "grau")]

    def randbeleg(self, fn):
        """Randbeleg aus einer ^[…]-Angabe: @Quelle wird zur Randsigle (Feld `rand`, sonst `kurz`) mit Verweis auf die
        Vollangabe im Quellenverzeichnis; eine Fundstelle in Klammern folgt ohne Klammern („@SCHM (383)“ → „Schmetterer 383“)."""
        teile, pos = [], 0
        fn = fn.strip().rstrip(".").strip()
        for m in re.finditer(r"@([A-Za-z0-9ÄÖÜäöü]+)(?:\s*\(([^)]*)\))?", fn):
            if m.start() > pos:
                teile.append(self.md(fn[pos:m.start()], latein=True))
            q = self.quellen[m.group(1)]
            pin = f"{NBSP}{typo_esc(m.group(2))}" if m.group(2) else ""
            teile.append(f'<a class="rb-q" href="#q-{quell_anker(q)}">{esc(q.get("rand") or q["kurz"])}</a>{pin}')
            pos = m.end()
        if pos < len(fn):
            teile.append(self.md(fn[pos:], latein=True))
        beleg = "".join(teile)
        beleg = re.sub(r'<(span|strong) class="rg" id="rg-\d+">(.*?)</\1>', r"\2", beleg)  # Registeranker nur im Fließtext
        beleg = beleg.replace("</a> ", "</a>" + NBSP)  # Sigle und Fundstelle bleiben in einer Zeile
        return re.sub(r"\b(Rz|S|Fn) ", lambda m: m.group(1) + NBSP, beleg)

    def md(self, text, latein=False):
        text, fns = fussnoten_zerlegen(text)
        platz = {}

        def merke(h):
            schl = f"\x00P{len(platz)}\x00"
            platz[schl] = h
            return schl

        def abb(m):
            art, i = m.group(1), m.group(2)
            wort = "Abb" if art == "abb" else "Tab"
            return merke(f'<a class="abbv" href="#{art}-{i}">{wort}{NBSP}{self.nummer[(art, i)]}</a>')

        def vw(m):
            if m.group(1) in self.codes:
                return m.group(0)
            return merke(f'<span class="vw-ext">{m.group(1)}</span>')
        text = RE_ABB.sub(abb, text)
        text = RE_VW.sub(vw, text)
        marken = {}

        def marke(art, schl, roh):  # Registerstelle: \x01 Nr \x02 … \x03 überlebt Escaping und Trennung
            n = len(self.reg)
            self.reg.append((art, schl, f"rg-{n}"))
            marken[n] = f"rg-{n}"
            return f"\x01{n}\x02{roh}\x03"
        if True:
            for p in self.personen:
                for name in p["suche"]:
                    text = re.sub(r"(?<![\x01-\x03\w])" + re.escape(name) + r"(?![\w])", lambda m, p=p: marke("person", p["name"], m.group(0)), text)
            text = RE_FUNDSTELLE.sub(lambda m: marke("fundstelle", f"{m.group(1)} {m.group(2)}/{m.group(3)}", m.group(0)), text)

            def norm(m):
                rest = text_ref[0][m.end():m.end() + 50]
                g = re.match(r"\s+([A-ZÄÖÜ][\w-]*(?:\s(?:Entwurf|Verfassung|über die Reichsvertretung|Wien|St\. Germain))?)", rest)
                if not g:
                    return m.group(0)
                return marke("norm", f"{g.group(1)}|{m.group(0)}", m.group(0))
            text_ref = [text]
            text = RE_NORM.sub(norm, text)
        h = satz.md(text, latein=latein)
        h = re.sub(r"\x01(\d+)\x02", lambda m: f'<span class="rg" id="rg-{m.group(1)}">', h).replace("\x03", "</span>")

        def fett(m):
            n = len(self.reg)
            begriff = re.sub(r"<[^>]+>", "", m.group(1)).replace("\u00ad", "").replace(NBSP, " ").rstrip(":").strip()  # Vorspann „**Begriff:**“
            self.reg.append(("sache", begriff, f"rg-{n}"))
            return f'<strong class="rg" id="rg-{n}">{m.group(1)}</strong>'
        h = re.sub(r"<strong>(.*?)</strong>", fett, h)
        for i, fn in enumerate(fns):  # Entwurf 13: Randbeleg; im Text bleibt nur ein unsichtbarer Anker, der Beleg steht am rechten Rand
            if getattr(self, "ohne_fn", False):  # Wiederholungen (Füllblock) tragen keinen zweiten Beleg
                h = h.replace(f"\x00F{i}\x00", "")
                continue
            self.randbelege.append(self.randbeleg(fn))
            n = len(self.randbelege)
            h = h.replace(f"\x00F{i}\x00", f'<span class="rb-anker" id="rb-{n}" data-rb="{n}"></span>')
        for schl, wert in platz.items():
            h = h.replace(schl, wert)
        return h


# ── Zeitstrahl (maßstabgetreu, Etiketten kollisionsfrei gesetzt) ──────────
def _tag(iso):
    return dt.date.fromisoformat(iso)


def zeitstrahl_svg(b, s):
    W, X0, X1 = 680, 16, 664
    von, bis = _tag(b["von"]), _tag(b["bis"])
    tage = (bis - von).days + 1
    xpos = lambda d: X0 + (X1 - X0) * ((d - von).days + 0.5) / tage
    ROW, FS, FD = 33, 12.5, 11.5

    def breite(e):
        return max(diagramm.breite(e["etikett"], FD, 700), diagramm.breite(e["kurz"], FS)) + 6

    seiten = {}
    for e in b["ereignisse"]:
        a = _tag(e["datum"])
        z = _tag(e["bis"]) if e.get("bis") else None
        x = (xpos(a) + xpos(z)) / 2 if z else xpos(a)
        seiten.setdefault(e.get("seite", "oben"), []).append({**e, "x": x, "x_a": xpos(a), "x_z": xpos(z) if z else None, "w": breite(e)})

    def platziere(evs, rmax=4):
        evs = sorted(evs, key=lambda e: e["x"])
        bestes = [None]

        def ok(wahl, e, r, anker):
            x1, x2 = (e["x"] + 4, e["x"] + 4 + e["w"]) if anker == "start" else (e["x"] - 4 - e["w"], e["x"] - 4)
            if x1 < 0 or x2 > W:
                return None
            for f, (rf, af, (y1, y2)) in wahl:
                if rf == r and not (x2 + 8 < y1 or x1 - 8 > y2):
                    return None
                if rf >= r and x1 - 3 <= f["x"] <= x2 + 3:
                    return None
                if r >= rf and y1 - 3 <= e["x"] <= y2 + 3:
                    return None
            return (x1, x2)

        def suche(i, wahl):
            if i == len(evs):
                kosten = (max(r for _, (r, _, _) in wahl), sum(r for _, (r, _, _) in wahl), sum(a == "end" for _, (_, a, _) in wahl))
                if bestes[0] is None or kosten < bestes[0][0]:
                    bestes[0] = (kosten, list(wahl))
                return
            e = evs[i]
            for r in range(1, rmax + 1):
                for anker in ("start", "end"):
                    sp = ok(wahl, e, r, anker)
                    if sp:
                        wahl.append((e, (r, anker, sp)))
                        suche(i + 1, wahl)
                        wahl.pop()
        suche(0, [])
        if bestes[0] is None:
            raise ValueError("Zeitstrahl: Etiketten nicht kollisionsfrei setzbar")
        return bestes[0][1]

    lagen = {sd: platziere(evs) for sd, evs in seiten.items()}
    r_oben = max((r for _, (r, _, _) in lagen.get("oben", [])), default=0)
    r_unten = max((r for _, (r, _, _) in lagen.get("unten", [])), default=0)
    BAND = 20
    Y_OBEN = 10 + r_oben * ROW + 8
    Y_UNTEN = Y_OBEN + BAND
    H = Y_UNTEN + r_unten * ROW + 26
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(b["titel"])}">']
    # Achsenteilung nach Spanne (4.0): bis 18 Monate Monate, bis 15 Jahre Jahre, darüber Jahrzehnte
    jahre = tage / 365.25
    schritt = 0 if jahre <= 1.5 else (1 if jahre <= 15 else 10)
    d = dt.date(von.year, von.month, 1) if not schritt else dt.date(von.year - von.year % schritt, 1, 1)
    k = 0
    while d <= bis:
        n = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1) if not schritt else dt.date(d.year + schritt, 1, 1)
        a, z = max(d, von), min(n - dt.timedelta(days=1), bis)
        xa, xz = xpos(a) - 0.5 * (X1 - X0) / tage, xpos(z) + 0.5 * (X1 - X0) / tage
        name = MON_K[d.month - 1] if not schritt else (str(d.year) if schritt == 1 else f"{d.year}er")
        o.append(f'<rect x="{xa:.1f}" y="{Y_OBEN}" width="{xz - xa:.1f}" height="{BAND}" fill="{"#E6EEF0" if k % 2 else "#F1F5F6"}"/>')
        if xz - xa >= diagramm.breite(name, 11) + 4:  # Teilstück zu schmal für seine Beschriftung: nur das Band
            o.append(f'<text x="{(xa + xz) / 2:.1f}" y="{Y_OBEN + 13.6}" text-anchor="middle" font-family="Alegreya Sans" font-size="11" font-weight="500" fill="#4A5468">{name}</text>')
        d, k = n, k + 1
    genutzt = []
    for seite, wahl in lagen.items():
        oben = seite == "oben"
        kante = Y_OBEN if oben else Y_UNTEN
        for e, (r, anker, (x1, x2)) in wahl:
            farb, mitt, hell = s.farbe(e.get("rolle"))
            if e.get("rolle") and e["rolle"] not in genutzt:
                genutzt.append(e["rolle"])
            if e["x_z"] is not None:
                yb = kante - 5 if oben else kante
                o.append(f'<rect x="{e["x_a"]:.1f}" y="{yb}" width="{e["x_z"] - e["x_a"]:.1f}" height="5" rx="1.5" fill="{mitt}"/>')
            ende = kante - (r * ROW) + 2 if oben else kante + r * ROW - 2
            o.append(f'<line x1="{e["x"]:.1f}" y1="{kante}" x2="{e["x"]:.1f}" y2="{ende}" stroke="{farb}" stroke-width="1.3"/>')
            if e["x_z"] is None:
                o.append(f'<circle cx="{e["x"]:.1f}" cy="{kante}" r="4" fill="{farb}" stroke="#FFFFFF" stroke-width="1.2"/>')
            tx = e["x"] + 4 if anker == "start" else e["x"] - 4
            y_datum = (kante - r * ROW + 12) if oben else (kante + (r - 1) * ROW + 15)
            o.append(f'<text x="{tx:.1f}" y="{y_datum:.1f}" text-anchor="{anker}" font-family="Alegreya Sans" font-weight="700" font-size="{FD}" fill="{farb}">{esc(e["etikett"])}</text>')
            o.append(f'<text x="{tx:.1f}" y="{y_datum + 14:.1f}" text-anchor="{anker}" font-family="Alegreya Sans" font-size="{FS}" fill="#1F2A44">{esc(e["kurz"])}</text>')
    x = X0
    yl = H - 7
    for r in genutzt:
        farb = s.farbe(r)[0]
        name = s.rollen.get(r, {}).get("name", r)
        o.append(f'<rect x="{x}" y="{yl - 8.5}" width="9" height="9" rx="2" fill="{farb}"/>'
                 f'<text x="{x + 13}" y="{yl}" font-family="Alegreya Sans" font-size="11" fill="#4A5468">{esc(name)}</text>')
        x += 13 + diagramm.breite(name, 11) + 18
    o.append(f'<text class="t-wz" x="{W - 3}" y="{H - 3}" text-anchor="end">{VERMERK}</text></svg>')
    alt = "; ".join(f'{e["etikett"]} {e["kurz"]}' for e in b["ereignisse"])
    return "".join(o), alt


# ── Blöcke (Terra-Erscheinungsbild: Etiketten, Kästen und Farben wie in den bisherigen Terrae) ──
# Entwurf 7: im Skript nur „Cave!“; was eine Klausurfalle ist, erklärt „Zum Gebrauch“
LABEL = {"klausurhinweis": "Cave!", "merke": "Merke", "feinheit": "Feinheit", "austriacum": "Austriacum", "aktualisierung": "Aktualisierung",
         "luecke": "Lücke im Material"}
KASTEN = {"klausurhinweis": "klausurfalle"}  # Spitzmarke → Kastenklasse der Satzvorlage skript.css


def block_html(s, b, kfarbe, bid="", umbruch=False, laufweite=None):
    """Zielscheibe: wichtige Bausteine tragen ☉ in der linken Randspalte (Einbettungen im Titel)."""
    h = _block_html(s, b, kfarbe, bid, umbruch, laufweite)
    if not b.get("wichtig"):
        return h
    if b["typ"] in ("abbildung", "tabelle", "akteure"):
        return h.replace('<div class="schema-titel">', f'<div class="schema-titel">{ziel()}', 1)
    if b["typ"] == "fallbeispiel":
        return h.replace('<div class="fb-kopf">', f'<div class="fb-kopf">{ziel()} ', 1)
    m = re.match(r'(<[a-z]+ class=")([^"]*)(")', h)
    return f'{m.group(1)}{m.group(2)} wichtig{m.group(3)}' + h[m.end():].replace(">", ">" + ziel(True), 1)


def _block_html(s, b, kfarbe, bid="", umbruch=False, laufweite=None):
    """Bausteine im Markup des Kits 3.7.1 (Kernblock, Kästen, schema-titel mit Abb-Marke, fig, Bildnachweis, table.t, Fallbeispiel)."""
    t = b["typ"]
    db = f' data-b="{bid}"' + (' data-neue-seite="ja"' if umbruch else "") + (f' data-lw="{laufweite}"' if laufweite else "")
    if t == "absatz":
        return f'<p class="sp"{db}>{s.md(b["text"])}</p>'
    if t == "definition":  # wie satz.baustein_html: Spitzmarke „Definition“, dann der Begriff in einem Absatz
        return f'<div class="sp definition"{db}><div class="label">Definition</div><p class="def">{s.md(b["text"])}</p></div>'
    if t == "kern":  # wie satz.baustein_html „kern“: Spitzmarke und Liste mit Fachbegriff als Vorspann
        lbl = f'<div class="label">{s.md(b["titel"])}</div>' if b.get("titel") else ""
        li = "".join(f'<li class="wichtig">{ziel(True)}{s.md(punkt_text(p))}</li>' if punkt_wichtig(p) else f"<li>{s.md(punkt_text(p))}</li>"
                     for p in b["punkte"])
        return f'<div class="sp kernliste"{db}>{lbl}<ul class="kern">{li}</ul></div>'
    if t == "kernsatz":
        return f'<div class="sp kernblock"{db}><div class="lbl">Kernsatz</div><p class="kernsatz">{s.md(b["text"])}</p></div>'
    if t == "spitzmarke":
        zusatz = ""  # 4.0: Angaben der Kästen aus dem Kachelsatz (Norm, Stand und Quelle, Grund der Lücke)
        if b["art"] == "austriacum" and b.get("norm"):
            zusatz = f' <span class="norm">{s.md(b["norm"])}</span>'
        elif b["art"] == "aktualisierung" and b.get("datum"):
            d = dt.date.fromisoformat(b["datum"])
            zusatz = f' <span class="meta">seit {d.day}. {satz.MONATE[d.month - 1]} {d.year}{" · " + s.md(b["quelle"]) if b.get("quelle") else ""}</span>'
        elif b["art"] == "luecke" and b.get("grund"):
            zusatz = f' <span class="grund">sinngemäß ergänzt · {s.md(b["grund"])}</span>'
        return f'<div class="sp box {KASTEN.get(b["art"], b["art"])}"{db}><div class="lbl">{LABEL[b["art"]]}{zusatz}</div><p>{s.md(b["text"])}</p></div>'
    if t == "aufzaehlung":
        tag = "ol" if b.get("nummeriert") else "ul"
        return f'<{tag} class="sp auf{" kern" if tag == "ul" else ""}"{db}>' + "".join(f"<li>{s.md(p)}</li>" for p in b["punkte"]) + f"</{tag}>"
    if t == "zitat":
        return (f'<blockquote class="sp zitat"{db}><span class="w">„{s.md(b["text"])}“</span>'
                f'<span class="q">{s.md(b["quelle"])}</span></blockquote>')
    if t == "merkband":
        teile = []
        for i, sch in enumerate(b["schritte"]):
            d, m, h = s.farbe(sch.get("rolle"), kfarbe)
            teile.append(f'<div class="mb-schritt{" erst" if i == 0 else ""}" style="--d:{d};--m:{m};--h:{h}"><span class="mb-kopf">{s.md(sch["kopf"])}</span>'
                         f'<span class="mb-text">{s.md(sch["text"])}</span></div>')
        return (f'<div class="sp merkhilfe merkband"{db}><div class="mh-kopf"><span class="lbl">Merkhilfe</span><span class="mb-titel">{s.md(b["titel"])}</span></div>'
                f'<div class="mb-reihe">{"".join(teile)}</div></div>')
    if t == "tabelle":
        n = s.nummer[("tab", b["id"])]
        rollen = b.get("spalten") or ["begriff"] + ["text"] * (len(b["kopf"]) - 1)
        srollen = b.get("spaltenrollen") or [""] * len(b["kopf"])
        vergleich = b.get("art") == "vergleich"

        def kopfzelle(i, h):
            if not srollen[i]:
                return f'<th class="ecke">{s.md(h, latein=True)}</th>'
            d, _, hh = s.farbe(srollen[i], kfarbe)
            unter = f'<span class="uk">{s.md(b["unterkopf"][i])}</span>' if b.get("unterkopf") and b["unterkopf"][i] else ""
            return f'<th class="begriff rolle" style="--d:{d};--h:{hh}">{s.md(h, latein=True)}{unter}</th>'

        def zelle(i, c):
            kl = rollen[i] if i < len(rollen) else "text"
            if vergleich and i == 0:
                kl = "dimension"
            inhalt = s.md(c)
            if c.startswith("✗"):
                inhalt = f'<span class="nein">✗</span>{s.md(c[1:].strip())}'
            return f'<td class="{kl}">{inhalt}</td>'
        zeilen = "".join("<tr>" + "".join(zelle(i, c) for i, c in enumerate(z)) + "</tr>" for z in b["zeilen"])
        aus = f'<p class="t-aussage"><span class="lbl">Aussage</span>{s.md(b["aussage"])}</p>' if b.get("aussage") else ""
        klasse = "t vergleich gestuerzt" if vergleich else "t"
        lh = lesehilfe_html(s, b) if b.get("lesehilfe") else ""
        lang = " teilbar" if len(b["zeilen"]) > LANGE_TABELLE else ""  # 4.0: lange Tabellen laufen über die Seite, Kopf wird wiederholt
        return (f'<div class="tab einbettung{lang}{" mit-lesehilfe" if lh else ""}" id="tab-{b["id"]}" data-nr="{n}"{db}><div class="schema-titel"><span class="abb">Tab{NBSP}{n}</span>'
                f'{s.md(b["titel"], latein=True)}</div><table class="{klasse}"><thead><tr>{"".join(kopfzelle(i, h) for i, h in enumerate(b["kopf"]))}</tr></thead>'
                f'<tbody>{zeilen}</tbody></table>{aus}{lh}</div>')
    if t == "abbildung":
        n = s.nummer[("abb", b["id"])]
        if b["variante"] == "zeitstrahl":
            svg, alt = zeitstrahl_svg(b, s)
        elif b["variante"] == "diagramm":
            dg = diagramm.Diagramm(b, {**s.rollen, "kapitel": {"name": "Kapitel", "farbe": kfarbe}})
            svg, alt = dg.svg(), dg.klartext()
        else:  # 4.0: Kurve, T-Konto, Organigramm, SVG, Bild und Zeitleiste aus den Renderern des Kits (satz.py), Rahmen und Nachweis vom Buchsatz
            satz.ATMEN = False
            svg = re.sub(r'^<div class="schema-titel">.*?</div>', "", satz.schema_html(b), count=1, flags=re.S)
            svg = re.sub(r'<div class="bildnachweis">.*?</div>', "", svg, flags=re.S)
            alt = ""

        def svg_norm(m):
            inhalt = html.unescape(m.group(3))
            for nm in RE_NORM.finditer(inhalt):
                g = re.match(r"\s+([A-ZÄÖÜ][\w-]*(?:\s(?:Entwurf|Verfassung))?)", inhalt[nm.end():nm.end() + 30])
                if g and g.group(1) in ("B-VG", "StGG"):
                    n = len(s.reg)
                    s.reg.append(("norm", f"{g.group(1)}|{nm.group(0)}", f"rg-{n}"))
                    return f'{m.group(1)}id="rg-{n}" {m.group(2)}{m.group(3)}{m.group(4)}'
            return m.group(0)
        svg = re.sub(r"(<text )([^>]*>)([^<]*)(</text>)", svg_norm, svg)
        nachweis = f'<div class="bildnachweis">{s.md(b["nachweis"])}<span style="display:none">{esc(alt)}</span></div>'
        if b.get("lesehilfe"):  # Entwurf 8: Lesehilfe als eigenes Feld, unten an die Grafik gekoppelt (unteilbar mit ihr)
            unten = lesehilfe_html(s, b, nachweis)
        else:
            unten = nachweis
        return (f'<figure class="abb einbettung{" mit-lesehilfe" if b.get("lesehilfe") else ""}" id="abb-{b["id"]}" data-nr="{n}"{db}><div class="schema-titel"><span class="abb">Abb{NBSP}{n}</span>'
                f'{s.md(b["titel"], latein=True)}</div><div class="fig">{svg}</div>{unten}</figure>')
    if t in ("formel", "rechenweg"):  # 4.0: wie im Kachelsatz, mit Zwischenüberschrift; Rechenweg mit Vermerk der Rechenprobe
        return f'<div class="sp {t}-block"{db}>{satz.baustein_html(b, s.kx)}</div>'
    if t == "latinum":
        n = len(s.reg)
        s.reg.append(("latein", b["lat"], f"rg-{n}"))
        return (f'<div class="sp box latinum"{db}><div class="lbl">Latinum</div><span class="lat" id="rg-{n}">{s.md(b["lat"], latein=True)}</span><span class="de">{s.md(b["de"])}</span>'
                f'<span class="stelle">{s.md(b["stelle"], latein=True)}</span></div>')
    if t == "steckbrief":
        d, m, h = s.farbe(b["rolle"], kfarbe)
        zeilen = "".join(f'<dt>{s.md(a, latein=True)}</dt><dd>{s.md(v)}</dd>' for a, v in b["felder"])
        return (f'<div class="sp steckbrief"{db} style="--d:{d};--h:{h}"><div class="lbl">Steckbrief <span class="sb-titel">{s.md(b["titel"], latein=True)}</span></div>'
                f'<dl>{zeilen}</dl></div>')
    if t == "glossar":
        # Latinum-Einträge des Werks nur auf ausdrücklichen Wunsch (latein: true); sonst zeigt das Glossar nur seine Einträge
        latein = [(x["lat"], f'{x["de"]} ({x["stelle"]})') for _, _, _, bl in listen(s.werk) for x in bl if x["typ"] == "latinum"] if b.get("latein") else []
        zeilen = "".join(f'<tr><td class="gb">{s.md(a, latein=True)}</td><td class="ge">{s.md(v)}</td></tr>' for a, v in b["eintraege"])
        zeilen += "".join(f'<tr class="lat"><td class="gb"><em>{s.md(a, latein=True)}</em></td><td class="ge">{s.md(v)}</td></tr>' for a, v in latein)
        return f'<div class="sp glossar"{db}><div class="lbl">{s.md(b["titel"], latein=True)}</div><table>{zeilen}</table></div>'
    if t == "akteure":
        n = s.nummer[("tab", b["id"])]
        zeilen = "".join(f'<tr><td class="begriff"><span class="rpunkt" style="--d:{s.farbe(p["rolle"])[0]}"></span>{esc(p["name"])}</td><td class="text">{s.md(p["funktion"])}</td>'
                         f'<td class="stichworte" style="--d:{s.farbe(p["rolle"])[0]}">{esc(s.rollen.get(p["rolle"], {}).get("name", ""))}</td></tr>'
                         for p in s.personen)
        return (f'<div class="tab akteure teilbar" id="tab-{b["id"]}" data-nr="{n}"{db}><div class="schema-titel"><span class="abb">Tab{NBSP}{n}</span>'
                f'{s.md(b["titel"], latein=True)}</div><table class="t akteure"><colgroup><col class="c0"><col><col class="c2"></colgroup>'
                f'<thead><tr>{"".join(f"<th>{esc(h)}</th>" for h in b.get("kopf", ["Person", "Funktion", "Zuordnung"]))}</tr></thead><tbody>{zeilen}</tbody></table></div>')
    if t == "fallbeispiel":
        return (f'<div class="fallbeispiel einbettung"{db}><div class="fb-kopf">Fallbeispiel</div>'
                f'<div class="fb-teil"><div class="fb-lbl">Sachverhalt</div><div class="sv"><p>{s.md(b["sachverhalt"])}</p></div></div>'
                f'<div class="fb-teil fb-lo"><div class="fb-lbl">Lösungsskizze</div><p>{s.md(b["loesung"])}</p></div></div>')
    raise ValueError(t)


def stand_text(werk):
    j, m = werk["meta"]["stand"].split("-")
    return f'{werk["modul"].get("stand_art", "Stand")} {MONATE[int(m) - 1]} {j}'


def ordnung(k, plan):
    """Lesefolge eines Kapitels nach dem Plan der Korrekturläufe: [(Eigentümer, Kennung, Block)].
    Gleitobjekte rücken je Schritt hinter den folgenden Textblock, auch über eine Abschnittsgrenze hinweg;
    der Eigentümer (in wessen Abschnitt der Block gesetzt wird) ist dann der des Vorgängers."""
    folge = []
    for schl, _, a, bl in listen({"kapitel": [k]}):
        folge += [[schl, f"{schl}~{i}", b] for i, b in enumerate(bl)]
    for bid, schritte in plan["gleiten"].items():
        pos = next((i for i, x in enumerate(folge) if x[1] == bid), None)
        if pos is None:
            continue
        e = folge.pop(pos)
        ziel = min(pos + schritte, len(folge))
        folge.insert(ziel, e)
        if ziel:
            e[0] = folge[ziel - 1][0]
    return folge


def gleiten_moeglich(k, plan, bid):
    """Ein weiterer Schritt ist erlaubt, wenn danach ein Textblock folgt (keine Einbettung überholen, Nummern bleiben in Folge)."""
    folge = ordnung(k, plan)
    pos = next((i for i, x in enumerate(folge) if x[1] == bid), None)
    if pos is None or pos + 1 >= len(folge):
        return False
    eigen, naechster = folge[pos][2]["typ"], folge[pos + 1][2]["typ"]
    reihe = lambda t: "abb" if t == "abbildung" else ("tab" if t in ("tabelle", "akteure") else t)
    if naechster == "zitat" or (naechster in EINBETTUNG and (reihe(eigen) == reihe(naechster) or "fallbeispiel" in (eigen, naechster))):
        return False  # gleiche Nummernreihe bleibt in Folge; Fälle und Zitate werden nicht überholt
    heimat, naechst = bid.rsplit("~", 1)[0], folge[pos + 1][0]
    if naechst.endswith("S") and naechst != heimat:  # nie in den Kapitelabschluss hinein
        return False
    if folge[pos + 1][2].get("text", "").rstrip().endswith(":"):  # nie zwischen Ankündigung und Aufzählung
        return False
    if folge[pos][2]["typ"] == "fallbeispiel" and naechst != heimat:  # Fälle bleiben in ihrem Abschnitt
        return False
    if naechst != heimat:  # höchstens in den unmittelbar folgenden Abschnitt
        reihe = [schl for schl, *_ in listen({"kapitel": [k]})]
        return reihe.index(naechst) == reihe.index(heimat) + 1
    return True


# ══ Entwurf 6: Titelei, Provinzen, Repetitorium und Anhang in der Form der bisherigen Terrae ═══════════════
# Markup und Klassen folgen skript.py (Kit 3.7.1); die Satzvorlage skript.css wird mitgeladen.
GEN = (("LF", "Klausurfallen im Überblick"), ("LQ", "Quellenkritik"), ("LV", "Lexicon"), ("LS", "Selbsttest"), ("LA", "Änderungsprotokoll"))


def daumenreihe(werk, mit_etikett=False, oben=28):
    prov = werk["meta"].get("provinzen", [])
    h = min(30, (297 - oben - 30) / max(1, len(prov)) - 2.5)
    return "".join(
        f'<div class="daumen" style="--p:{FARBEN[p["farbe"]][0]};top:{oben + i * (h + 2.5):.1f}mm;height:{h:.1f}mm"><span>{esc(p["nr"])}</span>'
        + (f'<em><b>Provinz {esc(p["nr"])}</b>{esc(p["name_de"])}</em>' if mit_etikett else "") + "</div>" for i, p in enumerate(prov))


TITELSEITEN = ("band", "einband", "karte", "klassisch", "studienbuch", "grundriss", "handbuch", "kurzlehrbuch", "leinen", "halbleinen", "umschlag", "relief", "relief-halbleinen", "relief-umschlag", "band-relief", "band-bezug", "band-rahmen")


def titelseite(werk, s=None):
    """Titelseite nach meta.titelseite, Standard „band-relief“ (bisherige Titelseite mit Relief im Kopfband und Register im Fluss);
    „band“ (Kit 3.7: Band mit Reihe und Autor, Titel auf Pergament, Register mit Daumen),
    „einband“ (Leineneinband mit Goldrahmen), „karte“ (Wissenslandkarte der Provinzen), „klassisch“ (Titelblatt, mittig)."""
    m = werk["meta"]
    art = m.get("titelseite", "band-relief")  # Standard seit Entwurf 13 (Wahl des Autors); „band“ ist die Fassung von Kit 3.7
    if art == "studienbuch":
        return titel_studienbuch(werk, s)
    if art != "band":
        return TITEL_ARTEN[art](werk)
    lv = f'<div class="tp-lv">{esc(satz.ohne_kursnummer(m["lehrveranstaltung"]))}</div>' if m.get("lehrveranstaltung") else ""
    return (f'<section class="titelseite schema-{m.get("farbschema", "nacht")}"><div class="tp-band"><div class="tp-reihe">{esc(m.get("reihe", "Lernskripten zur Prüfungsvorbereitung"))}</div>'
            f'<div class="tp-autor">Oliver Bedernik</div></div><div class="tp-mitte"><h1 class="tp-titel">{esc(m["titel"])}</h1>'
            f'<div class="tp-unter">{esc(m["untertitel"])}</div>{lv}<div class="tp-linie"></div>'
            f'<div class="tp-ausgabe">Version {esc(m["version"])} · {stand_text(werk)}</div></div>'
            f'{daumenreihe(werk, True, 150)}<div class="tp-fuss"><span>{esc(m.get("ort", "Wien"))} {m["stand"][:4]}</span>'
            + ('<span class="tp-probe">Probesatz</span>' if m.get("probesatz") else "") + '</div>'
            f'<div class="deckvermerk">{VERMERK}</div></section>')


def _tp_teile(werk):
    """Gemeinsame Bausteine der Titelseiten: Reihe, Lehrveranstaltung, Ausgabe, Ort und Jahr, Probesatzvermerk, Provinzen im Band."""
    m = werk["meta"]
    lv = esc(satz.ohne_kursnummer(m["lehrveranstaltung"])) if m.get("lehrveranstaltung") else ""
    imband = {k["code"] for k in werk["kapitel"]} | ({"L"} if werk.get("repetitorium") else set())
    return {"reihe": esc(m.get("reihe", "Lernskripten zur Prüfungsvorbereitung")), "lv": lv,
            "ausgabe": f'Version {esc(m["version"])} · {stand_text(werk)}', "ort": f'{esc(m.get("ort", "Wien"))} {m["stand"][:4]}',
            "probe": '<span class="tp-probe">Probesatz</span>' if m.get("probesatz") else "",
            "prov": m.get("provinzen", []), "imband": imband}


def _tp_leiste(t, klasse="tp-leiste"):
    """Provinzfarben als Leiste mit römischer Ziffer; Provinzen außerhalb des Bandes blass."""
    return f'<div class="{klasse}">' + "".join(
        f'<span class="{"" if p["code"] in t["imband"] else "aus"}" style="--d:{FARBEN[p["farbe"]][0]}"><b>{esc(p["nr"])}</b></span>' for p in t["prov"]) + "</div>"


def titel_einband(werk):
    m, t = werk["meta"], _tp_teile(werk)
    return (f'<section class="titelseite tv-einband schema-{m.get("farbschema", "nacht")}"><div class="te-rahmen"></div><div class="te-rahmen innen"></div>'
            f'<div class="te-reihe">{t["reihe"]}</div>'
            f'<div class="te-mitte"><h1 class="tp-titel">{esc(m["titel"])}</h1><div class="te-zier"><i></i><b></b><i></i></div>'
            f'<div class="tp-unter">{esc(m["untertitel"])}</div>' + (f'<div class="tp-lv">{t["lv"]}</div>' if t["lv"] else "") + '</div>'
            f'<div class="te-autor">Oliver Bedernik</div>'
            f'<div class="te-fuss">{_tp_leiste(t)}<div class="te-ort">{t["ort"]}</div><div class="te-ausgabe">{t["ausgabe"]}{(" · " + t["probe"]) if t["probe"] else ""}</div></div>'
            f'<div class="deckvermerk">{VERMERK}</div></section>')


def titel_karte(werk):
    m, t = werk["meta"], _tp_teile(werk)
    abschnitte = {k["code"]: [a["code"] for a in k["abschnitte"]] for k in werk["kapitel"]}
    if werk.get("repetitorium"):
        abschnitte["L"] = [c for c, _ in GEN]
    kacheln = []
    for p in t["prov"]:
        d, _, hell = FARBEN[p["farbe"]]
        chips = "".join(f'<i>{esc(c)}</i>' for c in abschnitte.get(p["code"], []))
        kacheln.append(f'<div class="tk-prov{"" if p["code"] in t["imband"] else " aus"}" style="--d:{d};--h:{hell}">'
                       f'<div class="tk-nr">{esc(p["nr"])}</div><div class="tk-name">{esc(p["name_de"])}</div>'
                       + (f'<div class="tk-chips">{chips}</div>' if chips else "") + '</div>')
    return (f'<section class="titelseite tv-karte schema-{m.get("farbschema", "nacht")}">'
            f'<div class="tk-kopf"><span>{t["reihe"]}</span><span>Oliver Bedernik</span></div>'
            f'<div class="tk-titel"><h1 class="tp-titel">{esc(m["titel"])}</h1><div class="tp-unter">{esc(m["untertitel"])}</div>'
            + (f'<div class="tp-lv">{t["lv"]}</div>' if t["lv"] else "") + '</div>'
            f'<div class="tk-karte"><div class="tk-legende">Die Provinzen dieser Terra{" · farbig: in diesem Band" if len(t["imband"]) < len(t["prov"]) else ""}</div>'
            f'<div class="tk-raster">{"".join(kacheln)}</div></div>'
            f'<div class="tp-fuss"><span>{t["ort"]}</span><span class="tk-ausgabe">{t["ausgabe"]}</span>{t["probe"]}</div>'
            f'<div class="deckvermerk">{VERMERK}</div></section>')


def titel_klassisch(werk):
    m, t = werk["meta"], _tp_teile(werk)
    return (f'<section class="titelseite tv-klassisch schema-{m.get("farbschema", "nacht")}">'
            f'<div class="tc-reihe">{t["reihe"]}</div><div class="tc-doppellinie"></div>'
            f'<div class="tc-mitte"><h1 class="tp-titel">{esc(m["titel"])}</h1><div class="tp-unter">{esc(m["untertitel"])}</div>'
            f'<div class="te-zier"><i></i><b></b><i></i></div><div class="tc-von">von</div><div class="tc-autor">Oliver Bedernik</div>'
            + (f'<div class="tp-lv">{t["lv"]}</div>' if t["lv"] else "") + '</div>'
            f'<div class="tc-fuss"><div class="tc-ort">{t["ort"]}</div><div class="te-ausgabe">{t["ausgabe"]}</div>{t["probe"]}</div>'
            f'{_tp_leiste(t, "tc-leiste")}<div class="deckvermerk">{VERMERK}</div></section>')


# Entwurf 13, zweite Runde: Gattungen des Lehr- und Fachbuchs (allgemeine Formen, keine Verlagsausstattung nachgebildet)
def _tp_band_farbe(werk):
    """Provinzfarbe, wenn der Band genau eine Provinz enthält, sonst None (dann gilt das Farbschema)."""
    if len(werk["kapitel"]) == 1:
        return FARBEN[KAPITELFARBE.get(werk["kapitel"][0]["code"], "petrol")][0]
    return None


def _tp_aus_dem_inhalt(werk):
    """„Aus dem Inhalt“: die Abschnitte des Bandes mit Code, bei großen Bänden die Provinzen."""
    abschnitte = [(a["code"], a["titel"]) for k in werk["kapitel"] for a in k["abschnitte"]]
    if len(abschnitte) > 10:
        abschnitte = [(k["code"], k["name_de"]) for k in werk["kapitel"]]
    if werk.get("repetitorium"):
        abschnitte.append(("L", "Repetitorium: Klausurfallen, Lexicon, Selbsttest"))
    return "".join(f'<li><b>{esc(c)}</b><span>{esc(t)}</span></li>' for c, t in abschnitte)


def _tp_umschlagbild(werk, s):
    """Umschlagbild aus dem eigenen Werk: die erste Diagramm-Abbildung, Kennungen umbenannt (sonst doppelt im Dokument)."""
    if s is None:
        return ""
    for _, _, _, bl in listen(werk):
        for b in bl:
            if b["typ"] == "abbildung" and b.get("variante") == "diagramm":
                svg = diagramm.Diagramm(b, {**s.rollen, "kapitel": {"name": "Kapitel", "farbe": "petrol"}}).svg()
                svg = re.sub(r'id="([^"]+)"', r'id="tp-\1"', svg).replace("url(#", "url(#tp-")
                return f'<div class="ts-bild" aria-hidden="true">{svg}</div>'
    return ""


def titel_studienbuch(werk, s=None):
    """Studienbuch: Autor über dem Titel, Titel in kräftiger Grotesk, Umschlagbild aus dem Werk, Reihenband, Störer mit dem Stand."""
    m, t = werk["meta"], _tp_teile(werk)
    staerke = ("Klausurfallen", "Lexicon", "Selbsttest") if werk.get("repetitorium") else ()
    return (f'<section class="titelseite tv-studienbuch schema-{m.get("farbschema", "nacht")}">'
            f'<div class="ts-autor">Oliver Bedernik</div><h1 class="ts-titel">{esc(m["titel"])}</h1><div class="ts-unter">{esc(m["untertitel"])}</div>'
            f'{_tp_umschlagbild(werk, s)}'
            f'<div class="ts-reihe"><span>{t["reihe"]}</span><span class="ts-lv">{t["lv"]}</span></div>'
            f'<div class="ts-stoerer"><small>Rechtsstand</small><b>{esc(stand_text(werk).replace("Rechtsstand ", ""))}</b></div>'
            + (f'<ul class="ts-mit">' + "".join(f"<li>{x}</li>" for x in staerke) + '</ul>' if staerke else "")
            + f'<div class="ts-fuss"><span>{t["ort"]}</span><span>Version {esc(m["version"])}</span>{t["probe"]}</div>'
            f'<div class="deckvermerk">{VERMERK}</div></section>')


def titel_grundriss(werk):
    """Grundriss: Rücken in der Schemafarbe mit senkrechtem Reihentitel, große Provinzziffer, sachliches Raster am Fuß."""
    m, t = werk["meta"], _tp_teile(werk)
    farbe = _tp_band_farbe(werk)
    ziffer = f'<div class="tg-ziffer" style="color:{farbe}">{esc(werk["kapitel"][0]["nr"])}</div>' if farbe else ""
    stand = esc(stand_text(werk))
    return (f'<section class="titelseite tv-grundriss schema-{m.get("farbschema", "nacht")}"><div class="tg-ruecken"><span>{t["reihe"]}</span></div>'
            f'<div class="tg-satz">{ziffer}<h1 class="tp-titel">{esc(m["titel"])}</h1><div class="tp-unter">{esc(m["untertitel"])}</div>'
            f'<div class="tg-autor">Oliver Bedernik</div></div>'
            f'<div class="tg-raster"><div><small>Lehrveranstaltung</small>{t["lv"] or "·"}</div><div><small>Stand</small>{stand}</div>'
            f'<div><small>Ausgabe</small>Version {esc(m["version"])} · {t["ort"]}</div></div>'
            + (f'<div class="tg-probe">{t["probe"]}</div>' if t["probe"] else "")
            + f'<div class="deckvermerk">{VERMERK}</div></section>')


def titel_handbuch(werk):
    """Handbuch: Leinen in der Schemafarbe, aufgesetztes Titelschild mit Doppelrahmen, Reihe und Ort am Fuß."""
    m, t = werk["meta"], _tp_teile(werk)
    return (f'<section class="titelseite tv-handbuch schema-{m.get("farbschema", "nacht")}">'
            f'<div class="th-schild"><div class="th-autor">Oliver Bedernik</div><h1 class="tp-titel">{esc(m["titel"])}</h1>'
            f'<div class="te-zier"><i></i><b></b><i></i></div><div class="tp-unter">{esc(m["untertitel"])}</div>'
            f'<div class="th-ausgabe">Version {esc(m["version"])} · {esc(stand_text(werk))}</div></div>'
            f'<div class="th-fuss"><div class="th-reihe">{t["reihe"]}</div><div class="th-ort">{t["ort"]}</div>{t["probe"]}</div>'
            f'<div class="deckvermerk">{VERMERK}</div></section>')


def titel_kurzlehrbuch(werk):
    """Kurzlehrbuch: oben Farbfeld (Provinzfarbe des Bandes) mit Titel in Grotesk, unten „Aus dem Inhalt“ mit den Abschnitten."""
    m, t = werk["meta"], _tp_teile(werk)
    farbe = _tp_band_farbe(werk) or "var(--tp-band)"
    return (f'<section class="titelseite tv-kurzlehrbuch schema-{m.get("farbschema", "nacht")}"><div class="tl-feld" style="background:{farbe}">'
            f'<div class="tl-reihe">{t["reihe"]}</div>' + (f'<div class="tl-ziffer">{esc(werk["kapitel"][0]["nr"])}</div>' if _tp_band_farbe(werk) else "")
            + f'<div class="tl-autor">Oliver Bedernik</div><h1 class="ts-titel">{esc(m["titel"])}</h1>'
            f'<div class="tl-unter">{esc(m["untertitel"])}</div></div>'
            f'<div class="tl-inhalt" style="--d:{farbe}"><div class="tl-lbl">Aus dem Inhalt</div><ul>{_tp_aus_dem_inhalt(werk)}</ul></div>'
            f'<div class="tl-fuss"><span>{t["ort"]}</span><span>{t["ausgabe"]}</span>{t["probe"]}</div>'
            f'<div class="deckvermerk">{VERMERK}</div></section>')


# Entwurf 13, dritte Runde: Umschläge wie beim hochwertigen gebundenen Fachbuch. Grundsätze: nur Angaben zum Werk (Autor,
# Titel, Untertitel, Reihe, Stand), nichts aus dem Stoff (keine Provinzfarben, Ziffern, Bilder, Inhaltslisten), keine Zierformen;
# eine Hausschrift in wenigen Größen auf einem festen Raster. Erkennungszeichen der Reihe: „Terra“ kursiv, der Rest aufrecht.
def _tp_werktitel(titel, zeilen=False):
    w = esc(titel).split(" ", 1)
    kopf = f'<em>{w[0]}</em>' if w[0] == "Terra" else w[0]
    if len(w) == 1:
        return kopf
    rest = w[1].split(" ") if zeilen else [w[1]]
    return kopf + "".join((f'<span class="z">{x}</span>' if zeilen else f" {x}") for x in rest)


def _tp_angaben(werk):
    m = werk["meta"]
    return {"stand": esc(stand_text(werk).replace("Rechtsstand", "Stand")), "reihe": esc(m.get("reihe", "Lernskripten zur Prüfungsvorbereitung")),
            "ort": f'{esc(m.get("ort", "Wien"))} {m["stand"][:4]}', "probe": '<span class="tu-probe">Probesatz</span>' if m.get("probesatz") else ""}


def titel_leinen(werk):
    """Ganzleinen mit Folienprägung: Tuch in der Schemafarbe, Schrift in Goldfolie, Titel tief gesetzt."""
    m, a = werk["meta"], _tp_angaben(werk)
    return (f'<section class="titelseite tv-leinen schema-{m.get("farbschema", "nacht")}">'
            f'<div class="tu-autor">Oliver Bedernik</div>'
            f'<div class="tu-block"><h1 class="tu-titel">{_tp_werktitel(m["titel"])}</h1><div class="tu-unter">{esc(m["untertitel"])}</div></div>'
            f'<div class="tu-fuss"><span>{a["reihe"]}</span><span>{a["stand"]}{" · " + a["probe"] if a["probe"] else ""}</span></div>'
            f'<div class="deckvermerk">{VERMERK}</div></section>')


def titel_halbleinen(werk):
    """Halbleinen: Tuch am Rücken, Bezugspapier auf dem Deckel, Goldlinie an der Kante; Titel auf dem Papier."""
    m, a = werk["meta"], _tp_angaben(werk)
    return (f'<section class="titelseite tv-halbleinen schema-{m.get("farbschema", "nacht")}"><div class="tu-tuch"><div class="tu-reihe">{a["reihe"]}</div></div>'
            f'<div class="tu-deckel"><div class="tu-autor">Oliver Bedernik</div><h1 class="tu-titel">{_tp_werktitel(m["titel"], True)}</h1>'
            f'<div class="tu-unter">{esc(m["untertitel"])}</div></div>'
            f'<div class="tu-fuss"><span>{a["ort"]}</span><span>{a["stand"]}{" · " + a["probe"] if a["probe"] else ""}</span></div>'
            f'<div class="deckvermerk">{VERMERK}</div></section>')


def titel_umschlag(werk):
    """Schutzumschlag, typografisch: heller Grund, Titel groß und linksbündig Wort für Wort, darunter eine Grundlinie mit Autor und Reihe."""
    m, a = werk["meta"], _tp_angaben(werk)
    return (f'<section class="titelseite tv-umschlag schema-{m.get("farbschema", "nacht")}"><div class="tu-kante"></div>'
            f'<h1 class="tu-titel">{_tp_werktitel(m["titel"], True)}</h1><div class="tu-unter">{esc(m["untertitel"])}</div>'
            f'<div class="tu-linie"></div><div class="tu-autor">Oliver Bedernik</div>'
            f'<div class="tu-rechts"><span>{a["reihe"]}</span><span>{a["stand"]}</span>{a["probe"]}</div>'
            f'<div class="deckvermerk">{VERMERK}</div></section>')


# Entwurf 13, vierte Runde: reicher ausgestattet, aber ohne Stoffbezug. Erkennungszeichen der Reihe ist ein Relief aus
# Höhenlinien (relief.py), dessen Gelände allein aus dem Titel folgt: „Terra“ als Landkarte, für jeden Themenkorb gleich passend.
def titel_relief(werk):
    """Ganzleinen mit Reliefplatte: oben das Relief in Goldton auf Tuch, darunter Goldfileten und der Titel auf glattem Tuch."""
    m, a = werk["meta"], _tp_angaben(werk)
    return (f'<section class="titelseite tv-relief schema-{m.get("farbschema", "nacht")}"><div class="tr-platte">{relief.svg(m["titel"])}</div>'
            f'<div class="tr-fileten"></div>'
            f'<div class="tr-unten"><div class="tr-autor">Oliver Bedernik</div><h1 class="tu-titel">{_tp_werktitel(m["titel"])}</h1>'
            f'<div class="tu-unter">{esc(m["untertitel"])}</div></div>'
            f'<div class="tr-fuss"><span>{a["reihe"]}</span><span>{a["stand"]}{" · " + a["probe"] if a["probe"] else ""}</span></div>'
            f'<div class="deckvermerk">{VERMERK}</div></section>')


def titel_relief_halbleinen(werk):
    """Halbleinen: Tuchrücken mit Goldfileten, Bezugspapier mit dem Relief Ton in Ton, aufgesetztes Titelschild aus Tuch."""
    m, a = werk["meta"], _tp_angaben(werk)
    return (f'<section class="titelseite tv-relief-halbleinen schema-{m.get("farbschema", "nacht")}">'
            f'<div class="trh-bezug">{relief.svg(m["titel"])}</div><div class="trh-tuch"><div class="trh-reihe">{a["reihe"]}</div></div>'
            f'<div class="trh-fileten"></div>'
            f'<div class="trh-schild"><div class="tr-autor">Oliver Bedernik</div><h1 class="tu-titel">{_tp_werktitel(m["titel"], True)}</h1>'
            f'<div class="tu-unter">{esc(m["untertitel"])}</div></div>'
            f'<div class="trh-fuss"><span>{a["ort"]}</span><span>{a["stand"]}{" · " + a["probe"] if a["probe"] else ""}</span></div>'
            f'<div class="deckvermerk">{VERMERK}</div></section>')


def titel_relief_umschlag(werk):
    """Schutzumschlag: oben das Relief in der Schemafarbe als Umschlagbild, darunter Titel und Autor, am Fuß ein Band mit der Reihe."""
    m, a = werk["meta"], _tp_angaben(werk)
    return (f'<section class="titelseite tv-relief-umschlag schema-{m.get("farbschema", "nacht")}"><div class="tru-bild">{relief.svg(m["titel"])}</div>'
            f'<div class="tru-text"><div class="tr-autor">Oliver Bedernik</div><h1 class="tu-titel">{_tp_werktitel(m["titel"])}</h1>'
            f'<div class="tu-unter">{esc(m["untertitel"])}</div></div>'
            f'<div class="tru-band"><span>{a["reihe"]}</span><span>{a["stand"]}{" · " + a["probe"] if a["probe"] else ""}</span></div>'
            f'<div class="deckvermerk">{VERMERK}</div></section>')


# Entwurf 13, fünfte Runde: die bisherige Titelseite (band) veredelt. Aufbau, Schriftgrößen und Angaben bleiben; dazu Relief,
# Goldfileten und die Daumen als farbiger Schnitt. Die Beschriftung der Daumen mit den Provinzen entfällt (Abgrenzung vom Stoff).
def titel_register(werk):
    """Register der Titelseite: je Provinz Beschriftung und Reiter in einer Zeile, im Fluss unter dem Titelblock. So kann eine
    Beschriftung weder den Titelblock noch eine andere Beschriftung oder den Fuß schneiden; vorhandene Provinzen sind verlinkt."""
    da = {k["code"] for k in werk["kapitel"]} | ({"L"} if werk.get("repetitorium") else set())
    zeilen = []
    for p in werk["meta"].get("provinzen", []):
        inhalt = (f'<span class="tb-etikett"><b>Provinz {esc(p["nr"])}</b><span>{esc(p["name_de"])}</span></span>'
                  f'<span class="tb-daumen">{esc(p["nr"])}</span>')
        zeilen.append(f'<a class="tb-reiter" href="#p-{p["code"]}" style="--p:{FARBEN[p["farbe"]][0]}">{inhalt}</a>' if p["code"] in da
                      else f'<div class="tb-reiter" style="--p:{FARBEN[p["farbe"]][0]}">{inhalt}</div>')
    return f'<nav class="tb-register" aria-label="Provinzen">{"".join(zeilen)}</nav>'


TITEL_STILE = ("terra-kursiv", "band-hoch", "band-schmal", "band-unten", "relief-dicht", "relief-papier", "papier-weiss", "fussband",
               "relief-blind", "relief-weit", "relief-kraeftig", "papier-bronze", "papier-deutlich", "papier-praegung", "papier-zaehl", "ohne-fileten", "papier-hell")
TITEL_STIL_STANDARD = ["relief-papier", "papier-praegung"]  # Wahl des Autors (Entwurf 13): 5f, Pergament wie bisher


def titel_band_veredelt(werk, art):
    """Bisherige Titelseite veredelt: Kopfband (mit Relief oder glatt) nur mit der Reihe, Goldfileten, Titelblock wie bisher,
    darunter das Register der Provinzen im Fluss; der Autor steht im Urhebervermerk, im Impressum und in den PDF-Metadaten."""
    m = werk["meta"]
    stil = m.get("titel_stil", TITEL_STIL_STANDARD)  # Abwandlungen (Entwurf 13): je Stichwort eine Klasse tvx-…, siehe TITEL_STILE
    if "fussband" in stil:
        art = "band-rahmen" if art == "band-relief" else art
    lv = f'<div class="tp-lv">{esc(satz.ohne_kursnummer(m["lehrveranstaltung"]))}</div>' if m.get("lehrveranstaltung") else ""
    stufen = 46 if "relief-dicht" in stil else 30
    # relief-weit: dasselbe Gelände auf kleinerer Fläche gerechnet und auf die Seite vergrößert, also breitere Formen und kräftigere Linien
    mass = {"breite": 140, "hoehe": 198, "staerke": 0.11, "zaehl": 0.24} if "relief-weit" in stil else {}
    rel = f'<div class="tb-relief">{relief.svg(m["titel"], stufen=stufen, **mass)}</div>'
    probe = '<span class="tp-probe">Probesatz</span>' if m.get("probesatz") else ""
    ort = f'<span>{esc(m.get("ort", "Wien"))} {m["stand"][:4]}</span>'
    titel = _tp_werktitel(m["titel"]) if "terra-kursiv" in stil else esc(m["titel"])
    zusatz = "".join(f" tvx-{x}" for x in stil)
    return (f'<section class="titelseite tv-{art}{zusatz} schema-{m.get("farbschema", "nacht")}">'
            + (f'<div class="tb-bezug">{relief.svg(m["titel"], stufen=stufen, **mass)}</div>' if art == "band-bezug" or "relief-papier" in stil else "")
            + f'<div class="tp-band">{rel if art != "band-bezug" else ""}<div class="tp-reihe">{esc(m.get("reihe", "Lernskripten zur Prüfungsvorbereitung"))}</div></div>'
            f'<div class="tb-fileten"></div>'
            f'<div class="tb-koerper"><div class="tp-mitte"><h1 class="tp-titel">{titel}</h1><div class="tp-unter">{esc(m["untertitel"])}</div>{lv}'
            f'<div class="tp-linie"></div><div class="tp-ausgabe">Version {esc(m["version"])} · {stand_text(werk)}</div></div>'
            f'{titel_register(werk)}' + ("" if art == "band-rahmen" else f'<div class="tp-fuss">{ort}{probe}</div>') + '</div>'
            + (f'<div class="tb-fileten unten"></div><div class="tb-fuss">{ort}{probe}</div>' if art == "band-rahmen" else "")
            + f'<div class="deckvermerk">{VERMERK}</div></section>')


TITEL_ARTEN = {"band-relief": lambda w: titel_band_veredelt(w, "band-relief"), "band-bezug": lambda w: titel_band_veredelt(w, "band-bezug"),
               "band-rahmen": lambda w: titel_band_veredelt(w, "band-rahmen"), "relief": titel_relief, "relief-halbleinen": titel_relief_halbleinen, "relief-umschlag": titel_relief_umschlag, "leinen": titel_leinen, "halbleinen": titel_halbleinen, "umschlag": titel_umschlag, "einband": titel_einband, "karte": titel_karte, "klassisch": titel_klassisch, "studienbuch": titel_studienbuch,
               "grundriss": titel_grundriss, "handbuch": titel_handbuch, "kurzlehrbuch": titel_kurzlehrbuch}


def impressum(werk):
    """Impressum wie satz.impressum: Motto als Epigraph, darunter Werkzeile, Haftung, Zitiervorschlag, Satz, Copyright."""
    m, mo, mt = werk["meta"], werk["modul"], werk["motto"]
    erste = werk["kapitel"][0]["abschnitte"][0]["code"]
    haftung = satz.HAFTUNG.get(mo["domaene"], "")
    zeilen = [
        f'<b>{esc(m["titel"])}</b>. {esc(m["untertitel"])}. Version {esc(m["version"])}, {stand_text(werk)}.'
        + (f' Zur Lehrveranstaltung {esc(satz.ohne_kursnummer(m["lehrveranstaltung"]))}.' if m.get("lehrveranstaltung") else ""),
        f'Alle Angaben ohne Gewähr. Das Skript dient dem Studium{haftung}.',
        f'<b>Zitiervorschlag:</b> <i>Bedernik</i>, {esc(m["titel"])} ({m["stand"][:4]}) Abschnitt {erste}.',
        'Quellen und Entstehung: siehe Quellenverzeichnis, Seite <a class="sz" href="#t-quellen"></a>.',
        f'Satz: Terra-Kit {satz.VERSION} (Buchsatz); Schriften Cormorant Garamond, Spectral und Alegreya Sans.',
        f'<b>© Oliver Bedernik, {esc(m.get("ort", "Wien"))} {m["stand"][:4]}.</b> Alle Rechte vorbehalten.']
    return (f'<section class="titelei-seite impressum-seite" id="t-impressum"><div class="epigraph"><div class="ep-lat">{satz.md(mt["lat"], latein=True)}</div>'
            f'<div class="ep-de">{satz.md(mt["de"])}</div><div class="ep-st">{satz.md(mt["stelle"], latein=True)}</div></div>'
            '<div class="impressum">' + "".join(f"<p>{z}</p>" for z in zeilen) + "</div></section>")


def _toczeile(ziel, text, code=""):
    c = f'<td class="c">{code}</td>' if code else ""
    return f'<tr>{c}<td class="t"><a href="#{ziel}">{text}</a></td><td class="n"><a class="sz" href="#{ziel}"></a></td></tr>'


def inhalt(werk, s):
    """Inhalt wie satz.inhaltsverzeichnis: zweispaltig, Titelei, Provinzkarten mit Codes, Anhang; alle Daumen am Rand."""
    karten = [f'<div class="tocp tocv farbe-grau"><table>{_toczeile("t-gebrauch", "Zum Gebrauch")}{_toczeile("t-abk", "Abkürzungen und Zitierweise")}</table></div>']
    hoehen = [2 * 6.6 + 4.6]
    for k in werk["kapitel"]:
        rows = "".join(_toczeile(f'k-{a["code"]}', s.md(a["titel"], latein=True) + (f'<span class="rs">{ziel()}</span>' if a.get("wichtig") else ""), a["code"])
                       for a in k["abschnitte"])
        if k.get("abschluss"):
            rows += _toczeile(f'k-{k["code"]}U', "Auf einen Blick", f'{k["code"]}·Ü')
        karten.append(f'<div class="tocp farbe-{KAPITELFARBE.get(k["code"], "petrol")}"><div class="k"><span class="pchip">{esc(k["nr"])} ({k["code"]})</span>'
                      f'<a class="pt" href="#p-{k["code"]}">{esc(k.get("name_lat", ""))}</a><div class="pd">{esc(k["name_de"])}</div>'
                      f'<span class="n"><a class="sz" href="#p-{k["code"]}"></a></span></div><table>{rows}</table></div>')
        hoehen.append(21 + 4.6 + _zeilen_mm([a["titel"] for a in k["abschnitte"]] + (["Auf einen Blick"] if k.get("abschluss") else []), 46, 6.3, 4.2))
    r = werk.get("repetitorium")
    if r:
        rows = "".join(_toczeile(f"k-{c}", t, f"L·{c[1]}") for c, t in GEN if gen_vorhanden(werk, c))
        karten.append(f'<div class="tocp farbe-tinte"><div class="k"><span class="pchip">{esc(r["nr"])} (L)</span>'
                      f'<a class="pt" href="#p-L">{esc(r["name_lat"])}</a><div class="pd">{esc(r["name_de"])}</div>'
                      f'<span class="n"><a class="sz" href="#p-L"></a></span></div><table>{rows}</table></div>')
        hoehen.append(21 + 4.6 + 6.3 * rows.count("<tr>"))
    karten.append('<div class="tocp tocv farbe-grau"><table>' + _toczeile("t-abbildungen", "Abbildungsverzeichnis")
                  + _toczeile("t-quellen", "Quellenverzeichnis") + _toczeile("t-register", "Sachregister") + "</table></div>")
    hoehen.append(3 * 6.6 + 4.6)
    return ('<section class="titelei-seite spalten-seite" id="t-inhalt"><div class="titelzeile"><div class="tz-ober">Titelei</div><h1 class="teil">Inhalt</h1>'
            '<div class="teil-unter">Jede Provinz beginnt auf einer neuen Seite und trägt ihre Farbe, auch im Daumenregister am Seitenrand. '
            'Codes und Seitenzahlen sind im PDF anklickbar; die Lesezeichenleiste bildet die Gliederung ab.</div></div>'
            + zweispaltig(karten, hoehen) + "</section>")


SPALTE_ERSTE, SPALTE_FOLGE = 224, 252  # nutzbare Spaltenhöhe in mm: erste Seite unter der Titelzeile, Folgeseiten (je mit Reserve)


def zweispaltig(teile, hoehen, erste=SPALTE_ERSTE, folge=SPALTE_FOLGE):
    """Zwei Spalten wie die Seitenart „spalten“ der Montage. Paged.js teilt ein Raster nicht spaltenweise; deshalb
    verteilt der Satz die unteilbaren Teile selbst: Spalte für Spalte, Seite für Seite, nach geschätzter Höhe in mm.
    Reicht die Schätzung nicht, meldet die Satzprüfung die geteilte Spalte."""
    spalten, i, n = [], 0, 0
    while i < len(teile):
        cap = erste if n < 2 else folge
        offen = sum(hoehen[i:])
        # erste Spalte einer Seite: reicht der Rest für diese Seite, werden beide Spalten ausgeglichen
        ziel = offen / 2 if (n % 2 == 0 and offen <= 2 * cap) else cap
        sp, rest = [], 0.0
        while i < len(teile) and (not sp or (rest + hoehen[i] <= cap and rest + hoehen[i] / 2 <= ziel)):
            sp.append(teile[i])
            rest += hoehen[i]
            i += 1
        spalten.append(sp)
        n += 1
    seiten = [spalten[i:i + 2] for i in range(0, len(spalten), 2)]
    return "".join(f'<div class="spalten-satz"{" data-folgeseite=\"ja\"" if i else ""}>' + "".join(f'<div class="spalte">{"".join(sp)}</div>' for sp in seite)
                   + "</div>" for i, seite in enumerate(seiten))


def _zeilen_mm(texte, breite_zeichen, zeile, umbruch):
    """Geschätzte Höhe einer Folge von Tabellenzeilen: einzeilig `zeile` mm, je weitere Zeile `umbruch` mm."""
    return sum(zeile + umbruch * (len(re.sub(r"<[^>]+>|[*_]", "", t)) // breite_zeichen) for t in texte)


def zum_gebrauch(werk, s):
    """Zum Gebrauch wie satz.zum_gebrauch: links Aufbau, Anatomie, Relevanz, Verweise, Belege, Daumenregister, Rechtsstand; rechts Bausteine."""
    k0 = werk["kapitel"][0]
    a0 = k0["abschnitte"][2] if len(k0["abschnitte"]) > 2 else k0["abschnitte"][0]
    n_ab = sum(len(k["abschnitte"]) for k in werk["kapitel"])
    n_prov = len(werk["kapitel"]) + (1 if werk.get("repetitorium") else 0)
    typen = {b["typ"] for _, _, _, bl in listen(werk) for b in bl}
    pills = "".join(f'<span class="rpill" style="--d:{FARBEN[r["farbe"]][0]};--h:{FARBEN[r["farbe"]][2]}">{esc(r["name"])}</span>' for r in s.rollen.values())
    links = (
        f'<h3>Aufbau</h3><p>Das Skript gliedert sich in <b>{n_prov} Provinzen</b> mit zusammen <b>{n_ab} Abschnitten</b>. '
        'Jeder Abschnitt entspricht einer Kachel der Wissenslandkarte und trägt deren Code; eine kurze Überleitung führt von einem Abschnitt zum nächsten. '
        'Innen folgt er dem Aufbau der Kacheln: Definition des zentralen Begriffs, Kerngehalt als Liste mit dem Fachbegriff als Vorspann, '
        'dann Abbildung, Kernsatz und Kästen. '
        'Die letzte Provinz (L) ist das <b>Repetitorium</b>: Klausurfallen, Quellenkritik, Lexicon und Selbsttest.</p>'
        f'<h3>Anatomie eines Abschnitts</h3><div class="anatomie farbe-{KAPITELFARBE.get(k0["code"], "petrol")}"><div class="an-kopf"><span class="an-code">{a0["code"]}</span>'
        f'<span class="an-titel">{s.md(a0["titel"], latein=True)} {ziel()}</span><span class="an-anker">{typo_esc(a0.get("anker", ""))}</span></div>'
        '<div class="an-leg"><span>Code</span><span>Titel und Schlüssel</span><span>Quellenanker</span></div></div>'
        f'<h3>Kerninhalt</h3><p>Der Schlüssel {ziel()} markiert Kerninhalte, also was nach den Hinweisen der Lehrveranstaltung sicher sitzen muss: '
        'am Abschnittskopf den ganzen Abschnitt, am linken Rand einen Absatz, Listenpunkt oder Kasten, wobei eine Leiste die ganze Stelle begleitet, '
        'im Titel eine Abbildung. Die Marke ist sparsam gesetzt und eine Einschätzung, keine Prüfungsauskunft; Unmarkiertes ist Stoff, nicht Beiwerk.</p>'
        f'<h3>Verweise</h3><p><a class="vw" href="#k-{a0["code"]}">{a0["code"]}</a> verweist auf einen Abschnitt dieses Skripts und ist anklickbar; '
        f'<span class="vw-ext">ADM{NBSP}D7</span> auf Kachel D7 einer anderen Terra, erkennbar an deren Sigle. Abb und Tab führen zur Grafik oder Tabelle.</p>'
        '<h3>Belege am Rand</h3><p>Die Fundstelle steht rechts neben der Zeile, in der die Aussage endet (<span class="rb-muster"><b>GKPS</b> Rz 9</span>); '
        'ein Klick führt zur Vollangabe im Quellenverzeichnis.</p>'
        '<h3>Daumenregister</h3><p>Am rechten Seitenrand markiert ein farbiger Reiter mit römischer Ziffer die Provinz. '
        'Die Farbe kehrt im Abschnittskopf, im Provinzkopf und im Inhaltsverzeichnis wieder.</p>'
        f'<h3>{esc(werk["modul"].get("stand_art", "Stand"))}</h3><p>Primärquelle ist {s.md(werk["modul"]["primaerquelle"])}. Maßgeblich ist der {stand_text(werk)}.</p>')
    proben = ['<div class="kernblock"><div class="lbl">Kernsatz</div><p class="kernsatz">Die Aussage, die man mitnehmen muss; die <b>fett gesetzten Begriffe</b> werden zu Anki-Lücken.</p></div>',
              '<div class="box klausurfalle"><div class="lbl">Cave!</div><b>Klausurfalle:</b> typischer Fehler, verwechselte Größe oder Frist, Regel ohne ihre Ausnahme. '
              'Im Skript heißt der Kasten nur „Cave!“; das Repetitorium sammelt alle unter L·F.</div>',
              '<div class="sp-probe"><div class="label">Definition</div><p class="zg-def">Der zentrale Begriff des Abschnitts, ausführlich erklärt.</p>'
              '<div class="label">Kerngehalt</div><ul class="kern"><li><b>Fachbegriff:</b> Erklärung in ein bis drei Sätzen.</li></ul></div>',
              '<div class="zg-paar"><div class="box merke"><div class="lbl">Merke</div>Was über den Abschnitt hinaus trägt.</div>'
              '<div class="box feinheit"><div class="lbl">Feinheit</div>Vertiefung für Fortgeschrittene.</div></div>']
    if "steckbrief" in typen:
        proben.append('<div class="steckbrief" style="--d:#854451;--h:#F8E6E8"><div class="lbl">Steckbrief</div>Datum, Fundstelle, Legitimation und Status eines Rechtstextes auf einen Blick.</div>')
    if "latinum" in typen:
        proben.append('<div class="box latinum"><div class="lbl">Latinum</div><span class="lat">Proverbium Latinum</span><span class="de">Übersetzung</span>'
                      '<span class="stelle">Quelle oder Stelle</span></div>')
    if "fallbeispiel" in typen:
        proben.append('<div class="fallbeispiel"><div class="fb-kopf">Fallbeispiel</div><div class="fb-teil"><div class="fb-lbl">Sachverhalt</div>'
                      '<div class="sv">Kurzer, eindeutig gefasster Fall.</div></div><div class="fb-teil fb-lo"><div class="fb-lbl">Lösungsskizze</div>Subsumtion in Schritten, mit Normzitat.</div></div>')
    if "merkband" in typen:
        proben.append('<p class="hinweis">Eine <b>Merkhilfe</b> fasst Reihenfolgen und Dreiheiten als Pfeilkette.</p>')
    proben.append('<p class="hinweis">Abbildungen und Tabellen sind fortlaufend nummeriert (Abb 3, Tab 1); das <b>Abbildungsverzeichnis</b> im Anhang sammelt sie mit Nachweis. '
                  'Anspruchsvolle Grafiken und Tabellen tragen unten eine <b>Lesehilfe</b>.</p>')
    proben.append('<p class="hinweis">Fachtermini stehen kursiv oder fett und sind im <b>Lexicon</b> des Repetitoriums mit Abschnittsverweis gesammelt.</p>')
    if pills:
        proben.append(f'<h3>Farbschlüssel</h3><p class="zg-p">{pills}</p>')
    rechts = "<h3>Bausteine</h3>" + "".join(proben)
    return (f'<section class="titelei-seite" id="t-gebrauch"><div class="titelzeile"><div class="tz-ober">Titelei</div><h1 class="teil">Zum Gebrauch</h1></div>'
            f'<table class="gebrauch"><tr><td>{links}</td><td>{rechts}</td></tr></table></section>')


def abkuerzungen_seite(werk):
    """Abkürzungen und Zitierweise wie satz.abkuerzungen; Liste aus dem Werk, ergänzt um die im Text gefundenen Kit-Abkürzungen."""
    # Abkürzungen aus dem Text; ein Siglen- oder Abkürzungsverzeichnis im Werk selbst zählt nicht (es erklärt sie schon)
    verzeichnis = lambda b: b["typ"] == "tabelle" and b["kopf"][0].strip().lower() in ("sigle", "abk.", "abkürzung", "kurzbezeichnung")
    alltext = " ".join([t for _, _, _, bl in listen(werk) for b in bl if not verzeichnis(b) for t in block_texte(b)]
                       + [t for o, t in texte(werk) if "Block" not in o])
    eigene = {a: b for a, b in werk.get("abkuerzungen", [])}
    for k, v in satz.ABK.items():
        muster = r"(?<![\w-])" + re.escape(k) + (r"(?=\s?\d)" if k == "Z" else r"(?![\w-])")
        if k not in eigene and re.search(muster, alltext):
            eigene[k] = v
    liste = sorted(eigene.items(), key=lambda x: x[0].lower().replace("ä", "a").replace("ö", "o").replace("ü", "u"))
    half = -(-len(liste) // 2)
    zeilen = "".join(f'<tr><td class="a">{esc(liste[i][0])}</td><td>{esc(liste[i][1])}</td>'
                     + (f'<td class="a">{esc(liste[i + half][0])}</td><td>{esc(liste[i + half][1])}</td>' if i + half < len(liste) else "<td></td><td></td>") + "</tr>"
                     for i in range(half))
    # 4.0: Beispiele nach dem Zitierstil des Werks (AZR im Recht, APA 7 in der Wirtschaft), nicht mehr aus einem Einzelwerk
    rand = next((q for q in werk["quellen"] if q.get("gattung") in ("literatur", "kommentar", "aufsatz", "beitrag", "lv")), werk["quellen"][0])
    rand_bsp = f'{rand.get("rand") or rand["kurz"]}' + (" 43" if werk["modul"].get("zitierstil") == "APA7" else " Rz 5")
    if werk["modul"].get("zitierstil") == "APA7":
        zit = [("Beleg im Text", "(Fisher, 1930, S. 43)", "Autor, Jahr und Seite nach APA 7; Vollangabe im Quellenverzeichnis"),
               ("Formel", "Gl. (1)", "Gleichungsnummer am rechten Rand; im Text als Verweis"),
               ("Randbeleg", rand_bsp, "Quelle und Fundstelle am rechten Rand, neben der belegten Zeile"),
               ("Querverweis", "→ B2, → ADM D7", "Abschnittscode; mit Sigle für Abschnitte einer anderen Terra")]
    else:
        zit = [("Paragraph", "§ 6 ABGB", "ohne Punkt nach Abkürzungen; Absatz und Ziffer werden nachgestellt: § 1 Abs 2 Z 3"),
               ("Artikel", "Art 149 Abs 1 B-VG", "Gesetz stets angeben; „ff“ für die folgenden Artikel: Art 137 ff B-VG"),
               ("Fundstelle", "BGBl 1930/1, RGBl 1867/142", "Gesetzblatt, Jahrgang und Nummer (AZR); vor 1849 PGS (Politische Gesetzsammlung)"),
               ("Randbeleg", rand_bsp, "Quelle und Fundstelle am rechten Rand, neben der belegten Zeile; Vollangabe im Quellenverzeichnis"),
               ("Querverweis", "→ B2, → ADM D7", "Abschnittscode; mit Sigle für Abschnitte einer anderen Terra")]
    zt = ('<h2 class="unter">Zitierweise</h2><table class="t zit"><thead><tr><th>Form</th><th>Beispiel</th><th>Hinweis</th></tr></thead><tbody>'
          + "".join(f"<tr><td><b>{a}</b></td><td>{typo_esc(b)}</td><td>{esc(c)}</td></tr>" for a, b, c in zit) + "</tbody></table>")
    return (f'<section class="titelei-seite" id="t-abk"><div class="titelzeile"><div class="tz-ober">Titelei</div><h1 class="teil">Abkürzungen und Zitierweise</h1></div>'
            f'<table class="abk"><thead><tr><th>Abk.</th><th>Bedeutung</th><th>Abk.</th><th>Bedeutung</th></tr></thead><tbody>{zeilen}</tbody></table>{zt}</section>')


def provinzkopf(s, k, gen=None):
    """Provinzkopf wie satz.provinzkopf (Chip, Name, Leitfrage, In 60 Sekunden, Anker, Verzeichnis), Verzeichnis mit Seitenzahlen."""
    eintr = [(a["code"], s.md(a["titel"], latein=True) + (f' <span class="rel">{ziel()}</span>' if a.get("wichtig") else "")) for a in k.get("abschnitte", [])]
    eintr += [(f"L·{c[1]}", t) for c, t in (gen or [])]
    half = -(-len(eintr) // 2)
    zeilen = []
    for i in range(half):
        zellen = []
        for e in (eintr[i], eintr[i + half] if i + half < len(eintr) else None):
            if e:
                zid = "k-" + e[0].replace("·", "")
                zellen.append(f'<td><a class="kis" href="#{zid}"></a><span class="c">{e[0]}</span><a href="#{zid}" class="ki">{e[1]}</a></td>')
            else:
                zellen.append("<td></td>")
        zeilen.append("<tr>" + "".join(zellen) + "</tr>")
    anker = " · ".join(esc(x) for x in k.get("anker", [])) + (f' · {esc(k["seiten"])}' if k.get("seiten") else "")
    pills = "".join(f'<span class="rpill" style="--d:{FARBEN[r["farbe"]][0]};--h:{FARBEN[r["farbe"]][2]}">{esc(r["name"])}</span>' for r in s.rollen.values())
    schluessel = ""  # Entwurf 10: Farbschlüssel nur noch in „Zum Gebrauch“; die Farben bleiben in Grafiken und Tabellenköpfen
    return (f'<div class="provkopf"><span class="pchip">Provinz {esc(k["nr"])} ({k["code"]})</span>'
            f'<h1 class="ptitel" id="p-{k["code"]}">{esc(k.get("name_lat", k["name_de"]))}</h1><div class="pde">{esc(k["name_de"])}</div>'
            f'<div class="leitfrage"><b>Leitfrage</b>{s.md(k["leitfrage"])}</div>'
            f'<div class="kompakt"><b>In 60 Sekunden</b><ol>{"".join(f"<li>{s.md(x)}</li>" for x in k["kompakt"])}</ol></div>'
            + (f'<div class="panker">{anker}</div>' if anker.strip(" ·") else "") + '</div>'
            f'<table class="kindex">{"".join(zeilen)}</table>{schluessel}')


def kachelkopf(code, titel_html, kanker_html, rel="", anzeige=None):
    """Abschnittskopf: Kachelkopf aus satz.kachelkopf (großer Code in Provinzfarbe, Anker rechts), ohne Rahmen."""
    return (f'<div class="kkopf" id="k-{code}"><span class="code">{anzeige or code}</span><h2>{titel_html}</h2>{rel}'
            f'<span class="kanker">{kanker_html}</span></div>')


def gen_vorhanden(werk, code):
    k = werk["kapitel"]
    return {"LF": any(b["typ"] == "spitzmarke" and b["art"] == "klausurhinweis" for _, _, _, bl in listen(werk) for b in bl),
            "LQ": bool(werk.get("quellenkritik")),
            "LV": bool(werk.get("lexicon")) or any(b["typ"] == "latinum" for _, _, _, bl in listen(werk) for b in bl),
            "LS": any(x.get("kontrollfragen") for x in k),
            "LA": bool(werk.get("aenderungen"))}[code]


def lexicon_eintraege(werk):
    """Lexicon wie satz.l_generiert: Lexicon-Einträge des Werks und Latinum-Bausteine, alphabetisch; Fremdsprachliches kursiv."""
    lex = {}
    for schl, k, a, bl in listen(werk):
        for b in bl:
            if b["typ"] == "latinum":
                lex[b["lat"]] = (f'*{b["lat"]}*', b["de"], a["code"] if a else k["code"])
    for e in werk.get("lexicon", []):
        lex[e["begriff"]] = (f'*{e["begriff"]}*' if e.get("sprache") else e["begriff"], e["bedeutung"], e["abschnitt"])
    return sorted(lex.values(), key=lambda x: satz._sortierschluessel(x[0].strip("*")))


def repetitorium(werk, s, plan=None):
    """Provinz L wie im Kit: Provinzkopf in Tinte, danach die generierten Abschnitte L·F, L·Q, L·V, L·S, L·A."""
    r = werk["repetitorium"]
    satz.SEITENVERWEIS = False
    gen = [(c, t) for c, t in GEN if gen_vorhanden(werk, c)]
    pc, pm, ph = FARBEN["tinte"]
    o = [f'<section class="kapitel repetitorium" data-kap="L" data-nr="{esc(r["nr"])}" data-lat="{esc(r["name_lat"])}" style="--p:{pc};--pm:{pm};--p-hell:{ph}">',
         f'<div class="auftakt">{provinzkopf(s, r, gen)}</div>']
    if r.get("abschnitte"):  # 4.0: eigene Abschnitte des Repetitoriums (L1 …), etwa Prüfungsroute oder Chronik, vor den generierten Teilen
        o += abschnitte_html(s, rep_kapitel(werk), plan or {"gleiten": {}, "umbruch": set(), "laufweite": {}}, "tinte")[0]
    teile = {}
    fallen = [(a["code"], b["text"]) for a in alle_abschnitte(werk) for b in a["bloecke"] if b["typ"] == "spitzmarke" and b["art"] == "klausurhinweis"]
    if fallen:
        teile["LF"] = satz.tabelle(["Nr", "Klausurfalle", "Abschnitt"], [[str(i), t, f"[[{c}]]"] for i, (c, t) in enumerate(fallen, 1)], klasse="t gen")
    if werk.get("quellenkritik"):
        teile["LQ"] = satz.tabelle(["Quelle", "Befund", "Richtig ist", "Abschnitt"], [[q["quelle"], q["befund"], q["richtig"], f'[[{q["abschnitt"]}]]'] for q in werk["quellenkritik"]])
    lex = lexicon_eintraege(werk)
    if lex:
        teile["LV"] = satz.tabelle(["Begriff", "Bedeutung", "Abschnitt"], [[b, d, f"[[{c}]]"] for b, d, c in lex], rollen=["begriff", "text", "text"])
    fragen = [q for k in werk["kapitel"] for q in k.get("kontrollfragen", [])]
    if fragen:
        teile["LS"] = (satz.tabelle(["Nr", "Frage", "Abschnitt"], [[str(i), q["frage"], f'[[{q["abschnitt"]}]]'] for i, q in enumerate(fragen, 1)], klasse="t gen")
                       + '<div class="schema-titel loes-titel">Auflösung</div>'
                       + satz.tabelle(["Nr", "Antwort"], [[str(i), q["antwort"]] for i, q in enumerate(fragen, 1)], klasse="t gen loes-t"))
    if werk.get("aenderungen"):
        teile["LA"] = satz.tabelle(["Version", "Datum", "Änderung"], [[a["version"], dt.date.fromisoformat(a["datum"]).strftime("%d.%m.%Y"), a["text"]] for a in werk["aenderungen"]],
                                     rollen=["begriff", "zahl", "text"])
    for c, t in gen:
        vor = ' data-neue-seite="ja"' if f"{c}~0" in (plan or {}).get("umbruch", set()) else ""
        o.append(f'<section class="abschnitt generiert" data-code="{c}"{vor}><header class="abkopf">{kachelkopf(c, t, "generiert", anzeige="L·" + c[1])}</header>'
                 f'<div class="bs sp">{teile[c]}</div></section>')
    o.append("</section>")
    return "".join(o)


def abschnitt_von(werk, schl):
    """Code, unter dem ein Block im Verzeichnis erscheint: Abschnittscode, Einleitung als Provinzcode, Abschluss als X·Ü."""
    if schl.endswith("E"):
        return schl[:-1]
    if schl.endswith("S"):
        return schl[:-1] + "·Ü"
    return schl


def abbildungsverzeichnis(werk, s):
    """Abbildungsverzeichnis wie satz.abbildungsverzeichnis: Nr, Titel mit Art, Nachweis, Abschnitt als Chip, Seite."""
    zeilen = []
    for schl, k, a, bl in listen(werk):
        for b in bl:
            if b["typ"] != "abbildung":
                continue
            n = s.nummer[("abb", b["id"])]
            art = {"zeitstrahl": "Zeitstrahl", "zeitleiste": "Zeitleiste", "diagramm": "BPMN" if b.get("stil") == "bpmn" else "Flussdiagramm",
                   "baum": "Organigramm", "kurve": "Kurve", "tkonto": "T-Konto", "bild": "Bild", "svg": "Grafik"}.get(b["variante"], "Grafik")
            code = abschnitt_von(werk, schl)
            zid = "p-" + k["code"] if code == k["code"] else "k-" + code.replace("·", "")
            zeilen.append(f'<tr><td class="nr"><a href="#abb-{b["id"]}">Abb{NBSP}{n}</a></td><td class="t">{s.md(b["titel"], latein=True)}<span class="art">{art}</span></td>'
                          f'<td class="nw">{s.md(b["nachweis"])}</td><td class="wo"><a class="kc farbe-{KAPITELFARBE.get(k["code"], "petrol")}" href="#{zid}">{code}</a></td>'
                          f'<td class="n"><a class="sz" href="#abb-{b["id"]}"></a></td></tr>')
    if len(zeilen) < satz.ABB_MIN_VERZEICHNIS:
        return ""
    return ('<section class="titelei-seite anhang" id="t-abbildungen"><div class="titelzeile"><div class="tz-ober">Anhang</div><h1 class="teil">Abbildungsverzeichnis</h1>'
            f'<div class="teil-unter">{len(zeilen)} Abbildungen; Nummer und Seitenzahl führen zur Abbildung, der Code zum Abschnitt.</div></div>'
            '<table class="av"><thead><tr><th>Nr</th><th>Titel</th><th>Nachweis</th><th>Abschnitt</th><th>Seite</th></tr></thead>'
            f'<tbody>{"".join(zeilen)}</tbody></table></section>')


def quellenverzeichnis(werk):
    """Quellenverzeichnis aus satz.quellenverzeichnis (Legende, Gattungen, Vollangabe, Verwendung als Chips, Schluss)."""
    kacheln = []
    schluessel = {x: q["kurz"] for q in werk["quellen"] for x in quell_schluessel(q)}
    for k in werk["kapitel"] + [x for x in [rep_kapitel(werk)] if x]:
        for a in k["abschnitte"]:
            qs = list(a.get("quellen", []))
            for b in a["bloecke"]:
                for t in block_texte(b):
                    for q in re.findall(r"@([A-Za-z0-9ÄÖÜäöü]+)", t):
                        q = schluessel.get(q, q)
                        if q not in qs:
                            qs.append(q)
            kacheln.append({"code": a["code"], "quellen": qs})
    alt = {"meta": {**werk["meta"], "kicker": werk["meta"].get("kicker")}, "modul": werk["modul"], "quellen": werk["quellen"],
           "provinzen": [{"code": k["code"], "farbe": KAPITELFARBE.get(k["code"], "petrol"), "kacheln": [x for x in kacheln if x["code"].startswith(k["code"])]}
                         for k in werk["kapitel"] + [x for x in [rep_kapitel(werk)] if x]],
           "quellenkritik": werk.get("quellenkritik")}
    h = "".join(satz.quellenverzeichnis(alt))
    # Quellen, die mehr als zwölf Abschnitte stützen (etwa das Lehrbuch der Lehrveranstaltung): Kapitel statt Abschnitte nennen
    def verdichten(m):
        chips = re.findall(r'<a class="kc farbe-([a-z]+)" href="#k-([A-Z]\d+)">[^<]*</a>', m.group(1))
        if len(chips) <= 12:
            return m.group(0)
        kap = {}
        for f, c in chips:
            kap.setdefault(c[0], (f, c, []))[2].append(c)
        return ('<td class="wo">' + "".join(f'<a class="kc farbe-{f}" href="#k-{c}" title="{", ".join(cs)}">{k}</a>' for k, (f, c, cs) in kap.items())
                + f'<span class="kc-n">{len(chips)} Abschnitte</span></td>')
    h = re.sub(r'<td class="wo">(.*?)</td>', verdichten, h, flags=re.S)
    # kleine Gattungsgruppen (bis acht Quellen) bleiben mit ihrer Überschrift beisammen; größere laufen mit wiederholtem Kopf weiter
    h = re.sub(r'<div class="unit" (data-[^>]*data-name="Quellen [^"]*")>(.*?)</table></div>',
               lambda m: f'<div class="unit{" qv-ganz" if m.group(2).count("<tr>") <= 9 else ""}" {m.group(1)}>{m.group(2)}</table></div>', h, flags=re.S)
    h = re.sub(r'<span data-ziel="([^"]+)"></span>', r'<a class="sz" href="#\1"></a>', h)
    # Sprungziel je Quelle für die Randbelege
    h = re.sub(r'<tr><td class="kurz">(.*?)</td>', lambda m: f'<tr id="q-{quell_anker({"kurz": html.unescape(re.sub(r"<[^>]+>", "", m.group(1)).replace(chr(173), ""))})}"><td class="kurz">{m.group(1)}</td>', h)
    for a, b in (("Kacheln, die sich auf die Quelle stützen", "Abschnitte, die sich auf die Quelle stützen"),
                 ("Quellenanker je Kachel", "Quellenanker je Abschnitt"), ("Inhaltsgleich mit der Wissenslandkarte", "Hervorgegangen aus der Wissenslandkarte"),
                 ("Kachelcodes stimmen in Karte, Skript und Exam überein", "Abschnittscodes stimmen mit den Kachelcodes der Karte überein"),
                 ('id="t-quellen"', "")):
        h = h.replace(a, b)
    return f'<section class="titelei-seite anhang" id="t-quellen">{h}</section>'


def sachregister(werk, s, anker):
    """Sachregister wie satz.sachregister: Buchstabengruppen (Begriffe, Latein, Personen), danach Normen und Fundstellen; zweispaltig."""
    gruppen = {}
    for art, schl, rid in s.reg:
        gruppen.setdefault(art, {}).setdefault(schl.replace(NBSP, " "), []).append(rid)

    def stellen(ids):
        seiten = {}
        for rid in ids:
            sz = anker.get(rid)
            if sz and sz not in seiten:
                seiten[sz] = rid
        return ", ".join(f'<a href="#{rid}">{sz}</a>' for sz, rid in sorted(seiten.items())) or "·"
    begriffe = {}
    lexbegriffe = {e[0].strip("*").lower() for e in lexicon_eintraege(werk)}
    for schl, ids in gruppen.get("sache", {}).items():
        if schl[:1].isupper() or schl.lower() in lexbegriffe:
            begriffe.setdefault(schl, []).extend(ids)
    for art in ("latein", "person"):
        for schl, ids in gruppen.get(art, {}).items():
            begriffe.setdefault(schl, []).extend(ids)
    # Groß- und Kleinschreibung zusammenführen („Suspensives Veto:“ am Listenanfang = „suspensives Veto“); Form des Lexicons hat Vorrang
    zusammen, lexform = {}, {e["begriff"].lower(): e["begriff"] for e in werk.get("lexicon", [])}
    for schl, ids in begriffe.items():
        zusammen.setdefault(schl.lower(), []).append((schl, ids))
    begriffe = {}
    for low, varianten in zusammen.items():
        form = lexform.get(low) or next((v for v, _ in varianten if v[:1].islower()), varianten[0][0])
        begriffe[form] = [i for _, ids in varianten for i in ids]
    vorhanden = {b.lower() for b in begriffe}
    for e in werk.get("lexicon", []):  # Lexicon-Begriff ohne eigene Textstelle: Verweis auf seinen Abschnitt
        if e["begriff"].lower() not in vorhanden:
            begriffe.setdefault(e["begriff"], []).append(f'k-{e["abschnitt"]}')
            if e.get("sprache"):
                gruppen.setdefault("latein", {})[e["begriff"]] = []
    bloecke = []

    def gruppe(kopf, zeilen, klasse="rb"):
        """Registergruppe (Kopf und Zeilen) als Block; eine Gruppe, die eine Spalte übersteigt, wird geteilt (4.0),
        die Fortsetzung trägt den Kopf mit „Fortsetzung“. zeilen: (HTML, Text für die Höhenschätzung)."""
        stueck, hoehe, teil = [], 9.0, 0
        for h, t in zeilen + [(None, None)]:
            zh = _zeilen_mm([t], 36, 4.5, 4.0) if t is not None else 0
            if t is None or (stueck and hoehe + zh > SPALTE_FOLGE - 30):
                k = esc(kopf) + (" <small>(Fortsetzung)</small>" if teil else "")
                bloecke.append((f'<div class="register"><div class="{klasse}">{k}</div><table>{"".join(stueck)}</table></div>', hoehe))
                stueck, hoehe, teil = [], 9.0, teil + 1
                if t is None:
                    break
            stueck.append(h)
            hoehe += zh
    buchst = {}
    for wort in sorted(begriffe, key=satz._sortierschluessel):
        buchst.setdefault(satz._sortierschluessel(wort)[:1].upper() or "#", []).append(wort)
    for b, woerter in buchst.items():
        gruppe(b, [(f'<tr><td class="t">{s.md(w, latein=True) if w not in gruppen.get("latein", {}) else "<i>" + esc(w) + "</i>"}</td><td class="rz">{stellen(begriffe[w])}</td></tr>',
                    w + " " + re.sub(r"<[^>]+>", "", stellen(begriffe[w]))) for w in woerter])
    normen = gruppen.get("norm", {})
    if normen:
        def nsch(x):
            gesetz, stelle = x.split("|", 1)
            zahl = re.findall(r"\d+", stelle)
            return (gesetz.lower(), int(zahl[0]) if zahl else 0, stelle)
        gruppe("Normen", [(f'<tr><td class="t">{typo_esc(x.split("|", 1)[1] + " " + x.split("|", 1)[0])}</td><td class="rz">{stellen(normen[x])}</td></tr>',
                           x + " " + re.sub(r"<[^>]+>", "", stellen(normen[x]))) for x in sorted(normen, key=nsch)], "rb rn")
    fund = gruppen.get("fundstelle", {})
    if fund:
        gruppe("Gesetzblätter", [(f'<tr><td class="t">{esc(x)}</td><td class="rz">{stellen(fund[x])}</td></tr>', x + " " + re.sub(r"<[^>]+>", "", stellen(fund[x])))
                                  for x in sorted(fund, key=lambda x: (lambda m: (m.group(1), int(m.group(2)), int(m.group(3))))(re.match(r"(.+?) (\d{4})/(\d+)", x)))], "rb rn")
    return ('<section class="titelei-seite anhang spalten-seite" id="t-register"><div class="titelzeile"><div class="tz-ober">Anhang</div><h1 class="teil">Sachregister</h1>'
            '<div class="teil-unter">Seitenzahlen führen zur Stelle; erfasst sind Fachbegriffe, Latein, Personen, Normen und Gesetzblätter.</div></div>'
            + zweispaltig([x for x, _ in bloecke], [g for _, g in bloecke]) + "</section>")


def typo_esc(x):
    return satz.typo(esc(x))


def abschnitte_html(s, k, plan, kfarbe):
    """Einleitung, Abschnitte und Abschluss eines Kapitels (auch der eigenen Abschnitte des Repetitoriums) → (HTML-Teile, Kernsätze)."""
    o = []
    folge = ordnung(k, plan)
    codes = {a["code"] for a in k["abschnitte"]}

    def setze_liste(schl):  # Seitenwechsel am ersten Block eines Abschnitts gilt dem ganzen Abschnitt (samt Kopf)
        def wechsel(bid):
            return bid in plan["umbruch"] and not (bid.endswith("~0") and bid[:-2] in codes)
        s.belege = []
        teile = [block_html(s, b, kfarbe, bid, wechsel(bid), plan.get("laufweite", {}).get(bid)) for eig, bid, b in folge if eig == schl]
        return teile
    o += setze_liste(f'{k["code"]}E')
    kerns = []
    for a in k["abschnitte"]:
        kanker = esc(a.get("anker", "")) + (f'<span class="seite">{esc(a["fundstelle"])}</span>' if a.get("fundstelle") else "")
        kopf = (f'<header class="abkopf">{kachelkopf(a["code"], s.md(a["titel"], latein=True), satz.typo(kanker), ziel() if a.get("wichtig") else "")}'
                f'</header>')
        teile = setze_liste(a["code"])
        if teile and len(a["bloecke"][0].get("text", "")) < 520 and f'data-b="{a["code"]}~0"' in teile[0]:
            kopf = f'<div class="kopfgruppe">{kopf}{teile[0]}</div>'
            teile = teile[1:]
        vor = ' data-neue-seite="ja"' if f'{a["code"]}~0' in plan["umbruch"] else ""
        o.append(f'<section class="abschnitt" data-code="{a["code"]}"{vor}>{kopf}' + "".join(teile) + "</section>")
        kerns += [(a["code"], b["text"]) for b in a["bloecke"] if b["typ"] == "kernsatz"]
    if k.get("abschluss"):
        vor = ' data-neue-seite="ja"' if f'{k["code"]}U~0' in plan["umbruch"] else ""
        o.append(f'<section class="abschnitt provinzende" data-code="{k["code"]}U"{vor}><header class="abkopf">{kachelkopf(k["code"] + "U", "Auf einen Blick", "Provinzende", anzeige=k["code"] + "·Ü")}</header>'
                 + "".join(setze_liste(f'{k["code"]}S')) + "</section>")
    return o, kerns


def dokument(werk, s, basis, plan=None):
    """plan: Gleiten, Seitenwechsel, Laufweite und Anker aus den Korrekturläufen des Satzes."""
    plan = plan or {"gleiten": {}, "umbruch": set(), "laufweite": {}}
    m = werk["meta"]
    s.reg, s.randbelege, s.ohne_fn = [], [], False
    o = [titelseite(werk, s), impressum(werk), inhalt(werk, s), zum_gebrauch(werk, s), abkuerzungen_seite(werk)]
    for k in werk["kapitel"]:
        kfarbe = KAPITELFARBE.get(k["code"], "petrol")
        pc, pm, ph = FARBEN[kfarbe]
        o.append(f'<section class="kapitel" data-kap="{k["code"]}" data-nr="{esc(k["nr"])}" data-lat="{esc(k.get("name_lat", k["name_de"]))}" '
                 f'style="--p:{pc};--pm:{pm};--p-hell:{ph}">')
        o.append(f'<div class="auftakt">{provinzkopf(s, k)}</div>')
        teile_k, kerns = abschnitte_html(s, k, plan, kfarbe)
        o += teile_k
        if kerns:
            s.ohne_fn = True
            li = "".join(f'<li>{s.md(t)} <span class="kf-code"><a class="vw" href="#k-{c}">{c}</a></span></li>' for c, t in kerns)
            s.ohne_fn = False
            o.append(f'<div class="fuellblock" id="kern-{k["code"]}"><div class="lbl">Kernfakten · Provinz {esc(k["nr"])}</div><ul>{li}</ul></div>')
        o.append("</section>")
    if werk.get("repetitorium"):
        o.append(repetitorium(werk, s, plan))
    o.append(abbildungsverzeichnis(werk, s))
    o.append(quellenverzeichnis(werk))
    o.append(sachregister(werk, s, plan.get("anker", {})))
    basis_css = (KIT / "vorlage" / "skript.css").read_text(encoding="utf-8")
    basis_css = re.sub(r"@font-face\s*\{[^}]*\}", "", basis_css)
    basis_css = re.sub(r"@page[^{]*\{[^}]*\}", "", basis_css)
    basis_css = re.sub(r"@media[^{]*\{(?:[^{}]*\{[^}]*\})*[^{}]*\}", "", basis_css)
    css = (KIT / "vorlage" / "buch.css").read_text(encoding="utf-8") + os.environ.get("TERRA_TEST_CSS", "")  # Testhaken
    rb_json = json.dumps({str(i): t for i, t in enumerate(s.randbelege, 1)}, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!DOCTYPE html><html lang="de-AT"><head><meta charset="utf-8"><title>{esc(m["titel"])} · {esc(m["untertitel"])}</title>
<meta name="author" content="{VERMERK}">{f'<link rel="stylesheet" href="{basis}{satz.NM}/katex/dist/katex.min.css">' if s.kx else ""}<style>{schriften_css(basis)}</style><style>{basis_css}</style><style>{satz.palette_css()}</style><style>{css}</style>
<script>window.PagedConfig = {{ auto: true, after: (f) => {{ window.__seiten = f.total; window.__fertig = true; }} }};</script>
<script type="application/json" id="randbelege">{rb_json}</script>
</head><body>{"".join(o)}<script src="{basis}{NM / 'pagedjs' / 'dist' / 'paged.polyfill.js'}"></script><script>{KOPF_JS}</script></body></html>"""


# Kopfzeile, Fußzeile und Daumenregister wie in den bisherigen Terrae; nach dem Umbruch eingesetzt (absolut, ohne Einfluss auf den Satz).
# Provinzseiten: Kolumne rechts und Daumen der Provinz; Inhalt und Sachregister: alle Daumen; Titelei und Anhang: keine Kolumne rechts.
TITEL_JS = r"""() => {
  // Titelseite: jede Textzeile (Range je Textknoten) gegen jede andere eines fremden Elements; Glyphenkasten oben und unten
  // um ein Zehntel gekürzt, damit enger Zeilenabstand nicht als Überschneidung zählt. Dazu: nichts ragt über die Seite.
  const tp = document.querySelector('.titelseite');
  if (!tp) return [];
  const seite = (tp.closest('.pagedjs_sheet') || tp).getBoundingClientRect();
  const gruppen = [], fehler = [];
  // Reicht der Platz unter dem Titelblock nicht, rückt das Register in zwei Stufen enger zusammen; reicht es dann noch nicht: Fehler
  const koerper = tp.querySelector('.tb-koerper');
  if (koerper) {
    for (const stufe of ['eng', 'enger']) {
      if (koerper.scrollHeight <= koerper.clientHeight + 1) break;
      koerper.classList.add(stufe);
    }
    if (koerper.scrollHeight > koerper.clientHeight + 1)
      fehler.push('Titelseite zu voll: Titelblock, Register und Fuß brauchen ' + Math.round((koerper.scrollHeight - koerper.clientHeight) * 25.4 / 96) + ' mm mehr');
  }
  const gang = document.createTreeWalker(tp, NodeFilter.SHOW_TEXT);
  for (let n; (n = gang.nextNode());) {
    if (!n.textContent.trim() || n.parentElement.closest('svg')) continue;
    const r = document.createRange();
    r.selectNodeContents(n);
    const kaesten = [...r.getClientRects()].filter(x => x.width > 0.5 && x.height > 0.5)
      .map(x => ({ l: x.left, r: x.right, o: x.top + x.height * 0.1, u: x.bottom - x.height * 0.1 }));
    if (kaesten.length) gruppen.push({ el: n.parentElement, text: n.textContent.trim().slice(0, 40), kaesten });
  }
  gruppen.forEach((a, i) => {
    if (a.kaesten.some(k => k.l < seite.left - 0.5 || k.r > seite.right + 0.5 || k.o < seite.top - 0.5 || k.u > seite.bottom + 0.5))
      fehler.push('Titelseite: „' + a.text + '“ ragt über die Seite');
    gruppen.slice(i + 1).forEach(b => {
      if (a.el.contains(b.el) || b.el.contains(a.el)) return;
      if (a.kaesten.some(p => b.kaesten.some(q => p.l < q.r - 0.5 && q.l < p.r - 0.5 && p.o < q.u && q.o < p.u)))
        fehler.push('Titelseite: „' + a.text + '“ schneidet „' + b.text + '“');
    });
  });
  return [...new Set(fehler)];
}"""

RAHMEN_JS = r"""(meta) => {
  const seiten = [...document.querySelectorAll('.pagedjs_page')], n = seiten.length;
  const prov = meta.provinzen, o = 28, u = 30, h = Math.min(30, (297 - o - u) / Math.max(1, prov.length) - 2.5);
  const reiter = (j) => '<div class="daumen" style="--p:' + prov[j].dunkel + ';top:' + (o + j * (h + 2.5)).toFixed(1) + 'mm;height:' + h.toFixed(1) + 'mm"><span>' + prov[j].nr + '</span></div>';
  seiten.forEach((pg, i) => {
    if (pg.querySelector('.titelseite')) return;
    const kap = pg.querySelector('[data-kap]');
    const rechts = kap ? 'Provinz ' + kap.dataset.nr + ' · ' + kap.dataset.lat : '';
    const box = document.createElement('div');
    box.className = 'terra-rahmen';
    box.innerHTML = '<div class="kopfzeile"><span class="l"><b>' + meta.titel + '</b> · ' + meta.untertitel + '</span><span class="r">' + rechts + '</span></div>'
      + '<div class="fusszeile"><span class="l">' + meta.stand + '</span><span class="m">(c) Oliver Bedernik</span><span class="r">Seite ' + (i + 1) + ' von ' + n + '</span></div>';
    if (kap) {
      const j = prov.findIndex(p => p.code === kap.dataset.kap);
      if (j >= 0) box.innerHTML += reiter(j);
    } else if (pg.querySelector('.spalten-seite')) {
      prov.forEach((_, j) => { box.innerHTML += reiter(j); });
    }
    pg.querySelector('.pagedjs_sheet').appendChild(box);
  });
  // Trennlinie über dem Abschnittskopf nur mitten auf der Seite; oben auf einer Seite trennt schon der Seitenwechsel
  const oben = [];
  document.querySelectorAll('.abschnitt:not([data-split-from])').forEach(sec => {
    const kopf = sec.querySelector('.abkopf');
    const area = sec.closest('.pagedjs_page') && sec.closest('.pagedjs_page').querySelector('.pagedjs_area');
    if (!kopf || !area) return;
    // oben auf der Seite: nur der Abstand über dem Abschnitt (7 mm) liegt zwischen Satzspiegel und Kopf
    if (kopf.getBoundingClientRect().top - area.getBoundingClientRect().top < 34) { sec.classList.add('seitenanfang'); oben.push(sec.dataset.code || ''); }
  });
  // Randbelege (Entwurf 13), als Letztes, denn jede Änderung davor (Seitenanfang) verschiebt die Zeilen: rechts neben dem Satzspiegel, Grundlinie auf der Zeile des Ankers. Bausteine, die in die
  // Randspalte reichen (Kopf, Abbildung, Tabelle, Fallbeispiel), sind Hindernisse; Belege derselben Zeile werden zusammengefasst,
  // gedrängte Belege weichen nach unten aus, vor einem Hindernis auch nach oben, wenn das näher liegt; am Seitenende nach oben.
  const pxmm = 96 / 25.4, rbText = JSON.parse((document.getElementById('randbelege') || {}).textContent || '{}');
  const spalte = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--spalte')) * pxmm;
  const rand = { anzahl: 0, seiten: {}, max_versatz_mm: 0, fehler: [], belege: [] };
  const grundlinie = el => { const i = document.createElement('i'); i.style.cssText = 'display:inline-block;width:0;height:0;vertical-align:baseline'; el.prepend(i); const y = i.getBoundingClientRect().top; i.remove(); return y; };
  seiten.forEach(pg => {
    const anker = [...pg.querySelectorAll('.pagedjs_area .rb-anker')];
    if (!anker.length) return;
    const nr = pg.dataset.pageNumber, sheet = pg.querySelector('.pagedjs_sheet'), sr = sheet.getBoundingClientRect();
    const ar = pg.querySelector('.pagedjs_area').getBoundingClientRect(), rechts = ar.right - spalte;
    const x = rechts + 2.6 * pxmm, breite = spalte + 2 * pxmm, luft = 1.2 * pxmm;
    const hind = [];
    const sammle = el => [...el.children].forEach(c => {
      const r = c.getBoundingClientRect();
      // eingerückte Bausteine sind nie Hindernis (ein geteilter Baustein meldet sein Rechteck samt Überlaufspalten)
      if (!r.height || r.right <= rechts + 2 || r.left >= ar.right || c.matches('.sp, ul.auf, ol.auf')) return;
      if (c.querySelector('.sp, ul.auf, ol.auf')) sammle(c); else hind.push([Math.max(r.top, ar.top) - luft, Math.min(r.bottom, ar.bottom) + luft]);
    });
    sammle(pg.querySelector('.pagedjs_page_content'));
    const items = [];
    anker.forEach(a => {
      const y = grundlinie(a), n = +a.dataset.rb, vor = items[items.length - 1];
      if (vor && Math.abs(y - vor.ziel) < 3) { vor.nrn.push(n); return; }
      items.push({ ziel: y, nrn: [n], anker: a });
    });
    items.forEach(it => {
      const d = document.createElement('div');
      d.className = 'randbeleg';
      d.id = 'rbt-' + it.nrn[0];
      d.style.cssText = 'position:absolute;left:' + (x - sr.left) + 'px;width:' + breite + 'px;top:0px;';
      d.style.setProperty('--p', getComputedStyle(it.anker).getPropertyValue('--p'));
      d.innerHTML = it.nrn.map(n => rbText[n] || '').join('; ');
      sheet.appendChild(d);
      const r = d.getBoundingClientRect();
      it.el = d; it.h = r.height; it.off = grundlinie(d) - r.top;
      it.y = it.ziel - it.off;  // Oberkante, bei der die Grundlinien übereinstimmen
    });
    const trifft = (y, h) => hind.find(([o, u]) => y < u && y + h > o);
    let unten = -Infinity;  // vorwärts: unter den vorigen Beleg und unter Hindernisse
    items.forEach(it => {
      const wunsch = Math.max(it.y, unten);
      let y = wunsch;
      for (let t; (t = trifft(y, it.h));) y = t[1];
      if (y > wunsch + 0.5) {  // Hindernis darunter: auch darüber versuchen (Unterkante an die Oberkante), der nähere Platz gewinnt
        let o = wunsch;
        for (let t; o >= ar.top && (t = trifft(o, it.h));) o = t[0] - it.h;
        if (o >= Math.max(unten, ar.top) && Math.abs(o - it.y) < Math.abs(y - it.y)) y = o;
      }
      it.y = y;
      unten = it.y + it.h + luft;
    });
    let grenze = ar.bottom;  // rückwärts: über das Seitenende und über den folgenden Beleg
    for (let i = items.length - 1; i >= 0; i--) {
      const it = items[i];
      if (it.y + it.h > grenze) { it.y = grenze - it.h; for (let t; (t = trifft(it.y, it.h));) it.y = t[0] - it.h; }
      grenze = it.y - luft;
    }
    items.forEach(it => { it.el.style.top = (it.y - sr.top) + 'px'; });
    items.forEach((it, i) => {
      const v = Math.abs(grundlinie(it.el) - grundlinie(it.anker)) / pxmm;  // nachgemessen: Abstand der Grundlinien im fertigen Satz
      rand.max_versatz_mm = Math.max(rand.max_versatz_mm, Math.round(v * 10) / 10);
      rand.belege.push({ seite: +nr, nrn: it.nrn, versatz_mm: Math.round(v * 10) / 10 });
      if (it.y < ar.top - 0.5 || it.y + it.h > ar.bottom + 0.5) rand.fehler.push('Randbeleg ' + it.nrn.join('+') + ' auf S ' + nr + ' außerhalb des Satzspiegels');
      if (trifft(it.y + 0.5, it.h - 1)) rand.fehler.push('Randbeleg ' + it.nrn.join('+') + ' auf S ' + nr + ' überdeckt eine Einbettung oder einen Kopf');
      if (i && it.y < items[i - 1].y + items[i - 1].h - 0.5) rand.fehler.push('Randbelege ' + items[i - 1].nrn.join('+') + ' und ' + it.nrn.join('+') + ' auf S ' + nr + ' überlappen');
    });
    rand.anzahl += anker.length;
    rand.seiten[nr] = anker.map(a => +a.dataset.rb);
  });
  return { seiten: n, seitenanfaenge: oben, rand };
}"""


def schriften_css(basis):
    """@font-face der fest versionierten Hausschriften mit absoluten Adressen (Paged.js liest Stilvorlagen neu ein)."""
    teile = []
    for fam, gew in (("cormorant-garamond", ["latin-500-normal", "latin-600-normal", "latin-700-normal", "latin-400-italic", "latin-500-italic", "latin-ext-600-normal", "latin-ext-400-italic"]),
                     ("spectral", ["latin-400-normal", "latin-600-normal", "latin-400-italic", "latin-ext-400-normal", "latin-ext-600-normal", "latin-ext-400-italic"]),
                     ("alegreya-sans", ["latin-400-normal", "latin-500-normal", "latin-700-normal", "latin-800-normal", "latin-ext-400-normal", "latin-ext-700-normal"])):
        for g in gew:
            datei = NM / "@fontsource" / fam / "files" / f"{fam}-{g}.woff2"
            if not datei.exists():
                continue
            sub, weight, stil = g.rsplit("-", 2)
            name = {"cormorant-garamond": "Cormorant Garamond", "spectral": "Spectral", "alegreya-sans": "Alegreya Sans"}[fam]
            rng = ("U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD"
                   if sub == "latin" else "U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF")
            teile.append(f'@font-face {{ font-family: "{name}"; font-style: {stil}; font-weight: {weight}; font-display: block; '
                         f'src: url("{basis}{datei}") format("woff2"); unicode-range: {rng}; }}')
    for w, f in (("400", "DejaVuSans.ttf"), ("700", "DejaVuSans-Bold.ttf")):
        teile.append(f'@font-face {{ font-family: "Terra Symbole"; font-weight: {w}; src: url("{basis}/usr/share/fonts/truetype/dejavu/{f}"); '
                     f'unicode-range: U+2190-21FF, U+221E, U+2248, U+2260, U+2264-2265, U+25A0-25FF, U+2600-26FF, U+2700-27BF; }}')
    return "\n".join(teile)


# ── Satz in Chromium, Prüfung im Satz ─────────────────────────────────────
GLEITEN_MAX = 3
RAND_VERSATZ_MAX = 12  # mm: weiter darf ein Randbeleg nicht von seiner Zeile abrücken, sonst Warnung  # höchstens so viele Textblöcke darf eine Einbettung hinter ihre Stelle gleiten (auch in den folgenden Abschnitt)
ANRISS = 1 / 3  # Mindestanteil des Satzspiegels für den Anfang eines Abschnitts, der auf die nächste Seite weiterläuft
PRUEF_JS = r"""() => {
  const ANRISS = %ANRISS%;
  const mm = px => px * 25.4 / 96;
  const seiteVon = el => { const p = el.closest('.pagedjs_page'); return p ? +p.dataset.pageNumber : null; };
  const fehler = [], warn = [], anker = {}, seiten = [], kopfunten = [], labelunten = [];
  document.querySelectorAll('[id]').forEach(el => { const s = seiteVon(el); if (s && !(el.id in anker)) anker[el.id] = s; });
  // Einbettungen und Tabellen dürfen nicht geteilt werden
  const teilung = [];
  document.querySelectorAll('.einbettung:not(.teilbar), .tab:not(.teilbar), .spalten-satz').forEach(el => {
    if (el.hasAttribute('data-split-to') || el.hasAttribute('data-split-from')) {
      fehler.push('geteilte Einbettung auf S ' + seiteVon(el) + ': ' + (el.id || el.className));
      if (el.dataset.b && !teilung.includes(el.dataset.b)) teilung.push(el.dataset.b);
    }
  });
  // Fußnote auf derselben Seite wie ihr Zeichen
  document.querySelectorAll('[data-footnote-call]').forEach(c => {
    const n = document.querySelector('[data-footnote-marker="' + c.dataset.footnoteCall + '"]') || document.querySelector('[data-note-id="' + c.dataset.footnoteCall + '"]');
    const ref = c.getAttribute('data-footnote-call');
    const note = document.querySelector('.pagedjs_footnote_area [data-ref="' + ref + '"], .pagedjs_footnote_area [data-id="' + ref + '"]') || n;
    if (!note) fehler.push('Fußnote ohne Text: ' + ref);
    else if (seiteVon(note) !== seiteVon(c)) fehler.push('Fußnote ' + ref + ' auf S ' + seiteVon(note) + ', Zeichen auf S ' + seiteVon(c));
  });
  // Überschrift als letztes Element einer Seite
  document.querySelectorAll('.pagedjs_page').forEach(pg => {
    const nr = +pg.dataset.pageNumber;
    const area = pg.querySelector('.pagedjs_page_content');
    const fnA = pg.querySelector('.pagedjs_footnote_area');
    const fnInhalt = fnA ? fnA.querySelector('.pagedjs_footnote_inner_content, .pagedjs_footnote_content') : null;
    const hatFn = fnInhalt && fnInhalt.textContent.trim().length > 0;
    const unten = hatFn ? fnA.getBoundingClientRect().top : pg.querySelector('.pagedjs_area').getBoundingClientRect().bottom;
    let tiefst = area.getBoundingClientRect().top;
    area.querySelectorAll('p, li, tr, h1, h2, h3, figure, .tab, .fall, .fallbeispiel, .leitfrage, .box, .kernblock, .steckbrief, .merkband, .zitat, .glossar, .provkopf, dl').forEach(e => { const r = e.getBoundingClientRect(); if (r.height) tiefst = Math.max(tiefst, r.bottom); });
    const fussnoten = pg.querySelector('.pagedjs_footnote_area');
    const fnh = fussnoten ? fussnoten.getBoundingClientRect().height : 0;
    const leer = mm(unten - tiefst);
    const bloecke = [...area.querySelectorAll('h2, h3, p, li, tr, figure, .tab, .box, .kernblock, .steckbrief, .fallbeispiel, .zitat, .merkband, .glossar, .provkopf, .label')]
      .filter(e => e.getBoundingClientRect().height > 0 && !e.closest('.abkopf .meta'));
    const letztesEl = bloecke.length ? bloecke[bloecke.length - 1] : null;
    // Überschrift oder Tabellenkopf ohne folgende Zeile (thead, Tabellentitel) gilt ebenso als Kopf am Seitenfuß
    const kopfEl = letztesEl ? (letztesEl.matches('h2, h3') ? letztesEl : (letztesEl.closest('h2, h3, thead') || null)) : null;
    const letzte = kopfEl ? [kopfEl] : [];
    if (letztesEl && letztesEl.matches('.label')) {  // Spitzmarke (Definition, Kerngehalt …) ohne ihren Inhalt am Seitenfuß
      fehler.push('Spitzmarke am Seitenfuß S ' + nr + ': ' + letztesEl.textContent.trim());
      const b = letztesEl.closest('[data-b]'); if (b && !labelunten.includes(b.dataset.b)) labelunten.push(b.dataset.b);
    }
    letzte.forEach(h => { fehler.push((h.matches('thead') ? 'Tabellenkopf' : 'Überschrift') + ' am Seitenfuß S ' + nr + ': ' + h.textContent.trim().slice(0, 40));
      const ab = h.closest('.abschnitt'); if (ab && ab.dataset.code) kopfunten.push(ab.dataset.code + '~0'); });
    seiten.push({ seite: nr, leer_mm: Math.round(leer), fussnoten_mm: Math.round(mm(fnh)), art: pg.classList.contains('pagedjs_titel_page') ? 'titel' : 'text',
                  abb: !!pg.querySelector('figure.abb') });
  });
  // Hurenkinder und Schusterjungen: geteilte Absätze mit nur einer Zeile auf einer Seite
  let einzel = 0; const einzelbloecke = [];
  document.querySelectorAll('p[data-split-to], p[data-split-from]').forEach(p => {
    const cs = getComputedStyle(p);
    const lh = parseFloat(cs.lineHeight); const innen = p.getBoundingClientRect().height - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom);
    const z = Math.round(innen / lh);
    if (z < 2) { einzel++; fehler.push('Einzelzeile eines geteilten Absatzes auf S ' + seiteVon(p) + ' (' + (p.dataset.b || '?') + ')'); if (p.dataset.b) einzelbloecke.push(p.dataset.b); }
  });
  // Blocksatz einheitlich: mehrzeiliger Lauftext steht nie im Flattersatz
  document.querySelectorAll('.kapitel p, .kapitel li').forEach(el => {
    if (el.closest('table, figure, .quellen, .zitat, .merkband, .kindex, .schema-titel, .belege, .rechenweg-block, .formel-block')) return;
    const lh = parseFloat(getComputedStyle(el).lineHeight);
    if (el.getBoundingClientRect().height > 1.6 * lh && getComputedStyle(el).textAlign !== 'justify')
      fehler.push('Flattersatz statt Blocksatz auf S ' + seiteVon(el) + ': ' + el.textContent.trim().slice(0, 40));
  });
  // Anriss (nach der Kit-Regel aus umbruch.js, für den Buchsatz verschärft): Ein Abschnitt beginnt nicht am Seitenfuß.
  // Läuft er auf die nächste Seite weiter, muss sein Kopf in den oberen zwei Dritteln stehen, sein Anfang also mindestens
  // ein Drittel des Satzspiegels füllen (Kit: ein Fünftel für Kacheln); sonst beginnt er auf der neuen Seite.
  const anfaenge = [];
  document.querySelectorAll('.abschnitt').forEach(sec => {
    const kopf = sec.querySelector('.abkopf');
    if (!kopf || !kopf.getBoundingClientRect().height) return;
    const pg = kopf.closest('.pagedjs_page'), area = pg.querySelector('.pagedjs_area').getBoundingClientRect();
    const geteilt = sec.hasAttribute('data-split-to') || (sec.dataset.ref && document.querySelectorAll('[data-ref="' + sec.dataset.ref + '"]').length > 1);
    const rest = mm(area.bottom - kopf.getBoundingClientRect().top), mindest = ANRISS * mm(area.height);
    anfaenge.push({ code: sec.dataset.code || '', seite: +pg.dataset.pageNumber, rest_mm: Math.round(rest), mindest_mm: Math.round(mindest), geteilt: !!geteilt });
    if (geteilt && rest < mindest) {
      fehler.push('Abschnitt ' + (sec.dataset.code || '?') + ' beginnt am Seitenfuß S ' + pg.dataset.pageNumber + ' (' + Math.round(rest) + ' mm, Mindestmaß ' + Math.round(mindest) + ' mm)');
      if (sec.dataset.code && !kopfunten.includes(sec.dataset.code + '~0')) kopfunten.push(sec.dataset.code + '~0');
    }
  });
  const folge = [...document.querySelectorAll('.abschnitt[data-code]')].map(e => e.dataset.code);
  kopfunten.sort((a, b) => folge.indexOf(a.slice(0, -2)) - folge.indexOf(b.slice(0, -2)));  // Lesefolge: der früheste zuerst
  // Verweise mit Seitenzahl müssen ein Ziel haben
  document.querySelectorAll('a.vw').forEach(a => { if (!document.querySelector(a.getAttribute('href'))) fehler.push('Verweis ohne Ziel: ' + a.getAttribute('href')); });
  const geteilt = document.querySelectorAll('p[data-split-from]').length;
  // Korrekturkandidaten: Lücke vor einer Einbettung (Gleiten) und Fußnote auf der Folgeseite (Umbruch)
  const gleiten = [], umbruch = [];
  const pages = [...document.querySelectorAll('.pagedjs_page')];
  pages.forEach((pg, i) => {
    const s = seiten[i]; const naechste = pages[i + 1];
    if (!naechste || s.leer_mm < 18) return;
    const erstes = naechste.querySelector('.pagedjs_page_content [data-b]');
    if (erstes && erstes.matches('.einbettung, .tab') && !erstes.hasAttribute('data-split-from')) gleiten.push(erstes.dataset.b);
  });
  document.querySelectorAll('[data-footnote-call]').forEach(c => {
    const ref = c.getAttribute('data-footnote-call');
    const note = document.querySelector('.pagedjs_footnote_area [data-ref="' + ref + '"], .pagedjs_footnote_area [data-id="' + ref + '"]') || document.querySelector('[data-footnote-marker="' + ref + '"]');
    if (note && seiteVon(note) !== seiteVon(c)) { const b = c.closest('[data-b]'); if (b) umbruch.push(b.dataset.b.split(' ')[0]); }
  });
  return { fehler, warn, anker, seiten, geteilte_absaetze: geteilt, einzelzeilen: einzel, gleiten, umbruch, einzelbloecke, kopfunten, teilung, labelunten, anfaenge };
}"""
PRUEF_JS = PRUEF_JS.replace("%ANRISS%", f"{ANRISS:.6f}")



def setze(bauen, pdf_pfad, satzordner, werk_ref, laeufe=16):
    """bauen(plan) → HTML. Bis zu `laeufe` Korrekturläufe: Einbettungen gleiten hinter folgenden Text, wenn vor ihnen
    eine Lücke bliebe; Absätze mit einer Fußnote, die auf die Folgeseite geriete, beginnen auf der neuen Seite."""
    from playwright.sync_api import sync_playwright

    class Stumm(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Stumm, directory="/"))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    basis = f"http://127.0.0.1:{srv.server_address[1]}"
    pfad = satzordner / "buch_satz.html"
    plan, protokoll = {"gleiten": {}, "umbruch": set(), "laufweite": {}, "anker": {}}, []
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            konsole = []
            for lauf in range(1, laeufe + 1):
                pfad.write_text(bauen(plan).replace("§BASIS§", basis), encoding="utf-8")
                pg = br.new_page()
                pg.on("console", lambda m: konsole.append(m.text) if m.type in ("error", "warning") else None)
                pg.goto(basis + str(pfad))
                pg.wait_for_function("window.__fertig === true", timeout=180_000)
                pg.evaluate("document.fonts.ready")
                bericht = pg.evaluate(PRUEF_JS)
                neu = False
                for bid in bericht["gleiten"]:
                    kap = next((k for k in werk_ref.werk["kapitel"] + [rep_kapitel(werk_ref.werk)] if k and bid.startswith(k["code"])), None)
                    if kap and gleiten_moeglich(kap, plan, bid) and plan["gleiten"].get(bid, 0) < GLEITEN_MAX:
                        plan["gleiten"][bid] = plan["gleiten"].get(bid, 0) + 1
                        protokoll.append(f"Lauf {lauf}: {bid} gleitet hinter den folgenden Text")
                        neu = True
                geglitten = neu  # Seitenwechsel und Laufweite erst, wenn die Gleitobjekte ruhen (sonst greifen sie auf veraltetem Umbruch)
                for bid in ([] if geglitten else bericht["einzelbloecke"]):  # Einzelzeile: Laufweite des Absatzes ausgleichen, erst enger, dann weiter
                    stufe = plan["laufweite"].get(bid)
                    nxt = {None: "eng", "eng": "weit"}.get(stufe)
                    if nxt:
                        plan["laufweite"][bid] = nxt
                        protokoll.append(f"Lauf {lauf}: {bid} Laufweite {nxt} (Einzelzeile vermeiden)")
                        neu = True
                    elif bid not in plan["umbruch"] and not bid.endswith("~0"):
                        plan["umbruch"].add(bid)
                        protokoll.append(f"Lauf {lauf}: {bid} beginnt neue Seite (Einzelzeile trotz Laufweite)")
                        neu = True
                for bid in ([] if geglitten else bericht["teilung"]):  # angeschnittene Einbettung: beginnt auf neuer Seite
                    if bid not in plan["umbruch"]:
                        plan["umbruch"].add(bid)
                        protokoll.append(f"Lauf {lauf}: Einbettung {bid} beginnt neue Seite (sonst angeschnitten)")
                        neu = True
                # Abschnitt am Seitenfuß (Kopf allein oder Anriss): beginnt auf neuer Seite. Je Lauf nur der erste in Lesefolge
                # je Kapitel, denn jeder Wechsel verschiebt die folgenden Anfänge desselben Kapitels; Kapitel beginnen stets auf
                # neuer Seite und beeinflussen einander daher nicht (4.0: alle Kapitel im selben Lauf).
                kapitel_gesehen = set()
                for bid in ([] if geglitten else bericht["kopfunten"]):
                    if bid not in plan["umbruch"] and bid[0] not in kapitel_gesehen:
                        plan["umbruch"].add(bid)
                        kapitel_gesehen.add(bid[0])
                        protokoll.append(f"Lauf {lauf}: Abschnitt {bid[:-2]} beginnt neue Seite (Anfang am Seitenfuß)")
                        neu = True
                for bid in ([] if geglitten else bericht["labelunten"]):  # Spitzmarke ohne Inhalt am Seitenfuß: Baustein beginnt auf neuer Seite
                    if bid not in plan["umbruch"]:
                        plan["umbruch"].add(bid)
                        protokoll.append(f"Lauf {lauf}: {bid} beginnt neue Seite (Spitzmarke am Seitenfuß)")
                        neu = True
                for bid in ([] if geglitten else bericht["umbruch"]):
                    if plan["laufweite"].get(bid) != "weit":
                        plan["laufweite"][bid] = "weit"
                        protokoll.append(f"Lauf {lauf}: {bid} Laufweite weit (Fußnote zu ihrem Zeichen bringen)")
                        neu = True
                        continue
                    if bid not in plan["umbruch"]:
                        plan["umbruch"].add(bid)
                        protokoll.append(f"Lauf {lauf}: {bid} beginnt neue Seite (Fußnote bei ihrem Zeichen)")
                        neu = True
                rg = lambda a: {k: v for k, v in (a or {}).items() if k.startswith("rg-") or k.startswith("abb-")}
                if not neu and rg(plan.get("anker")) != rg(bericht["anker"]):
                    plan["anker"] = bericht["anker"]  # Register und Verzeichnisse mit den Seiten dieses Laufs neu setzen
                    protokoll.append(f"Lauf {lauf}: Register mit Seitenzahlen gesetzt")
                    neu = True
                elif neu:
                    plan["anker"] = bericht["anker"]
                if not neu or lauf == laeufe:
                    break
                pg.close()
            # Rückbau: jeder erzwungene Seitenwechsel wird ohne ihn erneut gesetzt; er bleibt nur, wenn er Fehler verhindert
            # oder weniger Leerraum ergibt (frühere Korrekturen können ihn überflüssig gemacht haben)
            def leer(b):
                return sum(x["leer_mm"] for x in b["seiten"][1:-1])
            geprobt = bool(plan["umbruch"])
            for bid in sorted(plan["umbruch"]):
                probe = {**plan, "umbruch": plan["umbruch"] - {bid}}
                pfad.write_text(bauen(probe).replace("§BASIS§", basis), encoding="utf-8")
                pg.close()
                pg = br.new_page()
                pg.goto(basis + str(pfad))
                pg.wait_for_function("window.__fertig === true", timeout=180_000)
                pg.evaluate("document.fonts.ready")
                b2 = pg.evaluate(PRUEF_JS)
                if len(b2["fehler"]) <= len(bericht["fehler"]) and leer(b2) < leer(bericht) - 15:
                    plan = probe
                    bericht = b2
                    protokoll.append(f"Rückbau: Seitenwechsel vor {bid} entfällt ({leer(bericht)} mm Leerraum)")
            if geprobt:  # die geladene Seite ist die letzte Probe: mit dem endgültigen Plan neu setzen
                pfad.write_text(bauen(plan).replace("§BASIS§", basis), encoding="utf-8")
                pg.close()
                pg = br.new_page()
                pg.goto(basis + str(pfad))
                pg.wait_for_function("window.__fertig === true", timeout=180_000)
                pg.evaluate("document.fonts.ready")
                bericht = pg.evaluate(PRUEF_JS)
            bericht["konsole"] = konsole
            bericht["korrekturen"] = protokoll
            bericht["laeufe"] = lauf
            bericht["fehler"] += pg.evaluate(TITEL_JS)  # vor RAHMEN_JS: Kopf- und Fußzeilen gehören nicht zur Titelseite
            rahmen = pg.evaluate(RAHMEN_JS, werk_ref.rahmen)
            bericht["seitenanfaenge"], bericht["rand"] = rahmen["seitenanfaenge"], rahmen["rand"]
            bericht["fehler"] += rahmen["rand"]["fehler"]
            if rahmen["rand"]["max_versatz_mm"] > RAND_VERSATZ_MAX:
                bericht["warn"].append(f"Randbeleg bis {rahmen['rand']['max_versatz_mm']} mm von seiner Zeile verschoben (Belege bündeln)")
            bericht["fonts"] = pg.evaluate("[...document.fonts].filter(f => f.status === 'loaded').map(f => f.family + ' ' + f.weight + ' ' + f.style)")
            satzordner.joinpath("buch_satz_gesetzt.html").write_text(pg.content(), encoding="utf-8")
            pg.pdf(path=str(pdf_pfad), prefer_css_page_size=True, print_background=True, tagged=True)
            br.close()
    finally:
        srv.shutdown()
    return bericht


def metadaten_und_lesezeichen(pdf_pfad, werk, s, anker):
    from pypdf import PdfReader, PdfWriter
    w = PdfWriter(clone_from=PdfReader(str(pdf_pfad)))
    m = werk["meta"]
    w.add_metadata({"/Title": f'{m["titel"]} · {m["untertitel"]}', "/Author": VERMERK,
                    "/Subject": f'Lernskript{" (Probesatz)" if m.get("probesatz") else ""}, Stand {stand_text(werk)}, Version {m["version"]}',
                    "/Keywords": ", ".join(["Terra", m["titel"], werk["modul"]["domaene"]] + [k["name_de"] for k in werk["kapitel"]]),
                    "/Creator": f"Terra-Kit {satz.VERSION}, skript.py", "/Copyright": VERMERK})
    fehlend = []

    def ein(titel, ziel, eltern=None):
        if ziel not in anker:
            fehlend.append(ziel)
            return None
        return w.add_outline_item(titel, anker[ziel] - 1, parent=eltern)
    # Gliederung wie satz.lesezeichen_plan: Titelei, Provinzen mit Codes (L mit den generierten Abschnitten), Anhang mit Abbildungen
    for ziel, titel in (("t-inhalt", "Inhalt"), ("t-gebrauch", "Zum Gebrauch"), ("t-abk", "Abkürzungen")):
        ein(titel, ziel)
    for k in werk["kapitel"]:
        kp = ein(f'{k["code"]} · {k.get("name_lat", k["name_de"])}', f'p-{k["code"]}')
        for a in k["abschnitte"]:
            ein(f'{a["code"]} {re.sub(r"[*_]", "", a["titel"])}', f'k-{a["code"]}', kp)
        if k.get("abschluss"):
            ein(f'{k["code"]}·Ü Auf einen Blick', f'k-{k["code"]}U', kp)
        if any(b["typ"] == "kernsatz" for a in k["abschnitte"] for b in a["bloecke"]):
            ein(f'Kernfakten · Provinz {k["nr"]}', f'kern-{k["code"]}', kp)
    if werk.get("repetitorium"):
        r = werk["repetitorium"]
        lp = ein(f'L · {r["name_lat"]}', "p-L")
        for c, t in GEN:
            if gen_vorhanden(werk, c):
                ein(f"L·{c[1]} {t}", f"k-{c}", lp)
    av = ein("Abbildungsverzeichnis", "t-abbildungen")
    for _, _, _, bl in listen(werk):
        for b in bl:
            if b["typ"] == "abbildung":
                ein(f'Abb {s.nummer[("abb", b["id"])]} {re.sub(r"[*_]", "", b["titel"])}', f'abb-{b["id"]}', av)
    ein("Quellenverzeichnis", "t-quellen")
    ein("Sachregister", "t-register")
    w.page_mode = "/UseOutlines"
    with open(pdf_pfad, "wb") as f:
        w.write(f)
    return fehlend


def vermerk_pruefen(pdf_pfad):
    """Jede Seite trägt den Urhebervermerk im Text (Fußzeile oder Titelseite); Metadaten tragen ihn als Autor."""
    from pypdf import PdfReader
    r = PdfReader(str(pdf_pfad))
    fehler = []
    for i in range(len(r.pages)):
        t = subprocess.run(["pdftotext", "-f", str(i + 1), "-l", str(i + 1), str(pdf_pfad), "-"], capture_output=True, text=True).stdout
        if VERMERK not in t:
            fehler.append(f"Seite {i + 1} ohne Vermerk „{VERMERK}“")
    if (r.metadata or {}).get("/Author") != VERMERK:
        fehler.append("PDF-Metadaten ohne Vermerk als Autor")
    return fehler, len(r.pages)


def vorbereiten(werk, ordner=None):
    """Nach der Prüfung, vor dem Satz (nur im Speicher): verknüpfte Bilder einbetten, automatische Quellenkritik
    aus Rechenproben mit abweichender Quelle ergänzen. Mehrfacher Aufruf schadet nicht."""
    satz.bilder_laden(werk, ordner)
    kritik = werk.setdefault("quellenkritik", [])
    for e in rechenprobe.kritik(werk):
        if e not in kritik:
            kritik.append(e)
    if not kritik:
        werk.pop("quellenkritik")
    return werk


def main():
    ap = argparse.ArgumentParser(description="(c) Oliver Bedernik · Terra-Kit 4.0 · Lernskript im Buchsatz")
    ap.add_argument("werk")
    ap.add_argument("--aus", default="ausgabe")
    ap.add_argument("--nur-pruefen", action="store_true")
    ap.add_argument("--laeufe", type=int, default=24, help="höchstens so viele Korrekturläufe (Probe: 1)")
    arg = ap.parse_args()
    werk = json.loads(Path(arg.werk).read_text(encoding="utf-8"))
    fehler, warn = pruefe(werk, Path(arg.werk).resolve().parent)
    for f in fehler:
        print("FEHLER  ", f)
    for x in warn:
        print("WARNUNG ", x)
    print(f"Prüfung: {len(fehler)} Fehler, {len(warn)} Warnungen")
    if fehler:
        sys.exit(1)
    aus = Path(arg.aus).resolve()
    aus.mkdir(parents=True, exist_ok=True)
    (aus / "nahtliste.md").write_text(nahtliste(werk), encoding="utf-8")
    if arg.nur_pruefen:
        return
    satz.SEITENVERWEIS = False
    vorbereiten(werk, Path(arg.werk).resolve().parent)
    s = Satz(werk)
    m = werk["meta"]
    name = "Terra_" + "_".join(m["titel"].split()[1:]) + f'_{"Probesatz" if m.get("probesatz") else "Lernskript"}_v{m["version"]}_{m["stand"]}'
    pdf = aus / f"{name}.pdf"
    bericht = setze(lambda plan: dokument(werk, s, "§BASIS§", plan), pdf, aus, s, laeufe=arg.laeufe)
    bericht["fehler"] += [f"Lesezeichen ohne Ziel: {z}" for z in metadaten_und_lesezeichen(pdf, werk, s, bericht["anker"])]
    vf, n = vermerk_pruefen(pdf)
    bericht["fehler"] += vf
    bericht["warn"] += warn
    abb_seiten = [x["seite"] for x in bericht["seiten"] if x["abb"]]
    satz.kontaktabzug(pdf, aus / f"{name}_kontakt.png", markiert=abb_seiten)
    bericht.pop("anker")
    (aus / f"{name}_bericht.json").write_text(json.dumps(bericht, ensure_ascii=False, indent=1), encoding="utf-8")
    text = [x for x in bericht["seiten"] if x["art"] == "text"]
    for z in bericht["korrekturen"]:
        print("SATZ    ", z)
    print(f'Satz: {n} Seiten · {bericht["geteilte_absaetze"]} geteilte Absätze · {bericht["einzelzeilen"]} Einzelzeilen'
          f' · Leerraum je Textseite: ' + ", ".join(f'S {x["seite"]} {x["leer_mm"]} mm' for x in text))
    r = bericht["rand"]
    print(f'Randbelege: {r["anzahl"]} auf {len(r["seiten"])} Seiten · {len(r["belege"])} Randstellen · größter Versatz {r["max_versatz_mm"]} mm')
    for f in bericht["fehler"]:
        print("FEHLER  ", f)
    for k in bericht["konsole"]:
        print("KONSOLE ", k[:160])
    print(f'Ergebnis: {len(bericht["fehler"])} Fehler, {len(bericht["warn"])} Warnungen · {pdf}')
    sys.exit(1 if bericht["fehler"] else 0)


if __name__ == "__main__":
    main()
