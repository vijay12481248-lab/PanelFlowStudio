/**
 * Watermark Studio - Video Watermark & Logo Removal Tool
 * ChronoFlow NLE Module.
 */
(function() {
  'use strict';

  const S = {
    videoFile: null,
    videoPath: '',
    videoUrl: '',
    videoEl: null,
    selectionLayer: null,
    duration: 0,
    currentTime: 0,
    isPlaying: false,
    box: null,
    isDrawing: false,
    dragStart: null,
    mode: 'auto',
    featherPx: 3,
    jobId: null,
    isProcessing: false,
    previewData: null,
    candidates: [],
    pollTimer: null
  };

  function getToken() {
    return localStorage.getItem('panelflow_engine_token') || '';
  }

  function apiHeaders() {
    const h = { 'Content-Type': 'application/json' };
    const t = getToken();
    if (t) h['X-PanelFlow-Token'] = t;
    return h;
  }

  function formatTime(s) {
    if (!s || isNaN(s)) return '0:00.0';
    const m = Math.floor(s / 60);
    const sec = (s % 60).toFixed(1);
    return `${m}:${sec.padStart(4, '0')}`;
  }

  function mount(root) {
    if (!root) return;
    root.innerHTML = `
      <div class="wm-root">
        <!-- Left: Media & File Import -->
        <div class="wm-lib">
          <div class="wm-h">Video Sources</div>
          <label class="wm-drop" id="wmDropZone">
            <input type="file" id="wmFileInput" accept="video/mp4,video/quicktime,video/webm,video/x-matroska,video/*" style="display:none" />
            <span style="font-size: 1.5rem">📂</span>
            <b>Drop a video file here</b>
            <span>or click to browse from PC (.mp4, .mov, .mkv, .webm)</span>
          </label>

          <div class="wm-h" style="margin-top: 10px;">Current File</div>
          <div id="wmFileInfo" style="color: #9aa6d0; line-height: 1.5; font-size: 0.72rem;">
            No video loaded. Drop a file above to begin.
          </div>

          <div class="wm-h" style="margin-top: 10px;">Detected Candidates</div>
          <div id="wmCandidatesList" style="display: flex; flex-direction: column; gap: 4px; overflow-y: auto; max-height: 180px;">
            <span style="color: #6a76a3;">No scan performed yet.</span>
          </div>
        </div>

        <!-- Center: Video Canvas Stage -->
        <div class="wm-editor">
          <div class="wm-head">
            <h3 class="wm-title" id="wmVideoTitle">AI Watermark Remover - Interactive Studio</h3>
            <div style="display: flex; gap: 6px;">
              <button type="button" class="btn-tool" id="wmToggleCompareBtn" style="display:none">↔ Split Wipe</button>
            </div>
          </div>

          <div class="wm-stage" id="wmStage">
            <div class="wm-canvas-wrap" id="wmCanvasWrap" style="display:none">
              <video id="wmVideo" class="wm-video" playsinline></video>
              <div id="wmSelectionLayer" class="wm-selection-layer">
                <div id="wmBoxOverlay" class="wm-box-overlay" style="display:none">
                  <span id="wmBoxTag" class="wm-box-tag">Target Watermark</span>
                </div>
              </div>
            </div>

            <!-- Empty Placeholder -->
            <div id="wmEmptyStage" style="display: flex; flex-direction: column; align-items: center; gap: 10px; color: #6a76a3;">
              <span style="font-size: 2.2rem">🎬</span>
              <b>Load a video to preview and remove watermarks</b>
              <span>Drag & drop onto this area or click Browse on the left</span>
            </div>
          </div>

          <!-- Transport bar -->
          <div class="wm-transport" id="wmTransport">
            <button type="button" class="btn-tool" id="wmPlayBtn" disabled>▶ Play</button>
            <input type="range" class="wm-scrub" id="wmScrubBar" min="0" max="100" value="0" step="0.05" disabled />
            <span class="wm-time" id="wmTimeReadout">0:00.0 / 0:00.0</span>
          </div>
        </div>

        <!-- Right: AI Controls & Actions -->
        <div class="wm-side">
          <div class="wm-h">AI Parameters & Actions</div>
          <div class="wm-side-content">
            <!-- Algorithm -->
            <div class="wm-group">
              <span class="wm-group-h">Removal Algorithm</span>
              <select class="wm-select" id="wmAlgoSelect">
                <option value="auto">Auto (Algebraic Backdrop Inversion - Zero Blur)</option>
                <option value="inverse_alpha">Inverse Alpha (Transparent Bug - 100% Exact)</option>
                <option value="flow_guided">Flow-Guided AI (Opaque / Moving Camera)</option>
              </select>
              <span id="wmAlgoDesc" style="color: #8590bb; font-size: 0.70rem; line-height: 1.35;">
                Reconstructs authentic background pixels along motion trajectories with zero blur.
              </span>
            </div>

            <!-- Boundary Feathering -->
            <div class="wm-group">
              <div style="display: flex; justify-content: space-between; font-weight: 700; font-size: 0.74rem;">
                <span class="wm-group-h">Edge Feathering</span>
                <span id="wmFeatherVal" style="color: #7aa2ff;">3 px</span>
              </div>
              <input type="range" id="wmFeatherRange" min="0" max="12" value="3" step="1" style="accent-color: #3b6bf5" />
              <span style="color: #8590bb; font-size: 0.70rem;">Softens boundary seam so inpainting blends flawlessly into original video.</span>
            </div>

            <!-- Target Region Box Info -->
            <div class="wm-group">
              <span class="wm-group-h">Watermark Region</span>
              <div id="wmRegionInfo" style="color: #d5dcf5; font-family: monospace; font-size: 0.74rem;">
                No region selected. (Drag on video)
              </div>
            </div>

            <!-- Action Buttons -->
            <div style="display: flex; gap: 8px;">
              <button type="button" class="btn-tool" id="wmAutoDetectBtn" style="flex: 1; justify-content: center;" disabled>
                ⚡ Auto-Detect
              </button>
              <button type="button" class="btn-tool" id="wmPreviewBtn" style="flex: 1; justify-content: center;" disabled>
                👁 Preview Frame
              </button>
            </div>

            <!-- Primary Execution Button -->
            <button type="button" class="cfx-primary" id="wmRunBtn" style="padding: 10px; font-weight: 800; justify-content: center; width: 100%; font-size: 0.8rem;" disabled>
              💧 Remove Watermark (Zero Blur)
            </button>

            <!-- Progress Banner -->
            <div class="wm-progress-wrap" id="wmProgressWrap" style="display:none">
              <div style="display: flex; justify-content: space-between; font-weight: 700; font-size: 0.74rem; color: #7aa2ff;">
                <span id="wmProgressText">Processing video frames...</span>
                <span id="wmProgressPct">0%</span>
              </div>
              <div class="wm-progress-bar">
                <div class="wm-progress-fill" id="wmProgressFill" style="width: 0%"></div>
              </div>
            </div>

            <!-- Success Outcome -->
            <div id="wmSuccessWrap" style="display: none; padding: 10px; background: rgba(70, 214, 163, 0.15); border: 1px solid #46d6a3; border-radius: 6px; color: #46d6a3; flex-direction: column; gap: 6px;">
              <b style="color: #fff">✓ Watermark Removed Successfully!</b>
              <span style="font-size: 0.72rem; color: #d5dcf5;" id="wmSuccessPath"></span>
              <button type="button" class="btn-tool" id="wmPlayCleanedBtn" style="background: #46d6a3; color: #000; font-weight: 800; justify-content: center; margin-top: 4px;">
                ▶ Play Cleaned Video
              </button>
            </div>

          </div>
        </div>
      </div>
    `;

    bindEvents(root);
  }

  function bindEvents(root) {
    const video = root.querySelector('#wmVideo');
    const wrap = root.querySelector('#wmCanvasWrap');
    const selectionLayer = root.querySelector('#wmSelectionLayer');
    const emptyStage = root.querySelector('#wmEmptyStage');
    const fileInput = root.querySelector('#wmFileInput');
    const dropZone = root.querySelector('#wmDropZone');
    const playBtn = root.querySelector('#wmPlayBtn');
    const scrub = root.querySelector('#wmScrubBar');
    const timeReadout = root.querySelector('#wmTimeReadout');
    const fileInfo = root.querySelector('#wmFileInfo');
    const regionInfo = root.querySelector('#wmRegionInfo');
    const boxOverlay = root.querySelector('#wmBoxOverlay');
    const boxTag = root.querySelector('#wmBoxTag');
    const autoDetectBtn = root.querySelector('#wmAutoDetectBtn');
    const previewBtn = root.querySelector('#wmPreviewBtn');
    const runBtn = root.querySelector('#wmRunBtn');
    const algoSelect = root.querySelector('#wmAlgoSelect');
    const featherRange = root.querySelector('#wmFeatherRange');
    const featherVal = root.querySelector('#wmFeatherVal');
    const progressWrap = root.querySelector('#wmProgressWrap');
    const progressText = root.querySelector('#wmProgressText');
    const progressPct = root.querySelector('#wmProgressPct');
    const progressFill = root.querySelector('#wmProgressFill');
    const successWrap = root.querySelector('#wmSuccessWrap');
    const successPath = root.querySelector('#wmSuccessPath');
    const playCleanedBtn = root.querySelector('#wmPlayCleanedBtn');

    S.videoEl = video;
    S.selectionLayer = selectionLayer;

    // Drag and drop handler
    function handleDropFile(file) {
      if (!file) return;
      S.videoFile = file;
      const url = URL.createObjectURL(file);
      S.videoUrl = url;

      uploadToEngine(file);

      video.src = url;
      video.load();
      wrap.style.display = 'flex';
      emptyStage.style.display = 'none';
      playBtn.disabled = false;
      scrub.disabled = false;
      autoDetectBtn.disabled = false;

      fileInfo.innerHTML = `
        <b style="color: #eef1ff">${file.name}</b><br>
        Size: ${(file.size / (1024 * 1024)).toFixed(1)} MB
      `;
    }

    async function uploadToEngine(file) {
      const formData = new FormData();
      formData.append('file', file);
      try {
        const res = await fetch('/api/video/watermark/upload', {
          method: 'POST',
          headers: getToken() ? { 'X-PanelFlow-Token': getToken() } : {},
          body: formData
        });
        if (res.ok) {
          const data = await res.json();
          S.videoPath = data.video_path;
        }
      } catch (err) {
        console.warn('Video staging failed:', err);
      }
    }

    // Dropzone listeners
    dropZone.ondragover = (e) => { e.preventDefault(); dropZone.classList.add('over'); };
    dropZone.ondragleave = () => dropZone.classList.remove('over');
    dropZone.ondrop = (e) => {
      e.preventDefault();
      dropZone.classList.remove('over');
      if (e.dataTransfer && e.dataTransfer.files[0]) {
        handleDropFile(e.dataTransfer.files[0]);
      }
    };
    fileInput.onchange = (e) => {
      if (e.target.files && e.target.files[0]) {
        handleDropFile(e.target.files[0]);
      }
    };

    // Stage dropzone
    const stage = root.querySelector('#wmStage');
    stage.ondragover = (e) => { e.preventDefault(); };
    stage.ondrop = (e) => {
      e.preventDefault();
      if (e.dataTransfer && e.dataTransfer.files[0]) {
        handleDropFile(e.dataTransfer.files[0]);
      }
    };

    // Video events for smooth 60fps native playback
    video.onloadedmetadata = () => {
      S.duration = video.duration || 0;
      scrub.max = S.duration;
      timeReadout.textContent = `0:00.0 / ${formatTime(S.duration)}`;
      if (video.videoWidth && video.videoHeight) {
        wrap.style.aspectRatio = `${video.videoWidth} / ${video.videoHeight}`;
      }
      updateBoxVisual();
    };

    video.ontimeupdate = () => {
      S.currentTime = video.currentTime;
      scrub.value = S.currentTime;
      timeReadout.textContent = `${formatTime(S.currentTime)} / ${formatTime(S.duration)}`;
    };

    video.onended = () => {
      playBtn.textContent = '▶ Play';
    };

    // Transport controls
    playBtn.onclick = () => {
      if (video.paused) {
        video.play();
        playBtn.textContent = '❚❚ Pause';
      } else {
        video.pause();
        playBtn.textContent = '▶ Play';
      }
    };

    scrub.oninput = (e) => {
      video.pause();
      playBtn.textContent = '▶ Play';
      video.currentTime = parseFloat(e.target.value);
    };

    // Mouse selection layer
    selectionLayer.onmousedown = (e) => {
      const rect = selectionLayer.getBoundingClientRect();
      const scaleX = (video.videoWidth || 640) / rect.width;
      const scaleY = (video.videoHeight || 360) / rect.height;
      S.dragStart = {
        x: Math.round((e.clientX - rect.left) * scaleX),
        y: Math.round((e.clientY - rect.top) * scaleY)
      };
      S.isDrawing = true;
    };

    window.addEventListener('mousemove', (e) => {
      if (!S.isDrawing || !S.dragStart || !selectionLayer) return;
      const rect = selectionLayer.getBoundingClientRect();
      const scaleX = (video.videoWidth || 640) / rect.width;
      const scaleY = (video.videoHeight || 360) / rect.height;

      const currX = Math.round((e.clientX - rect.left) * scaleX);
      const currY = Math.round((e.clientY - rect.top) * scaleY);

      const x = Math.max(0, Math.min(S.dragStart.x, currX));
      const y = Math.max(0, Math.min(S.dragStart.y, currY));
      const width = Math.max(8, Math.min((video.videoWidth || 640) - x, Math.abs(currX - S.dragStart.x)));
      const height = Math.max(8, Math.min((video.videoHeight || 360) - y, Math.abs(currY - S.dragStart.y)));

      S.box = { x, y, width, height };
      updateBoxVisual();
      previewBtn.disabled = false;
      runBtn.disabled = false;
    });

    window.addEventListener('mouseup', () => {
      S.isDrawing = false;
      S.dragStart = null;
    });

    function updateBoxVisual() {
      if (!S.box || !video || !video.videoWidth) {
        boxOverlay.style.display = 'none';
        regionInfo.textContent = 'No region selected. (Drag on video)';
        return;
      }
      boxOverlay.style.display = 'block';
      const pctL = (S.box.x / video.videoWidth) * 100;
      const pctT = (S.box.y / video.videoHeight) * 100;
      const pctW = (S.box.width / video.videoWidth) * 100;
      const pctH = (S.box.height / video.videoHeight) * 100;

      boxOverlay.style.left = `${pctL}%`;
      boxOverlay.style.top = `${pctT}%`;
      boxOverlay.style.width = `${pctW}%`;
      boxOverlay.style.height = `${pctH}%`;

      boxTag.textContent = `Target [${S.box.x}, ${S.box.y}, ${S.box.width}×${S.box.height}]`;
      regionInfo.innerHTML = `
        <span style="color: #46d6a3">Active Box:</span><br>
        [X: ${S.box.x}, Y: ${S.box.y}, W: ${S.box.width}, H: ${S.box.height}]
      `;
    }

    // Auto-detect
    autoDetectBtn.onclick = async () => {
      if (!S.videoPath) return alert('Video not ready or still uploading.');
      autoDetectBtn.disabled = true;
      autoDetectBtn.textContent = 'Scanning...';
      try {
        const res = await fetch('/api/video/watermark/detect', {
          method: 'POST',
          headers: apiHeaders(),
          body: JSON.stringify({ video_path: S.videoPath, num_samples: 100, max_candidates: 4 })
        });
        const data = await res.json();
        const candList = root.querySelector('#wmCandidatesList');
        candList.innerHTML = '';

        if (!data.candidates || data.candidates.length === 0) {
          candList.innerHTML = '<span style="color: #f2667a">No static logo detected automatically. Please drag a box manually.</span>';
          return;
        }

        S.candidates = data.candidates;
        data.candidates.forEach((cand, idx) => {
          const btn = document.createElement('button');
          btn.className = 'btn-tool';
          btn.style.textAlign = 'left';
          btn.style.padding = '5px 8px';
          btn.style.fontSize = '0.70rem';
          btn.innerHTML = `
            <b>#${idx + 1} [${cand.box.x}, ${cand.box.y}, ${cand.box.width}×${cand.box.height}]</b>
            <span style="color: #46d6a3; margin-left: auto;">${(cand.confidence * 100).toFixed(0)}%</span>
          `;
          btn.onclick = () => {
            S.box = cand.box;
            updateBoxVisual();
            previewBtn.disabled = false;
            runBtn.disabled = false;
            if (cand.sample_frame_sec) {
              video.currentTime = cand.sample_frame_sec;
            }
          };
          candList.appendChild(btn);
        });

        // Auto-select first
        S.box = data.candidates[0].box;
        updateBoxVisual();
        previewBtn.disabled = false;
        runBtn.disabled = false;

      } catch (err) {
        alert('Detection error: ' + err.message);
      } finally {
        autoDetectBtn.disabled = false;
        autoDetectBtn.textContent = '⚡ Auto-Detect';
      }
    };

    // Edge feather slider
    featherRange.oninput = (e) => {
      S.featherPx = parseInt(e.target.value, 10);
      featherVal.textContent = `${S.featherPx} px`;
    };

    // Algo selection
    algoSelect.onchange = (e) => {
      S.mode = e.target.value;
      const desc = root.querySelector('#wmAlgoDesc');
      if (S.mode === 'inverse_alpha') {
        desc.textContent = 'Exact mathematical backdrop restoration for translucent channel watermarks (0 blur).';
      } else if (S.mode === 'flow_guided') {
        desc.textContent = 'Propagates real pixels from preceding and succeeding frames across motion paths.';
      } else {
        desc.textContent = 'Algebraic backdrop inversion with motion gating and authentic pixel retention.';
      }
    };

    // Preview Frame
    previewBtn.onclick = async () => {
      if (!S.videoPath || !S.box) return;
      previewBtn.disabled = true;
      previewBtn.textContent = 'Rendering Preview...';
      try {
        const res = await fetch('/api/video/watermark/preview', {
          method: 'POST',
          headers: apiHeaders(),
          body: JSON.stringify({
            video_path: S.videoPath,
            box: S.box,
            mode: S.mode,
            feather_px: S.featherPx,
            time_sec: S.currentTime || 1.0
          })
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || 'Preview request failed');
        }
        const data = await res.json();
        S.previewData = data;
        showPreviewModal(data);
      } catch (err) {
        alert('Preview failed: ' + err.message);
      } finally {
        previewBtn.disabled = false;
        previewBtn.textContent = '👁 Preview Frame';
      }
    };

    function showPreviewModal(data) {
      let modal = document.getElementById('wmModalCompare');
      if (!modal) {
        modal = document.createElement('div');
        modal.id = 'wmModalCompare';
        modal.style.cssText = 'position:fixed;inset:0;background:rgba(5,8,22,0.85);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px;';
        document.body.appendChild(modal);
      }
      modal.innerHTML = `
        <div style="background:#0b1230;border:1px solid #1a2350;border-radius:10px;padding:16px;max-width:900px;width:100%;display:flex;flex-direction:column;gap:12px;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <b style="color:#eef1ff;font-size:0.95rem;">Single Frame Preview (${data.mode_used}) - Zero Blur Verification</b>
            <button class="btn-tool" id="wmClosePreviewModal">✕ Close</button>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <div>
              <div style="color:#9aa6d0;font-size:0.75rem;margin-bottom:4px;">Original Watermarked</div>
              <img src="data:image/jpeg;base64,${data.original_frame_base64}" style="width:100%;border-radius:6px;border:1px solid #1a2350;" />
            </div>
            <div>
              <div style="color:#46d6a3;font-size:0.75rem;margin-bottom:4px;font-weight:700;">Cleaned (Retained Background Pixels)</div>
              <img src="data:image/jpeg;base64,${data.preview_frame_base64}" style="width:100%;border-radius:6px;border:1px solid #46d6a3;" />
            </div>
          </div>
        </div>
      `;
      modal.querySelector('#wmClosePreviewModal').onclick = () => { modal.remove(); };
    }

    // Run Full Watermark Removal
    runBtn.onclick = async () => {
      if (!S.videoPath || !S.box) {
        return alert('Please load a video and select a watermark box region.');
      }

      runBtn.disabled = true;
      progressWrap.style.display = 'block';
      progressFill.style.width = '0%';
      progressPct.textContent = '0%';
      progressText.textContent = 'Enqueuing watermark removal job...';
      successWrap.style.display = 'none';

      try {
        const res = await fetch('/api/video/watermark/remove', {
          method: 'POST',
          headers: apiHeaders(),
          body: JSON.stringify({
            project_id: 'default',
            video_path: S.videoPath,
            box: S.box,
            mode: S.mode,
            feather_px: S.featherPx,
            context_margin_px: 32,
            use_gpu: true
          })
        });

        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || 'Removal request rejected');
        }

        const data = await res.json();
        S.jobId = data.job_id;

        // Poll job status every 500ms
        if (S.pollTimer) clearInterval(S.pollTimer);
        S.pollTimer = setInterval(async () => {
          try {
            const jRes = await fetch(`/api/jobs/${S.jobId}`, { headers: apiHeaders() });
            if (!jRes.ok) return;
            const job = await jRes.json();
            const rawProg = job.progress !== undefined ? job.progress : 0;
            const pct = Math.min(100, Math.max(0, rawProg <= 1.0 && rawProg > 0 ? Math.round(rawProg * 100) : Math.round(rawProg)));

            progressFill.style.width = `${Math.max(4, pct)}%`;
            progressPct.textContent = `${pct}%`;
            progressText.textContent = job.message || `Inpainting video frames... (${pct}%)`;

            if (job.status === 'SUCCEEDED' || job.status === 'COMPLETED') {
              clearInterval(S.pollTimer);
              progressWrap.style.display = 'none';
              successWrap.style.display = 'flex';
              const outPath = job.output?.output_path || '';
              successPath.textContent = 'Output: ' + outPath;
              runBtn.disabled = false;

              playCleanedBtn.onclick = () => {
                const streamUrl = `/api/video/watermark/stream?path=${encodeURIComponent(outPath)}${getToken() ? `&token=${encodeURIComponent(getToken())}` : ''}`;
                video.src = streamUrl;
                video.load();
                video.play();
                playBtn.textContent = '❚❚ Pause';
                boxOverlay.style.display = 'none';
                S.box = null;
              };
            } else if (job.status === 'FAILED') {
              clearInterval(S.pollTimer);
              progressWrap.style.display = 'none';
              alert('Watermark removal job failed: ' + (job.error || 'Unknown error'));
              runBtn.disabled = false;
            }
          } catch (e) {
            console.warn(e);
          }
        }, 500);

      } catch (err) {
        alert('Removal request failed: ' + err.message);
        runBtn.disabled = false;
        progressWrap.style.display = 'none';
      }
    };
  }

  window.WatermarkEditor = {
    open: function(root) {
      if (!root) root = document.getElementById('tab-watermark');
      if (root && !root.hasChildNodes()) {
        mount(root);
      }
    },
    close: function() {
      if (S.videoEl) S.videoEl.pause();
    }
  };

})();
