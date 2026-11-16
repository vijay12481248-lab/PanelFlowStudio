/* ChronoFlow Audio Studio (Fairlight Workspace) Controller
   Multitrack cue sheet, real-time Web Audio graph, canvas waveforms, pointer dragging with cut snapping, mixer strips, and stem delivery. */
(function () {
  'use strict';

  const TRACK_ROLES = ['dialogue', 'music', 'sfx', 'ambience', 'foley'];
  const ROLE_COLORS = {
    dialogue: '#46d6a3',
    music: '#3b82f6',
    sfx: '#f0b35a',
    ambience: '#a855f7',
    foley: '#14b8a6'
  };

  const S = {
    open: false,
    planId: null,
    plan: null,
    selectedCueId: null,
    busy: false,
    auditionAudio: null,
    pps: 45, // pixels per second zoom
    waveforms: {}, // cueId -> [peaks]
    dragState: null,
    audioCtx: null,
    trackBuses: {},
    meterRaf: 0
  };

  let N = null, rootEl = null;

  const h = (tag, attrs, ...kids) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === 'class') e.className = v;
      else if (k === 'style') e.style.cssText = v;
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) e.setAttribute(k, v === true ? '' : v);
    }
    for (const c of kids.flat()) if (c != null) e.append(c.nodeType ? c : document.createTextNode(String(c)));
    return e;
  };

  const api = async (path, opt = {}) => {
    const res = await fetch(`/api/audio/studio${path}`, {
      headers: { 'Content-Type': 'application/json', ...(opt.headers || {}) },
      ...opt
    });
    const d = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(d.detail || d.error || `HTTP ${res.status}`);
    return d;
  };

  // ---------- Web Audio Engine Setup ----------
  function ensureAudioGraph() {
    if (S.audioCtx) {
      if (S.audioCtx.state === 'suspended') S.audioCtx.resume();
      return;
    }
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const masterGain = ctx.createGain();
      const masterAnalyser = ctx.createAnalyser();
      masterAnalyser.fftSize = 64;
      masterGain.connect(masterAnalyser);
      masterAnalyser.connect(ctx.destination);

      const buses = {};
      TRACK_ROLES.forEach(role => {
        const gainNode = ctx.createGain();
        const pannerNode = ctx.createStereoPanner ? ctx.createStereoPanner() : null;
        const filterNode = ctx.createBiquadFilter();
        filterNode.type = 'highpass';
        filterNode.frequency.value = 10;

        const analyserNode = ctx.createAnalyser();
        analyserNode.fftSize = 64;

        // Routing: source -> filter -> gain -> (panner) -> analyser -> masterGain
        filterNode.connect(gainNode);
        if (pannerNode) {
          gainNode.connect(pannerNode);
          pannerNode.connect(analyserNode);
        } else {
          gainNode.connect(analyserNode);
        }
        analyserNode.connect(masterGain);

        buses[role] = { gainNode, pannerNode, filterNode, analyserNode, buf: new Uint8Array(32) };
      });

      buses.master = { gainNode: masterGain, analyserNode: masterAnalyser, buf: new Uint8Array(32) };
      S.audioCtx = ctx;
      S.trackBuses = buses;
      startMeterLoop();
    } catch (e) {
      console.warn('Web Audio initialization error:', e);
    }
  }

  function applyTrackBuses() {
    if (!S.audioCtx || !S.plan || !S.plan.tracks) return;
    const hasSolo = S.plan.tracks.some(t => t.solo);
    S.plan.tracks.forEach(t => {
      const bus = S.trackBuses[t.id];
      if (!bus) return;
      const isMuted = t.mute || (hasSolo && !t.solo);
      const gainVal = isMuted ? 0 : Math.pow(10, (t.gain_db || 0) / 20);
      bus.gainNode.gain.setTargetAtTime(gainVal, S.audioCtx.currentTime, 0.02);

      if (bus.pannerNode && t.pan != null) {
        bus.pannerNode.pan.setTargetAtTime(Math.max(-1, Math.min(1, t.pan)), S.audioCtx.currentTime, 0.02);
      }
      if (bus.filterNode) {
        bus.filterNode.frequency.setTargetAtTime(t.hpf_hz && t.hpf_hz > 10 ? t.hpf_hz : 10, S.audioCtx.currentTime, 0.02);
      }
    });
  }

  function startMeterLoop() {
    if (S.meterRaf) cancelAnimationFrame(S.meterRaf);
    const tick = () => {
      if (!S.open) return;
      if (S.trackBuses && rootEl) {
        TRACK_ROLES.concat('master').forEach(key => {
          const bus = S.trackBuses[key];
          if (!bus) return;
          bus.analyserNode.getByteTimeDomainData(bus.buf);
          let sum = 0;
          for (let i = 0; i < bus.buf.length; i++) {
            const v = (bus.buf[i] - 128) / 128;
            sum += v * v;
          }
          const rms = Math.sqrt(sum / bus.buf.length);
          const pct = Math.min(100, Math.round(rms * 160));
          const el = rootEl.querySelector(`.audio-mixer-strip[data-strip="${key}"] .strip-meter-fill`);
          if (el) el.style.height = `${pct}%`;
        });
      }
      S.meterRaf = requestAnimationFrame(tick);
    };
    S.meterRaf = requestAnimationFrame(tick);
  }

  // ---------- Plan Loading & Initialisation ----------
  async function ensurePlan() {
    ensureAudioGraph();
    if (S.planId) {
      try {
        S.plan = await api(`/plans/${S.planId}`);
        applyTrackBuses();
        renderAll();
        return;
      } catch (e) {
        S.planId = null;
      }
    }
    let videoPath = null;
    if (N && N.tl && N.tl.clips && N.tl.clips.length) {
      videoPath = N.tl.clips[0].src;
    }
    if (!videoPath) {
      videoPath = 'output/chronoflow_active.mp4';
    }

    try {
      const created = await api('/plans', {
        method: 'POST',
        body: JSON.stringify({ video_path: videoPath, mode: 'auto' })
      });
      S.planId = created.id;
      S.plan = created;
      applyTrackBuses();
      renderAll();
    } catch (e) {
      console.warn('Could not auto-create audio plan, will render placeholder:', e.message);
      renderAll();
    }
  }

  // ---------- Waveform Extraction & Drawing ----------
  async function fetchCueWaveform(cue) {
    if (!S.planId || S.waveforms[cue.id]) return;
    if (!cue.chosen_take && (!cue.takes || !cue.takes.length)) return;
    try {
      const res = await api(`/plans/${S.planId}/cues/${cue.id}/waveform?bins=80`);
      if (res && res.peaks && res.peaks.length) {
        S.waveforms[cue.id] = res.peaks;
        const canvas = rootEl ? rootEl.querySelector(`.audio-cue-block[data-cue-id="${cue.id}"] canvas`) : null;
        if (canvas) drawWaveform(canvas, res.peaks, ROLE_COLORS[cue.track]);
      }
    } catch (e) {
      // quiet fallback
    }
  }

  function drawWaveform(canvas, peaks, color) {
    const w = canvas.width = canvas.parentElement.clientWidth;
    const h = canvas.height = canvas.parentElement.clientHeight;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, w, h);
    if (!peaks || !peaks.length) return;

    ctx.fillStyle = color || '#3b82f6';
    const barW = Math.max(1, w / peaks.length);
    const midY = h / 2;

    for (let i = 0; i < peaks.length; i++) {
      const barH = Math.max(2, peaks[i] * (h * 0.85));
      const x = i * barW;
      ctx.fillRect(x, midY - barH / 2, barW - 1, barH);
    }
  }

  // ---------- Toolbar Action Handlers ----------
  async function onSpot(useVision = false) {
    if (!S.planId) return;
    setBusy(true, useVision ? 'Analyzing keyframes with Vision AI...' : 'Spotting scene cuts with FFmpeg...');
    try {
      S.plan = await api(`/plans/${S.planId}/spot`, {
        method: 'POST',
        body: JSON.stringify({ use_vision: useVision })
      });
      applyTrackBuses();
      renderAll();
    } catch (e) {
      alert(`Spotting failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function onSourceAll() {
    if (!S.plan || !S.plan.cues.length) return;
    const drafts = S.plan.cues.filter(c => c.status === 'draft' || c.status === 'failed');
    if (!drafts.length) {
      alert('All cues have already been sourced.');
      return;
    }
    setBusy(true, `Sourcing ${drafts.length} cues...`);
    try {
      for (const c of drafts) {
        S.plan = await api(`/plans/${S.planId}/cues/${c.id}/source`, {
          method: 'POST',
          body: JSON.stringify({ mode: 'auto' })
        });
        renderAll();
      }
    } catch (e) {
      alert(`Sourcing failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function onRunQA() {
    if (!S.planId) return;
    setBusy(true, 'Running audio quality assurance & placement audit...');
    try {
      const res = await api(`/plans/${S.planId}/qa`, { method: 'POST' });
      S.plan = await api(`/plans/${S.planId}`);
      renderAll();
      alert(`QA Complete: ${res.errors} errors, ${res.warnings} warnings.`);
    } catch (e) {
      alert(`QA check failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function onCritique() {
    if (!S.planId) return;
    setBusy(true, 'Analyzing spectral mud, dialogue masking, and acoustic balance...');
    try {
      const res = await api(`/plans/${S.planId}/critique`, { method: 'POST' });
      S.critiqueReport = res;
      showCritiqueModal(res);
    } catch (e) {
      alert(`Critique failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function onApplyRemediations(remediationIds) {
    if (!S.planId || !remediationIds.length) return;
    setBusy(true, `Applying ${remediationIds.length} acoustic remediations...`);
    try {
      const res = await api(`/plans/${S.planId}/critique/apply`, {
        method: 'POST',
        body: JSON.stringify({ remediation_ids: remediationIds })
      });
      S.plan = res.plan;
      const updatedReport = await api(`/plans/${S.planId}/critique`, { method: 'POST' });
      S.critiqueReport = updatedReport;
      renderAll();
      showCritiqueModal(updatedReport);
    } catch (e) {
      alert(`Failed to apply fixes: ${e.message}`);
    } finally {
      setBusy(false);
    }
  }

  function showCritiqueModal(report) {
    const existing = document.getElementById('audioCritiqueModalBackdrop');
    if (existing) existing.remove();

    const score = report.overall_quality_score || 100;
    const scoreClass = score >= 85 ? 'critique-score-good' : (score >= 60 ? 'critique-score-warn' : 'critique-score-poor');
    const issues = report.issues || [];
    const remediations = report.remediations || [];

    const backdrop = h('div', { class: 'audio-modal-backdrop', id: 'audioCritiqueModalBackdrop' },
      h('div', { class: 'audio-critique-modal' },
        h('div', { class: 'audio-critique-header' },
          h('div', { class: 'audio-critique-title' },
            '🔬 Acoustic Quality Critique',
            h('span', { class: `critique-score-badge ${scoreClass}` }, `${score}/100 Score`)
          ),
          h('button', { class: 'audio-btn', onclick: () => backdrop.remove() }, '✕')
        ),
        h('div', { class: 'audio-critique-body' },
          issues.length === 0
            ? h('div', { style: 'text-align: center; color: #46d6a3; padding: 24px;' }, '✓ Perfect acoustic balance: no spectral mud, masking, or transient collisions detected!')
            : issues.map(iss => {
                const rem = iss.remediation;
                return h('div', { class: `critique-issue-card ${iss.severity}` },
                  h('div', { class: 'critique-issue-info' },
                    h('span', { class: 'critique-issue-title' }, `[${iss.track.toUpperCase()}] ${iss.message}`),
                    rem ? h('span', { class: 'critique-issue-msg' }, `Suggested Fix: ${rem.reason}`) : null
                  ),
                  rem ? h('div', { class: 'critique-issue-action' },
                    h('button', {
                      class: 'critique-fix-btn',
                      onclick: () => onApplyRemediations([rem.id])
                    }, `Fix ${rem.action.toUpperCase()} (${rem.value})`)
                  ) : null
                );
              })
        ),
        h('div', { class: 'audio-critique-footer' },
          h('span', { style: 'font-size: 0.74rem; color: #9aa6d0;' },
            `${issues.length} acoustic issues found · ${remediations.length} auto-fixes available`
          ),
          h('div', { style: 'display: flex; gap: 8px;' },
            remediations.length > 0 ? h('button', {
              class: 'audio-btn primary',
              onclick: () => onApplyRemediations(remediations.map(r => r.id))
            }, `⚡ Auto-Fix All (${remediations.length})`) : null,
            h('button', { class: 'audio-btn', onclick: () => backdrop.remove() }, 'Close')
          )
        )
      )
    );

    const mount = document.getElementById('audioStudioMount') || document.body;
    mount.appendChild(backdrop);
  }

  async function onMakeLoop(cueId) {
    if (!S.planId) return;
    setBusy(true, 'Generating seamless infinite loop with phase-aligned crossfade...');
    try {
      const res = await api(`/plans/${S.planId}/cues/${cueId}/loop`, { method: 'POST' });
      S.plan = res.plan;
      renderAll();
      alert(`Loop created! Duration: ${res.duration_s.toFixed(2)}s`);
    } catch (e) {
      alert(`Loop failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function onMixPreview() {
    if (!S.planId) return;
    setBusy(true, 'Rendering 48kHz stereo preview master & measuring loudness...');
    try {
      const res = await api(`/plans/${S.planId}/mix`, {
        method: 'POST',
        body: JSON.stringify({ target_lufs: -14.0, mux: false })
      });
      const loud = res.loudness || {};
      alert(`Mix Rendered: ${res.file}\nIntegrated: ${loud.integrated_lufs} LUFS\nTrue Peak: ${loud.true_peak_db} dBFS\nLRA: ${loud.lra} LU`);
      renderAll();
    } catch (e) {
      alert(`Mix preview failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function onExportStems() {
    if (!S.planId) return;
    setBusy(true, 'Exporting dialogue, music, effects, M&E stems, and cuesheet...');
    try {
      const res = await api(`/plans/${S.planId}/export`, {
        method: 'POST',
        body: JSON.stringify({ target_lufs: -14.0, mux: true, allow_incomplete: true })
      });
      alert(`Stems Exported to ${res.dir}:\nFiles: ${res.files.join(', ')}`);
      renderAll();
    } catch (e) {
      alert(`Export failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  }

  function setBusy(busy, msg = '') {
    S.busy = busy;
    const box = document.getElementById('audioStatusMessage');
    if (box) {
      box.textContent = msg || (S.plan ? `Plan v${S.plan.version} · ${S.plan.cues.length} Cues` : 'Audio Studio');
    }
    const btns = rootEl ? rootEl.querySelectorAll('.audio-btn') : [];
    btns.forEach(b => { if (b.id !== 'audioDismiss') b.disabled = busy; });
  }

  // ---------- Track & Cue Updates ----------
  async function updateCue(cueId, patch) {
    if (!S.planId) return;
    try {
      S.plan = await api(`/plans/${S.planId}`, {
        method: 'PUT',
        body: JSON.stringify({ cues: [{ id: cueId, ...patch }] })
      });
      renderAll();
    } catch (e) {
      console.error('Failed to update cue:', e);
    }
  }

  async function updateTrack(trackId, patch) {
    if (!S.planId) return;
    try {
      S.plan = await api(`/plans/${S.planId}`, {
        method: 'PUT',
        body: JSON.stringify({ tracks: [{ id: trackId, ...patch }] })
      });
      applyTrackBuses();
      renderAll();
    } catch (e) {
      console.error('Failed to update track:', e);
    }
  }

  async function pickCandidate(cueId, candidateId) {
    if (!S.planId) return;
    setBusy(true, 'Picking candidate...');
    try {
      S.plan = await api(`/plans/${S.planId}/cues/${cueId}/pick`, {
        method: 'POST',
        body: JSON.stringify({ candidate_id: candidateId })
      });
      delete S.waveforms[cueId];
      renderAll();
    } catch (e) {
      alert(`Pick failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  }

  // ---------- Interactive Drag & Magnetic Cut Snapping ----------
  function startCueDrag(e, cue, blockEl) {
    if (e.button !== 0) return; // primary click only
    e.stopPropagation();
    ensureAudioGraph();

    const startX = e.clientX;
    const initialT = cue.hit_t != null ? cue.hit_t : cue.t_in;
    const fps = S.plan ? S.plan.fps : 30;

    // Collect cut times for magnetic snapping
    const cuts = (S.plan && S.plan.cues)
      ? S.plan.cues.filter(c => c.id.startsWith('cut_') && c.hit_t != null).map(c => c.hit_t)
      : [];

    blockEl.classList.add('dragging');
    const tooltip = h('div', { class: 'audio-drag-tooltip' }, `Time: ${initialT.toFixed(2)}s`);
    document.body.appendChild(tooltip);

    let currentT = initialT;

    const onPointerMove = (ev) => {
      const dx = ev.clientX - startX;
      const dt = dx / S.pps;
      let targetT = Math.max(0, initialT + dt);

      // Frame snapping
      targetT = Math.round(targetT * fps) / fps;

      // Magnetic snapping to cut boundaries (threshold 0.15s)
      let snappedToCut = false;
      for (const cutT of cuts) {
        if (Math.abs(targetT - cutT) <= 0.15) {
          targetT = cutT;
          snappedToCut = true;
          break;
        }
      }

      currentT = targetT;
      const leftPx = targetT * S.pps;
      blockEl.style.left = `${leftPx}px`;

      tooltip.textContent = `Time: ${targetT.toFixed(2)}s ${snappedToCut ? '🧲 SNAP CUT' : ''}`;
      tooltip.style.left = `${ev.clientX}px`;
      tooltip.style.top = `${ev.clientY}px`;
    };

    const onPointerUp = async (ev) => {
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
      blockEl.classList.remove('dragging');
      if (tooltip.parentNode) tooltip.parentNode.removeChild(tooltip);

      if (Math.abs(currentT - initialT) > 0.01) {
        const patch = cue.hit_t != null ? { hit_t: currentT } : { t_in: currentT };
        await updateCue(cue.id, patch);
      }
    };

    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
  }

  // ---------- Audition Audio ----------
  function auditionCandidate(takePath) {
    if (S.auditionAudio) {
      S.auditionAudio.pause();
      S.auditionAudio = null;
    }
    if (!takePath) return;
    const url = `/api/audio/studio/plans/${S.planId}/files/${encodeURIComponent(takePath.replace(/\\/g, '/').split('/').slice(-2).join('/'))}`;
    S.auditionAudio = new Audio(url);
    S.auditionAudio.play().catch(e => console.warn('Audition playback error:', e));
  }

  // ---------- Rendering Components ----------
  function renderAll() {
    if (!rootEl) return;
    rootEl.textContent = '';

    const plan = S.plan;
    const cues = plan ? plan.cues : [];
    const totalDuration = plan ? plan.duration : (N ? N.total() : 60);

    // 1. Toolbar
    const toolbar = h('div', { class: 'audio-toolbar' },
      h('div', { class: 'audio-tb-left' },
        h('span', { class: 'audio-title-badge', id: 'audioStatusMessage' },
          plan ? `Plan v${plan.version} · ${cues.length} Cues` : 'Audio Studio'
        ),
        h('button', { class: 'audio-btn', onclick: () => onSpot(false), title: 'Detect cuts with FFmpeg and draft transition whooshes' }, '⚡ Spot Cuts'),
        h('button', { class: 'audio-btn', onclick: () => onSpot(true), title: 'Inspect keyframes with Ollama Qwen 3.5 9B vision to draft sounds' }, '👁️ Vision Spot'),
        h('button', { class: 'audio-btn', onclick: onSourceAll, title: 'Automatically source all draft and failed cues' }, '🎵 Source All'),
        h('button', { class: 'audio-btn', onclick: onRunQA, title: 'Check placement error (ms), clipping, and silence' }, '🔍 Run QA'),
        h('button', { class: 'audio-btn', onclick: onCritique, title: 'Analyze spectral mud, dialogue masking, and apply 1-click acoustic remediations' }, '🔬 Acoustic Critique')
      ),
      h('div', { class: 'audio-tb-right' },
        h('button', { class: 'audio-btn primary', onclick: onMixPreview, title: 'Mix preview to 48kHz stereo WAV with -14 LUFS loudness' }, '🎛️ Preview Mix'),
        h('button', { class: 'audio-btn', onclick: onExportStems, title: 'Export DX/MX/SFX/M&E stems and cuesheet' }, '📦 Export Stems')
      )
    );

    // 2. Main Layout (Timeline + Mixer + Inspector)
    const mainLayout = h('div', { class: 'audio-main-layout' });

    // 2a. Multitrack Lanes Deck
    const timelineDeck = h('div', { class: 'audio-timeline-deck' });
    const ruler = h('div', { class: 'audio-timeline-ruler' },
      `Timeline Duration: ${totalDuration.toFixed(2)}s · Snap: Frame (${plan ? plan.fps : 30} fps) · Drag blocks to reposition · Magnetic cut snapping enabled`
    );
    timelineDeck.appendChild(ruler);

    const lanesScroll = h('div', { class: 'audio-lanes-scroll' });

    TRACK_ROLES.forEach(role => {
      const trackObj = (plan && plan.tracks) ? plan.tracks.find(t => t.id === role) : null;
      const row = h('div', { class: 'audio-track-row' });

      // Track Header
      const header = h('div', { class: 'audio-track-header' },
        h('div', { class: 'audio-th-title' },
          h('span', { class: 'audio-th-strip', style: `background: ${ROLE_COLORS[role]}` }),
          role.toUpperCase()
        ),
        h('div', { class: 'audio-th-controls' },
          h('button', {
            class: `audio-toggle-btn mute ${trackObj && trackObj.mute ? 'active' : ''}`,
            onclick: () => updateTrack(role, { mute: !trackObj || !trackObj.mute })
          }, 'M'),
          h('button', {
            class: `audio-toggle-btn solo ${trackObj && trackObj.solo ? 'active' : ''}`,
            onclick: () => updateTrack(role, { solo: !trackObj || !trackObj.solo })
          }, 'S')
        )
      );

      // Track Canvas / Lane
      const canvas = h('div', { class: 'audio-lane-canvas' });
      const roleCues = cues.filter(c => c.track === role);

      roleCues.forEach(c => {
        const start = c.hit_t != null ? Math.max(0, c.hit_t - (c.anchor === 'peak' ? 0.6 : 0.05)) : c.t_in;
        const dur = (c.t_out != null && c.t_out > c.t_in) ? (c.t_out - c.t_in) : 1.2;
        const leftPx = start * S.pps;
        const widthPx = Math.max(34, dur * S.pps);

        const syncErr = c.placement_error_ms;
        const syncBadge = syncErr != null ? h('span', {
          class: `audio-sync-badge ${syncErr > 40 ? 'error' : (syncErr > 20 ? 'warn' : '')}`
        }, `±${syncErr.toFixed(1)}ms`) : null;

        const waveCanvas = h('canvas', { class: 'audio-cue-canvas' });

        const cueBlock = h('div', {
          class: `audio-cue-block ${S.selectedCueId === c.id ? 'selected' : ''}`,
          'data-cue-id': c.id,
          style: `left: ${leftPx}px; width: ${widthPx}px; border-color: ${ROLE_COLORS[role]};`,
          onpointerdown: (e) => startCueDrag(e, c, cueBlock),
          onclick: (e) => {
            e.stopPropagation();
            S.selectedCueId = c.id;
            renderAll();
          }
        },
          waveCanvas,
          h('div', { class: 'audio-cue-inner' },
            h('div', { class: 'audio-cue-label' }, c.intent || c.kind || c.id),
            h('div', { class: 'audio-cue-sub' },
              h('span', {}, c.status),
              syncBadge
            )
          )
        );

        canvas.appendChild(cueBlock);

        // Fetch waveform if available
        if (S.waveforms[c.id]) {
          setTimeout(() => drawWaveform(waveCanvas, S.waveforms[c.id], ROLE_COLORS[role]), 0);
        } else {
          fetchCueWaveform(c);
        }
      });

      row.append(header, canvas);
      lanesScroll.appendChild(row);
    });

    timelineDeck.appendChild(lanesScroll);

    // 2b. Mixer Deck
    const mixerDeck = h('div', { class: 'audio-mixer-deck' });
    TRACK_ROLES.forEach(role => {
      const trackObj = (plan && plan.tracks) ? plan.tracks.find(t => t.id === role) : null;
      const gain = trackObj ? trackObj.gain_db : 0;
      const pan = trackObj ? trackObj.pan : 0;

      const fader = h('input', {
        type: 'range',
        class: 'strip-fader',
        min: -60,
        max: 12,
        step: 0.5,
        value: gain,
        onchange: (e) => updateTrack(role, { gain_db: +e.target.value })
      });

      const panPot = h('input', {
        type: 'range',
        class: 'strip-pan-input',
        min: -1,
        max: 1,
        step: 0.1,
        value: pan,
        onchange: (e) => updateTrack(role, { pan: +e.target.value })
      });

      const strip = h('div', { class: 'audio-mixer-strip', 'data-strip': role },
        h('span', { class: 'strip-name', style: `color: ${ROLE_COLORS[role]}` }, role.slice(0, 3).toUpperCase()),
        h('div', { class: 'strip-pan' },
          h('span', { class: 'strip-pan-label' }, pan === 0 ? 'C' : (pan < 0 ? `L${Math.round(-pan*100)}` : `R${Math.round(pan*100)}`)),
          panPot
        ),
        h('div', { class: 'strip-fader-wrap' },
          fader,
          h('div', { class: 'strip-meter' }, h('div', { class: 'strip-meter-fill', style: 'height: 0%' }))
        ),
        h('span', { class: 'strip-db-readout' }, `${gain > 0 ? '+' : ''}${gain}dB`)
      );
      mixerDeck.appendChild(strip);
    });

    // Master Strip
    const masterStrip = h('div', { class: 'audio-mixer-strip master', 'data-strip': 'master' },
      h('span', { class: 'strip-name', style: 'color: #fff' }, 'MASTER'),
      h('div', { class: 'strip-pan' }, h('span', { class: 'strip-pan-label' }, '-14 LUFS')),
      h('div', { class: 'strip-fader-wrap' },
        h('input', { type: 'range', class: 'strip-fader', min: -60, max: 6, step: 0.5, value: 0 }),
        h('div', { class: 'strip-meter' }, h('div', { class: 'strip-meter-fill', style: 'height: 0%' }))
      ),
      h('span', { class: 'strip-db-readout' }, '0.0dB')
    );
    mixerDeck.appendChild(masterStrip);

    // 2c. Cue Inspector Deck
    const inspectorDeck = h('div', { class: 'audio-inspector-deck' });
    const selectedCue = cues.find(c => c.id === S.selectedCueId);

    if (selectedCue) {
      inspectorDeck.append(
        h('div', { class: 'insp-section-title' },
          h('span', {}, `Cue: ${selectedCue.id}`),
          h('span', { style: `color: ${ROLE_COLORS[selectedCue.track]}` }, selectedCue.track.toUpperCase())
        ),
        h('div', { class: 'insp-field' },
          h('label', {}, 'Sound Intent Description'),
          h('input', {
            type: 'text',
            class: 'insp-input',
            value: selectedCue.intent || '',
            onchange: (e) => updateCue(selectedCue.id, { intent: e.target.value })
          })
        ),
        h('div', { class: 'insp-row' },
          h('div', { class: 'insp-field', style: 'flex: 1;' },
            h('label', {}, 'Hit Time (s)'),
            h('input', {
              type: 'number',
              step: '0.01',
              class: 'insp-input',
              value: selectedCue.hit_t != null ? selectedCue.hit_t : '',
              onchange: (e) => updateCue(selectedCue.id, { hit_t: +e.target.value })
            })
          ),
          h('div', { class: 'insp-field', style: 'flex: 1;' },
            h('label', {}, 'Anchor Mode'),
            h('select', {
              class: 'insp-select',
              onchange: (e) => updateCue(selectedCue.id, { anchor: e.target.value })
            },
              h('option', { value: 'onset', selected: selectedCue.anchor === 'onset' }, 'Onset (Attack)'),
              h('option', { value: 'peak', selected: selectedCue.anchor === 'peak' }, 'Peak (Swell)')
            )
          )
        ),
        h('div', { class: 'insp-section-title', style: 'margin-top: 6px;' }, 'DSP & Spatial Controls'),
        h('div', { class: 'insp-row' },
          h('div', { class: 'insp-field', style: 'flex: 1;' },
            h('label', {}, `Pan (${selectedCue.pan || 0})`),
            h('input', {
              type: 'range', min: -1, max: 1, step: 0.05, value: selectedCue.pan || 0,
              onchange: (e) => updateCue(selectedCue.id, { pan: +e.target.value })
            })
          ),
          h('div', { class: 'insp-field', style: 'flex: 1;' },
            h('label', {}, `Pitch (${selectedCue.pitch_semitones || 0} st)`),
            h('input', {
              type: 'range', min: -12, max: 12, step: 1, value: selectedCue.pitch_semitones || 0,
              onchange: (e) => updateCue(selectedCue.id, { pitch_semitones: +e.target.value })
            })
          )
        ),
        h('div', { class: 'insp-row' },
          h('div', { class: 'insp-field', style: 'flex: 1;' },
            h('label', {}, `Gain (${selectedCue.gain_db || 0} dB)`),
            h('input', {
              type: 'range', min: -30, max: 12, step: 0.5, value: selectedCue.gain_db || 0,
              onchange: (e) => updateCue(selectedCue.id, { gain_db: +e.target.value })
            })
          ),
          h('div', { class: 'insp-field', style: 'flex: 1;' },
            h('label', {}, `HPF Cutoff (${selectedCue.hpf_hz || 'Off'} Hz)`),
            h('input', {
              type: 'range', min: 0, max: 500, step: 20, value: selectedCue.hpf_hz || 0,
              onchange: (e) => updateCue(selectedCue.id, { hpf_hz: +e.target.value > 10 ? +e.target.value : null })
            })
          )
        ),
        h('div', { class: 'insp-section-title', style: 'margin-top: 6px;' }, 'Take Candidates (A/B)'),
        selectedCue.track === 'music' && selectedCue.chosen_take ? h('div', { style: 'margin-bottom: 8px;' },
          h('button', {
            class: 'audio-btn',
            style: 'width: 100%; justify-content: center;',
            onclick: () => onMakeLoop(selectedCue.id),
            title: 'Equal-power crossfade to create seamless infinite loop'
          }, '🔁 Convert to Seamless Loop')
        ) : null,
        h('div', { style: 'display: flex; flex-direction: column; gap: 8px;' },
          (selectedCue.candidates.length ? selectedCue.candidates : selectedCue.takes).map(cand => {
            const isChosen = selectedCue.chosen_take === cand.id;
            return h('div', { class: `candidate-card ${isChosen ? 'chosen' : ''}` },
              h('div', { class: 'cand-title-row' },
                h('span', { class: 'cand-label' }, cand.label || cand.id),
                h('span', { class: 'cand-lic-tag' }, (cand.provenance && cand.provenance.licence) || 'CC0')
              ),
              h('div', { style: 'display: flex; gap: 6px; margin-top: 4px;' },
                h('button', {
                  class: 'audio-btn',
                  style: 'flex: 1; padding: 4px;',
                  onclick: () => auditionCandidate(cand.path)
                }, '▶ Audition'),
                !isChosen ? h('button', {
                  class: 'audio-btn primary',
                  style: 'flex: 1; padding: 4px;',
                  onclick: () => pickCandidate(selectedCue.id, cand.id)
                }, '✓ Pick Take') : h('span', { style: 'color: #46d6a3; font-weight: 700; font-size: 0.72rem; align-self: center;' }, '✓ Active Take')
              )
            );
          })
        )
      );
    } else {
      inspectorDeck.append(
        h('div', { class: 'insp-section-title' }, 'Cue Inspector'),
        h('p', { style: 'font-size: 0.75rem; color: #9aa6d0; line-height: 1.5;' },
          'Select or drag any cue block on the timeline lanes to reposition, audition candidates, adjust stereo panning, pitch tuning, and DSP filters.'
        )
      );
    }

    mainLayout.append(timelineDeck, mixerDeck, inspectorDeck);
    rootEl.append(toolbar, mainLayout);
  }

  // ---------- Public Module API ----------
  window.NLEAudio = {
    mount(cfg) {
      N = cfg || window.NLE;
      let mountEl = document.getElementById('audioStudioMount');
      if (!mountEl) {
        mountEl = document.createElement('div');
        mountEl.id = 'audioStudioMount';
        const ws = document.getElementById('cfWorkspace');
        if (ws) ws.appendChild(mountEl);
      }
      mountEl.className = 'audio-studio-wrapper';
      rootEl = mountEl;
    },
    open() {
      S.open = true;
      if (rootEl) rootEl.style.display = 'flex';
      ensurePlan();
    },
    close() {
      S.open = false;
      if (S.auditionAudio) {
        S.auditionAudio.pause();
        S.auditionAudio = null;
      }
      if (S.meterRaf) {
        cancelAnimationFrame(S.meterRaf);
        S.meterRaf = 0;
      }
      if (rootEl) rootEl.style.display = 'none';
    }
  };
})();
