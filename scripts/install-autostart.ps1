[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Hermes = Join-Path $env:LOCALAPPDATA 'hermes\bin\hermes.exe'
if (-not (Test-Path -LiteralPath $Hermes)) { throw "Hermes not found: $Hermes" }

Push-Location $Root
try {
    & $Hermes -p marketing config set gateway.multiplex_profiles false | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not select the standalone marketing gateway mode.' }
    & $Hermes -p marketing gateway install --force --start-on-login --start-now
    if ($LASTEXITCODE -ne 0) { throw 'Hermes marketing autostart installation failed.' }
    for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
        Start-Sleep -Seconds 1
        $StatePath = Join-Path $env:LOCALAPPDATA 'hermes\profiles\marketing\gateway_state.json'
        if (Test-Path -LiteralPath $StatePath) {
            $State = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
            if ($State.gateway_state -eq 'running' -and $State.platforms.buzz.state -eq 'connected') {
                Remove-Item -LiteralPath (Join-Path $Root 'runtime\hermes-marketing-gateway.pid') -Force -ErrorAction SilentlyContinue
                Write-Output 'Marketing autostart installed, enabled, and Buzz-connected.'
                exit 0
            }
        }
    }
    throw 'Autostart was installed, but Buzz did not reach connected state within 30 seconds.'
}
finally { Pop-Location }
