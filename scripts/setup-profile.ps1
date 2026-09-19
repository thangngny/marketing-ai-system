[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Hermes = Join-Path $env:LOCALAPPDATA 'hermes\bin\hermes.exe'
$Uv = Join-Path $env:LOCALAPPDATA 'hermes\bin\uv.exe'
$ProfileId = 'marketing'
$ProfileHome = Join-Path $env:LOCALAPPDATA "hermes\profiles\$ProfileId"

if (-not (Test-Path -LiteralPath $Hermes)) { throw "Hermes not found: $Hermes" }
if (-not (Test-Path -LiteralPath $Uv)) { throw "uv not found: $Uv" }

Push-Location $Root
try {
    & $Uv sync --frozen
    if ($LASTEXITCODE -ne 0) { throw 'uv sync failed' }

    & $Hermes profile show $ProfileId *> $null
    if ($LASTEXITCODE -ne 0) {
        & $Hermes profile create $ProfileId --clone-from default --no-alias --description 'Marketing Orchestrator for Buzz, specialist routing, safe MCP connectors, and mock-first workflows.'
        if ($LASTEXITCODE -ne 0) { throw 'Hermes profile creation failed' }
    }

    if (-not (Test-Path -LiteralPath $ProfileHome)) { throw "Expected profile home not found: $ProfileHome" }
    New-Item -ItemType Directory -Path (Join-Path $ProfileHome 'skills') -Force | Out-Null
    Get-ChildItem -LiteralPath (Join-Path $Root 'hermes\skills') -Directory | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $ProfileHome 'skills') -Recurse -Force
    }
    Copy-Item -LiteralPath (Join-Path $Root 'hermes\SOUL.md') -Destination (Join-Path $ProfileHome 'SOUL.md') -Force

    & $Hermes -p $ProfileId config set terminal.cwd $Root
    & $Hermes -p $ProfileId config set streaming.enabled false
    & $Hermes -p $ProfileId config set display.interim_assistant_messages false

    $McpList = (& $Hermes -p $ProfileId mcp list 2>&1 | Out-String)
    if ($McpList -notmatch 'marketing-system') {
        $Python = Join-Path $Root '.venv\Scripts\python.exe'
        'Y' | & $Hermes -p $ProfileId mcp add marketing-system --command $Python --args -m marketing_system.mcp_server
        if ($LASTEXITCODE -ne 0) { throw 'MCP registration failed' }
        $McpList = (& $Hermes -p $ProfileId mcp list 2>&1 | Out-String)
        if ($McpList -notmatch 'marketing-system') { throw 'MCP registration did not persist.' }
    }
    Write-Output 'Marketing profile: CONFIGURED (Buzz identity/provider still required).'
}
finally {
    Pop-Location
}
