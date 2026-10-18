@echo off
setlocal enabledelayedexpansion
title PanelFlow Studio Launcher

echo =======================================================
echo          PanelFlow Studio - Unified Launcher          
echo =======================================================
echo.

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

:: 1. Check if backend engine is already listening on 8765
echo [1/3] Checking backend engine status on port 8765...
powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }; if ($c) { exit 0 } else { exit 1 }"
if %ERRORLEVEL% equ 0 (
    echo   - Backend engine is already running on http://127.0.0.1:8765.
    goto :LAUNCH_APP
)

:: 2. Launch Backend Engine
echo [2/3] Starting backend engine...
if exist "%ROOT_DIR%release\engine_runtime\panelflow-engine.exe" (
    echo   - Found standalone runtime: release\engine_runtime\panelflow-engine.exe
    powershell -NoProfile -Command "Start-Process -FilePath '%ROOT_DIR%release\engine_runtime\panelflow-engine.exe' -WorkingDirectory '%ROOT_DIR%release\engine_runtime' -WindowStyle Hidden"
) else if exist "%ROOT_DIR%apps\desktop\src-tauri\resources\engine_runtime\panelflow-engine.exe" (
    echo   - Found resource runtime: apps\desktop\src-tauri\resources\engine_runtime\panelflow-engine.exe
    powershell -NoProfile -Command "Start-Process -FilePath '%ROOT_DIR%apps\desktop\src-tauri\resources\engine_runtime\panelflow-engine.exe' -WorkingDirectory '%ROOT_DIR%apps\desktop\src-tauri\resources\engine_runtime' -WindowStyle Hidden"
) else (
    echo   - Standalone binary not found. Launching via Python run_engine.py...
    powershell -NoProfile -Command "Start-Process -FilePath 'python.exe' -ArgumentList 'run_engine.py' -WorkingDirectory '%ROOT_DIR%' -WindowStyle Hidden"
)

:: 3. Wait for engine health check (HTTP 200)
echo   - Waiting for engine to bind port 8765 and become healthy...
set "HEALTHY=0"
for /L %%i in (1,1,20) do (
    if !HEALTHY! equ 0 (
        ping -n 2 127.0.0.1 >nul
        powershell -NoProfile -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/system/health' -TimeoutSec 1; if ($r.status -eq 'healthy') { exit 0 } else { exit 1 } } catch { exit 1 }"
        if !ERRORLEVEL! equ 0 (
            set "HEALTHY=1"
        )
    )
)

if !HEALTHY! equ 1 (
    echo   - Backend engine is HEALTHY and listening on http://127.0.0.1:8765!
) else (
    echo   [WARNING] Backend engine did not report healthy within 20 seconds.
    echo   Launching application anyway...
)

:LAUNCH_APP
:: 4. Launch Desktop Application
echo.
echo [3/3] Launching PanelFlow Studio Desktop...
if exist "release\PanelFlow-Studio-v1.0.0-beta.1-Portable.exe" (
    echo   - Starting release\PanelFlow-Studio-v1.0.0-beta.1-Portable.exe
    start "" "release\PanelFlow-Studio-v1.0.0-beta.1-Portable.exe"
) else if exist "apps\desktop\src-tauri\target\release\panelflow-desktop.exe" (
    echo   - Starting apps\desktop\src-tauri\target\release\panelflow-desktop.exe
    start "" "apps\desktop\src-tauri\target\release\panelflow-desktop.exe"
) else (
    echo   - Release executable not found. Launching dev desktop...
    call npm run dev:desktop
)

echo.
echo PanelFlow Studio launched successfully!
echo (You can close this command window at any time.)
ping -n 3 127.0.0.1 >nul
exit /b 0
