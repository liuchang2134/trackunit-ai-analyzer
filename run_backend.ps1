param([ValidateRange(1024,65535)][int]$Port = 8890)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $projectPython)) {
    $projectPython = Join-Path $PSScriptRoot '.tmp/venv/Scripts/python.exe'
}
if (!(Test-Path -LiteralPath $projectPython)) {
    $projectPython = (Get-Command python -ErrorAction Stop).Source
}
& $projectPython -m uvicorn app.main:app --host 127.0.0.1 --port $Port
