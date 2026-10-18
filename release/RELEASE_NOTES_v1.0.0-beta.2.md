# PanelFlow Studio v1.0.0-beta.2 Release Notes — Runtime Hardening

**Release Date**: October 17, 2026  
**Build Target**: Windows x64 (10/11)  
**Distribution Channel**: Closed Beta (5–20 Creators & Engineers)  
**Package Artifacts**:
- `PanelFlow-Studio-v1.0.0-beta.2-Setup.exe` (NSIS Installer)
- `PanelFlow-Studio-v1.0.0-beta.2.msi` (WiX Windows Installer)
- `PanelFlow-Studio-v1.0.0-beta.2-Portable.exe` (Standalone Portable Executable)
- `provider_manifest.json` (Machine-readable provider capability contract)
- `SHA256SUMS.txt` (Cryptographic verification checksums)

---

## 1. Runtime Hardening & Distribution Truth (Beta 2 Highlights)

The **v1.0.0-beta.2** release hardens the desktop distribution architecture and eliminates configuration ambiguity:

### 🐍 Explicit Backend Strategy (Strategy B: User-Installed Runtime)
- **Truthful Requirement**: PanelFlow Studio utilizes a local FastAPI engine powered by a user-installed **Python 3.12+ (64-bit)** runtime.
- **Discovery Mechanism**: Desktop shell probes `PANELFLOW_PYTHON` -> system `python` -> `py -3` Windows launcher -> `%LOCALAPPDATA%\Programs\Python\Python31*`.
- **First Launch Diagnostics**: If Python is absent, the application reports `PYTHON RUNTIME — MISSING` with direct installation guidance (`winget install Python.Python.3.12`) rather than failing silently.

### 🧠 Reconciled Neural Model Discovery (F5-TTS & ACE-Step)
- **F5-TTS Neural Voice**: Reconciled discovery to check Hugging Face hub cache (`models--SWivid--F5-TTS/snapshots/.../model_1250000.safetensors`, 1.35 GB) and `C:\Tools\F5-TTS`. When weights and CUDA are available (verified on RTX 5060 Ti), provider status accurately reflects `READY` with zero-shot neural synthesis.
- **ACE-Step Music Director**: Reconciled connection to local REST API service on port 8001 (`acestep-v15-turbo`). Accurately reports `READY` when online and `STOPPED (Procedural Synthesizer Active)` when service is offline, eliminating any false status reporting.

### 📂 Strict Separation of App Data vs Project Data
- **Application State**: Deterministically isolated to `%LOCALAPPDATA%\PanelFlow Studio\` (`database\panelflow.db`, `logs\`, `config\`, `cache\`).
- **User Project Data**: Writes strictly to the directory designated by the user (e.g. `C:\Users\...\PanelFlow User Test\Project A\`) with complete folder structure (`source`, `normalized`, `panels`, `ocr`, `story`, `script`, `audio`, `motion`, `renders`) and `project.json` manifest.
- **Zero WSL / Ubuntu Drift**: Native Windows paths enforced; all placeholder and resolution code stripped of Unix `/home/` references.
- **Zero Legacy Source Paths**: Removed all hardcoded development repository references.

---

## 2. Clean-PC Compatibility Matrix

| Configuration | Installed Software | Available Pipeline Stages | Audio / Video Mode |
| :--- | :--- | :--- | :--- |
| **Config A: Base App Only** | PanelFlow + Python 3.12 | Ingestion, Panel Detection, Story (rule-based), Script Editor | None (Video encoding blocked without FFmpeg) |
| **Config B: Base + FFmpeg** | PanelFlow + Python 3.12 + FFmpeg | Full end-to-end pipeline (Ingestion -> Panels -> OCR -> Script -> Audio -> Motion -> 1080p Render) | `PROCEDURAL_FALLBACK` (Harmonic voice tones + procedural crystal music) |
| **Config C: Base + FFmpeg + Ollama** | PanelFlow + Python 3.12 + FFmpeg + Ollama | Full end-to-end pipeline with deep character attribution & narrative adaptation | `NEURAL_STORY_PROCEDURAL_AV` |
| **Config D: Full Neural Stack** | PanelFlow + Python 3.12 + FFmpeg + Ollama + F5-TTS + ACE-Step | Complete autonomous workstation with zero-shot voice cloning, dynamic scoring, and NVENC encoding | `NEURAL_FULL` (Certified broadcast MP4) |

---

## 3. Verified Production Metrics

- **Unit & Integration Suite (pytest)**: 144 / 144 tests passing (100% pass rate in 14.24s).
- **TypeScript Compilation (tsc)**: 0 errors across `@panelflow/shared-types`, `@panelflow/api-client`, `@panelflow/ui`, and `@panelflow/desktop`.
- **Vite Production Bundler**: Built static bundle in 876ms (`dist/index.html` + css/js chunks).
- **Rust Tauri Shell**: 0 warnings in `cargo check`.
- **Tauri Release Bundler**: Generated 2 production bundles in 27.12s (WiX MSI 3.58 MiB + NSIS Setup 2.32 MiB).
- **Project Isolation Acceptance**: Verified creating projects across multiple independent custom directories.

---

## 4. Known Limitations for Beta 2

1. **System Python Prerequisite**: User must have Python 3.12+ (64-bit) installed (`winget install Python.Python.3.12`).
2. **FFmpeg Prerequisite**: FFmpeg must be installed on PATH (`winget install Gyan.FFmpeg`).
3. **Playwright Browser Crawling**: If crawling dynamic JavaScript-rendered webtoon websites, user must run `playwright install chromium`. Local folders and CBZ comic archives do not require Playwright.
