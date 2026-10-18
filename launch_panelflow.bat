@echo off
setlocal enabledelayedexpansion
title PanelFlow Studio - Desktop Application Launcher

echo =======================================================
echo          PanelFlow Studio - Desktop Application         
echo =======================================================
echo.

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

:: 1. Check & start Backend Engine on port 8765
echo [1/4] Checking Python backend engine on port 8765...
powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }; if ($c) { exit 0 } else { exit 1 }"
if %ERRORLEVEL% equ 0 (
    echo   - Backend engine is already running on http://127.0.0.1:8765.
) else (
    echo   - Starting backend engine via Python run_engine.py...
    powershell -NoProfile -Command "Start-Process -FilePath 'python.exe' -ArgumentList 'run_engine.py' -WorkingDirectory '%ROOT_DIR%' -WindowStyle Hidden"
)

:: 2. Check & start ACE-Step Music Server on port 8001
echo [2/4] Checking ACE-Step music engine on port 8001...
powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }; if ($c) { exit 0 } else { exit 1 }"
if %ERRORLEVEL% equ 0 (
    echo   - ACE-Step server is already running on http://127.0.0.1:8001.
) else (
    echo   - Starting ACE-Step API server...
    powershell -NoProfile -Command "Start-Process -FilePath 'C:\Tools\ACE-Step-1.5\.venv\Scripts\python.exe' -ArgumentList '-m acestep.api_server --host 127.0.0.1 --port 8001' -WorkingDirectory 'C:\Tools\ACE-Step-1.5' -WindowStyle Hidden"
)

:: 3. Check & start Vite Frontend Dev Server on port 5173
echo [3/4] Checking Vite dev server on port 5173...
powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }; if ($c) { exit 0 } else { exit 1 }"
if %ERRORLEVEL% equ 0 (
    echo   - Frontend dev server is already running on http://localhost:5173.
) else (
    echo   - Starting frontend dev server with latest code...
    powershell -NoProfile -Command "Start-Process -FilePath 'cmd.exe' -ArgumentList '/c npm run dev --workspace=@panelflow/desktop' -WorkingDirectory '%ROOT_DIR%' -WindowStyle Hidden"
    ping -n 3 127.0.0.1 >nul
)

:: 4. Launch Desktop Application Window with Latest Code
echo [4/4] Launching PanelFlow Studio Desktop Window...
powershell -NoProfile -Command "Get-Process -Name 'panelflow-desktop' -ErrorAction SilentlyContinue | Where-Object { $_.Path -notlike '*debug*' } | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }"

if exist "%ROOT_DIR%apps\desktop\src-tauri\target\debug\panelflow-desktop.exe" (
    powershell -NoProfile -Command "$p = Get-Process -Name 'panelflow-desktop' -ErrorAction SilentlyContinue; if (-not $p) { Start-Process '%ROOT_DIR%apps\desktop\src-tauri\target\debug\panelflow-desktop.exe' }"
    echo   - Native desktop application window opened with latest code.
) else (
    echo   - Launching desktop window via Tauri CLI...
    call npm --workspace=@panelflow/desktop run tauri dev
)

echo.
echo PanelFlow Studio Desktop is running with the latest code!
echo You can close this command window at any time.
ping -n 3 127.0.0.1 >nul
exit /b 0
