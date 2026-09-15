param([ValidateRange(1024,65535)][int]$Port = 8890, [switch]$DemoOnly)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $projectPython)) { $projectPython = Join-Path $PSScriptRoot '.tmp/venv/Scripts/python.exe' }
if (!(Test-Path -LiteralPath $projectPython)) { $projectPython = (Get-Command python -ErrorAction Stop).Source }
$readinessArgs = @((Join-Path $PSScriptRoot 'scripts/check_local_runtime.py'))
if ($DemoOnly) { $readinessArgs += '--demo-only' }
& $projectPython @readinessArgs
if ($LASTEXITCODE -ne 0) { throw 'Assistant prerequisites are incomplete. Check dependencies and configured AI provider credentials.' }
if ($DemoOnly) { Write-Host 'Local demonstration access: cloud readiness has not been verified. AI analysis still requires your configured provider.' }
$existing = $null
try { $existing = Invoke-RestMethod "http://127.0.0.1:$Port/openapi.json" -TimeoutSec 3 } catch {}
if ($existing) {
    if ($existing.info.title -ne 'Trackunit AI Analyzer') { throw "Port $Port is serving another application." }
    $runningConfiguration = $null
    try { $runningConfiguration = Invoke-RestMethod "http://127.0.0.1:$Port/assistant/runtime" -TimeoutSec 3 } catch {}
    if (!$runningConfiguration) { throw 'An older backend is running. Close its terminal yourself, or use a free port from 8890/8892 and choose the same port in the Chrome extension connection settings.' }
    $expectedBuild = & $projectPython -c 'from app.assistant_version import ASSISTANT_BUILD; print(ASSISTANT_BUILD)'
    if ($runningConfiguration.backend_build -ne $expectedBuild.Trim()) { throw 'The running backend is an older build. Close its terminal yourself or use a free port from 8890/8892 and choose the same port in the Chrome extension connection settings.' }
    if ($runningConfiguration.provider -eq 'gemini' -and ($runningConfiguration.investigation_timeout_seconds -ne 120 -or $runningConfiguration.transient_attempt_limit -ne 3)) { throw 'The backend version label is current but its runtime behavior is stale. Restart the backend before accepting this build.' }
    Write-Host "Assistant already running: http://127.0.0.1:$Port/assistant-ui/ ($($runningConfiguration.provider) / $($runningConfiguration.model))"
    return
}
Write-Host "Starting assistant: http://127.0.0.1:$Port/assistant-ui/"
& (Join-Path $PSScriptRoot 'run_backend.ps1') -Port $Port
