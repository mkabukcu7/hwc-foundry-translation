# SPDX-License-Identifier: MIT
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
Get-Content .env | ForEach-Object {
    if ($_ -match '^([A-Z][A-Z0-9_]*)=(.*)$') { Set-Item "env:$($Matches[1])" $Matches[2] }
}
if (-not $env:PYTHON_EXECUTABLE) { throw 'Set PYTHON_EXECUTABLE in .env to an installed Python environment' }
$env:PYTHONPATH = "$(Get-Location);$(Join-Path (Get-Location) 'src')"
Write-Host "Translation showcase: http://localhost:8765 (local access only; Ctrl+C to stop)"
& $env:PYTHON_EXECUTABLE -m uvicorn scripts.showcase:app --host 127.0.0.1 --port 8765 --no-access-log
exit $LASTEXITCODE
