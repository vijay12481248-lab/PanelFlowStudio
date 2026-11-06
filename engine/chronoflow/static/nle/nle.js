/* ChronoFlow NLE - program monitor (gapless A/B playback driven by the timeline) + multi-track timeline UI. */
(function () {
  'use strict';
  const M = window.NLEModel;
  const $ = (s, r) => (r || document).querySelector(s);
  const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const ZOOM_MIN = 3, ZOOM_MAX = 1800, HEAD_W = 112;
  const H = { v2: 34, v1: 66, a1: 46 };

  const cfg = { api: '/api/chronoflow', out: '/chronoflow/outputs', inp: '/chronoflow/inputs', token: '' };
  const tl = M.create(24);
  const hist = M.createHistory(tl);
  const ui = { pps: 45, t: 0, playing: false, rate: 1, sel: null, tool: 'select', snap: true, loop: false, jobId: null, sig: '', muted: false };
  const meta = {};            // src -> {fps,width,height,duration,has_audio,peaks,best:{count,url}}
  let root = {}, decks = [], active = 0, seekTok = 0, raf = 0, clockT0 = 0, clockBase = 0, lastBoundaryCheck = 0;
  let audio = null;           // {ctx, master, nodes:[{gain}], anL, anR}
  const listeners = {};
  const emit = (n, d) => (listeners[n] || []).forEach((f) => f(d));

  // ---------- urls ----------
  const q = (u) => (cfg.token ? `${u}${u.includes('?') ? '&' : '?'}token=${encodeURIComponent(cfg.token)}` : u);
  const mediaUrl = (item) => q(`${item.kind === 'image' ? cfg.inp : cfg.out}/${encodeURIComponent(item.src)}?v=${item.version || 0}`);
  const apiUrl = (path, params) => q(`${cfg.api}${path}?${new URLSearchParams(params)}`);
  const clipItem = (c) => ({ src: c.src, kind: 'video', version: c.version });

  // ---------- helpers ----------
  const total = () => M.total(tl);
  const selClip = () => (ui.sel && ui.sel.type === 'clip' ? M.byId(tl, ui.sel.id) : null);
  const selOvl = () => (ui.sel && ui.sel.type === 'ovl' ? tl.overlays.find((o) => o.id === ui.sel.id) : null);
  const fps = () => tl.fps;
  const tToX = (t) => t * ui.pps;
  const xToT = (x) => x / ui.pps;
  function status(msg) { const s = $('#nleStatus'); if (s) s.textContent = msg || ''; }
  function edit(fn) { hist.checkpoint(); fn(); persist(); renderAll(); refreshAt(); }

  // ---------- persistence (per job, browser-local) ----------
  const key = () => `nle:${ui.jobId}`;
  function persist() { try { if (ui.jobId) localStorage.setItem(key(), JSON.stringify(tl)); } catch (e) { /* private mode */ } }
  function restore(sig) {
    try {
      const raw = ui.jobId && localStorage.getItem(key());
      if (!raw) return false;
      const saved = JSON.parse(raw);
      const live = new Set(sig.split('|'));
      if (!saved.clips.length || saved.clips.some((c) => c.shot != null && !live.has(c.src))) return false; // chunks changed under the saved edit
      Object.keys(tl).forEach((k) => delete tl[k]);
      Object.assign(tl, saved);
      return true;
    } catch (e) { return false; }
  }

  // ---------- job loading ----------
  async function info(src) {
    if (meta[src] && meta[src].duration) return meta[src];
    const m = meta[src] || (meta[src] = {});
    try { Object.assign(m, await (await fetch(apiUrl('/media/info', { file: src }))).json()); } catch (e) { m.duration = m.duration || 5.17; }
    return m;
  }

  async function loadJob(job) {
    if (!root.stage) return;
    const files = ((job && job.chunks) || []).filter(Boolean).map((u) => u.split('/').pop().split('?')[0]);
    if (!files.length && job && job.master_video) files.push(job.master_video.split('/').pop().split('?')[0]);
    const sig = files.join('|');
    const jobId = job ? job.id : null;
    if (jobId === ui.jobId && sig === ui.sig) return;
    ui.jobId = jobId; ui.sig = sig;
    ui.sel = null; ui.t = 0; pause(); hist.reset();      // undo must never cross into another job's timeline
    const empty = $('.nle-empty', root.screen);
    if (!files.length) {
      Object.keys(tl).forEach((k) => delete tl[k]); Object.assign(tl, M.create(24));
      empty.style.display = 'flex'; empty.querySelector('.msg').textContent = job ? 'This job has no rendered clips yet' : 'No job selected';
      renderAll(); emit('load', tl); return;
    }
    empty.style.display = 'none';
    const infos = await Promise.all(files.map(info));
    if (restore(sig)) { /* keep the user's edit */ } else {
      Object.keys(tl).forEach((k) => delete tl[k]); Object.assign(tl, M.create(infos[0].fps || 24));
      files.forEach((f, i) => M.addClip(tl, { src: f, label: `Shot ${i + 1}`, srcDur: infos[i].duration, shot: i }));
    }
    tl.fps = infos[0].fps || tl.fps;
    zoomFit(true);
    renderAll();
    await seek(0);
    emit('load', tl);
  }

  /** A clip file was regenerated on disk: bump its version so caches and decks reload it. */
  function refreshSource(src) {
    tl.clips.filter((c) => c.src === src).forEach((c) => { c.version = (c.version || 0) + 1; });
    delete meta[src]; decks.forEach((d) => { if (d.src === src) d.url = null; });
    info(src).then(() => { renderAll(); refreshAt(); });
  }

  // ---------- audio graph ----------
  function ensureAudio() {
    if (audio) { if (audio.ctx.state === 'suspended') audio.ctx.resume(); return audio; }
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const master = ctx.createGain();
    const split = ctx.createChannelSplitter(2);
    const anL = ctx.createAnalyser(), anR = ctx.createAnalyser();
    anL.fftSize = anR.fftSize = 512;
    master.connect(split); master.connect(ctx.destination);
    split.connect(anL, 0); split.connect(anR, 1);
    const nodes = decks.map((d) => { const g = ctx.createGain(); ctx.createMediaElementSource(d.el).connect(g); g.connect(master); return { gain: g }; });
    audio = { ctx, master, nodes, anL, anR, bufL: new Float32Array(512), bufR: new Float32Array(512) };
    audio.master.gain.value = ui.muted ? 0 : 1;
    return audio;
  }
  function applyGain(deckIdx, clip, factor) { if (audio && clip) audio.nodes[deckIdx].gain.gain.value = clip.volume * (factor == null ? 1 : factor); }
  function meterTick() {
    const set = (id, an, buf) => {
      an.getFloatTimeDomainData(buf);
      let p = 0; for (let i = 0; i < buf.length; i++) p = Math.max(p, Math.abs(buf[i]));
      const db = p > 0 ? 20 * Math.log10(p) : -90;
      root.meter[id].style.height = `${clamp((db + 48) / 48, 0, 1) * 100}%`;
    };
    if (audio && ui.playing) { set(0, audio.anL, audio.bufL); set(1, audio.anR, audio.bufR); }
    else { root.meter[0].style.height = root.meter[1].style.height = '0%'; }
  }

  // ---------- decks (A/B gapless video) ----------
  const seekEl = (v, t) => new Promise((res) => {
    if (Math.abs(v.currentTime - t) < 0.001 && v.readyState >= 2) return res();
    const done = () => { v.removeEventListener('seeked', done); clearTimeout(to); res(); };
    const to = setTimeout(done, 1500);
    v.addEventListener('seeked', done); v.currentTime = t;
  });
  async function loadDeck(d, clip, srcTime) {
    const url = mediaUrl(clipItem(clip));
    if (d.url !== url) {
      d.url = url; d.src = clip.src; d.el.src = url; d.el.load();
      await new Promise((res) => { const done = () => { d.el.removeEventListener('loadeddata', done); clearTimeout(to); res(); }; const to = setTimeout(done, 4000); d.el.addEventListener('loadeddata', done); });
    }
    if (d.url === url) d.clipId = clip.id;        // a newer load may have taken this deck while we awaited
    await seekEl(d.el, srcTime);
  }
  function present(i) {
    active = i; styleBlend(null);
    decks.forEach((d, k) => { d.el.classList.toggle('on', k === i); if (k !== i) d.el.pause(); });
  }
  const standby = () => 1 - active;

  /** Cross-fade the two decks while a transition runs. `inIdx` is the incoming deck; dissolve = incoming fades over the outgoing,
      dip to black = outgoing fades out, then incoming fades in. Audio always cross-fades linearly (same as the export's acrossfade). */
  let blendOn = false;
  function styleBlend(blend, inIdx, inClip) {
    blendOn = !!blend;
    if (!blend) { decks.forEach((d) => { d.el.style.opacity = ''; d.el.style.zIndex = ''; }); return; }
    const p = clamp(blend.progress, 0, 1), dip = blend.kind === 'fadeblack', out = decks[1 - inIdx].el, inn = decks[inIdx].el;
    out.style.zIndex = 1; inn.style.zIndex = 2;
    out.style.opacity = dip ? Math.max(0, 1 - 2 * p) : 1;
    inn.style.opacity = dip ? Math.max(0, 2 * p - 1) : p;
    applyGain(1 - inIdx, blend.from, 1 - p); applyGain(inIdx, inClip, p);
  }

  /** Put the picture for timeline time t on screen (paused or while the clock is running). */
  async function show(t) {
    const tok = ++seekTok;
    const hit = M.locate(tl, t);
    updateOverlayImg(t);
    if (!hit) { return; }
    if (hit.blend) {                                   // inside a transition: both clips are on screen
      const inIdx = decks[active].clipId === hit.clip.id ? active : standby();
      await Promise.all([loadDeck(decks[inIdx], hit.clip, hit.srcTime), loadDeck(decks[1 - inIdx], hit.blend.from, hit.blend.fromSrc)]);
      if (tok !== seekTok) return;
      active = inIdx; styleBlend(hit.blend, inIdx, hit.clip);
      return;
    }
    const d = decks[active];
    if (d.clipId === hit.clip.id && d.url === mediaUrl(clipItem(hit.clip))) { await seekEl(d.el, hit.srcTime); }
    else {
      const sb = standby();
      await loadDeck(decks[sb], hit.clip, hit.srcTime);
      if (tok !== seekTok) return;
      present(sb);
    }
    if (blendOn) { styleBlend(null); decks[standby()].el.pause(); }
    applyGain(active, hit.clip);
  }

  function updateOverlayImg(t) {
    const o = tl.overlays.find((x) => t >= x.start && t < x.start + x.dur);
    const img = root.ovl;
    if (!o) { img.style.display = 'none'; img.removeAttribute('data-k'); return; }
    const url = mediaUrl({ src: o.src, kind: 'image' });
    if (img.getAttribute('data-k') !== url) { img.setAttribute('data-k', url); img.src = url; }
    img.style.display = 'block';
  }

  // ---------- transport ----------
  async function seek(t, keepPlaying) {
    ui.t = clamp(t, 0, total());
    if (ui.playing && !keepPlaying) pause();
    await show(ui.t);
    paintTime();
    if (ui.playing) { clockT0 = performance.now(); clockBase = ui.t; }
  }
  const refreshAt = () => { ui.t = clamp(ui.t, 0, total()); show(ui.t).then(paintTime); };
  const step = (n) => seek(M.frame(ui.t, fps()) + n / fps());

  function play(rate) {
    if (!tl.clips.length) return;
    ensureAudio();
    if (ui.t >= total() - 1e-3) ui.t = ui.loopStart != null ? ui.loopStart : 0;
    ui.rate = rate || 1; ui.playing = true;
    clockT0 = performance.now(); clockBase = ui.t;
    const hit = M.locate(tl, ui.t);
    show(ui.t).then(() => {
      if (!ui.playing) return;
      const v = decks[active].el; v.playbackRate = clamp(hit.clip.speed * Math.max(ui.rate, 0.0625), 0.0625, 16); if (ui.rate > 0) v.play().catch(() => {});
      if (hit.blend && ui.rate > 0) { const o = decks[standby()].el; o.playbackRate = clamp(hit.blend.from.speed * ui.rate, 0.0625, 16); o.play().catch(() => {}); }
    });
    cancelAnimationFrame(raf); raf = requestAnimationFrame(tick);
    root.playBtn.textContent = '⏸'; root.playBtn.classList.add('on');
  }
  function pause() {
    ui.playing = false; cancelAnimationFrame(raf);
    decks.forEach((d) => d.el.pause());
    root.playBtn.textContent = '▶'; root.playBtn.classList.remove('on');
    paintTime(); meterTick();
  }
  const togglePlay = () => (ui.playing ? pause() : play(1));
  function shuttle(dir) { // J / K / L like Resolve & Premiere: repeated press speeds up
    if (!ui.playing || Math.sign(ui.rate) !== dir) return play(dir);
    ui.rate = clamp(ui.rate * 2, -8, 8); clockT0 = performance.now(); clockBase = ui.t;
    const v = decks[active].el; const hit = M.locate(tl, ui.t); if (hit && dir > 0) v.playbackRate = clamp(hit.clip.speed * ui.rate, 0.0625, 16);
  }

  function tick(now) {
    if (!ui.playing) return;
    let t = clockBase + ((now - clockT0) / 1000) * ui.rate;
    const end = ui.outPlay != null ? ui.outPlay : total();
    if (t >= end || t < 0) {
      if (ui.loop && t >= end) { seek(ui.loopStart || 0, true).then(() => { if (ui.playing) decks[active].el.play().catch(() => {}); }); raf = requestAnimationFrame(tick); return; }
      ui.t = clamp(t, 0, total()); pause(); return;
    }
    ui.t = t;
    const hit = M.locate(tl, t);
    if (hit) {
      const d = decks[active];
      if (ui.rate < 0) { if (now - lastBoundaryCheck > 90) { lastBoundaryCheck = now; show(t); } }
      else if (d.clipId !== hit.clip.id) { if (!switching) switchTo(hit, t); }
      else {
        if (d.el.paused && ui.rate > 0) d.el.play().catch(() => {});
        if (Math.abs(d.el.currentTime - hit.srcTime) > 0.3) d.el.currentTime = hit.srcTime;     // drift correction
        if (hit.blend) {
          const o = decks[standby()];                  // the outgoing clip keeps playing until the transition ends
          if (o.clipId === hit.blend.from.id) {
            if (o.el.paused && ui.rate > 0) o.el.play().catch(() => {});
            if (Math.abs(o.el.currentTime - hit.blend.fromSrc) > 0.3) o.el.currentTime = hit.blend.fromSrc;
          }
          styleBlend(hit.blend, active, hit.clip);
        } else {
          if (blendOn) { styleBlend(null); decks[standby()].el.pause(); }
          const nxt = tl.clips[hit.index + 1];
          if (nxt && hit.end - t < 2.5 && decks[standby()].clipId !== nxt.id) loadDeck(decks[standby()], nxt, nxt.in);   // preload next clip
        }
      }
      updateOverlayImg(t);
    }
    paintTime(); meterTick();
    raf = requestAnimationFrame(tick);
  }
  let switching = false;
  async function switchTo(hit, t) {
    switching = true;
    try {
      const sb = standby(), d = decks[sb];
      if (d.clipId !== hit.clip.id) await loadDeck(d, hit.clip, hit.srcTime);
      else if (Math.abs(d.el.currentTime - hit.srcTime) > 0.1) d.el.currentTime = hit.srcTime;
      d.el.playbackRate = clamp(hit.clip.speed * Math.max(ui.rate, 0.0625), 0.0625, 16);
      if (hit.blend) { active = sb; styleBlend(hit.blend, sb, hit.clip); }       // keep the outgoing deck playing under the fade
      else { present(sb); applyGain(sb, hit.clip); }
      if (ui.playing) d.el.play().catch(() => {});
    } finally { switching = false; }
  }

  // ---------- painting ----------
  function paintTime() {
    root.tc.firstChild.nodeValue = M.toTimecode(ui.t, fps());
    root.tcTotal.textContent = `/ ${M.toTimecode(total(), fps())}`;
    const x = tToX(ui.t);
    root.playhead.style.left = `${x}px`;
    const hit = M.locate(tl, ui.t);
    root.badge.textContent = hit ? `${hit.clip.label} · f${Math.round((hit.srcTime) * fps())}` : '';
    if (ui.playing) { const sc = root.scroll, vx = x - sc.scrollLeft; if (vx > sc.clientWidth - 30 || vx < 0) sc.scrollLeft = Math.max(0, x - sc.clientWidth * 0.15); }
    emit('time', ui.t);
  }

  function renderRuler() {
    const r = root.ruler; r.innerHTML = '';
    const w = parseFloat(root.content.style.width);
    // pick a tick step that keeps labels >= 70px apart
    const steps = [1 / fps(), 2 / fps(), 5 / fps(), 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120, 300];
    const stepT = steps.find((s) => s * ui.pps >= 70) || 300;
    for (let t = 0; t * ui.pps < w; t += stepT) {
      const tick = el('div', 'nle-tick'); tick.style.left = `${tToX(t)}px`; tick.style.height = '10px';
      tick.innerHTML = `<span>${stepT < 1 ? M.toTimecode(t, fps()).slice(3) : M.toTimecode(t, fps()).slice(0, 8)}</span>`; r.appendChild(tick);
    }
    const minor = stepT / 5;
    if (minor * ui.pps >= 8) for (let t = 0; t * ui.pps < w; t += minor) { const m = el('div', 'nle-tick'); m.style.left = `${tToX(t)}px`; m.style.height = '4px'; r.appendChild(m); }
    tl.markers.forEach((mk) => { const d = el('div', 'nle-marker'); d.style.left = `${tToX(mk.t)}px`; d.title = `${mk.label || 'Marker'} — ${M.toTimecode(mk.t, fps())} (dbl-click to delete)`; d.ondblclick = (e) => { e.stopPropagation(); edit(() => M.removeMarker(tl, mk.id)); }; d.onmousedown = (e) => e.stopPropagation(); d.onclick = () => seek(mk.t); r.appendChild(d); });
  }

  function renderInOut() {
    const b = root.inout;
    if (tl.inPoint == null && tl.outPoint == null) { b.style.display = 'none'; return; }
    const a = tl.inPoint == null ? 0 : tl.inPoint, z = tl.outPoint == null ? total() : tl.outPoint;
    Object.assign(b.style, { display: 'block', left: `${tToX(a)}px`, width: `${tToX(Math.max(0, z - a))}px` });
  }

  function desiredCount(c) {
    const m = meta[c.src] || {}; const aspect = m.width && m.height ? m.width / m.height : 1;
    const tileW = H.v1 * aspect;
    const fullW = (c.srcDur / c.speed) * ui.pps;                        // pixel width of the entire source at this zoom
    const frames = Math.max(1, Math.round(c.srcDur * (m.fps || fps())));
    const ladder = [4, 8, 16, 32, 64, 128, 240];
    const need = Math.ceil(fullW / tileW);
    return Math.min(frames, ladder.find((n) => n >= need) || 240);
  }
  function applyFilm(node, c) {
    const best = (meta[c.src] || {}).best;
    if (!best) { node.style.backgroundImage = ''; return; }
    const fullW = (c.srcDur / c.speed) * ui.pps;
    Object.assign(node.style, { backgroundImage: `url("${best.url}")`, backgroundSize: `${fullW}px 100%`, backgroundPosition: `${-(c.in / c.speed) * ui.pps}px 0` });
  }
  const filmTimers = {};
  function ensureFilm(c) {
    const count = desiredCount(c), m = meta[c.src] || (meta[c.src] = {});
    if (m.best && m.best.count === count && m.best.v === c.version) return;
    clearTimeout(filmTimers[c.src]);
    filmTimers[c.src] = setTimeout(() => {
      const url = apiUrl('/media/filmstrip', { file: c.src, count, height: 72, v: c.version || 0 });
      const img = new Image();
      img.onload = () => { m.best = { count, url, v: c.version }; root.v1.querySelectorAll(`.nle-clip[data-src="${CSS.escape(c.src)}"]`).forEach((n) => { const cl = M.byId(tl, n.dataset.id); if (cl) applyFilm(n.firstChild, cl); }); };
      img.src = url;
    }, 120);
  }
  async function ensurePeaks(c) {
    const m = meta[c.src] || (meta[c.src] = {});
    if (m.peaks !== undefined || m.peaksPending) return;
    m.peaksPending = true;
    try { m.peaks = (await (await fetch(apiUrl('/media/waveform', { file: c.src, bins: 600, v: c.version || 0 }))).json()).peaks || []; } catch (e) { m.peaks = []; }
    m.peaksPending = false; renderAudio();
  }
  function drawWave(canvas, c) {
    const peaks = (meta[c.src] || {}).peaks || [];
    const w = canvas.width = Math.max(2, Math.min(6000, Math.round(canvas.parentNode.clientWidth))), h = canvas.height = H.a1 - 6;
    const g = canvas.getContext('2d'); g.clearRect(0, 0, w, h);
    if (!peaks.length) return;
    g.fillStyle = '#34d399';
    const a = (c.in / c.srcDur) * peaks.length, z = (c.out / c.srcDur) * peaks.length;
    for (let x = 0; x < w; x++) {
      const i = Math.floor(a + (x / w) * (z - a)); const p = Math.min(1, (peaks[i] || 0) * c.volume * 1.4), bh = Math.max(1, p * h);
      g.fillRect(x, (h - bh) / 2, 1, bh);
    }
  }

  function renderAudio() {
    const lane = root.a1; lane.innerHTML = '';
    M.layout(tl).forEach(({ clip, start, end }) => {
      const d = el('div', 'nle-clip audio' + (ui.sel && ui.sel.id === clip.id ? ' sel' : ''));
      Object.assign(d.style, { left: `${tToX(start)}px`, width: `${Math.max(2, tToX(end - start))}px` });
      d.innerHTML = `<canvas></canvas><div class="lbl">${clip.label} · ${Math.round(clip.volume * 100)}%</div>`;
      d.onclick = () => select({ type: 'clip', id: clip.id });
      lane.appendChild(d); drawWave(d.firstChild, clip); ensurePeaks(clip);
    });
  }

  function renderAll() {
    const T = total();
    const w = Math.max(root.scroll.clientWidth, tToX(T) + 160);
    root.content.style.width = `${w}px`;
    renderRuler(); renderInOut();
    // ----- V1
    const lane = root.v1;
    const seen = new Set();
    M.layout(tl).forEach(({ clip, start, end, overlap }, i) => {
      seen.add(clip.id);
      let d = lane.querySelector(`[data-id="${clip.id}"]`);
      if (!d) {
        d = el('div', 'nle-clip', '<div class="nle-film"></div><div class="lbl"></div><div class="spd"></div><div class="nle-trans"></div><div class="nle-handle l" data-edge="in"></div><div class="nle-handle r" data-edge="out"></div>');
        d.dataset.id = clip.id; lane.appendChild(d);
      }
      d.dataset.src = clip.src;
      d.classList.toggle('sel', !!ui.sel && ui.sel.id === clip.id);
      Object.assign(d.style, { left: `${tToX(start)}px`, width: `${Math.max(4, tToX(end - start))}px` });
      d.querySelector('.lbl').textContent = `${clip.label} · ${(end - start).toFixed(2)}s`;
      d.querySelector('.spd').textContent = clip.speed !== 1 ? `${clip.speed}×` : '';
      const tb = d.querySelector('.nle-trans');
      tb.style.display = overlap > 0 ? 'block' : 'none';
      tb.style.width = `${tToX(overlap)}px`;
      tb.className = `nle-trans ${clip.transition === 'fadeblack' ? 'dip' : ''}`;
      tb.title = overlap > 0 ? `${clip.transition === 'fadeblack' ? 'Dip to black' : 'Cross dissolve'} ${overlap.toFixed(2)}s` : '';
      applyFilm(d.firstChild, clip); ensureFilm(clip);
    });
    lane.querySelectorAll('.nle-clip').forEach((n) => { if (!seen.has(n.dataset.id)) n.remove(); });
    // ----- V2 overlays
    root.v2.innerHTML = '';
    tl.overlays.forEach((o) => {
      const d = el('div', 'nle-clip ovl' + (ui.sel && ui.sel.id === o.id ? ' sel' : ''), `<div class="lbl">${o.label}</div><div class="nle-handle l" data-edge="l"></div><div class="nle-handle r" data-edge="r"></div>`);
      Object.assign(d.style, { left: `${tToX(o.start)}px`, width: `${Math.max(6, tToX(o.dur))}px`, backgroundImage: `url("${mediaUrl({ src: o.src, kind: 'image' })}")` });
      d.dataset.id = o.id; root.v2.appendChild(d);
    });
    renderAudio(); paintTime(); renderInspector();
    root.zoom.value = Math.log(ui.pps / ZOOM_MIN) / Math.log(ZOOM_MAX / ZOOM_MIN) * 1000;
    root.undo.disabled = !hist.canUndo; root.redo.disabled = !hist.canRedo;
    root.tl.classList.toggle('blade', ui.tool === 'blade');
    root.toolSel.classList.toggle('on', ui.tool === 'select'); root.toolBlade.classList.toggle('on', ui.tool === 'blade');
    root.snapBtn.classList.toggle('on', ui.snap); root.loopBtn.classList.toggle('on', ui.loop);
    emit('render');
  }

  function renderInspector() {
    const c = selClip(), o = selOvl(), i = root.insp;
    if (!c && !o) { i.innerHTML = `<span>Select a clip · <b>${tl.clips.length}</b> clips · ${M.toTimecode(total(), fps())} · ${fps()} fps</span>`; return; }
    if (o) { i.innerHTML = `<span>Edited-frame overlay <b>${o.label}</b> · start ${M.toTimecode(o.start, fps())} · ${o.dur.toFixed(2)} s</span><button class="nle-btn" id="inspDel">🗑 Remove overlay</button>`; $('#inspDel', i).onclick = () => edit(() => { M.removeOverlay(tl, o.id); ui.sel = null; }); return; }
    const dur = M.clipDur(c);
    i.innerHTML = `<span>Inspector: <b>${c.label}</b> · ${dur.toFixed(2)}s · src ${M.toTimecode(c.in, fps()).slice(3)}–${M.toTimecode(c.out, fps()).slice(3)}</span>
      <label>Speed <input type="number" id="inspSpeed" min="0.25" max="4" step="0.05" value="${c.speed}">×</label>
      <label>Volume <input type="range" id="inspVol" min="0" max="2" step="0.05" value="${c.volume}"> <span id="inspVolL">${Math.round(c.volume * 100)}%</span></label>
      <label title="How this clip joins the previous one. A transition overlaps both clips, so the timeline gets shorter by its length.">Transition in
        <select id="inspTrans" ${tl.clips[0] === c ? 'disabled' : ''}><option value="cut">Cut</option><option value="dissolve">Cross dissolve</option><option value="fadeblack">Dip to black</option></select>
        <input type="number" id="inspTD" min="0.1" max="3" step="0.1" value="${c.transDur || M.DEFAULT_TRANS}" ${c.transition && c.transition !== 'cut' ? '' : 'disabled'}> s</label>
      <span class="grow" style="flex:1"></span>
      <button class="nle-btn" id="inspRegen">🔄 Regenerate shot</button>`;
    $('#inspSpeed', i).onchange = (e) => edit(() => M.setSpeed(tl, c.id, e.target.value));
    $('#inspTrans', i).value = c.transition || 'cut';
    $('#inspTrans', i).onchange = (e) => edit(() => M.setTransition(tl, c.id, e.target.value, c.transDur));
    $('#inspTD', i).onchange = (e) => edit(() => M.setTransition(tl, c.id, c.transition, e.target.value));
    const vol = $('#inspVol', i);
    vol.oninput = () => { c.volume = +vol.value; $('#inspVolL', i).textContent = `${Math.round(c.volume * 100)}%`; applyGain(active, c); };
    vol.onchange = () => { persist(); renderAudio(); };
    vol.onpointerdown = () => hist.checkpoint();
    $('#inspRegen', i).onclick = () => { if (c.shot != null && typeof openShotDirectorModal === 'function') openShotDirectorModal(c.shot + 1); };
  }

  // ---------- selection / zoom ----------
  function select(s) { ui.sel = s; renderAll(); if (s && s.type === 'clip') { const l = M.layout(tl).find((x) => x.clip.id === s.id); if (l && (ui.t < l.start || ui.t > l.end)) seek(l.start); } }
  function setZoom(pps, anchorX) {
    const sc = root.scroll, ax = anchorX == null ? sc.clientWidth / 2 : anchorX;
    const tAnchor = xToT(sc.scrollLeft + ax);
    ui.pps = clamp(pps, ZOOM_MIN, ZOOM_MAX); renderAll();
    sc.scrollLeft = Math.max(0, tToX(tAnchor) - ax);
  }
  function zoomFit(silent) {
    const T = Math.max(total(), 1); ui.pps = clamp((root.scroll.clientWidth - 90) / T, ZOOM_MIN, ZOOM_MAX);
    if (!silent) { renderAll(); root.scroll.scrollLeft = 0; }
  }

  // ---------- pointer interaction ----------
  const timeAtEvent = (e) => xToT(e.clientX - root.content.getBoundingClientRect().left);
  const snapT = (t, exclude) => (ui.snap ? M.snap(t, M.snapPoints(tl, [ui.t]).filter((p) => !exclude || !exclude.includes(p)), 8 / ui.pps) : t);

  function drag(e, onMove, onUp) {
    const move = (ev) => onMove(ev), up = (ev) => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); if (onUp) onUp(ev); };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
  }

  function bindTimeline() {
    // scrub
    const scrub = (e) => { e.preventDefault(); if (ui.playing) pause(); const go = (ev) => { const t = M.frame(clamp(timeAtEvent(ev), 0, total()), fps()); ui.t = t; paintTime(); show(t); }; go(e); drag(e, go); };
    root.ruler.addEventListener('pointerdown', (e) => { if (e.target === root.ruler || e.target.classList.contains('nle-tick') || e.target.parentNode.classList.contains('nle-tick')) scrub(e); });
    root.playhead.addEventListener('pointerdown', scrub);
    root.playhead.style.pointerEvents = 'none';
    root.playhead.querySelector('i').addEventListener('pointerdown', scrub);

    // V1 clips: select / reorder / trim / blade
    root.v1.addEventListener('pointerdown', (e) => {
      const node = e.target.closest('.nle-clip'); if (!node) { select(null); return; }
      const id = node.dataset.id, clip = M.byId(tl, id); if (!clip) return;
      if (ui.tool === 'blade') { const t = M.frame(timeAtEvent(e), fps()); edit(() => { M.splitAt(tl, t); }); return; }
      const edge = e.target.dataset.edge;
      e.preventDefault(); ui.sel = { type: 'clip', id };
      if (edge) return startTrim(e, clip, edge);
      startReorder(e, node, clip);
    });
    root.v1.addEventListener('pointermove', (e) => { if (ui.tool !== 'blade') { root.blade.style.display = 'none'; return; } root.blade.style.display = 'block'; root.blade.style.left = `${tToX(timeAtEvent(e))}px`; });
    root.v1.addEventListener('pointerleave', () => { root.blade.style.display = 'none'; });

    // V2 overlays: move / resize
    root.v2.addEventListener('pointerdown', (e) => {
      const node = e.target.closest('.nle-clip'); if (!node) { select(null); return; }
      const o = tl.overlays.find((x) => x.id === node.dataset.id); if (!o) return;
      e.preventDefault(); ui.sel = { type: 'ovl', id: o.id }; renderAll(); hist.checkpoint();
      const edge = e.target.dataset.edge, t0 = timeAtEvent(e), s0 = o.start, d0 = o.dur;
      drag(e, (ev) => {
        const dt = timeAtEvent(ev) - t0;
        if (edge === 'r') M.updateOverlay(tl, o.id, { dur: snapT(s0 + d0 + dt, [s0 + d0]) - s0 });
        else if (edge === 'l') { const ns = clamp(snapT(s0 + dt, [s0]), 0, s0 + d0 - M.minDur(tl)); M.updateOverlay(tl, o.id, { start: ns, dur: s0 + d0 - ns }); }
        else M.updateOverlay(tl, o.id, { start: snapT(s0 + dt, [s0]) });
        renderAll(); updateOverlayImg(ui.t);
      }, () => { persist(); });
    });

    // wheel: ctrl/alt = zoom at pointer, otherwise horizontal scroll
    root.scroll.addEventListener('wheel', (e) => {
      if (e.ctrlKey || e.altKey || e.metaKey) { e.preventDefault(); setZoom(ui.pps * (e.deltaY < 0 ? 1.18 : 1 / 1.18), e.clientX - root.scroll.getBoundingClientRect().left); }
      else if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) { e.preventDefault(); root.scroll.scrollLeft += e.deltaY; }
    }, { passive: false });
  }

  function startTrim(e, clip, edge) {
    hist.checkpoint();
    const L = M.layout(tl).find((l) => l.clip.id === clip.id), start = L.start, x0 = e.clientX, in0 = clip.in, out0 = clip.out;
    drag(e, (ev) => {
      const dt = (ev.clientX - x0) / ui.pps;
      if (edge === 'out') { const newEnd = snapT(start + (out0 - in0) / clip.speed + dt, [L.end]); M.trimEdge(tl, clip.id, 'out', in0 + (newEnd - start) * clip.speed); }
      else { const newStartEdge = snapT(start + dt, [start]); M.trimEdge(tl, clip.id, 'in', in0 + (newStartEdge - start) * clip.speed); }
      renderAll(); show(edge === 'out' ? Math.max(start, start + M.clipDur(clip) - 1 / fps()) : start);
    }, () => { persist(); refreshAt(); });
  }

  function startReorder(e, node, clip) {
    renderAll();
    const x0 = e.clientX; let moved = false, targetIdx = tl.clips.indexOf(clip);
    node = root.v1.querySelector(`[data-id="${clip.id}"]`);
    drag(e, (ev) => {
      if (!moved && Math.abs(ev.clientX - x0) < 5) return;
      if (!moved) { moved = true; hist.checkpoint(); node.classList.add('dragging'); }
      const t = timeAtEvent(ev), others = M.layout(tl).filter((l) => l.clip.id !== clip.id);
      targetIdx = others.filter((l) => (l.start + l.end) / 2 < t).length;
      const edgeT = targetIdx === 0 ? 0 : others[targetIdx - 1].end;
      root.drop.style.display = 'block'; root.drop.style.left = `${tToX(edgeT) - 1}px`;
      node.style.transform = `translateX(${ev.clientX - x0}px)`;
    }, () => {
      root.drop.style.display = 'none';
      if (moved) { M.moveClip(tl, clip.id, targetIdx); persist(); renderAll(); refreshAt(); }
      else { renderAll(); select({ type: 'clip', id: clip.id }); }
    });
  }

  // ---------- actions ----------
  function splitAtPlayhead() { const t = M.frame(ui.t, fps()); const clip = (M.locate(tl, t) || {}).clip; if (!clip) return; edit(() => M.splitAt(tl, t)); }
  function deleteSelection() {
    const c = selClip(), o = selOvl();
    if (c) { if (tl.clips.length <= 1) return status('At least one clip must remain on V1.'); edit(() => { M.removeClip(tl, c.id); ui.sel = null; }); }
    else if (o) edit(() => { M.removeOverlay(tl, o.id); ui.sel = null; });
  }
  function toggleDissolve() {
    const c = selClip();
    if (!c || tl.clips[0] === c) return status('Select a clip after the first one to add a dissolve at its start.');
    edit(() => M.setTransition(tl, c.id, c.transition === 'dissolve' ? 'cut' : 'dissolve', c.transDur || M.DEFAULT_TRANS));
  }
  const duplicateSel = () => { const c = selClip(); if (c) edit(() => { ui.sel = { type: 'clip', id: M.duplicateClip(tl, c.id).id }; }); };
  const setTool = (t) => { ui.tool = t; renderAll(); };
  function markIn() { edit(() => { tl.inPoint = M.frame(ui.t, fps()); if (tl.outPoint != null && tl.outPoint <= tl.inPoint) tl.outPoint = null; }); syncLoopRange(); }
  function markOut() { edit(() => { tl.outPoint = M.frame(ui.t, fps()); if (tl.inPoint != null && tl.inPoint >= tl.outPoint) tl.inPoint = null; }); syncLoopRange(); }
  function clearRange() { edit(() => { tl.inPoint = tl.outPoint = null; }); syncLoopRange(); }
  function syncLoopRange() { ui.loopStart = tl.inPoint != null ? tl.inPoint : 0; ui.outPlay = tl.outPoint != null ? tl.outPoint : null; }
  const addMarker = () => edit(() => M.addMarker(tl, M.frame(ui.t, fps()), ''));
  function undo() { if (hist.undo()) { persist(); ui.sel = null; renderAll(); refreshAt(); } }
  function redo() { if (hist.redo()) { persist(); ui.sel = null; renderAll(); refreshAt(); } }

  /** Current program frame as a PNG data URL (what the viewer sees right now, overlay included). */
  function captureFrame() {
    const v = decks[active].el, ovl = root.ovl.style.display !== 'none' && root.ovl.complete && root.ovl.naturalWidth ? root.ovl : null;
    const src = ovl || v, w = ovl ? ovl.naturalWidth : v.videoWidth, h = ovl ? ovl.naturalHeight : v.videoHeight;
    if (!w || !h) return null;
    const c = document.createElement('canvas'); c.width = w; c.height = h; c.getContext('2d').drawImage(src, 0, 0, w, h);
    return { dataUrl: c.toDataURL('image/png'), width: w, height: h };
  }

  async function exportCut() {
    if (!tl.clips.length) return;
    status('Baking master cut with FFmpeg…');
    try {
      const res = await fetch(`${cfg.api}/timeline/export`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(M.toEdl(tl)) });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.detail || data.error || res.status);
      const url = q(data.master_video.replace(/^\/outputs\//, `${cfg.out}/`));
      status('Master cut ready — downloading.');
      const a = document.createElement('a'); a.href = url; a.download = data.filename || 'chronoflow_master.mp4'; document.body.appendChild(a); a.click(); a.remove();
    } catch (err) { status(`Export failed: ${err.message}`); }
  }

  // ---------- keyboard ----------
  function onKey(e) {
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select' || e.target.isContentEditable) return;
    if (!root.tl.offsetParent) return;                                           // timeline tab not visible
    const k = e.key, ctrl = e.ctrlKey || e.metaKey;
    const map = {
      ' ': () => togglePlay(), k: () => pause(), j: () => shuttle(-1), l: () => (ctrl ? (ui.loop = !ui.loop, renderAll()) : shuttle(1)),
      ArrowLeft: () => (e.shiftKey ? seek(ui.t - 1) : step(-1)), ArrowRight: () => (e.shiftKey ? seek(ui.t + 1) : step(1)),
      ArrowUp: () => seek(M.neighbour(tl, ui.t, -1)), ArrowDown: () => seek(M.neighbour(tl, ui.t, 1)),
      Home: () => seek(0), End: () => seek(total()), i: markIn, o: markOut, m: addMarker, v: () => setTool('select'), b: () => (ctrl ? splitAtPlayhead() : setTool('blade')),
      s: splitAtPlayhead, n: () => { ui.snap = !ui.snap; renderAll(); }, Delete: deleteSelection, Backspace: deleteSelection,
      d: () => ctrl && duplicateSel(), t: () => ctrl && toggleDissolve(), z: () => (ctrl ? (e.shiftKey ? redo() : undo()) : e.shiftKey && zoomFit()), y: () => ctrl && redo(),
      '=': () => setZoom(ui.pps * 1.4), '+': () => setZoom(ui.pps * 1.4), '-': () => setZoom(ui.pps / 1.4), x: () => e.altKey && clearRange(),
    };
    const fn = map[k.length === 1 ? k.toLowerCase() : k];
    if (!fn) return;
    if (/^[dyt]$/i.test(k) && !ctrl) return;                     // D / Y / T only act with Ctrl
    e.preventDefault(); fn();
  }

  // ---------- mount ----------
  function mount(opts) {
    Object.assign(cfg, opts || {});
    const body = $('#nleMonitorBody'), tlMount = $('#nleTimeline');
    body.className = 'nle-body';
    body.innerHTML = `
      <div class="nle-stage">
        <div class="nle-screen" id="nleScreen">
          <video playsinline preload="auto"></video><video playsinline preload="auto"></video>
          <img class="nle-ovl" alt="">
          <canvas class="nle-brush"></canvas>
          <div class="nle-badge"></div>
          <div class="nle-empty"><div style="font-size:34px;opacity:.4">🎬</div><div class="msg">No job selected</div></div>
        </div>
        <div class="nle-meter" title="Master level (real, from the audio being played)"><div class="ch"><i></i></div><div class="ch"><i></i></div></div>
      </div>
      <div class="nle-hud" id="nleBrushHud"></div>
      <div class="nle-transport">
        <button class="nle-btn" data-a="home" title="Start (Home)">⏮</button>
        <button class="nle-btn" data-a="prev" title="Previous frame (←)">◀|</button>
        <button class="nle-btn" data-a="rev" title="Shuttle back (J)">⏪</button>
        <button class="nle-btn" data-a="play" style="min-width:38px" title="Play / pause (Space)">▶</button>
        <button class="nle-btn" data-a="fwd" title="Shuttle forward (L)">⏩</button>
        <button class="nle-btn" data-a="next" title="Next frame (→)">|▶</button>
        <button class="nle-btn" data-a="end" title="End (End)">⏭</button>
        <button class="nle-btn" data-a="loop" title="Loop (Ctrl+L)">🔁</button>
        <span class="nle-sep"></span>
        <button class="nle-btn" data-a="mute" title="Mute">🔊</button>
        <span class="grow"></span>
        <div class="nle-tc" id="nleTc">00:00:00:00<small id="nleTcTotal">/ 00:00:00:00</small></div>
      </div>
      <div class="nle-status" id="nleStatus"></div>
      <div id="nleFrameMount"></div>`;
    tlMount.className = 'nle-tl';
    tlMount.innerHTML = `
      <div class="nle-tl-bar">
        <button class="nle-btn on" data-t="select" title="Selection (V)">↖ Select</button>
        <button class="nle-btn" data-t="blade" title="Blade (B) · split at playhead: S or Ctrl+B">✂ Blade</button>
        <button class="nle-btn" data-t="split" title="Split at playhead (S)">⎍ Split</button>
        <button class="nle-btn" data-t="dup" title="Duplicate (Ctrl+D)">⧉ Duplicate</button>
        <button class="nle-btn" data-t="dissolve" title="Add / remove a cross dissolve at the start of the selected clip (Ctrl+T)">⧖ Dissolve</button>
        <button class="nle-btn" data-t="del" title="Ripple delete (Del)">🗑 Delete</button>
        <span class="nle-sep"></span>
        <button class="nle-btn" data-t="undo" title="Undo (Ctrl+Z)">↶</button><button class="nle-btn" data-t="redo" title="Redo (Ctrl+Shift+Z)">↷</button>
        <span class="nle-sep"></span>
        <button class="nle-btn on" data-t="snap" title="Magnetic snap (N)">🧲 Snap</button>
        <button class="nle-btn" data-t="in" title="Mark in (I)">I ⟦</button><button class="nle-btn" data-t="out" title="Mark out (O)">⟧ O</button>
        <button class="nle-btn" data-t="clr" title="Clear in/out (Alt+X)">✕ range</button>
        <button class="nle-btn" data-t="mk" title="Add marker (M)">◆ Marker</button>
        <span class="grow"></span>
        <button class="nle-btn" data-t="zout" title="Zoom out (-)">−</button>
        <input class="nle-zoom" type="range" min="0" max="1000" title="Zoom (Ctrl+wheel)">
        <button class="nle-btn" data-t="zin" title="Zoom in (=)">+</button>
        <button class="nle-btn" data-t="fit" title="Fit timeline (Shift+Z)">⇔ Fit</button>
        <button class="nle-btn" data-t="frames" title="Zoom to individual frames">▦ Frames</button>
        <span class="nle-sep"></span>
        <button class="nle-btn primary" data-t="export" title="Bake the timeline to a master video">🚀 Bake Master Cut</button>
      </div>
      <div class="nle-tl-grid">
        <div class="nle-heads">
          <div class="nle-head" style="height:26px"></div>
          <div class="nle-head" style="height:${H.v2}px"><i class="strip" style="background:#a855f7"></i><b>V2</b> Frames</div>
          <div class="nle-head" style="height:${H.v1}px"><i class="strip" style="background:#3b82f6"></i><b>V1</b> Video</div>
          <div class="nle-head" style="height:${H.a1}px"><i class="strip" style="background:#10b981"></i><b>A1</b> Voice<span class="tb"><button data-t="amute" title="Mute audio">M</button></span></div>
        </div>
        <div class="nle-scroll"><div class="nle-content">
          <div class="nle-ruler"></div>
          <div class="nle-lane" style="height:${H.v2}px" data-lane="v2"></div>
          <div class="nle-lane" style="height:${H.v1}px" data-lane="v1"></div>
          <div class="nle-lane" style="height:${H.a1}px" data-lane="a1"></div>
          <div class="nle-inout"></div><div class="nle-drop"></div><div class="nle-blade"></div>
          <div class="nle-play"><i style="position:absolute;top:0;left:-8px;width:16px;height:14px;pointer-events:auto;cursor:ew-resize"></i></div>
        </div></div>
      </div>
      <div class="nle-insp"></div>`;

    const scr = $('#nleScreen');
    root = { stage: body, screen: scr, tl: tlMount, ovl: $('.nle-ovl', scr), badge: $('.nle-badge', scr), insp: $('.nle-insp', tlMount),
      meter: [...tlMount.ownerDocument.querySelectorAll('.nle-meter i')], tc: $('#nleTc'), tcTotal: $('#nleTcTotal'), playBtn: $('[data-a=play]', body),
      scroll: $('.nle-scroll', tlMount), content: $('.nle-content', tlMount), ruler: $('.nle-ruler', tlMount), playhead: $('.nle-play', tlMount),
      v2: $('[data-lane=v2]', tlMount), v1: $('[data-lane=v1]', tlMount), a1: $('[data-lane=a1]', tlMount), inout: $('.nle-inout', tlMount),
      drop: $('.nle-drop', tlMount), blade: $('.nle-blade', tlMount), zoom: $('.nle-zoom', tlMount),
      undo: $('[data-t=undo]', tlMount), redo: $('[data-t=redo]', tlMount), toolSel: $('[data-t=select]', tlMount), toolBlade: $('[data-t=blade]', tlMount),
      snapBtn: $('[data-t=snap]', tlMount), loopBtn: $('[data-a=loop]', body) };
    decks = [...scr.querySelectorAll('video')].map((v) => ({ el: v, clipId: null, url: null, src: null }));
    decks[0].el.classList.add('on');

    const act = { home: () => seek(0), prev: () => step(-1), next: () => step(1), end: () => seek(total()), play: togglePlay, rev: () => shuttle(-1), fwd: () => shuttle(1),
      loop: () => { ui.loop = !ui.loop; renderAll(); },
      mute: (b) => { ui.muted = !ui.muted; if (audio) audio.master.gain.value = ui.muted ? 0 : 1; b.textContent = ui.muted ? '🔇' : '🔊'; $('[data-t=amute]', tlMount).classList.toggle('on', ui.muted); } };
    body.addEventListener('click', (e) => { const b = e.target.closest('[data-a]'); if (b && act[b.dataset.a]) act[b.dataset.a](b); });
    const tools = { select: () => setTool('select'), blade: () => setTool('blade'), split: splitAtPlayhead, dup: duplicateSel, dissolve: toggleDissolve, del: deleteSelection, undo, redo, in: markIn, out: markOut, clr: clearRange, mk: addMarker,
      snap: () => { ui.snap = !ui.snap; renderAll(); }, zin: () => setZoom(ui.pps * 1.4), zout: () => setZoom(ui.pps / 1.4), fit: () => zoomFit(), frames: () => setZoom(fps() * 40),
      export: exportCut, amute: () => act.mute($('[data-a=mute]', body)) };
    tlMount.addEventListener('click', (e) => { const b = e.target.closest('[data-t]'); if (b && tools[b.dataset.t]) tools[b.dataset.t](); });
    root.zoom.oninput = () => setZoom(ZOOM_MIN * Math.pow(ZOOM_MAX / ZOOM_MIN, root.zoom.value / 1000));
    bindTimeline();
    document.addEventListener('keydown', onKey);
    new ResizeObserver(() => { if (tl.clips.length) renderAll(); }).observe(root.scroll);
    if (window.NLEFrameEdit) window.NLEFrameEdit.mount(api);
    renderAll();
  }

  const api = {
    mount, loadJob, refreshSource, seek, play, pause, step, captureFrame, select, edit, status, exportCut,
    on: (n, f) => (listeners[n] = listeners[n] || []).push(f),
    get tl() { return tl; }, get ui() { return ui; }, get root() { return root; }, cfg, mediaUrl, apiUrl, q, info, selectedClip: selClip,
    clipAtPlayhead: () => M.locate(tl, ui.t), poolItems: () => tl.clips.map((c, i) => ({ clip: c, index: i })), renderAll, refreshAt,
  };
  window.NLE = api;
})();
