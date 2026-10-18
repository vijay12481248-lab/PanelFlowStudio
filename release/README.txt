================================================================================
PANELFLOW STUDIO v1.0.0-beta.2 — GETTING STARTED & QUICK START
================================================================================

Welcome to the PanelFlow Studio Beta!

PanelFlow Studio is a desktop workstation application that transforms authorized,
illustrated visual narratives (comics, manga, manhwa, webtoons) into synchronized,
motion-comic video presentations using local AI-assisted production.

--------------------------------------------------------------------------------
1. INSTALLATION OPTIONS
--------------------------------------------------------------------------------
Choose the installer that best fits your Windows environment:

A. NSIS Setup Installer (Recommended for new users):
   - Double-click `PanelFlow-Studio-v1.0.0-beta.2-Setup.exe`
   - Installs to %LOCALAPPDATA%\Programs\PanelFlow Studio
   - Creates Start Menu shortcut and Windows uninstaller entry.

B. WiX MSI Installer (Enterprise / Managed deployments):
   - Double-click `PanelFlow-Studio-v1.0.0-beta.2.msi`
   - Installs per-machine into Program Files with standard Windows Installer MSI.

C. Portable Executable:
   - Run `PanelFlow-Studio-v1.0.0-beta.2-Portable.exe` directly.
   - Zero installation required.

--------------------------------------------------------------------------------
2. SYSTEM REQUIREMENTS (BACKEND STRATEGY B: USER-INSTALLED RUNTIME)
--------------------------------------------------------------------------------
Minimum Requirements (Baseline Operation):
  - OS: Windows 10 (64-bit) Version 1909 or Windows 11
  - Python Runtime: Python 3.12+ 64-bit (REQUIRED for backend engine)
    Install command: `winget install Python.Python.3.12` or from python.org
  - Processor: 4-core 64-bit x86_64 CPU (Intel Core i5-6400 / AMD Ryzen 3 1200)
  - Memory: 8 GB RAM
  - Storage: 2 GB free disk space for base application; 15 GB for render cache
  - Video Encoder: FFmpeg 6.0+ installed and on system PATH (`winget install Gyan.FFmpeg`)

Recommended Requirements (Hardware-Accelerated Neural Voice & 1080p Video):
  - OS: Windows 11 Pro 64-bit
  - Python: Python 3.12 (64-bit)
  - Processor: 8-core CPU (Intel Core i7-10700 / AMD Ryzen 7 5700X or newer)
  - Memory: 16 GB - 32 GB RAM
  - Graphics: NVIDIA GeForce RTX 3060 / 4060 / 5060 Ti or higher (>= 8 GB VRAM)
  - Acceleration: NVIDIA CUDA 12.x + NVENC hardware video encoding
  - Storage: NVMe SSD with >= 50 GB free space

--------------------------------------------------------------------------------
3. APPLICATION DATA VS PROJECT DATA
--------------------------------------------------------------------------------
PanelFlow strictly distinguishes application state from your creative projects:

A. APPLICATION STATE (Automated & Isolated):
   - Location: `%LOCALAPPDATA%\PanelFlow Studio\`
   - Contains:
     * `database/panelflow.db` (Application SQLite catalog & job state)
     * `logs/` (Sanitized application execution logs)
     * `config/` (User preferences & UI layout state)
     * `cache/` (Intermediate processing cache)

B. PROJECT DATA (User-Selected & Independent):
   - Location: Exactly the directory chosen when clicking "New Project"
     (e.g., `D:\My Comics\Issue 1\` or `C:\Users\Name\Projects\Title\`)
   - Structure:
     * `project.json` (Project manifest)
     * `source/` (Original ingested images)
     * `normalized/` (Normalized canvas images)
     * `panels/` (Detected polygonal panel crops)
     * `ocr/` (Speech balloon text regions)
     * `story/` (Character attribution & scene beats)
     * `script/` (Adapted dialogue scripts)
     * `audio/` (MasterAudioTimeline & dialogue WAVs)
     * `motion/` (Visual timeline & camera framing)
     * `renders/` (Generated certified 1080p/720p MP4 videos)
   - Note: Uninstalling PanelFlow Studio NEVER deletes your project folders or videos!

--------------------------------------------------------------------------------
4. DEPENDENCY SETUP (FIRST LAUNCH)
--------------------------------------------------------------------------------
When you first open PanelFlow Studio, click "Tools & Models" in the top header.
The built-in System Diagnostics dialog will check:

- Python 3.12+ (REQUIRED):
  PanelFlow automatically searches system PATH, the Windows `py -3` launcher,
  and `%LOCALAPPDATA%\Programs\Python\Python31*`.

- FFmpeg Video Encoder (REQUIRED):
  Install via Windows Package Manager:
    winget install Gyan.FFmpeg
  Or download from https://www.gyan.dev/ffmpeg/builds/ and add bin/ to your PATH.

- Ollama Story Intelligence (OPTIONAL):
  Download from https://ollama.com/ and launch the app (`ollama run qwen3.5:9b`).
  If offline, PanelFlow gracefully falls back to rule-based story pacing.

- F5-TTS Neural Voice (RECOMMENDED):
  Integrated neural dialogue engine. When neural model weights are present on CUDA,
  zero-shot voice synthesis is used. Procedural voice fallback is provided if offline.

- ACE-Step Dynamic Music (RECOMMENDED):
  Adaptive crystal soundtrack generator rooted in D-Minor. Operates via local REST
  server (port 8001) or built-in procedural synthesizer fallback.

- Playwright Browser Engine (OPTIONAL):
  Only needed if crawling dynamic single-page web readers. Local folders and
  CBZ archives do not require browser runtimes.

--------------------------------------------------------------------------------
5. CREATING YOUR FIRST VIDEO (5-MINUTE SAMPLE WORKFLOW)
--------------------------------------------------------------------------------
We have included a legally safe 5-page sample comic in the `sample_project/` folder:

Step 1: Open PanelFlow Studio.
Step 2: Click "New Project".
Step 3: Enter Title: "Lumina Prelude Demo".
Step 4: Source Type: Choose "Local Folder".
Step 5: Click Browse and select the `sample_project/` directory included in this folder.
Step 6: Optional: Choose your custom project destination folder.
Step 7: Rights Gate: Select "Creative Commons (CC-BY 4.0)" and confirm.
Step 8: Click "Create Project".
Step 9: Follow the top progression bar:
        - Source (Import images)
        - Panels (Review panel boundaries)
        - OCR (Review detected dialogue balloons)
        - Story (Analyze narrative character beats)
        - Script (Review narrator and character lines)
        - Audio (Preview voice and music intervals)
        - Motion (Review cinematic shot camera moves)
        - Render (Click "Start Render" with standard_1080p)
Step 10: Watch the rendered video right inside PanelFlow's built-in player!
Step 11: Click "Open Folder" to find your MP4 file on disk.

================================================================================
