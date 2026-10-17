# PanelFlow Studio v1.0.0-beta.1 Release Notes

**Release Date**: October 17, 2026  
**Build Target**: Windows x64 (10/11)  
**Distribution Channel**: Closed Beta (5–20 Creators & Engineers)  
**Package Artifacts**:
- `PanelFlow-Studio-v1.0.0-beta.1-Setup.exe` (NSIS Installer)
- `PanelFlow-Studio-v1.0.0-beta.1.msi` (WiX Windows Installer)
- `PanelFlow-Studio-v1.0.0-beta.1-Portable.exe` (Standalone Executable)

---

## 1. Overview & Vision
PanelFlow Studio is an AI-assisted desktop workstation designed to transform static, illustrated graphic novels, webtoons, manga, and comics into professionally paced motion-comic video presentations.

By integrating computer vision panel detection, speech balloon OCR, narrative story intelligence, neural voice synthesis (F5-TTS), adaptive music direction (ACE-Step), deterministic camera choreography (Motion Director), and hardware-accelerated video rendering into **one unified desktop interface**, PanelFlow removes the need for terminal commands and fragmented editing tools.

---

## 2. What's Included in Beta 1

### 🎥 End-to-End Motion Comic Workflow
- **Rights Gate Enforcement**: Explicit legal declarations required before processing (`USER_OWNED`, `CREATIVE_COMMONS`, `PUBLIC_DOMAIN`, `LICENSED`).
- **Source Ingestion**: Native support for local image directories, CBZ archives, and single-page webtoon layouts.
- **Computer Vision Panel Detection**: Automatic polygonal panel bounding box extraction with visual split, merge, and manual border editing.
- **Multilingual OCR & Text Regions**: Speech bubble, narration box, and sound effect (SFX) classification with OCR confidence filtering.
- **Narrative Intelligence (Layer B)**: Deep character attribution, dialogue line structuring, and scene emotional arc tracking.
- **Video Script Adaptation**: Faithful and condensed script adaptation profiles with pacing timing and faithfulness validation.
- **Neural Voice & Audio Direction**: F5-TTS neural speech synthesis with measured speech durations, zero-shot emotion, and dynamic ACE-Step background score.
- **Motion Director (Layer D)**: Cinematic camera framing (Ken Burns zooms, pans, tracking focus) synchronized strictly to the audio clock.
- **Production Renderer**: Full 1920×1080 / 30 FPS H.264 video and stereo AAC audio composition with automated A/V validation audits (0 black frames, 0 timeline gaps, 0 audio clipping).
- **In-App Video Playback**: HTML5 video streaming player with seek controls, validation audit cards, and direct Windows Explorer "Open File" and "Open Folder" actions.
- **Multi-Profile Render History**: Independent tracking of `standard_1080p` and `draft_720p` renders without overwriting prior outputs.
- **Mid-Flight Cancellation**: One-click cancellation from the UI that terminates active encoding subprocesses and cleans up partial disk files.
- **Downstream Stale-State Invalidation**: Editing upstream script lines or panel cuts automatically cascades `(STALE)` status badges across downstream stages while keeping upstream stages intact.

### 🛡️ Diagnostic & Hardware Diagnostics
- **Local Engine Health Grid**: Real-time status reporting across all 6 local tools (FFmpeg, FFprobe, Ollama, F5-TTS, ACE-Step, Playwright).
- **Hardware Performance Tiering**: Automatic assessment of CPU cores, system RAM, NVIDIA GPU model, and VRAM with broad tier ratings:
  - `GOOD`: >= 16 GB RAM + NVIDIA GPU with >= 6 GB VRAM.
  - `SUPPORTED`: >= 12 GB RAM + CUDA GPU or modern 8-core CPU.
  - `LIMITED`: 8 GB RAM (procedural CPU audio fallback).
  - `UNSUPPORTED`: < 8 GB RAM or < 10 GB disk space.
- **Privacy-Preserving Diagnostic Export**: One-click "Export Diagnostics" generating a sanitized JSON bundle with zero user images, passwords, or personal documents.

---

## 3. Verified Production Metrics
- **Pytest Regression**: 144 / 144 passing unit and integration tests (100% pass rate in 12.65s).
- **Combined Test Verifications**: 171 passing test verifications (144 functions + 27 benchmark fixtures).
- **TypeScript & React UI**: 0 errors across `@panelflow/shared-types`, `@panelflow/api-client`, `@panelflow/ui`, `@panelflow/desktop`, and `@panelflow/web`.
- **Rust Tauri Shell**: 0 errors in `cargo check`.
- **E2E Acceptance Suite**: 12 / 12 automated Edge Playwright workflows passed cleanly.

---

## 4. Known Limitations in Beta 1
1. **FFmpeg Prerequisite**: FFmpeg is an external system tool and must be installed on the machine PATH (`winget install Gyan.FFmpeg`).
2. **First Neural Audio Cold Start**: When generating F5-TTS neural speech for the first time on a machine without a warm GPU cache, initialization may take up to 20-30 seconds before speech synthesis begins.
3. **Web Reader Cloudflare / Bot Walls**: PanelFlow strictly honors robots.txt, authentication barriers, and anti-bot challenges. If a web source is protected by a login wall, import via Local Folder or CBZ instead.
4. **Vertical Webtoon Stitching**: Single continuous webtoon strips longer than 50,000 pixels are segmented into normalized pages.

---

## 5. Beta Feedback Instructions
We encourage all beta testers to report any confusion, setup friction, or unexpected behavior:
1. Export your sanitized diagnostic report via **Tools & Models** -> **Export Diagnostics**.
2. Record your issue using the feedback questionnaire in `release/BETA_ONBOARDING_AND_USER_GUIDE.md`.
3. Share your findings with the core engineering team.
