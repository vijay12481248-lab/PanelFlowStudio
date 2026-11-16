/* ChronoFlow Audio page - the cockpit for a video's sound plan (engine/audio/studio, REST /api/audio/studio).
   Left: plan, mode and the cue list. Centre: the video. Right: the selected cue. Bottom: lanes and mixer.
   All state lives on the server (the plan); this page only reads it, sends small edits and plays the preview stems.
   Pure maths is in audio-model.js. Reuses the Deliver page's .dl-* control styles. */
(function () {
  'use strict';
  const M = window.AudioModel;
  const BASE = '/api/audio/studio', LS = 'nle:audio:v1';
  const S = { busyN: 0, loadSeq: 0, openingVideo: false, open: false, mounted: false, plans: [], plan: null, sel: null, busy: '', msg: '', bad: false, seen: null, timer: 0, qa: null, lastErr: '' };
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
    if (S.busyN++ === 0) S.busy = label;   // the first (longest-running) job names the busy state; later short calls do not replace it
    paintBusy();
    try { return await fn(); } catch (e) { say(`${label}: ${e.message}`, true); return null; } finally { if (--S.busyN === 0) S.busy = ''; paintBusy(); }
  }
  const isCurrent = (id) => !!S.plan && S.plan.id === id;   // a slow answer for a plan that is no longer open is dropped
  const save = () => { try { localStorage.setItem(LS, JSON.stringify({ planId: S.plan && S.plan.id })); } catch (e) { /* private mode */ } };
  const remembered = () => { try { return (JSON.parse(localStorage.getItem(LS) || '{}') || {}).planId || null; } catch (e) { return null; } };

  // ---------- data ----------
  async function refreshPlans() {   // the newest answer wins: two refreshes can overlap (open + openVideo) and the older one must not overwrite the newer
    const seq = (S.plansSeq = (S.plansSeq || 0) + 1), rows = await call('GET', '/plans');
    if (seq === S.plansSeq) { S.plans = rows; paintPlanSelect(); }
  }
  async function loadPlan(id) {
    const seq = ++S.loadSeq, plan = await call('GET', `/plans/${id}`);
    if (seq !== S.loadSeq) return;   // a newer open/load started meanwhile
    const prev = S.plan && S.plan.id; S.plan = plan; S.seen = S.plan.version; save();
    if (prev !== id) { S.qa = null; S.msg = ''; S.bad = false; P.master_info = null; if (P.playing) pause(); P.preview = null; P.stale = true; for (const st of M.STEMS) { P.els[st].removeAttribute('src'); delete P.els[st].dataset.url; } }
    if (S.sel && !S.plan.cues.some((c) => c.id === S.sel)) S.sel = null;
    const vurl = withToken(`${BASE}/plans/${id}/video`);
    if (el.video.dataset.url !== vurl) { el.video.dataset.url = vurl; el.video.src = vurl; }   // do not reload (and rewind) the video for the same plan
    paintAll();
  }
  async function reload() {
    if (!S.plan) return;
    const id = S.plan.id, p = await call('GET', `/plans/${id}`);
    if (isCurrent(id)) { S.plan = p; S.seen = p.version; paintAll(); }
  }
  async function openVideo(path) {
    S.openingVideo = true;   // open() must not load the remembered plan over the one being opened here
    return guard('Open video', async () => {
      await refreshPlans();
      const have = S.plans.find((p) => p.video_path === path);
      const plan = have ? { id: have.id } : await call('POST', '/plans', { video_path: path });
      await loadPlan(plan.id); await refreshPlans();
      say(have ? 'Opened the existing sound plan for this video.' : 'New sound plan created. Next: Spot to find the picture cuts.');
    }).finally(() => { S.openingVideo = false; });
  }
  async function pickVideo() {
    const r = await guard('Choose video', () => fetch('/api/chronoflow/library/pick_files', { method: 'POST' }).then((x) => x.json()));
    if (r && r.paths && r.paths[0]) openVideo(r.paths[0]);
  }
  async function edit(body, note) {
    const id = S.plan && S.plan.id;
    return guard(note || 'Save', async () => {
      const p = await call('PUT', `/plans/${id}`, body);
      if (!isCurrent(id)) return null;   // saved on the server, but another plan is open now: do not paint this one over it
      S.plan = p; S.seen = p.version; paintAll(); return S.plan;
    });
  }

  async function spot() {
    const id = S.plan.id, p = await guard('Spot', () => call('POST', `/plans/${id}/spot`));
    if (p && isCurrent(id)) { S.plan = p; S.seen = p.version; paintAll(); say(`Found ${p.cuts.length} picture cut(s); drafted ${p.cues.filter((c) => c.status === 'draft').length} cue(s). Rewrite the intents, then Source.`); }
  }
  async function runAutoFoley() {
    if (!S.plan) return;
    const id = S.plan.id;
    let scenes = [];
    if (window._newVideo && typeof window._newVideo.scenesNow === 'function') {
      scenes = window._newVideo.scenesNow();
    } else if (window.scenes) {
      scenes = window.scenes;
    }
    if (!scenes || !scenes.length) {
      const cuts = S.plan.cuts && S.plan.cuts.length ? S.plan.cuts : [0.0];
      const dur = S.plan.duration || 10.0;
      const b = [...cuts, dur];
      for (let i = 0; i < b.length - 1; i++) {
        scenes.push({ prompt: `Scene ${i + 1}`, duration: Math.max(1.0, b[i + 1] - b[i]) });
      }
    }
    const res = await guard('Auto-design foley', () => call('POST', `/plans/${id}/auto_foley`, { scenes, auto_source: true }));
    if (res && res.plan && isCurrent(id)) {
      S.plan = res.plan;
      S.seen = res.plan.version;
      paintAll();
      say(`🪄 Auto-designed ${res.cue_count} soundscape and foley cue(s)!`);
      previewSoon();
    }
  }
  async function sourceOne(id, mode) {
    const pid = S.plan.id, p = await call('POST', `/plans/${pid}/cues/${id}/source`, mode ? { mode } : {});
    if (!isCurrent(pid)) return;
    S.plan = p; S.seen = p.version; paintAll();
  }
  async function sourceAll() {
    const todo = S.plan.cues.filter((c) => c.status === 'draft' || c.status === 'failed').map((c) => c.id);
    if (!todo.length) { say('Nothing to source: every cue already has a sound or is waiting for a pick.'); return; }
    let ok = 0, bad = 0;
    const planId = S.plan.id;
    await guard('Source all', async () => {
      for (let i = 0; i < todo.length; i++) {
        S.busy = `Sourcing ${i + 1}/${todo.length}`; paintBusy();
        if (!isCurrent(planId)) break;   // the owner opened another video: stop sourcing this one
        try { await sourceOne(todo[i]); ok++; } catch (e) { bad++; S.lastErr = e.message; }
      }
    });
    say(`Sourced ${ok} cue(s)${bad ? `, ${bad} could not be sourced (${S.lastErr})` : ''}.`, !!bad);
  }
  async function runQa() {
    const id = S.plan.id, q = await guard('QA', () => call('POST', `/plans/${id}/qa`));
    if (q && isCurrent(id)) { S.qa = q; await reload(); say(`QA: ${q.errors} error(s), ${q.warnings} warning(s).`, q.errors > 0); }
  }

  // ---------- critique ----------
  async function runCritique() {
    if (!S.plan) return;
    const id = S.plan.id, rep = await guard('Critique', () => call('POST', `/plans/${id}/critique`));
    if (rep && isCurrent(id)) {
      showCritiqueModal(rep);
    }
  }
  async function applyCritiqueRemediations(ids) {
    if (!S.plan || !ids || !ids.length) return;
    const id = S.plan.id;
    const res = await guard('Apply remediations', () => call('POST', `/plans/${id}/critique/apply`, { remediation_ids: ids }));
    if (res && isCurrent(id)) {
      S.plan = res.plan; S.seen = res.plan.version; paintAll();
      const rep = await call('POST', `/plans/${id}/critique`);
      showCritiqueModal(rep);
      say(`Applied ${res.applied_ids.length} acoustic remediation(s).`);
    }
  }
  function showCritiqueModal(report) {
    const existing = document.getElementById('audioCritiqueModalBackdrop');
    if (existing) existing.remove();
    const score = report.overall_quality_score != null ? report.overall_quality_score : 100;
    const scoreClass = score >= 85 ? 'critique-score-good' : (score >= 60 ? 'critique-score-warn' : 'critique-score-poor');
    const issues = report.issues || [];
    const remediations = report.remediations || [];
    const backdrop = h('div', { class: 'audio-modal-backdrop', id: 'audioCritiqueModalBackdrop' },
      h('div', { class: 'audio-critique-modal' },
        h('div', { class: 'audio-critique-header' },
          h('div', { class: 'audio-critique-title' },
            '🔬 Acoustic Quality Critique',
            h('span', { class: `critique-score-badge ${scoreClass}` }, `${score}/100 Score`)
          ),
          h('button', { class: 'dl-btn', onclick: () => backdrop.remove() }, '✕')
        ),
        h('div', { class: 'audio-critique-body' },
          issues.length === 0
            ? h('div', { style: 'text-align: center; color: #46d6a3; padding: 24px;' }, '✓ Perfect acoustic balance: no spectral mud, masking, or transient collisions detected!')
            : issues.map(iss => {
                const rem = iss.remediation;
                return h('div', { class: `critique-issue-card ${iss.severity}` },
                  h('div', { class: 'critique-issue-info' },
                    h('span', { class: 'critique-issue-title' }, `[${iss.track.toUpperCase()}] ${iss.message}`),
                    rem ? h('span', { class: 'critique-issue-msg' }, `Suggested Fix: ${rem.reason}`) : null
                  ),
                  rem ? h('div', { class: 'critique-issue-action' },
                    h('button', {
                      class: 'critique-fix-btn',
                      onclick: () => applyCritiqueRemediations([rem.id])
                    }, `Fix ${rem.action.toUpperCase()} (${rem.value})`)
                  ) : null
                );
              })
        ),
        h('div', { class: 'audio-critique-footer' },
          h('span', { style: 'font-size: 0.74rem; color: #9aa6d0;' },
            `${issues.length} acoustic issues found · ${remediations.length} auto-fixes available`
          ),
          h('div', { style: 'display: flex; gap: 8px;' },
            remediations.length > 0 ? h('button', {
              class: 'dl-btn accent',
              onclick: () => applyCritiqueRemediations(remediations.map(r => r.id))
            }, `⚡ Auto-Fix All (${remediations.length})`) : null,
            h('button', { class: 'dl-btn', onclick: () => backdrop.remove() }, 'Close')
          )
        )
      )
    );
    document.body.appendChild(backdrop);
  }
  async function makeCueLoop(cueId) {
    if (!S.plan || !cueId) return;
    const r = await guard('Make Loop', () => call('POST', `/plans/${S.plan.id}/cues/${cueId}/loop`));
    if (r) {
      await reload();
      say(`Loop created for ${cueId}: ${r.duration_s ? r.duration_s.toFixed(2) : ''} s.`);
    }
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
  function paintQa() {
    const q = S.qa, box = el.qaBox; if (!box) return;
    box.replaceChildren();
    if (!q || !S.plan) return;
    box.append(h('div', { class: 'dl-sub' }, `QA · ${q.errors} error(s), ${q.warnings} warning(s)`));
    if (!q.findings.length) { box.append(h('div', { class: 'au-empty' }, 'Nothing to fix.')); return; }
    for (const f of q.findings) {
      box.append(h('button', { type: 'button', class: `au-find ${f.severity}`, 'data-cue': f.cue_id, title: f.message, onclick: () => selectCue(f.cue_id, true) },
        h('span', { class: 'au-dot' }), h('b', {}, f.cue_id), h('span', { class: 'au-find-text' }, f.message)));
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
  function paintAll() { paintPlanSelect(); paintHeader(); paintCues(); paintQa(); renderInspector(); renderLanes(); paintMixer(); previewSoon(); }
  function selectCue(id, seek) {
    if (AU && AU.el) { AU.el.pause(); AU.id = null; }
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
  async function pickCandidate(id, candId) { const pid = S.plan.id, p = await guard('Pick', () => call('POST', `/plans/${pid}/cues/${id}/pick`, { candidate_id: candId })); if (p && isCurrent(pid)) { S.plan = p; S.seen = p.version; paintAll(); say(`${id}: picked.`); } }

  // audition: play one candidate (or the chosen sound) on its own, outside the video
  const AU = { el: null, id: null };
  function stopAudition() { if (AU.el) AU.el.pause(); if (AU.id) { AU.id = null; renderInspector(); } }
  function toggleAudition(item) {
    if (!AU.el) { AU.el = document.createElement('audio'); AU.el.addEventListener('ended', () => { AU.id = null; renderInspector(); }); }
    if (AU.id === item.id) { stopAudition(); return; }
    if (P.playing) pause();
    AU.el.src = fileUrl(`takes/${encodeURIComponent(item.path.split(/[\\/]/).pop())}`); AU.el.currentTime = 0; AU.id = item.id;
    AU.el.play().catch((e) => { AU.id = null; say(`Could not play this sound: ${e.message}`, true); renderInspector(); });
    renderInspector();
  }
  function drawMini(cv, peaks) {
    const w = cv.width = 120, hh = cv.height = 26, g = cv.getContext('2d'); g.clearRect(0, 0, w, hh); g.fillStyle = '#a9c7ff';
    const bars = M.peaksToBars(peaks, w, 0, 1);
    for (let x = 0; x < w; x++) { const b = Math.max(1, bars[x] * (hh - 4)); g.fillRect(x, hh / 2 - b / 2, 1, b); }
  }
  function miniWave(item) {
    const cv = h('canvas', { class: 'au-mini-wave', width: 120, height: 26 });
    call('GET', `/plans/${S.plan.id}/takes/${item.id}/peaks?bins=120`).then((r) => drawMini(cv, r.peaks)).catch(() => { /* no waveform: the row still works */ });
    return cv;
  }
  function provenanceBlock(t, cue) {
    const pv = t.provenance || {};
    const canLoop = cue && (cue.track === 'music' || cue.track === 'ambience');
    return h('div', { class: 'au-prov' },
      h('div', {}, h('b', {}, pv.source || 'unknown source'), pv.model ? ` · ${pv.model}` : '', pv.seed != null ? ` · seed ${pv.seed}` : ''),
      h('div', {}, `Licence: ${pv.licence || 'unknown'}`, pv.author ? ` · by ${pv.author}` : ''),
      M.safeUrl(pv.url) ? h('a', { href: M.safeUrl(pv.url), target: '_blank', rel: 'noopener noreferrer', class: 'au-link' }, 'Open the source page') : null,
      h('div', { class: 'dl-hint' }, `${t.duration_s.toFixed(2)} s · peak ${t.peak_db.toFixed(1)} dBFS · hit at ${t.onset_s.toFixed(2)} s`),
      h('div', { class: 'au-cand' },
        h('button', { type: 'button', class: 'dl-btn au-play', id: 'auListenTake', onclick: () => toggleAudition(t), title: 'Listen to this sound on its own' }, AU.id === t.id ? '■' : '▶'),
        canLoop ? h('button', { type: 'button', class: 'dl-btn', title: 'Convert into seamless infinite loop', onclick: () => makeCueLoop(cue.id) }, 'Loop') : null,
        miniWave(t)));
  }
  function candidateRow(c, cueId) {
    return h('div', { class: 'au-cand', 'data-cand': c.id },
      h('button', { type: 'button', class: 'dl-btn au-play', title: 'Listen to this candidate', onclick: () => toggleAudition(c) }, AU.id === c.id ? '■' : '▶'),
      h('div', { class: 'au-cand-info' }, h('b', {}, c.label || c.id), h('span', { class: 'dl-hint' }, `${c.provenance.source} · ${c.provenance.licence} · ${c.duration_s.toFixed(1)} s`), miniWave(c)),
      h('button', { type: 'button', class: 'dl-btn accent', onclick: () => pickCandidate(cueId, c.id) }, 'Pick'));
  }

  function renderInspector() {
    const box = el.inspBody; if (!box) return;
    const sig = JSON.stringify([S.plan && S.plan.id, S.sel, cueById(S.sel), AU.id, S.plan && S.plan.fps]), active = document.activeElement, inside = !!(active && box.contains(active));
    if (inside && sig === el.inspSig) { paintBusy(); return; }   // nothing changed for this cue: keep what is being typed
    const holder = inside ? active.closest('[data-f]') : null, key = holder ? holder.dataset.f : null, typed = inside && 'value' in active ? active.value : null;
    const range = inside && active.selectionStart != null ? [active.selectionStart, active.selectionEnd] : null;
    buildInspector(box); el.inspSig = sig;
    if (key) {
      const n = box.querySelector(`[data-f="${key}"]`);
      if (n) { n.focus({ preventScroll: true }); if (typed != null && 'value' in n && n.value !== typed) n.value = typed; if (range && n.setSelectionRange) { try { n.setSelectionRange(range[0], range[1]); } catch (e) { /* number inputs */ } } }
    }
    paintBusy();
  }
  function buildInspector(box) {
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
      field('What it should sound like', h('textarea', { class: 'dl-in au-intent', 'data-f': 'intent', rows: 2, onchange: (e) => patchCue(c.id, { intent: e.target.value }) }, c.intent || ''),
        'Plain words, like searching a sound library. The Openverse search uses this text.'),
      h('div', { class: 'au-two' },
        field('Kind', h('input', { class: 'dl-in', 'data-f': 'kind', list: 'auKinds', value: c.kind, onchange: (e) => e.target.value.trim() && patchCue(c.id, { kind: e.target.value.trim() }) }),
          'Synth knows: whoosh, impact, click, pop, ding, riser, drop, noise_bed. Music goes to ACE-Step.'),
        field('Lane', h('select', { class: 'dl-in', 'data-f': 'lane', onchange: (e) => patchCue(c.id, { track: e.target.value }) },
          ...M.LANES.filter((l) => l.id !== 'dialogue').map((l) => h('option', { value: l.id, selected: c.track === l.id }, l.label))))),
      h('datalist', { id: 'auKinds' }, ...KINDS.map((k) => h('option', { value: k }))),
      isHit ? h('div', { class: 'au-two' },
        field('Hit time (s)', h('div', { class: 'au-nudge' },
          h('button', { type: 'button', class: 'dl-btn', title: 'One frame earlier (Shift: ten)', onclick: (e) => patchCue(c.id, { hit_t: Math.max(0, M.snapFrame(c.hit_t - (e.shiftKey ? 10 : 1) / fps, fps)) }) }, '◀'),
          numIn(c.hit_t.toFixed(3), '0.001', (e) => { const v = num(e.target.value); if (v != null) patchCue(c.id, { hit_t: v }); }, { 'data-f': 'hit' }),
          h('button', { type: 'button', class: 'dl-btn', title: 'One frame later (Shift: ten)', onclick: (e) => patchCue(c.id, { hit_t: Math.min(p.duration, M.snapFrame(c.hit_t + (e.shiftKey ? 10 : 1) / fps, fps)) }) }, '▶'))),
        field('Lands on', h('select', { class: 'dl-in', 'data-f': 'anchor', onchange: (e) => patchCue(c.id, { anchor: e.target.value }) },
          h('option', { value: 'onset', selected: c.anchor === 'onset' }, 'the start (hits, clicks)'), h('option', { value: 'peak', selected: c.anchor === 'peak' }, 'the swell (whooshes, risers)'))))
        : h('div', { class: 'au-two' },
          field('From (s)', numIn((c.t_in || 0).toFixed(3), '0.001', (e) => { const v = num(e.target.value); if (v != null) patchCue(c.id, { t_in: v }); }, { 'data-f': 'from' })),
          field('To (s)', numIn(c.t_out == null ? '' : c.t_out.toFixed(3), '0.001', (e) => { const v = num(e.target.value); if (v != null) patchCue(c.id, { t_out: v }); }, { placeholder: 'sound length', 'data-f': 'to' }))),
      h('div', { class: 'au-three' },
        field('Gain (dB)', numIn(c.gain_db, '0.5', (e) => { const v = num(e.target.value); if (v != null) patchCue(c.id, { gain_db: v }); }, { 'data-f': 'gain' })),
        field('Fade in (s)', numIn(c.fade_in, '0.05', (e) => { const v = num(e.target.value); if (v != null && v >= 0) patchCue(c.id, { fade_in: v }); }, { min: 0, 'data-f': 'fin' })),
        field('Fade out (s)', numIn(c.fade_out, '0.05', (e) => { const v = num(e.target.value); if (v != null && v >= 0) patchCue(c.id, { fade_out: v }); }, { min: 0, 'data-f': 'fout' }))),
      field('Sourcing for this cue', h('select', { class: 'dl-in', 'data-f': 'mode', onchange: (e) => patchCue(c.id, { mode: e.target.value || null }) },
        h('option', { value: '', selected: !c.mode }, 'Same as the plan'), h('option', { value: 'auto', selected: c.mode === 'auto' }, 'Auto: the engine picks'), h('option', { value: 'ask', selected: c.mode === 'ask' }, 'Ask me: I pick'))),
      h('div', { class: 'dl-sub' }, 'Sound'),
      take ? provenanceBlock(take, c) : h('div', { class: 'au-empty' }, c.status === 'needs_pick' ? 'Candidates are waiting for your pick.' : 'No sound yet.'),
      c.candidates && c.candidates.length ? h('div', { class: 'au-cands' }, ...c.candidates.map((cd) => candidateRow(cd, c.id))) : null,
      h('div', { class: 'au-actions' },
        h('button', { type: 'button', class: 'dl-btn accent', id: 'auSourceCue', onclick: () => sourceSel(c.id), disabled: !!S.busy }, take || c.candidates.length ? 'Source again' : 'Source'),
        h('button', { type: 'button', class: 'dl-btn', id: 'auDeleteCue', onclick: () => deleteCue(c.id), disabled: !!S.busy }, 'Delete cue')));
  }
  // ---------- lanes: ruler, five lanes of cue blocks with waveforms, picture cuts, playhead ----------
  const LANE_H = 52, HEAD_W = 64, RULER_H = 24, MIN_PPS = 0.1, MAX_PPS = 1200;   // 0.1 px/s still fits a three-hour film in a 1200 px lane
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
      h('div', { class: 'au-lanearea' }, bar, el.laneScroll, (el.hscroll = h('div', { class: 'au-hscroll', title: 'Drag to scroll the lanes' }, (el.hthumb = h('div', { class: 'au-hthumb' }))))));
    el.mixerHost = h('div', { class: 'au-mixer' });
    el.bottom.append(el.lanes, el.mixerHost);
    for (const id of ['ruler', ...M.LANES.map((l) => l.id)]) bindCanvas(L.cv[id], id);
    el.laneScroll.addEventListener('wheel', onWheel, { passive: false });
    bindScrollbar();
    if (window.ResizeObserver) new ResizeObserver(() => { if (S.plan) { if (L.fittedFor !== S.plan.id) fit(); else scheduleDraw(); } }).observe(el.laneScroll);
  }
  const cvWidth = () => (L.cv.ruler ? L.cv.ruler.clientWidth : 0);
  function paintScroll() {   // thumb = the part of the video that is in view
    if (!el.hthumb || !S.plan) return;
    const dur = Math.max(S.plan.duration, 0.01), vis = cvWidth() / L.view.pps, a = Math.min(1, L.view.t0 / dur), b = Math.min(1, (L.view.t0 + vis) / dur);
    el.hthumb.style.left = `${HEAD_W + a * (el.hscroll.clientWidth - HEAD_W)}px`; el.hthumb.style.width = `${Math.max(14, (b - a) * (el.hscroll.clientWidth - HEAD_W))}px`;
  }
  function bindScrollbar() {
    let grab = null;
    const at = (e) => { const r = el.hscroll.getBoundingClientRect(); return (e.clientX - r.left - HEAD_W) / Math.max(1, r.width - HEAD_W); };
    el.hscroll.addEventListener('pointerdown', (e) => {
      if (!S.plan) return; el.hscroll.setPointerCapture(e.pointerId);
      const vis = cvWidth() / L.view.pps, f = at(e) * S.plan.duration, onThumb = f >= L.view.t0 && f <= L.view.t0 + vis;
      grab = onThumb ? f - L.view.t0 : vis / 2;   // clicking outside the thumb centres the view there
      L.view = { ...L.view, t0: Math.max(0, f - grab) }; scheduleDraw();
    });
    el.hscroll.addEventListener('pointermove', (e) => { if (grab == null || !S.plan) return; L.view = { ...L.view, t0: Math.max(0, Math.min(S.plan.duration - 0.1, at(e) * S.plan.duration - grab)) }; scheduleDraw(); });
    const end = () => { grab = null; }; el.hscroll.addEventListener('pointerup', end); el.hscroll.addEventListener('pointercancel', end);
  }
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
  function seek(t) { if (!S.plan) return; try { el.video.currentTime = Math.min(Math.max(0, t), S.plan.duration); } catch (e) { /* video not ready */ } movePlayhead(); if (P.preview) syncStems(true); }
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
  function drawDialogue(g, w) {
    const pk = P.preview && P.preview.stems.dialogue.peaks, v = L.view, dur = S.plan.duration;
    if (!pk || !pk.length) { g.fillStyle = '#4b5686'; g.font = '10px sans-serif'; g.textBaseline = 'middle'; g.fillText(S.plan.dialogue_path ? 'Press Preview mix to see the dialogue' : 'This video has no dialogue track', 8, LANE_H / 2); return; }
    g.fillStyle = '#4fb08c'; g.globalAlpha = P.stale ? 0.4 : 0.75;
    for (let x = 0; x < w; x++) { const a = M.xToTime(x, v) / dur, b = M.xToTime(x + 1, v) / dur; if (b < 0 || a > 1) continue; const f = Math.max(...pk.slice(Math.max(0, Math.floor(a * pk.length)), Math.max(1, Math.ceil(b * pk.length))), 0), hh = Math.max(1, f * (LANE_H - 12)); g.fillRect(x, LANE_H / 2 - hh / 2, 1, hh); }
    g.globalAlpha = 1;
  }
  function drawLane(lane) {
    const { g, w } = sizeCanvas(L.cv[lane.id], LANE_H), p = S.plan, v = L.view, fps = p.fps;
    g.fillStyle = COL.bg; g.fillRect(0, 0, w, LANE_H);
    for (const k of M.rulerTicks(v, w, fps)) if (k.major) { g.fillStyle = COL.grid; g.fillRect(Math.round(M.timeToX(k.t, v)), 0, 1, LANE_H); }
    if (lane.id === 'dialogue') drawDialogue(g, w);
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
    drawRuler(); for (const lane of M.LANES) drawLane(lane); paintScroll();
    if (el.zoomLabel) el.zoomLabel.textContent = `${Math.round(L.view.pps)} px/s`;
    movePlayhead();
  }
  function renderLanes() { if (!el.lanes) return; if (S.plan) for (const c of S.plan.cues) ensurePeaks(c); scheduleDraw(); }

  // ---------- playback and mixer ----------
  // The video element is the clock (muted). The preview's three stems (dialogue / music / effects, rendered by the engine with the same code as the
  // export) play through Web Audio gain nodes, so faders, mute and solo are instant. A fader is a trim relative to the gains the stems were rendered
  // with, until "Preview mix" renders them again.
  const P = { ctx: null, nodes: null, master: null, anM: null, preview: null, stale: true, mute: new Set(), solo: new Set(), live: {}, els: {}, playing: false,
    syncTimer: 0, meterTimer: 0, previewTimer: 0, lvl: {}, master_info: null };
  const STEM_LABEL = { dialogue: 'Dialogue', music: 'Music', effects: 'Effects' };
  const trackDb = (id) => { const t = S.plan && S.plan.tracks.find((x) => x.id === id); return t ? t.gain_db : 0; };
  const planDb = (stem) => (stem === 'effects' ? trackDb('sfx') : trackDb(stem));
  const bakedDb = (stem) => { const g = (P.preview && P.preview.gains) || {}; return (stem === 'effects' ? g.sfx : g[stem]) || 0; };
  const faderDb = (stem) => (P.live[stem] != null ? P.live[stem] : planDb(stem));

  function applyGains() {
    if (!P.nodes) return;
    const d = {}; for (const st of M.STEMS) d[st] = faderDb(st) - bakedDb(st);
    const g = M.effectiveGains(d, P.mute, P.solo);
    for (const st of M.STEMS) P.nodes[st].gain.gain.value = g[st];
  }
  function ensureGraph() {
    if (P.ctx) return;
    const Ctx = window.AudioContext || window.webkitAudioContext; if (!Ctx) throw new Error('This browser has no Web Audio');
    P.ctx = new Ctx(); P.master = P.ctx.createGain(); P.anM = P.ctx.createAnalyser(); P.anM.fftSize = 1024;
    P.master.connect(P.anM); P.anM.connect(P.ctx.destination); P.nodes = {};
    for (const st of M.STEMS) {
      const src = P.ctx.createMediaElementSource(P.els[st]), gain = P.ctx.createGain(), an = P.ctx.createAnalyser(); an.fftSize = 1024;
      src.connect(gain); gain.connect(an); an.connect(P.master); P.nodes[st] = { src, gain, an };
    }
    applyGains();
  }
  function loadStemAudio() {
    if (!P.preview) return;
    for (const st of M.STEMS) { const a = P.els[st], url = fileUrl(`${P.preview.dir}/${P.preview.stems[st].file}`); if (a.dataset.url !== url) { a.dataset.url = url; a.src = url; a.load(); } }
    syncStems(true);
  }
  function syncStems(force) {
    const t = el.video.currentTime;
    for (const st of M.STEMS) { const a = P.els[st]; if (!a.src) continue; const act = force ? t : M.driftAction(t, a.currentTime, 0.06); if (act != null) { try { a.currentTime = act; } catch (e) { /* not loaded */ } } }
  }
  async function play() {
    if (!S.plan) return;
    if (AU.el) { AU.el.pause(); AU.id = null; }
    if (!P.preview) { say('Nothing to hear yet: press “Preview mix” to render the sound.', true); return; }
    try {
      ensureGraph(); await P.ctx.resume(); applyGains(); syncStems(true);
      await Promise.all([el.video.play(), ...M.STEMS.map((st) => P.els[st].play())]);
      P.playing = true; clearInterval(P.syncTimer); P.syncTimer = setInterval(() => { if (el.video.ended || el.video.paused) { if (P.playing) pause(); return; } syncStems(false); }, 250);
    } catch (e) { say(`Could not play: ${e.message}`, true); pause(); }
    paintTransport();
  }
  function pause() { el.video.pause(); for (const st of M.STEMS) P.els[st].pause(); P.playing = false; clearInterval(P.syncTimer); paintTransport(); }
  const toggle = () => (P.playing ? pause() : play());
  function step(dt) { if (S.plan) { seek(el.video.currentTime + dt); syncStems(true); } }

  function previewSoon() { clearTimeout(P.previewTimer); P.previewTimer = setTimeout(refreshPreview, 500); }
  async function refreshPreview() {
    if (!S.plan) { P.preview = null; paintMixer(); return; }
    const id = S.plan.id;
    try {
      const r = await call('GET', `/plans/${id}/preview`);
      if (!S.plan || S.plan.id !== id) return;
      if (r.stems) { const changed = !P.preview || P.preview.dir !== r.dir; P.preview = r; if (changed) loadStemAudio(); } else P.preview = null;
      P.stale = !!r.stale;
    } catch (e) { /* engine busy */ }
    applyGains(); paintMixer(); scheduleDraw();
  }
  async function renderPreview() {
    const id = S.plan.id, r = await guard('Rendering the preview', () => call('POST', `/plans/${id}/preview`));
    if (!r || !isCurrent(id)) return;
    P.preview = r; P.stale = false; loadStemAudio(); applyGains(); paintMixer(); scheduleDraw();
    say('Preview ready. Press Play (Space).');
  }
  async function mixMaster() {
    const id = S.plan.id, std = (el.masterStd && el.masterStd.value) || 'youtube';
    const r = await guard('Mastering broadcast mix', () => call('POST', `/plans/${id}/master`, { standard: std, mux: !!(el.muxBox && el.muxBox.checked) }));
    if (r && isCurrent(id)) {
      P.master_info = r.loudness;
      paintMixer();
      const comp = r.compliance || {};
      const status = comp.compliant ? '✓ Compliant' : '⚠ Non-compliant';
      say(`Master (${std.toUpperCase()}): ${r.loudness.integrated_lufs.toFixed(1)} LUFS, ${r.loudness.true_peak_db.toFixed(1)} dBTP · ${status}.`);
    }
  }
  async function sendToTimeline() {
    if (!S.plan) return say('Open a video first.', true);
    if (!window.NLE || typeof window.NLE.placeSounds !== 'function') return say('The Video Studio timeline is not available here.', true);
    const id = S.plan.id;
    const r = await guard('Sending to the timeline', async () => {
      const x = await fetch('/api/audio/library/from_plan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ plan_id: id }) });
      const d = await x.json().catch(() => ({})); if (!x.ok) throw new Error(d.detail || `HTTP ${x.status}`); return d;
    });
    if (!r) return;
    const placed = window.NLE.placeSounds(`plan:${id}`, r.items);
    if (placed.error) return say(placed.error, true);
    if (typeof window.switchResolvePage === 'function') window.switchResolvePage('edit');
  }

  async function exportAll() {
    const mux = !!(el.muxBox && el.muxBox.checked);
    const id = S.plan.id, r = await guard('Exporting', () => call('POST', `/plans/${id}/export`, { target_lufs: -14, mux }));
    if (r && isCurrent(id)) { P.master_info = r.loudness; paintMixer(); const f = r.findings || { errors: 0, warnings: 0 }; say(`Exported ${r.files.length} files to ${r.out_dir} (${f.errors} QA error(s), ${f.warnings} warning(s)).`, f.errors > 0); }
  }
  async function exportDaw() {
    const id = S.plan.id, std = (el.masterStd && el.masterStd.value) || 'youtube';
    const r = await guard('Exporting DAW Package', () => call('POST', `/plans/${id}/export_daw`, { standard: std, make_zip: true }));
    if (r && isCurrent(id)) {
      say(`DAW Package exported to ${r.out_dir} (${r.files.length} files, FCPXML, EDL, Stems).`);
    }
  }

  function commitFader(stem, db) {
    const ids = stem === 'effects' ? ['sfx', 'ambience', 'foley'] : [stem], delta = db - planDb(stem);   // effects: move all three by the same amount
    return edit({ tracks: ids.map((id) => ({ id, gain_db: stem === 'effects' ? Math.round((trackDb(id) + delta) * 100) / 100 : db })) }, 'Fader').finally(() => { delete P.live[stem]; applyGains(); paintMixer(); });
  }
  function buildTransport() {
    const b = (t, f, title, id) => h('button', { type: 'button', class: 'dl-btn au-mini', id, title, onclick: f }, t);
    el.playBtn = b('Play', toggle, 'Play / pause (Space)', 'auPlay');
    el.transport.replaceChildren(b('Start', () => { seek(0); syncStems(true); }, 'Go to the start (Home)', 'auStart'), b('−1f', () => step(-1 / S.plan.fps), 'One frame back (,)'), el.playBtn,
      b('+1f', () => step(1 / S.plan.fps), 'One frame forward (.)'), b('End', () => { seek(S.plan.duration); syncStems(true); }, 'Go to the end (End)'), el.tc);
  }
  function paintTransport() { if (el.playBtn) el.playBtn.textContent = P.playing ? 'Pause' : 'Play'; }

  function buildMixer() {
    for (const st of M.STEMS) { const a = document.createElement('audio'); a.preload = 'auto'; a.crossOrigin = 'anonymous'; P.els[st] = a; }
    el.strips = {}; el.meters = {};
    const strip = (st) => {
      const meter = h('div', { class: 'au-meter', title: 'Level (peak, dBFS)' }, h('i', {})), db = h('div', { class: 'au-db' }, '0.0');
      const fader = h('input', { type: 'range', class: 'au-fader', min: '-30', max: '12', step: '0.5', value: '0', 'aria-label': `${STEM_LABEL[st]} level in dB`,
        oninput: (e) => { P.live[st] = +e.target.value; db.textContent = (+e.target.value).toFixed(1); applyGains(); },
        onchange: (e) => commitFader(st, +e.target.value), ondblclick: () => commitFader(st, 0) });
      const mute = h('button', { type: 'button', class: 'au-ms', title: 'Mute (preview only)', onclick: () => { P.mute.has(st) ? P.mute.delete(st) : P.mute.add(st); applyGains(); paintMixer(); } }, 'M');
      const solo = h('button', { type: 'button', class: 'au-ms solo', title: 'Solo (preview only)', onclick: () => { P.solo.has(st) ? P.solo.delete(st) : P.solo.add(st); applyGains(); paintMixer(); } }, 'S');
      el.strips[st] = { fader, db, mute, solo }; el.meters[st] = meter;
      return h('div', { class: 'au-strip', 'data-stem': st }, h('div', { class: 'au-ms-row' }, mute, solo), h('div', { class: 'au-fader-row' }, fader, meter), db, h('div', { class: 'au-strip-name' }, STEM_LABEL[st]));
    };
    el.masterStd = h('select', { class: 'dl-in', id: 'auMasterStd', style: 'width:auto;padding:2px 6px;font-size:0.68rem;', title: 'Broadcast Loudness Standard' },
      h('option', { value: 'youtube' }, 'YouTube (-14 LUFS)'),
      h('option', { value: 'ebu_r128' }, 'EBU R128 (-23 LUFS)'));
    el.masterMeter = h('div', { class: 'au-meter', title: 'Master level (peak, dBFS)' }, h('i', {}));
    el.masterInfo = h('div', { class: 'au-master-info' });
    el.pvState = h('span', { class: 'au-pvstate' });
    el.muxBox = h('input', { type: 'checkbox', id: 'auMux' });
    el.pvBtn = h('button', { type: 'button', class: 'dl-btn accent', id: 'auPreview', title: 'Render the three stems so you can play the mix', onclick: renderPreview }, 'Preview mix');
    el.mixerHost.append(
      h('div', { class: 'au-mixhead' }, el.pvBtn, el.pvState),
      h('div', { class: 'au-strips' }, ...M.STEMS.map(strip), h('div', { class: 'au-strip master' }, h('div', { class: 'au-fader-row' }, el.masterMeter), el.masterInfo, h('div', { class: 'au-strip-name' }, 'Master'))),
      h('div', { class: 'au-mixfoot' },
        el.masterStd,
        h('button', { type: 'button', class: 'dl-btn', id: 'auMaster', title: 'Master broadcast audio with True-Peak lookahead limiter', onclick: mixMaster }, 'Master'),
        h('button', { type: 'button', class: 'dl-btn', id: 'auExport', title: 'Write stems, master, cue sheet and credits', onclick: exportAll }, 'Export'),
        h('button', { type: 'button', class: 'dl-btn', id: 'auExportDaw', title: 'Export FCPXML, EDL, and stem package for DaVinci Resolve or Final Cut Pro', onclick: exportDaw }, 'DAW Export'),
        h('button', { type: 'button', class: 'dl-btn accent', id: 'auSendTl', title: 'Put every ready cue on the Video Studio timeline (A2 voice, A3 music, A4 effects) and into the Audio Studio library', onclick: sendToTimeline }, 'Send to timeline'),
        h('label', { class: 'dl-check', title: 'Also write master.mp4: the video with this mix' }, el.muxBox, 'with video')));
    el.meterTimer = null; P.meterTimer = setInterval(paintMeters, 70);
  }
  function paintMixer() {
    if (!el.strips) return;
    for (const st of M.STEMS) {
      const e = el.strips[st], db = faderDb(st);
      e.fader.value = db; e.db.textContent = db.toFixed(1);
      e.mute.classList.toggle('on', P.mute.has(st)); e.solo.classList.toggle('on', P.solo.has(st));
    }
    el.pvState.textContent = !P.preview ? 'not rendered' : P.stale ? 'out of date' : 'up to date';
    el.pvState.className = 'au-pvstate ' + (!P.preview ? 'muted' : P.stale ? 'warn' : 'ok');
    el.pvBtn.disabled = !S.plan || !!S.busy;
    const m = P.master_info;
    el.masterInfo.replaceChildren(...(m ? [h('div', {}, `${m.integrated_lufs.toFixed(1)} LUFS`), h('div', {}, `${m.true_peak_db.toFixed(1)} dBTP`), h('div', { class: 'dl-hint' }, `LRA ${m.lra.toFixed(1)}`)]
      : [h('div', { class: 'dl-hint' }, 'Press Master to measure')]));
  }
  const peakDb = (an, buf) => { an.getFloatTimeDomainData(buf); let m = 0; for (let i = 0; i < buf.length; i++) { const v = Math.abs(buf[i]); if (v > m) m = v; } return m > 0 ? 20 * Math.log10(m) : -90; };
  const meterBuf = new Float32Array(1024);
  function paintMeters() {
    if (!P.nodes || !el.meters) return;
    const set = (key, node, an) => {
      const db = P.playing ? peakDb(an, meterBuf) : -90, prev = P.lvl[key] == null ? -90 : P.lvl[key], v = Math.max(db, prev - 3);   // falls back smoothly
      P.lvl[key] = v; const i = node.firstChild; i.style.height = `${Math.max(0, Math.min(100, ((v + 60) / 60) * 100))}%`; node.classList.toggle('hot', v > -1);
    };
    for (const st of M.STEMS) set(st, el.meters[st], P.nodes[st].an);
    set('master', el.masterMeter, P.anM);
  }
  document.addEventListener('keydown', (e) => {
    if (!S.open || !S.plan || e.ctrlKey || e.metaKey || e.altKey) return;
    const tag = (e.target && e.target.tagName) || '';
    if (['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON', 'OPTION'].includes(tag) && !(tag === 'INPUT' && e.target.type === 'checkbox' && false)) return;
    if (e.key === ' ') { e.preventDefault(); toggle(); }
    else if (e.key === 'Home') { e.preventDefault(); seek(0); syncStems(true); }
    else if (e.key === 'End') { e.preventDefault(); seek(S.plan.duration); syncStems(true); }
    else if (e.key === ',') step(-1 / S.plan.fps); else if (e.key === '.') step(1 / S.plan.fps);
  });

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
      h('button', { type: 'button', class: 'dl-btn', id: 'auAutoFoley', title: 'Auto-design layered atmospheric soundscapes and foley cues', onclick: runAutoFoley }, '🪄 Foley'),
      h('button', { type: 'button', class: 'dl-btn', id: 'auSourceAll', title: 'Find a sound for every cue that has none', onclick: sourceAll }, 'Source all'),
      h('button', { type: 'button', class: 'dl-btn', id: 'auQa', title: 'Check clipping, silence and how close each hit lands to its frame', onclick: runQa }, 'QA'),
      h('button', { type: 'button', class: 'dl-btn', id: 'auCritique', title: 'Analyze acoustic quality, masking, and apply remediations', onclick: runCritique }, 'Critique'),
    ];
    el.cueHead = h('div', { class: 'dl-sub' }, 'Cues'); el.qaBox = h('div', { class: 'au-qa', id: 'auQaBox' });
    el.cueList = h('div', { class: 'au-cues' });
    el.status = h('div', { class: 'au-status', role: 'status' });
    el.left.append(h('div', { class: 'cf-panel-head' }, 'Sound plan'),
      h('div', { class: 'au-pane' },
        h('div', { class: 'dl-field' }, h('span', { class: 'dl-lab' }, 'Plan'), el.planSel,
          h('button', { type: 'button', class: 'dl-btn', id: 'auOpen', onclick: pickVideo, title: 'Choose a finished video file' }, 'Open video…')),
        h('div', { class: 'dl-field' }, h('span', { class: 'dl-lab' }, 'Sourcing'), el.mode,
          h('label', { class: 'dl-check', title: 'Also accept CC-BY clips; credits are written to credits.txt' }, el.ccby, 'Allow CC-BY (needs credits)')),
        h('div', { class: 'au-actions' }, ...el.actions), el.cueHead, el.cueList, el.qaBox, el.status));
    el.title = h('b', { class: 'au-title' }, 'No video open'); el.badge = h('span', { class: 'au-badge' });
    el.video = h('video', { class: 'au-video', muted: true, playsinline: true, preload: 'auto' });
    el.video.muted = true;
    el.tc = h('span', { class: 'au-tcbig' }, '00:00:00:00');
    el.transport = h('div', { class: 'au-transport' });
    el.mon.append(h('div', { class: 'au-monhead' }, el.title, el.badge), h('div', { class: 'au-videowrap' }, el.video), el.transport);
    el.video.addEventListener('timeupdate', () => { if (S.plan) { el.tc.textContent = M.fmtTC(el.video.currentTime, S.plan.fps); movePlayhead(); } });
    el.video.addEventListener('seeked', () => movePlayhead());
    el.insp.append(h('div', { class: 'cf-panel-head' }, 'Cue'), (el.inspBody = h('div', { class: 'au-pane' })));
    buildLanes(); buildMixer(); buildTransport();
    el.video.addEventListener('seeked', () => { if (!P.playing) syncStems(true); });
    el.video.addEventListener('ended', () => { if (P.playing) pause(); });
    S.mounted = true; paintAll();
  }
  async function open() {
    mount(); if (!S.mounted) return;
    S.open = true;
    await guard('Load plans', async () => {
      await refreshPlans();
      const want = (S.plan && S.plan.id) || remembered();
      if (S.plan) await reload();
      else if (!S.openingVideo && want && S.plans.some((p) => p.id === want)) await loadPlan(want);
      else paintAll();
    });
    poll();
  }
  function close() { S.open = false; clearTimeout(S.timer); if (AU.el) AU.el.pause(); if (el.video && P.playing) pause(); else if (el.video) el.video.pause(); }

  window.NLEAudio = { mount, open, close, openVideo, get state() { return S; }, selectCue, reload, call, edit, sourceOne, guard, say, get audition() { return AU; }, addCueAtPlayhead, fit, zoom, seek, play, pause, renderPreview, mixMaster, exportAll, exportDaw, runCritique, showCritiqueModal, makeCueLoop, runAutoFoley, get mixer() { return P; }, get view() { return L.view; }, get peaks() { return L.peaks; } };
})();
