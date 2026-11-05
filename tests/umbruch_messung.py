#!/usr/bin/env python3
"""(c) Oliver Bedernik · Terra-Kit · tests/umbruch_messung.py

Misst den Seitenumbruch eines gesetzten Lernskripts, unabhängig von der Kit-Version,
damit Vorher und Nachher identisch gemessen werden (seit 3.6.0).

    python3 tests/umbruch_messung.py werk.json [--kit ORDNER] [--aus ORDNER] [--json DATEI]

Ohne --kit wird mit dem Kit gesetzt, in dem dieses Skript liegt. Gemessen wird am
montierten HTML (Montage blockiert, Satz unverändert) und am PDF:

  Seiten           Seitenzahl des PDF
  Fortsetzungen    Kachelteile, die eine Kachel von der Vorseite fortsetzen
  Kleinreste       letzter Kachelteil auf der Folgeseite aus einem einzigen Baustein, niedriger als
                   20 % des Satzspiegels (etwa nur das Latinum)
  Anrisse          erster Kachelteil am Seitenende aus Kopf und einem Baustein, niedriger als 20 %
  Füllstand        Unterkante des letzten Inhalts im Satzspiegel; Durchschnitt über die
                   Inhaltsseiten (Art normal oder quer, mit Provinzkopf oder Kachel)
  unter 50 / 60 %  Inhaltsseiten unter der Schwelle, ausgenommen die letzte Seite vor einem
                   festen Umbruch (neue Provinz, Anhang, Seitenartwechsel, Werkende)
  Grafikschrift    kleinste Schrift je Abbildung in pt (ohne Wasserzeichen)
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

KIT_HIER = Path(__file__).resolve().parent.parent
SCHWELLE_KLEIN = 0.20

MESS_JS = r"""
() => {
  const px2mm = 25.4 / 96;
  const seiten = Array.from(document.querySelectorAll('#buch > .page'));
  const art = p => ['deck', 'titelei', 'spalten', 'quer'].find(x => p.classList.contains(x)) || 'normal';
  const out = [];
  seiten.forEach((p, i) => {
    const k = p.querySelector('.koerper'); const kb = k.getBoundingClientRect();
    let unten = kb.top;
    for (const c of k.children) for (const r of c.getClientRects()) unten = Math.max(unten, r.bottom);
    const naechste = seiten[i + 1];
    const ersteNaechste = naechste ? naechste.querySelector('.koerper .unit') : null;
    const fest = !naechste || art(naechste) !== art(p) || (ersteNaechste && ersteNaechste.dataset.neueSeite === '1');
    const teile = Array.from(k.querySelectorAll(':scope > .kachel')).map(e => ({
      code: e.dataset.code, fortsetzung: e.classList.contains('fortsetzung'), offen: e.classList.contains('offen-unten'),
      hoehe: e.getBoundingClientRect().height / kb.height, einheiten: e.querySelectorAll(':scope > .unit').length }));
    const figs = Array.from(p.querySelectorAll('.fig')).map(f => {
      let min = null;
      f.querySelectorAll('svg text').forEach(t => {
        if (t.classList.contains('t-wz')) return;
        const fs = parseFloat(getComputedStyle(t).fontSize); const m = t.getScreenCTM();
        if (!m || !fs) return;
        const pt = fs * Math.hypot(m.a, m.b) * 0.75;
        if (min === null || pt < min) min = pt;
      });
      const kachel = f.closest('.kachel');
      return { kachel: kachel ? kachel.dataset.code : null, hoehe_mm: +(f.getBoundingClientRect().height * px2mm).toFixed(1),
               skala: f.dataset.skala ? +f.dataset.skala : null, min_pt: min === null ? null : +min.toFixed(2) };
    });
    out.push({ nr: i + 1, art: art(p), inhalt: !!k.querySelector('.kachel, .provkopf'), fest,
               fuell: (unten - kb.top) / kb.height, teile, figs });
  });
  return out;
}
"""


def setze(werk, kit, aus):
    t0 = time.time()
    r = subprocess.run([sys.executable, str(kit / "skript.py"), str(werk), "--aus", str(aus)],
                       capture_output=True, text=True, cwd=str(kit))
    dauer = time.time() - t0
    bericht = next(aus.glob("*_bericht.json"), None)
    if bericht is None:
        sys.exit("Satz gescheitert:\n" + r.stdout[-2000:] + r.stderr[-2000:])
    return json.loads(bericht.read_text(encoding="utf-8")), dauer, r.stdout


def miss_dom(montiert):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.launch(args=["--allow-file-access-from-files"])
        pg = br.new_page()
        pg.route("**/montage.js", lambda route: route.abort())
        pg.emulate_media(media="print")
        pg.goto(montiert.as_uri())
        pg.wait_for_load_state("load")
        pg.evaluate("document.fonts.ready.then(() => true)")
        daten = pg.evaluate(MESS_JS)
        br.close()
    return daten


def auswerten(seiten, bericht, pdf_seiten, dauer):
    inhalt = [s for s in seiten if s["art"] in ("normal", "quer") and s["inhalt"]]
    gueltig = [s for s in inhalt if s["fuell"] <= 1.001]
    fortsetzungen = sum(1 for s in seiten for t in s["teile"] if t["fortsetzung"])
    kleinreste = [f'{t["code"]} S {s["nr"]}' for s in seiten for t in s["teile"]
                  if t["fortsetzung"] and not t["offen"] and t["einheiten"] == 1 and t["hoehe"] < SCHWELLE_KLEIN]
    einbaustein = sum(1 for s in seiten for t in s["teile"] if t["fortsetzung"] and t["einheiten"] == 1)
    anrisse = [f'{t["code"]} S {s["nr"]}' for s in seiten for t in s["teile"]
               if not t["fortsetzung"] and t["offen"] and t["einheiten"] == 1 and t["hoehe"] < SCHWELLE_KLEIN]
    unter = lambda g: [s["nr"] for s in inhalt if s["fuell"] < g and not s["fest"]]
    figs = [f for s in seiten for f in s["figs"]]
    minpt = [f["min_pt"] for f in figs if f["min_pt"] is not None]
    return {
        "seiten": pdf_seiten,
        "inhaltsseiten": len(inhalt),
        "fortsetzungen": fortsetzungen,
        "fortsetzungen_ein_baustein": einbaustein,
        "kleinreste": kleinreste,
        "anrisse": anrisse,
        "fuellstand_mittel": round(sum(s["fuell"] for s in gueltig) / max(1, len(gueltig)), 3),
        "ueberlauf_seiten": [s["nr"] for s in inhalt if s["fuell"] > 1.001],
        "unter_50": unter(0.5),
        "unter_60": unter(0.6),
        "abbildungen": len(figs),
        "grafikschrift_min_pt": round(min(minpt), 2) if minpt else None,
        "grafiken_unter_6_5_pt": sorted({f["kachel"] or "?" for f in figs if f["min_pt"] is not None and f["min_pt"] < 6.5}),
        "fehler": len(bericht.get("fehler", [])),
        "warnungen": len(bericht.get("warnungen", [])),
        "fehlertexte": bericht.get("fehler", [])[:6],
        "dauer_s": round(dauer, 1),
    }


def main():
    ap = argparse.ArgumentParser(description="Umbruchmessung eines Terra-Lernskripts")
    ap.add_argument("werk")
    ap.add_argument("--kit", default=str(KIT_HIER))
    ap.add_argument("--aus", default=None)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    kit, werk = Path(a.kit).resolve(), Path(a.werk).resolve()
    aus = Path(a.aus).resolve() if a.aus else Path("/tmp/terra-messung") / (kit.name + "_" + werk.stem)
    aus.mkdir(parents=True, exist_ok=True)
    for f in aus.glob("*"):
        if f.is_file():
            f.unlink()
    bericht, dauer, _ = setze(werk, kit, aus)
    from pypdf import PdfReader
    pdf = next(aus.glob("*.pdf"))
    m = auswerten(miss_dom(next(aus.glob("*_montiert.html"))), bericht, len(PdfReader(str(pdf)).pages), dauer)
    m["kit"], m["werk"] = kit.name, werk.name
    print(json.dumps(m, ensure_ascii=False, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
