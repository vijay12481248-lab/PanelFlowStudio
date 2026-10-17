# PanelFlow Studio — Release QA Checklist

Run this checklist prior to certifying any production release candidate.

---

## 1. Automated Verification Checks

- [ ] **Full Regression Suite**: All pytest unit and integration tests pass (100% pass rate).
- [ ] **TypeScript / Vite Build**: `npm run build --workspaces` completes with 0 errors across `@panelflow/shared-types`, `@panelflow/api-client`, `@panelflow/ui`, and `@panelflow/desktop`.
- [ ] **Tauri Backend**: `cargo check --manifest-path apps/desktop/src-tauri/Cargo.toml` finishes with exit code 0.
- [ ] **Database Migration**: Schema tables (`projects`, `pages`, `panels`, `ocr_records`, `text_regions`, `video_scripts`, `audio_timelines`, `visual_timelines`, `render_jobs`) initialize cleanly on a fresh database.
- [ ] **Crash Recovery**: Interrupted jobs from previous engine sessions are automatically marked as `FAILED` on startup without deadlocking.

---

## 2. Audio-Visual Integrity

- [ ] **Video Codec**: Output is strictly H.264 (`libx264`, `yuv420p`, baseline or main profile).
- [ ] **Audio Stream**: AAC stereo at 48,000 Hz, with clear vocal presence and ducked background score (-10 dB).
- [ ] **Zero Black Frames**: No uncomposed black frames between shot transitions.
- [ ] **Zero Timeline Gaps**: Total audio timeline duration equals total visual timeline duration within ±1.5s tolerance.
- [ ] **A/V Sync Verification**: Speech cues match the camera focus on the active dialogue panel.
- [ ] **No Audio Clipping**: Zero samples exceed 0 dBFS ceiling.

---

## 3. Desktop Application Usability

- [ ] **Engine Indicator**: Top navbar displays engine connection status (`CONNECTED` / `DISCONNECTED`) and latency indicator.
- [ ] **Tools & Models Inspection**: Provider health modal correctly detects FFmpeg, FFprobe, F5-TTS, ACE-Step, Ollama, and Playwright.
- [ ] **Pipeline Progression Navbar**: Breadcrumb bar shows current project state and enables one-click navigation between approved stages.
- [ ] **Video Preview**: Embedded HTML5 `<video>` player streams and seeks rendered MP4 smoothly.
- [ ] **OS File Exploration**: "Open Video File" and "Open Folder" successfully trigger native OS explorer (`os.startfile` / `explorer.exe`).
