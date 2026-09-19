[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Hermes = Join-Path $env:LOCALAPPDATA 'hermes\bin\hermes.exe'
if (-not (Test-Path -LiteralPath $Hermes)) { throw "Hermes not found: $Hermes" }

& $Hermes -p marketing gateway uninstall
if ($LASTEXITCODE -ne 0) { throw 'Hermes marketing autostart removal failed.' }
Write-Output 'Marketing autostart removed. Profile configuration and secrets were preserved.'
