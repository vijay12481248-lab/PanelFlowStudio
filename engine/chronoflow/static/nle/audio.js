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

  window.NLEAudio = { mount, open, close, openVideo, get state() { return S; }, selectCue, reload, call, edit, sourceOne, guard, say, addCueAtPlayhead };
})();
