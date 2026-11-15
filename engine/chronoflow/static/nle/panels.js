/* ChronoFlow Video Studio: draggable panel sizes. Left panel, right panel and timeline height, remembered per page.
   Drag a handle, or focus it and use the arrow keys (Shift = bigger steps); double-click resets that page's size. */
(function () {
  const KEY = 'cf.layout.v1', MIN_MONITOR = 360, GUT = 10;
  const VAR = { l: '--cf-l', r: '--cf-r', h: '--cf-tl' };
  // On the Color page the bottom divider sizes the grade panel (the clip strip there has a fixed height)
  const hVar = () => (page === 'color' ? '--cf-cp' : '--cf-tl');
  const hEl = () => document.querySelector(page === 'color' ? '#cfWorkspace .color-panel' : '#nleTimeline');
  const MIN = { l: 200, r: 240, h: 110 };
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { saved = {}; }
  let page = 'edit';
  const ws = () => document.getElementById('cfWorkspace');
  const row = () => document.querySelector('#cfWorkspace .davinci-top-row');

  function persist() { try { localStorage.setItem(KEY, JSON.stringify(saved)); } catch (e) { /* private mode: sizes just reset next time */ } }

  function cols() {   // current pixel widths of [left, right] read from the real grid
    const t = getComputedStyle(row()).gridTemplateColumns.split(' ').map(parseFloat);
    return t.length >= 5 ? { l: t[0], r: t[4] } : { l: t[0], r: t[t.length - 1] };
  }
  function limit(k) {   // the monitor always keeps MIN_MONITOR px (width) / 260 px (height)
    const w = ws().getBoundingClientRect(), c = cols();
    if (k === 'l') return Math.max(MIN.l, w.width - c.r - 2 * GUT - MIN_MONITOR);
    if (k === 'r') return Math.max(MIN.r, w.width - c.l - 2 * GUT - MIN_MONITOR);
    return Math.max(MIN.h, w.height - 260 - (page === 'color' ? 110 : 0));
  }
  const clamp = (k, v) => Math.round(Math.min(Math.max(v, MIN[k]), limit(k)));
  function size(k) { return k === 'h' ? hEl().getBoundingClientRect().height : cols()[k]; }
  const cssVar = (k) => (k === 'h' ? hVar() : VAR[k]);
  function set(k, v, remember) {
    v = clamp(k, v);
    ws().style.setProperty(cssVar(k), v + 'px');
    if (remember) { (saved[page] = saved[page] || {})[k] = v; persist(); }
    const h = document.querySelector(`[data-split="${k}"]`); if (h) h.setAttribute('aria-valuenow', v);
    window.dispatchEvent(new Event('resize'));   // the timeline and the player re-measure themselves on resize
  }
  function reset(k) { ws().style.removeProperty(cssVar(k)); if (saved[page]) { delete saved[page][k]; persist(); } window.dispatchEvent(new Event('resize')); }

  function apply(p) {
    page = p; const w = ws(); if (!w) return;
    [...Object.values(VAR), '--cf-cp'].forEach((v) => w.style.removeProperty(v));
    const o = saved[p] || {};
    ['l', 'r', 'h'].forEach((k) => { if (o[k]) set(k, o[k], false); });   // reading the grid forces layout, so no rAF (it never fires in a background tab)
  }

  function bind(handle) {
    const k = handle.dataset.split, dir = k === 'h' ? 'y' : 'x';
    handle.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      e.preventDefault(); handle.setPointerCapture(e.pointerId); handle.classList.add('drag'); document.body.classList.add('cf-resizing');
      const start = dir === 'x' ? e.clientX : e.clientY, from = size(k);
      const move = (ev) => {
        const d = (dir === 'x' ? ev.clientX : ev.clientY) - start;
        set(k, k === 'l' ? from + d : from - d, false);   // right panel and timeline grow when dragged left / up
      };
      const up = () => {
        handle.classList.remove('drag'); document.body.classList.remove('cf-resizing');
        handle.removeEventListener('pointermove', move); handle.removeEventListener('pointerup', up); handle.removeEventListener('pointercancel', up);
        (saved[page] = saved[page] || {})[k] = clamp(k, size(k)); persist();
      };
      handle.addEventListener('pointermove', move); handle.addEventListener('pointerup', up); handle.addEventListener('pointercancel', up);
    });
    handle.addEventListener('dblclick', () => reset(k));
    handle.addEventListener('keydown', (e) => {
      // the arrow moves the divider; the left panel grows with it, the right panel and the timeline shrink
      const move = (dir === 'x' ? { ArrowRight: 1, ArrowLeft: -1 } : { ArrowDown: 1, ArrowUp: -1 })[e.key];
      if (!move) return;
      e.preventDefault();
      set(k, size(k) + (k === 'l' ? move : -move) * (e.shiftKey ? 80 : 20), true);
    });
  }

  function init() {
    document.querySelectorAll('#cfWorkspace [data-split]').forEach(bind);
    let t; window.addEventListener('resize', () => { clearTimeout(t); t = setTimeout(() => { ['l', 'r', 'h'].forEach((k) => { const v = ws() && ws().style.getPropertyValue(cssVar(k)); if (v) set(k, parseFloat(v), false); }); }, 150); });
    apply(document.body.dataset.page || 'edit');
  }
  init();
  window.CFPanels = { apply, reset: (k) => reset(k) };
})();
