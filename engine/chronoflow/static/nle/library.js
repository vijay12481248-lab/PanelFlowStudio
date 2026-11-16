/* ChronoFlow Media page: every video PanelFlow has made, plus anything on disk, and importing it into the studio.
   Uses index.html globals: API_BASE, mediaSrc, studioStore, currentJobData, switchResolvePage, addTerminalLog, openSceneImporterModal. */
(function () {
  const S = { sources: [], source: '', q: '', items: [], total: 0, sel: new Map(), busy: false, shown: false, mounted: false, timer: null };
  let root;
  const esc = (t) => String(t == null ? '' : t).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const $ = (sel) => root.querySelector(sel);
  const PAGE = 60;

  async function call(path, opts) {
    const r = await fetch(`${API_BASE}/library${path}`, opts);
    const body = await r.json().catch(() => ({}));
    if (!r.ok) { const d = body.detail; throw new Error(typeof d === 'string' ? d : (d && d.message) || `Request failed (${r.status})`); }
    return body;
  }
  const post = (path, data) => call(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data || {}) });
  const fileUrl = (p) => mediaSrc(`${API_BASE}/files/serve?path=${encodeURIComponent(p)}`);
  const ago = (t) => { const h = (Date.now() / 1000 - t) / 3600; return h < 1 ? 'just now' : h < 24 ? `${Math.round(h)}h ago` : h < 48 ? 'yesterday' : `${Math.round(h / 24)}d ago`; };
  function note(msg, bad) { const n = $('#libNote'); if (!n) return; n.textContent = msg || ''; n.className = 'lib-note' + (bad ? ' bad' : ''); n.style.display = msg ? 'block' : 'none'; }

  function shell() {
    root.innerHTML = `
      <aside class="lib-side" aria-label="Video sources">
        <div class="cf-panel-head">Sources</div>
        <nav class="lib-sources" id="libSources"></nav>
        <div class="lib-side-actions">
          <div class="cf-label">Add from your computer</div>
          <button type="button" class="cfx-primary" id="libFiles" title="Pick one or more video files (.mp4 .webm .mov)">📄 Import files…</button>
          <button type="button" class="cfx-btn" id="libFolder" title="Make a folder show up in the list on the left">📁 Add a folder…</button>
          <button type="button" class="cfx-btn" id="libScene" title="Bring in the rendered shots of a storyboard scene">📜 From a storyboard scene…</button>
        </div>
      </aside>
      <section class="lib-main">
        <div class="lib-toolbar">
          <div><h2 id="libTitle">Recent videos</h2><div class="lib-sub" id="libSub"></div></div>
          <input type="search" id="libSearch" placeholder="Search by name or folder…" aria-label="Search videos">
        </div>
        <div class="lib-note" id="libNote" style="display:none" role="status"></div>
        <div class="lib-grid" id="libGrid" aria-live="polite"></div>
        <div class="lib-more"><button type="button" class="cfx-btn" id="libMore" style="display:none">Show more</button></div>
        <footer class="lib-footer" id="libFooter" style="display:none">
          <span id="libSelCount"></span>
          <span class="grow"></span>
          <button type="button" class="cfx-btn" id="libClear">Clear</button>
          <button type="button" class="cfx-btn" id="libAudio" style="display:none" title="Make music and sound effects for this video">Open in Audio</button>
          <button type="button" class="cfx-btn" id="libAppend" title="Add to the imported project that is open now">Add to open project</button>
          <button type="button" class="cfx-primary" id="libNew">Import as new project</button>
        </footer>
      </section>`;
    $('#libFiles').onclick = pickFiles;
    $('#libFolder').onclick = addFolder;
    $('#libScene').onclick = () => { if (typeof openSceneImporterModal === 'function') openSceneImporterModal(); };
    $('#libSearch').oninput = (e) => { clearTimeout(S.timer); S.timer = setTimeout(() => { S.q = e.target.value; load(true); }, 250); };
    $('#libMore').onclick = () => load(false);
    $('#libClear').onclick = () => { S.sel.clear(); renderGrid(); };
    $('#libNew').onclick = () => doImport(null);
    $('#libAudio').onclick = () => { const p = [...S.sel.keys()][0]; if (p && typeof switchResolvePage === 'function') { switchResolvePage('audio'); if (window.NLEAudio) NLEAudio.openVideo(p); } };
    $('#libAppend').onclick = () => doImport(currentJobData && currentJobData.workflow_mode === 'imported' ? currentJobData.id : null);
    $('#libGrid').addEventListener('click', onCard);
    $('#libGrid').addEventListener('mouseover', (e) => { const v = e.target.closest('.lib-card') && e.target.closest('.lib-card').querySelector('video'); if (v) v.play().catch(() => {}); });
    $('#libGrid').addEventListener('mouseout', (e) => { const c = e.target.closest('.lib-card'); if (c && !c.contains(e.relatedTarget)) { const v = c.querySelector('video'); if (v) { v.pause(); v.currentTime = 0.1; } } });
  }

  function renderSources() {
    const total = S.sources.reduce((n, s) => n + s.count, 0);
    const row = (id, label, count, icon) => `<button type="button" class="lib-src${S.source === id ? ' on' : ''}" data-src="${esc(id)}"><span>${icon} ${esc(label)}</span><b>${count}</b></button>`;
    const out = S.sources.filter((s) => s.kind === 'output'), loc = S.sources.filter((s) => s.kind === 'location');
    $('#libSources').innerHTML = row('', 'Recent', total, '🕘')
      + `<div class="cf-label lib-grp">Made by PanelFlow</div>` + out.map((s) => row(s.id, s.label, s.count, '🎞️')).join('')
      + (loc.length ? `<div class="cf-label lib-grp">Your folders</div>` + loc.map((s) => row(s.id, s.label, s.count, '📁')).join('') : '');
    $('#libSources').querySelectorAll('[data-src]').forEach((b) => { b.onclick = () => { S.source = b.dataset.src; renderSources(); load(true); }; });
  }

  function renderGrid() {
    const g = $('#libGrid');
    if (!S.items.length) {
      g.innerHTML = `<div class="cf-empty"><div class="cf-empty-icon">🎞️</div><h4>${S.q ? 'No videos match your search' : 'No videos here yet'}</h4>
        <p>${S.q ? 'Try a different word, or pick another source on the left.' : 'Import files from your computer, or add a folder that holds your videos.'}</p></div>`;
    } else {
      g.innerHTML = S.items.map((i) => `
        <div class="lib-card${S.sel.has(i.path) ? ' sel' : ''}" data-path="${esc(i.path)}" tabindex="0" role="checkbox" aria-checked="${S.sel.has(i.path)}" title="${esc(i.path)}">
          <div class="lib-thumb"><video muted loop preload="metadata" playsinline src="${fileUrl(i.path)}#t=0.1"></video><span class="lib-check">${S.sel.has(i.path) ? '✓' : ''}</span></div>
          <div class="lib-meta"><div class="lib-name">${esc(i.name)}</div><div class="lib-sub">${esc(i.folder && i.folder !== '.' ? i.folder + ' · ' : '')}${i.size_mb} MB · ${ago(i.mtime)}</div></div>
        </div>`).join('');
    }
    const label = S.source ? (S.sources.find((s) => s.id === S.source) || {}).label : 'Recent videos';
    $('#libTitle').textContent = label || 'Videos';
    $('#libSub').textContent = `${S.total} video${S.total === 1 ? '' : 's'}${S.q ? ` matching “${S.q}”` : ''} · newest first`;
    $('#libMore').style.display = S.items.length < S.total ? '' : 'none';
    const n = S.sel.size;
    $('#libFooter').style.display = n ? 'flex' : 'none';
    $('#libSelCount').textContent = `${n} selected`;
    $('#libAudio').style.display = n === 1 ? '' : 'none';
    $('#libAppend').style.display = currentJobData && currentJobData.workflow_mode === 'imported' ? '' : 'none';
  }

  function onCard(e) {
    const c = e.target.closest('.lib-card'); if (!c) return;
    const p = c.dataset.path;
    if (S.sel.has(p)) S.sel.delete(p); else S.sel.set(p, true);
    c.classList.toggle('sel', S.sel.has(p));
    c.setAttribute('aria-checked', S.sel.has(p));
    c.querySelector('.lib-check').textContent = S.sel.has(p) ? '✓' : '';
    const n = S.sel.size;
    $('#libFooter').style.display = n ? 'flex' : 'none';
    $('#libSelCount').textContent = `${n} selected`;
    $('#libAudio').style.display = n === 1 ? '' : 'none';
  }

  async function load(reset) {
    if (reset) { S.items = []; }
    try {
      const qs = new URLSearchParams({ source: S.source, q: S.q, limit: PAGE, offset: S.items.length });
      const d = await call(`/videos?${qs}`);
      S.items = S.items.concat(d.items); S.total = d.total;
      renderGrid();
    } catch (e) { note(`Could not load videos: ${e.message}`, true); }
  }

  async function loadSources() {
    try { S.sources = (await call('/sources')).sources; renderSources(); } catch (e) { note(`Could not scan for videos: ${e.message}`, true); }
  }

  async function doImport(jobId, paths) {
    paths = paths || [...S.sel.keys()];
    if (!paths.length || S.busy) return;
    S.busy = true; note(`Importing ${paths.length} video${paths.length === 1 ? '' : 's'}…`);
    try {
      const r = await post('/import', { paths, job_id: jobId });
      S.sel.clear();
      const skip = r.skipped.length ? ` ${r.skipped.length} skipped (${r.skipped[0].reason}).` : '';
      if (typeof addTerminalLog === 'function') addTerminalLog('IMPORT', `Imported ${r.added.length} video(s) into project ${r.job_id}.${skip}`, true);
      studioStore.selectJob(r.job_id);
      switchResolvePage('edit');
      if (skip) alert(`Imported ${r.added.length} video(s).${skip}`);
    } catch (e) { note(`Import failed: ${e.message}`, true); }
    finally { S.busy = false; }
  }

  async function pickFiles() {
    note('Choose videos in the window that just opened…');
    try {
      const d = await post('/pick_files');
      if (d.cancelled) { note(''); return; }
      await doImport(null, d.paths);
    } catch (e) { note(`Could not open the file dialog: ${e.message}`, true); }
  }

  async function addFolder() {
    note('Choose a folder in the window that just opened…');
    try {
      const pick = await (await fetch(`${API_BASE}/storage/pick_folder`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })).json();
      if (!pick.success) { note(''); return; }
      await fetch(`${API_BASE}/storage/locations`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: pick.name, path: pick.path }) });
      note(`Added “${pick.name}”.`);
      await loadSources(); S.source = ''; await load(true);
    } catch (e) { note(`Could not add the folder: ${e.message}`, true); }
  }

  function open() {
    root = document.getElementById('cfLibrary'); if (!root) return;
    if (!S.mounted) { root.className = 'cf-library'; shell(); S.mounted = true; }
    root.style.display = 'flex'; S.shown = true; note('');
    loadSources(); load(true);
  }
  function close() { if (!root) root = document.getElementById('cfLibrary'); if (root) root.style.display = 'none'; S.shown = false; }

  window.CFLibrary = { open, close, refresh: () => { if (S.shown) { loadSources(); load(true); } } };
})();
