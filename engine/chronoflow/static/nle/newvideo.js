/* ChronoFlow "New Video": start-mode wizard + the per-shot approval gate.
 * The tables mirror engine/chronoflow/start_modes.py (keep them in step). Pure functions first (unit-tested in tests/js), DOM wiring in mount(). */
(function (root) {
  const SEG_SECONDS = 5.17, MAX_SECONDS = 600;
  const SLOTS = { text: [], first: ['first'], from_video: ['first'], first_last: ['first', 'last'], last: ['last'], reference: ['ref1', 'ref2'] };

  function slotsFor(mode) {
    if (!(mode in SLOTS)) throw new Error(`unknown start mode '${mode}'`);
    return SLOTS[mode].slice();
  }
  const segmentCount = (seconds) => Math.max(1, Math.round(seconds / SEG_SECONDS));
  function lengthLabel(seconds) {
    const min = Math.floor(seconds / 60), s = Math.round(seconds % 60);
    const text = min === 0 ? `${s} s` : (s === 0 ? `${min} min` : `${min} min ${s} s`);
    const n = segmentCount(seconds);
    return `${text} = ${n} segment${n === 1 ? '' : 's'}${n > 1 ? ` × ${SEG_SECONDS} s` : ''}`;
  }

  // A card is "chained" when it continues from the previous clip's tail frame (no picture of its own).
  const chained = (s) => !!s.inherits_tail && !s.first_frame;

  function canRender(scenes, i) {
    const s = scenes[i];
    if (!chained(s)) return { ok: true, reason: '' };
    if (i === 0) return { ok: false, reason: 'Nothing to continue from: add a first frame to this shot.' };
    if (scenes[i - 1].approved) return { ok: true, reason: '' };
    return { ok: false, reason: `Approve Shot ${scenes[i - 1].shot_index || i} first: this shot continues from its last frame.` };
  }
  const prevTail = (scenes, i) => (i > 0 && scenes[i - 1].tail_frame) || '';

  function markRendered(scenes, i, res) {
    Object.assign(scenes[i], { state: 'review', approved: false, rendered_video: res.video_url || res.video || '', tail_frame: res.tail_frame || '' });
    if (res.filename) scenes[i].rendered_video_filename = res.filename;
  }
  function approve(scenes, i) { Object.assign(scenes[i], { approved: true, state: 'approved' }); }
  function markRedo(scenes, i) {
    Object.assign(scenes[i], { approved: false, state: 'ready', rendered_video: '', tail_frame: '' });
    for (let j = i + 1; j < scenes.length && chained(scenes[j]); j++) Object.assign(scenes[j], { approved: false, state: 'stale' }); // their start frame came from the old clip
  }

  // ---- card helpers (mirror engine/chronoflow/start_modes.py so a card can say what it still needs before the server is asked)
  const CHAINED_MODES = ['text', 'first', 'from_video'];
  const MODE_LABEL = { text: 'Text only', first: 'First frame', first_last: 'First + last', last: 'Last frame only', reference: 'Reference', from_video: 'From a video' };
  const SLOT_LABEL = { first: 'First frame', last: 'Last frame', ref1: 'Reference 1', ref2: 'Reference 2' };

  function getSlot(s, slot) {
    if (slot === 'first') return s.first_frame || '';
    if (slot === 'last') return s.last_frame || '';
    return (s.ref_images || [])[slot === 'ref1' ? 0 : 1] || '';
  }
  function setSlot(s, slot, name) {
    if (slot === 'first') s.first_frame = name;
    else if (slot === 'last') s.last_frame = name;
    else {
      const refs = (s.ref_images || []).slice();
      if (slot === 'ref2' && !refs[0]) throw new Error('Add reference 1 before reference 2');
      refs[slot === 'ref1' ? 0 : 1] = name;
      s.ref_images = refs.filter(Boolean); // never leave a hole: the server reads the list in order
    }
  }
  function effectiveMode(s, i) {
    if (s.start_mode === 'from_video' || (s.start_mode === 'text' && i >= 1 && s.inherits_tail)) return 'first';
    return s.start_mode;
  }
  function missingInputs(s, i) {
    const need = { text: [], first: ['first'], first_last: ['first', 'last'], last: ['last'], reference: ['ref1'] }[effectiveMode(s, i)];
    const out = need.filter((k) => !getSlot(s, k));
    if (out.includes('first') && s.inherits_tail) out.splice(out.indexOf('first'), 1); // the tail frame is supplied at render time
    if (!(s.prompt || '').trim()) out.push('prompt');
    return out;
  }
  function sizeWarning(s, i) {
    const m = effectiveMode(s, i);
    if (m !== 'text' && m !== 'reference') return '';
    const portrait = (s.height || 768) > (s.width || 1344), size = portrait ? '544×960' : '960×544', want = portrait ? '768×1344' : '1344×768';
    return (s.width || 1344) * (s.height || 768) > 960 * 544 ? `Renders at ${size}, smaller than this video's ${want}` : '';
  }
  function setMode(scenes, i, mode) {
    const s = scenes[i];
    slotsFor(mode);
    s.start_mode = mode;
    s.inherits_tail = i >= 1 && CHAINED_MODES.includes(mode);
    if (s.state === 'review' || s.state === 'approved' || s.rendered_video) markRedo(scenes, i); // the old clip no longer matches the card
    else s.state = (s.prompt || '').trim() ? 'ready' : 'empty';
  }

  // ---- the wizard popup (markup lives in index.html: ids nvStep1..3 etc.)
  function mount(cfg) {
    ctx = cfg;
    const $ = (id) => document.getElementById(id);
    const st = { mode: 'text', seconds: 300, portrait: false };
    const showStep = (n) => [1, 2, 3].forEach((k) => { $(`nvStep${k}`).style.display = k === n ? '' : 'none'; });
    const err = (msg) => { $('nvError').textContent = msg || ''; };
    const refreshLength = () => {
      const v = $('nvLengthPreset').value;
      st.seconds = v === 'custom' ? parseFloat($('nvLengthCustom').value) || 0 : parseFloat(v);
      $('nvLengthCustom').style.display = v === 'custom' ? '' : 'none';
      $('nvLengthLabel').textContent = st.seconds >= 1 && st.seconds <= MAX_SECONDS ? lengthLabel(st.seconds) : `Length must be between 1 and ${MAX_SECONDS} seconds`;
    };
    $('nvModeCards').addEventListener('click', (e) => {
      const el = e.target.closest('[data-mode]');
      if (!el) return;
      st.mode = el.dataset.mode;
      [...$('nvModeCards').children].forEach((c) => c.classList.toggle('active', c === el));
      err(''); refreshLength(); showStep(2);
    });
    ['nvLengthPreset', 'nvLengthCustom'].forEach((id) => $(id).addEventListener('input', refreshLength));
    $('nvToStep3').addEventListener('click', () => { if (st.seconds >= 1 && st.seconds <= MAX_SECONDS) { err(''); showStep(3); } else err(`Length must be between 1 and ${MAX_SECONDS} seconds`); });
    document.querySelectorAll('[data-nv-back]').forEach((b) => b.addEventListener('click', () => showStep(parseInt(b.dataset.nvBack, 10))));
    $('nvCreate').addEventListener('click', async () => {
      const btn = $('nvCreate');
      const wantDraft = $('nvDraft').checked, idea = $('nvIdea').value.trim();
      if (wantDraft && !idea) return err('Write a story idea first, or untick "Draft all prompts with AI".');
      btn.disabled = true; err('');
      try {
        const plan = await cfg.post('/storyboard/plan', { mode: st.mode, length_seconds: st.seconds, title: `${idea.slice(0, 40) || 'New Video'} ${new Date().toISOString().slice(5, 16).replace(/\D/g, '')}` }); // the stamp keeps two plans from sharing one vault file
        if (wantDraft) {
          btn.textContent = 'Drafting prompts…';
          const d = await cfg.post('/storyboard/draft_prompts', { idea, count: plan.scenes.length, mode: st.mode });
          plan.scenes.forEach((s, i) => { s.prompt = d.prompts[i]; s.state = 'ready'; });
        }
        const portrait = document.querySelector('input[name="nvFormat"]:checked').value === 'portrait';
        plan.scenes.forEach((s) => Object.assign(s, { width: portrait ? 768 : 1344, height: portrait ? 1344 : 768, lora_choice: $('nvSpeed').value }));
        await cfg.onPlanReady(plan);
      } catch (e) {
        err(e.message || String(e));
      } finally {
        btn.disabled = false; btn.textContent = 'Create storyboard';
      }
    });
    return { open() { err(''); showStep(1); refreshLength(); } };
  }

  // ---- storyboard cards for wizard plans (browser only; mount() stores the page's helpers in ctx)
  let ctx = null, pending = null;
  const STATE_LABEL = { empty: 'Needs a prompt', ready: 'Ready', rendering: 'Rendering…', review: 'Review', approved: 'Approved', stale: 'Redo needed' };
  const PROMPT_KEY = { first: 'first_prompt', last: 'last_prompt', ref1: 'ref1_prompt', ref2: 'ref2_prompt' };
  const scenesNow = () => ctx.scenes();
  const touch = async () => { await ctx.save(); ctx.rerender(); };

  function slotWidget(s, i, slot) {
    const name = getSlot(s, slot), e = ctx.esc;
    const note = slot === 'first' && s.inherits_tail ? ` <i>(optional: otherwise continues from Shot ${i})</i>` : '';
    const thumb = name ? `<img src="${e(ctx.media(name, 'input'))}" alt="${e(name)}" style="width:54px;height:34px;object-fit:cover;border-radius:4px;border:1px solid rgba(255,255,255,.12)">` : '<span class="nv-blank">empty</span>';
    const clip = s.start_mode === 'from_video' && i === 0 && slot === 'first' ? `<button type="button" class="btn-tool" onclick="NewVideo.clip(${i})">Clip…</button>` : '';
    return `<div class="nv-slot"><span class="nv-slot-label">${SLOT_LABEL[slot]}${note}</span>${thumb}
      <button type="button" class="btn-tool" onclick="NewVideo.upload(${i},'${slot}')">Upload</button>${clip}
      <button type="button" class="btn-tool" onclick="NewVideo.vault(${i},'${slot}')">Vault</button>
      <button type="button" class="btn-tool" onclick="NewVideo.generate(${i},'${slot}')">Generate</button>
      ${name ? `<button type="button" class="btn-tool" onclick="NewVideo.clear(${i},'${slot}')" title="Clear">✕</button>` : ''}</div>`;
  }

  function cardHtml(scenes, i) {
    const s = scenes[i], e = ctx.esc;
    const opts = Object.keys(MODE_LABEL).map((m) => `<option value="${m}"${m === s.start_mode ? ' selected' : ''}>${MODE_LABEL[m]}</option>`).join('');
    const slots = slotsFor(s.start_mode).filter((k) => k !== 'ref2' || getSlot(s, 'ref1')).map((k) => slotWidget(s, i, k)).join('');
    const chain = s.inherits_tail && !s.first_frame && s.start_mode !== 'from_video' ? `<div class="nv-note">Continues from the last frame of Shot ${i}</div>` : '';
    const warn = sizeWarning(s, i), miss = missingInputs(s, i).filter((k) => k !== 'prompt');
    return `<div class="nv-card">
      <div class="nv-row"><select onchange="NewVideo.onMode(${i}, this.value)" title="Start mode of this shot">${opts}</select><span class="nv-state nv-${s.state}">${STATE_LABEL[s.state] || s.state}</span></div>
      ${chain}${warn ? `<div class="nv-warn">${e(warn)}</div>` : ''}${slots}
      <textarea class="nv-prompt" rows="3" placeholder="What happens in this shot?" onchange="NewVideo.onPrompt(${i}, this.value)">${e(s.prompt || '')}</textarea>
      ${miss.length ? `<div class="nv-note">Still needs: ${miss.map((k) => SLOT_LABEL[k]).join(', ')}</div>` : ''}
      ${s.error ? `<div class="nv-error">${e(s.error)}</div>` : ''}</div>`;
  }

  function actionsHtml(scenes, i) {
    const s = scenes[i], gate = canRender(scenes, i), miss = missingInputs(s, i);
    if (s.state === 'rendering') return '<button type="button" class="btn-primary" disabled style="flex:1;padding:4px 10px;font-size:.72rem"><span><span class="spinner"></span> Rendering…</span></button>';
    if (s.state === 'review') return `<button type="button" class="btn-primary" style="flex:1;padding:4px 10px;font-size:.72rem;background:rgba(70,214,163,.85);border-color:#46d6a3" onclick="NewVideo.approveCard(${i})">✓ Approve</button>
      <button type="button" class="btn-tool" onclick="NewVideo.redo(${i})">🔄 Redo</button>`;
    if (s.state === 'approved') return `<span style="flex:1;color:#46d6a3;font-size:.78rem;font-weight:700">✓ Approved</span><button type="button" class="btn-tool" onclick="NewVideo.redo(${i})">🔄 Redo</button>`;
    const blocked = !gate.ok ? gate.reason : (miss.length ? `Needs: ${miss.map((k) => SLOT_LABEL[k] || k).join(', ')}` : '');
    return `<button type="button" class="btn-primary" style="flex:1;padding:4px 10px;font-size:.72rem" ${blocked ? 'disabled' : ''} title="${ctx.esc(blocked || 'Render this shot')}" onclick="NewVideo.render(${i})">▶ Render</button>`;
  }

  async function render(i) {
    const sc = scenesNow(), s = sc[i];
    if (sc.some((c) => c.state === 'rendering')) { s.error = 'Another shot is rendering. Wait for it to finish.'; return ctx.rerender(); }
    s.error = '';
    s.state = 'rendering';
    ctx.rerender();
    try {
      const res = await ctx.post('/storyboard/render_shot', { scene: { ...s, prev_tail: prevTail(sc, i) }, shot_index: i + 1, width: s.width || 1344, height: s.height || 768,
        steps: s.lora_choice === '8step' ? 8 : 4, lora_choice: s.lora_choice || '4step' });
      const now = scenesNow(), j = now.indexOf(s); // the card may have moved while it rendered
      if (j >= 0) markRendered(now, j, res);
    } catch (err) {
      s.state = 'ready';
      s.error = err.message || String(err);
    }
    await touch();
  }

  const panel = (html) => {
    let el = document.getElementById('nvPanel');
    if (!el) { el = document.createElement('div'); el.id = 'nvPanel'; el.className = 'modal-overlay'; el.onclick = (ev) => { if (ev.target === el) el.style.display = 'none'; }; document.body.appendChild(el); }
    el.innerHTML = `<div class="modal-box" style="width:560px;max-width:95vw" onclick="event.stopPropagation()">${html}</div>`;
    el.style.display = 'flex';
    return el;
  };
  const closePanel = () => { const el = document.getElementById('nvPanel'); if (el) el.style.display = 'none'; pending = null; };
  const thumbs = (items) => `<div class="nv-grid">${items.map((it) => `<button type="button" class="nv-thumb" data-name="${ctx.esc(it.name)}" onclick="NewVideo.pick(this)" title="${ctx.esc(it.label || it.name)}">${it.video ? `<span>${ctx.esc(it.label || it.name)}</span>` : `<img src="${ctx.esc(ctx.media(it.name, 'input'))}" alt="">`}</button>`).join('')}</div>`;

  const cardApi = {
    cardHtml, actionsHtml, render,
    onMode(i, mode) { setMode(scenesNow(), i, mode); touch(); },
    onPrompt(i, v) { const s = scenesNow()[i]; s.prompt = v; if (s.state === 'empty' && v.trim()) s.state = 'ready'; touch(); },
    approveCard(i) { approve(scenesNow(), i); touch(); },
    redo(i) { markRedo(scenesNow(), i); touch(); },
    clear(i, slot) { setSlot(scenesNow()[i], slot, ''); touch(); },
    upload(i, slot) {
      const input = document.createElement('input');
      input.type = 'file'; input.accept = 'image/*';
      input.onchange = async () => {
        if (!input.files[0]) return;
        try { setSlot(scenesNow()[i], slot, await ctx.upload(input.files[0])); } catch (err) { scenesNow()[i].error = err.message; }
        touch();
      };
      input.click();
    },
    async vault(i, slot) {
      pending = { s: scenesNow()[i], slot };
      panel('<h4 style="margin:0 0 8px;color:#f6f8ff">Pick a picture</h4><div id="nvPick">Loading…</div>');
      try {
        const [chars, gal] = await Promise.all([ctx.get('/characters'), ctx.get('/gallery')]);
        const items = [...(chars.characters || []).filter((c) => c.image).map((c) => ({ name: c.image, label: c.name })), ...(gal.images || []).slice().sort((a, b) => b.created_at - a.created_at).slice(0, 60).map((x) => ({ name: x.filename }))];
        document.getElementById('nvPick').innerHTML = items.length ? thumbs(items) : 'No pictures yet. Upload one or generate it.';
      } catch (err) { document.getElementById('nvPick').textContent = err.message; }
    },
    async clip(i) {
      pending = { s: scenesNow()[i], slot: 'first', clip: true };
      panel('<h4 style="margin:0 0 8px;color:#f6f8ff">Continue from which video?</h4><div id="nvPick">Loading…</div>');
      try {
        const gal = await ctx.get('/gallery');
        const clips = [...(gal.masters || []), ...(gal.chunks || [])].sort((a, b) => b.created_at - a.created_at).slice(0, 40);
        document.getElementById('nvPick').innerHTML = clips.length ? thumbs(clips.map((c) => ({ name: c.filename, video: true, label: c.filename }))) : 'No rendered videos found in the studio output folder.';
      } catch (err) { document.getElementById('nvPick').textContent = err.message; }
    },
    async pick(btn) {
      const { s, slot, clip } = pending || {};
      if (!s) return;
      try {
        const name = clip ? (await ctx.post('/storyboard/tail_frame', { video: btn.dataset.name })).filename : btn.dataset.name;
        setSlot(s, slot, name);
        closePanel();
        touch();
      } catch (err) { document.getElementById('nvPick').textContent = err.message; }
    },
    generate(i, slot) {
      const s = scenesNow()[i], key = PROMPT_KEY[slot];
      pending = { s, slot, key };
      panel(`<h4 style="margin:0 0 8px;color:#f6f8ff">Generate the ${SLOT_LABEL[slot].toLowerCase()}</h4>
        <textarea id="nvGenPrompt" rows="4" style="width:100%;font-size:.85rem" placeholder="Describe the picture">${ctx.esc(s[key] || s.prompt || '')}</textarea>
        <div id="nvGenOut" style="margin:8px 0;min-height:1.2em;font-size:.8rem;color:#9aa6d0"></div>
        <div class="nv-row" style="justify-content:space-between"><button type="button" class="btn-tool" onclick="NewVideo.closePanel()">Cancel</button>
        <button type="button" class="btn-primary" id="nvGenBtn" style="width:auto;padding:8px 22px" onclick="NewVideo.runGenerate()">Generate picture</button></div>`);
    },
    async runGenerate() {
      const prompt = document.getElementById('nvGenPrompt').value.trim(), out = document.getElementById('nvGenOut'), btn = document.getElementById('nvGenBtn');
      if (!prompt) { out.textContent = 'Describe the picture first.'; return; }
      btn.disabled = true; out.textContent = 'Generating… (this takes a little while)';
      try {
        const r = await ctx.post('/generate_image', { prompt, width: pending.s.width || 1344, height: pending.s.height || 768 });
        pending.pic = r.filename; pending.prompt = prompt;
        out.innerHTML = `<img src="${ctx.esc(ctx.media(r.filename, 'input'))}" alt="generated" style="max-width:100%;border-radius:6px"><div class="nv-row" style="margin-top:8px"><button type="button" class="btn-primary" style="width:auto;padding:6px 16px" onclick="NewVideo.acceptGenerated()">Use this picture</button><span style="font-size:.76rem">Not right? Change the description and generate again.</span></div>`;
      } catch (err) { out.textContent = err.message; }
      btn.disabled = false;
    },
    acceptGenerated() {
      const { s, slot, key, pic, prompt } = pending;
      s[key] = prompt;
      setSlot(s, slot, pic);
      closePanel();
      touch();
    },
    closePanel,
  };

  const api = { SEG_SECONDS, MAX_SECONDS, slotsFor, segmentCount, lengthLabel, canRender, prevTail, markRendered, approve, markRedo, mount,
    getSlot, setSlot, effectiveMode, missingInputs, sizeWarning, setMode, modeLabel: (s, i) => MODE_LABEL[effectiveMode(s, i)], ...cardApi };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.NewVideo = api;
})(typeof window !== 'undefined' ? window : globalThis);
