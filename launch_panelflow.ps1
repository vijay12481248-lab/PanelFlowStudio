<#
.SYNOPSIS
    PanelFlow Studio Unified Launcher (PowerShell)
    Autonomously checks/starts the backend engine and launches the desktop app.
#>

$ErrorActionPreference = "Stop"
$rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $rootDir

Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "          PanelFlow Studio - Unified Launcher          " -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check if backend engine is already listening on 8765
Write-Host "[1/3] Checking backend engine status on port 8765..." -ForegroundColor Yellow
$activeConn = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" }

if ($activeConn) {
    Write-Host "  -> Backend engine is already RUNNING on http://127.0.0.1:8765." -ForegroundColor Green
} else {
    Write-Host "[2/3] Starting backend engine..." -ForegroundColor Yellow

    $standaloneExe = "$rootDir\release\engine_runtime\panelflow-engine.exe"
    $resourceExe = "$rootDir\apps\desktop\src-tauri\resources\engine_runtime\panelflow-engine.exe"

    if (Test-Path $standaloneExe) {
        Write-Host "  -> Launching standalone engine: $standaloneExe" -ForegroundColor Cyan
        Start-Process -FilePath $standaloneExe -WorkingDirectory (Split-Path $standaloneExe) -WindowStyle Hidden
    } elseif (Test-Path $resourceExe) {
        Write-Host "  -> Launching packaged engine: $resourceExe" -ForegroundColor Cyan
        Start-Process -FilePath $resourceExe -WorkingDirectory (Split-Path $resourceExe) -WindowStyle Hidden
    } else {
        Write-Host "  -> Standalone engine not found. Launching via Python run_engine.py..." -ForegroundColor Cyan
        Start-Process -FilePath "python.exe" -ArgumentList "run_engine.py" -WorkingDirectory $rootDir -WindowStyle Hidden
    }

    # Poll for health check
    Write-Host "  -> Waiting for backend engine to report healthy..." -NoNewline
    $healthy = $false
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 600
        try {
            $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/system/health" -TimeoutSec 1 -ErrorAction SilentlyContinue
            if ($resp -and $resp.status -eq "healthy") {
                $healthy = $true
                break
            }
        } catch {
            Write-Host "." -NoNewline
        }
    }
    Write-Host ""

    if ($healthy) {
        Write-Host "  -> Backend engine is HEALTHY (v$($resp.version))!" -ForegroundColor Green
    } else {
        Write-Host "  -> [WARNING] Backend engine did not respond in 12s. Launching desktop app anyway..." -ForegroundColor Yellow
    }
}

# 2. Launch Desktop Application
Write-Host "[3/3] Launching PanelFlow Studio Desktop..." -ForegroundColor Yellow

$portableApp = "$rootDir\release\PanelFlow-Studio-v1.0.0-beta.1-Portable.exe"
$releaseApp = "$rootDir\apps\desktop\src-tauri\target\release\panelflow-desktop.exe"

if (Test-Path $portableApp) {
    Write-Host "  -> Starting $portableApp" -ForegroundColor Green
    Start-Process -FilePath $portableApp -WorkingDirectory (Split-Path $portableApp)
} elseif (Test-Path $releaseApp) {
    Write-Host "  -> Starting $releaseApp" -ForegroundColor Green
    Start-Process -FilePath $releaseApp -WorkingDirectory (Split-Path $releaseApp)
} else {
    Write-Host "  -> Pre-compiled binary not found. Launching dev desktop..." -ForegroundColor Cyan
    Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev:desktop" -WorkingDirectory $rootDir
}

Write-Host ""
Write-Host "PanelFlow Studio is ready!" -ForegroundColor Green
