[CmdletBinding()]
param([switch]$Live)

$Root = Split-Path -Parent $PSScriptRoot
$Uv = Join-Path $env:LOCALAPPDATA 'hermes\bin\uv.exe'
Push-Location $Root
try {
    if ($Live) { & $Uv run marketing-system doctor --live }
    else { & $Uv run marketing-system doctor }
    exit $LASTEXITCODE
}
finally { Pop-Location }

