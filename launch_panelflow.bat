@echo off
setlocal enabledelayedexpansion
title PanelFlow Studio Launcher

echo =======================================================
echo          PanelFlow Studio - Desktop Application        
echo =======================================================
echo.

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

:: -------------------------------------------------------------
:: 1. Verify or Start Backend Processing Engine (Port 8765)
:: -------------------------------------------------------------
echo [1/3] Checking backend processing engine on port 8765...
curl.exe -f -s http://127.0.0.1:8765/api/system/health >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo   - Backend engine is already RUNNING on http://127.0.0.1:8765.
    goto :CHECK_AUDIO
)

echo   - Backend engine is offline. Starting service...

set "ENGINE_EXE="
set "ENGINE_DIR="

if exist "%ROOT_DIR%release\engine_runtime\panelflow-engine.exe" (
    set "ENGINE_EXE=%ROOT_DIR%release\engine_runtime\panelflow-engine.exe"
    set "ENGINE_DIR=%ROOT_DIR%release\engine_runtime"
) else if exist "%ROOT_DIR%apps\desktop\src-tauri\resources\engine_runtime\panelflow-engine.exe" (
    set "ENGINE_EXE=%ROOT_DIR%apps\desktop\src-tauri\resources\engine_runtime\panelflow-engine.exe"
    set "ENGINE_DIR=%ROOT_DIR%apps\desktop\src-tauri\resources\engine_runtime"
) else if exist "%ROOT_DIR%engine_runtime\panelflow-engine.exe" (
    set "ENGINE_EXE=%ROOT_DIR%engine_runtime\panelflow-engine.exe"
    set "ENGINE_DIR=%ROOT_DIR%engine_runtime"
)

if defined ENGINE_EXE (
    echo   - Launching standalone engine: !ENGINE_EXE!
    powershell.exe -ExecutionPolicy Bypass -NoProfile -Command "Start-Process -FilePath '!ENGINE_EXE!' -WorkingDirectory '!ENGINE_DIR!' -WindowStyle Hidden"
) else (
    echo   - Standalone binary not found. Launching via python run_engine.py...
    powershell.exe -ExecutionPolicy Bypass -NoProfile -Command "Start-Process -FilePath 'python.exe' -ArgumentList 'run_engine.py' -WorkingDirectory '%ROOT_DIR%' -WindowStyle Hidden"
)

:: Wait for engine health check (HTTP 200)
echo   - Waiting for backend engine to report healthy...
set "ENGINE_READY=0"
for /L %%i in (1,1,25) do (
    if !ENGINE_READY! equ 0 (
        ping -n 2 127.0.0.1 >nul
        curl.exe -f -s http://127.0.0.1:8765/api/system/health >nul 2>&1
        if !ERRORLEVEL% equ 0 (
            set "ENGINE_READY=1"
        ) else (
            <nul set /p=.
        )
    )
)
echo.

if !ENGINE_READY! equ 1 (
    echo   - Backend engine is HEALTHY and listening on http://127.0.0.1:8765!
) else (
    echo   [NOTICE] Backend engine is initializing in background. Launching UI...
)

:CHECK_AUDIO
:: -------------------------------------------------------------
:: 2. Optional: ACE-Step 1.5 Music Server on port 8001
:: -------------------------------------------------------------
if exist "C:\Tools\ACE-Step-1.5\.venv\Scripts\python.exe" (
    echo [2/3] Checking ACE-Step music engine on port 8001...
    curl.exe -f -s http://127.0.0.1:8001/health >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        echo   - ACE-Step server is running on http://127.0.0.1:8001.
    ) else (
        echo   - Starting ACE-Step API server in background...
        powershell.exe -ExecutionPolicy Bypass -NoProfile -Command "Start-Process -FilePath 'C:\Tools\ACE-Step-1.5\.venv\Scripts\python.exe' -ArgumentList '-m acestep.api_server --host 127.0.0.1 --port 8001' -WorkingDirectory 'C:\Tools\ACE-Step-1.5' -WindowStyle Hidden"
    )
) else (
    echo [2/3] ACE-Step neural model optional. Procedural synthesizer fallback active.
)

:: -------------------------------------------------------------
:: 3. Launch Desktop Application UI
:: -------------------------------------------------------------
echo.
echo [3/3] Launching PanelFlow Studio Desktop...

set "APP_EXE="

:: Priority 1: Check release directory for standalone portable executable
for /f "delims=" %%f in ('dir /b /o-n "%ROOT_DIR%release\PanelFlow-Studio-*-Portable.exe" 2^>nul') do (
    set "APP_EXE=%ROOT_DIR%release\%%f"
    goto :RUN_DESKTOP
)

:: Priority 2: Check target/release
if exist "%ROOT_DIR%apps\desktop\src-tauri\target\release\panelflow-desktop.exe" (
    set "APP_EXE=%ROOT_DIR%apps\desktop\src-tauri\target\release\panelflow-desktop.exe"
    goto :RUN_DESKTOP
)

:: Priority 3: Check target/debug
if exist "%ROOT_DIR%apps\desktop\src-tauri\target\debug\panelflow-desktop.exe" (
    set "APP_EXE=%ROOT_DIR%apps\desktop\src-tauri\target\debug\panelflow-desktop.exe"
    goto :RUN_DESKTOP
)

:RUN_DESKTOP
if defined APP_EXE (
    echo   - Starting !APP_EXE!
    start "" "!APP_EXE!"
) else (
    echo   - Standalone binary not found. Launching development desktop...
    call npm run dev:desktop
)

echo.
echo PanelFlow Studio Desktop is running!
echo (You can close this command window at any time.)
ping -n 3 127.0.0.1 >nul
exit /b 0
