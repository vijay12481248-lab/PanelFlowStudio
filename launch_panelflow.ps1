<#
.SYNOPSIS
    PanelFlow Studio Unified Launcher (PowerShell)
    Restarts the backend engine and launches the desktop app.
#>
param([switch]$EngineOnly, [switch]$CancelJobs, [switch]$Dev)

$ErrorActionPreference = "Stop"
$rootDir = if ($PSScriptRoot) { $PSScriptRoot } elseif ($MyInvocation.MyCommand.Path) { Split-Path -Parent $MyInvocation.MyCommand.Path } else { (Get-Location).Path }
Set-Location $rootDir
$venvPython = Join-Path $rootDir '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $venvPython) {
    $env:PANELFLOW_PYTHON = $venvPython
}
# Chapters are narrated by the local narration compiler; the legacy audio stage cannot validate its scripts.
if (-not $env:PANELFLOW_NARRATION_ENGINE) { $env:PANELFLOW_NARRATION_ENGINE = 'compiler' }
$tokenFile = Join-Path $env:LOCALAPPDATA 'PanelFlow Studio\engine.token'
$rootTokenFile = Join-Path $rootDir '.engine_token'
$engineWasRunning = $false
try {
    $probe = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/system/health' -TimeoutSec 1 -UseBasicParsing
    $engineWasRunning = $probe.app -eq 'PanelFlow Studio'
} catch {}

if (Test-Path -LiteralPath $tokenFile) {
    $existing = (Get-Content -LiteralPath $tokenFile -Raw).Trim()
    if ($existing.Length -ge 32) {
        $env:PANELFLOW_ENGINE_TOKEN = $existing
    }
}
if (-not $env:PANELFLOW_ENGINE_TOKEN -and (Test-Path -LiteralPath $rootTokenFile)) {
    $existing = (Get-Content -LiteralPath $rootTokenFile -Raw).Trim()
    if ($existing.Length -ge 32) {
        $env:PANELFLOW_ENGINE_TOKEN = $existing
    }
}
if (-not $env:PANELFLOW_ENGINE_TOKEN) {
    $tokenBytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($tokenBytes)
    $env:PANELFLOW_ENGINE_TOKEN = ([System.BitConverter]::ToString($tokenBytes)).Replace('-', '').ToLowerInvariant()
}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $tokenFile) | Out-Null
[System.IO.File]::WriteAllText($tokenFile, $env:PANELFLOW_ENGINE_TOKEN)
[System.IO.File]::WriteAllText($rootTokenFile, $env:PANELFLOW_ENGINE_TOKEN)
$authHeaders = @{ 'X-PanelFlow-Token' = $env:PANELFLOW_ENGINE_TOKEN }

function Invoke-PanelFlowJsonGet {
    param([Parameter(Mandatory=$true)][string]$Uri)
    $response = Invoke-RestMethod -Uri $Uri -Headers $authHeaders -TimeoutSec 5
    if ($response -is [string]) {
        # Windows PowerShell 5.1 silently returns raw JSON when its case-insensitive
        # parser encounters legitimate case-distinct settings keys (Visuals/visuals).
        # These endpoints must return lists; malformed data must block a restart.
        if ($response.TrimStart() -notmatch '^\[') { throw 'Expected a JSON inventory array; engine kept running.' }
        if ((Get-Command ConvertFrom-Json).Parameters.ContainsKey('AsHashtable')) {
            $response = ConvertFrom-Json -InputObject $response -AsHashtable -ErrorAction Stop
        } else {
            Add-Type -AssemblyName System.Web.Extensions
            $parser = New-Object System.Web.Script.Serialization.JavaScriptSerializer
            $parser.MaxJsonLength = 16777216
            $parser.RecursionLimit = 128
            $response = $parser.DeserializeObject($response)
        }
    }
    return $response
}

function Get-PanelFlowActiveWork {
    foreach ($jobStatus in @('QUEUED', 'RUNNING')) {
        $jobs = Invoke-PanelFlowJsonGet "http://127.0.0.1:8765/api/jobs?status=$jobStatus&limit=200"
        foreach ($job in $jobs) {
            if ($job.status -eq $jobStatus) {
                [pscustomobject]@{Id=$job.job_id; Type=$job.job_type; Status=$job.status; Progress=[math]::Round(100*$job.progress); Project=$job.project_id; Started=$job.started_at; CancelUrl="http://127.0.0.1:8765/api/jobs/$($job.job_id)/cancel"}
            }
        }
    }
    $projects = Invoke-PanelFlowJsonGet 'http://127.0.0.1:8765/api/projects'
    foreach ($project in $projects) {
        if ([string]::IsNullOrWhiteSpace($project.id)) { throw 'Project inventory is missing an ID; engine kept running.' }
        $renders = Invoke-PanelFlowJsonGet "http://127.0.0.1:8765/api/projects/$($project.id)/render/jobs"
        foreach ($render in $renders) {
            if ($render.status -in @('QUEUED', 'RUNNING', 'PREPARING', 'COMPOSING', 'ENCODING', 'MUXING', 'VALIDATING')) {
                $renderId = if ($render.render_id) { $render.render_id } else { $render.id }
                [pscustomobject]@{Id=$renderId; Type='RENDER'; Status=$render.status; Progress=[math]::Round(100*$render.progress); Project=$project.id; Started=$render.started_at; CancelUrl="http://127.0.0.1:8765/api/projects/$($project.id)/render/jobs/$renderId/cancel"}
            }
        }
    }
}

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
    Write-Host "  -> Restarting existing PanelFlow backend..." -ForegroundColor Yellow
    if ($resp.app -ne "PanelFlow Studio") { throw "Port 8765 belongs to another application." }
    $activeWork = @(Get-PanelFlowActiveWork)
    $restartAllowed = $true
    if ($activeWork.Count -gt 0) {
        $activeWork | Select-Object Id,Type,Status,Progress,Project,Started | Format-Table -AutoSize -Wrap | Out-Host
        $cancelApproved = $CancelJobs -or ((Read-Host 'Cancel these jobs and restart the backend? [y/N]') -match '^(y|yes)$')
        if (-not $cancelApproved) {
            Write-Host '  -> Keeping the existing engine and jobs running.' -ForegroundColor Yellow
            $restartAllowed = $false
        } else {
            foreach ($work in $activeWork) {
                Write-Host "  -> Requesting cancellation: $($work.Type) $($work.Id)" -ForegroundColor Yellow
                try { Invoke-RestMethod $work.CancelUrl -Method Post -Headers $authHeaders -TimeoutSec 5 | Out-Null }
                catch {
                    if (@(Get-PanelFlowActiveWork | Where-Object { $_.Id -eq $work.Id }).Count -gt 0) { throw }
                }
            }
            for ($attempt = 0; $attempt -lt 60; $attempt++) {
                if (@(Get-PanelFlowActiveWork).Count -eq 0) { break }
                Start-Sleep -Milliseconds 500
            }
            if (@(Get-PanelFlowActiveWork).Count -gt 0) { throw 'Cancellation is still pending. Engine kept running; retry after jobs stop.' }
        }
    }
    if ($restartAllowed) {
    $engineListeners = @(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction Stop)
    $enginePids = @($engineListeners | Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($enginePid in $enginePids) {
        $engineProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$enginePid"
        if ($engineProcess.CommandLine -notmatch '(?i)(run_engine\.py|panelflow-engine\.exe|uvicorn\s+engine\.api\.app:app)') {
            throw "Cannot identify process $enginePid as a PanelFlow engine; refusing to stop it."
        }
    }
    foreach ($enginePid in $enginePids) {
        Stop-Process -Id $enginePid -ErrorAction Stop
        Wait-Process -Id $enginePid -Timeout 10 -ErrorAction SilentlyContinue
    }
    $healthy = $false
    }
}

if (-not $healthy) {
    Write-Host "  -> Backend engine is offline. Starting service..." -ForegroundColor Yellow

    $standaloneExe = Join-Path $rootDir "release\engine_runtime\panelflow-engine.exe"
    $resourceExe = Join-Path $rootDir "apps\desktop\src-tauri\resources\engine_runtime\panelflow-engine.exe"
    $localExe = Join-Path $rootDir "engine_runtime\panelflow-engine.exe"

    $sourceEntry = Join-Path $rootDir 'run_engine.py'
    $venvPython = Join-Path $rootDir '.venv\Scripts\python.exe'
    $sourcePython = Get-Command python.exe -ErrorAction SilentlyContinue
    $engineProcess = $null
    if ((Test-Path $sourceEntry) -and (Test-Path $venvPython)) {
        Write-Host "  -> Launching updated source engine (venv: Python 3.14)." -ForegroundColor Cyan
        $engineProcess = Start-Process -FilePath $venvPython -ArgumentList 'run_engine.py' -WorkingDirectory $rootDir -WindowStyle Hidden -PassThru
    } elseif ((Test-Path $sourceEntry) -and $sourcePython) {
        Write-Host "  -> Launching updated source engine (system Python)." -ForegroundColor Cyan
        $engineProcess = Start-Process -FilePath $sourcePython.Source -ArgumentList 'run_engine.py' -WorkingDirectory $rootDir -WindowStyle Hidden -PassThru
    } elseif (Test-Path $standaloneExe) {
        Write-Host "  -> Launching standalone engine: $standaloneExe" -ForegroundColor Cyan
        $engineProcess = Start-Process -FilePath $standaloneExe -WorkingDirectory (Split-Path $standaloneExe) -WindowStyle Hidden -PassThru
    } elseif (Test-Path $resourceExe) {
        Write-Host "  -> Launching packaged engine: $resourceExe" -ForegroundColor Cyan
        $engineProcess = Start-Process -FilePath $resourceExe -WorkingDirectory (Split-Path $resourceExe) -WindowStyle Hidden -PassThru
    } elseif (Test-Path $localExe) {
        Write-Host "  -> Launching local engine: $localExe" -ForegroundColor Cyan
        $engineProcess = Start-Process -FilePath $localExe -WorkingDirectory (Split-Path $localExe) -WindowStyle Hidden -PassThru
    } else {
        $py = if (Test-Path $venvPython) { $venvPython } else { "python.exe" }
        Write-Host "  -> Launching via $py run_engine.py..." -ForegroundColor Cyan
        $engineProcess = Start-Process -FilePath $py -ArgumentList "run_engine.py" -WorkingDirectory $rootDir -WindowStyle Hidden -PassThru
    }

    # Poll for health check
    Write-Host "  -> Waiting for backend engine to report healthy..." -NoNewline
    for ($i = 0; $i -lt 25; $i++) {
        Start-Sleep -Milliseconds 600
        try {
            $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/system/health" -TimeoutSec 1 -UseBasicParsing -ErrorAction Stop
            if ($resp -and $resp.status -eq "healthy" -and $resp.app -eq 'PanelFlow Studio') {
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
        throw "Backend engine did not become healthy. Check the engine log before launching the UI."
    }
}

if ($EngineOnly) { return }

# 2. Check ACE-Step Music Server
if (Test-Path "C:\Tools\ACE-Step-1.5\.venv\Scripts\python.exe") {
    Write-Host "[2/4] Checking ACE-Step music engine on port 8001..." -ForegroundColor Yellow
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
    Write-Host "[2/4] ACE-Step neural model optional. Procedural synthesizer fallback active." -ForegroundColor Gray
}

# 3. Check Ollama Local AI Engine
$ollamaExe = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
if (Test-Path $ollamaExe) {
    Write-Host "[3/4] Checking Ollama AI engine on port 11434..." -ForegroundColor Yellow
    $ollamaHealthy = $false
    try {
        $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 1 -UseBasicParsing -ErrorAction Stop
        if ($tags) { $ollamaHealthy = $true }
    } catch {
        $ollamaHealthy = $false
    }
    if ($ollamaHealthy) {
        $modelNames = ($tags.models | ForEach-Object { $_.name }) -join ', '
        Write-Host "  -> Ollama is running on http://127.0.0.1:11434 ($modelNames)." -ForegroundColor Green
    } else {
        Write-Host "  -> Starting Ollama service in background..." -ForegroundColor Cyan
        Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden
    }
} else {
    Write-Host "[3/4] Ollama local engine optional. Cloud AI fallback active." -ForegroundColor Gray
}

# 4. Launch Desktop Application
Write-Host "[4/4] Launching PanelFlow Studio Desktop..." -ForegroundColor Yellow

$releaseApp = Join-Path $rootDir "apps\desktop\src-tauri\target\release\panelflow-desktop.exe"
$portableCandidates = Get-ChildItem -Path (Join-Path $rootDir "release") -Filter "PanelFlow-Studio-*-Portable.exe" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending
$portableApp = if ($portableCandidates) { $portableCandidates[0].FullName } else { $null }

$candidateApps = @($releaseApp, $portableApp) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | ForEach-Object { Get-Item -LiteralPath $_ }
$nativeApp = $candidateApps | Select-Object -First 1

if (-not $Dev -and $nativeApp) {
    # Check if frontend source code has been updated since the binary was compiled
    $latestSrc = Get-ChildItem -Path (Join-Path $rootDir "apps\desktop\src") -Recurse -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latestSrc -and ($latestSrc.LastWriteTime -gt $nativeApp.LastWriteTime)) {
        Write-Host "  -> Note: Source code in apps/desktop/src was modified ($($latestSrc.LastWriteTime)) after the release binary was built ($($nativeApp.LastWriteTime))." -ForegroundColor Yellow
        Write-Host "  -> Automatically launching updated live desktop app so your latest features and changes are visible." -ForegroundColor Green
        $nativeApp = $null
    }
}

if (-not $Dev -and $nativeApp) {
    # Clean up leftover orphaned WebView2 processes from previous sessions
    Get-CimInstance Win32_Process -Filter "name = 'msedgewebview2.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*panelflow*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

    Write-Host "  -> Launching native desktop application: $($nativeApp.Name)" -ForegroundColor Green
    Write-Host "  -> Keep this window open while using PanelFlow Studio." -ForegroundColor Cyan
    Write-Host ""
    Write-Host "PanelFlow Studio is ready!" -ForegroundColor Green
    $desktopProcess = Start-Process -FilePath $nativeApp.FullName -WorkingDirectory $rootDir -PassThru
    $desktopProcess.WaitForExit()

    # Clean up backend engine when desktop window closes
    if ($engineProcess -and -not $engineProcess.HasExited) {
        Stop-Process -Id $engineProcess.Id -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Host "  -> Launching in development mode (Vite live reload)..." -ForegroundColor Cyan
    Write-Host "  -> Keep this window open while using PanelFlow Studio." -ForegroundColor Cyan

    # Start Vite dev server in background process if not already running on port 5173
    $alreadyListening = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
    $viteProcess = $null
    if (-not $alreadyListening) {
        $viteProcess = Start-Process -FilePath "npm.cmd" -ArgumentList "--workspace=@panelflow/desktop", "run", "dev" -WorkingDirectory $rootDir -PassThru
    } else {
        Write-Host "  -> Existing Vite dev server already active on port 5173." -ForegroundColor Green
    }
    
    # Wait for Vite dev server on port 5173
    $viteReady = $false
    for ($i = 0; $i -lt 15; $i++) {
        Start-Sleep -Milliseconds 500
        try {
            $tcp = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
            if ($tcp) { $viteReady = $true; break }
        } catch {}
    }
    
    if (-not $viteReady) {
        Write-Host "  -> Waiting for Vite server..." -ForegroundColor Cyan
        Start-Sleep -Seconds 2
    }

    # Launch standalone application window via Edge/Chrome app mode
    $browserCandidates = @(
        "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "C:\Program Files\Google\Chrome\Application\chrome.exe",
        "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    )
    $browserApp = $browserCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    $appUrl = if ($env:PANELFLOW_ENGINE_TOKEN) { "http://localhost:5173?token=$($env:PANELFLOW_ENGINE_TOKEN)" } else { "http://localhost:5173" }
    $profileDir = Join-Path $env:LOCALAPPDATA 'PanelFlow Studio\desktop_profile'
    New-Item -ItemType Directory -Force -Path $profileDir | Out-Null

    if ($browserApp) {
        Write-Host "  -> Launching PanelFlow Studio standalone window..." -ForegroundColor Green
        $desktopProcess = Start-Process -FilePath $browserApp -ArgumentList "--app=$appUrl", "--user-data-dir=`"$profileDir`"", "--window-size=1360,900" -PassThru
        $desktopProcess.WaitForExit()
    } else {
        Write-Host "  -> Opening PanelFlow Studio at $appUrl..." -ForegroundColor Green
        Start-Process $appUrl
        $viteProcess.WaitForExit()
    }

    # Clean up background services when window closes
    if ($viteProcess -and -not $viteProcess.HasExited) {
        Stop-Process -Id $viteProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if ($engineProcess -and -not $engineProcess.HasExited) {
        Stop-Process -Id $engineProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
