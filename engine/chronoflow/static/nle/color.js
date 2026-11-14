/* ChronoFlow Color page - Resolve-style grading on the program monitor.
   Each timeline clip carries `clip.grade` = a serial stack of nodes (see grade.js). This file is the UI and the preview:
   gallery of stills + looks (left), the monitor graded live by WebGL (centre), scopes (right), nodes + primaries/curves/LUT tools (bottom).
   The same nodes are baked to a 3D LUT for the export (NLEColor.lutFor), so the render matches the monitor. */
(function () {
  'use strict';
  const G = window.NLEGrade;
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const LS_STILLS = 'nle:stills:v1', LS_LUTS = 'nle:luts:v1';
  const S = { open: false, tab: 'primaries', ni: 0, curve: 'y', hueCurve: 'hueVsHue', bypass: false, wipe: 100, ref: null, compare: false, stills: [], lib: {}, clipboard: null, scopeErr: '' };
  let N = null, wrap = null, el = {};
  const controls = [];                     // {sync(node)} - every control re-reads the current node through these

  const h = (tag, attrs, ...kids) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === 'class') e.className = v; else if (k === 'style') e.style.cssText = v;
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else if (v !== false && v != null) e.setAttribute(k, v === true ? '' : v);
    }
    for (const c of kids.flat()) if (c != null) e.append(c.nodeType ? c : document.createTextNode(String(c)));
    return e;
  };
  const say = (m) => { if (N) N.status(m); };

  // ---------- current clip / grade ----------
  const clip = () => { const hit = N && N.clipAtPlayhead(); return hit ? hit.clip : null; };
  const gradeOf = () => { const c = clip(); return c && c.grade ? c.grade : null; };
  const nodeOf = () => { const g = gradeOf(); if (!g) return null; S.ni = clamp(S.ni, 0, g.nodes.length - 1); return g.nodes[S.ni]; };
  const blankNode = () => G.newNode('');
  let lastKey = '', lastAt = 0, persistT = 0;
  /** Change the current node. Edits with the same key within 1.2 s share one undo step (so a drag is one step). */
  function edit(key, fn) {
    const c = clip(); if (!c) return;
    const now = performance.now();
    if (key !== lastKey || now - lastAt > 1200) N.checkpoint();
    lastKey = key; lastAt = now;
    if (!c.grade) c.grade = G.newGrade();
    S.ni = clamp(S.ni, 0, c.grade.nodes.length - 1);
    fn(c.grade, c.grade.nodes[S.ni]);
    clearTimeout(persistT); persistT = setTimeout(() => N.persist(), 250);
    renderNodes(); renderHeader();
  }
  /** Structural change (add/delete/paste/reset) as one undo step, then re-read everything. */
  function change(fn) {
    const c = clip(); if (!c) return;
    N.checkpoint(); lastKey = ''; fn(c);
    N.persist(); refreshUI();
  }

  // ---------- LUT library (imported .cube files; the table is stored as 16-bit base64) ----------
  const b64 = (u8) => { let s = ''; for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000)); return btoa(s); };
  function saveLib() {
    try {
      const out = {};
      for (const [id, l] of Object.entries(S.lib)) { const u = new Uint16Array(l.table.length); for (let i = 0; i < u.length; i++) u[i] = Math.round(clamp(l.table[i], 0, 1) * 65535); out[id] = { title: l.title, size: l.size, data: b64(new Uint8Array(u.buffer)) }; }
      localStorage.setItem(LS_LUTS, JSON.stringify(out));
    } catch (e) { say('Could not remember the LUT library (browser storage full).'); }
  }
  function loadLib() {
    try {
      const raw = JSON.parse(localStorage.getItem(LS_LUTS) || '{}');
      for (const [id, l] of Object.entries(raw)) {
        const bin = atob(l.data), u8 = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
        const u = new Uint16Array(u8.buffer), t = new Float32Array(u.length); for (let i = 0; i < u.length; i++) t[i] = u[i] / 65535;
        S.lib[id] = { title: l.title, size: l.size, table: t };
      }
    } catch (e) { /* no library yet */ }
  }
  async function importCube(file) {
    try {
      const lut = G.parseCube(await file.text());
      lut.title = lut.title === 'Imported LUT' ? file.name.replace(/\.cube$/i, '') : lut.title;
      let hsh = 5381; for (let i = 0; i < lut.table.length; i += 7) hsh = (hsh * 33 + Math.round(lut.table[i] * 1000)) | 0;
      const id = `L${(hsh >>> 0).toString(16)}`;
      S.lib[id] = lut; saveLib();
      if (clip()) change(() => { clip().grade = clip().grade || G.newGrade(); const g = clip().grade; (g.nodes[S.ni] || g.nodes[0]).lut = { id, strength: 1 }; });
      else renderTab();
      say(`Imported LUT "${lut.title}" (${lut.size}³).`);
    } catch (err) { say(`Could not read that LUT: ${err.message}`); alert(`Could not read that LUT: ${err.message}`); }
  }

  // ---------- baked tables (one per clip, rebuilt only when its grade changes) ----------
  const tables = new Map();
  function tableFor(c) {
    const g = c.grade;
    if (!g || G.isIdentity(g)) return null;
    const lutIds = G.activeNodes(g).map((n) => (n.lut ? n.lut.id : '')).join(',');
    const sig = JSON.stringify(g) + lutIds;
    let t = tables.get(c.id);
    if (!t || t.sig !== sig) { t = { sig, size: G.LUT_SIZE, table: G.bake(g, G.LUT_SIZE, S.lib) }; tables.set(c.id, t); }
    return t;
  }
  const gradedCount = () => (N ? N.tl.clips.filter((c) => c.grade && !G.isIdentity(c.grade)).length : 0);
  /** For the export: the clip's grade as {id, cube}, or null when it changes nothing. Identical grades share an id. */
  const cubeCache = new Map();
  function lutFor(c) {
    const g = c && c.grade;
    if (!g || G.isIdentity(g)) return null;
    const id = G.hashGrade(g, S.lib);
    if (!cubeCache.has(id)) { cubeCache.set(id, G.toCube(G.bake(g, G.LUT_SIZE, S.lib), G.LUT_SIZE, `ChronoFlow ${id}`)); if (cubeCache.size > 40) cubeCache.delete(cubeCache.keys().next().value); }
    return { id, cube: cubeCache.get(id) };
  }

  // ---------- monitor: each video deck gets a WebGL canvas that draws the frame through the clip's LUT ----------
  const VS = '#version 300 es\nout vec2 uv; void main(){ vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2)); uv = p; gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0); }';
  const FS = '#version 300 es\nprecision highp float; precision highp sampler3D; in vec2 uv; out vec4 o; uniform sampler2D vid; uniform sampler3D lut; uniform float n;\n' +
    'void main(){ vec3 c = clamp(texture(vid, uv).rgb, 0.0, 1.0); vec3 p = c * ((n - 1.0) / n) + 0.5 / n; o = vec4(texture(lut, p).rgb, 1.0); }';
  class GradeView {
    constructor(video) {
      this.v = video; this.cv = h('canvas', { class: 'cf-grade' }); video.parentNode.appendChild(this.cv);
      const gl = this.gl = this.cv.getContext('webgl2', { alpha: false, antialias: false });
      this.ok = !!gl; this.key = ''; this.sig = '';
      if (!gl) return;
      const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; };
      const p = this.prog = gl.createProgram(); gl.attachShader(p, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(p, sh(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(p);
      gl.useProgram(p); gl.uniform1i(gl.getUniformLocation(p, 'vid'), 0); gl.uniform1i(gl.getUniformLocation(p, 'lut'), 1); this.uN = gl.getUniformLocation(p, 'n');
      const tex = (unit, target) => { const t = gl.createTexture(); gl.activeTexture(gl.TEXTURE0 + unit); gl.bindTexture(target, t); gl.texParameteri(target, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(target, gl.TEXTURE_MAG_FILTER, gl.LINEAR); [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T, gl.TEXTURE_WRAP_R].forEach((w) => gl.texParameteri(target, w, gl.CLAMP_TO_EDGE)); return t; };
      this.vt = tex(0, gl.TEXTURE_2D); this.lt = tex(1, gl.TEXTURE_3D);
    }
    hide() { this.cv.style.display = 'none'; this.key = ''; }              // a hidden canvas must redraw when it comes back
    show(opacity, z) { this.cv.style.display = 'block'; this.cv.style.opacity = opacity; this.cv.style.zIndex = z === 'auto' ? 1 : z; this.cv.style.clipPath = S.wipe < 100 ? `inset(0 ${100 - S.wipe}% 0 0)` : ''; }
    draw(t, clipId) {
      const gl = this.gl, v = this.v;
      if (v.readyState < 2 || !v.videoWidth) return;
      const key = `${clipId}|${v.currentTime}|${t.sig.length}|${t.sig.slice(-24)}|${v.videoWidth}`;
      if (key === this.key && v.paused) return;                       // nothing changed on a paused frame
      this.key = key;
      const w = Math.min(v.videoWidth, 1920), hh = Math.round((w / v.videoWidth) * v.videoHeight);
      if (this.cv.width !== w || this.cv.height !== hh) { this.cv.width = w; this.cv.height = hh; }
      gl.viewport(0, 0, w, hh); gl.useProgram(this.prog);
      if (this.sig !== t.sig) {                                       // new grade: upload its LUT as a 3D texture
        const N3 = t.size, rgba = new Float32Array(N3 * N3 * N3 * 4);
        for (let i = 0, j = 0; i < t.table.length; i += 3, j += 4) { rgba[j] = t.table[i]; rgba[j + 1] = t.table[i + 1]; rgba[j + 2] = t.table[i + 2]; rgba[j + 3] = 1; }
        gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_3D, this.lt);
        gl.texImage3D(gl.TEXTURE_3D, 0, gl.RGBA16F, N3, N3, N3, 0, gl.RGBA, gl.FLOAT, rgba);
        gl.uniform1f(this.uN, N3); this.sig = t.sig;
      }
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.vt);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
      try { gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, v); } catch (e) { return; }
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }
  }
  const views = [];
  function monitorTick() {
    requestAnimationFrame(monitorTick);
    if (!N || !N.root.screen || !N.root.screen.offsetParent) return;
    N.decks().forEach((d, i) => {
      const view = views[i] || (views[i] = new GradeView(d.el));
      const c = d.clipId && N.tl.clips.find((x) => x.id === d.clipId);
      const t = c && !S.bypass ? tableFor(c) : null;
      if (!t || !view.ok) { view.hide(); return; }
      const cs = getComputedStyle(d.el);
      if (parseFloat(cs.opacity) <= 0.001) { view.hide(); return; }
      view.show(cs.opacity, cs.zIndex); view.draw(t, c.id);
    });
    if (S.open) { const now = performance.now(); if (now - lastScope > 110) { lastScope = now; drawScopes(); } }
  }
  let lastScope = 0;

  // ---------- scopes (computed on a 192x108 copy of the frame, with the grade applied on the CPU) ----------
  const SW = 192, SH = 108, probe = document.createElement('canvas'); probe.width = SW; probe.height = SH;
  const pctx = probe.getContext('2d', { willReadFrequently: true });
  function frameData(applyGrade) {
    const c = clip(); if (!c) return null;
    const d = N.decks().find((x) => x.clipId === c.id && x.el.readyState >= 2);
    if (!d) return null;
    try { pctx.drawImage(d.el, 0, 0, SW, SH); const img = pctx.getImageData(0, 0, SW, SH); S.scopeErr = ''; if (applyGrade && !S.bypass) { const t = tableFor(c); if (t) G.applyToPixels(img.data, t.table, t.size); } return img; }
    catch (e) { S.scopeErr = 'Scopes unavailable (the video is not same-origin).'; return null; }
  }
  function drawScopes() {
    if (!el.scopeWave) return;
    const img = frameData(true);
    if (!img) { ['scopeWave', 'scopeParade', 'scopeVec', 'scopeHist'].forEach((k) => { const cv = el[k]; cv.getContext('2d').clearRect(0, 0, cv.width, cv.height); }); return; }
    const d = img.data, n = SW * SH, L = G.LUMA;
    // waveform + parade accumulators
    const WW = 256, WH = 128, wf = new Uint16Array(WW * WH), pr = new Uint16Array(WW * WH * 3), hist = [new Uint32Array(256), new Uint32Array(256), new Uint32Array(256), new Uint32Array(256)];
    const vec = new Uint16Array(200 * 200);
    for (let i = 0; i < n; i++) {
      const r = d[i * 4], g = d[i * 4 + 1], b = d[i * 4 + 2], x = i % SW, y = (L[0] * r + L[1] * g + L[2] * b);
      const wx = Math.floor((x * WW) / SW), px = Math.floor((x * (WW / 3)) / SW);
      wf[(WH - 1 - Math.round((y / 255) * (WH - 1))) * WW + wx]++;
      pr[(WH - 1 - Math.round((r / 255) * (WH - 1))) * WW + px]++; pr[WW * WH + (WH - 1 - Math.round((g / 255) * (WH - 1))) * WW + px + 86]++; pr[2 * WW * WH + (WH - 1 - Math.round((b / 255) * (WH - 1))) * WW + px + 171]++;
      hist[0][r]++; hist[1][g]++; hist[2][b]++; hist[3][Math.round(y)]++;
      const cb = (b - y) / 255 / 1.8556, cr = (r - y) / 255 / 1.5748;
      const vx = Math.round(100 + cb * 190), vy = Math.round(100 - cr * 190);
      if (vx >= 0 && vx < 200 && vy >= 0 && vy < 200) vec[vy * 200 + vx]++;
    }
    const paint = (cv, w, hgt, fn, grat) => { const ctx = cv.getContext('2d'), im = ctx.createImageData(w, hgt); for (let p = 0; p < w * hgt; p++) { const c = fn(p); im.data[p * 4] = c[0]; im.data[p * 4 + 1] = c[1]; im.data[p * 4 + 2] = c[2]; im.data[p * 4 + 3] = 255; } ctx.putImageData(im, 0, 0); if (grat) grat(ctx); };
    const lines = (ctx) => { ctx.strokeStyle = 'rgba(150,175,255,.22)'; ctx.fillStyle = 'rgba(150,175,255,.6)'; ctx.font = '9px monospace'; [0, 25, 50, 75, 100].forEach((p) => { const y = Math.round((1 - p / 100) * (WH - 1)) + 0.5; ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(WW, y); ctx.stroke(); ctx.fillText(String(p), 2, Math.min(WH - 2, Math.max(9, y - 1))); }); };
    const inten = (c) => Math.min(255, Math.sqrt(c) * 70);
    paint(el.scopeWave, WW, WH, (p) => { const v = inten(wf[p]); return [v * 0.35, v, v * 0.55]; }, lines);
    paint(el.scopeParade, WW, WH, (p) => { const r = inten(pr[p]), g = inten(pr[WW * WH + p]), b = inten(pr[2 * WW * WH + p]); return [r + g * 0.0, g, b]; }, (ctx) => { lines(ctx); ctx.strokeStyle = 'rgba(255,255,255,.15)'; [86, 171].forEach((x) => { ctx.beginPath(); ctx.moveTo(x + 0.5, 0); ctx.lineTo(x + 0.5, WH); ctx.stroke(); }); });
    paint(el.scopeVec, 200, 200, (p) => { const v = inten(vec[p] * 3); return [v * 0.7, v, v * 0.9]; }, (ctx) => {
      ctx.strokeStyle = 'rgba(150,175,255,.28)'; ctx.beginPath(); ctx.arc(100, 100, 95, 0, Math.PI * 2); ctx.stroke(); ctx.beginPath(); ctx.arc(100, 100, 47, 0, Math.PI * 2); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(100, 5); ctx.lineTo(100, 195); ctx.moveTo(5, 100); ctx.lineTo(195, 100); ctx.stroke();
      [['R', 1, 0, 0], ['Y', 1, 1, 0], ['G', 0, 1, 0], ['C', 0, 1, 1], ['B', 0, 0, 1], ['M', 1, 0, 1]].forEach(([nm, r, g, b]) => {
        const y = L[0] * r + L[1] * g + L[2] * b, cb = (b - y) / 1.8556, cr = (r - y) / 1.5748, x = 100 + cb * 190, yy = 100 - cr * 190;
        ctx.strokeStyle = `rgb(${r * 255},${g * 255},${b * 255})`; ctx.strokeRect(x - 5, yy - 5, 10, 10); ctx.fillStyle = '#fff'; ctx.font = '9px monospace'; ctx.fillText(nm, x + 7, yy + 3);
      });
      const sy = L[0] * 1 + L[1] * 0.75 + L[2] * 0.55, scb = (0.55 - sy) / 1.8556, scr = (1 - sy) / 1.5748, ang = Math.atan2(scr, scb);   // skin-tone line
      ctx.strokeStyle = 'rgba(255,200,140,.7)'; ctx.beginPath(); ctx.moveTo(100, 100); ctx.lineTo(100 + Math.cos(ang) * 95, 100 - Math.sin(ang) * 95); ctx.stroke();
    });
    const hc = el.scopeHist, hx = hc.getContext('2d'); hx.fillStyle = '#060918'; hx.fillRect(0, 0, hc.width, hc.height);
    let mx = 1; for (let k = 0; k < 4; k++) for (let i = 2; i < 254; i++) mx = Math.max(mx, hist[k][i]);
    hx.globalCompositeOperation = 'lighter';
    [['#ff3b4a', 0], ['#2bd96b', 1], ['#3b7bff', 2]].forEach(([col, k]) => { hx.fillStyle = col; hx.globalAlpha = 0.55; for (let i = 0; i < 256; i++) { const bh = Math.min(1, hist[k][i] / mx) * (hc.height - 2); hx.fillRect(i, hc.height - bh, 1, bh); } });
    hx.globalAlpha = 1; hx.fillStyle = 'rgba(255,255,255,.55)'; for (let i = 0; i < 256; i++) { const bh = Math.min(1, hist[3][i] / mx) * (hc.height - 2); hx.fillRect(i, hc.height - bh, 1, 1.5); }
    hx.globalCompositeOperation = 'source-over';
  }

  // ---------- Auto balance and Shot match (statistics of the frame -> an ASC CDL node) ----------
  function frameStats(img) {
    const d = img.data, n = SW * SH, L = G.LUMA, ys = new Float32Array(n);
    const sum = [0, 0, 0], sq = [0, 0, 0], midSum = [0, 0, 0]; let midN = 0, midY = 0;
    for (let i = 0; i < n; i++) {
      const r = d[i * 4] / 255, g = d[i * 4 + 1] / 255, b = d[i * 4 + 2] / 255, y = L[0] * r + L[1] * g + L[2] * b; ys[i] = y;
      sum[0] += r; sum[1] += g; sum[2] += b; sq[0] += r * r; sq[1] += g * g; sq[2] += b * b;
      if (y > 0.12 && y < 0.88) { midSum[0] += r; midSum[1] += g; midSum[2] += b; midN++; midY += y; }
    }
    const sorted = Array.from(ys).sort((a, b) => a - b);
    const mean = sum.map((s) => s / n), std = sq.map((s, i) => Math.sqrt(Math.max(1e-8, s / n - mean[i] * mean[i])));
    return { mean, std, p1: sorted[Math.floor(n * 0.01)], p99: sorted[Math.floor(n * 0.99)], mid: midN > 200 ? midSum.map((s) => s / midN) : mean, midY: midN > 200 ? midY / midN : (mean[0] + mean[1] + mean[2]) / 3 };
  }
  function autoBalance() {
    const img = frameData(false); if (!img) return say('Nothing to analyse: put the playhead on a clip.');
    const s = frameStats(img);
    const gains = s.mid.map((m) => clamp(1 + (s.midY / Math.max(0.02, m) - 1) * 0.8, 0.75, 1.33));          // gray-world on the mid tones, 80 % of the way
    const lo = Math.min(s.p1, 0.12), hi = Math.max(s.p99, 0.85), ls = clamp(1 / Math.max(0.2, hi - lo), 0.85, 1.35);
    const r4 = (x) => Math.round(x * 1e4) / 1e4;
    change((c) => {
      c.grade = c.grade || G.newGrade();
      let n0 = c.grade.nodes.find((n) => n.label === 'Auto Balance');
      if (!n0) { n0 = G.newNode('Auto Balance'); c.grade.nodes.unshift(n0); S.ni = 0; }
      n0.cdl = { slope: gains.map((g) => r4(g * ls)), offset: [r4(-lo * ls), r4(-lo * ls), r4(-lo * ls)], power: [1, 1, 1] };
    });
    say(`Auto balance: gains ${gains.map((g) => g.toFixed(2)).join(' / ')}, black ${lo.toFixed(2)}, white ${hi.toFixed(2)}.`);
  }
  function matchToStill(strength) {
    const ref = S.stills.find((x) => x.id === S.ref); if (!ref) return say('Pick a reference still in the gallery first.');
    const c = clip(); if (!c) return say('Nothing to match: put the playhead on a clip.');
    // statistics of what the clip looks like now, without any earlier Shot Match node
    const keep = c.grade; const probeGrade = keep ? { ...keep, nodes: keep.nodes.filter((n) => n.label !== 'Shot Match') } : null;
    const was = c.grade; c.grade = probeGrade && !G.isIdentity(probeGrade) ? probeGrade : null;
    const img = frameData(true); c.grade = was;
    if (!img) return say('Could not read the frame.');
    const s = frameStats(img), r = ref.stats, k = strength == null ? 0.85 : strength, r4 = (x) => Math.round(x * 1e4) / 1e4;
    const slope = s.std.map((sd, i) => clamp(Math.pow(r.std[i] / sd, k), 0.6, 1.6)), offset = slope.map((sl, i) => r4(r.mean[i] * k + s.mean[i] * (1 - k) - sl * s.mean[i]));
    change((cl) => {
      cl.grade = cl.grade || G.newGrade();
      let nm = cl.grade.nodes.find((n) => n.label === 'Shot Match');
      if (!nm) { nm = G.newNode('Shot Match'); cl.grade.nodes.push(nm); S.ni = cl.grade.nodes.length - 1; }
      nm.cdl = { slope: slope.map(r4), offset, power: [1, 1, 1] };
    });
    say(`Shot match to "${ref.name}": slope ${slope.map((x) => x.toFixed(2)).join(' / ')}.`);
  }

  // ---------- stills (graded thumbnails + the grade that made them) ----------
  function loadStills() { try { S.stills = JSON.parse(localStorage.getItem(LS_STILLS) || '[]'); } catch (e) { S.stills = []; } }
  function saveStills() { try { localStorage.setItem(LS_STILLS, JSON.stringify(S.stills)); } catch (e) { say('Could not remember the stills (browser storage full).'); } }
  function grabStill() {
    const c = clip(); const img = frameData(true); if (!c || !img) return say('Nothing to grab: put the playhead on a clip.');
    const cv = h('canvas', { width: SW, height: SH }); cv.getContext('2d').putImageData(img, 0, 0);
    const id = `s${Date.now().toString(36)}`;
    S.stills.unshift({ id, name: `${c.label || c.src}`.slice(0, 40), thumb: cv.toDataURL('image/jpeg', 0.82), stats: (() => { const s = frameStats(img); return { mean: s.mean, std: s.std }; })(), grade: c.grade ? JSON.parse(JSON.stringify(c.grade)) : null });
    S.stills = S.stills.slice(0, 24); S.ref = id; saveStills(); renderGallery(); say(`Grabbed a still from "${c.label || c.src}".`);
  }
  function applyStill(st) {
    if (!clip() || !st.grade) return say(st.grade ? 'Nothing to apply to.' : 'That still had no grade.');
    change((c) => { const g = JSON.parse(JSON.stringify(st.grade)); g.nodes.forEach((n) => { n.id = `n${Math.random().toString(36).slice(2, 8)}`; }); c.grade = g; S.ni = 0; });
    say(`Applied the grade of "${st.name}".`);
  }

  // ---------- looks (each adds one node, so it can be switched off or tuned) ----------
  const LOOKS = {
    'Teal & Orange': (n) => { n.lift = { x: -0.8, y: -0.15, m: 0 }; n.gain = { x: 0.6, y: 0.35, m: 0.02 }; n.contrast = 1.12; n.saturation = 1.12; },
    'Warm film': (n) => { n.temp = 18; n.tint = 4; n.contrast = 1.08; n.saturation = 1.05; n.lift = { x: 0.2, y: 0.15, m: 0.02 }; n.curves.y = [[0, 0.03], [0.5, 0.52], [1, 0.97]]; },
    'Cold night': (n) => { n.temp = -22; n.gamma = { x: -0.5, y: -0.4, m: -0.08 }; n.contrast = 1.1; n.saturation = 0.9; n.highlights = -10; },
    'Bleach bypass': (n) => { n.saturation = 0.55; n.contrast = 1.3; n.pivot = 0.45; n.highlights = -6; },
    'Faded matte': (n) => { n.lift = { x: 0, y: 0, m: 0.12 }; n.contrast = 0.92; n.saturation = 0.9; n.curves.y = [[0, 0.06], [1, 0.94]]; },
    'Vivid pop': (n) => { n.boost = 40; n.saturation = 1.2; n.contrast = 1.1; },
    'Noir': (n) => { n.saturation = 0; n.contrast = 1.32; n.curves.y = [[0, 0], [0.3, 0.2], [0.7, 0.8], [1, 1]]; },
  };
  function addLook(name) {
    change((c) => { c.grade = c.grade || G.newGrade(); const n = G.newNode(name); LOOKS[name](n); c.grade.nodes.push(n); S.ni = c.grade.nodes.length - 1; });
  }

  // ---------- controls ----------
  function slider(label, o) {
    const rng = h('input', { type: 'range', min: o.min, max: o.max, step: o.step }), num = h('input', { type: 'number', min: o.min, max: o.max, step: o.step, class: 'cf-num' });
    const put = (v) => { rng.value = v; num.value = (+v).toFixed(o.fmt == null ? 2 : o.fmt); };
    const apply = (raw) => { const v = clamp(+raw, o.min, o.max); if (Number.isNaN(v)) return; edit(`s:${label}`, (g, n) => o.set(n, v)); put(v); };
    rng.addEventListener('input', () => apply(rng.value)); num.addEventListener('change', () => apply(num.value));
    const lab = h('label', { title: 'Double-click to reset', ondblclick: () => apply(o.def) }, label);
    controls.push({ sync: (n) => put(n ? o.get(n) : o.def) });
    return h('div', { class: 'cf-row' }, lab, rng, num);
  }
  let ringImg = null;
  function ring() {
    if (ringImg) return ringImg;
    const cv = h('canvas', { width: 120, height: 120 }), ctx = cv.getContext('2d'), im = ctx.createImageData(120, 120);
    for (let y = 0; y < 120; y++) for (let x = 0; x < 120; x++) {
      const dx = x - 60 + 0.5, dy = 60 - y - 0.5, r = Math.hypot(dx, dy) / 54;
      if (r > 1) continue;
      const hue = (Math.atan2(dy, dx) / (2 * Math.PI) + 1) % 1, c = G.hsv2rgb(hue, Math.min(1, r) * 0.9, 0.42 + 0.1 * (1 - r)), i = (y * 120 + x) * 4;
      im.data[i] = c[0] * 255; im.data[i + 1] = c[1] * 255; im.data[i + 2] = c[2] * 255; im.data[i + 3] = 255;
    }
    ctx.putImageData(im, 0, 0); ctx.strokeStyle = 'rgba(150,175,255,.4)'; ctx.beginPath(); ctx.arc(60, 60, 54, 0, 7); ctx.stroke(); ctx.beginPath(); ctx.moveTo(60, 8); ctx.lineTo(60, 112); ctx.moveTo(8, 60); ctx.lineTo(112, 60); ctx.strokeStyle = 'rgba(255,255,255,.12)'; ctx.stroke();
    return (ringImg = cv);
  }
  function wheelCtl(title, key) {
    const cv = h('canvas', { width: 120, height: 120, class: 'cf-wheel', title: 'Drag the puck to push a colour into this tonal range. Double-click to reset.' }), ctx = cv.getContext('2d');
    const master = h('input', { type: 'range', min: -1, max: 1, step: 0.005, class: 'cf-master', title: `${title} master (brightness of this range)` });
    const ro = h('div', { class: 'cf-ro' });
    const draw = (n) => {
      const w = n ? n[key] : { x: 0, y: 0, m: 0 }; ctx.clearRect(0, 0, 120, 120); ctx.drawImage(ring(), 0, 0);
      const px = 60 + w.x * 54, py = 60 - w.y * 54; ctx.fillStyle = '#fff'; ctx.strokeStyle = '#000'; ctx.beginPath(); ctx.arc(px, py, 5, 0, 7); ctx.fill(); ctx.stroke();
      const rgb = G.wheelRgb(w); ro.textContent = `R ${(rgb[0] + w.m).toFixed(2)}  G ${(rgb[1] + w.m).toFixed(2)}  B ${(rgb[2] + w.m).toFixed(2)}`; master.value = w.m;
    };
    const move = (e) => {
      const r = cv.getBoundingClientRect(); let x = ((e.clientX - r.left) / r.width * 120 - 60) / 54, y = (60 - (e.clientY - r.top) / r.height * 120) / 54;
      const len = Math.hypot(x, y); if (len > 1) { x /= len; y /= len; }
      edit(`w:${key}`, (g, n) => { n[key].x = Math.round(x * 1000) / 1000; n[key].y = Math.round(y * 1000) / 1000; draw(n); });
    };
    cv.addEventListener('pointerdown', (e) => { cv.setPointerCapture(e.pointerId); move(e); cv.onpointermove = move; });
    cv.addEventListener('pointerup', () => { cv.onpointermove = null; });
    cv.addEventListener('dblclick', () => edit(`w:${key}:r`, (g, n) => { n[key] = { x: 0, y: 0, m: 0 }; draw(n); }));
    master.addEventListener('input', () => edit(`m:${key}`, (g, n) => { n[key].m = +master.value; draw(n); }));
    master.addEventListener('dblclick', () => edit(`m:${key}:r`, (g, n) => { n[key].m = 0; draw(n); }));
    controls.push({ sync: draw });
    return h('div', { class: 'cf-wheelbox' }, h('div', { class: 'cf-wtitle' }, title), cv, master, ro);
  }

  // curve editor: click empty space to add a point, drag to move, double-click or right-click a point to remove it
  function curveEditor(o) {
    const W = o.w || 300, H = o.h || 190, cv = h('canvas', { width: W, height: H, class: 'cf-curve' }), ctx = cv.getContext('2d');
    let drag = -1;
    const pts = () => { const n = nodeOf(); return n ? o.get(n).map((p) => p.slice()) : []; };
    const toPx = (p) => [p[0] * W, H - ((p[1] - o.ymin) / (o.ymax - o.ymin)) * H];
    const fromEv = (e) => { const r = cv.getBoundingClientRect(); return [clamp((e.clientX - r.left) / r.width, 0, 1), clamp(o.ymin + (1 - (e.clientY - r.top) / r.height) * (o.ymax - o.ymin), o.ymin, o.ymax)]; };
    const nearest = (e) => { const r = cv.getBoundingClientRect(), mx = (e.clientX - r.left) * (W / r.width), my = (e.clientY - r.top) * (H / r.height); let best = -1, bd = 12; pts().forEach((p, i) => { const q = toPx(p), d = Math.hypot(q[0] - mx, q[1] - my); if (d < bd) { bd = d; best = i; } }); return best; };
    const draw = () => {
      ctx.fillStyle = '#080d22'; ctx.fillRect(0, 0, W, H);
      if (o.hueBar) { const g = ctx.createLinearGradient(0, 0, W, 0); for (let i = 0; i <= 12; i++) { const c = G.hsv2rgb(i / 12, 0.8, 0.8); g.addColorStop(i / 12, `rgb(${c[0] * 255 | 0},${c[1] * 255 | 0},${c[2] * 255 | 0})`); } ctx.fillStyle = g; ctx.globalAlpha = 0.28; ctx.fillRect(0, 0, W, H); ctx.globalAlpha = 1; }
      ctx.strokeStyle = 'rgba(150,175,255,.14)'; for (let i = 1; i < 4; i++) { ctx.beginPath(); ctx.moveTo((i * W) / 4, 0); ctx.lineTo((i * W) / 4, H); ctx.moveTo(0, (i * H) / 4); ctx.lineTo(W, (i * H) / 4); ctx.stroke(); }
      if (o.tone) { ctx.strokeStyle = 'rgba(255,255,255,.22)'; ctx.beginPath(); ctx.moveTo(0, H); ctx.lineTo(W, 0); ctx.stroke(); } else { const z = toPx([0, 0])[1]; ctx.strokeStyle = 'rgba(255,255,255,.3)'; ctx.beginPath(); ctx.moveTo(0, z); ctx.lineTo(W, z); ctx.stroke(); }
      const p = pts(), f = G.curveFn(p, o.cyclic, o.tone ? undefined : () => 0);
      ctx.strokeStyle = o.color || '#e6ebff'; ctx.lineWidth = 2; ctx.beginPath();
      for (let x = 0; x <= W; x += 2) { const y = clamp(f(x / W), o.ymin, o.ymax), q = toPx([x / W, y]); x ? ctx.lineTo(q[0], q[1]) : ctx.moveTo(q[0], q[1]); } ctx.stroke(); ctx.lineWidth = 1;
      p.forEach((pt) => { const q = toPx(pt); ctx.fillStyle = '#fff'; ctx.strokeStyle = '#000'; ctx.beginPath(); ctx.arc(q[0], q[1], 4.5, 0, 7); ctx.fill(); ctx.stroke(); });
    };
    const put = (arr) => edit(`c:${o.id}`, (g, n) => { o.set(n, arr.map((q) => [Math.round(q[0] * 1000) / 1000, Math.round(q[1] * 1000) / 1000])); draw(); });
    cv.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      cv.setPointerCapture(e.pointerId); let p = pts(); let i = nearest(e);
      if (i < 0) { if (!p.length && o.seed) p = o.seed.map((x) => [x, 0]); const q = fromEv(e); p.push(q); p.sort((a, b) => a[0] - b[0]); i = p.indexOf(p.find((x) => x[0] === q[0] && x[1] === q[1])); put(p); }
      drag = i;
    });
    cv.addEventListener('pointermove', (e) => {
      if (drag < 0) return; const p = pts(); if (!p[drag]) return; const q = fromEv(e), last = p.length - 1;
      const fixedX = o.tone && (drag === 0 || drag === last);
      p[drag] = [fixedX ? p[drag][0] : clamp(q[0], drag ? p[drag - 1][0] + 0.01 : 0, drag < last ? p[drag + 1][0] - 0.01 : 1), q[1]]; put(p);
    });
    cv.addEventListener('pointerup', () => { drag = -1; });
    const remove = (e) => { e.preventDefault(); const i = nearest(e), p = pts(); if (i < 0) return; if (o.tone && (p.length <= 2 || i === 0 || i === p.length - 1)) return; p.splice(i, 1); put(p); };
    cv.addEventListener('dblclick', remove); cv.addEventListener('contextmenu', remove);
    controls.push({ sync: draw });
    return cv;
  }

  // ---------- panels ----------
  const TABS = [['primaries', 'Primaries'], ['curves', 'Curves'], ['hue', 'Hue / Sat curves'], ['lut', 'LUTs & Looks'], ['match', 'Auto & Match']];
  function renderTab() {
    controls.length = 0; el.body.textContent = '';
    el.tabs.querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.tab === S.tab));
    const tab = S.tab;
    if (tab === 'primaries') {
      el.body.append(h('div', { class: 'cf-wheels' }, wheelCtl('Lift', 'lift'), wheelCtl('Gamma', 'gamma'), wheelCtl('Gain', 'gain'), wheelCtl('Offset', 'offset')),
        h('div', { class: 'cf-sliders' },
          slider('Contrast', { min: 0, max: 2, step: 0.01, def: 1, get: (n) => n.contrast, set: (n, v) => { n.contrast = v; } }),
          slider('Pivot', { min: 0, max: 1, step: 0.005, def: 0.435, get: (n) => n.pivot, set: (n, v) => { n.pivot = v; } }),
          slider('Saturation', { min: 0, max: 2, step: 0.01, def: 1, get: (n) => n.saturation, set: (n, v) => { n.saturation = v; } }),
          slider('Hue', { min: -180, max: 180, step: 0.5, def: 0, fmt: 1, get: (n) => n.hue, set: (n, v) => { n.hue = v; } }),
          slider('Temp', { min: -100, max: 100, step: 0.5, def: 0, fmt: 1, get: (n) => n.temp, set: (n, v) => { n.temp = v; } }),
          slider('Tint', { min: -100, max: 100, step: 0.5, def: 0, fmt: 1, get: (n) => n.tint, set: (n, v) => { n.tint = v; } }),
          slider('Color boost', { min: 0, max: 100, step: 0.5, def: 0, fmt: 1, get: (n) => n.boost, set: (n, v) => { n.boost = v; } }),
          slider('Shadows', { min: -100, max: 100, step: 0.5, def: 0, fmt: 1, get: (n) => n.shadows, set: (n, v) => { n.shadows = v; } }),
          slider('Highlights', { min: -100, max: 100, step: 0.5, def: 0, fmt: 1, get: (n) => n.highlights, set: (n, v) => { n.highlights = v; } })));
    } else if (tab === 'curves') {
      const chans = [['y', 'Luma', '#e6ebff'], ['r', 'Red', '#ff5a68'], ['g', 'Green', '#3be07a'], ['b', 'Blue', '#5a8cff']];
      const box = h('div', { class: 'cf-curvebox' });
      const draw = () => { box.textContent = ''; const [id, , col] = chans.find((c) => c[0] === S.curve);
        box.append(curveEditor({ id: `tone:${id}`, tone: true, ymin: 0, ymax: 1, color: col, get: (n) => n.curves[id], set: (n, v) => { n.curves[id] = v; } })); controls.push({ sync() {} }); };
      el.body.append(h('div', { class: 'cf-curvetab' }, h('div', { class: 'cf-chips' }, chans.map(([id, label]) => h('button', { class: `cf-chip${S.curve === id ? ' on' : ''}`, onclick: () => { S.curve = id; renderTab(); } }, label)),
        h('button', { class: 'cf-chip', onclick: () => edit('c:reset', (g, n) => { n.curves[S.curve] = G.tone0(); renderTab(); }) }, 'Reset curve')), box,
        h('div', { class: 'cf-hint' }, 'Click to add a point · drag to move · double-click or right-click a point to remove it. Luma moves all three channels; R, G, B bend one.')));
      draw();
    } else if (tab === 'hue') {
      const kinds = [['hueVsHue', 'Hue vs Hue', -1, 1, true, [0, 1 / 6, 2 / 6, 3 / 6, 4 / 6, 5 / 6], 'Move one colour towards another (up = shift forward round the wheel).'],
        ['hueVsSat', 'Hue vs Sat', -1, 1, true, [0, 1 / 6, 2 / 6, 3 / 6, 4 / 6, 5 / 6], 'Raise or lower the saturation of just one colour range.'],
        ['hueVsLum', 'Hue vs Lum', -1, 1, true, [0, 1 / 6, 2 / 6, 3 / 6, 4 / 6, 5 / 6], 'Brighten or darken one colour range.'],
        ['lumVsSat', 'Lum vs Sat', -1, 1, false, [0, 0.25, 0.5, 0.75, 1], 'Saturate or desaturate by brightness (left = shadows, right = highlights).']];
      const k = kinds.find((x) => x[0] === S.hueCurve) || kinds[0], box = h('div', { class: 'cf-curvebox' });
      box.append(curveEditor({ id: `hue:${k[0]}`, ymin: k[2], ymax: k[3], cyclic: k[4], hueBar: k[4], seed: k[5], color: '#e6ebff', get: (n) => n[k[0]], set: (n, v) => { n[k[0]] = v; } }));
      el.body.append(h('div', { class: 'cf-curvetab' }, h('div', { class: 'cf-chips' }, kinds.map((x) => h('button', { class: `cf-chip${S.hueCurve === x[0] ? ' on' : ''}`, onclick: () => { S.hueCurve = x[0]; renderTab(); } }, x[1])),
        h('button', { class: 'cf-chip', onclick: () => edit('c:reset', (g, n) => { n[k[0]] = []; renderTab(); }) }, 'Reset curve')), box, h('div', { class: 'cf-hint' }, `${k[6]} Click to add a point (the first click lays down a flat set of anchors), drag to move, double-click to remove.`)));
    } else if (tab === 'lut') {
      const n = nodeOf(), file = h('input', { type: 'file', accept: '.cube', style: 'display:none', onchange: (e) => { if (e.target.files[0]) importCube(e.target.files[0]); e.target.value = ''; } });
      const libs = Object.entries(S.lib);
      el.body.append(h('div', { class: 'cf-lut' },
        h('div', { class: 'cf-col' }, h('div', { class: 'cf-sub' }, '3D LUTs'), file, h('button', { class: 'cf-btn', onclick: () => file.click() }, '⤓ Import .cube LUT…'),
          h('div', { class: 'cf-lutlist' }, libs.length ? libs.map(([id, l]) => h('div', { class: `cf-lutitem${n && n.lut && n.lut.id === id ? ' on' : ''}` },
            h('button', { class: 'cf-link', onclick: () => change((c) => { c.grade = c.grade || G.newGrade(); (c.grade.nodes[S.ni] || c.grade.nodes[0]).lut = { id, strength: 1 }; }) }, `${l.title} · ${l.size}³`),
            h('button', { class: 'cf-x', title: 'Remove from library', onclick: () => { delete S.lib[id]; saveLib(); renderTab(); } }, '×'))) : h('div', { class: 'cf-hint' }, 'No LUTs yet. Import a .cube file (3D or 1D); it is stored in this browser and baked into the export.')),
          n && n.lut && S.lib[n.lut.id] ? h('div', {}, slider('LUT strength', { min: 0, max: 1, step: 0.01, def: 1, get: (nn) => (nn.lut ? nn.lut.strength : 1), set: (nn, v) => { if (nn.lut) nn.lut.strength = v; } }),
            h('button', { class: 'cf-btn', onclick: () => edit('lut:off', (g, nn) => { nn.lut = null; renderTab(); }) }, 'Remove LUT from this node')) : null),
        h('div', { class: 'cf-col' }, h('div', { class: 'cf-sub' }, 'Looks (add a node you can tune or switch off)'),
          h('div', { class: 'cf-looks' }, Object.keys(LOOKS).map((name) => h('button', { class: 'cf-btn', onclick: () => addLook(name) }, name))))));
    } else if (tab === 'match') {
      const n = nodeOf(), cdl = n && n.cdl, fmt = (a) => a.map((x) => x.toFixed(3)).join('  ');
      el.body.append(h('div', { class: 'cf-lut' },
        h('div', { class: 'cf-col' }, h('div', { class: 'cf-sub' }, 'Auto balance'), h('div', { class: 'cf-hint' }, 'Reads the frame at the playhead: neutralises the colour cast on the mid tones and sets black and white points. Adds (or updates) a first node called "Auto Balance".'),
          h('button', { class: 'cf-btn accent', onclick: autoBalance }, '✨ Auto balance this clip'),
          h('div', { class: 'cf-sub', style: 'margin-top:14px' }, 'Shot match'), h('div', { class: 'cf-hint' }, 'Pick a reference still in the gallery (left), then match this clip to its colour and contrast. Adds (or updates) a last node called "Shot Match".'),
          h('div', { class: 'cf-matchrow' }, h('span', {}, S.ref ? `Reference: ${(S.stills.find((x) => x.id === S.ref) || {}).name || 'none'}` : 'No reference chosen'), h('button', { class: 'cf-btn accent', onclick: () => matchToStill() }, 'Match to still'))),
        h('div', { class: 'cf-col' }, h('div', { class: 'cf-sub' }, `ASC CDL of node ${S.ni + 1}${n && n.label ? ` · ${n.label}` : ''}`),
          cdl ? h('pre', { class: 'cf-cdl' }, `Slope   ${fmt(cdl.slope)}\nOffset  ${fmt(cdl.offset)}\nPower   ${fmt(cdl.power)}`) : null,
          h('div', { class: 'cf-hint' }, 'The Auto balance and Shot match nodes are plain slope / offset / power, the interchange format other grading tools read.'))));
    }
    refreshControls();
  }
  function refreshControls() { const n = nodeOf(); controls.forEach((c) => c.sync(n)); }

  function renderNodes() {
    const g = gradeOf(), box = el.nodes; box.textContent = '';
    const list = g ? g.nodes : [blankNode()];
    list.forEach((n, i) => box.append(h('div', { class: `cf-node${i === S.ni ? ' sel' : ''}${n.enabled === false ? ' off' : ''}${g && !G.isNodeIdentity(n) ? ' mod' : ''}`, onclick: () => { S.ni = i; refreshUI(); } },
      h('span', { class: 'cf-num0' }, String(i + 1).padStart(2, '0')), h('span', { class: 'cf-nlabel' }, n.label || `Node ${i + 1}`),
      h('button', { class: 'cf-eye', title: n.enabled === false ? 'Enable node' : 'Bypass node', onclick: (e) => { e.stopPropagation(); if (g) change(() => { n.enabled = n.enabled === false; }); } }, n.enabled === false ? '○' : '●'))));
  }
  function renderHeader() {
    const c = clip(), g = gradeOf(), list = N.tl.clips, idx = c ? list.indexOf(c) : -1;
    el.clipLabel.textContent = c ? `${idx + 1}/${list.length} · ${c.label || c.src}` : 'No clip at the playhead';
    el.gradeOn.classList.toggle('on', !g || g.on !== false); el.gradeOn.textContent = !g || g.on !== false ? 'Grade ON' : 'Grade OFF';
    el.orig.classList.toggle('on', S.bypass); el.count.textContent = `${gradedCount()} graded clip${gradedCount() === 1 ? '' : 's'}`;
    el.wipe.value = S.wipe;
  }
  function renderGallery() {
    el.stills.textContent = '';
    if (!S.stills.length) el.stills.append(h('div', { class: 'cf-hint', style: 'padding:6px' }, 'No stills yet. "Grab still" keeps the current frame with its grade, so you can apply it to other shots, match to it, or compare against it.'));
    S.stills.forEach((st) => el.stills.append(h('div', { class: `cf-still${st.id === S.ref ? ' sel' : ''}`, onclick: () => { S.ref = st.id; renderGallery(); updateStillOverlay(); if (S.tab === 'match') renderTab(); } },
      h('img', { src: st.thumb, alt: st.name }), h('span', {}, st.name),
      h('div', { class: 'cf-stillbtns' }, h('button', { class: 'cf-link', onclick: (e) => { e.stopPropagation(); applyStill(st); } }, 'Apply grade'),
        h('button', { class: 'cf-x', title: 'Delete still', onclick: (e) => { e.stopPropagation(); S.stills = S.stills.filter((x) => x.id !== st.id); if (S.ref === st.id) S.ref = null; saveStills(); renderGallery(); updateStillOverlay(); } }, '×')))));
    el.compare.classList.toggle('on', S.compare); el.compare.disabled = !S.ref;
  }
  function updateStillOverlay() {
    const st = S.stills.find((x) => x.id === S.ref), img = el.stillOverlay;
    if (!img) return;
    if (S.compare && st) { img.src = st.thumb; img.style.display = 'block'; img.style.clipPath = `inset(0 0 0 ${S.wipe}%)`; } else img.style.display = 'none';
  }
  function refreshUI() { renderNodes(); renderHeader(); renderTab(); }

  // ---------- grade-level actions ----------
  const actions = {
    toggle: () => change((c) => { c.grade = c.grade || G.newGrade(); c.grade.on = c.grade.on === false; }),
    orig: () => { S.bypass = !S.bypass; renderHeader(); },
    copy: () => { const g = gradeOf(); if (!g) return say('This clip has no grade to copy.'); S.clipboard = JSON.parse(JSON.stringify(g)); say('Grade copied.'); },
    paste: () => { if (!S.clipboard) return say('Nothing copied yet.'); change((c) => { c.grade = JSON.parse(JSON.stringify(S.clipboard)); }); say('Grade pasted.'); },
    all: () => { const g = gradeOf(); if (!g) return say('Grade this clip first.'); if (!confirm('Apply this clip\'s grade to every clip in the timeline? (Undo with Ctrl+Z.)')) return; N.checkpoint(); N.tl.clips.forEach((c) => { c.grade = JSON.parse(JSON.stringify(g)); }); N.persist(); refreshUI(); say('Grade applied to all clips.'); },
    reset: () => { if (!gradeOf()) return; change((c) => { delete c.grade; S.ni = 0; }); say('Clip grade reset.'); },
    addNode: () => change((c) => { c.grade = c.grade || G.newGrade(); c.grade.nodes.push(G.newNode('')); S.ni = c.grade.nodes.length - 1; }),
    delNode: () => { const g = gradeOf(); if (!g) return; change((c) => { if (c.grade.nodes.length > 1) c.grade.nodes.splice(S.ni, 1); else c.grade.nodes[0] = G.newNode(''); S.ni = Math.max(0, S.ni - 1); }); },
    resetNode: () => { if (!gradeOf()) return; change((c) => { const old = c.grade.nodes[S.ni]; const fresh = G.newNode(old.label); fresh.id = old.id; c.grade.nodes[S.ni] = fresh; }); },
    prev: () => step(-1), next: () => step(1), grab: grabStill,
    compare: () => { S.compare = !S.compare; renderGallery(); updateStillOverlay(); },
  };
  function step(dir) {
    const c = clip(), list = N.tl.clips; if (!c) return;
    const lay = window.NLEModel.layout(N.tl), i = list.indexOf(c) + dir; if (i < 0 || i >= list.length) return;
    S.ni = 0; N.seek(lay[i].start + 0.01);
  }

  // ---------- mount ----------
  function mount() {
    N = window.NLE; if (!N || el.mounted) return;
    wrap = document.querySelector('.davinci-nle-wrapper');
    if (!wrap) return;
    loadLib(); loadStills();
    const mk = (id) => document.getElementById(id);
    el.gallery = mk('colorGallery'); el.scopes = mk('colorScopes'); el.panel = mk('colorPanel');
    // gallery (left)
    el.stills = h('div', { class: 'cf-stills' }); el.compare = h('button', { class: 'cf-chip', title: 'Show the chosen still on the right half of the viewer', onclick: actions.compare }, 'Compare with still');
    el.gallery.append(h('div', { class: 'cf-head' }, h('b', {}, 'Stills'), h('button', { class: 'cf-btn accent', title: 'Keep the current frame with its grade (Ctrl+Alt+G)', onclick: actions.grab }, '📷 Grab still')), el.stills, h('div', { class: 'cf-foot' }, el.compare));
    // scopes (right)
    const sc = (cls, title, w, hgt) => { const cv = h('canvas', { width: w, height: hgt, class: `cf-scope ${cls}` }); return [h('div', { class: 'cf-stitle' }, title), cv, cv]; };
    const w1 = sc('wave', 'Waveform', 256, 128), w2 = sc('parade', 'RGB parade', 256, 128), w3 = sc('vec', 'Vectorscope', 200, 200), w4 = sc('hist', 'Histogram', 256, 90);
    el.scopeWave = w1[2]; el.scopeParade = w2[2]; el.scopeVec = w3[2]; el.scopeHist = w4[2];
    el.scopes.append(h('div', { class: 'cf-head' }, h('b', {}, 'Scopes'), h('span', { class: 'cf-hint', style: 'margin:0' }, 'of the graded frame')),
      h('div', { class: 'cf-scopegrid' }, h('div', {}, w1[0], w1[1]), h('div', {}, w2[0], w2[1]), h('div', {}, w3[0], w3[1]), h('div', {}, w4[0], w4[1])));
    // panel (bottom)
    el.nodes = h('div', { class: 'cf-nodes' });
    const btn = (label, act, title, cls) => h('button', { class: `cf-btn ${cls || ''}`, title, onclick: actions[act] }, label);
    el.clipLabel = h('span', { class: 'cf-cliplabel' }); el.gradeOn = btn('Grade ON', 'toggle', 'Turn this clip\'s whole grade on or off'); el.orig = btn('Original', 'orig', 'Show the original picture on the whole monitor');
    el.count = h('span', { class: 'cf-count' });
    el.wipe = h('input', { type: 'range', min: 0, max: 100, step: 1, value: 100, class: 'cf-wipeinput', title: 'Split: left = graded, right = original (or the chosen still)', oninput: () => { S.wipe = +el.wipe.value; updateStillOverlay(); updateWipeHandle(); } });
    el.tabs = h('div', { class: 'cf-tabs' }, TABS.map(([id, label]) => h('button', { 'data-tab': id, onclick: () => { S.tab = id; renderTab(); } }, label)));
    el.body = h('div', { class: 'cf-body' });
    el.panel.append(
      h('div', { class: 'cf-nodecol' }, h('div', { class: 'cf-head' }, h('b', {}, 'Nodes')), el.nodes,
        h('div', { class: 'cf-nodebtns' }, btn('+ Node', 'addNode', 'Add a serial node after the last one'), btn('Delete', 'delNode', 'Delete this node'), btn('Reset', 'resetNode', 'Reset this node to neutral'))),
      h('div', { class: 'cf-main' },
        h('div', { class: 'cf-bar' }, btn('‹', 'prev', 'Previous clip'), el.clipLabel, btn('›', 'next', 'Next clip'), h('span', { class: 'cf-sep' }), el.gradeOn, el.orig, h('label', { class: 'cf-splitlab' }, 'Split', el.wipe),
          h('span', { class: 'cf-grow' }), el.count, btn('Copy', 'copy', 'Copy this clip\'s grade'), btn('Paste', 'paste', 'Paste the copied grade onto this clip'), btn('Apply to all', 'all', 'Copy this grade to every clip'), btn('Reset clip', 'reset', 'Remove this clip\'s grade')),
        el.tabs, el.body));
    // viewer extras: still overlay + split handle
    const screen = N.root.screen;
    el.stillOverlay = h('img', { class: 'cf-still-img', alt: '' }); el.handle = h('div', { class: 'cf-handle', title: 'Drag to move the split' });
    screen.append(el.stillOverlay, el.handle);
    el.handle.addEventListener('pointerdown', (e) => { el.handle.setPointerCapture(e.pointerId); el.handle.onpointermove = (ev) => { const r = screen.getBoundingClientRect(); S.wipe = Math.round(clamp(((ev.clientX - r.left) / r.width) * 100, 0, 100)); el.wipe.value = S.wipe; updateStillOverlay(); updateWipeHandle(); }; });
    el.handle.addEventListener('pointerup', () => { el.handle.onpointermove = null; });
    document.addEventListener('keydown', (e) => { if (S.open && e.ctrlKey && e.altKey && (e.key === 'g' || e.key === 'G')) { e.preventDefault(); grabStill(); } });
    N.on('time', () => { if (!S.open) return; const c = clip(); const id = c ? c.id : ''; if (id !== el.lastClip) { el.lastClip = id; S.ni = 0; refreshUI(); } });
    el.mounted = true; renderGallery();
    setInterval(() => { if (!S.open) return; const g = gradeOf(), sig = g ? JSON.stringify(g) : ''; if (sig !== el.sig) { el.sig = sig; renderNodes(); renderHeader(); refreshControls(); } }, 300);   // picks up undo / redo / paste
    requestAnimationFrame(monitorTick);
  }
  function updateWipeHandle() { if (el.handle) { el.handle.style.display = S.open && S.wipe > 0 && S.wipe < 100 ? 'block' : 'none'; el.handle.style.left = `${S.wipe}%`; } }

  function open() {
    if (!el.mounted) mount();
    if (!wrap) return;
    S.open = true; wrap.classList.add('is-color'); el.lastClip = null; refreshUI(); updateStillOverlay(); updateWipeHandle();
    say(clip() ? '' : 'Color: load a job and put the playhead on a clip to grade it.');
  }
  function close() { if (!wrap || !S.open) return; S.open = false; wrap.classList.remove('is-color'); updateWipeHandle(); if (el.stillOverlay) el.stillOverlay.style.display = 'none'; }

  window.NLEColor = { mount, open, close, lutFor, gradedCount, tableFor, get state() { return S; }, get lib() { return S.lib; } };
})();
