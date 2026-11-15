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

  // ---- the wizard popup (markup lives in index.html: ids nvStep1..3 etc.)
  function mount(cfg) {
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

  const api = { SEG_SECONDS, MAX_SECONDS, slotsFor, segmentCount, lengthLabel, canRender, prevTail, markRendered, approve, markRedo, mount };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.NewVideo = api;
})(typeof window !== 'undefined' ? window : globalThis);
