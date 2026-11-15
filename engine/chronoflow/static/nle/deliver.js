/* ChronoFlow Deliver page - render settings (left), render queue (right), on the same timeline and monitor as Edit.
   "Add to Render Queue" sends the timeline (cuts, transitions, colour grades, Fusion effects) to the engine's Deliver queue
   (engine/chronoflow/deliver.py), which makes the master and then one final encode with these settings. */
(function () {
  'use strict';
  const LS = 'nle:deliver:v1';
  const RES = [['0x0', 'Match timeline'], ['1920x1080', '1080p (1920×1080)'], ['3840x2160', '4K UHD (3840×2160)'], ['2560x1440', '1440p (2560×1440)'], ['1280x720', '720p (1280×720)'],
    ['1080x1920', 'Vertical (1080×1920)'], ['1080x1080', 'Square (1080×1080)'], ['custom', 'Custom size…']];
  const CODECS = [['h264', 'H.264 · MP4'], ['h265', 'H.265 (HEVC) · MP4'], ['prores', 'ProRes 422 · MOV'], ['vp9', 'VP9 · WebM']];
  const PRORES = ['Proxy', 'LT', '422', '422 HQ', '4444', '4444 XQ'];
  const QDEF = { h264: 18, h265: 24, vp9: 32, prores: 2 };
  const QRANGE = { h264: [10, 36], h265: [14, 40], vp9: [20, 50], prores: [0, 5] };
  const S = { open: false, presets: [], nvenc: false, renders: [], busy: false, st: null, timer: 0, error: '' };
  let N = null, el = {}, controls = [];

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
  const api = (p, opt) => fetch(`${N.cfg.api}${p}`, opt).then(async (r) => { const d = await r.json().catch(() => ({})); if (!r.ok) throw new Error(d.detail || d.error || `HTTP ${r.status}`); return d; });
  const fmtT = (s) => { s = Math.max(0, Math.round(s)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };
  const fmtSize = (b) => (b > 1e9 ? `${(b / 1e9).toFixed(2)} GB` : `${(b / 1e6).toFixed(1)} MB`);
  const stamp = () => { const d = new Date(), p = (n) => String(n).padStart(2, '0'); return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`; };

  // ---------- settings state (remembered between sessions) ----------
  const DEFAULTS = { preset: 'youtube_1080p', name: '', range: 'all', codec: 'h264', encoder: 'cpu', res: '1920x1080', cw: 1920, ch: 1080, fit: 'fit', fps: 0, quality: 18, bitrate_k: 0,
    audio: true, audio_kbps: 192, sample_rate: 48000, loudness: -14 };
  function load() { try { return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(LS) || '{}') }; } catch (e) { return { ...DEFAULTS }; } }
  const save = () => { try { localStorage.setItem(LS, JSON.stringify(S.st)); } catch (e) { /* private mode */ } };
  const resKey = (w, hh) => { const k = `${w}x${hh}`; return RES.some((r) => r[0] === k) ? k : 'custom'; };
  function applyPreset(p) {
    const s = p.settings;
    Object.assign(S.st, { preset: p.id, codec: s.codec, res: resKey(s.width, s.height), cw: s.width || S.st.cw, ch: s.height || S.st.ch, fit: s.fit, fps: s.fps, quality: s.quality, loudness: s.loudness, bitrate_k: 0 });
    if (S.st.encoder === 'nvenc' && !['h264', 'h265'].includes(s.codec)) S.st.encoder = 'cpu';
    save(); renderSettings();
  }
  function request() {
    const s = S.st, tl = N.tl, [w, hh] = s.res === 'custom' ? [+s.cw, +s.ch] : s.res.split('x').map(Number);
    const out = { preset: s.preset, name: s.name || defaultName(), codec: s.codec, encoder: s.encoder, width: w, height: hh, fit: s.fit, fps: +s.fps, quality: +s.quality, bitrate_k: +s.bitrate_k || 0,
      audio: s.audio, audio_kbps: +s.audio_kbps, sample_rate: +s.sample_rate, loudness: s.loudness, range_in: null, range_out: null };
    if (s.range === 'marks') { out.range_in = tl.inPoint == null ? 0 : tl.inPoint; out.range_out = tl.outPoint == null ? null : tl.outPoint; }
    return out;
  }
  const defaultName = () => {
    const sel = document.getElementById('projectJobSelect'), t = sel && sel.selectedOptions[0] ? sel.selectedOptions[0].textContent : '';
    const title = t.replace(/\(.*$/, '').replace(/^[^\w]+/, '').replace(/^[0-9a-f]{8}:\s*/i, '').replace(/[^\w\- ]+/g, ' ').trim().slice(0, 40).trim() || 'chronoflow';
    return `${title}_${stamp()}`.replace(/\s+/g, '_');
  };

  // ---------- form building ----------
  const field = (label, ctl, hint) => h('label', { class: 'dl-field' }, h('span', { class: 'dl-lab' }, label), ctl, hint ? h('span', { class: 'dl-hint' }, hint) : null);
  function select(key, options, onchange) {
    const sel = h('select', { class: 'dl-in' }, options.map(([v, t, dis]) => h('option', { value: v, disabled: !!dis }, t)));
    sel.value = String(S.st[key]);
    sel.addEventListener('change', () => { S.st[key] = isNaN(+sel.value) || sel.value === '' ? sel.value : (key === 'res' ? sel.value : +sel.value); if (key === 'loudness' && sel.value === 'off') S.st[key] = null; save(); if (onchange) onchange(); else summary(); });
    return sel;
  }
  function renderSettings() {
    const s = S.st, box = el.settings;
    const marks = N.tl.inPoint != null || N.tl.outPoint != null;
    const total = N.total(), a = N.tl.inPoint == null ? 0 : N.tl.inPoint, b = N.tl.outPoint == null ? total : N.tl.outPoint;
    const q = QRANGE[s.codec], isPro = s.codec === 'prores';
    const quality = h('input', { type: 'range', min: q[0], max: q[1], step: 1, value: s.quality, oninput: (e) => { s.quality = +e.target.value; qv.textContent = qLabel(); save(); summary(); } });
    const qLabel = () => (isPro ? PRORES[s.quality] : `CRF ${s.quality}`);
    const qv = h('span', { class: 'dl-qv' }, qLabel());
    box.textContent = '';
    box.append(
      h('div', { class: 'dl-head' }, h('b', {}, 'Render settings')),
      h('div', { class: 'dl-scroll' },
        h('div', { class: 'dl-presets' }, S.presets.map((p) => h('button', { class: `dl-preset${s.preset === p.id ? ' on' : ''}`, title: p.note, onclick: () => applyPreset(p) }, p.name))),
        field('File name', h('input', { class: 'dl-in', type: 'text', value: s.name, placeholder: defaultName(), maxlength: 80, oninput: (e) => { s.name = e.target.value; save(); } }), 'Saved in output/chronoflow/deliver'),
        h('div', { class: 'dl-field' }, h('span', { class: 'dl-lab' }, 'Render range'),
          h('div', { class: 'dl-radios' },
            h('label', {}, h('input', { type: 'radio', name: 'dlrange', checked: s.range !== 'marks' || !marks, onchange: () => { s.range = 'all'; save(); summary(); } }), ` Entire timeline (${fmtT(total)})`),
            h('label', { class: marks ? '' : 'dim', title: marks ? '' : 'Set In/Out marks on the timeline (I and O keys) first' },
              h('input', { type: 'radio', name: 'dlrange', disabled: !marks, checked: s.range === 'marks' && marks, onchange: () => { s.range = 'marks'; save(); summary(); } }), ` In to Out marks (${fmtT(a)} to ${fmtT(b)})`))),
        h('div', { class: 'dl-sub' }, 'Video'),
        field('Format', select('codec', CODECS, () => { s.quality = QDEF[s.codec]; if (!['h264', 'h265'].includes(s.codec)) s.encoder = 'cpu'; s.preset = ''; save(); renderSettings(); })),
        field('Encoder', select('encoder', [['cpu', 'CPU (best quality per size)'], ['nvenc', S.nvenc ? 'NVIDIA NVENC (fast, uses the GPU)' : 'NVIDIA NVENC (not found)', !S.nvenc || !['h264', 'h265'].includes(s.codec)]]),
          s.encoder === 'nvenc' ? 'The GPU is shared with ComfyUI and Ollama.' : null),
        field('Resolution', select('res', RES, () => { s.preset = ''; save(); renderSettings(); })),
        s.res === 'custom' ? h('div', { class: 'dl-two' }, h('input', { class: 'dl-in', type: 'number', min: 160, max: 7680, step: 2, value: s.cw, oninput: (e) => { s.cw = +e.target.value; save(); summary(); } }), h('span', {}, '×'),
          h('input', { class: 'dl-in', type: 'number', min: 160, max: 7680, step: 2, value: s.ch, oninput: (e) => { s.ch = +e.target.value; save(); summary(); } })) : null,
        s.res !== '0x0' ? field('When the shape differs', select('fit', [['fit', 'Fit (black bars)'], ['fill', 'Fill (crop the edges)'], ['stretch', 'Stretch (distorts)']])) : null,
        field('Frame rate', select('fps', [[0, 'Keep the timeline\'s'], [23.976, '23.976'], [24, '24'], [25, '25'], [29.97, '29.97'], [30, '30'], [50, '50'], [59.94, '59.94'], [60, '60']])),
        field(isPro ? 'ProRes profile' : 'Quality', h('div', { class: 'dl-qrow' }, quality, qv), isPro ? null : 'Lower CRF = better picture, bigger file'),
        isPro ? null : field('Video bitrate (kbps, optional)', h('input', { class: 'dl-in', type: 'number', min: 0, max: 400000, step: 100, value: s.bitrate_k || '', placeholder: 'blank = use Quality', oninput: (e) => { s.bitrate_k = +e.target.value || 0; save(); summary(); } })),
        h('div', { class: 'dl-sub' }, 'Audio'),
        h('label', { class: 'dl-check' }, h('input', { type: 'checkbox', checked: s.audio, onchange: (e) => { s.audio = e.target.checked; save(); renderSettings(); } }), ' Include audio'),
        s.audio ? [field('Loudness', select('loudness', [['off', 'Off (keep the mix as it is)'], [-14, '−14 LUFS · YouTube / streaming'], [-16, '−16 LUFS · podcast / mobile'], [-23, '−23 LUFS · EBU R128 broadcast']]),
            s.loudness == null ? null : 'Measured, then adjusted; peaks limited to −1.5 dBTP'),
          s.codec === 'prores' ? null : field('Audio bitrate', select('audio_kbps', [[128, '128 kbps'], [192, '192 kbps'], [256, '256 kbps'], [320, '320 kbps']])),
          field('Sample rate', select('sample_rate', [[44100, '44.1 kHz'], [48000, '48 kHz']]))] : null),
      h('div', { class: 'dl-foot' }, el.summary = h('div', { class: 'dl-summary' }), el.error = h('div', { class: 'dl-error' }, S.error),
        el.add = h('button', { class: 'dl-btn accent', onclick: submit }, 'Add to Render Queue')));
    if (s.loudness == null) { const sel = box.querySelector('select option[value="off"]'); if (sel) sel.parentElement.value = 'off'; }
    summary();
  }
  function summary() {
    if (!el.summary) return;
    const s = S.st, [w, hh] = s.res === 'custom' ? [s.cw, s.ch] : s.res.split('x').map(Number), tl = N.tl;
    const len = s.range === 'marks' && (tl.inPoint != null || tl.outPoint != null) ? (tl.outPoint == null ? N.total() : tl.outPoint) - (tl.inPoint || 0) : N.total();
    const codec = (CODECS.find((c) => c[0] === s.codec) || [])[1] || s.codec;
    el.summary.textContent = `${w ? `${w}×${hh}` : 'timeline size'} · ${codec.split(' · ')[0]}${s.fps ? ` · ${s.fps} fps` : ''}${s.audio && s.loudness != null ? ` · ${s.loudness} LUFS` : ''} · ${fmtT(len)} long`;
    if (el.add) el.add.disabled = !N.tl.clips.length || S.busy;
  }

  async function submit() {
    S.error = ''; el.error.textContent = '';
    if (!N.tl.clips.length) return;
    const nodes = window.NLEColor ? window.NLEColor.gradedCount() : 0;
    S.busy = true; summary();
    try {
      const edl = window.NLEModel.toEdl(N.tl, window.NLEColor && window.NLEColor.lutFor);
      const rec = await api('/deliver/render', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ clips: edl.clips, overlays: edl.overlays, luts: edl.luts, settings: request() }) });
      say(`Queued "${rec.file}"${nodes ? ` (${nodes} graded clip${nodes === 1 ? '' : 's'})` : ''}.`);
      await refresh(); poll();
    } catch (err) { S.error = err.message; el.error.textContent = err.message; say(`Could not queue the render: ${err.message}`); }
    S.busy = false; summary();
  }

  // ---------- queue ----------
  const STAGE = { queued: 'Waiting', timeline: 'Rendering timeline', measuring: 'Measuring loudness', encoding: 'Encoding', done: 'Done', failed: 'Failed', cancelled: 'Cancelled' };
  function renderQueue() {
    const box = el.list; box.textContent = '';
    if (!S.renders.length) { box.append(h('div', { class: 'dl-hint', style: 'padding:10px' }, 'Nothing rendered yet. Choose a preset, check the settings, then "Add to Render Queue". Renders run one at a time; this list is kept between sessions.')); return; }
    S.renders.forEach((r) => {
      const active = r.status === 'queued' || r.status === 'rendering', s = r.settings || {};
      const meta = r.status === 'done' ? `${r.width}×${r.height} · ${fmtT(r.duration)} · ${fmtSize(r.size)}` : `${s.width ? `${s.width}×${s.height}` : 'timeline size'} · ${(s.codec || '').toUpperCase()}${s.loudness != null ? ` · ${s.loudness} LUFS` : ''}`;
      const took = r.started && r.finished ? ` · took ${fmtT(r.finished - r.started)}` : '';
      box.append(h('div', { class: `dl-card ${r.status}` },
        h('div', { class: 'dl-cardtop' }, h('b', { class: 'dl-file', title: r.path }, r.file), h('span', { class: `dl-chip ${r.status}` }, STAGE[r.stage] || r.status)),
        h('div', { class: 'dl-meta' }, meta + took), active ? h('div', { class: 'dl-bar' }, h('i', { style: `width:${Math.round((r.progress || 0) * 100)}%` })) : null,
        r.status === 'failed' ? h('div', { class: 'dl-error' }, r.error) : null,
        h('div', { class: 'dl-actions' },
          r.status === 'done' ? [h('a', { class: 'dl-btn accent', href: N.q(r.url), download: r.file }, '⤓ Download'), h('button', { class: 'dl-btn', title: r.path, onclick: () => copy(r.path) }, 'Copy path')] : null,
          active ? h('button', { class: 'dl-btn', onclick: () => api(`/deliver/render/${r.id}/cancel`, { method: 'POST' }).then(refresh).catch((e) => say(e.message)) }, 'Cancel') : null,
          !active ? h('button', { class: 'dl-x', title: 'Remove from the list and delete the file', onclick: () => { if (confirm(`Delete ${r.file}${r.status === 'done' ? ' from disk' : ''}? This cannot be undone.`)) api(`/deliver/render/${r.id}`, { method: 'DELETE' }).then(refresh).catch((e) => say(e.message)); } }, 'Delete') : null)));
    });
  }
  const copy = (t) => { try { navigator.clipboard.writeText(t); say('Path copied.'); } catch (e) { say(t); } };
  async function refresh() { try { S.renders = (await api('/deliver/renders')).renders; renderQueue(); } catch (e) { /* engine busy */ } }
  function poll() {
    clearTimeout(S.timer);
    if (!S.open) return;
    refresh().then(() => { S.timer = setTimeout(poll, S.renders.some((r) => r.status === 'queued' || r.status === 'rendering') ? 1200 : 6000); });
  }

  // ---------- mount / open / close ----------
  function mount() {
    N = window.NLE; if (!N || el.mounted) return;
    const wrap = document.querySelector('.davinci-nle-wrapper'); el.wrap = wrap;
    el.settings = document.getElementById('deliverSettings'); el.queue = document.getElementById('deliverQueue');
    if (!wrap || !el.settings || !el.queue) return;
    S.st = load();
    el.queue.append(h('div', { class: 'dl-head' }, h('b', {}, 'Render queue'), h('button', { class: 'dl-btn', onclick: refresh, title: 'Refresh' }, '⟳')), el.list = h('div', { class: 'dl-list' }));
    el.mounted = true;
    api('/deliver/presets').then((d) => { S.presets = d.presets; S.nvenc = d.nvenc; if (S.open) renderSettings(); }).catch(() => { /* retried on open */ });
  }
  function open() {
    if (!el.mounted) mount();
    if (!el.wrap) return;
    S.open = true; el.wrap.classList.add('is-deliver');
    const go = () => { renderSettings(); renderQueue(); poll(); };
    if (!S.presets.length) api('/deliver/presets').then((d) => { S.presets = d.presets; S.nvenc = d.nvenc; go(); }).catch((e) => { go(); say(`Deliver presets unavailable: ${e.message}`); }); else go();
  }
  function close() { if (!el.wrap || !S.open) return; S.open = false; el.wrap.classList.remove('is-deliver'); clearTimeout(S.timer); }

  window.NLEDeliver = { mount, open, close, get state() { return S; }, request };
})();
