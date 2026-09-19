[CmdletBinding()]
param()

$Root = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $Root 'runtime\hermes-marketing-gateway.pid'
$Hermes = Join-Path $env:LOCALAPPDATA 'hermes\bin\hermes.exe'
$Uv = Join-Path $env:LOCALAPPDATA 'hermes\bin\uv.exe'
if (Test-Path -LiteralPath $Hermes) {
    $GatewayStatus = (& $Hermes -p marketing gateway status 2>&1 | Out-String)
    if ($LASTEXITCODE -eq 0 -and $GatewayStatus -match 'Gateway(?: process| is)? running') {
        Write-Output 'Hermes marketing gateway: RUNNING'
    }
    elseif (Test-Path -LiteralPath $PidFile) {
        $GatewayPid = [int](Get-Content -LiteralPath $PidFile -Raw)
        if (Get-Process -Id $GatewayPid -ErrorAction SilentlyContinue) { Write-Output "Hermes marketing gateway: RUNNING (PID $GatewayPid)" }
        else { Write-Output 'Hermes marketing gateway: STALE_PID' }
    }
    else { Write-Output 'Hermes marketing gateway: STOPPED' }
}
elseif (Test-Path -LiteralPath $PidFile) {
    $GatewayPid = [int](Get-Content -LiteralPath $PidFile -Raw)
    if (Get-Process -Id $GatewayPid -ErrorAction SilentlyContinue) { Write-Output "Hermes marketing gateway: RUNNING (PID $GatewayPid)" }
    else { Write-Output 'Hermes marketing gateway: STALE_PID' }
}
else { Write-Output 'Hermes marketing gateway: STOPPED' }
Push-Location $Root
try { & $Uv run marketing-system status }
finally { Pop-Location }
