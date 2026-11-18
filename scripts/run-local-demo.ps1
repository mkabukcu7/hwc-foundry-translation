# SPDX-License-Identifier: MIT
param(
    [Parameter(Mandatory)][string]$InputFile,
    [string]$SourceLanguage,
    [Parameter(Mandatory)][string[]]$TargetLanguages,
    [ValidateSet('translator', 'llm')]
    [string]$Engine = 'translator'
)
$ErrorActionPreference = 'Stop'
Get-Content (Join-Path $PSScriptRoot '..\.env') | ForEach-Object {
    if ($_ -match '^([A-Z][A-Z0-9_]*)=(.*)$') { Set-Item "env:$($Matches[1])" $Matches[2] }
}
if (-not $env:PYTHON_EXECUTABLE) { throw 'Set PYTHON_EXECUTABLE in .env to an installed Python environment' }
$env:PYTHONPATH = Join-Path $PSScriptRoot '..\src'
$cli = @($InputFile, '--engine', $Engine, '--target-languages') + $TargetLanguages
if ($SourceLanguage) { $cli += @('--source-language', $SourceLanguage) }
& $env:PYTHON_EXECUTABLE (Join-Path $PSScriptRoot 'local_demo.py') @cli
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
