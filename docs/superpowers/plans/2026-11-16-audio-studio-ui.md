# Audio Studio UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (the owner chose native execution). Steps use checkbox syntax.

**Goal:** A ChronoFlow "Audio" rail page that opens a finished video's sound plan, plays video + stems in sync with live faders/meters, shows waveform lanes with draggable hits, and lets the owner audition, pick, fix, mix and export, using only the Phase 1 REST API plus five small additions.

**Architecture:** Backend adds (list, video with Range, take peaks, preview stems, stored cuts). Front end follows the Color/Fusion/Deliver module pattern: pure `audio-model.js` (node-tested), `audio.js` + `audio.css`, a rail button, `data-page="audio"` rules in `layout.css`.

**Tech stack:** FastAPI + ffmpeg (backend), vanilla JS/CSS in `engine/chronoflow/static/nle/`, Web Audio, `node --test`, pytest, headless Chromium via the venv's Playwright.

**Spec:** `docs/superpowers/specs/2026-11-16-audio-studio-ui-design.md`

## Global Constraints
- Branch `feat/audio-ui`, worktree `.worktrees/audio-ui`; commit only own files; Python from `E:/VIJAY SEKAR/PanelFlow Studio/.venv/Scripts/python.exe` with `PYTHONPATH=<worktree>`.
- Test engine: isolated data dir, port 8767, `PANELFLOW_ALLOW_INSECURE_LOCAL_API=1`. Never touch the live engine (8765) or its data.
- Do not change Edit/Color/Fusion/Deliver behaviour; layout rules only in `layout.css`, rail highlighting only through `switchResolvePage` (see memory: ChronoFlow UX redesign).
- No second implementation of mixing/ducking in JS. No requestAnimationFrame-dependent logic that must run in a hidden pane (use timeouts for state, rAF only for painting).
- File names from the API are never put in HTML as markup (use textContent); the engine token goes on media URLs as `?token=` like the rest of the page.
- Tests: `.venv/.../python.exe -m pytest tests/unit/audio_studio -p no:cacheprovider -q`, `node --test tests/js/audio_model.test.js`, UI check script `tests/ui/audio_page_check.py` (needs the 8767 engine).

## Review Focus
- Plan with no cues / no takes / a failed cue: page renders, no console errors, inspector says why.
- Video with no audio stream, or no dialogue: stems still play, no NaN meters.
- 9-minute video: lanes and zoom stay usable; preview file sizes sane; seek far away resyncs stems.
- Plan edited by an agent while the page is open: the page refreshes (poll plan version) without losing selection.
- Stale preview after any edit is visible and the mixer says so; a 502/400 from the API shows its message.

### Task 1: Backend additions (list, cuts, video, take peaks)
**Files:** `engine/audio/studio/plan.py` (add `cuts: list[float]`), `engine/api/routers/audio_studio.py`, tests `tests/unit/audio_studio/test_router_ui.py`.
**Produces:** `GET /plans` -> `[{id, video_name, video_path, version, cues, duration, fps}]` newest first; `spot` stores `plan.cuts`; `GET /plans/{id}/video` (FileResponse of `plan.video_path`, supports Range); `GET /plans/{id}/takes/{take_id}/peaks?bins=400` -> `{peaks:[0..1], duration}` for a take or candidate of that plan (404 otherwise), cached in `plan_dir/peaks/`.
- [ ] Tests: list returns created plans newest first; spot saves cuts; video endpoint returns 206 for a Range request and 404 without a file; peaks for a chosen take has `bins` values in 0..1, unknown take 404, path-like take id 400.
- [ ] Implement; run suite; commit `feat(audio-studio): list, cuts, video and take peaks endpoints`.

### Task 2: Preview stems
**Files:** `engine/audio/studio/preview.py`, router, `tests/unit/audio_studio/test_preview.py`.
**Produces:** `build_preview(plan, out_dir) -> {version, duration, stems: {dialogue|music|effects: {file, peaks}}}` (render_roles into temp, transcode each to `.m4a` 160k, peaks 1200 bins); `POST /plans/{id}/preview` renders into `plan_dir/preview/v<version>/` (reuses when `preview.json` has the same version) and returns it; stems served by `files/{name}`.
- [ ] Tests: 3 stems m4a exist with duration within 0.1 s of the plan; peaks length 1200 in 0..1; second call is cached (same mtime); edit -> new version re-renders; plan with nothing playable still returns silent stems (no crash).
- [ ] Implement, run suite, commit.

### Task 3: `audio-model.js` (pure logic) with node tests
**Files:** `engine/chronoflow/static/nle/audio-model.js`, `tests/js/audio_model.test.js`.
**Produces (`window.AudioModel` / `module.exports`):** `fmtTC(t,fps)`, `snapFrame(t,fps)`, `timeToX/xToTime(view)`, `zoomAt(view, factor, anchorT, limits)`, `LANES`, `cueSpan(cue,plan)`, `dragCue(cue,dt,plan,cuts,pxTol)` -> patch (`hit_t` for hit cues, `t_in/t_out` for beds/music; frame-snapped, snapped to a cut within tolerance, clamped to [0,duration]), `dbToGain/gainToDb`, `effectiveGains(gainsDb, mute, solo)`, `driftAction(videoT,audioT,tol)`, `statusChip(cue)`, `peaksToBars(peaks,w,t0,t1,dur)`, `stemOf(track)` (dialogue/music/effects).
- [ ] Tests for each, including: 29.97 fps timecode, drag clamps at 0 and duration, drag snaps to a cut inside tolerance but not outside, solo overrides mute logic, drift under tolerance returns null.
- [ ] Implement, `node --test`, commit.

### Task 4: Page shell, plan open, cue list
**Files:** `static/index.html` (rail button `railAudio`, `CF_PAGES`, switchResolvePage hooks, asset list), `static/nle/audio.js`, `audio.css`, `layout.css` rules, `tests/ui/audio_page_check.py`.
**Behaviour:** `NLEAudio.open/close`; header with plan switcher, "Open video...", mode Auto/Ask, CC-BY toggle; left panel cue list with chips and Spot / Source all; status line; empty state explaining what to do.
- [ ] UI check (RED first): rail has `railAudio`; page shows the three panels at 1600x900 without console errors; creating a plan from a real video via the page lists its cues; Spot adds cut cues; screenshot looked at.
- [ ] Implement; commit.

### Task 5: Inspector and cue actions
**Behaviour:** edit intent/kind/track/anchor/gain/fades/hit time with frame nudge buttons; Source (Auto/Ask), Delete, "+ Cue at playhead"; provenance with licence and link; failed cue shows reason. All writes through `put_plan` / `source_cue` / `pick`, then refresh.
- [ ] UI check: edit intent persists (reload shows it); add and delete a cue; source a whoosh cue (synth/Openverse) and see status ready with provenance; failed cue shows its reason.
- [ ] Commit.

### Task 6: Lanes (ruler, waveforms, cuts, playhead, zoom, drag)
**Behaviour:** per spec; canvas per lane for waveforms from take peaks; DOM blocks for hit targets; drag uses `AudioModel.dragCue`; arrow-key nudge; ruler seek; wheel zoom.
- [ ] UI check: drag a block 1 s and the saved `hit_t` changed by a frame-snapped amount; zoom keeps the cursor time fixed; screenshot looked at on a real plan with 14 cues.
- [ ] Commit.

### Task 7: Playback, mixer, meters
**Behaviour:** `<video>` muted + 3 `<audio>` via Web Audio (gain per stem, analyser per stem and master); transport + shortcuts; drift correction every 250 ms with `driftAction`; faders write `tracks[].gain_db` (debounced) and mute/solo are local; "Preview mix" calls `preview`, shows "stale" after edits and re-enables; meters from analysers; master shows last `mix` LUFS/TP/LRA.
- [ ] UI check: after Preview, play 2 s and `currentTime` advances for video and the three stems within 100 ms of each other; muting a stem sets its gain node to 0; a seek resyncs; no console errors.
- [ ] Commit.

### Task 8: Ask-me audition, QA, master, export, Media "Open in Audio"
**Behaviour:** candidate list with ▶ audition and Pick; QA panel (click -> select cue); Master and Export buttons with results; Media library card gets "Open in Audio" (`CFLibrary` hook) which calls `NLEAudio.openVideo(path)`.
- [ ] UI check: Ask-me source on a cue -> candidates shown -> audition plays -> Pick marks ready; QA lists a seeded error and click selects its cue; Master shows LUFS near -14; Export lists files; "Open in Audio" from a Media card opens that video.
- [ ] Commit.

### Task 9: Real-data verification, docs, review, merge
- [ ] Run the full flow in headless Chromium on the mosquito reel (66 s) and the Dawn Gate draft (9:25): open, spot, source, preview, play, drag, pick, qa, master, export; open every screenshot; record numbers (load time, preview render time, stem sizes, drift observed).
- [ ] Update `docs/AUDIO_STUDIO.md` (UI section + limits), skill file note; run pytest (audio_studio + mcp profiles), node tests; fresh whole-branch review; fix important findings test-first; then ask the owner before merging or pushing.
