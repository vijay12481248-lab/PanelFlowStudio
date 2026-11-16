/* ChronoFlow Audio Studio: a sound editor. Library of sounds (voice, music, effects) -> one sound open as a big waveform -> edit tools.
   No video here: sounds are placed against the picture on the Video Studio timeline (Send to Video Studio). REST: /api/audio/library. */
(function () {
  'use strict';
  const BASE = '/api/audio/library', LS = 'nle:sound-editor:v1';
  const KINDS = [{ id: 'voice', label: 'Voice' }, { id: 'music', label: 'Music' }, { id: 'effect', label: 'Effects' }];
  const KIND_LABEL = { voice: 'Voice', music: 'Music', effect: 'Effect' };
  const FX_KINDS = ['whoosh', 'impact', 'riser', 'drop', 'click', 'pop', 'ding', 'noise_bed'];
  const M = () => window.AudioModel;
  const S = { open: false, mounted: false, sounds: [], filter: 'all', q: '', sound: null, peaks: [], dur: 0, view: { t0: 0, pps: 100 }, sel: null, t: 0, playing: false,
              ops: [], voices: { kokoro: [], qwen3_tts: [] }, panel: 'tools', busy: '', cands: [], rec: null, prevUrl: null, raf: 0 };
  const el = {};
  const $ = (s, r) => (r || document).querySelector(s);

  function h(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k.startsWith('on')) n[k] = v; else if (k === 'class') n.className = v; else n.setAttribute(k, v === true ? '' : v);
    }
    for (const k of kids.flat()) if (k != null && k !== false) n.append(k.nodeType ? k : document.createTextNode(String(k)));
    return n;
  }
  async function call(method, path, body) {
    const r = await fetch(BASE + path, body === undefined ? { method } : { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof d.detail === 'string' ? d.detail : `HTTP ${r.status}`);
    return d;
  }
  function say(msg, bad) { if (el.status) { el.status.textContent = msg || ''; el.status.classList.toggle('bad', !!bad); } }
  async function guard(label, fn) {
    if (S.busy) { say(`Wait: ${S.busy}`, true); return null; }
    S.busy = label; say(`${label}...`); paintBusy();
    try { const r = await fn(); say(''); return r; } catch (e) { say(`${label}: ${e.message}`, true); return null; } finally { S.busy = ''; paintBusy(); }
  }
  const fmt = (t) => { t = Math.max(0, t || 0); const m = Math.floor(t / 60), s = t - m * 60; return `${m}:${s.toFixed(2).padStart(5, '0')}`; };
  const sel = () => (S.sel && S.sel.b - S.sel.a > 0.005 ? S.sel : null);
  const fileUrl = (s, v) => `${BASE}/sounds/${s.id}/file?v=${v || s.current}`;

  // ---------------------------------------------------------------- library
  async function loadSounds() {
    const qs = new URLSearchParams();
    if (S.filter === 'trash') qs.set('trash', 'true'); else if (S.filter !== 'all') qs.set('kind', S.filter);
    if (S.q) qs.set('q', S.q);
    try { S.sounds = await call('GET', `/sounds?${qs}`); } catch (e) { S.sounds = []; say(`Library: ${e.message}`, true); }
    paintLibrary();
  }
  function paintLibrary() {
    const L = el.list; if (!L) return;
    el.filters.querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.f === S.filter));
    el.empty.hidden = S.filter !== 'trash' || !S.sounds.length;
    L.replaceChildren(...(S.sounds.length ? S.sounds.map((s) => h('button', { type: 'button', class: `se-row k-${s.kind}${S.sound && S.sound.id === s.id ? ' sel' : ''}`, 'data-id': s.id,
      onclick: () => openSound(s.id), title: `${s.name} (${KIND_LABEL[s.kind]}, ${s.provenance.source})` },
      h('i', { class: 'se-dot' }), h('span', { class: 'se-rname' }, s.name), h('span', { class: 'se-rlen' }, fmt(s.duration_s)),
      h('span', { class: 'se-rsrc' }, `${KIND_LABEL[s.kind]} · ${srcLabel(s.provenance)}`))) :
      [h('div', { class: 'se-none' }, S.filter === 'trash' ? 'The trash is empty.' : S.q ? `No sound matches "${S.q}".` : 'No sounds yet. Use New sound to speak a line, make music, find an effect, import a file or record.')]));
  }
  function srcLabel(p) {
    const s = p.source || '';
    if (s.startsWith('tts/')) return s === 'tts/kokoro' ? 'Kokoro' : 'Qwen3-TTS';
    return { 'ace-step': 'ACE-Step', synth: 'made by code', openverse: 'Openverse', import: 'imported', recording: 'recorded' }[s] || s;
  }

  // ---------------------------------------------------------------- open a sound
  async function openSound(id, keepView) {
    stop();
    const s = await guard('Opening', () => call('GET', `/sounds/${id}`));
    if (!s) return;
    S.panel = 'tools';
    if (!keepView) { S.sel = null; S.t = 0; }
    try { localStorage.setItem(LS, JSON.stringify({ id })); } catch (e) { /* private window */ }
    await loadPeaks(!keepView, s);   // sets S.sound with its peaks
    paintAll();
  }
  async function loadPeaks(fit, next) {   // next: a sound whose new version replaces S.sound once its peaks are here (state never mixes two versions)
    const s = next || S.sound; if (!s) return;
    let pk = [], dur = s.duration_s;
    try { const p = await call('GET', `/sounds/${s.id}/peaks?v=${s.current}&bins=4000`); pk = p.peaks; dur = p.duration; } catch (e) { /* drawn empty */ }
    S.sound = s; S.peaks = pk; S.dur = dur;
    S.t = Math.min(S.t, S.dur);
    if (S.sel) S.sel = { a: Math.min(S.sel.a, S.dur), b: Math.min(S.sel.b, S.dur) };
    if (fit) fitView();
  }
  function fitView() { const w = el.wave ? el.wave.clientWidth : 800; S.view = { t0: 0, pps: Math.max(5, (w - 2) / Math.max(S.dur, 0.1)) }; }
  function applied(s, msg) { stop(); loadPeaks(false, s).then(() => { paintAll(); say(msg); }); loadSounds(); }

  // ---------------------------------------------------------------- waveform
  function draw() {
    const cv = el.wave, rc = el.ruler; if (!cv || !rc) return;
    const dpr = window.devicePixelRatio || 1, w = cv.clientWidth, hh = cv.clientHeight;
    for (const c of [cv, rc]) { const W = Math.round(c.clientWidth * dpr), H = Math.round(c.clientHeight * dpr); if (c.width !== W || c.height !== H) { c.width = W; c.height = H; } }
    const g = cv.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, hh);
    const kind = S.sound ? S.sound.kind : 'voice', color = getComputedStyle(el.root).getPropertyValue(`--k-${kind}`).trim() || '#46d6a3';
    const v = S.view, x = (t) => (t - v.t0) * v.pps, mid = hh / 2;
    g.fillStyle = '#081027'; g.fillRect(0, 0, w, hh);
    g.strokeStyle = '#16204a'; g.beginPath(); g.moveTo(0, mid); g.lineTo(w, mid); g.stroke();
    for (const db of [-6, -12]) { const y = mid * Math.pow(10, db / 20); g.strokeStyle = 'rgba(122,162,255,.08)'; g.beginPath(); g.moveTo(0, mid - y * 0.92); g.lineTo(w, mid - y * 0.92); g.moveTo(0, mid + y * 0.92); g.lineTo(w, mid + y * 0.92); g.stroke(); }
    const s = sel();
    if (s) { g.fillStyle = 'rgba(122,162,255,.16)'; g.fillRect(x(s.a), 0, Math.max(1, (s.b - s.a) * v.pps), hh); }
    if (S.dur > 0 && S.peaks.length) {
      const endX = Math.min(w, x(S.dur)), bars = M().peaksToBars(S.peaks, Math.max(1, Math.ceil(endX)), v.t0 / S.dur, (v.t0 + endX / v.pps) / S.dur);
      g.fillStyle = color;
      for (let i = 0; i < bars.length; i++) {
        const tt = v.t0 + i / v.pps, inSel = s && tt >= s.a && tt <= s.b, a = Math.max(0.5, bars[i] * mid * 0.92);
        g.globalAlpha = s && !inSel ? 0.55 : 1; g.fillRect(i, mid - a, 1, a * 2);
      }
      g.globalAlpha = 1;
      if (endX < w) { g.fillStyle = '#060b1d'; g.fillRect(endX, 0, w - endX, hh); }
    } else if (!S.sound) {
      g.fillStyle = '#4e5a8a'; g.font = '13px system-ui, sans-serif'; g.textAlign = 'center';
      g.fillText('Open a sound from the library, or make a new one.', w / 2, mid);
    }
    if (s) { g.fillStyle = '#7aa2ff'; g.fillRect(x(s.a), 0, 1, hh); g.fillRect(x(s.b), 0, 1, hh); }
    g.fillStyle = '#ffffff'; g.fillRect(Math.round(x(S.t)), 0, 1.5, hh);
    // ruler
    const r = rc.getContext('2d'), rw = rc.clientWidth, rh = rc.clientHeight; r.setTransform(dpr, 0, 0, dpr, 0, 0); r.clearRect(0, 0, rw, rh);
    r.fillStyle = '#0c1334'; r.fillRect(0, 0, rw, rh); r.font = '10px system-ui, sans-serif'; r.fillStyle = '#8590bb'; r.strokeStyle = '#2a3566';
    for (const tk of M().rulerTicks(v, rw, 100)) {
      const px = Math.round(x(tk.t)) + 0.5; r.beginPath(); r.moveTo(px, tk.major ? 6 : 14); r.lineTo(px, rh); r.stroke();
      if (tk.major) r.fillText(fmt(tk.t), px + 3, 11);
    }
    if (el.time) el.time.textContent = `${fmt(S.t)} / ${fmt(S.dur)}`;
    if (el.selRead) el.selRead.textContent = s ? `Selection ${fmt(s.a)} to ${fmt(s.b)} (${(s.b - s.a).toFixed(2)} s)` : 'No selection: tools act on the whole sound';
  }
  function bindWave() {
    const cv = el.wave, tAt = (e) => { const r = cv.getBoundingClientRect(); return Math.min(S.dur, Math.max(0, S.view.t0 + (e.clientX - r.left) / S.view.pps)); };
    cv.onpointerdown = (e) => {
      if (!S.sound) return;
      cv.setPointerCapture(e.pointerId);
      const t0 = tAt(e), x0 = e.clientX; let dragged = false;
      cv.onpointermove = (m) => {
        if (Math.abs(m.clientX - x0) < 3 && !dragged) return;
        dragged = true; const t1 = tAt(m); S.sel = { a: Math.min(t0, t1), b: Math.max(t0, t1) }; draw(); paintTools();
      };
      cv.onpointerup = () => {
        cv.onpointermove = cv.onpointerup = null;
        if (!dragged) { S.sel = null; seek(t0); paintTools(); } else { seek(S.sel.a); }
      };
    };
    cv.onwheel = (e) => {
      if (!S.sound) return; e.preventDefault();
      if (e.shiftKey) { S.view.t0 = Math.max(0, S.view.t0 + e.deltaY / S.view.pps); }
      else { const r = cv.getBoundingClientRect(); S.view = M().zoomAt(S.view, e.deltaY < 0 ? 1.25 : 0.8, S.view.t0 + (e.clientX - r.left) / S.view.pps, { minPps: 2, maxPps: 20000 }); }
      draw();
    };
    el.ruler.onpointerdown = (e) => { if (!S.sound) return; const r = el.ruler.getBoundingClientRect(); seek(Math.max(0, S.view.t0 + (e.clientX - r.left) / S.view.pps)); };
  }

  // ---------------------------------------------------------------- playback (one <audio>, a meter from an analyser)
  let A = null;
  function audio() {
    if (A) return A;
    const el2 = new Audio(); el2.preload = 'auto';
    A = { el: el2, ctx: null, an: null, until: null };
    el2.onended = () => stop();
    return A;
  }
  function meterSetup() {
    const a = audio(); if (a.ctx) return;
    try { a.ctx = new AudioContext(); const src = a.ctx.createMediaElementSource(a.el); a.an = a.ctx.createAnalyser(); a.an.fftSize = 1024; src.connect(a.an); a.an.connect(a.ctx.destination); } catch (e) { a.ctx = null; }
  }
  function seek(t) { S.t = Math.max(0, Math.min(S.dur, t)); if (A && S.playing) A.el.currentTime = S.t; draw(); }
  async function play(range, url) {
    const a = audio(); meterSetup(); if (a.ctx && a.ctx.state === 'suspended') await a.ctx.resume();
    const src = url || (S.sound ? fileUrl(S.sound) : null); if (!src) return;
    if (a.el.dataset.src !== src) { a.el.src = src; a.el.dataset.src = src; }
    const from = range ? range.a : (S.t >= S.dur - 0.01 ? 0 : S.t);
    a.until = range ? range.b : null; a.preview = !!url;
    try { a.el.currentTime = url ? 0 : from; await a.el.play(); } catch (e) { say(`Play: ${e.message}`, true); return; }
    S.playing = true; paintTransport(); tick();
  }
  function stop() { if (A) A.el.pause(); S.playing = false; cancelAnimationFrame(S.raf); if (el.meter) el.meter.style.setProperty('--lvl', '0%'); paintTransport(); }
  function tick() {
    cancelAnimationFrame(S.raf);
    const step = () => {
      if (!S.playing || !A) return;
      if (!A.preview) { S.t = A.el.currentTime; if (A.until != null && S.t >= A.until) { stop(); S.t = A.until; } }
      if (A.an && el.meter) {
        const d = new Float32Array(A.an.fftSize); A.an.getFloatTimeDomainData(d); let pk = 0; for (const v of d) pk = Math.max(pk, Math.abs(v));
        const db = 20 * Math.log10(Math.max(pk, 1e-5)); el.meter.style.setProperty('--lvl', `${Math.max(0, Math.min(100, (db + 60) / 60 * 100))}%`); el.meter.dataset.db = db.toFixed(1);
      }
      draw(); S.raf = requestAnimationFrame(step);
    };
    S.raf = requestAnimationFrame(step);
  }
  function togglePlay() { if (S.playing) stop(); else play(null); }

  // ---------------------------------------------------------------- tools
  function paramInput(op, name, spec, store) {
    if (spec.choices) {
      const s = h('select', { class: 'dl-in', 'data-p': name, 'aria-label': name }, ...spec.choices.map((c) => h('option', { value: c }, c.replace(/_/g, ' '))));
      s.value = store[name] != null ? store[name] : spec.choices[0]; s.onchange = () => { store[name] = s.value; };
      return h('label', { class: 'se-param' }, h('span', null, name.replace(/_/g, ' ')), s);
    }
    const step = Number.isInteger(spec.default) ? 1 : (spec.max - spec.min) > 40 ? 1 : 0.01, val = store[name] != null ? store[name] : spec.default;
    const out = h('output', null, String(val));
    const r = h('input', { type: 'range', min: spec.min, max: spec.max, step, value: val, 'data-p': name, 'aria-label': name });
    r.oninput = () => { store[name] = +r.value; out.textContent = r.value; };
    return h('label', { class: 'se-param' }, h('span', null, name.replace(/_/g, ' ')), r, out);
  }
  const PARAMS = {};
  function opBody(o) {
    const s = sel();
    if (o.op === 'insert_silence') PARAMS[o.op] = { ...(PARAMS[o.op] || {}), at: +S.t.toFixed(3) };
    const store = (PARAMS[o.op] = PARAMS[o.op] || {});
    const need = o.selection === 'needs' && !s, scope = o.selection === 'none' ? 'Whole sound' : o.selection === 'needs' ? 'Selection' : s ? 'Selection' : 'Whole sound';
    const params = Object.entries(o.params).filter(([n]) => !(o.op === 'insert_silence' && n === 'at')).map(([n, spec]) => paramInput(o.op, n, spec, store));
    return h('div', { class: 'se-op', 'data-op': o.op },
      h('div', { class: 'se-ophead' }, h('b', null, o.label), h('span', { class: `se-scope${need ? ' need' : ''}` }, need ? 'Select a part first' : scope)),
      params.length ? h('div', { class: 'se-params' }, ...params) : null,
      h('div', { class: 'se-opbtns' },
        h('button', { type: 'button', class: 'dl-btn', disabled: need || !!S.busy, onclick: () => previewOp(o) }, 'Preview'),
        h('button', { type: 'button', class: 'dl-btn accent', disabled: need || !!S.busy, onclick: () => applyOp(o) }, 'Apply')));
  }
  function opArgs(o) {
    const s = sel(), p = { ...(PARAMS[o.op] || {}) };
    if (o.op === 'insert_silence') p.at = S.t;
    return { op: o.op, params: p, a: s && o.selection !== 'none' ? s.a : null, b: s && o.selection !== 'none' ? s.b : null };
  }
  async function applyOp(o) {
    const id = S.sound.id, r = await guard(o.label, () => call('POST', `/sounds/${id}/edit`, opArgs(o)));
    if (!r) return;
    if (o.op === 'trim' || o.op === 'delete') S.sel = null;
    applied(r, `${o.label}: done (version ${r.current}). Ctrl+Z to undo.`);
  }
  async function previewOp(o) {
    const id = S.sound.id;
    const blob = await guard(`Preview ${o.label.toLowerCase()}`, async () => {
      const r = await fetch(`${BASE}/sounds/${id}/preview`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(opArgs(o)) });
      if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.detail || `HTTP ${r.status}`); }
      return r.blob();
    });
    if (!blob) return;
    if (S.prevUrl) URL.revokeObjectURL(S.prevUrl);
    S.prevUrl = URL.createObjectURL(blob); stop(); play(null, S.prevUrl);
    say(`Playing the preview of ${o.label.toLowerCase()}. Apply keeps it.`);
  }
  function paintTools() {
    const T = el.tools; if (!T) return;
    if (S.panel !== 'tools') return paintNew();
    el.toolsHead.textContent = 'Tools';
    if (!S.sound) { T.replaceChildren(h('div', { class: 'se-none' }, 'Open a sound to edit it. Drag on the waveform to select a part; without a selection the tools act on the whole sound.')); return; }
    if (S.sound.trashed) { T.replaceChildren(h('div', { class: 'se-none' }, 'This sound is in the trash. Restore it to edit it.')); return; }
    const open = new Set([...T.querySelectorAll('details[open]')].map((d) => d.dataset.g));
    if (!T.children.length || !open.size) open.add('Edit');
    const groups = [...new Set(S.ops.map((o) => o.group))];
    T.replaceChildren(...groups.map((g) => h('details', { class: 'se-group', 'data-g': g, open: open.has(g) },
      h('summary', null, g),
      ...(g === 'Edit' ? [h('div', { class: 'se-quick' },
        h('button', { type: 'button', class: 'dl-btn', disabled: !!S.busy, onclick: splitHere, title: 'The sound keeps the part before the playhead; the part after becomes a new sound' }, 'Split at playhead'),
        h('button', { type: 'button', class: 'dl-btn', disabled: !!S.busy, onclick: duplicate }, 'Duplicate'),
        joinPicker())] : []),
      ...S.ops.filter((o) => o.group === g).map(opBody))));
  }
  function joinPicker() {
    const others = S.sounds.filter((s) => s.id !== S.sound.id && !s.trashed);
    const pick = h('select', { class: 'dl-in', 'aria-label': 'Sound to add at the end' }, h('option', { value: '' }, 'Add another sound at the end...'), ...others.map((s) => h('option', { value: s.id }, s.name)));
    pick.onchange = async () => {
      if (!pick.value) return;
      const r = await guard('Joining', () => call('POST', `/sounds/${S.sound.id}/join`, { other: pick.value }));
      if (r) applied(r, 'Joined. Ctrl+Z to undo.');
    };
    return pick;
  }
  async function splitHere() {
    if (!(S.t > 0.01 && S.t < S.dur - 0.01)) return say('Put the playhead inside the sound first (click the waveform).', true);
    const r = await guard('Splitting', () => call('POST', `/sounds/${S.sound.id}/split`, { at: S.t }));
    if (r) applied(r.sound, `Split: the part after the playhead is the new sound "${r.new.name}".`);
  }
  async function duplicate() { const r = await guard('Duplicating', () => call('POST', `/sounds/${S.sound.id}/duplicate`)); if (r) { await loadSounds(); openSound(r.id); } }
  async function undo(redo) {
    if (!S.sound) return;
    const r = await guard(redo ? 'Redo' : 'Undo', () => call('POST', `/sounds/${S.sound.id}/${redo ? 'redo' : 'undo'}`));
    if (r) applied(r, `${redo ? 'Redo' : 'Undo'}: version ${r.current}.`);
  }

  // ---------------------------------------------------------------- new sound
  const NEW = [{ id: 'voice', label: 'Speak text' }, { id: 'script', label: 'Speak a script' }, { id: 'music', label: 'Make music' }, { id: 'effect', label: 'Find an effect' }, { id: 'import', label: 'Import a file' }, { id: 'record', label: 'Record' }];
  function showNew(id) { S.panel = id; paintTools(); paintHeadBtns(); }
  function paintNew() {
    const T = el.tools, k = S.panel;
    el.toolsHead.textContent = NEW.find((n) => n.id === k).label;
    const back = h('button', { type: 'button', class: 'dl-btn se-back', onclick: () => { S.panel = 'tools'; stopRec(); paintTools(); paintHeadBtns(); } }, 'Back to tools');
    const form = { voice: voiceForm, script: scriptForm, music: musicForm, effect: effectForm, import: importForm, record: recordForm }[k]();
    T.replaceChildren(h('div', { class: 'se-newform' }, form, back));
  }
  const field = (label, input, hint) => h('label', { class: 'dl-field' }, h('span', { class: 'dl-lab' }, label), input, hint ? h('span', { class: 'dl-hint' }, hint) : null);
  async function made(s, msg) { if (!s) return; S.filter = 'all'; await loadSounds(); await openSound(s.id); say(msg || `Made "${s.name}".`); }
  const voiceSelect = (id) => h('select', { class: 'dl-in', id },
    h('optgroup', { label: 'Kokoro (fast, on the CPU)' }, ...S.voices.kokoro.map((v) => h('option', { value: `kokoro:${v}` }, v))),
    S.voices.qwen3_tts.length ? h('optgroup', { label: 'Qwen3-TTS (cloned voices, uses the GPU)' }, ...S.voices.qwen3_tts.map((v) => h('option', { value: `qwen3_tts:${v}` }, v))) : null);
  // A pasted script: one voice sound per paragraph (one paragraph -> per sentence), then placed on A2 Voice back to back or one line per picture cut.
  function scriptForm() {
    const text = h('textarea', { class: 'dl-in se-text', id: 'seScriptText', rows: 9, placeholder: 'Paste the narration. A blank line starts a new line of speech; a single paragraph is split into sentences.' });
    const voice = voiceSelect('seScriptVoice');
    const speed = h('input', { type: 'range', min: 0.6, max: 1.5, step: 0.05, value: 1, id: 'seScriptSpeed' }), sv = h('output', null, '1.00x');
    speed.oninput = () => { sv.textContent = `${(+speed.value).toFixed(2)}x`; count(); };
    const est = h('span', { class: 'dl-hint', id: 'seScriptEst' }, 'No lines yet');
    const count = () => {
      const lines = M().splitScript(text.value);
      est.textContent = lines.length ? `${lines.length} line(s), about ${lines.reduce((t, l) => t + M().estimateSeconds(l, +speed.value), 0).toFixed(1)} s` : 'No lines yet';
    };
    text.oninput = count;
    const placeRow = h('div', { class: 'se-footrow', id: 'seScriptPlace', hidden: true });
    const place = (mode) => {
      if (!window.NLE || typeof window.NLE.placeNarration !== 'function' || typeof window.switchResolvePage !== 'function') return say('The Video Studio timeline is not available here.', true);
      const r = window.NLE.placeNarration(S.script, { mode });
      if (r.error) return say(r.error, true);
      window.switchResolvePage('edit');
    };
    const go = h('button', { type: 'button', class: 'dl-btn accent', id: 'seMakeScript', onclick: async () => {
      const [provider, v] = voice.value.split(':');
      const r = await guard('Speaking the script', () => call('POST', '/sounds/script', { text: text.value, voice: v, provider, speed: +speed.value }));
      if (!r) { loadSounds(); return; }
      S.script = r.sounds; S.filter = 'all'; await loadSounds();   // stay on this form: the place buttons are here
      say(`Made ${r.sounds.length} voice line(s). Place them on the timeline below.`);
      placeRow.hidden = false;
    } }, 'Speak all lines');
    placeRow.append(h('button', { type: 'button', class: 'dl-btn', id: 'seScriptSeq', title: 'A2 Voice, back to back from the playhead', onclick: () => place('sequential') }, 'Place back to back'),
      h('button', { type: 'button', class: 'dl-btn', id: 'seScriptCut', title: 'Line 1 at the start, each next line on the next picture cut', onclick: () => place('per_cut') }, 'Place one per picture cut'));
    return h('div', { class: 'se-form' }, field('Script', text), est, field('Voice', voice), h('label', { class: 'se-param' }, h('span', null, 'Pace'), speed, sv), go, placeRow);
  }
  function voiceForm() {
    const text = h('textarea', { class: 'dl-in se-text', id: 'seVoiceText', rows: 5, placeholder: 'The words to speak' });
    const voice = voiceSelect('seVoice');
    const speed = h('input', { type: 'range', min: 0.6, max: 1.5, step: 0.05, value: 1, id: 'seSpeed' }), sv = h('output', null, '1.00x');
    speed.oninput = () => { sv.textContent = `${(+speed.value).toFixed(2)}x`; };
    const est = h('span', { class: 'dl-hint' }, 'About 0 s');
    text.oninput = () => { est.textContent = `About ${M().estimateSeconds(text.value, +speed.value).toFixed(1)} s`; };
    const go = h('button', { type: 'button', class: 'dl-btn accent', id: 'seMakeVoice', onclick: async () => {
      const [provider, v] = voice.value.split(':');
      made(await guard('Speaking', () => call('POST', '/sounds/voice', { text: text.value, voice: v, provider, speed: +speed.value })));
    } }, 'Speak and add');
    return h('div', { class: 'se-form' }, field('Words', text), est, field('Voice', voice), h('label', { class: 'se-param' }, h('span', null, 'Pace'), speed, sv), go);
  }
  function musicForm() {
    const d = h('textarea', { class: 'dl-in se-text', id: 'seMusicText', rows: 3, placeholder: 'soft piano, slow and hopeful' });
    const secs = h('input', { type: 'number', class: 'dl-in', min: 5, max: 240, value: 30, id: 'seMusicSecs' }), bpm = h('input', { type: 'number', class: 'dl-in', min: 40, max: 220, placeholder: 'auto' });
    const moods = ['calm', 'tense', 'epic', 'sad', 'playful', 'dreamy'].map((m) => h('button', { type: 'button', class: 'dl-preset', onclick: () => { d.value = d.value ? `${d.value}, ${m}` : m; } }, m));
    const go = h('button', { type: 'button', class: 'dl-btn accent', id: 'seMakeMusic', onclick: async () =>
      made(await guard('Making music with ACE-Step (minutes)', () => call('POST', '/sounds/music', { description: d.value, seconds: +secs.value || 30, bpm: +bpm.value || null }))) }, 'Make and add');
    return h('div', { class: 'se-form' }, field('Describe the music', d), h('div', { class: 'dl-presets' }, ...moods),
      h('div', { class: 'dl-two' }, field('Length (s)', secs), field('Tempo (bpm)', bpm)), go, h('span', { class: 'dl-hint' }, 'ACE-Step 1.5 (MIT) runs on this PC and takes the GPU while it works.'));
  }
  function effectForm() {
    const d = h('input', { class: 'dl-in', id: 'seFxText', placeholder: 'door creak, rain on a window...' });
    let kind = 'whoosh';
    const chips = FX_KINDS.map((k) => h('button', { type: 'button', class: `dl-preset${k === kind ? ' on' : ''}`, 'data-k': k, onclick: (e) => {
      kind = k; chips.forEach((c) => c.classList.toggle('on', c === e.currentTarget));
    } }, k.replace('_', ' ')));
    const anyword = h('button', { type: 'button', class: 'dl-preset', 'data-k': 'search', onclick: (e) => { kind = 'search'; chips.forEach((c) => c.classList.toggle('on', c === e.currentTarget)); } }, 'search Openverse');
    chips.push(anyword);
    const list = h('div', { class: 'se-cands', id: 'seCands' }, ...candRows());
    const go = h('button', { type: 'button', class: 'dl-btn accent', id: 'seFindFx', onclick: async () => {
      const r = await guard('Finding effects', () => call('POST', '/effects/find', { description: d.value, kind: kind === 'search' ? (d.value || 'sound') : kind, limit: 3 }));
      if (r) { S.cands = r.candidates; list.replaceChildren(...candRows()); say(`${S.cands.length} to hear. Keep the one you like.`); }
    } }, 'Find');
    return h('div', { class: 'se-form' }, h('div', { class: 'dl-presets' }, ...chips), field('Or describe it', d, 'Code-made kinds are instant and CC0. A search uses Openverse (CC0 only).'), go, list);
  }
  function candRows() {
    return S.cands.map((c) => h('div', { class: 'se-cand' },
      h('button', { type: 'button', class: 'dl-btn', onclick: () => { stop(); play(null, `${BASE}/effects/candidates/${c.id}/file`); } }, 'Play'),
      h('span', { class: 'se-cname', title: `${c.provenance.licence} · ${c.provenance.source}` }, c.label),
      h('button', { type: 'button', class: 'dl-btn accent', onclick: async () => made(await guard('Keeping', () => call('POST', '/effects/keep', { candidate_id: c.id }))) }, 'Keep')));
  }
  function upload(file, kind, source, name) {
    const fd = new FormData(); fd.append('file', file, file.name || 'recording.webm'); fd.append('kind', kind); fd.append('source', source); if (name) fd.append('name', name);
    return guard(source === 'recording' ? 'Saving the recording' : `Importing ${file.name}`, async () => {
      const r = await fetch(`${BASE}/sounds/upload`, { method: 'POST', body: fd }), d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`); return d;
    });
  }
  function kindSelect(id, v) { const s = h('select', { class: 'dl-in', id }, ...KINDS.map((k) => h('option', { value: k.id }, k.label))); s.value = v; return s; }
  function importForm() {
    const kind = kindSelect('seImportKind', 'effect');
    const inp = h('input', { type: 'file', accept: 'audio/*,video/*', id: 'seImportFile', class: 'se-file' });
    const drop = h('label', { class: 'se-drop', for: 'seImportFile' }, h('b', null, 'Drop a file here'), h('span', null, 'or click to choose: wav, mp3, m4a, flac, ogg, or a video (its sound is taken)'), inp);
    const take = async (f) => { if (f) made(await upload(f, kind.value, 'import'), `Imported "${f.name}".`); };
    inp.onchange = () => take(inp.files[0]);
    drop.ondragover = (e) => { e.preventDefault(); drop.classList.add('over'); };
    drop.ondragleave = () => drop.classList.remove('over');
    drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove('over'); take(e.dataTransfer.files[0]); };
    return h('div', { class: 'se-form' }, field('Use it as', kind), drop, h('span', { class: 'dl-hint' }, 'Only bring sounds you have the right to use; they are marked as yours.'));
  }
  function recordForm() {
    const kind = kindSelect('seRecKind', 'voice'), clock = h('div', { class: 'se-clock', id: 'seRecClock' }, '0:00.0');
    const btn = h('button', { type: 'button', class: 'dl-btn accent se-recbtn', id: 'seRecBtn', onclick: () => (S.rec ? stopRec(true) : startRec(btn, clock, kind)) }, 'Start recording');
    return h('div', { class: 'se-form' }, field('Use it as', kind), clock, btn, h('span', { class: 'dl-hint' }, 'The browser asks for the microphone the first time. Stop saves the recording as a new sound.'));
  }
  async function startRec(btn, clock, kind) {
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } }); }
    catch (e) { return say(`Microphone: ${e.message}`, true); }
    const chunks = [], mr = new MediaRecorder(stream), t0 = performance.now();
    S.rec = { mr, stream, timer: setInterval(() => { clock.textContent = fmt((performance.now() - t0) / 1000).replace(/(\.\d)\d$/, '$1'); }, 100), kind: kind.value, save: false };
    mr.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    mr.onstop = async () => {
      const rec = S.rec; S.rec = null; clearInterval(rec.timer); rec.stream.getTracks().forEach((t) => t.stop());
      btn.textContent = 'Start recording'; btn.classList.remove('rec');
      if (rec.save && chunks.length) made(await upload(new File(chunks, 'recording.webm', { type: mr.mimeType || 'audio/webm' }), rec.kind, 'recording'), 'Recording saved.');
    };
    mr.start(250); btn.textContent = 'Stop and save'; btn.classList.add('rec'); say('Recording...');
  }
  function stopRec(save) { if (S.rec) { S.rec.save = !!save; S.rec.mr.stop(); } }

  // ---------------------------------------------------------------- footer: name, kind, versions, licence, delete, send
  function paintFoot() {
    const F = el.foot, s = S.sound; if (!F) return;
    if (!s) { F.replaceChildren(h('div', { class: 'se-none' }, 'Versions, licence and Send to Video Studio appear here when a sound is open.')); return; }
    const name = h('input', { class: 'dl-in se-name', id: 'seName', value: s.name, 'aria-label': 'Sound name' });
    name.onchange = async () => { const r = await guard('Renaming', () => call('PATCH', `/sounds/${s.id}`, { name: name.value })); if (r) { S.sound = r; loadSounds(); } };
    const kind = kindSelect('seKind', s.kind);
    kind.onchange = async () => { const r = await guard('Changing the kind', () => call('PATCH', `/sounds/${s.id}`, { kind: kind.value })); if (r) { S.sound = r; loadSounds(); draw(); el.root.dataset.kind = r.kind; } };
    const vers = h('div', { class: 'se-versions', id: 'seVersions' }, ...s.versions.map((v) => h('button', { type: 'button', class: `se-ver${v.n === s.current ? ' on' : ''}${v.n > s.current ? ' undone' : ''}`, 'data-n': v.n,
      title: `${new Date(v.created).toLocaleString()} · ${v.duration_s.toFixed(2)} s · peak ${v.peak_db.toFixed(1)} dB`,
      onclick: async () => { const r = await guard('Going to that version', () => call('POST', `/sounds/${s.id}/versions/${v.n}/current`)); if (r) applied(r, `Version ${v.n}.`); } },
      h('b', null, v.n), ' ', opName(v))));
    const p = s.provenance;
    const lic = h('div', { class: 'se-lic' }, h('b', null, p.licence === 'owner' ? 'Yours' : p.licence), ` · ${srcLabel(p)}${p.model ? ` · ${p.model}` : ''}${p.author ? ` · ${p.author}` : ''}`);
    const del = s.trashed ? h('button', { type: 'button', class: 'dl-btn', id: 'seRestore', onclick: async () => { const r = await guard('Restoring', () => call('POST', `/sounds/${s.id}/restore`)); if (r) { S.sound = r; loadSounds(); paintAll(); } } }, 'Restore')
      : h('button', { type: 'button', class: 'dl-btn se-del', id: 'seDelete', onclick: async () => { const r = await guard('Moving to the trash', () => call('DELETE', `/sounds/${s.id}`)); if (r) { S.sound = null; S.peaks = []; S.dur = 0; stop(); loadSounds(); paintAll(); say(`"${r.name}" is in the trash. Restore it from Trash.`); } } }, 'Delete');
    const send = h('button', { type: 'button', class: 'dl-btn accent se-send', id: 'seSend', disabled: s.trashed, onclick: sendToVideo, title: 'Put this sound on the Video Studio timeline at the playhead' }, 'Send to Video Studio');
    F.replaceChildren(h('div', { class: 'se-footrow' }, name, kind, lic, h('span', { class: 'se-grow' }), del, send), vers);
  }
  function opName(v) {
    const p = v.params || {};
    if (v.op === 'created') return 'original';
    if (v.op === 'gain') return `gain ${p.db > 0 ? '+' : ''}${p.db} dB`;
    if (v.op === 'pitch') return `pitch ${p.semitones > 0 ? '+' : ''}${p.semitones}`;
    if (v.op === 'speed') return `speed ${p.factor}x`;
    return v.op.replace(/_/g, ' ');
  }
  function sendToVideo() {
    const s = S.sound;
    if (!window.NLE || typeof window.NLE.addSound !== 'function' || typeof window.switchResolvePage !== 'function') return say('The Video Studio timeline is not available here.', true);
    window.switchResolvePage('edit');
    const r = window.NLE.addSound({ sound: s.id, version: s.current, label: s.name, kind: s.kind, duration: s.duration_s, url: fileUrl(s) });
    if (r && r.error) say(r.error, true);
  }

  // ---------------------------------------------------------------- paint
  function paintTransport() {
    if (!el.play) return;
    el.play.textContent = S.playing ? 'Pause' : 'Play'; el.play.setAttribute('aria-pressed', S.playing);
    [el.play, el.playSel, el.fit].forEach((b) => { b.disabled = !S.sound; });
    el.playSel.disabled = !S.sound || !sel();
  }
  function paintHeadBtns() { el.newMenu.querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.n === S.panel)); }
  function paintBusy() {
    el.root && el.root.classList.toggle('busy', !!S.busy);
    if (el.undo) { el.undo.disabled = el.redo.disabled = !S.sound || !!S.busy; }
    if (el.tools) el.tools.querySelectorAll('.se-opbtns button, .se-quick button, #seMakeVoice, #seMakeScript, #seMakeMusic, #seFindFx').forEach((b) => { if (!b.closest('.se-op') || !b.closest('.se-op').querySelector('.se-scope.need')) b.disabled = !!S.busy; });
  }
  function paintAll() {
    if (!el.root) return;
    el.root.dataset.kind = S.sound ? S.sound.kind : '';
    el.title.textContent = S.sound ? S.sound.name : 'No sound open';
    el.meta.textContent = S.sound ? `${KIND_LABEL[S.sound.kind]} · ${fmt(S.sound.duration_s)} · version ${S.sound.current} of ${S.sound.versions.length}` : '';
    paintLibrary(); paintTools(); paintFoot(); paintTransport(); paintBusy(); draw();
  }

  // ---------------------------------------------------------------- mount / open / close
  function mount() {
    if (S.mounted) return true;
    const root = $('#soundEditor'); if (!root || !M()) return false;
    el.root = root;
    const search = h('input', { class: 'dl-in', id: 'seSearch', placeholder: 'Search sounds', 'aria-label': 'Search sounds' });
    let qt = 0; search.oninput = () => { clearTimeout(qt); qt = setTimeout(() => { S.q = search.value.trim(); loadSounds(); }, 200); };
    el.filters = h('div', { class: 'se-filters', role: 'group', 'aria-label': 'Show' }, ...[{ id: 'all', label: 'All' }, ...KINDS, { id: 'trash', label: 'Trash' }].map((f) =>
      h('button', { type: 'button', 'data-f': f.id, class: f.id === 'all' ? 'on' : '', onclick: () => { S.filter = f.id; loadSounds(); } }, f.label)));
    el.list = h('div', { class: 'se-list', id: 'seList' });
    el.empty = h('button', { type: 'button', class: 'dl-btn se-del', id: 'seEmptyTrash', hidden: true, onclick: async () => {
      if (!window.confirm(`Delete the ${S.sounds.length} sound(s) in the trash for good? This cannot be undone.`)) return;
      const r = await guard('Emptying the trash', () => call('POST', '/trash/empty')); if (r) { if (S.sound && r.removed.includes(S.sound.id)) { S.sound = null; S.peaks = []; } loadSounds(); paintAll(); say(`Deleted ${r.removed.length} sound(s) for good.`); }
    } }, 'Empty the trash');
    el.newMenu = h('div', { class: 'se-new', role: 'group', 'aria-label': 'New sound' }, ...NEW.map((n) => h('button', { type: 'button', 'data-n': n.id, onclick: () => showNew(n.id) }, n.label)));
    const lib = h('section', { class: 'se-lib', 'aria-label': 'Sound library' }, h('div', { class: 'se-h' }, 'New sound'), el.newMenu, h('div', { class: 'se-h' }, 'Library'), search, el.filters, el.list, el.empty);

    el.title = h('h2', { class: 'se-title' }); el.meta = h('span', { class: 'se-meta' });
    el.ruler = h('canvas', { class: 'se-ruler', 'aria-hidden': 'true' });
    el.wave = h('canvas', { class: 'se-wave', id: 'seWave', role: 'img', 'aria-label': 'Waveform: drag to select, click to move the playhead, wheel to zoom' });
    el.play = h('button', { type: 'button', class: 'dl-btn accent se-play', id: 'sePlay', onclick: togglePlay }, 'Play');
    el.playSel = h('button', { type: 'button', class: 'dl-btn', id: 'sePlaySel', onclick: () => play(sel()) }, 'Play selection');
    el.fit = h('button', { type: 'button', class: 'dl-btn', onclick: () => { fitView(); draw(); } }, 'Fit');
    el.undo = h('button', { type: 'button', class: 'dl-btn', id: 'seUndo', onclick: () => undo(false), title: 'Ctrl+Z' }, 'Undo');
    el.redo = h('button', { type: 'button', class: 'dl-btn', id: 'seRedo', onclick: () => undo(true), title: 'Ctrl+Y' }, 'Redo');
    el.time = h('span', { class: 'se-time', id: 'seTime' }, '0:00.00 / 0:00.00');
    el.selRead = h('span', { class: 'se-selread', id: 'seSel' });
    el.meter = h('div', { class: 'se-meter', id: 'seMeter', title: 'Level while playing' });
    el.foot = h('div', { class: 'se-foot', id: 'seFoot' });
    const editor = h('section', { class: 'se-editor', 'aria-label': 'Sound editor' },
      h('div', { class: 'se-head' }, el.title, el.meta, h('span', { class: 'se-grow' }), el.undo, el.redo),
      h('div', { class: 'se-stage' }, el.ruler, el.wave),
      h('div', { class: 'se-transport' }, el.play, el.playSel, el.fit, el.time, el.meter, h('span', { class: 'se-grow' }), el.selRead),
      el.foot);
    el.toolsHead = h('div', { class: 'se-h' }, 'Tools');
    el.tools = h('div', { class: 'se-tools', id: 'seTools' });
    el.status = h('div', { class: 'se-status', id: 'seStatus', role: 'status', 'aria-live': 'polite' });
    const tools = h('section', { class: 'se-side', 'aria-label': 'Tools' }, el.toolsHead, el.tools, el.status);
    root.replaceChildren(lib, editor, tools);
    bindWave();
    new ResizeObserver(() => draw()).observe(el.wave);
    document.addEventListener('keydown', onKey);
    S.mounted = true;
    return true;
  }
  function onKey(e) {
    if (!S.open || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable) return;
    const k = e.key.toLowerCase();
    if (k === ' ') { e.preventDefault(); togglePlay(); }
    else if ((e.ctrlKey || e.metaKey) && k === 'z') { e.preventDefault(); undo(e.shiftKey); }
    else if ((e.ctrlKey || e.metaKey) && k === 'y') { e.preventDefault(); undo(true); }
    else if ((k === 'delete' || k === 'backspace') && sel() && S.sound) { e.preventDefault(); const o = S.ops.find((x) => x.op === 'delete'); if (o) applyOp(o); }
    else if (k === 'escape') { S.sel = null; draw(); paintTools(); }
    else if (k === 'home') { seek(0); }
  }
  async function open() {
    if (!mount()) return;
    S.open = true;
    if (!S.ops.length) { try { S.ops = await call('GET', '/ops'); } catch (e) { say(`Tools: ${e.message}`, true); } }
    try { const r = await fetch('/api/audio/studio/voices').then((x) => x.json()); S.voices = r.voices || S.voices; } catch (e) { /* voices stay empty; Speak shows none */ }
    await loadSounds();
    if (!S.sound) { let last = null; try { last = JSON.parse(localStorage.getItem(LS) || 'null'); } catch (e) { /* none */ } if (last && S.sounds.some((s) => s.id === last.id)) await openSound(last.id); }
    paintAll();
  }
  function close() { S.open = false; stop(); stopRec(false); }

  window.SoundEditor = { open, close, openSound, reload: loadSounds, showNew, play, stop, seek, undo, get state() { return S; }, select: (a, b) => { S.sel = a == null ? null : { a, b }; draw(); paintTools(); }, applyOp: (op, params) => { const o = S.ops.find((x) => x.op === op); if (o) { PARAMS[op] = { ...(PARAMS[op] || {}), ...(params || {}) }; return applyOp(o); } } };
})();
