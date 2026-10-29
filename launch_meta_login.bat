@echo off
title PanelFlow Studio - Meta AI Session Setup
cd /d "%~dp0"

echo ======================================================================
echo  PanelFlow Studio: Starting Persistent Meta AI Session Setup
echo ======================================================================
echo.

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" scripts\setup_meta_ai_session.py
) else (
    python scripts\setup_meta_ai_session.py
)

pause
