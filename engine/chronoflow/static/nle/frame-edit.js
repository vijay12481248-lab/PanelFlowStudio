/* ChronoFlow NLE - Magic Brush (paint on the paused frame) and the prompt bar under the player.
   Flow: capture the paused frame -> inpaint the painted region (or generate a whole new image) -> pick a candidate -> merge into the timeline. */
(function () {
  'use strict';
  let nle = null, mount = null;
  const S = { mode: 'frame', customRef: null, brushing: false, busy: false, base: null, size: 40, erase: false, strength: 0.85, cands: [], sel: null, mergeMode: 'hold', down: false, last: null, hasMask: false };
  let maskCv = null, viewCv = null, ring = null;      // offscreen mask (frame resolution) and the visible overlay canvas
  const $ = (s, r) => (r || mount).querySelector(s);

  const post = async (path, body) => {
    let base = (nle && nle.cfg && nle.cfg.api) ? nle.cfg.api : '/api';
    let cleanPath = path.startsWith('/') ? path : '/' + path;
    if (cleanPath.startsWith('/api/') && (base.endsWith('/api') || base.endsWith('/api/chronoflow'))) {
      cleanPath = cleanPath.slice(4);
    }
    const fullUrl = `${base.replace(/\/+$/, '')}/${cleanPath.replace(/^\/+/, '')}`;
    const res = await fetch(fullUrl, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.success === false) throw new Error(data.detail || data.error || `HTTP ${res.status}`);
    return data;
  };
  const say = (m) => nle.status(m);

  function buildBar() {
    mount.innerHTML = `
      <input type="file" id="feFileInput" accept="image/*" style="display:none">
      <div class="nle-framebar">
        <div class="nle-fb-top">
          <div class="nle-fb-modes">
            <button class="nle-btn ${S.mode === 'frame' ? 'on' : ''}" id="feModeFrame" title="Edit or regenerate frame X at current playhead">● Frame (Playhead X)</button>
            <button class="nle-btn ${S.mode === 'range' ? 'on' : ''}" id="feModeRange" title="Regenerate clip across timeline range [X → Y] via In/Out markers">⟷ Range [X → Y]</button>
          </div>
          <div class="nle-fb-range" id="feRangeInfo">
            <button class="nle-btn" id="feMarkIn" title="Set In point [I] at playhead">[I] In</button>
            <input type="number" id="feInInput" min="0" step="0.1" value="0.0" style="width:58px;background:#050816;color:#eef1ff;border:1px solid #222d5e;border-radius:3px;padding:2px 4px;font-family:monospace;font-size:0.75rem;text-align:center;" title="In point in seconds (editable)">
            <span>&rarr;</span>
            <button class="nle-btn" id="feMarkOut" title="Set Out point [O] at playhead">[O] Out</button>
            <input type="number" id="feOutInput" min="0" step="0.1" value="10.0" style="width:58px;background:#050816;color:#eef1ff;border:1px solid #222d5e;border-radius:3px;padding:2px 4px;font-family:monospace;font-size:0.75rem;text-align:center;" title="Out point in seconds (editable)">
            <small>(<b id="feDurText" style="color:#7aa2ff">10.0s</b>)</small>
            <button class="nle-btn" id="feClearRange" title="Clear In/Out range (Reset to full video) [Alt+X]">✕</button>
          </div>
        </div>
        <div class="nle-fb-main">
          <div class="thumb" id="feThumb" title="Click to upload reference image or reset to playhead snapshot">
            <span class="thumb-badge" id="feThumbBadge">Playhead</span>
          </div>
          <div style="flex:1; display:flex; flex-direction:column; gap:4px; min-width:0;">
            <div style="display:flex; justify-content:space-between; align-items:center; padding:0 2px;">
              <span id="feClipPromptBadge" style="font-size:0.75rem; color:#9aa6d0; font-weight:600;"><span id="feClipName" style="color:#7aa2ff;">Selected Clip</span> Prompt <small style="color:#6a76a3;">(original generation prompt)</small>:</span>
              <div style="display:flex; gap:6px; align-items:center;">
                <button class="nle-btn" id="feAutoPromptBtn" style="font-size:0.7rem; padding:1px 8px; height:20px; line-height:18px; color:#a9c1ff; border-color:rgba(252,211,77,0.4);" title="Analyze visual scene in range [X → Y] and auto-generate prompt incorporating your adjustments">⚡ Auto-Gen Prompt</button>
                <button class="nle-btn" id="feResetPromptBtn" style="font-size:0.7rem; padding:1px 6px; height:20px; line-height:18px;" title="Reset back to original generation prompt">↺ Reset Original</button>
              </div>
            </div>
            <textarea id="fePrompt" style="width:100%; min-height:56px;" placeholder="Describe action, modifications, or guide prompt for this frame or range… (Ctrl+Enter)"></textarea>
          </div>
          <div class="col">
            <button class="nle-btn accent" id="feGo">✨ Regen Frame</button>
            <button class="nle-btn" id="feBrushBtn" title="Magic Brush: paint region to inpaint on frame">🖌 Magic Brush</button>
          </div>
        </div>
      </div>
      <div class="nle-resrow" id="feResRow"><div class="nle-cands" id="feCands"></div><div class="nle-merge" id="feMerge"></div></div>
      <div class="nle-status" id="feStatus" style="display:none"></div>`;

    bindBarEvents();
    updateRangeDisplay();
  }

  let activePromptClipId = null;
  const userClipPrompts = {};

  function syncClipPrompt(force = false) {
    if (!nle) return;
    const tl = nle.tl || (nle.timeline ? nle.timeline() : null);
    if (!tl || !tl.clips || !tl.clips.length) return;

    let clip = null;
    if (typeof nle.selectedClip === 'function') clip = nle.selectedClip();
    if (!clip && typeof nle.clipAtPlayhead === 'function') {
      const hit = nle.clipAtPlayhead();
      if (hit && hit.clip) clip = hit.clip;
    }
    if (!clip && tl.clips.length) clip = tl.clips[0];
    if (!clip) return;

    const clipNameEl = $('#feClipName');
    if (clipNameEl) {
      clipNameEl.textContent = clip.label || 'Selected Clip';
    }

    const fePrompt = $('#fePrompt');
    if (!fePrompt) return;

    let origPrompt = clip.prompt || clip.originalPrompt || '';
    if (!origPrompt && nle.ui && nle.ui.job) {
      const job = nle.ui.job;
      const shotIdx = clip.shot != null ? clip.shot : 0;
      if (job.chunk_prompts && job.chunk_prompts[shotIdx]) origPrompt = job.chunk_prompts[shotIdx];
      else if (job.scenes && job.scenes[shotIdx] && job.scenes[shotIdx].prompt) origPrompt = job.scenes[shotIdx].prompt;
      else if (job.plan && job.plan.shots && job.plan.shots[shotIdx] && job.plan.shots[shotIdx].prompt) origPrompt = job.plan.shots[shotIdx].prompt;
      else if (job.prompt) origPrompt = shotIdx === 0 ? job.prompt : `${job.prompt} [continuation sequence ${shotIdx + 1}, fluid motion]`;
      clip.prompt = origPrompt;
      clip.originalPrompt = origPrompt;
    }

    const shouldUpdate = force || (activePromptClipId !== clip.id) || (!fePrompt.value && origPrompt);

    if (shouldUpdate) {
      activePromptClipId = clip.id;
      if (document.activeElement !== fePrompt || force) {
        const val = (userClipPrompts[clip.id] !== undefined && userClipPrompts[clip.id] !== '')
          ? userClipPrompts[clip.id]
          : origPrompt;
        fePrompt.value = val;
      }
    }
  }

  function updateRangeDisplay() {
    const inInput = $('#feInInput'), outInput = $('#feOutInput'), durEl = $('#feDurText');
    if (!inInput || !outInput || !nle) return;
    const tl = nle.tl || (nle.timeline ? nle.timeline() : null);
    if (!tl) return;
    const tot = typeof nle.total === 'function' ? nle.total() : (tl.clips && tl.clips.length ? window.NLEModel.total(tl) : 10);
    const inP = (tl.inPoint != null) ? tl.inPoint : 0;
    const outP = (tl.outPoint != null) ? tl.outPoint : tot;
    const d0 = Math.min(inP, outP), d1 = Math.max(inP, outP);

    if (document.activeElement !== inInput) inInput.value = d0.toFixed(1);
    if (document.activeElement !== outInput) outInput.value = d1.toFixed(1);
    if (durEl) durEl.textContent = `${(d1 - d0).toFixed(1)}s`;
  }

  function bindBarEvents() {
    const feFileInput = $('#feFileInput');
    const feThumb = $('#feThumb');
    const feThumbBadge = $('#feThumbBadge');
    const feModeFrame = $('#feModeFrame');
    const feModeRange = $('#feModeRange');
    const feGo = $('#feGo');
    const fePrompt = $('#fePrompt');

    feModeFrame.onclick = () => {
      S.mode = 'frame';
      feModeFrame.classList.add('on'); feModeRange.classList.remove('on');
      feGo.textContent = '✨ Regen Frame';
      fePrompt.placeholder = 'Describe what this frame should show, action changes, or inpainting prompt… (Ctrl+Enter)';
    };

    feModeRange.onclick = () => {
      S.mode = 'range';
      feModeRange.classList.add('on'); feModeFrame.classList.remove('on');
      feGo.textContent = '🚀 Regen Range (Fast H3)';
      fePrompt.placeholder = 'Describe action, prompt, or changes across timeline range [X to Y]… (Ctrl+Enter)';
      updateRangeDisplay();
    };

    $('#feMarkIn').onclick = () => {
      const curT = nle.ui ? nle.ui.t : 0;
      if (typeof nle.markIn === 'function') {
        nle.markIn();
      } else if (nle.tl) {
        nle.edit(() => {
          nle.tl.inPoint = Math.round(curT * 100) / 100;
          if (nle.tl.outPoint != null && nle.tl.outPoint <= nle.tl.inPoint) nle.tl.outPoint = null;
        });
      }
      updateRangeDisplay();
    };
    $('#feMarkOut').onclick = () => {
      const curT = nle.ui ? nle.ui.t : 0;
      if (typeof nle.markOut === 'function') {
        nle.markOut();
      } else if (nle.tl) {
        nle.edit(() => {
          nle.tl.outPoint = Math.round(curT * 100) / 100;
          if (nle.tl.inPoint != null && nle.tl.inPoint >= nle.tl.outPoint) nle.tl.inPoint = null;
        });
      }
      updateRangeDisplay();
    };

    const feClearRange = $('#feClearRange');
    if (feClearRange) {
      feClearRange.onclick = () => {
        if (typeof nle.clearRange === 'function') nle.clearRange();
        else if (nle.tl) nle.edit(() => { nle.tl.inPoint = null; nle.tl.outPoint = null; });
        updateRangeDisplay();
      };
    }

    const inInput = $('#feInInput'), outInput = $('#feOutInput');
    const onInputChange = () => {
      if (!inInput || !outInput || !nle || !nle.tl) return;
      const v0 = parseFloat(inInput.value), v1 = parseFloat(outInput.value);
      if (isNaN(v0) || isNaN(v1)) return;
      nle.edit(() => {
        nle.tl.inPoint = Math.max(0, v0);
        nle.tl.outPoint = Math.max(v0 + 0.1, v1);
      });
      const durEl = $('#feDurText');
      if (durEl) durEl.textContent = `${Math.max(0, v1 - v0).toFixed(1)}s`;
    };
    if (inInput) inInput.onchange = onInputChange;
    if (outInput) outInput.onchange = onInputChange;

    feThumb.onclick = () => {
      if (S.customRef) {
        if (confirm('Clear uploaded reference image and use playhead video frame?')) {
          S.customRef = null;
          feThumbBadge.textContent = 'Playhead';
          captureBase();
          return;
        }
      }
      feFileInput.click();
    };

    feFileInput.onchange = async () => {
      const file = feFileInput.files && feFileInput.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = async (e) => {
        say('Uploading reference image to ComfyUI…');
        try {
          const r = await post('/api/nle/upload_ref', { image: e.target.result, filename: file.name });
          S.customRef = r.filename;
          feThumb.style.backgroundImage = `url("${r.url}")`;
          feThumbBadge.textContent = 'Ref Attached';
          say(`Reference image attached: ${r.filename}`);
        } catch (err) { say('Reference upload error: ' + err.message); }
      };
      reader.readAsDataURL(file);
    };

    feGo.onclick = generate;
    $('#feBrushBtn').onclick = toggleBrush;

    fePrompt.addEventListener('input', () => {
      if (activePromptClipId) {
        userClipPrompts[activePromptClipId] = fePrompt.value;
        if (nle && nle.tl && nle.tl.clips) {
          const c = nle.tl.clips.find((x) => x.id === activePromptClipId);
          if (c) c.prompt = fePrompt.value;
        }
      }
    });

    const autoPromptBtn = $('#feAutoPromptBtn');
    if (autoPromptBtn) {
      autoPromptBtn.onclick = async () => {
        const tl = nle.tl || (nle.timeline ? nle.timeline() : null);
        const inP = (tl && tl.inPoint != null) ? tl.inPoint : 0;
        const outP = (tl && tl.outPoint != null) ? tl.outPoint : (nle.total ? nle.total() : 10);
        const t0 = Math.min(inP, outP), t1 = Math.max(inP, outP);
        const adjustments = fePrompt.value.trim();
        const c = (typeof nle.selectedClip === 'function' ? nle.selectedClip() : null) ||
                  (activePromptClipId && tl ? tl.clips.find((x) => x.id === activePromptClipId) : null) ||
                  (tl && tl.clips && tl.clips[0]);
        const orig = c ? (c.originalPrompt || c.prompt || '') : '';
        autoPromptBtn.disabled = true;
        autoPromptBtn.textContent = '⏳ Analyzing…';
        say(`Analyzing video range [${t0.toFixed(1)}s → ${t1.toFixed(1)}s] with Qwen 3.5 Vision…`);
        try {
          const r = await post('/nle/range/auto_prompt', {
            job_id: nle.ui ? nle.ui.jobId : null,
            t_start: t0,
            t_end: t1,
            adjustments: adjustments || 'Analyze scene continuity, motion, and lighting issues and generate full cinematic prompt.',
            current_prompt: orig,
            reference_image: S.customRef
          });
          if (r.prompt) {
            fePrompt.value = r.prompt;
            if (activePromptClipId) userClipPrompts[activePromptClipId] = r.prompt;
            if (c) c.prompt = r.prompt;
            if (r.anchor_url && !S.customRef) {
              feThumb.style.backgroundImage = `url("${r.anchor_url}")`;
              feThumbBadge.textContent = `${t0.toFixed(1)}s`;
            }
            say(`✨ Auto-generated prompt: ${r.summary || 'Ready for range regen'}`);
          }
        } catch (err) {
          say(`Auto-prompt error: ${err.message}`);
        } finally {
          autoPromptBtn.disabled = false;
          autoPromptBtn.textContent = '⚡ Auto-Gen Prompt';
        }
      };
    }

    const resetBtn = $('#feResetPromptBtn');
    if (resetBtn) {
      resetBtn.onclick = () => {
        if (!nle || !nle.tl) return;
        const c = (typeof nle.selectedClip === 'function' ? nle.selectedClip() : null) ||
                  (activePromptClipId ? nle.tl.clips.find((x) => x.id === activePromptClipId) : null) ||
                  (nle.tl.clips && nle.tl.clips[0]);
        if (c) {
          let orig = c.originalPrompt || c.prompt || '';
          if (!orig && nle.ui && nle.ui.job) {
            const shotIdx = c.shot != null ? c.shot : 0;
            const job = nle.ui.job;
            if (job.chunk_prompts && job.chunk_prompts[shotIdx]) orig = job.chunk_prompts[shotIdx];
            else if (job.scenes && job.scenes[shotIdx] && job.scenes[shotIdx].prompt) orig = job.scenes[shotIdx].prompt;
            else if (job.plan && job.plan.shots && job.plan.shots[shotIdx] && job.plan.shots[shotIdx].prompt) orig = job.plan.shots[shotIdx].prompt;
            else if (job.prompt) orig = shotIdx === 0 ? job.prompt : `${job.prompt} [continuation sequence ${shotIdx + 1}, fluid motion]`;
          }
          fePrompt.value = orig;
          c.prompt = orig;
          c.originalPrompt = orig;
          delete userClipPrompts[c.id];
          say(`Reset ${c.label} to original prompt`);
        }
      };
    }

    fePrompt.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        generate();
      }
    });
  }

  function buildHud() {
    const hud = document.getElementById('nleBrushHud');
    hud.innerHTML = `<b style="color:#7aa2ff">✨ Magic Brush</b>
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
      if (c.isRange) {
        d.innerHTML = `<span style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:0.6rem;color:#a9c1ff;background:#0b1230;text-align:center;padding:2px;font-weight:700;">Range Clip<br>${(c.t1 - c.t0).toFixed(1)}s</span>`;
      }
      d.title = c.prompt || '';
      d.onclick = () => { if (!c.busy) selectCand(c); };
      box.appendChild(d);
    });
  }
  async function generate() {
    if (S.busy) return;
    const prompt = $('#fePrompt').value.trim();
    if (!prompt) { say('Write a prompt first.'); return; }

    if (S.mode === 'range') {
      const tl = nle.tl || (nle.timeline ? nle.timeline() : null);
      const inP = (tl && tl.inPoint != null) ? tl.inPoint : 0;
      const outP = (tl && tl.outPoint != null) ? tl.outPoint : (nle.total ? nle.total() : 10);
      const t0 = Math.min(inP, outP), t1 = Math.max(inP, outP);
      if (Math.abs(t1 - t0) < 0.2) {
        say('Set In and Out points [I and O] to specify a range first.');
        return;
      }
      S.busy = true; $('#feGo').disabled = true;
      const cand = addCand({ busy: true, prompt, isRange: true, t0, t1 });
      say(`Generating Fast H3 replacement video for [${t0.toFixed(1)}s → ${t1.toFixed(1)}s]…`);
      try {
        const r = await post('/nle/range/generate', {
          prompt,
          t_start: t0,
          t_end: t1,
          reference_image: S.customRef,
          job_id: nle.ui ? nle.ui.jobId : null
        });
        cand.busy = false;
        cand.clipFilename = r.clip_filename;
        cand.clipUrl = r.clip_url;
        selectCand(cand);
        say(`Range video generated (${r.clip_filename}). Click candidate to preview and splice.`);
      } catch (err) {
        say(`Range generation failed: ${err.message}`);
        cand.busy = false; S.cands = S.cands.filter((x) => x !== cand); renderCands();
      } finally {
        S.busy = false; $('#feGo').disabled = false;
      }
      return;
    }

    if (!S.brushing && !captureBase()) return;
    if (S.brushing && !S.hasMask) { say('Paint the region to change first.'); return; }
    S.busy = true; $('#feGo').disabled = true;
    const cand = addCand({ busy: true, prompt, isRange: false });
    try {
      let d;
      if (S.brushing) {
        say('Inpainting the painted area with ComfyUI…');
        const file = await ensureBaseSaved();
        const out = document.createElement('canvas'); out.width = maskCv.width; out.height = maskCv.height;
        const g = out.getContext('2d'); g.fillStyle = '#000'; g.fillRect(0, 0, out.width, out.height); g.drawImage(maskCv, 0, 0);
        d = await post('/inpaint_image', { image_filename: file, mask_data: out.toDataURL('image/png'), prompt, denoise: S.strength, steps: 4 });
      } else {
        say('Generating a new image with Qwen Image 2.1…');
        d = await post('/nle/frame/generate', {
          prompt,
          time: nle.ui ? nle.ui.t : 0,
          reference_image: S.customRef,
          job_id: nle.ui ? nle.ui.jobId : null
        });
      }
      cand.busy = false;
      cand.filename = d.id || d.filename;
      cand.url = d.image_url || nle.q(`${nle.cfg.inp}/${encodeURIComponent(d.filename)}`);
      selectCand(cand);
      say('Done — review the candidate, then merge it into the timeline.');
    } catch (err) {
      say(`Generation failed: ${err.message}`);
      cand.busy = false; S.cands = S.cands.filter((x) => x !== cand); renderCands();
    } finally {
      S.busy = false; $('#feGo').disabled = false;
    }
  }

  // ---------- merge ----------
  function selectCand(c) {
    S.sel = c; renderCands();
    const m = $('#feMerge');
    if (c.isRange) {
      m.innerHTML = `
        <span style="color:#a9c1ff;font-weight:700;">Replacement Clip: ${c.clipFilename} [${c.t0.toFixed(1)}s &rarr; ${c.t1.toFixed(1)}s]</span>
        <button class="nle-btn primary" id="feApplyRangeBtn">⧫ Splice Range into Master Video</button>
        <button class="nle-btn" id="feDiscard">Discard</button>
      `;
      $('#feDiscard').onclick = () => { S.cands = S.cands.filter((x) => x !== c); S.sel = null; $('#feMerge').innerHTML = ''; renderCands(); };
      $('#feApplyRangeBtn').onclick = async () => {
        const btn = $('#feApplyRangeBtn');
        btn.disabled = true;
        say(`Splicing [${c.t0.toFixed(1)}s → ${c.t1.toFixed(1)}s] into master video with FFmpeg…`);
        try {
          const r = await post('/nle/range/apply', {
            job_id: nle.ui ? nle.ui.jobId : null,
            clip_filename: c.clipFilename,
            t_start: c.t0,
            t_end: c.t1
          });
          say(`Splice complete! New master video: ${r.spliced_filename}`);
          m.innerHTML = '';
          const vid = nle.root && nle.root.vid ? nle.root.vid : document.querySelector('.nle-screen video');
          if (vid) {
            vid.src = r.spliced_url;
            vid.load();
            vid.play().catch(() => {});
          }
          if (nle.loadMaster) nle.loadMaster(r.spliced_url);
        } catch (err) { say('Splice error: ' + err.message); }
        finally { btn.disabled = false; }
      };
      return;
    }

    const img = nle.root.ovl; img.setAttribute('data-k', 'preview'); img.src = c.url; img.style.display = 'block';
    const hit = nle.clipAtPlayhead(), rest = hit ? Math.max(0.5, +(hit.end - S.base.t).toFixed(2)) : 2;
    m.innerHTML = `<b style="color:#e3e8fb">Merge into timeline:</b>
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
    if (nle && nle.on) {
      nle.on('render', () => { updateRangeDisplay(); syncClipPrompt(); });
      nle.on('inout', () => updateRangeDisplay());
      nle.on('load', () => { updateRangeDisplay(); syncClipPrompt(); });
      nle.on('select', () => syncClipPrompt());
      nle.on('time', (t) => {
        if (!S.customRef) {
          const b = $('#feThumbBadge');
          if (b) b.textContent = `${t.toFixed(1)}s`;
        }
        syncClipPrompt();
      });
    }
    syncClipPrompt();
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

  window.NLEFrameEdit = { mount: mountBar, toggleBrush: () => nle && toggleBrush(), reanimate, state: S, updateRangeDisplay, syncClipPrompt };
})();
