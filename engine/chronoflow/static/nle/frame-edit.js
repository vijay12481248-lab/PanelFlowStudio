/* ChronoFlow NLE - Magic Brush (paint on the paused frame) and the prompt bar under the player.
   Flow: capture the paused frame -> inpaint the painted region (or generate a whole new image) -> pick a candidate -> merge into the timeline. */
(function () {
  'use strict';
  let nle = null, mount = null;
  const S = { brushing: false, busy: false, base: null, size: 40, erase: false, strength: 0.85, cands: [], sel: null, mergeMode: 'hold', down: false, last: null, hasMask: false };
  let maskCv = null, viewCv = null, ring = null;      // offscreen mask (frame resolution) and the visible overlay canvas
  const $ = (s, r) => (r || mount).querySelector(s);

  const post = async (path, body) => {
    const res = await fetch(`${nle.cfg.api}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.success === false) throw new Error(data.detail || data.error || `HTTP ${res.status}`);
    return data;
  };
  const say = (m) => nle.status(m);

  function buildBar() {
    mount.innerHTML = `
      <div class="nle-framebar">
        <div class="thumb" id="feThumb" title="Frame being edited"></div>
        <textarea id="fePrompt" placeholder="Describe what this frame should show — or what to fix in the painted area (e.g. “hand with five fingers, same flat illustration style”)…"></textarea>
        <div class="col">
          <button class="nle-btn accent" id="feGo">✨ Generate new image</button>
          <button class="nle-btn" id="feBrushBtn" title="Magic Brush: paint the region to change">🖌 Magic Brush</button>
        </div>
      </div>
      <div class="nle-resrow"><div class="nle-cands" id="feCands"></div><div class="nle-merge" id="feMerge"></div></div>`;
    $('#feGo').onclick = generate;
    $('#feBrushBtn').onclick = toggleBrush;
    $('#fePrompt').addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); generate(); } });
  }

  function buildHud() {
    const hud = document.getElementById('nleBrushHud');
    hud.innerHTML = `<b style="color:#f59e0b">✨ Magic Brush</b>
      <label>Size <input type="range" id="feSize" min="6" max="160" value="${S.size}"></label>
      <button class="nle-btn" id="feErase">Erase</button><button class="nle-btn" id="feClear">Clear</button>
      <label title="How strongly the painted area is repainted">Strength <input type="range" id="feStr" min="0.3" max="1" step="0.05" value="${S.strength}"></label>
      <button class="nle-btn" id="feDone">✕ Close</button>`;
    hud.querySelector('#feSize').oninput = (e) => { S.size = +e.target.value; };
    hud.querySelector('#feStr').oninput = (e) => { S.strength = +e.target.value; };
    hud.querySelector('#feErase').onclick = (e) => { S.erase = !S.erase; e.target.classList.toggle('on', S.erase); };
    hud.querySelector('#feClear').onclick = clearMask;
    hud.querySelector('#feDone').onclick = () => setBrush(false);
  }

  // ---------- brush canvas ----------
  function layoutCanvas() {
    if (!S.base || !viewCv) return;
    const scr = nle.root.screen, W = scr.clientWidth, Hh = scr.clientHeight, ar = S.base.width / S.base.height;
    const w = Math.min(W, Hh * ar), h = w / ar;                       // object-fit: contain
    Object.assign(viewCv.style, { width: `${w}px`, height: `${h}px`, left: `${(W - w) / 2}px`, top: `${(Hh - h) / 2}px` });
  }
  const toFrame = (e) => { const r = viewCv.getBoundingClientRect(); return { x: ((e.clientX - r.left) / r.width) * viewCv.width, y: ((e.clientY - r.top) / r.height) * viewCv.height, k: viewCv.width / r.width }; };

  function paintView() {
    const g = viewCv.getContext('2d'); g.clearRect(0, 0, viewCv.width, viewCv.height);
    g.globalAlpha = 0.55; g.drawImage(maskCv, 0, 0); g.globalAlpha = 1;
  }
  function stroke(a, b, k) {
    const g = maskCv.getContext('2d');
    g.save(); g.globalCompositeOperation = S.erase ? 'destination-out' : 'source-over';
    g.strokeStyle = g.fillStyle = '#ff0000'; g.lineCap = g.lineJoin = 'round'; g.lineWidth = S.size * k;
    g.beginPath(); g.moveTo(a.x, a.y); g.lineTo(b.x, b.y); g.stroke(); g.restore();
    if (!S.erase) S.hasMask = true;
    paintView();
  }
  function clearMask() { if (!maskCv) return; maskCv.getContext('2d').clearRect(0, 0, maskCv.width, maskCv.height); S.hasMask = false; paintView(); }

  function bindCanvas() {
    viewCv.addEventListener('pointerdown', (e) => { viewCv.setPointerCapture(e.pointerId); S.down = true; const p = toFrame(e); S.last = p; stroke(p, p, p.k); });
    viewCv.addEventListener('pointermove', (e) => {
      const r = nle.root.screen.getBoundingClientRect(), d = S.size * (viewCv.getBoundingClientRect().width / viewCv.width);
      Object.assign(ring.style, { display: 'block', width: `${d}px`, height: `${d}px`, left: `${e.clientX - r.left - d / 2}px`, top: `${e.clientY - r.top - d / 2}px` });
      if (!S.down) return; const p = toFrame(e); stroke(S.last, p, p.k); S.last = p;
    });
    viewCv.addEventListener('pointerup', () => { S.down = false; });
    viewCv.addEventListener('pointerleave', () => { ring.style.display = 'none'; });
  }

  // ---------- modes ----------
  function captureBase() {
    nle.pause();
    const shot = nle.captureFrame();
    if (!shot) { say('Nothing on the monitor to edit yet.'); return false; }
    const hit = nle.clipAtPlayhead();
    S.base = { ...shot, t: nle.ui.t, clipId: hit ? hit.clip.id : null, filename: null };
    $('#feThumb').style.backgroundImage = `url("${shot.dataUrl}")`;
    return true;
  }
  async function ensureBaseSaved() {
    if (S.base.filename) return S.base.filename;
    const d = await post('/save_frame', { frame_data: S.base.dataUrl, prefix: 'magic_base' });
    return (S.base.filename = d.filename);
  }

  function setBrush(on) {
    if (on && !captureBase()) return;
    S.brushing = on;
    const scr = nle.root.screen;
    scr.classList.toggle('brushing', on); nle.root.stage.classList.toggle('brushing', on);
    $('#feGo').textContent = on ? '✨ Apply brush edit' : '✨ Generate new image';
    $('#feBrushBtn').classList.toggle('on', on);
    const top = document.getElementById('btnMagicBrush'); if (top) top.classList.toggle('on', on);
    if (on) {
      if (!viewCv) { viewCv = scr.querySelector('canvas.nle-brush'); ring = document.createElement('div'); ring.style.cssText = 'position:absolute;z-index:7;border:1.5px solid #fff;border-radius:50%;pointer-events:none;display:none;box-shadow:0 0 0 1px #000'; scr.appendChild(ring); buildHud(); bindCanvas(); }
      maskCv = document.createElement('canvas'); maskCv.width = viewCv.width = S.base.width; maskCv.height = viewCv.height = S.base.height;
      S.hasMask = false; layoutCanvas(); paintView();
      say('Paint the area to change, describe it below, then press “Apply brush edit” (Ctrl+Enter).');
      $('#fePrompt').focus();
    } else if (ring) ring.style.display = 'none';
  }
  const toggleBrush = () => setBrush(!S.brushing);

  // ---------- generate ----------
  const addCand = (c) => { S.cands.unshift(c); renderCands(); return c; };
  function renderCands() {
    const box = $('#feCands'); box.innerHTML = '';
    S.cands.forEach((c) => {
      const d = document.createElement('div');
      d.className = `nle-cand${c.busy ? ' busy' : ''}${S.sel === c ? ' sel' : ''}`;
      if (c.url) d.style.backgroundImage = `url("${c.url}")`;
      d.title = c.prompt || '';
      d.onclick = () => { if (!c.busy) selectCand(c); };
      box.appendChild(d);
    });
  }
  async function generate() {
    if (S.busy) return;
    const prompt = $('#fePrompt').value.trim();
    if (!prompt) { say('Write a prompt first.'); return; }
    if (!S.brushing && !captureBase()) return;
    if (S.brushing && !S.hasMask) { say('Paint the region to change first.'); return; }
    S.busy = true; $('#feGo').disabled = true;
    const cand = addCand({ busy: true, prompt });
    try {
      let d;
      if (S.brushing) {
        say('Inpainting the painted area with ComfyUI…');
        const file = await ensureBaseSaved();
        const out = document.createElement('canvas'); out.width = maskCv.width; out.height = maskCv.height;
        const g = out.getContext('2d'); g.fillStyle = '#000'; g.fillRect(0, 0, out.width, out.height); g.drawImage(maskCv, 0, 0);
        d = await post('/inpaint_image', { image_filename: file, mask_data: out.toDataURL('image/png'), prompt, denoise: S.strength, steps: 4 });
      } else {
        say('Generating a new image with Qwen Image…');
        const f = Math.min(1, 1024 / Math.max(S.base.width, S.base.height)), r16 = (v) => Math.max(256, Math.round((v * f) / 16) * 16);
        d = await post('/generate_image', { prompt, width: r16(S.base.width), height: r16(S.base.height) });
      }
      cand.busy = false; cand.filename = d.filename; cand.url = nle.q(`${nle.cfg.inp}/${encodeURIComponent(d.filename)}`);
      selectCand(cand); say('Done — review the candidate, then merge it into the timeline.');
    } catch (err) {
      S.cands = S.cands.filter((c) => c !== cand); renderCands(); say(`Generation failed: ${err.message}`);
    } finally { S.busy = false; $('#feGo').disabled = false; }
  }

  // ---------- merge ----------
  function selectCand(c) {
    S.sel = c; renderCands();
    const img = nle.root.ovl; img.setAttribute('data-k', 'preview'); img.src = c.url; img.style.display = 'block';   // preview on the monitor
    const hit = nle.clipAtPlayhead(), rest = hit ? Math.max(0.5, +(hit.end - S.base.t).toFixed(2)) : 2;
    const m = $('#feMerge');
    m.innerHTML = `<b style="color:#e2e8f0">Merge into timeline:</b>
      <select id="feMode"><option value="hold">Replace the picture (instant) — still overlay on V2</option><option value="anim" ${S.mergeMode === 'anim' ? 'selected' : ''}>Re-animate shot from this frame (GPU, minutes)</option></select>
      <label id="feDurL">for <input type="number" id="feDur" min="0.2" step="0.1" value="${rest}" style="width:64px"> s</label>
      <button class="nle-btn primary" id="feMergeGo">⇥ Merge</button><button class="nle-btn" id="feDiscard">Discard</button>`;
    const sync = () => { S.mergeMode = $('#feMode').value; $('#feDurL').style.display = S.mergeMode === 'hold' ? '' : 'none'; };
    $('#feMode').onchange = sync; sync();
    $('#feMergeGo').onclick = merge;
    $('#feDiscard').onclick = () => { S.cands = S.cands.filter((x) => x !== c); S.sel = null; $('#feMerge').innerHTML = ''; renderCands(); nle.refreshAt(); };
  }

  function merge() {
    const c = S.sel; if (!c || !S.base) return;
    if (S.mergeMode === 'hold') {
      const dur = Math.max(0.2, +$('#feDur').value || 1);
      nle.edit(() => { const o = window.NLEModel.addOverlay(nle.tl, { src: c.filename, label: 'Edited frame', start: S.base.t, dur }); nle.ui.sel = { type: 'ovl', id: o.id }; });
      say(`Merged: edited frame is held for ${dur}s on V2 at ${window.NLEModel.toTimecode(S.base.t, nle.tl.fps)}.`);
      $('#feMerge').innerHTML = ''; S.sel = null; setBrush(false);
    } else if (window.NLEFrameEdit.reanimate) window.NLEFrameEdit.reanimate(c, S.base);
  }

  function mountBar(api) {
    nle = api; mount = document.getElementById('nleFrameMount'); buildBar();
    window.addEventListener('resize', layoutCanvas);
    new ResizeObserver(layoutCanvas).observe(nle.root.screen);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && S.brushing) setBrush(false); });
  }

  /** Re-animate the shot from the edited frame (GPU). The original stays on disk; the new render replaces the tail of the clip on the timeline. */
  async function reanimate(c, base) {
    const M = window.NLEModel, tl = nle.tl, hit = M.locate(tl, base.t);
    if (!hit || hit.clip.shot == null) { say('Only original shots can be re-animated. Use “Replace the picture” for this clip.'); return; }
    const clip = hit.clip, rest = Math.max(1, hit.end - base.t), prompt = $('#fePrompt').value.trim();
    $('#feMergeGo').disabled = true;
    try {
      const jobUrl = `${nle.cfg.api}/job/${nle.ui.jobId}`;
      const before = ((await (await fetch(jobUrl)).json()).last_variant || {}).at || 0;
      say(`Re-animating Shot ${clip.shot + 1} from the edited frame — queued on ComfyUI…`);
      await post('/regenerate_chunk', { job_id: nle.ui.jobId, chunk_index: clip.shot + 1, notes: prompt, anchor_image: c.filename, duration: rest, variant: true, audio_offset: hit.srcTime });
      let job;
      for (let i = 0; i < 400; i++) {                       // ~20 min ceiling
        await new Promise((r) => setTimeout(r, 3000));
        job = await (await fetch(jobUrl)).json();
        if (job.status === 'failed') throw new Error(job.error || 'render failed');
        if ((job.last_variant || {}).at > before && job.status === 'completed') break;
        say(`Re-animating Shot ${clip.shot + 1}… ${job.step_progress || 0}%`);
        job = null;
      }
      if (!job) throw new Error('timed out waiting for the render');
      const file = job.last_variant.file, meta = await nle.info(file), cut = base.t;
      nle.edit(() => {
        const L = M.layout(tl).find((l) => l.clip.id === clip.id), edge = M.minDur(tl);
        let idx = tl.clips.indexOf(clip), keep = rest;
        if (cut - L.start >= edge && L.end - cut >= edge) { const r = M.splitAt(tl, cut); M.removeClip(tl, r.right.id); idx += 1; }   // keep the original head
        else if (cut - L.start < edge) { M.removeClip(tl, clip.id); keep = L.end - L.start; }                                       // edit at the very start: replace the clip
        else idx += 1;                                                                                                             // at the very end: add after
        const nc = M.addClip(tl, { src: file, label: `Shot ${clip.shot + 1} · re-animated`, srcDur: meta.duration, out: Math.min(meta.duration, keep) }, idx);
        nle.ui.sel = { type: 'clip', id: nc.id };
      });
      say(`Merged: Shot ${clip.shot + 1} now continues from the edited frame (original file kept).`);
      $('#feMerge').innerHTML = ''; S.sel = null; setBrush(false);
    } catch (err) { say(`Re-animate failed: ${err.message}`); $('#feMergeGo') && ($('#feMergeGo').disabled = false); }
  }

  window.NLEFrameEdit = { mount: mountBar, toggleBrush: () => nle && toggleBrush(), reanimate, state: S };
})();
