/* ChronoFlow Audio page - pure logic (no DOM): time <-> pixels, frame snapping, where a cue block sits, drag maths, gains, drift, status chips.
   Everything is in seconds. Kept free of the DOM so it can be tested with `node --test tests/js/audio_model.test.js`. */
(function (root) {
  'use strict';

  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const r6 = (v) => Math.round(v * 1e6) / 1e6;
  const LANES = [
    { id: 'dialogue', label: 'DX', stem: 'dialogue' }, { id: 'music', label: 'MX', stem: 'music' }, { id: 'sfx', label: 'SFX', stem: 'effects' },
    { id: 'ambience', label: 'AMB', stem: 'effects' }, { id: 'foley', label: 'FOL', stem: 'effects' },
  ];
  const STEMS = ['dialogue', 'music', 'effects'];
  const stemOf = (track) => (track === 'dialogue' ? 'dialogue' : track === 'music' ? 'music' : 'effects');

  /** hh:mm:ss:ff, non-drop at the nominal frame rate (29.97 counts 30 frames a second). */
  function fmtTC(t, fps) {
    const frames = Math.round(Math.max(0, t) * fps), nom = Math.round(fps) || 24, p = (n) => String(n).padStart(2, '0');
    const s = Math.floor(frames / nom);
    return `${p(Math.floor(s / 3600))}:${p(Math.floor(s / 60) % 60)}:${p(s % 60)}:${p(frames % nom)}`;
  }
  const snapFrame = (t, fps) => Math.round(t * fps) / fps;

  // view = { t0, pps }: the time at the left edge and pixels per second
  const timeToX = (t, v) => (t - v.t0) * v.pps;
  const xToTime = (x, v) => v.t0 + x / v.pps;
  function zoomAt(v, factor, anchorT, lim) {
    const pps = clamp(v.pps * factor, lim.minPps, lim.maxPps);
    return { t0: Math.max(0, anchorT - (anchorT - v.t0) * v.pps / pps), pps };
  }

  function rulerStep(pps, fps) {
    const steps = [1 / fps, 2 / fps, 5 / fps, 10 / fps, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600];
    return steps.find((s) => s * pps >= 60) || 600;
  }
  function rulerTicks(v, width, fps) {
    const step = rulerStep(v.pps, fps), end = v.t0 + width / v.pps, out = [], minor = step / 4;
    for (let k = Math.ceil(v.t0 / minor - 1e-9); k * minor <= end + 1e-9; k++) {
      const t = r6(k * minor) + 0; // + 0 turns -0 into 0
      out.push({ t, major: Math.abs(t / step - Math.round(t / step)) < 1e-6 });
    }
    return out;
  }

  const chosenTake = (cue) => (cue.takes || []).find((t) => t.id === cue.chosen_take) || null;

  /** Where a cue's block sits on its lane: {start, end}. A hit cue starts "anchor seconds" before its hit (trimmed at 0). */
  function cueSpan(cue) {
    const take = chosenTake(cue);
    if (cue.t_out != null) return { start: cue.t_in || 0, end: cue.t_out };
    if (cue.hit_t != null) {
      if (!take) return { start: cue.hit_t, end: r6(cue.hit_t + 0.4) };
      const off = cue.anchor === 'peak' ? take.peak_s : take.onset_s, raw = cue.hit_t - off, start = Math.max(0, raw);
      return { start: r6(start), end: r6(start + take.duration_s - (start - raw)) };
    }
    const s = cue.t_in || 0;
    return { start: s, end: r6(s + (take ? take.duration_s : 1)) };
  }

  /** The patch to send to put_plan after dragging a cue block dt seconds. Frame-snapped; a hit snaps to a picture cut within tol seconds. */
  function dragCue(cue, dt, plan, cuts, tol) {
    if (cue.hit_t != null) {
      const raw = cue.hit_t + dt, cut = (cuts || []).reduce((b, c) => (Math.abs(c - raw) <= tol && (b == null || Math.abs(c - raw) < Math.abs(b - raw)) ? c : b), null);
      return { hit_t: r6(clamp(cut != null ? cut : snapFrame(raw, plan.fps), 0, plan.duration)) };
    }
    const len = cue.t_out != null ? cue.t_out - (cue.t_in || 0) : 0, t_in = r6(clamp(snapFrame((cue.t_in || 0) + dt, plan.fps), 0, Math.max(0, plan.duration - len)));
    return cue.t_out != null ? { t_in, t_out: r6(t_in + len) } : { t_in };
  }

  const dbToGain = (db) => Math.pow(10, db / 20);
  const gainToDb = (g) => (g <= 0 ? -Infinity : 20 * Math.log10(g));

  /** Linear gain per stem for the preview. Solo wins: with any solo, only the soloed stems are heard. */
  function effectiveGains(gainsDb, mute, solo) {
    const out = {};
    for (const s of STEMS) {
      const audible = solo.size ? solo.has(s) : !mute.has(s);
      out[s] = audible ? dbToGain((gainsDb && gainsDb[s]) || 0) : 0;
    }
    return out;
  }

  /** null when a stem is close enough to the video clock, otherwise the time to seek it to. */
  const driftAction = (videoT, audioT, tol) => (Math.abs(videoT - audioT) <= (tol == null ? 0.06 : tol) ? null : videoT);

  function statusChip(cue) {
    const e = cue.placement_error_ms;
    switch (cue.status) {
      case 'needs_pick': return { text: 'pick one', tone: 'warn' };
      case 'failed': return { text: 'failed', tone: 'bad' };
      case 'ready':
        if (e > 40) return { text: `ready · ${Math.round(e)} ms`, tone: 'bad' };
        if (e > 20) return { text: `ready · ${Math.round(e)} ms`, tone: 'warn' };
        return { text: 'ready', tone: 'ok' };
      default: return { text: 'draft', tone: 'muted' };
    }
  }

  /** `width` bars from a peaks array (0..1 per bin) over the slice [from, to] of it (fractions). */
  function peaksToBars(peaks, width, from, to) {
    const out = new Array(width).fill(0), n = peaks.length;
    if (!n) return out;
    for (let i = 0; i < width; i++) {
      const a = Math.floor((from + (to - from) * i / width) * n), b = Math.max(a + 1, Math.ceil((from + (to - from) * (i + 1) / width) * n));
      let m = 0;
      for (let k = Math.max(0, a); k < Math.min(n, b); k++) if (peaks[k] > m) m = peaks[k];
      out[i] = m;
    }
    return out;
  }

  const needsRefresh = (seen, current) => seen == null || current > seen;

  const api = { LANES, STEMS, stemOf, fmtTC, snapFrame, timeToX, xToTime, zoomAt, rulerStep, rulerTicks, chosenTake, cueSpan, dragCue, dbToGain, gainToDb,
    effectiveGains, driftAction, statusChip, peaksToBars, needsRefresh };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.AudioModel = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
