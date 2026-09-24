[CmdletBinding()]
param([switch]$Live)

# Full automated suite (hermetic, mock). -Live adds read-only live checks against real providers.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Uv = Join-Path $env:LOCALAPPDATA 'hermes\bin\uv.exe'
Push-Location $Root
try {
    & $Uv run pytest -o addopts="" -q
    if ($LASTEXITCODE -ne 0) { throw 'Automated tests failed.' }
    if ($Live) {
        $env:RUN_LIVE_RUNTIME_TESTS = '1'
        & $Uv run pytest -o addopts="" -q -k live tests/test_runtime_contract.py
        if ($LASTEXITCODE -ne 0) { throw 'Live runtime test failed.' }
        & $Uv run python scripts/live_read_check.py
    }
}
finally { Pop-Location }
