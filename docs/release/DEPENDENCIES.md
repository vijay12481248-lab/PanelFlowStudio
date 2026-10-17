# PanelFlow Studio — Dependency Matrix & Local Model Guide

This guide details all external engines, local neural models, and tools used by PanelFlow Studio.

---

## 1. Local Tool Registry

| Tool / Model | Subsystem | Required? | Verified Location | Fallback Mode |
| :--- | :--- | :---: | :--- | :--- |
| **FFmpeg** | Video Compositor | **Yes** | Winget / PATH (`ffmpeg.exe`) | None (Hard blocker for MP4 encoding) |
| **FFprobe** | Media Validator | **Yes** | Winget / PATH (`ffprobe.exe`) | None (Hard blocker for stream audit) |
| **F5-TTS** | Audio Director | **Yes** | `C:\Tools\generated_audio\marcus_male_deep` | 48 kHz harmonic speech tone simulation |
| **ACE-Step** | Music Director | **Yes** | `assets/cinematics/intro/audio/someone_stayed_ace_master.ogg` | Chamber orchestral theme (`someone_stayed_chamber.wav`) |
| **Ollama** | Story Intelligence | No | `http://127.0.0.1:11434` (Qwen2.5 / Gemma) | Deterministic rule-based story parser (`MockLLMProvider`) |
| **Playwright** | Chapter Extractor | No | Chromium headless shell | Static DOM / JSON extraction strategies |

---

## 2. Verification & Diagnostics

The desktop UI provides a one-click **Tools & Models** inspection modal in the top header bar, backed by `GET /api/system/providers`.

### Probing Details
1. **FFmpeg**: Executes `ffmpeg -version` and verifies libx264, AAC, and pipe IO support.
2. **FFprobe**: Executes `ffprobe -version` and checks JSON output parsing.
3. **F5-TTS**: Inspects `C:\Tools\generated_audio\marcus_male_deep` for pre-rendered neural takes.
4. **ACE-Step**: Checks for the canonical 48 kHz D-Minor master crystal score file.
5. **Ollama**: Pings `http://127.0.0.1:11434/api/tags` with a 1.0s timeout and lists installed models.
6. **Playwright**: Attempts headless browser launch via `sync_playwright()`.

---

## 3. Installation Guide

### Windows (Winget)
```powershell
# Install video rendering tools
winget install Gyan.FFmpeg

# Verify in PowerShell
ffmpeg -version
ffprobe -version
```

### Local Story Model (Ollama)
```powershell
# If Ollama is installed
ollama run qwen2.5:7b-instruct-q4_K_M
```

### Audio Assets
Ensure approved voice files are located in `C:\Tools\generated_audio\marcus_male_deep\` and master music in `assets/cinematics/intro/audio/`.
