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
  function paintBusy() { paintStatus(); for (const b of el.actions || []) b.disabled = !!S.busy || !S.plan; }
  function paintPlanSelect() {
    if (!el.planSel) return;
    el.planSel.replaceChildren(h('option', { value: '' }, S.plans.length ? 'Choose a sound plan…' : 'No sound plans yet'),
      ...S.plans.map((p) => h('option', { value: p.id, selected: S.plan && S.plan.id === p.id }, `${p.video_name} · ${p.cues} cue(s)`)));
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
  function renderInspector() { /* Task 5 */ }
  function renderLanes() { /* Task 6 */ }

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
    el.video.addEventListener('timeupdate', () => { if (S.plan) el.tc.textContent = M.fmtTC(el.video.currentTime, S.plan.fps); });
    el.insp.append(h('div', { class: 'cf-panel-head' }, 'Cue'), (el.inspBody = h('div', { class: 'au-pane' })));
    el.bottom.append((el.lanes = h('div', { class: 'au-lanes' })));
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

  window.NLEAudio = { mount, open, close, openVideo, get state() { return S; }, selectCue, reload, call, edit, sourceOne, guard, say };
})();
