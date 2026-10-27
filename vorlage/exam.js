/* (c) Oliver Bedernik · Terra-Kit · exam.js · interaktive Prüfung (Standard 3.1)
   Ablauf: Start (Zeitlimit, Modus Durum) → Fragen (Navigation, Markieren, Übersicht) →
   Abgabe (Bestätigung, Hinweis auf Offenes) → Auswertung (Urteil, Provinzen, Durchsicht).
   Fortschritt im Browser gespeichert. Ein Punkt nur bei vollständig richtiger Auswahl. */
(function () {
  'use strict';
  const D = JSON.parse(document.getElementById('exam-daten').textContent);
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const SCHLUESSEL = 'terra-exam:' + D.schluessel;
  const N = D.fragen.length;
  let Z = null, uhrTakt = null;

  const leer = () => ({ phase: 'start', modus: { zeit: true, durum: false }, start: 0, endet: 0, antworten: {}, markiert: [], idx: 0, ergebnis: null });
  const speichern = () => { try { localStorage.setItem(SCHLUESSEL, JSON.stringify(Z)); } catch (e) {} };
  function laden() { try { const v = localStorage.getItem(SCHLUESSEL); return v ? JSON.parse(v) : null; } catch (e) { return null; } }

  /* Thema */
  const THEMEN = ['auto', 'light', 'dark'], THEMA_TXT = { auto: 'Automatisch', light: 'Hell', dark: 'Dunkel' };
  let thema = 'auto'; try { thema = localStorage.getItem('terra:thema') || 'auto'; } catch (e) {}
  function setzeThema(t) {
    if (t === 'auto') document.documentElement.removeAttribute('data-theme'); else document.documentElement.setAttribute('data-theme', t);
    $$('.k-thema').forEach(k => { k.title = 'Darstellung: ' + THEMA_TXT[t]; k.setAttribute('aria-label', k.title); });
    try { localStorage.setItem('terra:thema', t); } catch (e) {}
  }
  setzeThema(thema);
  $$('.k-thema').forEach(k => k.addEventListener('click', () => { thema = THEMEN[(THEMEN.indexOf(thema) + 1) % 3]; setzeThema(thema); }));

  function schirm(id) {
    $$('.schirm').forEach(s => { s.hidden = s.id !== id; });
    $('#ekopf').hidden = id !== 's-frage';
    window.scrollTo(0, 0);
  }

  /* ── Start ─────────────────────────────────────────────────────── */
  function zeigeStart() {
    const alt = laden();
    const laeuft = alt && alt.phase === 'laeuft', fertig = alt && alt.phase === 'fertig';
    $('#b-fortsetzen').hidden = !laeuft;
    $('#b-ergebnis').hidden = !fertig;
    $('#b-beginnen').textContent = laeuft || fertig ? 'Neu beginnen' : 'Prüfung beginnen';
    $('#gespeichert').hidden = !laeuft;
    if (laeuft) {
      const n = Object.keys(alt.antworten).filter(k => alt.antworten[k].length).length;
      $('#gespeichert').textContent = 'Gespeicherter Versuch: ' + n + ' von ' + N + ' Fragen beantwortet' +
        (alt.modus.zeit ? ', Restzeit ' + format(Math.max(0, alt.endet - Date.now())) : '') + '.';
    }
    schirm('s-start');
  }
  $('#b-beginnen').addEventListener('click', () => {
    const alt = laden();
    if (alt && alt.phase === 'laeuft' && !confirm('Der gespeicherte Versuch wird verworfen. Neu beginnen?')) return;
    Z = leer();
    Z.modus.zeit = $('#o-zeit').checked; Z.modus.durum = $('#o-durum').checked;
    Z.phase = 'laeuft'; Z.start = Date.now(); Z.endet = Z.start + D.minuten * 60000;
    speichern(); starteUhr(); zeigeFrage(0);
  });
  $('#b-fortsetzen').addEventListener('click', () => { Z = laden(); starteUhr(); zeigeFrage(Z.idx || 0); });
  $('#b-ergebnis').addEventListener('click', () => { Z = laden(); zeigeErgebnis(); });

  /* ── Uhr ───────────────────────────────────────────────────────── */
  function format(ms) { const s = Math.ceil(ms / 1000), m = Math.floor(s / 60); return m + ':' + String(s % 60).padStart(2, '0'); }
  function starteUhr() {
    clearInterval(uhrTakt);
    $('#uhr').hidden = !Z.modus.zeit;
    if (!Z.modus.zeit) return;
    const tick = () => {
      const rest = Z.endet - Date.now();
      $('#uhr').textContent = format(Math.max(0, rest));
      $('#uhr').classList.toggle('knapp', rest < 5 * 60000);
      if (rest <= 0) { clearInterval(uhrTakt); auswerten(true); }
    };
    tick(); uhrTakt = setInterval(tick, 1000);
  }

  /* ── Frage ─────────────────────────────────────────────────────── */
  function zeigeFrage(i) {
    Z.idx = Math.max(0, Math.min(N - 1, i)); speichern();
    const f = D.fragen[Z.idx], p = D.provinzen[f.provinz];
    const mehrfach = Z.modus.durum || f.typ === 'mehrfach';
    const gew = Z.antworten[f.id] || [];
    const karte = $('#fkarte');
    karte.className = 'fkarte farbe-' + p.farbe;
    const typ = Z.modus.durum ? 'Durum: eine oder mehrere richtig' : (f.typ === 'mehrfach' ? 'Mehrfachauswahl: eine oder mehrere richtig' : 'Einfachauswahl: genau eine richtig');
    karte.innerHTML =
      '<div class="fkopf2"><span class="fnr">Frage ' + (Z.idx + 1) + '<small>von ' + N + '</small></span>' +
      '<span class="pchip">Provinz ' + p.nr + ' (' + f.provinz + ')</span><span class="ftyp">' + typ + '</span>' +
      (Z.markiert.includes(f.id) ? '<span class="fmarke">markiert</span>' : '') + '</div>' +
      (f.sv ? '<div class="fallbeispiel"><div class="fb-kopf">Sachverhalt</div><div class="fb-teil">' + f.sv + '</div></div>' : '') +
      '<p class="ftext" id="ftext">' + f.frage + '</p>' +
      '<div class="optionen" role="' + (mehrfach ? 'group' : 'radiogroup') + '" aria-labelledby="ftext">' +
      f.optionen.map(o => '<label class="opt ' + (mehrfach ? 'check' : 'radio') + (gew.includes(o.id) ? ' an' : '') + '">' +
        '<input type="' + (mehrfach ? 'checkbox' : 'radio') + '" name="o" value="' + o.id + '"' + (gew.includes(o.id) ? ' checked' : '') + '>' +
        '<span class="bu" aria-hidden="true">' + o.id + '</span><span>' + o.text + '</span></label>').join('') + '</div>';
    $$('input', karte).forEach(inp => inp.addEventListener('change', () => {
      const wahl = $$('input', karte).filter(x => x.checked).map(x => x.value);
      Z.antworten[f.id] = wahl; speichern();
      $$('.opt', karte).forEach(l => l.classList.toggle('an', l.querySelector('input').checked));
      fortschritt();
    }));
    $('#b-zurueck').disabled = Z.idx === 0;
    $('#b-weiter .lbl').textContent = Z.idx === N - 1 ? 'Zur Abgabe' : 'Weiter';
    $('#b-markieren').setAttribute('aria-pressed', String(Z.markiert.includes(f.id)));
    fortschritt(); schirm('s-frage');
  }
  function fortschritt() {
    const n = D.fragen.filter(f => (Z.antworten[f.id] || []).length).length;
    $('#balken i').style.width = (n / N * 100) + '%';
    $('#balken').setAttribute('aria-valuenow', String(n));
  }
  $('#b-zurueck').addEventListener('click', () => zeigeFrage(Z.idx - 1));
  $('#b-weiter').addEventListener('click', () => { if (Z.idx === N - 1) abgabeDialog(); else zeigeFrage(Z.idx + 1); });
  $('#b-markieren').addEventListener('click', () => {
    const id = D.fragen[Z.idx].id;
    Z.markiert = Z.markiert.includes(id) ? Z.markiert.filter(x => x !== id) : Z.markiert.concat(id);
    speichern(); zeigeFrage(Z.idx);
  });
  document.addEventListener('keydown', e => {
    if ($('#s-frage').hidden || document.querySelector('dialog[open]')) return;
    if (e.key === 'ArrowRight' && Z.idx < N - 1) zeigeFrage(Z.idx + 1);
    if (e.key === 'ArrowLeft' && Z.idx > 0) zeigeFrage(Z.idx - 1);
  });

  /* ── Übersicht und Abgabe ──────────────────────────────────────── */
  function uebersicht() {
    $('#raster').innerHTML = D.fragen.map((f, i) => {
      const k = [(Z.antworten[f.id] || []).length ? 'beantwortet' : '', Z.markiert.includes(f.id) ? 'markiert' : '', i === Z.idx ? 'aktuell' : ''].join(' ');
      return '<button class="' + k + '" data-i="' + i + '" aria-label="Frage ' + (i + 1) + '">' + (i + 1) + '</button>';
    }).join('');
    $('#d-uebersicht').showModal();
  }
  $('#raster').addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; $('#d-uebersicht').close(); zeigeFrage(+b.dataset.i); });
  $('#b-uebersicht').addEventListener('click', uebersicht);
  function abgabeDialog() {
    const offen = D.fragen.map((f, i) => (Z.antworten[f.id] || []).length ? null : i + 1).filter(Boolean);
    const mark = D.fragen.map((f, i) => Z.markiert.includes(f.id) ? i + 1 : null).filter(Boolean);
    let t = offen.length ? '<p><b>' + offen.length + ' Fragen sind unbeantwortet:</b> ' + offen.join(', ') + '. Unbeantwortete Fragen zählen null Punkte.</p>' : '<p>Alle Fragen sind beantwortet.</p>';
    if (mark.length) t += '<p><b>Markiert:</b> ' + mark.join(', ') + '.</p>';
    t += '<p>Nach der Abgabe sind keine Änderungen mehr möglich.</p>';
    $('#abgabe-text').innerHTML = t;
    $('#d-abgabe').showModal();
  }
  $('#b-abgeben').addEventListener('click', abgabeDialog);
  $$('dialog .schliessen').forEach(b => b.addEventListener('click', () => b.closest('dialog').close()));
  $('#b-abgabe-ok').addEventListener('click', () => { $('#d-abgabe').close(); auswerten(false); });

  /* ── Auswertung ────────────────────────────────────────────────── */
  const gleich = (a, b) => a.length === b.length && a.every(x => b.includes(x));
  /* Brücke Exam → Anki (3.4): Suchbegriff für die Kacheln aller falsch beantworteten Fragen */
  function ankiSuche() {
    const istRichtig = f => gleich(Z.antworten[f.id] || [], f.optionen.filter(o => o.richtig).map(o => o.id));
    const codes = [];
    D.fragen.forEach(f => { if (!istRichtig(f)) f.kacheln.forEach(c => { if (!codes.includes(c)) codes.push(c); }); });
    if (!codes.length || !D.anki_tag) return '';
    return 'tag:' + D.anki_tag + ' (' + codes.map(c => 'tag:Kachel::' + c).join(' or ') + ')';
  }
  function ankiBruecke() {
    const s = ankiSuche();
    if (!s) return '';
    return '<div class="anki-bruecke"><div class="lbl">In Anki wiederholen</div>'
      + '<p>Im Kartenbrowser suchen, danach „Karten neu planen“ oder ein gefiltertes Deck aus der Suche erstellen:</p>'
      + '<code id="anki-suche">' + s + '</code> <button type="button" id="anki-kopie" onclick="navigator.clipboard && navigator.clipboard.writeText(document.getElementById(\'anki-suche\').textContent).then(() => { this.textContent = \'kopiert\'; })">Kopieren</button></div>';
  }
  function auswerten(auto) {
    clearInterval(uhrTakt);
    const je = {};
    let punkte = 0;
    D.fragen.forEach(f => {
      const richtig = f.optionen.filter(o => o.richtig).map(o => o.id);
      const ok = gleich(Z.antworten[f.id] || [], richtig);
      if (ok) punkte++;
      je[f.provinz] = je[f.provinz] || { p: 0, n: 0 }; je[f.provinz].n++; if (ok) je[f.provinz].p++;
    });
    Z.phase = 'fertig'; Z.ergebnis = { punkte, je, auto, zeit: Date.now() - Z.start };
    speichern(); zeigeErgebnis();
  }
  function urteil(q) {
    if (q >= 0.9) return ['Summa cum laude', 'Hervorragend: Der Stoff sitzt auch in seinen Fallen.'];
    if (q >= 0.8) return ['Magna cum laude', 'Sehr gut: Einzelne Feinheiten nacharbeiten.'];
    if (q >= 0.7) return ['Cum laude', 'Gut: Die Struktur sitzt, die Abgrenzungen noch nicht durchgehend.'];
    if (q >= 0.6) return ['Rite', 'Bestanden: Die markierten Provinzen gezielt wiederholen.'];
    return ['Non sufficit', 'Noch nicht ausreichend: Mit den Provinzen beginnen, die unten am schwächsten ausfallen.'];
  }
  function zeigeErgebnis(nurFalsch) {
    const E = Z.ergebnis, q = E.punkte / N, [lat, satz] = urteil(q);
    $('#urteil').innerHTML = '<div class="lat">' + lat + '</div><div class="zahl"><b>' + E.punkte + '</b> von ' + N + ' Punkten · ' + Math.round(q * 100) + ' %</div>' +
      '<div class="hinweis">' + satz + (E.auto ? ' Die Prüfung wurde bei Ablauf der Zeit automatisch abgegeben.' : '') +
      (Z.modus.durum ? ' Modus Durum: Fragetyp verborgen.' : '') + '</div>';
    $('#provinzwertung').innerHTML = Object.keys(D.provinzen).filter(k => E.je[k]).map(k => {
      const p = D.provinzen[k], w = E.je[k];
      return '<div class="pw farbe-' + p.farbe + '" title="' + p.name + '"><i>' + p.nr + '</i><div class="bahn"><b style="width:' + (w.p / w.n * 100) + '%"></b></div><span>' + w.p + ' / ' + w.n + '</span></div>';
    }).join('');
    const liste = D.fragen.map((f, i) => {
      const richtig = f.optionen.filter(o => o.richtig).map(o => o.id), gew = Z.antworten[f.id] || [], ok = gleich(gew, richtig);
      if (nurFalsch && ok) return '';
      const p = D.provinzen[f.provinz];
      const opts = f.optionen.map(o => {
        const g = gew.includes(o.id);
        const k = g && o.richtig ? 'rg' : g && !o.richtig ? 'fg' : !g && o.richtig ? 'rn' : '';
        const wert = k === 'rg' ? 'richtig gewählt' : k === 'fg' ? 'falsch gewählt' : k === 'rn' ? 'richtig, nicht gewählt' : 'falsch, nicht gewählt';
        return '<div class="dopt ' + k + '"><div class="zeile"><span class="bu">' + o.id + '</span><span>' + o.text + '</span><span class="wert">' + wert + '</span></div>' +
          '<div class="beg">' + o.beg + (o.norm ? '<span class="norm">' + o.norm + '</span>' : '') + '</div></div>';
      }).join('');
      const karte = f.kacheln.map(c => D.karte_url ? '<a class="karteverweis" target="_blank" rel="noopener" href="' + D.karte_url + '#k-' + c + '">Karte: ' + c + ' ' + (D.kacheln[c] || '') + '</a>'
                                                   : '<span class="karteverweis">Karte: ' + c + ' ' + (D.kacheln[c] || '') + '</span>').join(' · ');
      const merke = f.merke ? '<div class="box merke"><div class="lbl">Merke</div>' + f.merke.text + '</div>' +
        (f.merke.lat ? '<div class="box latinum"><span class="lat">' + f.merke.lat + '</span><span class="de">' + (f.merke.de || '') + '</span></div>' : '') : '';
      return '<article class="fkarte farbe-' + p.farbe + '"><div class="fkopf2"><span class="fnr">Frage ' + (i + 1) + '</span>' +
        '<span class="pchip">Provinz ' + p.nr + ' (' + f.provinz + ')</span><span class="ftyp">' + (f.typ === 'mehrfach' ? 'Mehrfachauswahl' : 'Einfachauswahl') + '</span>' +
        '<span class="status ' + (ok ? 'ok' : 'nein') + '" style="margin-left:auto">' + (ok ? 'richtig, 1 Punkt' : 'nicht richtig, 0 Punkte') + '</span></div>' +
        (f.sv ? '<div class="fallbeispiel"><div class="fb-kopf">Sachverhalt</div><div class="fb-teil">' + f.sv + '</div></div>' : '') +
        '<p class="ftext">' + f.frage + '</p>' + opts + merke + '<div>' + karte + '</div></article>';
    }).join('');
    $('#durchsicht').innerHTML = (liste || '<p class="gespeichert">Keine falsch beantworteten Fragen. Gratulation.</p>') + ankiBruecke();
    $('#f-alle').setAttribute('aria-pressed', String(!nurFalsch)); $('#f-falsch').setAttribute('aria-pressed', String(!!nurFalsch));
    schirm('s-ergebnis');
  }
  $('#f-alle').addEventListener('click', () => zeigeErgebnis(false));
  $('#f-falsch').addEventListener('click', () => zeigeErgebnis(true));
  $('#b-nochmal').addEventListener('click', () => { try { localStorage.removeItem(SCHLUESSEL); } catch (e) {} zeigeStart(); });

  /* ── Start ─────────────────────────────────────────────────────── */
  const alt = laden();
  if (alt && alt.phase === 'laeuft' && alt.modus.zeit && alt.endet <= Date.now()) { Z = alt; auswerten(true); }
  else zeigeStart();
  window.__exam = { bereit: true, zustand: () => Z, zeigeFrage, auswerten };
})();
