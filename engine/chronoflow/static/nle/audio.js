/* ChronoFlow Audio page - the cockpit for a video's sound plan (engine/audio/studio, REST /api/audio/studio).
   Left: plan, mode and the cue list. Centre: the video. Right: the selected cue. Bottom: lanes and mixer.
   All state lives on the server (the plan); this page only reads it, sends small edits and plays the preview stems.
   Pure maths is in audio-model.js. Reuses the Deliver page's .dl-* control styles. */
(function () {
  'use strict';
  const M = window.AudioModel;
  const BASE = '/api/audio/studio', LS = 'nle:audio:v1';
  const S = { open: false, mounted: false, plans: [], plan: null, sel: null, busy: '', msg: '', bad: false, seen: null, timer: 0, qa: null, lastErr: '' };
  const el = {};

  const h = (tag, attrs, ...kids) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === 'class') e.className = v; else if (k === 'style') e.style.cssText = v;
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else if (v !== false && v != null) e.setAttribute(k, v === true ? '' : v);
    }
    for (const c of kids.flat()) if (c != null) e.append(c.nodeType ? c : document.createTextNode(String(c)));
    return e;
  };
  const $ = (s, r) => (r || document).querySelector(s);
  const token = () => (window.NLE && window.NLE.cfg && window.NLE.cfg.token) || '';
  const withToken = (u) => (token() ? `${u}${u.includes('?') ? '&' : '?'}token=${encodeURIComponent(token())}` : u);
  const fileUrl = (name) => withToken(`${BASE}/plans/${S.plan.id}/files/${name}`);
  const say = (m, bad) => { S.msg = m || ''; S.bad = !!bad; paintStatus(); };

  async function call(method, path, body) {
    const r = await fetch(BASE + path, body === undefined ? { method } : { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof d.detail === 'string' ? d.detail : `HTTP ${r.status}`);
    return d;
  }
  async function guard(label, fn) {   // one place where a failed call becomes a visible message
    S.busy = label; paintBusy();
    try { return await fn(); } catch (e) { say(`${label}: ${e.message}`, true); return null; } finally { S.busy = ''; paintBusy(); }
  }
  const save = () => { try { localStorage.setItem(LS, JSON.stringify({ planId: S.plan && S.plan.id })); } catch (e) { /* private mode */ } };
  const remembered = () => { try { return (JSON.parse(localStorage.getItem(LS) || '{}') || {}).planId || null; } catch (e) { return null; } };

  // ---------- data ----------
  async function refreshPlans() { S.plans = await call('GET', '/plans'); paintPlanSelect(); }
  async function loadPlan(id) {
    S.plan = await call('GET', `/plans/${id}`); S.seen = S.plan.version; save();
    if (S.sel && !S.plan.cues.some((c) => c.id === S.sel)) S.sel = null;
    el.video.src = withToken(`${BASE}/plans/${id}/video`);
    paintAll();
  }
  async function reload() { if (S.plan) { S.plan = await call('GET', `/plans/${S.plan.id}`); S.seen = S.plan.version; paintAll(); } }
  async function openVideo(path) {
    return guard('Open video', async () => {
      await refreshPlans();
      const have = S.plans.find((p) => p.video_path === path);
      const plan = have ? { id: have.id } : await call('POST', '/plans', { video_path: path });
      await loadPlan(plan.id); await refreshPlans();
      say(have ? 'Opened the existing sound plan for this video.' : 'New sound plan created. Next: Spot to find the picture cuts.');
    });
  }
  async function pickVideo() {
    const r = await guard('Choose video', () => fetch('/api/chronoflow/library/pick_files', { method: 'POST' }).then((x) => x.json()));
    if (r && r.paths && r.paths[0]) openVideo(r.paths[0]);
  }
  async function edit(body, note) { return guard(note || 'Save', async () => { S.plan = await call('PUT', `/plans/${S.plan.id}`, body); S.seen = S.plan.version; paintAll(); return S.plan; }); }

  async function spot() {
    const p = await guard('Spot', () => call('POST', `/plans/${S.plan.id}/spot`));
    if (p) { S.plan = p; S.seen = p.version; paintAll(); say(`Found ${p.cuts.length} picture cut(s); drafted ${p.cues.filter((c) => c.status === 'draft').length} cue(s). Rewrite the intents, then Source.`); }
  }
  async function sourceOne(id, mode) {
    const p = await call('POST', `/plans/${S.plan.id}/cues/${id}/source`, mode ? { mode } : {});
    S.plan = p; S.seen = p.version; paintAll();
  }
  async function sourceAll() {
    const todo = S.plan.cues.filter((c) => c.status === 'draft' || c.status === 'failed').map((c) => c.id);
    if (!todo.length) { say('Nothing to source: every cue already has a sound or is waiting for a pick.'); return; }
    let ok = 0, bad = 0;
    await guard('Source all', async () => {
      for (let i = 0; i < todo.length; i++) {
        S.busy = `Sourcing ${i + 1}/${todo.length}`; paintBusy();
        try { await sourceOne(todo[i]); ok++; } catch (e) { bad++; S.lastErr = e.message; }
      }
    });
    say(`Sourced ${ok} cue(s)${bad ? `, ${bad} could not be sourced (${S.lastErr})` : ''}.`, !!bad);
  }
  async function runQa() {
    const q = await guard('QA', () => call('POST', `/plans/${S.plan.id}/qa`));
    if (q) { S.qa = q; await reload(); say(`QA: ${q.errors} error(s), ${q.warnings} warning(s).`, q.errors > 0); }
  }

  // poll: an agent may change the plan while the page is open
  function poll() {
    clearTimeout(S.timer);
    if (!S.open) return;
    S.timer = setTimeout(async () => {
      try {
        if (S.plan && !S.busy) {
          const rows = await call('GET', '/plans');
          const row = rows.find((r) => r.id === S.plan.id);
          if (row && M.needsRefresh(S.seen, row.version)) { await reload(); say('The plan was changed elsewhere (an agent or another tab); refreshed.'); }
        }
      } catch (e) { /* engine busy: try again */ }
      poll();
    }, 3000);
  }

  // ---------- painting ----------
  function paintStatus() { if (el.status) { el.status.textContent = S.busy ? `${S.busy}…` : S.msg; el.status.className = 'au-status' + (S.bad && !S.busy ? ' bad' : ''); } }
  function paintBusy() {
    paintStatus();
    for (const b of el.actions || []) b.disabled = !!S.busy || !S.plan;
    if (el.inspBody) for (const b of el.inspBody.querySelectorAll('button')) b.disabled = !!S.busy;   // the inspector is drawn while a call may be in flight
  }
  function paintPlanSelect() {
    if (!el.planSel) return;
    el.planSel.replaceChildren(h('option', { value: '' }, S.plans.length ? 'Choose a sound plan…' : 'No sound plans yet'),
      ...S.plans.map((p) => h('option', { value: p.id, selected: S.plan && S.plan.id === p.id }, `${p.video_name} · ${S.plan && S.plan.id === p.id ? S.plan.cues.length : p.cues} cue(s)`)));
  }
  function paintCues() {
    const list = el.cueList, p = S.plan;
    list.replaceChildren();
    el.cueHead.textContent = p ? `Cues (${p.cues.length})` : 'Cues';
    if (!p) { list.append(h('div', { class: 'au-empty' }, 'Open a finished video to start.', h('br'), 'Use “Open video…”, or “Open in Audio” on a video in Media.')); return; }
    if (!p.cues.length) { list.append(h('div', { class: 'au-empty' }, 'No cues yet. “Spot” finds the picture cuts and drafts whooshes and an underscore.')); return; }
    const order = [...p.cues].sort((a, b) => (a.hit_t != null ? a.hit_t : a.t_in || 0) - (b.hit_t != null ? b.hit_t : b.t_in || 0));
    for (const c of order) {
      const chip = M.statusChip(c), lane = M.LANES.find((l) => l.id === c.track), t = c.hit_t != null ? c.hit_t : c.t_in || 0;
      const row = h('button', { type: 'button', class: 'au-cue' + (S.sel === c.id ? ' sel' : ''), 'data-cue': c.id, title: c.reason || c.intent || c.kind,
        onclick: () => selectCue(c.id, true) },
        h('span', { class: `au-chip ${chip.tone}` }, chip.text), h('span', { class: 'au-lane' }, lane ? lane.label : c.track),
        h('span', { class: 'au-cue-text' }, c.intent || c.kind), h('span', { class: 'au-tc' }, M.fmtTC(t, p.fps)));
      list.append(row);
    }
  }
  function paintHeader() {
    const p = S.plan;
    el.title.textContent = p ? p.video_path.split(/[\\/]/).pop() : 'No video open';
    el.badge.textContent = p ? `${p.fps} fps · ${M.fmtTC(p.duration, p.fps)}` : '';
    if (el.mode) { el.mode.value = p ? p.mode : 'auto'; el.mode.disabled = !p; }
    if (el.ccby) { el.ccby.checked = !!(p && p.allow_cc_by); el.ccby.disabled = !p; }
    paintBusy();
  }
  function paintAll() { paintPlanSelect(); paintHeader(); paintCues(); renderInspector(); renderLanes(); }
  function selectCue(id, seek) {
    S.sel = id; paintCues(); renderInspector(); renderLanes();
    const c = S.plan.cues.find((x) => x.id === id);
    if (seek && c && el.video) { const t = c.hit_t != null ? c.hit_t : c.t_in || 0; try { el.video.currentTime = Math.max(0, t - 0.5); } catch (e) { /* not loaded yet */ } }
  }
  // ---------- inspector ----------
  const KINDS = ['whoosh', 'impact', 'click', 'pop', 'ding', 'riser', 'drop', 'noise_bed', 'music'];
  const cueById = (id) => (S.plan ? S.plan.cues.find((c) => c.id === id) : null);
  const num = (v) => { const n = parseFloat(v); return Number.isFinite(n) ? n : null; };
  const patchCue = (id, fields, note) => edit({ cues: [{ id, ...fields }] }, note || 'Save cue');
  const field = (label, control, hint) => h('div', { class: 'dl-field' }, h('span', { class: 'dl-lab' }, label), control, hint ? h('span', { class: 'dl-hint' }, hint) : null);
  const numIn = (value, step, onchange, attrs) => h('input', { class: 'dl-in au-num', type: 'number', step, value: value == null ? '' : value, onchange, ...(attrs || {}) });
  const nextCueId = () => { let n = 1; while (cueById(`cue_${String(n).padStart(2, '0')}`)) n++; return `cue_${String(n).padStart(2, '0')}`; };

  async function addCueAtPlayhead() {
    if (!S.plan) return;
    const id = nextCueId(), t = M.snapFrame(el.video ? el.video.currentTime : 0, S.plan.fps);
    const p = await edit({ cues: [{ id, track: 'sfx', kind: 'whoosh', intent: 'whoosh swish', hit_t: t }] }, 'Add cue');
    if (p) { selectCue(id, false); const i = el.inspBody.querySelector('textarea'); if (i) i.focus(); say(`Added ${id} at ${M.fmtTC(t, S.plan.fps)}. Edit its words, then Source.`); }
  }
  async function deleteCue(id) { const p = await edit({ remove_cues: [id] }, 'Delete cue'); if (p) { S.sel = null; paintAll(); say(`Deleted ${id}.`); } }
  async function sourceSel(id) {
    const c = cueById(id), mode = c && c.mode;
    await guard('Source', async () => { await sourceOne(id, mode || undefined); });
    const n = cueById(id);
    if (n) say(n.status === 'ready' ? `${id}: sound found (${(n.takes.find((t) => t.id === n.chosen_take) || { provenance: {} }).provenance.source}).`
      : n.status === 'needs_pick' ? `${id}: ${n.candidates.length} candidate(s). Pick one in the inspector.` : `${id}: ${n.reason || 'no sound found'}`, n.status === 'failed');
  }
  async function pickCandidate(id, candId) { const p = await guard('Pick', () => call('POST', `/plans/${S.plan.id}/cues/${id}/pick`, { candidate_id: candId })); if (p) { S.plan = p; S.seen = p.version; paintAll(); say(`${id}: picked.`); } }

  function provenanceBlock(t) {
    const pv = t.provenance || {};
    return h('div', { class: 'au-prov' },
      h('div', {}, h('b', {}, pv.source || 'unknown source'), pv.model ? ` · ${pv.model}` : '', pv.seed != null ? ` · seed ${pv.seed}` : ''),
      h('div', {}, `Licence: ${pv.licence || 'unknown'}`, pv.author ? ` · by ${pv.author}` : ''),
      pv.url ? h('a', { href: pv.url, target: '_blank', rel: 'noopener noreferrer', class: 'au-link' }, 'Open the source page') : null,
      h('div', { class: 'dl-hint' }, `${t.duration_s.toFixed(2)} s · peak ${t.peak_db.toFixed(1)} dBFS · hit at ${t.onset_s.toFixed(2)} s`));
  }
  function candidateRow(c, cueId) {
    return h('div', { class: 'au-cand', 'data-cand': c.id },
      h('div', { class: 'au-cand-info' }, h('b', {}, c.label || c.id), h('span', { class: 'dl-hint' }, `${c.provenance.source} · ${c.provenance.licence} · ${c.duration_s.toFixed(1)} s`)),
      h('button', { type: 'button', class: 'dl-btn accent', onclick: () => pickCandidate(cueId, c.id) }, 'Pick'));
  }

  function renderInspector() {
    const box = el.inspBody; if (!box) return;
    box.replaceChildren();
    const p = S.plan;
    if (!p) { box.append(h('div', { class: 'au-empty' }, 'Open a video to see its cues.')); return; }
    const c = cueById(S.sel);
    box.append(h('button', { type: 'button', class: 'dl-btn', id: 'auAddCue', onclick: addCueAtPlayhead, title: 'Add a sound effect cue at the video position' }, '+ Cue at playhead'));
    if (!c) { box.append(h('div', { class: 'au-empty' }, 'Select a cue in the list or on a lane to edit it.')); return; }
    const chip = M.statusChip(c), isHit = c.hit_t != null, fps = p.fps, take = M.chosenTake(c);
    box.append(
      h('div', { class: 'au-insp-top' }, h('span', { class: `au-chip ${chip.tone}` }, chip.text), h('b', {}, c.id), h('span', { class: 'au-tc' }, isHit ? M.fmtTC(c.hit_t, fps) : `${M.fmtTC(c.t_in || 0, fps)} – ${c.t_out != null ? M.fmtTC(c.t_out, fps) : 'end of sound'}`)),
      c.reason ? h('div', { class: 'dl-error' }, c.reason) : null,
      field('What it should sound like', h('textarea', { class: 'dl-in au-intent', rows: 2, onchange: (e) => patchCue(c.id, { intent: e.target.value }) }, c.intent || ''),
        'Plain words, like searching a sound library. The Openverse search uses this text.'),
      h('div', { class: 'au-two' },
        field('Kind', h('input', { class: 'dl-in', list: 'auKinds', value: c.kind, onchange: (e) => e.target.value.trim() && patchCue(c.id, { kind: e.target.value.trim() }) }),
          'Synth knows: whoosh, impact, click, pop, ding, riser, drop, noise_bed. Music goes to ACE-Step.'),
        field('Lane', h('select', { class: 'dl-in', onchange: (e) => patchCue(c.id, { track: e.target.value }) },
          ...M.LANES.filter((l) => l.id !== 'dialogue').map((l) => h('option', { value: l.id, selected: c.track === l.id }, l.label))))),
      h('datalist', { id: 'auKinds' }, ...KINDS.map((k) => h('option', { value: k }))),
      isHit ? h('div', { class: 'au-two' },
        field('Hit time (s)', h('div', { class: 'au-nudge' },
          h('button', { type: 'button', class: 'dl-btn', title: 'One frame earlier (Shift: ten)', onclick: (e) => patchCue(c.id, { hit_t: Math.max(0, M.snapFrame(c.hit_t - (e.shiftKey ? 10 : 1) / fps, fps)) }) }, '◀'),
          numIn(c.hit_t.toFixed(3), '0.001', (e) => { const v = num(e.target.value); if (v != null) patchCue(c.id, { hit_t: v }); }),
          h('button', { type: 'button', class: 'dl-btn', title: 'One frame later (Shift: ten)', onclick: (e) => patchCue(c.id, { hit_t: Math.min(p.duration, M.snapFrame(c.hit_t + (e.shiftKey ? 10 : 1) / fps, fps)) }) }, '▶'))),
        field('Lands on', h('select', { class: 'dl-in', onchange: (e) => patchCue(c.id, { anchor: e.target.value }) },
          h('option', { value: 'onset', selected: c.anchor === 'onset' }, 'the start (hits, clicks)'), h('option', { value: 'peak', selected: c.anchor === 'peak' }, 'the swell (whooshes, risers)'))))
        : h('div', { class: 'au-two' },
          field('From (s)', numIn((c.t_in || 0).toFixed(3), '0.001', (e) => { const v = num(e.target.value); if (v != null) patchCue(c.id, { t_in: v }); })),
          field('To (s)', numIn(c.t_out == null ? '' : c.t_out.toFixed(3), '0.001', (e) => { const v = num(e.target.value); if (v != null) patchCue(c.id, { t_out: v }); }, { placeholder: 'sound length' }))),
      h('div', { class: 'au-three' },
        field('Gain (dB)', numIn(c.gain_db, '0.5', (e) => { const v = num(e.target.value); if (v != null) patchCue(c.id, { gain_db: v }); })),
        field('Fade in (s)', numIn(c.fade_in, '0.05', (e) => { const v = num(e.target.value); if (v != null && v >= 0) patchCue(c.id, { fade_in: v }); }, { min: 0 })),
        field('Fade out (s)', numIn(c.fade_out, '0.05', (e) => { const v = num(e.target.value); if (v != null && v >= 0) patchCue(c.id, { fade_out: v }); }, { min: 0 }))),
      field('Sourcing for this cue', h('select', { class: 'dl-in', onchange: (e) => patchCue(c.id, { mode: e.target.value || null }) },
        h('option', { value: '', selected: !c.mode }, 'Same as the plan'), h('option', { value: 'auto', selected: c.mode === 'auto' }, 'Auto: the engine picks'), h('option', { value: 'ask', selected: c.mode === 'ask' }, 'Ask me: I pick'))),
      h('div', { class: 'dl-sub' }, 'Sound'),
      take ? provenanceBlock(take) : h('div', { class: 'au-empty' }, c.status === 'needs_pick' ? 'Candidates are waiting for your pick.' : 'No sound yet.'),
      c.candidates && c.candidates.length ? h('div', { class: 'au-cands' }, ...c.candidates.map((cd) => candidateRow(cd, c.id))) : null,
      h('div', { class: 'au-actions' },
        h('button', { type: 'button', class: 'dl-btn accent', id: 'auSourceCue', onclick: () => sourceSel(c.id), disabled: !!S.busy }, take || c.candidates.length ? 'Source again' : 'Source'),
        h('button', { type: 'button', class: 'dl-btn', id: 'auDeleteCue', onclick: () => deleteCue(c.id), disabled: !!S.busy }, 'Delete cue')));
  }
  // ---------- lanes: ruler, five lanes of cue blocks with waveforms, picture cuts, playhead ----------
  const LANE_H = 52, HEAD_W = 64, RULER_H = 24, MIN_PPS = 4, MAX_PPS = 1200;
  const L = { view: { t0: 0, pps: 40 }, fittedFor: null, peaks: {}, loading: new Set(), drag: null, scrub: false, pending: 0, cv: {} };
  const COL = { bg: '#0a1128', grid: 'rgba(122,162,255,.08)', cut: 'rgba(122,162,255,.35)', ready: ['#1c3f86', '#4f7be8'], wave: '#a9c7ff', hit: '#ffd166', sel: '#ffffff',
    draft: '#6a76a3', failed: '#f2667a', pick: '#f0b14a', text: '#eaf0ff' };

  function buildLanes() {
    el.bottom.replaceChildren();
    const btn = (t, f, title) => h('button', { type: 'button', class: 'dl-btn au-mini', title, onclick: f }, t);
    el.zoomLabel = h('span', { class: 'au-hint' });
    const bar = h('div', { class: 'au-lanebar' }, btn('−', () => zoom(1 / 1.4), 'Zoom out'), btn('+', () => zoom(1.4), 'Zoom in'), btn('Fit', fit, 'Show the whole video'), el.zoomLabel,
      h('span', { class: 'au-hint au-right' }, 'Wheel: zoom · Shift+wheel: scroll · Drag a block: move its hit · ←/→: one frame'));
    el.laneRows = h('div', { class: 'au-lanerows' });
    const rulerCv = h('canvas', { class: 'au-cv au-rulercv', 'data-lane': 'ruler' });
    el.laneRows.append(h('div', { class: 'au-row', style: `height:${RULER_H}px` }, h('div', { class: 'au-head' }, ''), rulerCv));
    L.cv.ruler = rulerCv;
    for (const lane of M.LANES) {
      const cv = h('canvas', { class: 'au-cv', 'data-lane': lane.id }); L.cv[lane.id] = cv;
      el.laneRows.append(h('div', { class: 'au-row', style: `height:${LANE_H}px` }, h('div', { class: 'au-head', title: lane.id }, lane.label), cv));
    }
    el.playhead = h('div', { class: 'au-playhead' });
    el.laneScroll = h('div', { class: 'au-lanescroll' }, el.laneRows, el.playhead);
    el.lanes = h('div', { class: 'au-lanes', tabindex: '0', 'aria-label': 'Sound lanes. Arrow keys move the selected cue by one frame.', onkeydown: onLaneKey },
      h('div', { class: 'au-lanearea' }, bar, el.laneScroll));
    el.mixerHost = h('div', { class: 'au-mixer' });
    el.bottom.append(el.lanes, el.mixerHost);
    for (const id of ['ruler', ...M.LANES.map((l) => l.id)]) bindCanvas(L.cv[id], id);
    el.laneScroll.addEventListener('wheel', onWheel, { passive: false });
    if (window.ResizeObserver) new ResizeObserver(() => { if (S.plan) { if (L.fittedFor !== S.plan.id) fit(); else scheduleDraw(); } }).observe(el.laneScroll);
  }
  const cvWidth = () => (L.cv.ruler ? L.cv.ruler.clientWidth : 0);
  function fit() { const w = cvWidth(); if (!S.plan || w < 50) return; L.view = { t0: 0, pps: Math.max(MIN_PPS, w / Math.max(S.plan.duration, 1)) }; L.fittedFor = S.plan.id; scheduleDraw(); }
  function zoom(f, anchorT) { const w = cvWidth(), a = anchorT != null ? anchorT : L.view.t0 + w / L.view.pps / 2; L.view = M.zoomAt(L.view, f, a, { minPps: MIN_PPS, maxPps: MAX_PPS }); scheduleDraw(); }
  function onWheel(e) {
    if (!S.plan) return; e.preventDefault();
    const r = L.cv.ruler.getBoundingClientRect(), x = e.clientX - r.left;
    if (e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) { L.view = { ...L.view, t0: Math.max(0, L.view.t0 + (e.shiftKey ? e.deltaY : e.deltaX) / L.view.pps) }; scheduleDraw(); return; }
    zoom(Math.exp(-Math.max(-400, Math.min(400, e.deltaY)) * 0.0015), x >= 0 ? M.xToTime(x, L.view) : undefined);   // proportional: a notch is about 16 %, a trackpad flick is smooth
  }

  const shown = (c) => (L.drag && L.drag.id === c.id ? { ...c, ...L.drag.patch } : c);
  function cueAt(laneId, x) {
    const t = M.xToTime(x, L.view);
    for (let i = S.plan.cues.length - 1; i >= 0; i--) {
      const c = shown(S.plan.cues[i]); if (c.track !== laneId) continue;
      const sp = M.cueSpan(c), pad = 3 / L.view.pps;
      if (t >= sp.start - pad && t <= sp.end + pad) return S.plan.cues[i];
    }
    return null;
  }
  function bindCanvas(cv, id) {
    cv.addEventListener('pointerdown', (e) => {
      if (!S.plan || e.button !== 0) return;
      el.lanes.focus({ preventScroll: true });
      const x = e.clientX - cv.getBoundingClientRect().left;
      if (id === 'ruler') { L.scrub = true; cv.setPointerCapture(e.pointerId); seek(M.xToTime(x, L.view)); return; }
      const c = cueAt(id, x);
      if (!c) { seek(M.xToTime(x, L.view)); return; }
      if (S.sel !== c.id) selectCue(c.id, false);
      L.drag = { id: c.id, x0: e.clientX, orig: c, patch: {}, moved: false, cv }; cv.setPointerCapture(e.pointerId);
    });
    cv.addEventListener('pointermove', (e) => {
      if (L.scrub && id === 'ruler') { seek(M.xToTime(e.clientX - cv.getBoundingClientRect().left, L.view)); return; }
      const d = L.drag; if (!d || d.cv !== cv) return;
      if (Math.abs(e.clientX - d.x0) > 3) d.moved = true;
      if (d.moved) { d.patch = M.dragCue(d.orig, (e.clientX - d.x0) / L.view.pps, S.plan, S.plan.cuts || [], 8 / L.view.pps); scheduleDraw(); }
    });
    const up = async (e) => {
      L.scrub = false;
      const d = L.drag; if (!d || d.cv !== cv) return;
      L.drag = null;
      if (d.moved && Object.keys(d.patch).length) { await edit({ cues: [{ id: d.id, ...d.patch }] }, 'Move cue'); const m = cueById(d.id); if (m) say(`Moved ${d.id} to ${M.fmtTC(m.hit_t != null ? m.hit_t : m.t_in || 0, S.plan.fps)}.`); }
      else scheduleDraw();
    };
    cv.addEventListener('pointerup', up); cv.addEventListener('pointercancel', up);
  }
  function seek(t) { if (!S.plan) return; try { el.video.currentTime = Math.min(Math.max(0, t), S.plan.duration); } catch (e) { /* video not ready */ } movePlayhead(); }
  function onLaneKey(e) {
    if (!S.plan || !S.sel || (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight')) return;
    e.preventDefault();
    const c = cueById(S.sel); if (!c) return;
    const dt = (e.key === 'ArrowLeft' ? -1 : 1) * (e.shiftKey ? 10 : 1) / S.plan.fps;
    edit({ cues: [{ id: c.id, ...M.dragCue(c, dt, S.plan, [], 0) }] }, 'Nudge cue');
  }
  function movePlayhead() {
    if (!el.playhead || !S.plan) return;
    const x = M.timeToX(el.video.currentTime || 0, L.view), w = cvWidth();
    el.playhead.style.display = x >= 0 && x <= w ? 'block' : 'none';
    el.playhead.style.left = `${HEAD_W + x}px`;
  }

  function ensurePeaks(c) {
    const t = M.chosenTake(c); if (!t || L.peaks[t.id] || L.loading.has(t.id) || !S.plan) return;
    L.loading.add(t.id);
    call('GET', `/plans/${S.plan.id}/takes/${t.id}/peaks?bins=600`).then((r) => { L.peaks[t.id] = r.peaks; }).catch(() => { L.peaks[t.id] = []; })
      .finally(() => { L.loading.delete(t.id); scheduleDraw(); });
  }
  function colPeak(peaks, a, b) {   // max of the peaks between fractions a and b of the sound, wrapping so a looped bed repeats
    const n = peaks.length; if (!n) return 0;
    if (b - a >= 1) return Math.max(...peaks);
    const fa = ((a % 1) + 1) % 1, i0 = Math.floor(fa * n), i1 = Math.max(i0 + 1, Math.ceil((fa + (b - a)) * n));
    let m = 0; for (let k = i0; k < i1; k++) { const v = peaks[k % n]; if (v > m) m = v; } return m;
  }

  function scheduleDraw() { if (L.pending) return; L.pending = setTimeout(() => { L.pending = 0; draw(); }, 0); }
  function sizeCanvas(cv, hCss) {
    const dpr = window.devicePixelRatio || 1, w = cv.clientWidth, w2 = Math.round(w * dpr), h2 = Math.round(hCss * dpr);
    if (cv.width !== w2 || cv.height !== h2) { cv.width = w2; cv.height = h2; }
    const g = cv.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); return { g, w };
  }
  function drawRuler() {
    const { g, w } = sizeCanvas(L.cv.ruler, RULER_H), fps = S.plan.fps;
    g.fillStyle = '#0f1740'; g.fillRect(0, 0, w, RULER_H); g.font = '10px monospace'; g.textBaseline = 'middle';
    for (const k of M.rulerTicks(L.view, w, fps)) {
      const x = Math.round(M.timeToX(k.t, L.view)) + 0.5;
      g.strokeStyle = k.major ? '#5a6bb0' : '#2a3770'; g.beginPath(); g.moveTo(x, k.major ? 8 : 16); g.lineTo(x, RULER_H); g.stroke();
      if (k.major) { g.fillStyle = '#9aa6d0'; g.fillText(M.fmtTC(k.t, fps).slice(3), x + 3, 8); }
    }
    for (const c of S.plan.cuts || []) { const x = M.timeToX(c, L.view); if (x >= 0 && x <= w) { g.fillStyle = '#7aa2ff'; g.fillRect(Math.round(x) - 1, RULER_H - 5, 3, 5); } }
  }
  function drawLane(lane) {
    const { g, w } = sizeCanvas(L.cv[lane.id], LANE_H), p = S.plan, v = L.view, fps = p.fps;
    g.fillStyle = COL.bg; g.fillRect(0, 0, w, LANE_H);
    for (const k of M.rulerTicks(v, w, fps)) if (k.major) { g.fillStyle = COL.grid; g.fillRect(Math.round(M.timeToX(k.t, v)), 0, 1, LANE_H); }
    g.fillStyle = COL.cut; for (const c of p.cuts || []) { const x = M.timeToX(c, v); if (x >= -1 && x <= w + 1) g.fillRect(Math.round(x), 0, 1, LANE_H); }
    for (const raw of p.cues) {
      if (raw.track !== lane.id) continue;
      const c = shown(raw), sp = M.cueSpan(c), x0 = M.timeToX(sp.start, v), x1 = M.timeToX(sp.end, v);
      if (x1 < 0 || x0 > w) continue;
      const bw = Math.max(4, x1 - x0), y = 5, bh = LANE_H - 10, sel = S.sel === c.id, take = M.chosenTake(c);
      const style = c.status === 'ready' ? COL.ready : null, edge = c.status === 'failed' ? COL.failed : c.status === 'needs_pick' ? COL.pick : c.status === 'draft' ? COL.draft : COL.ready[1];
      g.fillStyle = style ? style[0] : c.status === 'failed' ? 'rgba(242,102,122,.12)' : c.status === 'needs_pick' ? 'rgba(240,177,74,.12)' : 'rgba(106,118,163,.12)';
      g.fillRect(x0, y, bw, bh);
      if (take) {
        ensurePeaks(c);
        const peaks = L.peaks[take.id];
        if (peaks && peaks.length) {
          const off = c.hit_t != null ? (c.anchor === 'peak' ? take.peak_s : take.onset_s) : 0, trim = c.hit_t != null ? Math.max(0, off - c.hit_t) : 0, dur = Math.max(take.duration_s, 0.01);
          g.fillStyle = COL.wave; g.globalAlpha = 0.85;
          const from = Math.max(0, Math.floor(x0)), to = Math.min(w, Math.ceil(x0 + bw));
          for (let x = from; x < to; x += 1) {
            const ta = M.xToTime(x, v) - sp.start + trim, tb = M.xToTime(x + 1, v) - sp.start + trim, pk = colPeak(peaks, ta / dur, tb / dur), hh = Math.max(1, pk * (bh - 6));
            g.fillRect(x, y + bh / 2 - hh / 2, 1, hh);
          }
          g.globalAlpha = 1;
        }
      }
      g.lineWidth = sel ? 2 : 1; g.strokeStyle = sel ? COL.sel : edge; g.setLineDash(c.status === 'draft' ? [4, 3] : []); g.strokeRect(x0 + 0.5, y + 0.5, bw - 1, bh - 1); g.setLineDash([]);
      if (c.hit_t != null) { const hx = Math.round(M.timeToX(c.hit_t, v)); g.fillStyle = COL.hit; g.fillRect(hx, y - 3, 2, bh + 6); }
      g.save(); g.beginPath(); g.rect(x0, y, bw, bh); g.clip(); g.fillStyle = COL.text; g.font = '10px sans-serif'; g.textBaseline = 'top';
      g.fillText(c.intent || c.kind, Math.max(x0, 0) + 4, y + 2); g.restore();
    }
  }
  function draw() {
    if (!S.plan || !el.lanes || cvWidth() < 50) return;
    if (L.fittedFor !== S.plan.id) { fit(); return; }
    drawRuler(); for (const lane of M.LANES) drawLane(lane);
    if (el.zoomLabel) el.zoomLabel.textContent = `${Math.round(L.view.pps)} px/s`;
    movePlayhead();
  }
  function renderLanes() { if (!el.lanes) return; if (S.plan) for (const c of S.plan.cues) ensurePeaks(c); scheduleDraw(); }

  // ---------- mount / open / close ----------
  function mount() {
    if (S.mounted) return;
    el.left = $('#audioPlanPane'); el.mon = $('#audioMonitor'); el.insp = $('#audioInspector'); el.bottom = $('#audioPanel');
    if (!el.left || !el.mon || !el.insp || !el.bottom || !M) return;
    el.planSel = h('select', { class: 'dl-in', 'aria-label': 'Sound plan', onchange: (e) => { if (e.target.value) guard('Open plan', () => loadPlan(e.target.value)); } });
    el.mode = h('select', { class: 'dl-in', 'aria-label': 'How cues are sourced', onchange: (e) => edit({ mode: e.target.value }, 'Mode') },
      h('option', { value: 'auto' }, 'Auto: the engine picks'), h('option', { value: 'ask' }, 'Ask me: I pick'));
    el.ccby = h('input', { type: 'checkbox', onchange: (e) => edit({ allow_cc_by: e.target.checked }, 'Licence') });
    el.actions = [
      h('button', { type: 'button', class: 'dl-btn', id: 'auSpot', title: 'Find the picture cuts and draft cues', onclick: spot }, 'Spot'),
      h('button', { type: 'button', class: 'dl-btn', id: 'auSourceAll', title: 'Find a sound for every cue that has none', onclick: sourceAll }, 'Source all'),
      h('button', { type: 'button', class: 'dl-btn', id: 'auQa', title: 'Check clipping, silence and how close each hit lands to its frame', onclick: runQa }, 'QA'),
    ];
    el.cueHead = h('div', { class: 'dl-sub' }, 'Cues');
    el.cueList = h('div', { class: 'au-cues' });
    el.status = h('div', { class: 'au-status', role: 'status' });
    el.left.append(h('div', { class: 'cf-panel-head' }, 'Sound plan'),
      h('div', { class: 'au-pane' },
        h('div', { class: 'dl-field' }, h('span', { class: 'dl-lab' }, 'Plan'), el.planSel,
          h('button', { type: 'button', class: 'dl-btn', id: 'auOpen', onclick: pickVideo, title: 'Choose a finished video file' }, 'Open video…')),
        h('div', { class: 'dl-field' }, h('span', { class: 'dl-lab' }, 'Sourcing'), el.mode,
          h('label', { class: 'dl-check', title: 'Also accept CC-BY clips; credits are written to credits.txt' }, el.ccby, 'Allow CC-BY (needs credits)')),
        h('div', { class: 'au-actions' }, ...el.actions), el.cueHead, el.cueList, el.status));
    el.title = h('b', { class: 'au-title' }, 'No video open'); el.badge = h('span', { class: 'au-badge' });
    el.video = h('video', { class: 'au-video', muted: true, playsinline: true, preload: 'auto' });
    el.video.muted = true;
    el.tc = h('span', { class: 'au-tcbig' }, '00:00:00:00');
    el.mon.append(h('div', { class: 'au-monhead' }, el.title, el.badge), h('div', { class: 'au-videowrap' }, el.video),
      h('div', { class: 'au-transport' }, el.tc));
    el.video.addEventListener('timeupdate', () => { if (S.plan) { el.tc.textContent = M.fmtTC(el.video.currentTime, S.plan.fps); movePlayhead(); } });
    el.video.addEventListener('seeked', () => movePlayhead());
    el.insp.append(h('div', { class: 'cf-panel-head' }, 'Cue'), (el.inspBody = h('div', { class: 'au-pane' })));
    buildLanes();
    S.mounted = true; paintAll();
  }
  async function open() {
    mount(); if (!S.mounted) return;
    S.open = true;
    await guard('Load plans', async () => {
      await refreshPlans();
      const want = (S.plan && S.plan.id) || remembered();
      if (want && S.plans.some((p) => p.id === want)) await loadPlan(want); else paintAll();
    });
    poll();
  }
  function close() { S.open = false; clearTimeout(S.timer); if (el.video) el.video.pause(); }

  window.NLEAudio = { mount, open, close, openVideo, get state() { return S; }, selectCue, reload, call, edit, sourceOne, guard, say, addCueAtPlayhead, fit, zoom, seek, get view() { return L.view; }, get peaks() { return L.peaks; } };
})();
