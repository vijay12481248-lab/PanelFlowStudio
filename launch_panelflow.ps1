<#
.SYNOPSIS
    PanelFlow Studio Unified Launcher (PowerShell)
    Autonomously checks/starts the backend engine and launches the desktop app.
#>

$ErrorActionPreference = "Continue"
$rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $rootDir

Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "          PanelFlow Studio - Unified Launcher          " -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check if backend engine is already listening on 8765
Write-Host "[1/3] Checking backend engine status on port 8765..." -ForegroundColor Yellow
$healthy = $false
try {
    $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/system/health" -TimeoutSec 1 -UseBasicParsing -ErrorAction Stop
    if ($resp -and $resp.status -eq "healthy") {
        $healthy = $true
    }
} catch {
    $healthy = $false
}

if ($healthy) {
    Write-Host "  -> Backend engine is already RUNNING on http://127.0.0.1:8765." -ForegroundColor Green
} else {
    Write-Host "  -> Backend engine is offline. Starting service..." -ForegroundColor Yellow

    $standaloneExe = Join-Path $rootDir "release\engine_runtime\panelflow-engine.exe"
    $resourceExe = Join-Path $rootDir "apps\desktop\src-tauri\resources\engine_runtime\panelflow-engine.exe"
    $localExe = Join-Path $rootDir "engine_runtime\panelflow-engine.exe"

    if (Test-Path $standaloneExe) {
        Write-Host "  -> Launching standalone engine: $standaloneExe" -ForegroundColor Cyan
        Start-Process -FilePath $standaloneExe -WorkingDirectory (Split-Path $standaloneExe) -WindowStyle Hidden
    } elseif (Test-Path $resourceExe) {
        Write-Host "  -> Launching packaged engine: $resourceExe" -ForegroundColor Cyan
        Start-Process -FilePath $resourceExe -WorkingDirectory (Split-Path $resourceExe) -WindowStyle Hidden
    } elseif (Test-Path $localExe) {
        Write-Host "  -> Launching local engine: $localExe" -ForegroundColor Cyan
        Start-Process -FilePath $localExe -WorkingDirectory (Split-Path $localExe) -WindowStyle Hidden
    } else {
        Write-Host "  -> Standalone engine not found. Launching via Python run_engine.py..." -ForegroundColor Cyan
        Start-Process -FilePath "python.exe" -ArgumentList "run_engine.py" -WorkingDirectory $rootDir -WindowStyle Hidden
    }

    # Poll for health check
    Write-Host "  -> Waiting for backend engine to report healthy..." -NoNewline
    for ($i = 0; $i -lt 25; $i++) {
        Start-Sleep -Milliseconds 600
        try {
            $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/system/health" -TimeoutSec 1 -UseBasicParsing -ErrorAction Stop
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
        Write-Host "  -> [NOTICE] Backend engine is initializing in background. Launching desktop app..." -ForegroundColor Yellow
    }
}

# 2. Check ACE-Step Music Server
if (Test-Path "C:\Tools\ACE-Step-1.5\.venv\Scripts\python.exe") {
    Write-Host "[2/3] Checking ACE-Step music engine on port 8001..." -ForegroundColor Yellow
    $aceHealthy = $false
    try {
        $aceResp = Invoke-RestMethod -Uri "http://127.0.0.1:8001/health" -TimeoutSec 1 -UseBasicParsing -ErrorAction Stop
        if ($aceResp) { $aceHealthy = $true }
    } catch {
        $aceHealthy = $false
    }
    if ($aceHealthy) {
        Write-Host "  -> ACE-Step server is running on http://127.0.0.1:8001." -ForegroundColor Green
    } else {
        Write-Host "  -> Starting ACE-Step API server in background..." -ForegroundColor Cyan
        Start-Process -FilePath "C:\Tools\ACE-Step-1.5\.venv\Scripts\python.exe" -ArgumentList "-m acestep.api_server --host 127.0.0.1 --port 8001" -WorkingDirectory "C:\Tools\ACE-Step-1.5" -WindowStyle Hidden
    }
} else {
    Write-Host "[2/3] ACE-Step neural model optional. Procedural synthesizer fallback active." -ForegroundColor Gray
}

# 3. Launch Desktop Application
Write-Host "[3/3] Launching PanelFlow Studio Desktop..." -ForegroundColor Yellow

$portableCandidates = Get-ChildItem -Path (Join-Path $rootDir "release") -Filter "PanelFlow-Studio-*-Portable.exe" -ErrorAction SilentlyContinue | Sort-Object Name -Descending
$portableApp = if ($portableCandidates) { $portableCandidates[0].FullName } else { $null }
$releaseApp = Join-Path $rootDir "apps\desktop\src-tauri\target\release\panelflow-desktop.exe"
$debugApp = Join-Path $rootDir "apps\desktop\src-tauri\target\debug\panelflow-desktop.exe"

if ($portableApp -and (Test-Path $portableApp)) {
    Write-Host "  -> Starting $portableApp" -ForegroundColor Green
    Start-Process -FilePath $portableApp -WorkingDirectory (Split-Path $portableApp)
} elseif (Test-Path $releaseApp) {
    Write-Host "  -> Starting $releaseApp" -ForegroundColor Green
    Start-Process -FilePath $releaseApp -WorkingDirectory (Split-Path $releaseApp)
} elseif (Test-Path $debugApp) {
    Write-Host "  -> Starting $debugApp" -ForegroundColor Green
    Start-Process -FilePath $debugApp -WorkingDirectory (Split-Path $debugApp)
} else {
    Write-Host "  -> Pre-compiled binary not found. Launching dev desktop..." -ForegroundColor Cyan
    Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev:desktop" -WorkingDirectory $rootDir
}

Write-Host ""
Write-Host "PanelFlow Studio is ready!" -ForegroundColor Green
Start-Sleep -Seconds 2
