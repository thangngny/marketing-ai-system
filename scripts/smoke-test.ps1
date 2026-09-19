[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Uv = Join-Path $env:LOCALAPPDATA 'hermes\bin\uv.exe'
$env:MARKETING_ENVIRONMENT = 'mock'
$env:MARKETING_SAFE_DRY_RUN = 'true'
Push-Location $Root
try {
    & $Uv run pytest
    if ($LASTEXITCODE -ne 0) { throw 'Automated tests failed.' }
    & $Uv run marketing-system acceptance
    if ($LASTEXITCODE -ne 0) { throw 'Mock acceptance tests failed.' }
}
finally { Pop-Location }

