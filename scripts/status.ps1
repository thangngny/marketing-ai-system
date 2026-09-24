[CmdletBinding()]
param()

# One-screen status: runtime, gateway, connectors, workflows, approvals.
$Root = Split-Path -Parent $PSScriptRoot
$Uv = Join-Path $env:LOCALAPPDATA 'hermes\bin\uv.exe'
Push-Location $Root
try {
    & $Uv run marketing-system doctor
    Write-Output ''
    Write-Output 'Workflows:'
    & $Uv run marketing-system workflows list
    Write-Output ''
    Write-Output 'Approvals:'
    & $Uv run marketing-system approvals list
}
finally { Pop-Location }
