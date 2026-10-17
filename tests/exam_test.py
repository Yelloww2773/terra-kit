# (c) Oliver Bedernik · Terra-Kit · Browsertest der interaktiven Prüfung
# Aufruf: python3 exam.py exam.json werk.json --lokal --aus /tmp/e && python3 tests/exam_test.py /tmp/e/<datei>_lokal.html exam.json [Bildpräfix]
import json, sys
from playwright.sync_api import sync_playwright
datei, exam_pfad = sys.argv[1], sys.argv[2]
pref = sys.argv[3] if len(sys.argv) > 3 else "exam"
exam = json.load(open(exam_pfad, encoding="utf-8"))
loes = {f["id"]: [o["id"] for o in f["optionen"] if o["richtig"]] for f in exam["fragen"]}
N = len(exam["fragen"]); fehler = []; erg = {}
with sync_playwright() as p:
    b = p.chromium.launch(args=["--allow-file-access-from-files"])
    ctx = b.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: fehler.append(str(e))); pg.on("console", lambda m: fehler.append(m.text) if m.type == "error" else None)
    pg.goto("file://" + datei); pg.wait_for_function("window.__exam && window.__exam.bereit"); pg.wait_for_timeout(300)
    pg.screenshot(path=f"{pref}_1_start.png", full_page=True)
    pg.click("#b-beginnen"); pg.wait_for_timeout(150)
    erg["uhr_sichtbar"] = pg.is_visible("#uhr")
    # Frage 1 richtig, Frage 2 falsch, Frage 3 markieren
    for oid in loes["q1"]: pg.click(f"#fkarte input[value={oid}] >> xpath=..")
    pg.click("#b-weiter")
    falsch = [o for o in "abcd" if o not in loes["q2"]][0]
    pg.click(f"#fkarte input[value={falsch}] >> xpath=..")
    pg.click("#b-weiter"); pg.click("#b-markieren")
    pg.screenshot(path=f"{pref}_2_frage.png", full_page=True)
    pg.click("#b-uebersicht"); pg.wait_for_timeout(150)
    erg["raster"] = pg.evaluate("[...document.querySelectorAll('#raster button')].slice(0,3).map(b=>b.className.trim())")
    pg.screenshot(path=f"{pref}_3_uebersicht.png"); pg.keyboard.press("Escape")
    pg.click("#b-abgeben"); pg.wait_for_timeout(100)
    erg["abgabe_hinweis"] = pg.inner_text("#abgabe-text")[:90]
    pg.click("#d-abgabe .dknoepfe .schliessen")
    # Neuladen und fortsetzen
    pg.reload(); pg.wait_for_function("window.__exam && window.__exam.bereit")
    erg["fortsetzen_sichtbar"] = pg.is_visible("#b-fortsetzen")
    pg.click("#b-fortsetzen"); pg.wait_for_timeout(100)
    z = pg.evaluate("window.__exam.zustand()")
    erg["nach_neuladen"] = {"frage": z["idx"] + 1, "q1": z["antworten"].get("q1"), "markiert": z["markiert"]}
    # Alle übrigen richtig beantworten (ausser q2), abgeben
    pg.evaluate("""l => { const Z = window.__exam.zustand(); for (const [k, v] of Object.entries(l)) if (k !== 'q2') Z.antworten[k] = v; }""", loes)
    pg.evaluate("window.__exam.auswerten(false)"); pg.wait_for_timeout(200)
    erg["urteil"] = pg.inner_text("#urteil .lat"); erg["punkte"] = pg.inner_text("#urteil .zahl")
    pg.screenshot(path=f"{pref}_4_ergebnis.png")
    pg.click("#f-falsch"); pg.wait_for_timeout(100)
    erg["nur_falsche"] = pg.evaluate("document.querySelectorAll('#durchsicht .fkarte').length")
    erg["markierungen_q2"] = pg.evaluate("[...document.querySelectorAll('#durchsicht .dopt')].map(d=>d.className.replace('dopt','').trim()).join(',')")
    pg.screenshot(path=f"{pref}_5_durchsicht.png", full_page=True)
    # Modus Durum
    pg.click("#b-nochmal"); pg.check("#o-durum"); pg.click("#b-beginnen"); pg.wait_for_timeout(100)
    erg["durum_nur_checkboxen"] = pg.evaluate("[...document.querySelectorAll('#fkarte input')].every(i=>i.type==='checkbox')")
    erg["durum_typ"] = pg.inner_text("#fkarte .ftyp")
    # Zeitablauf: Ende in die Vergangenheit setzen, neu laden
    pg.evaluate("""() => { const k = Object.keys(localStorage).find(x => x.startsWith('terra-exam:')); const z = JSON.parse(localStorage.getItem(k)); z.endet = Date.now() - 1000; localStorage.setItem(k, JSON.stringify(z)); }""")
    pg.reload(); pg.wait_for_function("window.__exam && window.__exam.bereit"); pg.wait_for_timeout(200)
    erg["zeitablauf"] = pg.inner_text("#urteil .hinweis")[-80:]
    # Dunkelmodus
    pg.evaluate("document.documentElement.setAttribute('data-theme','dark')"); pg.click("#f-alle"); pg.wait_for_timeout(100)
    pg.screenshot(path=f"{pref}_6_dunkel.png")
    # Mobil
    m = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True).new_page()
    m.on("pageerror", lambda e: fehler.append("mobil: " + str(e)))
    m.goto("file://" + datei); m.wait_for_function("window.__exam && window.__exam.bereit")
    m.click("#b-beginnen"); m.wait_for_timeout(150); m.screenshot(path=f"{pref}_7_mobil.png")
    erg["mobil_ueberlauf"] = m.evaluate("document.documentElement.scrollWidth > innerWidth")
    erg["mobil_kleine_ziele"] = m.evaluate("""[...document.querySelectorAll('button, .opt')].filter(e=>{const r=e.getBoundingClientRect(); return r.width && r.height && (r.height<44)}).map(e=>e.id||e.className).slice(0,5)""")
    b.close()
erg["konsolenfehler"] = fehler
print(json.dumps(erg, ensure_ascii=False, indent=1))
