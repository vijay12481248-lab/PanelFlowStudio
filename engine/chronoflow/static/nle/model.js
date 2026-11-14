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
    return { fps: fps || 24, clips: [], overlays: [], markers: [], dismissedSrcs: [], inPoint: null, outPoint: null, nextId: 1 };
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
      prompt: spec.prompt || null, originalPrompt: spec.originalPrompt || spec.prompt || null,
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
    const [c] = tl.clips.splice(i, 1);
    if (tl) {
      if (!Array.isArray(tl.dismissedSrcs)) tl.dismissedSrcs = [];
      if (c && c.src && !tl.dismissedSrcs.includes(c.src)) tl.dismissedSrcs.push(c.src);
      if (c && Array.isArray(c.sources)) {
        c.sources.forEach((s) => {
          if (s && s.src && !tl.dismissedSrcs.includes(s.src)) tl.dismissedSrcs.push(s.src);
        });
      }
    }
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

  /** Merge multiple selected clips on track V1.
   * If contiguous slices of the same source video, joins them back into a single continuous take.
   * If distinct clips, consolidates them into a single continuous merged sequence clip.
   */
  function mergeClips(tl, clipIds) {
    if (!tl || !tl.clips || !clipIds || clipIds.length < 2) return null;
    const ids = new Set(clipIds);
    const matched = tl.clips.filter((c) => ids.has(c.id));
    if (matched.length < 2) return null;

    const firstIdx = tl.clips.indexOf(matched[0]);
    const lastIdx = tl.clips.indexOf(matched[matched.length - 1]);
    if (lastIdx - firstIdx + 1 !== matched.length) {
      // Must be adjacent clips on timeline
      return null;
    }

    const first = matched[0];
    const sameSrc = matched.every((c) => c.src === first.src);

    let mergedClip = null;
    if (sameSrc) {
      const minIn = Math.min(...matched.map((c) => c.in));
      const maxOut = Math.max(...matched.map((c) => c.out));
      mergedClip = {
        ...first,
        id: newId(tl, 'c'),
        in: minIn,
        out: maxOut,
        transition: 'cut',
      };
    } else {
      const totalDur = matched.reduce((acc, c) => acc + (c.out - c.in) / (c.speed || 1), 0);
      const labels = matched.map((c) => c.label.replace(/^Shot\s*/i, '#')).join(' + ');
      mergedClip = {
        id: newId(tl, 'c'),
        src: first.src,
        sources: matched.map((c) => ({ src: c.src, in: c.in, out: c.out, speed: c.speed || 1 })),
        label: `Merged (${labels})`,
        srcDur: totalDur,
        in: 0,
        out: totalDur,
        speed: 1,
        volume: first.volume == null ? 1 : first.volume,
        shot: first.shot != null ? first.shot : 0,
        version: 0,
        prompt: matched.map((c) => c.prompt).filter(Boolean).join('\n---\n') || first.prompt,
        originalPrompt: first.originalPrompt || first.prompt,
      };
    }

    tl.clips.splice(firstIdx, matched.length, mergedClip);
    return mergedClip;
  }

  /** Merge multiple selected frame overlays on track V2. */
  function mergeOverlays(tl, ovlIds) {
    if (!tl || !tl.overlays || !ovlIds || ovlIds.length < 2) return null;
    const ids = new Set(ovlIds);
    const matched = tl.overlays.filter((o) => ids.has(o.id));
    if (matched.length < 2) return null;

    const minStart = Math.min(...matched.map((o) => o.start));
    const maxEnd = Math.max(...matched.map((o) => o.start + o.dur));
    const first = matched[0];

    const mergedOvl = {
      id: newId(tl, 'o'),
      src: first.src,
      label: `Merged frames (${matched.length})`,
      start: minStart,
      dur: r6(maxEnd - minStart),
    };

    tl.overlays = tl.overlays.filter((o) => !ids.has(o.id));
    tl.overlays.push(mergedOvl);
    tl.overlays.sort((a, b) => a.start - b.start);
    return mergedOvl;
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

  /** Payload for POST /timeline/export (the server's EDL renderer).
      lutFor(clip) -> {id, cube} | null supplies a colour grade as a baked 3D LUT; clips name it in "lut" and the cube text goes once into "luts".
      fusionFor(clip) -> ffmpeg filter string | null supplies node VFX filters (blur, vignette, text, transform, shake, etc.). */
  function toEdl(tl, lutFor, fusionFor) {
    const clips = [], luts = {};
    const lutOf = (c) => { const g = lutFor ? lutFor(c) : null; if (!g) return {}; luts[g.id] = g.cube; return { lut: g.id }; };
    const fusionOf = (c) => {
      if (fusionFor) {
        const f = fusionFor(c);
        if (f) return { fusion_filter: f };
      }
      if (typeof window !== 'undefined' && window.NLEFusionGraph && c.fusion && !window.NLEFusionGraph.isIdentity(c.fusion)) {
        const f = window.NLEFusionGraph.toFfmpegFilter(c.fusion);
        if (f) return { fusion_filter: f };
      }
      return {};
    };
    tl.clips.forEach((c) => {
      const lut = lutOf(c);
      const fx = fusionOf(c);
      if (c.sources && c.sources.length) {
        c.sources.forEach((s) => {
          clips.push({ filename: s.src, in_point: s.in, out_point: s.out, speed: s.speed || 1, volume: c.volume, transition: 'cut', ...lut, ...fx });
        });
      } else {
        clips.push({ filename: c.src, in_point: c.in, out_point: c.out, speed: c.speed, volume: c.volume, transition: c.transition || 'cut', trans_dur: c.transDur || DEFAULT_TRANS, ...lut, ...fx });
      }
    });
    return {
      clips: clips,
      overlays: tl.overlays.map((o) => ({ filename: o.src, start: o.start, duration: o.dur })),
      luts: luts,
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
    removeClip, setSpeed, setVolume, duplicateClip, mergeClips, mergeOverlays, snapPoints, snap, neighbour, addOverlay, updateOverlay, removeOverlay,
    addMarker, removeMarker, toTimecode, toEdl, createHistory,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.NLEModel = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
