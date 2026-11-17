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
    if (i === 0) return s.start_mode === 'text' ? { ok: true, reason: '' } : { ok: false, reason: 'Nothing to continue from: add a first frame to this shot.' }; // a text card first renders as text
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
    Object.assign(scenes[i], { approved: false, state: 'ready', rendered_video: '', tail_frame: '', prev_tail: '' });
    for (let j = i + 1; j < scenes.length && chained(scenes[j]); j++) Object.assign(scenes[j], { approved: false, state: 'stale', prev_tail: '' }); // their start frame came from the old clip
  }

  // Who continues from whom depends on order: recompute after a delete, move or insert. A rendered card whose start frame changes is stale.
  function relink(scenes) {
    scenes.forEach((s, i) => {
      if (!s.start_mode) return;
      const want = i >= 1 && ['text', 'first', 'from_video'].includes(s.start_mode);
      if (!!s.inherits_tail !== want) {
        s.inherits_tail = want;
        if (s.rendered_video) Object.assign(s, { state: 'stale', approved: false });
      }
    });
  }
  function newCard(scenes) {
    const last = scenes[scenes.length - 1] || {}, n = scenes.length, mode = last.start_mode || 'text';
    return { shot_index: n + 1, title: `Shot ${n + 1}`, shot_type: 'Medium Tracking', duration: SEG_SECONDS, start_mode: mode,
      workflow: { reference: 'reference', first_last: 'flf2v' }[mode] || 'sliding_window', prompt: '', first_frame: '', last_frame: '', ref_images: [], first_prompt: '', last_prompt: '',
      state: 'empty', approved: false, inherits_tail: n >= 1 && ['text', 'first', 'from_video'].includes(mode), width: last.width || 1344, height: last.height || 768, lora_choice: last.lora_choice || '4step', folder_id: null };
  }
  function chainKeyframe(scenes, i) {  // the end picture of a first+last card is offered as the start of the next one (never over a picture the user chose)
    const s = scenes[i], n = scenes[i + 1];
    if (s && n && s.start_mode === 'first_last' && s.last_frame && n.start_mode === 'first_last' && !n.first_frame) n.first_frame = s.last_frame;
  }

  // ---- Motion Bank on a First + last card: pick a harvested motion and a character, get the start and end pictures (engine/chronoflow/motion_frames.py)
  function motionRequest(sel, s) {
    if (!sel.motion) throw new Error('Choose a motion first.');
    if (!sel.character) throw new Error('Choose the character picture first.');
    const a = Number(sel.start), b = Number(sel.end);
    if (!(a >= 0 && b <= 100 && a < b)) throw new Error('The start must be before the end (0 to 100 %).');
    return { motion_id: sel.motion, character_picture: sel.character, width: s.width || 1344, height: s.height || 768,
      start_pct: a / 100, end_pct: b / 100, hint: (sel.hint || '').trim() };
  }
  function applyMotionFrames(scenes, i, res, sel) {
    const s = scenes[i];
    if (!res.first_frame || !res.last_frame) throw new Error('The engine returned no pictures.');
    if (s.state === 'review' || s.state === 'approved' || s.rendered_video) markRedo(scenes, i); // the old clip no longer matches the pictures
    s.first_frame = res.first_frame;
    s.last_frame = res.last_frame;
    s.motion = { id: res.motion_id, character: sel.character, start_pct: Number(sel.start) / 100, end_pct: Number(sel.end) / 100,
      first_index: res.first_index, last_index: res.last_index, rights: res.rights || '' };
    if (s.state === 'empty' && (s.prompt || '').trim()) s.state = 'ready';
    chainKeyframe(scenes, i);
  }

  // ---- plan import: pictures from the picture job and the Render all queue
  function applyPictureItems(scenes, items, slug) {
    let changed = false;
    const mine = (v) => !v || String(v).startsWith(slug + '_'); // empty, or an earlier plan picture: never the owner's own file
    for (const it of items) {
      const s = scenes.find((c) => c.take_id === it.take_id);
      if (!s) continue;
      if (it.start && it.start !== s.first_frame && mine(s.first_frame)) { s.first_frame = it.start; changed = true; }
      if (it.end && it.end !== s.last_frame && mine(s.last_frame)) { s.last_frame = it.end; changed = true; }
      const probs = it.problems || [];
      if (JSON.stringify(s.picture_problems || []) !== JSON.stringify(probs)) { s.picture_problems = probs; changed = true; }
    }
    return changed;
  }
  const pictureCounts = (scenes) => ({ takes: scenes.length, ready: scenes.filter((s) => s.first_frame && s.last_frame).length });
  function renderAllQueue(scenes) {
    const run = [], waiting = [];
    scenes.forEach((s, i) => {
      if (!['ready', 'stale', 'empty'].includes(displayState(s))) return; // rendering, in review or approved
      const gate = canRender(scenes, i), miss = missingInputs(s, i);
      if (!gate.ok || miss.length) waiting.push({ i, reason: gate.reason || `Needs: ${miss.map((k) => SLOT_LABEL[k] || k).join(', ')}` });
      else run.push(i);
    });
    return { run, waiting };
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

  // ---- plan upload: what the owner sees after a check (pure, so it is tested without a page)
  function planResultHtml(r, e, auto) {
    const n = (r.changes || []).length;
    const fixed = n ? `<details class="nv-plan-fixed" open><summary><b>Auto-fix changed ${n} thing${n === 1 ? '' : 's'}</b></summary><ul>${r.changes.map((c) => `<li>${e(c)}</li>`).join('')}</ul>
      <button type="button" class="btn-tool" data-nv-act="undo">Undo auto-fix</button></details>` : '';
    if (!r.ok) {
      const k = r.problems.length;
      const note = n ? '<div class="nv-note">Auto-fix repaired what it could safely. These could not be repaired safely, so they need the assistant or you.</div>'
        : (auto ? '<div class="nv-note">Auto-fix found nothing here that it could repair safely.</div>' : '');
      const manual = auto ? '' : '<button type="button" class="btn-primary" data-nv-act="fix" style="width:auto;padding:5px 14px;font-size:.78rem">Auto-fix</button> ';
      return `${fixed}<div class="nv-plan-bad"><b>${k} problem${k === 1 ? '' : 's'} in this plan</b><ul>${r.problems.map((m) => `<li>${e(m)}</li>`).join('')}</ul>${note}
        ${manual}<button type="button" class="btn-tool" data-nv-act="copy">Copy for the assistant</button> <span class="nv-note">Paste this to the assistant and ask for the whole corrected plan.</span></div>`;
    }
    const m = r.summary;
    return `${fixed}<div class="nv-plan-ok"><b>${e(m.title)}</b><div>${m.takes} shots &middot; ${m.seconds} s &middot; ${e(m.format)} &middot; ${m.pictures} pictures to draw &middot; ${m.clip_seconds} s clips${m.narration === 'narrator' ? ' &middot; narrated' : ''}</div>
      ${(r.warnings || []).map((w) => `<div class="nv-warn">${e(w)}</div>`).join('')}
      <button type="button" class="btn-primary" data-nv-act="import" style="width:auto;padding:8px 22px;margin-top:8px">Import plan</button></div>`;
  }

  // ---- the wizard popup (markup lives in index.html: ids nvStep1..3 etc.)
  function mount(cfg) {
    ctx = cfg;
    const $ = (id) => document.getElementById(id);
    const st = { mode: 'text', seconds: 300, portrait: false };
    const STEPS = { 0: 'nvStep0', 1: 'nvStep1', 2: 'nvStep2', 3: 'nvStep3', plan: 'nvStepPlan' };
    const showStep = (n) => Object.entries(STEPS).forEach(([k, id]) => { $(id).style.display = String(k) === String(n) ? '' : 'none'; });
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

    // ---- start from a plan file: download the kit, paste or upload the plan, check it, import it
    const NL = String.fromCharCode(10);
    const e = (v) => cfg.esc(v);
    let lastProblems = [];
    const planResult = (html) => { $('nvPlanResult').innerHTML = html; };
    document.querySelectorAll('[data-nv-start]').forEach((b) => b.addEventListener('click', () => { err(''); showStep(b.dataset.nvStart === 'plan' ? 'plan' : 1); }));
    $('nvKitBtn').addEventListener('click', async () => { try { await cfg.download('/plan/kit', 'PANELFLOW_VIDEO_PLAN_KIT.md'); } catch (x) { err(x.message || String(x)); } });
    $('nvCheckerBtn').addEventListener('click', async () => { try { await cfg.download('/plan/checker', 'check_plan.py'); } catch (x) { err(x.message || String(x)); } });
    let originalText = null; // the text before the last auto-fix, for Undo
    async function planCheck(forceFix, noFix) {
      const text = $('nvPlanText').value;
      err('');
      if (!text.trim()) return planResult('<div class="nv-warn">Paste the plan, or choose the file, first.</div>');
      planResult('Checking the plan…');
      const auto = noFix === true ? false : (forceFix === true || $('nvAutoFix').checked);
      try {
        const r = await cfg.post('/plan/validate', { text, fix: auto });
        lastProblems = r.problems;
        if ((r.changes || []).length && r.fixed_text) { originalText = text; $('nvPlanText').value = r.fixed_text; }
        planResult(planResultHtml(r, e, auto || $('nvAutoFix').checked));
      } catch (x) { planResult(`<div class="nv-error">${e(x.message || String(x))}</div>`); }
    }
    $('nvPlanCheck').addEventListener('click', () => planCheck());
    $('nvPlanText').addEventListener('paste', () => setTimeout(() => planCheck(), 60));
    $('nvPlanFile').addEventListener('change', async () => {
      const f = $('nvPlanFile').files[0];
      if (!f) return;
      if (f.size > 2000000) return err('That file is too big to be a plan (over 2 MB).');
      $('nvPlanText').value = await f.text();
      $('nvPlanFile').value = '';
      planCheck();
    });
    $('nvPlanResult').addEventListener('click', async (ev) => {
      const act = ev.target.closest('[data-nv-act]');
      if (!act) return;
      if (act.dataset.nvAct === 'fix') {
        planCheck(true);
      } else if (act.dataset.nvAct === 'undo') {
        if (originalText !== null) { $('nvPlanText').value = originalText; originalText = null; }
        planCheck(false, true);
      } else if (act.dataset.nvAct === 'copy') {
        const text = ['Please fix these problems in the plan, then send me the whole corrected JSON again (only the JSON):'].concat(lastProblems.map((m) => '- ' + m)).join(NL);
        try { await navigator.clipboard.writeText(text); act.textContent = 'Copied'; } catch (x) { $('nvPlanText').focus(); err('Could not copy automatically. Select the problems above and copy them.'); }
      } else if (act.dataset.nvAct === 'import') {
        act.disabled = true; err('');
        try { await cfg.onPlanImported(await cfg.post('/plan/import', { text: $('nvPlanText').value, fix: $('nvAutoFix').checked })); } catch (x) { err(x.message || String(x)); act.disabled = false; }
      }
    });
    return { open() { err(''); showStep(0); refreshLength(); planResult(''); $('nvPlanText').value = ''; } };
  }

  // ---- storyboard cards for wizard plans (browser only; mount() stores the page's helpers in ctx)
  let ctx = null, pending = null;
  const activeRenders = new Set(); // 'rendering' is only true while this page is rendering it; a saved 'rendering' (reload, crash) is shown as ready
  const STATE_LABEL = { empty: 'Needs a prompt', ready: 'Ready', rendering: 'Rendering…', review: 'Review', approved: 'Approved', stale: 'Redo needed' };
  const PROMPT_KEY = { first: 'first_prompt', last: 'last_prompt', ref1: 'ref1_prompt', ref2: 'ref2_prompt' };
  const scenesNow = () => ctx.scenes();
  function displayState(s) {
    if (s.state === 'rendering') return activeRenders.has(s) ? 'rendering' : 'ready';
    return Object.prototype.hasOwnProperty.call(STATE_LABEL, s.state) ? s.state : 'ready';
  }
  // Save, then redraw the grid. Text typed in a prompt box (even if not yet committed) must survive the redraw.
  const touch = async () => {
    await ctx.save();
    const a = document.activeElement;
    const snap = a && a.classList && a.classList.contains('nv-prompt') ? { i: +a.dataset.i, v: a.value, s: a.selectionStart, e: a.selectionEnd } : null;
    if (snap && scenesNow()[snap.i]) { const sc = scenesNow()[snap.i]; sc.prompt = snap.v; if (sc.state === 'empty' && snap.v.trim()) sc.state = 'ready'; }
    ctx.rerender();
    if (snap) {
      const ta = document.querySelector(`.nv-prompt[data-i="${snap.i}"]`);
      if (ta) { ta.focus(); ta.setSelectionRange(snap.s, snap.e); }
      ctx.save();
    }
  };
  function setSlotChained(s, slot, name) {
    setSlot(s, slot, name);
    const sc = scenesNow(), i = sc.indexOf(s);
    if (slot === 'last' && i >= 0) chainKeyframe(sc, i);
  }

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
    const motionBar = s.start_mode === 'first_last'
      ? `<div class="nv-slot"><span class="nv-slot-label">Motion</span>${s.motion ? `<span class="nv-note" title="Start and end pose taken from the Motion Bank">🕺 ${e(s.motion.id)} (${Math.round(s.motion.start_pct * 100)}–${Math.round(s.motion.end_pct * 100)} %)</span>` : '<span class="nv-blank">none</span>'}
        <button type="button" class="btn-tool" onclick="NewVideo.motion(${i})">🕺 From motion…</button></div>` : '';
    const chain = s.inherits_tail && !s.first_frame && s.start_mode !== 'from_video' ?`<div class="nv-note">Continues from the last frame of Shot ${i}</div>` : '';
    const warn = sizeWarning(s, i), miss = missingInputs(s, i).filter((k) => k !== 'prompt');
    const probs = (s.picture_problems || []).length ? `<div class="nv-warn">Picture check: ${e(s.picture_problems.join('; '))}</div>` : '';
    const narr = s.narration ? `<div class="nv-note" title="The narration for this shot is kept; voice-over is not produced from here yet">🎙 ${e(s.narration)}</div>` : '';
    return `<div class="nv-card">
      <div class="nv-row"><select onchange="NewVideo.onMode(${i}, this.value)" title="Start mode of this shot">${opts}</select><span class="nv-state nv-${displayState(s)}">${STATE_LABEL[displayState(s)]}</span></div>
      ${chain}${warn ? `<div class="nv-warn">${e(warn)}</div>` : ''}${narr}${probs}${slots}${motionBar}
      <textarea class="nv-prompt" data-i="${i}" rows="3" placeholder="What happens in this shot?" onchange="NewVideo.onPrompt(${i}, this.value)">${e(s.prompt || '')}</textarea>
      ${miss.length ? `<div class="nv-note">Still needs: ${miss.map((k) => SLOT_LABEL[k]).join(', ')}</div>` : ''}
      ${s.error ? `<div class="nv-error">${e(s.error)}</div>` : ''}</div>`;
  }

  function actionsHtml(scenes, i) {
    const s = scenes[i], gate = canRender(scenes, i), miss = missingInputs(s, i);
    const st = displayState(s);
    if (st === 'rendering') return '<button type="button" class="btn-primary" disabled style="flex:1;padding:4px 10px;font-size:.72rem"><span><span class="spinner"></span> Rendering…</span></button>';
    if (st === 'review') return `<button type="button" class="btn-primary" style="flex:1;padding:4px 10px;font-size:.72rem;background:rgba(70,214,163,.85);border-color:#46d6a3" onclick="NewVideo.approveCard(${i})">✓ Approve</button>
      <button type="button" class="btn-tool" onclick="NewVideo.redo(${i})">🔄 Redo</button>`;
    if (st === 'approved') return `<span style="flex:1;color:#46d6a3;font-size:.78rem;font-weight:700">✓ Approved</span><button type="button" class="btn-tool" onclick="NewVideo.redo(${i})">🔄 Redo</button>`;
    const blocked = !gate.ok ? gate.reason : (miss.length ? `Needs: ${miss.map((k) => SLOT_LABEL[k] || k).join(', ')}` : '');
    return `<button type="button" class="btn-primary" style="flex:1;padding:4px 10px;font-size:.72rem" ${blocked ? 'disabled' : ''} title="${ctx.esc(blocked || 'Render this shot')}" onclick="NewVideo.render(${i})">▶ Render</button>`;
  }

  async function render(i) {
    const sc = scenesNow(), s = sc[i];
    if (activeRenders.size) { s.error = 'Another shot is rendering. Wait for it to finish.'; return ctx.rerender(); }
    s.error = '';
    s.state = 'rendering';
    activeRenders.add(s);
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
    activeRenders.delete(s);
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

  function drawMotionPanel() {
    const host = document.getElementById('nvMotion');
    if (!host || !pending || !pending.motionPanel) return;
    const e = ctx.esc, sel = pending.sel, L = pending.lists, url = (p) => (ctx.motionMedia ? ctx.motionMedia(p) : p);
    const motions = L.motions.length ? `<div class="nv-grid">${L.motions.map((m) => `<button type="button" class="nv-thumb${sel.motion === m.id ? ' active' : ''}" style="${sel.motion === m.id ? 'outline:2px solid #46d6a3' : ''}" onclick="NewVideo.motionSelect('motion','${e(m.id)}')" title="${e(m.title)} · ${m.duration_sec}s · rights ${e(m.rights || '?')}">${m.thumbnail ? `<img src="${e(url(m.thumbnail))}" alt="">` : `<span>${e(m.title)}</span>`}</button>`).join('')}</div>`
      : '<div class="nv-note">No harvested motions yet. Harvest one in Library → Motions (real footage you have the rights to).</div>';
    const pics = L.pics.length ? `<div class="nv-grid">${L.pics.map((p) => `<button type="button" class="nv-thumb" style="${sel.character === p.name ? 'outline:2px solid #46d6a3' : ''}" onclick="NewVideo.motionSelect('character','${e(p.name)}')" title="${e(p.label || p.name)}"><img src="${e(ctx.media(p.name, 'input'))}" alt=""></button>`).join('')}</div>` : '<div class="nv-note">No pictures yet. Upload one on the card first.</div>';
    const pv = pending.preview ? `<div class="nv-row" style="gap:8px;margin:6px 0"><img src="${e(ctx.media(pending.preview.ref_first || pending.preview.pose_first, 'input'))}" style="width:48%;background:#000;border-radius:4px" alt="start pose"><img src="${e(ctx.media(pending.preview.ref_last || pending.preview.pose_last, 'input'))}" style="width:48%;background:#000;border-radius:4px" alt="end pose"></div>` : '';
    host.innerHTML = `<div class="nv-note" style="margin-bottom:6px">Takes the start and end frame of the harvested footage and draws your character in those two poses. The video model then invents the movement between the two pictures.</div>
      <b style="font-size:.8rem">1. Motion</b>${motions}
      <b style="font-size:.8rem">2. Character picture</b>${pics}
      <div class="nv-row" style="gap:8px;margin:8px 0;align-items:center"><label style="font-size:.78rem">Start at <input type="number" min="0" max="99" value="${sel.start}" style="width:56px" onchange="NewVideo.motionField('start',this.value)"> %</label>
        <label style="font-size:.78rem">End at <input type="number" min="1" max="100" value="${sel.end}" style="width:56px" onchange="NewVideo.motionField('end',this.value)"> %</label></div>
      <input type="text" value="${e(sel.hint)}" placeholder="Optional: who does what (e.g. the woman in blue armour does the move)" style="width:100%;font-size:.8rem" onchange="NewVideo.motionField('hint',this.value)">
      ${pv}<div style="min-height:1.2em;font-size:.78rem;color:#9aa6d0;margin:6px 0">${e(pending.msg || '')}</div>
      <div class="nv-row" style="justify-content:space-between"><button type="button" class="btn-tool" onclick="NewVideo.closePanel()">Cancel</button>
        <span><button type="button" class="btn-tool" ${pending.busy ? 'disabled' : ''} onclick="NewVideo.motionRun(false)">Preview poses</button>
        <button type="button" class="btn-primary" style="width:auto;padding:8px 18px" ${pending.busy ? 'disabled' : ''} onclick="NewVideo.motionRun(true)" title="Experimental: look at both pictures before rendering">Build first + last pictures (experimental)</button></span></div>`;
  }

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
        try { setSlotChained(scenesNow()[i], slot, await ctx.upload(input.files[0])); } catch (err) { scenesNow()[i].error = err.message; }
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
        setSlotChained(s, slot, name);
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
      setSlotChained(s, slot, pic);
      closePanel();
      touch();
    },
    async motion(i) {
      pending = { s: scenesNow()[i], i, motionPanel: true, sel: { motion: '', character: '', start: 0, end: 100, hint: '' }, lists: null, preview: null, busy: false, msg: '' };
      panel('<h4 style="margin:0 0 8px;color:#f6f8ff">Pose from the Motion Bank</h4><div id="nvMotion" style="max-height:78vh;overflow-y:auto">Loading…</div>');
      try {
        const [m, chars, gal] = await Promise.all([ctx.get('/motions'), ctx.get('/characters'), ctx.get('/gallery')]);
        const pics = [...(chars.characters || []).filter((c) => c.image).map((c) => ({ name: c.image, label: c.name })), ...(gal.images || []).slice().sort((a, b) => b.created_at - a.created_at).slice(0, 40).map((x) => ({ name: x.filename }))];
        pending.lists = { motions: m.motions || [], pics };
        drawMotionPanel();
      } catch (err) { document.getElementById('nvMotion').textContent = err.message; }
    },
    motionSelect(kind, value) { if (!pending || !pending.motionPanel) return; pending.sel[kind] = value; pending.preview = null; drawMotionPanel(); },
    motionField(kind, value) { if (pending && pending.motionPanel) { pending.sel[kind] = value; pending.preview = null; } },
    async motionRun(stylize) {
      if (!pending || !pending.motionPanel || pending.busy) return;
      let body;
      try { body = { ...motionRequest(pending.sel, pending.s), stylize }; } catch (err) { pending.msg = err.message; return drawMotionPanel(); }
      pending.busy = true; pending.msg = stylize ? 'Drawing the first and the last picture with your character… this takes a few minutes. Keep this window open.' : 'Drawing the two poses…';
      drawMotionPanel();
      try {
        const res = await ctx.post('/storyboard/motion_frames', body);
        if (!stylize) { pending.preview = res; pending.msg = `Poses at frames ${res.first_index} and ${res.last_index}.`; }
        else {
          applyMotionFrames(scenesNow(), pending.i, res, pending.sel);
          closePanel();
          return touch();
        }
      } catch (err) { pending.msg = err.message || String(err); }
      pending.busy = false;
      drawMotionPanel();
    },
    closePanel,
    async assembleSequence(options = {}) {
      const sc = scenesNow();
      if (!sc || !sc.length) {
        if (typeof alert === 'function') alert("No storyboard shots to assemble.");
        return;
      }

      panel(`
        <h4 style="margin:0 0 8px;color:#f6f8ff">Checking Shots for Assembly</h4>
        <div style="font-size:.82rem;color:#9aa6d0;margin-bottom:12px">Validating render status and resolutions…</div>
        <div class="spinner" style="margin:20px auto"></div>
      `);

      try {
        const readyCheck = await ctx.post('/storyboard/check_readiness', {
          scenes: sc,
          approved_only: !!options.approved_only,
        });

        if (!readyCheck.is_ready) {
          return panel(`
            <h4 style="margin:0 0 8px;color:#f6f8ff">Cannot Assemble Timeline</h4>
            <div class="nv-warn" style="margin-bottom:12px">Some shots are not ready for timeline concatenation:</div>
            <ul style="font-size:.82rem;color:#f87171;margin:0 0 16px 20px;text-align:left">
              ${readyCheck.problems.map((p) => `<li>${ctx.esc(p)}</li>`).join('')}
            </ul>
            <div class="nv-row" style="justify-content:flex-end;gap:8px">
              <button type="button" class="btn-tool" onclick="NewVideo.closePanel()">Close</button>
              <button type="button" class="btn-primary" style="width:auto;padding:6px 16px;background:#4f46e5;border-color:#4f46e5" onclick="NewVideo.assembleSequence({ approved_only: true })">Assemble Approved Only</button>
            </div>
          `);
        }

        panel(`
          <h4 style="margin:0 0 8px;color:#f6f8ff">🎬 Assembling Timeline Video</h4>
          <div style="font-size:.82rem;color:#9aa6d0;margin-bottom:12px">
            Normalizing mixed resolutions, letterboxing, and concatenating master stream…
          </div>
          <div class="spinner" style="margin:20px auto"></div>
        `);

        const title = (ctx.screenplay && ctx.screenplay() && ctx.screenplay().title) || 'Storyboard Master';
        const res = await ctx.post('/storyboard/assemble', {
          scenes: sc,
          title: title,
          approved_only: !!options.approved_only,
          create_sound_plan: true,
        });

        panel(`
          <h4 style="margin:0 0 8px;color:#f6f8ff">🎬 Sequence Assembly Complete</h4>
          <div style="font-size:.82rem;color:#46d6a3;margin-bottom:12px">
            ✓ Concatenated ${res.shot_count} shots &middot; ${res.duration} s &middot; ${res.width}×${res.height} @ ${res.fps} fps
          </div>
          <video src="${ctx.esc(res.master_video)}" controls autoplay style="width:100%;max-height:260px;border-radius:6px;background:#000;margin-bottom:14px"></video>
          <div class="nv-row" style="justify-content:space-between">
            <button type="button" class="btn-tool" onclick="NewVideo.closePanel()">Close</button>
            <div class="nv-row" style="gap:8px">
              <a href="${ctx.esc(res.master_video)}" download="${ctx.esc(res.filename)}" class="btn-tool" style="text-decoration:none;display:inline-flex;align-items:center;padding:6px 14px">⬇ Download</a>
              <button type="button" class="btn-primary" style="width:auto;padding:6px 14px;background:linear-gradient(135deg, #ec4899, #f43f5e);border:none" onclick="NewVideo.promptExportReel('${ctx.esc(res.master_video)}', '${ctx.esc(title)}')">
                📱 Export 9:16 Reel
              </button>
              ${res.sound_plan_id ? `
                <button type="button" class="btn-primary" style="width:auto;padding:6px 18px;background:linear-gradient(135deg, #4f46e5, #7c3aed);border:none" onclick="NewVideo.openInAudioStudio('${ctx.esc(res.master_video)}', '${ctx.esc(res.sound_plan_id)}')">
                  🎙 Open in Audio Studio
                </button>
              ` : ''}
            </div>
          </div>
        `);
      } catch (err) {
        panel(`
          <h4 style="margin:0 0 8px;color:#f6f8ff">Assembly Failed</h4>
          <div class="nv-error" style="margin-bottom:16px">${ctx.esc(err.message || String(err))}</div>
          <div class="nv-row" style="justify-content:flex-end">
            <button type="button" class="btn-tool" onclick="NewVideo.closePanel()">Close</button>
          </div>
        `);
      }
    },
    openInAudioStudio(videoUrl, planId) {
      closePanel();
      if (typeof window !== 'undefined' && typeof window.switchResolvePage === 'function') {
        window.switchResolvePage('audio');
      }
      if (typeof window !== 'undefined' && window.NLEAudio) {
        if (typeof window.NLEAudio.loadPlan === 'function') {
          window.NLEAudio.loadPlan(planId);
        } else if (typeof window.NLEAudio.openVideo === 'function') {
          window.NLEAudio.openVideo(videoUrl, planId);
        }
      }
    },
    promptExportReel(videoUrl, title) {
      const sp = (ctx.screenplay && ctx.screenplay()) || {};
      const hookDefault = sp.hook || title || 'An Epic Story';
      const transcript = (scenesNow() || []).map((s) => (s.narration || '').trim()).filter(Boolean).join(' ');
      panel(`
        <h4 style="margin:0 0 8px;color:#f6f8ff">📱 Export as 9:16 YouTube Short / Reel</h4>
        <div style="font-size:.82rem;color:#9aa6d0;margin-bottom:14px">
          Auto-crop horizontal video into vertical 1080×1920 with focal tracking, glowing karaoke subtitles, and -14 LUFS mastering.
        </div>
        <div style="display:flex;flex-direction:column;gap:12px;margin-bottom:16px;text-align:left">
          <div>
            <label style="display:block;font-size:.76rem;color:#cbd5e1;margin-bottom:4px">Top Hook Banner (First 2.5s)</label>
            <input type="text" id="nvReelHook" value="${ctx.esc(hookDefault)}" style="width:100%;padding:6px 10px;background:#1e293b;border:1px solid #334155;border-radius:4px;color:#fff;font-size:.82rem" />
          </div>
          <div style="display:flex;gap:12px">
            <div style="flex:1">
              <label style="display:block;font-size:.76rem;color:#cbd5e1;margin-bottom:4px">Reframing Camera</label>
              <select id="nvReelMode" style="width:100%;padding:6px;background:#1e293b;border:1px solid #334155;border-radius:4px;color:#fff;font-size:.82rem">
                <option value="shot_stable" selected>Shot Stable (Focal lock per shot)</option>
                <option value="smooth_pan">Smooth Pan (Continuous tracking)</option>
                <option value="center">Center Crop (Static)</option>
              </select>
            </div>
            <div style="flex:1;display:flex;align-items:flex-end;padding-bottom:4px">
              <label style="font-size:.8rem;color:#cbd5e1;display:flex;align-items:center;gap:6px;cursor:pointer">
                <input type="checkbox" id="nvReelSubs" checked /> Burn Karaoke Subtitles
              </label>
            </div>
          </div>
        </div>
        <div class="nv-row" style="justify-content:space-between">
          <button type="button" class="btn-tool" onclick="NewVideo.closePanel()">Cancel</button>
          <button type="button" class="btn-primary" style="width:auto;padding:6px 18px;background:linear-gradient(135deg, #ec4899, #f43f5e);border:none" onclick="NewVideo.executeExportReel('${ctx.esc(videoUrl)}', '${ctx.esc(title)}')">
            🚀 Render 9:16 Reel
          </button>
        </div>
      `);
    },
    async executeExportReel(videoUrl, title) {
      const hookInput = document.getElementById('nvReelHook');
      const modeSelect = document.getElementById('nvReelMode');
      const subsCheck = document.getElementById('nvReelSubs');

      const hookText = hookInput ? hookInput.value : '';
      const reframingMode = modeSelect ? modeSelect.value : 'shot_stable';
      const burnSubs = subsCheck ? subsCheck.checked : true;
      const transcript = (scenesNow() || []).map((s) => (s.narration || '').trim()).filter(Boolean).join(' ');

      panel(`
        <h4 style="margin:0 0 8px;color:#f6f8ff">🚀 Rendering 9:16 Reel</h4>
        <div style="font-size:.82rem;color:#9aa6d0;margin-bottom:12px">
          Tracking visual focus, formatting karaoke timing, and mastering audio…
        </div>
        <div class="spinner" style="margin:20px auto"></div>
      `);

      try {
        const res = await ctx.post('/reels/autocut', {
          input_video_path: videoUrl,
          hook_text: hookText,
          transcript: transcript,
          burn_subtitles: burnSubs,
          reframing_mode: reframingMode,
          title: title,
        });

        // Determine accessible web URL
        let reelWebUrl = res.output_video_path;
        if (reelWebUrl.includes('outputs')) {
          const fn = reelWebUrl.split(/[\\\\/]/).pop();
          reelWebUrl = `/chronoflow/outputs/${fn}`;
        }

        panel(`
          <h4 style="margin:0 0 8px;color:#f6f8ff">📱 9:16 Reel Ready</h4>
          <div style="font-size:.82rem;color:#46d6a3;margin-bottom:12px">
            ✓ 1080×1920 (9:16) &middot; ${res.duration_sec} s &middot; -14.0 LUFS mastered audio
          </div>
          <video src="${ctx.esc(reelWebUrl)}" controls autoplay style="width:100%;max-height:360px;border-radius:6px;background:#000;margin-bottom:14px"></video>
          <div style="font-size:.76rem;color:#94a3b8;margin-bottom:14px;background:#0f172a;padding:8px 12px;border-radius:4px;text-align:left">
            ✓ <b>PUBLISH.md</b> created with viral title, description, and AI disclosure tags.
          </div>
          <div class="nv-row" style="justify-content:space-between">
            <button type="button" class="btn-tool" onclick="NewVideo.closePanel()">Close</button>
            <a href="${ctx.esc(reelWebUrl)}" download="${ctx.esc(res.output_video_path.split(/[\\\\/]/).pop())}" class="btn-primary" style="width:auto;text-decoration:none;display:inline-flex;align-items:center;padding:6px 18px;background:linear-gradient(135deg, #ec4899, #f43f5e);border:none">
              ⬇ Download Reel
            </a>
          </div>
        `);
      } catch (err) {
        panel(`
          <h4 style="margin:0 0 8px;color:#f6f8ff">Reel Export Failed</h4>
          <div class="nv-error" style="margin-bottom:16px">${ctx.esc(err.message || String(err))}</div>
          <div class="nv-row" style="justify-content:flex-end">
            <button type="button" class="btn-tool" onclick="NewVideo.closePanel()">Close</button>
          </div>
        `);
      }
    },
  };

  // ---- the plan bar above the storyboard: draw the pictures, look at them, then render all the videos
  const plan = { state: null, timer: null, primed: new Set(), renderingAll: false, stop: false };
  const planMeta = () => { const sp = ctx && ctx.screenplay && ctx.screenplay(); return (sp && sp.anchor_images && sp.anchor_images.plan) || null; };
  function planBarHtml(meta, scenes) {
    const e = (ctx && ctx.esc) || ((v) => String(v));
    const c = pictureCounts(scenes), q = renderAllQueue(scenes), job = plan.state || {};
    const drawing = job.status === 'running';
    const videos = scenes.filter((s) => ['review', 'approved'].includes(displayState(s))).length;
    const canAssemble = videos >= 1;
    const assembleBtn = `<button type="button" class="btn-primary" ${canAssemble && !drawing && !plan.renderingAll ? '' : 'disabled'} onclick="NewVideo.assembleSequence()" style="width:auto;padding:5px 14px;font-size:.78rem;background:#4f46e5;border-color:#4f46e5" title="Assemble rendered shots into master video timeline">🎬 Assemble Video</button>`;
    const draw = `<button type="button" class="btn-primary" ${drawing || plan.renderingAll ? 'disabled' : ''} onclick="NewVideo.planDraw()" style="width:auto;padding:5px 14px;font-size:.78rem">${drawing ? '⏳ Drawing…' : (c.ready ? '↻ Draw the pictures again' : '🎨 Draw the pictures')}</button>`;
    const good = c.ready === c.takes && !meta.pictures_ok && !drawing ? `<button type="button" class="btn-tool" onclick="NewVideo.planApprovePictures()">✓ Pictures look good</button>` : '';
    const all = plan.renderingAll
      ? `<button type="button" class="btn-tool" onclick="NewVideo.planStop()">⏹ Stop after this shot</button>`
      : `<button type="button" class="btn-primary" ${meta.pictures_ok && q.run.length && !drawing ? '' : 'disabled'} onclick="NewVideo.planRenderAll()" style="width:auto;padding:5px 14px;font-size:.78rem" title="${meta.pictures_ok ? 'Render every shot that is ready, one after another' : 'Look at the pictures and approve them first'}">▶ Render all videos${q.run.length ? ` (${q.run.length})` : ''}</button>`;
    const waiting = q.waiting.length ? `<div class="nv-note">${q.waiting.length} shot${q.waiting.length === 1 ? '' : 's'} not ready: ${q.waiting.slice(0, 3).map((w) => `Shot ${w.i + 1} (${e(w.reason)})`).join('; ')}${q.waiting.length > 3 ? '…' : ''}</div>` : '';
    return `<div class="nv-bar"><div><b>📜 ${e(meta.title)}</b> &middot; ${meta.takes} shots &middot; ${meta.pictures} pictures &middot; ${meta.total_seconds} s &middot; ${e(meta.format)}</div>
      <div class="nv-row"><span>Pictures <b>${c.ready}/${c.takes}</b> shots &middot; videos <b>${videos}/${c.takes}</b></span>${draw}${good}${all}${assembleBtn}</div>
      ${drawing ? `<div class="nv-note">${e(job.message || '')} (${job.done_takes || 0}/${job.total_takes || c.takes} shots drawn)</div>` : ''}
      ${job.status === 'failed' ? `<div class="nv-error">Drawing the pictures failed: ${e(job.error || '')}</div>` : ''}${waiting}
      ${meta.narration === 'narrator' ? '<div class="nv-note">The narration text stays with each shot. Voice-over, captions and music are not produced from here yet.</div>' : ''}</div>`;
  }
  function renderPlanBar() {
    const el = document.getElementById('nvPlanBar');
    if (!el) return;
    const meta = planMeta();
    if (!meta) { el.style.display = 'none'; el.innerHTML = ''; return; }
    el.style.display = '';
    el.innerHTML = planBarHtml(meta, scenesNow());
    if (!plan.primed.has(meta.slug)) {  // after a reload: is the picture job still running, and did pictures arrive that were never saved?
      plan.primed.add(meta.slug);
      ctx.get('/plan/pictures/status?slug=' + encodeURIComponent(meta.slug)).then(async (s) => {
        plan.state = s;
        if (s.status === 'running') pollPlan(meta.slug);
        else if (applyPictureItems(scenesNow(), s.items || [], meta.slug)) await touch();
        else renderPlanBar();
      }).catch(() => {});
    }
  }
  function pollPlan(slug) {
    clearInterval(plan.timer);
    const tick = async () => {
      try {
        const s = await ctx.get('/plan/pictures/status?slug=' + encodeURIComponent(slug));
        plan.state = s;
        if (s.status !== 'running') clearInterval(plan.timer);
        if (applyPictureItems(scenesNow(), s.items || [], slug)) await touch(); else renderPlanBar();
      } catch (x) {
        clearInterval(plan.timer);
        plan.state = { status: 'failed', error: x.message || String(x), message: '', items: [] };
        renderPlanBar();
      }
    };
    plan.timer = setInterval(tick, 3000);
    tick();
  }
  async function planDraw() {
    const meta = planMeta();
    if (!meta) return;
    meta.pictures_ok = false;
    try {
      await ctx.post('/plan/pictures/start', { slug: meta.slug });
      plan.state = { status: 'running', message: 'Starting…', items: [], done_takes: 0, total_takes: meta.takes };
      pollPlan(meta.slug);
    } catch (x) { plan.state = { status: 'failed', error: x.message || String(x), message: '', items: [] }; }
    renderPlanBar();
  }
  function planApprovePictures() { const meta = planMeta(); if (meta) { meta.pictures_ok = true; touch(); } }
  async function planRenderAll() {
    if (plan.renderingAll) return;
    plan.renderingAll = true; plan.stop = false;
    renderPlanBar();
    try {
      for (;;) {
        const q = renderAllQueue(scenesNow());
        if (!q.run.length || plan.stop) break;
        const s = scenesNow()[q.run[0]];
        await render(q.run[0]);
        if (s.error) break; // a failed render stops the run: the same failure would repeat on every shot
      }
    } finally { plan.renderingAll = false; ctx.rerender(); }
  }

  const api = { SEG_SECONDS, MAX_SECONDS, slotsFor, segmentCount, lengthLabel, canRender, prevTail, markRendered, approve, markRedo, mount,
    applyPictureItems, pictureCounts, renderAllQueue, planResultHtml, planBarHtml, planDraw, planApprovePictures, planRenderAll, planStop() { plan.stop = true; }, renderPlanBar, getSlot, setSlot, relink, newCard, chainKeyframe, motionRequest, applyMotionFrames, __ctx(c) { ctx = c; }, displayState, effectiveMode, missingInputs, sizeWarning, setMode, modeLabel: (s, i) => MODE_LABEL[effectiveMode(s, i)], ...cardApi };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.NewVideo = api;
})(typeof window !== 'undefined' ? window : globalThis);
