[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $Root 'runtime\hermes-marketing-gateway.pid'
$Hermes = Join-Path $env:LOCALAPPDATA 'hermes\bin\hermes.exe'
if (Test-Path -LiteralPath $Hermes) {
    $GatewayStatus = (& $Hermes -p marketing gateway status 2>&1 | Out-String)
    if ($LASTEXITCODE -eq 0 -and $GatewayStatus -match 'Gateway(?: process| is)? running') {
        & $Hermes -p marketing gateway stop | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Hermes native gateway stop failed.' }
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        Write-Output 'Marketing gateway stopped cleanly.'
        exit 0
    }
}
if (-not (Test-Path -LiteralPath $PidFile)) {
    Write-Output 'Marketing gateway is not running.'
    exit 0
}
$GatewayPid = [int](Get-Content -LiteralPath $PidFile -Raw)
$Process = Get-CimInstance Win32_Process -Filter "ProcessId=$GatewayPid" -ErrorAction SilentlyContinue
if ($Process) {
    $Command = [string]$Process.CommandLine
    if ($Process.Name -notmatch '^hermes(\.exe)?$' -or $Command -notmatch 'marketing' -or $Command -notmatch 'gateway') {
        throw "PID $GatewayPid is not the recorded marketing gateway; refusing to stop it."
    }
    if (Test-Path -LiteralPath $Hermes) {
        & $Hermes -p marketing gateway stop | Out-Null
        for ($Attempt = 0; $Attempt -lt 20; $Attempt++) {
            if (-not (Get-Process -Id $GatewayPid -ErrorAction SilentlyContinue)) { break }
            Start-Sleep -Milliseconds 250
        }
    }
    if (Get-Process -Id $GatewayPid -ErrorAction SilentlyContinue) {
        Stop-Process -Id $GatewayPid
        Write-Output "Marketing gateway required forced fallback stop (PID $GatewayPid)."
    }
    else {
        Write-Output "Marketing gateway stopped cleanly (PID $GatewayPid)."
    }
}
else {
    Write-Output 'Recorded marketing gateway process is already gone.'
}
Remove-Item -LiteralPath $PidFile -Force
