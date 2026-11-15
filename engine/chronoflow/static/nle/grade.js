/* ChronoFlow colour grade - pure maths (no DOM), shared by the monitor, the scopes and the export.
   A clip's grade is a serial stack of nodes. The whole stack is baked into ONE 3D LUT:
     - the monitor draws it with WebGL (nle/color.js),
     - the scopes apply it to a small frame on the CPU,
     - the export writes it as a .cube file and FFmpeg's lut3d applies it,
   so what you see is what is rendered. All values are display-referred RGB, 0..1, Rec.709 luma. */
(function (root) {
  'use strict';

  const LUMA = [0.2126, 0.7152, 0.0722];
  const LUT_SIZE = 33;
  const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
  const smooth = (a, b, x) => { const t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
  const wheel0 = () => ({ x: 0, y: 0, m: 0 });
  const tone0 = () => [[0, 0], [1, 1]];

  /** A fresh node: every control at its neutral value. */
  function newNode(label) {
    return {
      id: `n${Math.random().toString(36).slice(2, 8)}`, label: label || '', enabled: true,
      cdl: { slope: [1, 1, 1], offset: [0, 0, 0], power: [1, 1, 1] },          // ASC CDL, applied first (Auto balance / Shot match write here)
      lift: wheel0(), gamma: wheel0(), gain: wheel0(), offset: wheel0(),
      contrast: 1, pivot: 0.435, saturation: 1, hue: 0, temp: 0, tint: 0, boost: 0, shadows: 0, highlights: 0,
      curves: { y: tone0(), r: tone0(), g: tone0(), b: tone0() },
      hueVsHue: [], hueVsSat: [], hueVsLum: [], lumVsSat: [],                    // [] = untouched; points are [x, offset]
      lut: null,                                                                  // {id, name, strength 0..1}
    };
  }
  const newGrade = () => ({ v: 1, on: true, nodes: [newNode('')] });

  // ---------- curves (monotone cubic Hermite: never overshoots between points) ----------
  function hermite(xs, ys) {
    const n = xs.length, d = [], m = new Array(n);
    for (let i = 0; i < n - 1; i++) d[i] = (ys[i + 1] - ys[i]) / Math.max(1e-9, xs[i + 1] - xs[i]);
    m[0] = d[0]; m[n - 1] = d[n - 2];
    for (let i = 1; i < n - 1; i++) m[i] = d[i - 1] * d[i] <= 0 ? 0 : (d[i - 1] + d[i]) / 2;
    for (let i = 0; i < n - 1; i++) {
      if (d[i] === 0) { m[i] = m[i + 1] = 0; continue; }
      const a = m[i] / d[i], b = m[i + 1] / d[i], s = a * a + b * b;
      if (s > 9) { const t = 3 / Math.sqrt(s); m[i] = t * a * d[i]; m[i + 1] = t * b * d[i]; }
    }
    return (x) => {
      if (x <= xs[0]) return ys[0];
      if (x >= xs[n - 1]) return ys[n - 1];
      let i = 0; while (x > xs[i + 1]) i++;
      const h = xs[i + 1] - xs[i], t = (x - xs[i]) / h, t2 = t * t, t3 = t2 * t;
      return (2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h * m[i] + (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h * m[i + 1];
    };
  }
  /** Curve through [x, y] points. cyclic = hue axis that wraps from 1 back to 0. Fewer than two points: constant (or identity if none). */
  function curveFn(points, cyclic, fallback) {
    const p = (points || []).filter((q) => Array.isArray(q)).sort((a, b) => a[0] - b[0]);
    if (!p.length) return fallback || ((x) => x);
    if (p.length === 1) return () => p[0][1];
    if (cyclic) {
      const ext = [...p.map((q) => [q[0] - 1, q[1]]), ...p, ...p.map((q) => [q[0] + 1, q[1]])];
      const f = hermite(ext.map((q) => q[0]), ext.map((q) => q[1]));
      return (x) => f(((x % 1) + 1) % 1);
    }
    return hermite(p.map((q) => q[0]), p.map((q) => q[1]));
  }
  const isToneIdentity = (pts) => !pts || (pts.length === 2 && pts[0][0] === 0 && pts[0][1] === 0 && pts[1][0] === 1 && pts[1][1] === 1);

  // ---------- colour helpers ----------
  function rgb2hsv(r, g, b) {
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b), c = mx - mn;
    let h = 0;
    if (c > 1e-9) { h = mx === r ? ((g - b) / c) % 6 : mx === g ? (b - r) / c + 2 : (r - g) / c + 4; h /= 6; if (h < 0) h += 1; }
    return [h, mx > 1e-9 ? c / mx : 0, mx];
  }
  function hsv2rgb(h, s, v) {
    h = ((h % 1) + 1) % 1; const i = Math.floor(h * 6), f = h * 6 - i, p = v * (1 - s), q = v * (1 - f * s), t = v * (1 - (1 - f) * s);
    return [[v, t, p], [q, v, p], [p, v, t], [p, q, v], [t, p, v], [v, p, q]][i % 6];
  }
  /** Wheel puck (x, y in -1..1, screen space, y up) to a per-channel RGB offset with zero mean, so the puck changes colour, not brightness. */
  function wheelRgb(w) {
    const amt = Math.min(1, Math.hypot(w.x, w.y));
    if (amt < 1e-6) return [0, 0, 0];
    const hue = (Math.atan2(w.y, w.x) / (2 * Math.PI) + 1) % 1;   // 0 = right (red), counter-clockwise, as on a Resolve wheel
    const c = hsv2rgb(hue, 1, 1), mean = (c[0] + c[1] + c[2]) / 3;
    return [(c[0] - mean) * amt, (c[1] - mean) * amt, (c[2] - mean) * amt];
  }

  // ---------- one node -> function(r, g, b, out) ----------
  function compileNode(n, lutLib) {
    const cdl = n.cdl || { slope: [1, 1, 1], offset: [0, 0, 0], power: [1, 1, 1] };
    const lw = wheelRgb(n.lift), gw = wheelRgb(n.gamma), nw = wheelRgb(n.gain), ow = wheelRgb(n.offset);
    const lift = [0, 1, 2].map((i) => (lw[i] + n.lift.m) * 0.5);                                   // shadows: raises black, fades out to white
    const gain = [0, 1, 2].map((i) => Math.max(0, 1 + (nw[i] + n.gain.m)));                         // highlights: multiplies
    const gamma = [0, 1, 2].map((i) => 1 / clamp(1 + (gw[i] + n.gamma.m) * 0.8, 0.15, 4));          // midtones: exponent
    const off = [0, 1, 2].map((i) => (ow[i] + n.offset.m) * 0.15);                                  // whole image
    const t = n.temp / 100, ti = n.tint / 100;
    const wb = [1 + 0.3 * t, 1 - 0.25 * ti, 1 - 0.3 * t];                                           // + temp warms (more red, less blue), + tint goes magenta
    const sh = n.shadows / 100, hi = n.highlights / 100;
    const hueRot = (n.hue * Math.PI) / 180, cosH = Math.cos(hueRot), sinH = Math.sin(hueRot);
    const toneY = isToneIdentity(n.curves.y) ? null : curveFn(n.curves.y);
    const toneC = ['r', 'g', 'b'].map((k) => (isToneIdentity(n.curves[k]) ? null : curveFn(n.curves[k])));
    const hh = n.hueVsHue.length ? curveFn(n.hueVsHue, true, () => 0) : null;
    const hs = n.hueVsSat.length ? curveFn(n.hueVsSat, true, () => 0) : null;
    const hl = n.hueVsLum.length ? curveFn(n.hueVsLum, true, () => 0) : null;
    const ls = n.lumVsSat.length ? curveFn(n.lumVsSat, false, () => 0) : null;
    const lut = n.lut && lutLib && lutLib[n.lut.id] ? { ...lutLib[n.lut.id], strength: clamp(n.lut.strength == null ? 1 : n.lut.strength, 0, 1) } : null;
    const v = [0, 0, 0];

    return function (r, g, b, out) {
      v[0] = r; v[1] = g; v[2] = b;
      for (let i = 0; i < 3; i++) {
        let c = v[i] * cdl.slope[i] + cdl.offset[i];
        c = c > 0 && cdl.power[i] !== 1 ? Math.pow(c, cdl.power[i]) : c;
        c += off[i];
        c *= wb[i];
        c = c + lift[i] * (1 - c);
        c *= gain[i];
        if (c > 0 && gamma[i] !== 1) c = Math.pow(c, gamma[i]);
        v[i] = c;
      }
      if (sh || hi) {
        const y = LUMA[0] * v[0] + LUMA[1] * v[1] + LUMA[2] * v[2];
        const d = sh * 0.3 * (1 - smooth(0, 0.55, y)) + hi * 0.3 * smooth(0.45, 1, y);
        v[0] += d; v[1] += d; v[2] += d;
      }
      if (n.contrast !== 1) for (let i = 0; i < 3; i++) v[i] = (v[i] - n.pivot) * n.contrast + n.pivot;
      if (n.saturation !== 1 || n.boost || n.hue) {
        const y = LUMA[0] * v[0] + LUMA[1] * v[1] + LUMA[2] * v[2];
        const chroma = clamp(Math.max(v[0], v[1], v[2]) - Math.min(v[0], v[1], v[2]), 0, 1);
        const s = n.saturation * (1 + (n.boost / 100) * (1 - chroma));                              // colour boost lifts the dull colours more than the vivid ones
        let dr = (v[0] - y) * s, dg = (v[1] - y) * s, db = (v[2] - y) * s;
        if (n.hue) {                                                                                  // rotate the chroma vector round the grey axis (Rodrigues, axis (1,1,1)/sqrt3)
          const k = 1 / 3, a = cosH + k * (1 - cosH), bb = k * (1 - cosH) - Math.sqrt(k) * sinH, cc = k * (1 - cosH) + Math.sqrt(k) * sinH;
          const nr = a * dr + bb * dg + cc * db, ng = cc * dr + a * dg + bb * db, nb = bb * dr + cc * dg + a * db;
          dr = nr; dg = ng; db = nb;
        }
        v[0] = y + dr; v[1] = y + dg; v[2] = y + db;
      }
      if (toneY) for (let i = 0; i < 3; i++) v[i] = toneY(v[i]);
      for (let i = 0; i < 3; i++) if (toneC[i]) v[i] = toneC[i](v[i]);
      if (hh || hs || hl || ls) {
        const c = [clamp(v[0], 0, 1), clamp(v[1], 0, 1), clamp(v[2], 0, 1)];
        const [h0, s0, v0] = rgb2hsv(c[0], c[1], c[2]);
        const wgt = smooth(0, 0.15, s0);                                                              // greys are left alone
        const yy = LUMA[0] * c[0] + LUMA[1] * c[1] + LUMA[2] * c[2];
        let h = h0, s1 = s0, v1 = v0;
        if (hh) h = h0 + hh(h0) * 0.25 * wgt;
        if (hs) s1 *= 1 + hs(h0) * wgt;
        if (ls) s1 *= 1 + ls(yy);
        if (hl) v1 = v0 + hl(h0) * 0.3 * wgt;
        const o = hsv2rgb(h, clamp(s1, 0, 1), clamp(v1, 0, 1.5));
        v[0] = o[0]; v[1] = o[1]; v[2] = o[2];
      }
      if (lut && lut.strength > 0) {
        const o = [0, 0, 0]; sampleLut(lut.table, lut.size, clamp(v[0], 0, 1), clamp(v[1], 0, 1), clamp(v[2], 0, 1), o);
        for (let i = 0; i < 3; i++) v[i] += (o[i] - v[i]) * lut.strength;
      }
      out[0] = v[0]; out[1] = v[1]; out[2] = v[2];
    };
  }

  // ---------- 3D LUT (table layout: red fastest, then green, then blue - the .cube order) ----------
  function sampleLut(table, N, r, g, b, out) {
    const fr = r * (N - 1), fg = g * (N - 1), fb = b * (N - 1);
    const r0 = Math.min(N - 2, Math.floor(fr)), g0 = Math.min(N - 2, Math.floor(fg)), b0 = Math.min(N - 2, Math.floor(fb));
    const dr = fr - r0, dg = fg - g0, db = fb - b0;
    for (let c = 0; c < 3; c++) {
      const at = (ri, gi, bi) => table[((bi * N + gi) * N + ri) * 3 + c];
      const c00 = at(r0, g0, b0) * (1 - dr) + at(r0 + 1, g0, b0) * dr, c10 = at(r0, g0 + 1, b0) * (1 - dr) + at(r0 + 1, g0 + 1, b0) * dr;
      const c01 = at(r0, g0, b0 + 1) * (1 - dr) + at(r0 + 1, g0, b0 + 1) * dr, c11 = at(r0, g0 + 1, b0 + 1) * (1 - dr) + at(r0 + 1, g0 + 1, b0 + 1) * dr;
      out[c] = (c00 * (1 - dg) + c10 * dg) * (1 - db) + (c01 * (1 - dg) + c11 * dg) * db;
    }
    return out;
  }

  const activeNodes = (grade) => (grade && grade.on !== false ? (grade.nodes || []).filter((n) => n.enabled !== false && !isNodeIdentity(n)) : []);
  function isNodeIdentity(n) {
    const d = newNode('');
    const strip = (x) => JSON.stringify({ ...x, id: 0, label: 0, enabled: 0 });
    return strip(n) === strip(d);
  }
  const isIdentity = (grade) => activeNodes(grade).length === 0;

  /** Bake the grade into a size^3 table of RGB floats (clamped to 0..1). */
  function bake(grade, size, lutLib) {
    const N = size || LUT_SIZE, nodes = activeNodes(grade).map((n) => compileNode(n, lutLib)), table = new Float32Array(N * N * N * 3);
    const v = [0, 0, 0], o = [0, 0, 0];
    let k = 0;
    for (let bi = 0; bi < N; bi++) for (let gi = 0; gi < N; gi++) for (let ri = 0; ri < N; ri++) {
      v[0] = ri / (N - 1); v[1] = gi / (N - 1); v[2] = bi / (N - 1);
      for (const f of nodes) { f(v[0], v[1], v[2], o); v[0] = o[0]; v[1] = o[1]; v[2] = o[2]; }
      table[k++] = clamp(v[0], 0, 1); table[k++] = clamp(v[1], 0, 1); table[k++] = clamp(v[2], 0, 1);
    }
    return table;
  }

  function toCube(table, size, title) {
    const lines = [`TITLE "${(title || 'ChronoFlow grade').replace(/"/g, "'")}"`, `LUT_3D_SIZE ${size}`, 'DOMAIN_MIN 0.0 0.0 0.0', 'DOMAIN_MAX 1.0 1.0 1.0'];
    for (let i = 0; i < table.length; i += 3) lines.push(`${table[i].toFixed(6)} ${table[i + 1].toFixed(6)} ${table[i + 2].toFixed(6)}`);
    return lines.join('\n') + '\n';
  }

  /** Read a .cube file (3D, or 1D which becomes three per-channel curves). Large tables are resampled down to LUT_SIZE. Throws a readable error. */
  function parseCube(text) {
    let size3 = 0, size1 = 0, title = '', dmin = [0, 0, 0], dmax = [1, 1, 1];
    const rows = [];
    for (const raw of String(text).split(/\r?\n/)) {
      const line = raw.trim();
      if (!line || line.startsWith('#')) continue;
      const parts = line.split(/\s+/);
      const key = parts[0].toUpperCase();
      if (key === 'TITLE') title = line.slice(5).trim().replace(/^"|"$/g, '');
      else if (key === 'LUT_3D_SIZE') size3 = parseInt(parts[1], 10);
      else if (key === 'LUT_1D_SIZE') size1 = parseInt(parts[1], 10);
      else if (key === 'DOMAIN_MIN') dmin = parts.slice(1, 4).map(Number);
      else if (key === 'DOMAIN_MAX') dmax = parts.slice(1, 4).map(Number);
      else if (/^[-+\d.]/.test(parts[0]) && parts.length >= 3) rows.push([+parts[0], +parts[1], +parts[2]]);
    }
    if (!size3 && !size1) throw new Error('Not a .cube file: no LUT_3D_SIZE or LUT_1D_SIZE line.');
    const want = size3 ? size3 ** 3 : size1;
    if (rows.length !== want || rows.some((r) => r.some((x) => !Number.isFinite(x)))) throw new Error(`.cube has ${rows.length} usable rows, expected ${want}.`);
    const norm = (x, i) => clamp((x - dmin[i]) / ((dmax[i] - dmin[i]) || 1), 0, 1);
    let table, N;
    if (size3) {
      const src = new Float32Array(want * 3);
      rows.forEach((r, i) => { src[i * 3] = r[0]; src[i * 3 + 1] = r[1]; src[i * 3 + 2] = r[2]; });
      if (size3 <= LUT_SIZE) { table = src; N = size3; }
      else {
        N = LUT_SIZE; table = new Float32Array(N ** 3 * 3); const o = [0, 0, 0]; let k = 0;
        for (let bi = 0; bi < N; bi++) for (let gi = 0; gi < N; gi++) for (let ri = 0; ri < N; ri++) {
          sampleLut(src, size3, ri / (N - 1), gi / (N - 1), bi / (N - 1), o); table[k++] = o[0]; table[k++] = o[1]; table[k++] = o[2];
        }
      }
    } else {
      N = LUT_SIZE; table = new Float32Array(N ** 3 * 3);
      const at = (x, c) => { const f = clamp(x, 0, 1) * (size1 - 1), i = Math.min(size1 - 2, Math.floor(f)); return rows[i][c] + (rows[i + 1][c] - rows[i][c]) * (f - i); };
      let k = 0;
      for (let bi = 0; bi < N; bi++) for (let gi = 0; gi < N; gi++) for (let ri = 0; ri < N; ri++) { table[k++] = at(ri / (N - 1), 0); table[k++] = at(gi / (N - 1), 1); table[k++] = at(bi / (N - 1), 2); }
    }
    return { title: title || 'Imported LUT', size: N, table: table.map((x, i) => norm(x, i % 3)) };
  }

  /** Short stable id for a grade's effective content (identical grades share one LUT in the export). */
  function hashGrade(grade, lutLib) {
    const eff = activeNodes(grade).map((n) => ({ ...n, id: 0, label: 0, enabled: 0, lutData: n.lut && lutLib && lutLib[n.lut.id] ? lutLib[n.lut.id].title : 0 }));
    const s = JSON.stringify(eff);
    let h1 = 0x811c9dc5, h2 = 5381;
    for (let i = 0; i < s.length; i++) { h1 = Math.imul(h1 ^ s.charCodeAt(i), 16777619); h2 = (h2 * 33) ^ s.charCodeAt(i); }
    return ((h1 >>> 0).toString(16).padStart(8, '0') + (h2 >>> 0).toString(16).padStart(8, '0'));
  }

  /** Apply a baked table to an ImageData-like RGBA byte array in place. */
  function applyToPixels(data, table, size) {
    const o = [0, 0, 0];
    for (let i = 0; i < data.length; i += 4) {
      sampleLut(table, size, data[i] / 255, data[i + 1] / 255, data[i + 2] / 255, o);
      data[i] = o[0] * 255 + 0.5; data[i + 1] = o[1] * 255 + 0.5; data[i + 2] = o[2] * 255 + 0.5;
    }
    return data;
  }

  const api = {
    LUT_SIZE, LUMA, newNode, newGrade, curveFn, isToneIdentity, wheelRgb, rgb2hsv, hsv2rgb, compileNode, sampleLut, bake, toCube, parseCube,
    isIdentity, isNodeIdentity, activeNodes, hashGrade, applyToPixels, tone0,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.NLEGrade = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
