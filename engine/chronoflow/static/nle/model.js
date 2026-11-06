/* ChronoFlow NLE - pure timeline model (no DOM). V1 is a gapless, ripple sequence of clips; V2 holds free-placed still overlays.
   Every time is in seconds; clip duration on the timeline = (out - in) / speed. */
(function (root) {
  'use strict';

  const TRANSITIONS = ['cut', 'dissolve', 'fadeblack'];
  const DEFAULT_TRANS = 0.5;
  const MIN_FRAMES = 2;               // a clip never gets shorter than this many frames
  const SPEED_MIN = 0.25, SPEED_MAX = 4;
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const r6 = (v) => Math.round(v * 1e6) / 1e6;

  function create(fps) {
    return { fps: fps || 24, clips: [], overlays: [], markers: [], inPoint: null, outPoint: null, nextId: 1 };
  }
  const newId = (tl, p) => `${p}${tl.nextId++}`;
  const clipDur = (c) => (c.out - c.in) / c.speed;
  const minDur = (tl) => MIN_FRAMES / tl.fps;
  const frame = (t, fps) => Math.round(t * fps) / fps;

  /** Seconds the clip at index i overlaps the one before it (a transition eats half of each neighbour at most). */
  function overlapAt(tl, i) {
    const c = tl.clips[i];
    if (!i || !c || !c.transition || c.transition === 'cut') return 0;
    return r6(Math.min(c.transDur || DEFAULT_TRANS, clipDur(tl.clips[i - 1]) / 2, clipDur(c) / 2));
  }

  /** Each clip starts where the previous one ends, minus its transition overlap. */
  function layout(tl) {
    let end = 0;
    return tl.clips.map((clip, i) => {
      const overlap = overlapAt(tl, i), start = i ? end - overlap : 0;
      end = start + clipDur(clip);
      return { clip, start: r6(start), end: r6(end), overlap };
    });
  }
  const total = (tl) => { const L = layout(tl); return L.length ? L[L.length - 1].end : 0; };

  /** Clip under time t (the incoming clip during a transition; the last clip owns its end frame).
      Returns {index, clip, start, end, srcTime, blend} or null. blend = {from, fromSrc, progress, kind} while a transition is running. */
  function locate(tl, t) {
    const L = layout(tl);
    for (let i = L.length - 1; i >= 0; i--) {
      const last = i === L.length - 1;
      if (t >= L[i].start && (t < L[i].end || (last && t <= L[i].end))) {
        const c = L[i].clip, hit = { index: i, clip: c, start: L[i].start, end: L[i].end, srcTime: c.in + (t - L[i].start) * c.speed, blend: null };
        if (L[i].overlap > 0 && t < L[i].start + L[i].overlap) {
          const p = L[i - 1].clip;
          hit.blend = { from: p, fromSrc: p.in + (t - L[i - 1].start) * p.speed, progress: (t - L[i].start) / L[i].overlap, kind: c.transition };
        }
        return hit;
      }
    }
    return null;
  }

  function addClip(tl, spec, index) {
    const dur = spec.srcDur || 5;
    const clip = {
      id: newId(tl, 'c'), src: spec.src, label: spec.label || spec.src, srcDur: dur,
      in: spec.in || 0, out: spec.out == null ? dur : spec.out, speed: spec.speed || 1, volume: spec.volume == null ? 1 : spec.volume,
      shot: spec.shot == null ? null : spec.shot, version: spec.version || 0,
    };
    tl.clips.splice(index == null ? tl.clips.length : index, 0, clip);
    return clip;
  }
  const byId = (tl, id) => tl.clips.find((c) => c.id === id) || null;

  /** Blade: cut the clip under t into two. Returns {left, right} or null when t is on/too near an edge. */
  function splitAt(tl, t) {
    const hit = locate(tl, t);
    if (!hit) return null;
    const edge = minDur(tl);
    if (t - hit.start < edge || hit.end - t < edge) return null;
    const cut = r6(hit.srcTime);
    const right = { ...hit.clip, id: newId(tl, 'c'), in: cut, transition: 'cut' };   // two halves of one take join without a transition
    hit.clip.out = cut;
    tl.clips.splice(hit.index + 1, 0, right);
    return { left: hit.clip, right };
  }

  /** Ripple-trim one edge of a clip to a source time. */
  function trimEdge(tl, id, edge, srcTime) {
    const c = byId(tl, id);
    if (!c) return null;
    const gap = minDur(tl) * c.speed;
    if (edge === 'in') c.in = r6(clamp(srcTime, 0, c.out - gap));
    else c.out = r6(clamp(srcTime, c.in + gap, c.srcDur));
    return c;
  }

  function moveClip(tl, id, toIndex) {
    const from = tl.clips.findIndex((c) => c.id === id);
    if (from < 0) return false;
    const [c] = tl.clips.splice(from, 1);
    tl.clips.splice(clamp(toIndex, 0, tl.clips.length), 0, c);
    return true;
  }

  function removeClip(tl, id) {
    const i = tl.clips.findIndex((c) => c.id === id);
    if (i < 0) return false;
    tl.clips.splice(i, 1);
    return true;
  }

  function setTransition(tl, id, kind, dur) {
    const c = byId(tl, id);
    if (!c || !TRANSITIONS.includes(kind)) return null;
    c.transition = kind;
    if (dur != null) c.transDur = clamp(+dur || DEFAULT_TRANS, 0.1, 3);
    return c;
  }
  const setSpeed = (tl, id, v) => { const c = byId(tl, id); if (c) c.speed = clamp(+v || 1, SPEED_MIN, SPEED_MAX); return c; };
  const setVolume = (tl, id, v) => { const c = byId(tl, id); if (c) c.volume = clamp(+v, 0, 2); return c; };

  function duplicateClip(tl, id) {
    const i = tl.clips.findIndex((c) => c.id === id);
    if (i < 0) return null;
    const copy = { ...tl.clips[i], id: newId(tl, 'c') };
    tl.clips.splice(i + 1, 0, copy);
    return copy;
  }

  /** Sorted unique edit points (clip edges, markers, in/out) for magnetic snapping. */
  function snapPoints(tl, extra) {
    const pts = new Set([0]);
    layout(tl).forEach((l) => { pts.add(l.start); pts.add(l.end); });
    tl.overlays.forEach((o) => { pts.add(o.start); pts.add(r6(o.start + o.dur)); });
    tl.markers.forEach((m) => pts.add(m.t));
    if (tl.inPoint != null) pts.add(tl.inPoint);
    if (tl.outPoint != null) pts.add(tl.outPoint);
    (extra || []).forEach((p) => pts.add(p));
    return [...pts].sort((a, b) => a - b);
  }
  function snap(t, points, tol) {
    let best = t, bestD = tol;
    for (const p of points) { const d = Math.abs(p - t); if (d <= bestD) { best = p; bestD = d; } }
    return best;
  }

  /** Previous / next edit point around t (for Up/Down arrow jumps). */
  function neighbour(tl, t, dir) {
    const pts = snapPoints(tl);
    const eps = 1e-4;
    return dir < 0 ? [...pts].reverse().find((p) => p < t - eps) ?? 0 : pts.find((p) => p > t + eps) ?? total(tl);
  }

  function addOverlay(tl, spec) {
    const o = { id: newId(tl, 'o'), src: spec.src, label: spec.label || 'Edited frame', start: r6(spec.start), dur: Math.max(minDur(tl), spec.dur || 1) };
    tl.overlays.push(o);
    return o;
  }
  function updateOverlay(tl, id, patch) {
    const o = tl.overlays.find((x) => x.id === id);
    if (!o) return null;
    if (patch.start != null) o.start = r6(Math.max(0, patch.start));
    if (patch.dur != null) o.dur = r6(Math.max(minDur(tl), patch.dur));
    return o;
  }
  const removeOverlay = (tl, id) => { const n = tl.overlays.length; tl.overlays = tl.overlays.filter((o) => o.id !== id); return tl.overlays.length < n; };

  function addMarker(tl, t, label) {
    const m = { id: newId(tl, 'm'), t: r6(t), label: label || '' };
    tl.markers.push(m);
    tl.markers.sort((a, b) => a.t - b.t);
    return m;
  }
  const removeMarker = (tl, id) => { const n = tl.markers.length; tl.markers = tl.markers.filter((m) => m.id !== id); return tl.markers.length < n; };

  function toTimecode(t, fps) {
    const f = Math.round(Math.max(0, t) * fps);
    const ff = f % Math.round(fps), s = Math.floor(f / fps);
    const p = (n) => String(n).padStart(2, '0');
    return `${p(Math.floor(s / 3600))}:${p(Math.floor((s % 3600) / 60))}:${p(s % 60)}:${p(ff)}`;
  }

  /** Payload for POST /timeline/export (the server's EDL renderer). */
  function toEdl(tl) {
    return {
      clips: tl.clips.map((c) => ({ filename: c.src, in_point: c.in, out_point: c.out, speed: c.speed, volume: c.volume, transition: c.transition || 'cut', trans_dur: c.transDur || DEFAULT_TRANS })),
      overlays: tl.overlays.map((o) => ({ filename: o.src, start: o.start, duration: o.dur })),
    };
  }

  /** Snapshot undo/redo that restores into the same timeline object. */
  function createHistory(tl, limit) {
    const max = limit || 100;
    let past = [], future = [];
    const snap0 = () => JSON.stringify(tl);
    const restore = (s) => { const next = JSON.parse(s); Object.keys(tl).forEach((k) => delete tl[k]); Object.assign(tl, next); };
    return {
      checkpoint() { past.push(snap0()); if (past.length > max) past.shift(); future = []; },
      undo() { if (!past.length) return false; future.push(snap0()); restore(past.pop()); return true; },
      redo() { if (!future.length) return false; past.push(snap0()); restore(future.pop()); return true; },
      reset() { past = []; future = []; },
      get canUndo() { return past.length > 0; },
      get canRedo() { return future.length > 0; },
    };
  }

  const api = {
    SPEED_MIN, SPEED_MAX, TRANSITIONS, DEFAULT_TRANS, overlapAt, setTransition, create, clipDur, minDur, frame, layout, total, locate, addClip, byId, splitAt, trimEdge, moveClip,
    removeClip, setSpeed, setVolume, duplicateClip, snapPoints, snap, neighbour, addOverlay, updateOverlay, removeOverlay,
    addMarker, removeMarker, toTimecode, toEdl, createHistory,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.NLEModel = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
