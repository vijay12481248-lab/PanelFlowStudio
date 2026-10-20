# Run with: powershell -NoProfile -File tests/unit/test_launcher_restart.ps1
# Every process and network operation is mocked; no running engine is touched.
$ErrorActionPreference = 'Stop'
$global:panelFlowTestHealthCalls = 0
$global:panelFlowTestStopped = @()
$global:panelFlowTestLaunched = $null
$global:panelFlowTestMode = 'idle'
$global:panelFlowTestCancelled = $false
$global:panelFlowTestCancelCalls = 0
function Invoke-RestMethod {
    param($Uri, $TimeoutSec, [switch]$UseBasicParsing, $ErrorAction, $Method)
    if ($Uri -match '/health$') {
        $global:panelFlowTestHealthCalls++
        return [pscustomobject]@{status='healthy';app='PanelFlow Studio';version='test'}
    }
    if ($Uri -match '/api/jobs\?') {
        if ($global:panelFlowTestMode -in @('busy', 'pending') -and -not $global:panelFlowTestCancelled) { return [pscustomobject]@{job_id='test-job';job_type='STORY_ANALYSIS';status='RUNNING';progress=0.8;project_id='test-project';started_at='2026-10-19T22:00:00Z'} }
        return ,@()
    }
    if ($Uri -match '/api/projects$') {
        if ($global:panelFlowTestMode -eq 'render') { return [pscustomobject]@{id='test-project'} }
        return ,@()
    }
    if ($Uri -match '/render/jobs$') {
        if (-not $global:panelFlowTestCancelled) { return [pscustomobject]@{render_id='test-render';status='ENCODING';progress=0.8} }
        return ,@()
    }
    if ($Uri -match '/cancel$' -and $Method -eq 'Post') {
        $global:panelFlowTestCancelCalls++
        if ($global:panelFlowTestMode -ne 'pending') { $global:panelFlowTestCancelled=$true }
        return [pscustomobject]@{status='CANCELLED'}
    }
    throw "Unexpected URL: $Uri"
}
function Get-NetTCPConnection { param($LocalPort,$State,$ErrorAction); [pscustomobject]@{OwningProcess=12345} }
function Get-CimInstance {
    param($ClassName,$Filter)
    if ($global:panelFlowTestMode -eq 'unrelated') { return [pscustomobject]@{CommandLine='python unrelated.py'} }
    [pscustomobject]@{CommandLine='python run_engine.py'}
}
function Stop-Process { param($Id,$ErrorAction); $global:panelFlowTestStopped += $Id }
function Wait-Process { param($Id,$Timeout,$ErrorAction) }
function Start-Process { param($FilePath,$ArgumentList,$WorkingDirectory,$WindowStyle); $global:panelFlowTestLaunched=@{FilePath=$FilePath;ArgumentList=$ArgumentList;WindowStyle=$WindowStyle} }
function Start-Sleep { param($Milliseconds,$Seconds) }
function Read-Host { param($Prompt); return 'n' }
& (Join-Path $PSScriptRoot '..\..\launch_panelflow.ps1') -EngineOnly
if ($global:panelFlowTestStopped.Count -ne 1 -or $global:panelFlowTestStopped[0] -ne 12345) { throw 'Existing engine was not restarted' }
if ($global:panelFlowTestLaunched.ArgumentList -ne 'run_engine.py' -or $global:panelFlowTestLaunched.WindowStyle -ne 'Hidden') { throw 'Updated source engine was not launched hidden' }
if ($global:panelFlowTestHealthCalls -lt 2) { throw 'Restarted engine was not health checked' }
Write-Output 'PASS: launcher validates, restarts, starts source engine, and checks health (mocked)'
foreach ($failureMode in @('unrelated')) {
    $global:panelFlowTestMode = $failureMode
    $global:panelFlowTestStopped = @()
    $global:panelFlowTestLaunched = $null
    $rejected = $false
    try { & (Join-Path $PSScriptRoot '..\..\launch_panelflow.ps1') -EngineOnly }
    catch { $rejected = $true }
    if (-not $rejected -or $global:panelFlowTestStopped.Count -ne 0 -or $global:panelFlowTestLaunched) {
        throw "Launcher did not refuse $failureMode restart"
    }
    Write-Output "PASS: launcher refuses $failureMode restart (mocked)"
}

$global:panelFlowTestMode='busy'
$global:panelFlowTestStopped=@()
$global:panelFlowTestLaunched=$null
& (Join-Path $PSScriptRoot '..\..\launch_panelflow.ps1') -EngineOnly
if ($global:panelFlowTestStopped.Count -or $global:panelFlowTestCancelCalls) { throw 'Declining cancellation must preserve existing jobs and engine' }
Write-Output 'PASS: declining cancellation keeps the engine running (mocked)'

foreach ($cancelMode in @('busy', 'render', 'pending')) {
    $global:panelFlowTestMode=$cancelMode
    $global:panelFlowTestCancelled=$false
    $global:panelFlowTestCancelCalls=0
    $global:panelFlowTestStopped=@()
    $global:panelFlowTestLaunched=$null
    $failed=$false
    try { & (Join-Path $PSScriptRoot '..\..\launch_panelflow.ps1') -EngineOnly -CancelJobs }
    catch { $failed=$true }
    if ($global:panelFlowTestCancelCalls -ne 1) { throw "Expected exactly one $cancelMode cancellation" }
    if ($cancelMode -eq 'pending') {
        if (-not $failed -or $global:panelFlowTestStopped.Count) { throw 'Engine stopped before cancellation completed' }
    } elseif ($failed -or $global:panelFlowTestStopped.Count -ne 1 -or -not $global:panelFlowTestLaunched) {
        throw "Cancel-and-restart failed for $cancelMode"
    }
    Write-Output "PASS: $cancelMode cancellation behavior (mocked)"
}
