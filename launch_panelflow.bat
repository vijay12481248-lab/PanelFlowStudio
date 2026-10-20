@echo off
setlocal
title PanelFlow Studio Launcher
:: Share backend restart and launch behavior with the PowerShell launcher.
powershell.exe -NoProfile -File "%~dp0launch_panelflow.ps1" %*
exit /b %ERRORLEVEL%
