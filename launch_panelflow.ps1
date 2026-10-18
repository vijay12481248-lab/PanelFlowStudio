<#
.SYNOPSIS
    PanelFlow Studio Unified Desktop Launcher (PowerShell)
    Starts Python Engine (8765), ACE-Step (8001), Vite dev server (5173),
    and launches the native Tauri desktop application window running latest code.
#>

$ErrorActionPreference = "Stop"
$rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $rootDir

Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "          PanelFlow Studio - Desktop Application       " -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Backend Engine (Port 8765)
Write-Host "[1/4] Checking backend engine on port 8765..." -ForegroundColor Yellow
$engineConn = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" }
if ($engineConn) {
    Write-Host "  -> Backend engine is already running on http://127.0.0.1:8765." -ForegroundColor Green
} else {
    Write-Host "  -> Starting Python backend engine..." -ForegroundColor Cyan
    Start-Process -FilePath "python.exe" -ArgumentList "run_engine.py" -WorkingDirectory $rootDir -WindowStyle Hidden
}

# 2. ACE-Step 1.5 Music Server (Port 8001)
Write-Host "[2/4] Checking ACE-Step music engine on port 8001..." -ForegroundColor Yellow
$aceConn = Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" }
if ($aceConn) {
    Write-Host "  -> ACE-Step server is already running on http://127.0.0.1:8001." -ForegroundColor Green
} else {
    Write-Host "  -> Starting ACE-Step server..." -ForegroundColor Cyan
    Start-Process -FilePath "C:\Tools\ACE-Step-1.5\.venv\Scripts\python.exe" -ArgumentList "-m acestep.api_server --host 127.0.0.1 --port 8001" -WorkingDirectory "C:\Tools\ACE-Step-1.5" -WindowStyle Hidden
}

# 3. Vite Dev Server (Port 5173)
Write-Host "[3/4] Checking Vite dev server on port 5173..." -ForegroundColor Yellow
$viteConn = Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" }
if ($viteConn) {
    Write-Host "  -> Vite dev server is already running on http://localhost:5173." -ForegroundColor Green
} else {
    Write-Host "  -> Starting Vite dev server with latest code..." -ForegroundColor Cyan
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c npm run dev --workspace=@panelflow/desktop" -WorkingDirectory $rootDir -WindowStyle Hidden
    Start-Sleep -Seconds 3
}

# 4. Native Desktop Window (Tauri)
Write-Host "[4/4] Launching PanelFlow Studio Desktop Window..." -ForegroundColor Yellow
$existingProcess = Get-Process -Name "panelflow-desktop" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existingProcess) {
    Write-Host "  -> PanelFlow Studio desktop window is already open and running (PID $($existingProcess.Id))." -ForegroundColor Green
} else {
    $debugApp = "$rootDir\apps\desktop\src-tauri\target\debug\panelflow-desktop.exe"
    if (Test-Path $debugApp) {
        Write-Host "  -> Opening native desktop application window (latest code)..." -ForegroundColor Green
        Start-Process -FilePath $debugApp -WorkingDirectory (Split-Path $debugApp)
    } else {
        Write-Host "  -> Launching desktop window via Tauri CLI..." -ForegroundColor Cyan
        Start-Process -FilePath "npm.cmd" -ArgumentList "--workspace=@panelflow/desktop", "run", "tauri", "dev" -WorkingDirectory $rootDir
    }
}

Write-Host ""
Write-Host "PanelFlow Studio Desktop is ready!" -ForegroundColor Green
