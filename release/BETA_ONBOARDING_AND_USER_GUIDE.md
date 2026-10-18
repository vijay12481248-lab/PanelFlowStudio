# PanelFlow Studio — Beta Onboarding & User Guide

Welcome to the **PanelFlow Studio v1 Closed Beta (v1.0.0-beta.2)**. This guide explains how to install PanelFlow on a clean Windows machine, configure local dependencies, and produce your first motion comic video in under 10 minutes.

---

## 1. Prerequisites & The 10-Step Beta Onboarding Flow

### ⚠️ System Prerequisite (Backend Strategy B: User-Installed Runtime)
Before launching PanelFlow Studio, ensure you have **Python 3.12+ (64-bit)** installed on your Windows machine:
```powershell
winget install Python.Python.3.12
```

| Step | Milestone | User Action | Typical Duration |
| :---: | :--- | :--- | :--- |
| 1 | **Install** | Run `PanelFlow-Studio-v1.0.0-beta.2-Setup.exe` (or `.msi` / `.exe`). | 30 seconds |
| 2 | **Launch** | Open PanelFlow Studio from the Start Menu or desktop shortcut. | 5 seconds |
| 3 | **System Check** | Click **Tools & Models** in the top bar to inspect your hardware and tool engines. | 1 minute |
| 4 | **Configure** | Ensure FFmpeg and Python are ready; observe which neural models are detected. | 1–3 minutes |
| 5 | **New Project** | Click **New Project**, choose a title, and select source folder (`sample_project/`). | 30 seconds |
| 6 | **Rights Gate** | Select your legal source declaration (e.g., `Creative Commons`). | 10 seconds |
| 7 | **Process** | Follow the PipelineNavbar: Source -> Panels -> OCR. | 1–2 minutes |
| 8 | **Story & Script** | Review character dialogue lines and approve the adapted script. | 1 minute |
| 9 | **Audio & Motion** | Preview voice intervals, background score, and camera choreography. | 1 minute |
| 10 | **Render & Watch** | Select `standard_1080p`, click **Start Render**, and watch your MP4! | 2–4 minutes |

---

## 2. Dependency Setup Guide (Clean-Machine Perspective)

PanelFlow is built with a **graceful degradation philosophy**: missing optional tools will never cause the application to crash or prevent you from navigating projects.

### Required: Python 3.12+ (64-bit)
- **Why PanelFlow needs it**: Drives the local FastAPI engine, computer vision processing, and pipeline orchestration.
- **How to install**: Run `winget install Python.Python.3.12` or download from [python.org](https://www.python.org/).

### Required: FFmpeg Video Encoder
- **Why PanelFlow needs it**: Encodes raw video frames, mixes multi-track audio, and outputs the final MP4.
- **How to install on Windows**:
  1. Open Windows PowerShell and run:
     ```powershell
     winget install Gyan.FFmpeg
     ```
  2. Or download a build from [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/) and add its `bin/` directory to your Windows System Environment Variables `PATH`.
  3. Re-launch PanelFlow Studio or click **Re-scan System** in **Tools & Models**.

### Optional: Ollama Local LLM
- **Why PanelFlow needs it**: Automatically identifies characters, speech bubble speakers, and emotional tone.
- **How to configure**: Download and run Ollama from [ollama.com](https://ollama.com/), then run `ollama run qwen3.5:9b`.
- **Graceful Fallback**: If Ollama is offline, PanelFlow automatically uses deterministic rule-based dialogue attribution.

### Recommended: F5-TTS Neural Voice
- **Why PanelFlow needs it**: Synthesizes natural, emotional character voice lines with natural breathiness.
- **Graceful Fallback**: If F5-TTS neural weights are offline, PanelFlow automatically uses procedural voice synthesizers so audio review and video rendering remain fully functional.

### Recommended: ACE-Step Dynamic Music
- **Why PanelFlow needs it**: Dynamically scores background music rooted in D-Minor crystal techno-magic.
- **Graceful Fallback**: Built-in cinematic synthesizer tracks are automatically substituted if the ACE-Step master pipeline is inactive.

### Optional: Playwright Browser Engine
- **Why PanelFlow needs it**: Required only if scraping dynamic single-page webtoon reader websites.
- **Setup**: Run `playwright install chromium` in PowerShell if you plan to crawl web chapters. Local folders and CBZ archives do not require Playwright.

---

## 3. Sample Project Walkthrough

A legally authorized 5-page sample story is bundled in your release folder under `sample_project/`:
- **Title**: *Lumina: The Shattered Prism — Prelude*
- **License**: Creative Commons Attribution 4.0 International (CC-BY 4.0)
- **Files**: `page_01.jpg` through `page_05.jpg` + `LICENSE_AND_ATTRIBUTION.txt`

### How to run the sample project:
1. In PanelFlow Studio, click **New Project**.
2. Set **Title**: `Lumina Demo`.
3. Set **Source Type**: `Local Folder`.
4. Click **Browse** and select the `sample_project` folder inside your release folder.
5. In the **Rights Declaration**, select `Creative Commons (CC-BY 4.0)` and check the verification box.
6. Click **Create Project**.
7. Navigate through the top navbar to see how PanelFlow detects the panels, reads the speech bubbles, adapts the dialogue, casts the narrator voice, frames the camera, and renders the 1080p MP4!

---

## 4. Rights & Licensing Policy

PanelFlow Studio enforces a strict **Rights Gate** on every project.

> [!IMPORTANT]
> Having the technical capability to download, split, or process comic images does NOT grant legal permission to adapt or publish copyrighted manga or comics.

### Approved Source Categories:
- **USER_OWNED**: You created the original artwork and narrative script yourself.
- **CREATIVE_COMMONS / OPEN_LICENSE**: The creator has released the visual material under a CC license (CC-BY, CC-BY-SA, CC0) allowing adaptation.
- **PUBLIC_DOMAIN**: The copyright term has expired in your jurisdiction.
- **LICENSED / EXPLICIT_PERMISSION**: You have received written permission or a contractual license from the publisher/rights holder.

---

## 5. Support & Troubleshooting Matrix

| Symptom | Likely Cause | User Action |
| :--- | :--- | :--- |
| **"Processing engine unavailable" on launch** | Background Python engine was stopped or blocked by firewall. | Click **Retry Engine Connection** in the UI. If still offline, launch `panelflow-desktop.exe` as Administrator. |
| **"FFmpeg Video Encoder: MISSING"** | FFmpeg is not installed or not in system PATH. | Run `winget install Gyan.FFmpeg` in PowerShell, then click **Re-scan System** in the Tools & Models modal. |
| **"Ollama Local LLM: OFFLINE"** | Ollama background daemon is not running. | Launch Ollama from Start Menu or run `ollama serve`. If you prefer offline rule-based adaptation, you can safely ignore this. |
| **"Create Project" button is disabled** | Rights declaration has not been selected. | Select a valid Rights Status (e.g. `Creative Commons`) and check the confirmation box. |
| **Render is taking longer than expected** | Running 4,000+ frames on CPU without GPU acceleration. | In **Render Settings**, select `draft_720p` for faster previews, or ensure NVIDIA CUDA is enabled in your GPU driver. |
| **Render was cancelled by accident** | Cancel button was clicked mid-flight. | Simply click **Start Render** again. Renders are non-destructive and resume cleanly. |
| **Video player shows black screen** | Browser GPU acceleration glitch or missing codec. | Click **Open File** to launch the rendered MP4 directly in Windows Media Player or VLC. |

---

## 6. Uninstalling & Data Safety

### Uninstall Procedure:
- Open Windows **Settings** -> **Apps** -> **Installed Apps**.
- Locate **PanelFlow Studio** and click **Uninstall**.

### Data Safety Guarantee:
- Uninstalling PanelFlow Studio removes application binaries and desktop shortcuts.
- It **never deletes your creative projects, source visuals, or rendered videos**.
- Your projects remain safely stored in `%USERPROFILE%\.panelflow\workspaces\`.

---

## 7. Beta Tester Feedback Questionnaire

Please answer these 10 short questions after completing your first project:

1. **Installation**: Did the installer complete smoothly without developer prompts? (Yes / No — if no, describe error)
2. **First Launch**: Did the Tools & Models dialog accurately report your system hardware and FFmpeg status?
3. **Onboarding**: Was the 8-stage top progression bar (Source -> Panels -> OCR -> Story -> Script -> Audio -> Motion -> Render) intuitive to follow?
4. **Rights Gate**: Did the rights selection screen clearly explain legal responsibility without being confusing?
5. **Panel Detection & OCR**: Did the panel boundaries and dialogue balloon detection look accurate on your images?
6. **Audio & Voice**: How did the generated speech pacing and background music sound?
7. **Render Performance**: How long did your video take to render, and which profile did you choose (`standard_1080p` or `draft_720p`)?
8. **Final Video Quality**: Did the camera motion (zooms, pans, holds) match the pacing of the audio?
9. **Biggest Confusion / Friction Point**: What was the most frustrating or confusing moment during your test?
10. **Sanitized Diagnostics**: Did you export your `panelflow_diagnostics.json` from the Tools & Models modal? (Please attach to your feedback!)
