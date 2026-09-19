[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Runtime = Join-Path $Root 'runtime'
$PidFile = Join-Path $Runtime 'hermes-marketing-gateway.pid'
$Hermes = Join-Path $env:LOCALAPPDATA 'hermes\bin\hermes.exe'
$ProfileHome = Join-Path $env:LOCALAPPDATA 'hermes\profiles\marketing'

New-Item -ItemType Directory -Path $Runtime -Force | Out-Null
if (-not (Test-Path -LiteralPath $Hermes)) { throw "Hermes not found: $Hermes" }
if (-not (Test-Path -LiteralPath $ProfileHome)) { throw 'Marketing profile missing. Run setup-profile.ps1.' }

$GatewayStatus = (& $Hermes -p marketing gateway status 2>&1 | Out-String)
if ($LASTEXITCODE -eq 0 -and $GatewayStatus -match 'Gateway(?: process| is)? running') {
    Write-Output 'Marketing gateway already running.'
    exit 0
}
if (Test-Path -LiteralPath $PidFile) {
    $ExistingPid = [int](Get-Content -LiteralPath $PidFile -Raw)
    $Existing = Get-Process -Id $ExistingPid -ErrorAction SilentlyContinue
    if ($Existing) {
        Write-Output "Marketing gateway already running (PID $ExistingPid)."
        exit 0
    }
    Remove-Item -LiteralPath $PidFile -Force
}
$EnvFile = Join-Path $ProfileHome '.env'
$HasBuzzKey = (Test-Path -LiteralPath $EnvFile -PathType Leaf) -and (Select-String -LiteralPath $EnvFile -Pattern '^BUZZ_PRIVATE_KEY=\S+' -Quiet)
if (-not $HasBuzzKey) { throw 'Buzz identity missing. Run configure-buzz.ps1 with the dedicated identity.' }

# Prefer the Hermes-managed user service when autostart has been installed.
& $Hermes -p marketing gateway start 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    Start-Sleep -Seconds 2
    $GatewayStatus = (& $Hermes -p marketing gateway status 2>&1 | Out-String)
    if ($LASTEXITCODE -eq 0 -and $GatewayStatus -match 'Gateway(?: process| is)? running') {
        Write-Output 'Marketing gateway started via Hermes user service.'
        exit 0
    }
}

$Process = Start-Process -FilePath $Hermes -ArgumentList @('-p','marketing','gateway','run') -WorkingDirectory $Root -WindowStyle Hidden -PassThru
Set-Content -LiteralPath $PidFile -Value $Process.Id -Encoding ascii
Start-Sleep -Seconds 2
if (-not (Get-Process -Id $Process.Id -ErrorAction SilentlyContinue)) {
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    throw 'Marketing gateway exited during startup. Run doctor.ps1 and inspect Hermes gateway logs.'
}
Write-Output "Marketing gateway started (PID $($Process.Id))."
