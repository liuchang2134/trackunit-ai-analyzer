param([string]$PythonExecutable = '')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$basePython = if ($PythonExecutable) { (Get-Command $PythonExecutable -ErrorAction Stop).Source } else { (Get-Command python -ErrorAction Stop).Source }
& $basePython -c 'import sys; assert (3,11) <= sys.version_info < (3,14), "Python 3.11-3.13 required; tested on 3.12"'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11-3.13 is required. Use -PythonExecutable to select an installed interpreter.' }
$localPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $localPython)) {
    & $basePython -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
& $localPython -c 'import sys; assert (3,11) <= sys.version_info < (3,14), "Existing venv Python is unsupported"'
if ($LASTEXITCODE -ne 0) { throw 'Existing .venv uses an unsupported Python. Preserve it and set up this release in a new directory.' }
$dependencyArgs = @('-r', (Join-Path $PSScriptRoot 'requirements.txt'))
$xgssRequirements = Join-Path $PSScriptRoot 'requirements-xgss.txt'
if (Test-Path -LiteralPath $xgssRequirements) { $dependencyArgs += @('-r', $xgssRequirements) }
& $localPython -m pip install @dependencyArgs
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
if (!(Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
& $localPython (Join-Path $PSScriptRoot 'scripts/prepare_parts_demo.py') --install
if ($LASTEXITCODE -ne 0) { throw 'Demo preparation failed; inspect the existing local catalog for conflicts.' }
Write-Host 'Dependencies and synthetic demo ready. Configure GEMINI_API_KEY in .env. Gemini mode does not require Ollama.'
Write-Host 'Then run start_local.ps1. Existing .env settings have been preserved.'
Write-Host 'To inspect synthetic data before configuring cloud AI, run start_local.ps1 -DemoOnly.'
