# PanelFlow Studio — Troubleshooting Guide

Common diagnostic procedures and resolutions for PanelFlow Studio.

---

## 1. Local Processing Engine Unavailable (Port 8765)

### Symptom
Desktop frontend displays: `"Processing engine unavailable on 127.0.0.1:8765"`.

### Cause
The background Python FastAPI service is not running or another process is occupying port 8765.

### Resolution
1. Verify if port 8765 is in use:
   ```powershell
   Get-NetTCPConnection -LocalPort 8765
   ```
2. Launch the engine manually if running in development:
   ```powershell
   python -m uvicorn engine.api.app:app --host 127.0.0.1 --port 8765
   ```
3. Test health response in browser:
   `http://127.0.0.1:8765/api/system/health`

---

## 2. FFmpeg or FFprobe Not Detected

### Symptom
Tools & Models modal shows FFmpeg or FFprobe as `MISSING`, or render fails with `Preflight check failed`.

### Resolution
1. Install FFmpeg via Windows Package Manager:
   ```powershell
   winget install Gyan.FFmpeg
   ```
2. Restart your terminal or the desktop app to ensure the updated system `PATH` is inherited.
3. Test by running `ffmpeg -version` in PowerShell.

---

## 3. High CPU Usage During Encoding

### Symptom
Encoding causes noticeable system fan noise or high CPU utilization.

### Resolution
- By default, PanelFlow uses software `libx264` with a multi-threaded medium preset to guarantee pristine visual fidelity and reproducible frames.
- For rapid test iterations, select **Draft 720p** in the Render settings, which utilizes `ultrafast` preset and 720p scaling for 3x faster encoding.

---

## 4. SQLite Database Locks

### Symptom
Intermittent `database is locked` error during heavy concurrent writes.

### Resolution
- PanelFlow Studio configures SQLite with WAL (Write-Ahead Logging) mode and a 30-second timeout.
- Ensure that the workspace directory is located on a local SSD drive rather than a network-mapped drive or syncing cloud folder (e.g. OneDrive / Dropbox).
