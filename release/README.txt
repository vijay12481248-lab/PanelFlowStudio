================================================================================
PANELFLOW STUDIO v1.0.0-beta.1 — GETTING STARTED & QUICK START
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
   - Double-click `PanelFlow-Studio-v1.0.0-beta.1-Setup.exe`
   - Installs to %LOCALAPPDATA%\Programs\PanelFlow Studio
   - Creates Start Menu shortcut and Windows uninstaller entry.

B. WiX MSI Installer (Enterprise / Managed deployments):
   - Double-click `PanelFlow-Studio-v1.0.0-beta.1.msi`
   - Installs per-machine into Program Files with standard Windows Installer MSI.

C. Portable Executable:
   - Run `PanelFlow-Studio-v1.0.0-beta.1-Portable.exe` directly.
   - Zero installation required.

--------------------------------------------------------------------------------
2. SYSTEM REQUIREMENTS
--------------------------------------------------------------------------------
Minimum Requirements (CPU Rendering & Baseline Operation):
  - OS: Windows 10 (64-bit) Version 1909 or Windows 11
  - Processor: 4-core 64-bit x86_64 CPU (Intel Core i5-6400 / AMD Ryzen 3 1200)
  - Memory: 8 GB RAM
  - Storage: 2 GB free disk space for base application; 15 GB for render cache
  - Video Encoder: FFmpeg 6.0+ installed and on system PATH

Recommended Requirements (Hardware-Accelerated Neural Voice & 1080p Video):
  - OS: Windows 11 Pro 64-bit
  - Processor: 8-core CPU (Intel Core i7-10700 / AMD Ryzen 7 5700X or newer)
  - Memory: 16 GB - 32 GB RAM
  - Graphics: NVIDIA GeForce RTX 3060 / 4060 / 5060 Ti or higher (>= 8 GB VRAM)
  - Acceleration: NVIDIA CUDA 12.x + NVENC hardware video encoding
  - Storage: NVMe SSD with >= 50 GB free space

--------------------------------------------------------------------------------
3. DEPENDENCY SETUP (FIRST LAUNCH)
--------------------------------------------------------------------------------
When you first open PanelFlow Studio, click "Tools & Models" in the top header.
The built-in System Diagnostics dialog will check:

- FFmpeg Video Encoder (REQUIRED):
  Install via Windows Package Manager:
    winget install Gyan.FFmpeg
  Or download from https://www.gyan.dev/ffmpeg/builds/ and add bin/ to your PATH.

- Ollama Story Intelligence (OPTIONAL):
  Download from https://ollama.com/ and launch the app.
  If offline, PanelFlow gracefully falls back to rule-based story pacing.

- F5-TTS Neural Voice (RECOMMENDED):
  If neural voice weights are not installed, PanelFlow automatically provides
  procedural audio voice generation so your projects never crash.

- ACE-Step Dynamic Music (RECOMMENDED):
  Adaptive crystal soundtrack generator rooted in D-Minor.
  Procedural synthesizers are used if ACE-Step is offline.

- Playwright Browser Engine (OPTIONAL):
  Only needed if crawling dynamic single-page web readers. Local folders and
  CBZ archives do not require browser runtimes.

--------------------------------------------------------------------------------
4. CREATING YOUR FIRST VIDEO (5-MINUTE SAMPLE WORKFLOW)
--------------------------------------------------------------------------------
We have included a legally safe 5-page sample comic in the `sample_project/` folder:

Step 1: Open PanelFlow Studio.
Step 2: Click "New Project".
Step 3: Enter Title: "My First Motion Comic".
Step 4: Source Type: Choose "Local Folder".
Step 5: Click Browse and select the `sample_project/` directory included in this folder.
Step 6: Rights Gate: Select "Creative Commons (CC-BY 4.0)" and confirm.
Step 7: Click "Create Project".
Step 8: Follow the top progression bar:
        - Source (Import images)
        - Panels (Review panel boundaries)
        - OCR (Review detected dialogue balloons)
        - Story (Analyze narrative character beats)
        - Script (Review narrator and character lines)
        - Audio (Preview voice and music intervals)
        - Motion (Review cinematic shot camera moves)
        - Render (Click "Start Render" with standard_1080p or draft_720p)
Step 9: Watch the rendered video right inside PanelFlow's built-in player!
Step 10: Click "Open Folder" to find your MP4 file on disk.

--------------------------------------------------------------------------------
5. RIGHTS & LEGAL RESPONSIBILITY NOTICE
--------------------------------------------------------------------------------
PanelFlow Studio is an AI-assisted video editing tool. Having the technical
capability to process comic images does NOT grant legal rights to adapt or publish
copyrighted manga or comics without author permission. Always ensure you own the
source visuals, have explicit license approval, or use public-domain/creative
commons works.

--------------------------------------------------------------------------------
6. REPORTING BUGS & BETA FEEDBACK
--------------------------------------------------------------------------------
Found an issue? We want to know!
1. Open "Tools & Models" -> click "Export Diagnostics".
2. This downloads a sanitized `panelflow_diagnostics.json` file with your
   hardware tier and error codes (zero personal files or images).
3. Submit feedback with the diagnostics file attached.
================================================================================
