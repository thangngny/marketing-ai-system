[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ChannelId,
    [string]$OwnerNpub,
    [string]$RelayUrl = 'https://phamgianam.communities.buzz.xyz',
    [switch]$GenerateIdentity
)

$ErrorActionPreference = 'Stop'
$Hermes = Join-Path $env:LOCALAPPDATA 'hermes\bin\hermes.exe'
$ProfileId = 'marketing'
$ProfileHome = Join-Path $env:LOCALAPPDATA "hermes\profiles\$ProfileId"
$EnvFile = Join-Path $ProfileHome '.env'
$BuzzCli = 'D:\Buzz\buzz.exe'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$HermesPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$HermesSource = Join-Path $env:LOCALAPPDATA 'hermes\hermes-agent'

if (-not (Test-Path -LiteralPath $Hermes)) { throw "Hermes not found: $Hermes" }
if (-not (Test-Path -LiteralPath $BuzzCli)) { throw "Buzz CLI not found: $BuzzCli" }
if (-not (Test-Path -LiteralPath $HermesPython)) { throw "Hermes Python not found: $HermesPython" }
if (-not (Test-Path -LiteralPath $ProfileHome)) { throw 'Run setup-profile.ps1 first.' }
if ([string]::IsNullOrWhiteSpace($OwnerNpub)) {
    $ManagedAgents = Join-Path $env:APPDATA 'xyz.block.buzz.app\agents\managed-agents.json'
    if (Test-Path -LiteralPath $ManagedAgents) {
        $Candidates = @(
            (Get-Content -LiteralPath $ManagedAgents -Raw | ConvertFrom-Json) |
                ForEach-Object {
                    if (-not [string]::IsNullOrWhiteSpace($_.auth_tag)) {
                        try {
                            $Tag = $_.auth_tag | ConvertFrom-Json
                            if ($Tag.Count -eq 4 -and $Tag[0] -eq 'auth' -and $Tag[1] -match '^[0-9a-fA-F]{64}$') {
                                [string]$Tag[1]
                            }
                        }
                        catch { }
                    }
                } |
                Sort-Object -Unique
        )
        if ($Candidates.Count -eq 1) { $OwnerNpub = [string]$Candidates[0] }
    }
}
if ([string]::IsNullOrWhiteSpace($OwnerNpub)) { throw 'Owner npub/hex is required; pass -OwnerNpub explicitly.' }

$PlainKey = $null
$PublicIdentity = $null
$Pointer = [IntPtr]::Zero
try {
    if ($GenerateIdentity) {
        $Bytes = [byte[]]::new(32)
        [System.Security.Cryptography.RandomNumberGenerator]::Fill($Bytes)
        $PlainKey = [Convert]::ToHexString($Bytes).ToLowerInvariant()
        [Array]::Clear($Bytes, 0, $Bytes.Length)
    }
    else {
        $SecureKey = Read-Host 'Paste the dedicated Marketing Orchestrator nsec/private key' -AsSecureString
        $Pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureKey)
        $PlainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Pointer)
    }
    if ([string]::IsNullOrWhiteSpace($PlainKey)) { throw 'Empty Buzz private key.' }

    $env:BUZZ_KEY_CANDIDATE = $PlainKey
    $env:HERMES_SOURCE_ROOT = $HermesSource
    $PublicIdentity = & $HermesPython -c "import importlib.util,os,pathlib; p=pathlib.Path(os.environ['HERMES_SOURCE_ROOT'])/'plugins/platforms/buzz/nostr_auth.py'; s=importlib.util.spec_from_file_location('buzz_nostr_auth',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(m.public_key_hex(os.environ['BUZZ_KEY_CANDIDATE']))"
    if ($LASTEXITCODE -ne 0 -or $PublicIdentity -notmatch '^[0-9a-f]{64}$') { throw 'Generated/provided Buzz private key is invalid.' }

    $Existing = if (Test-Path -LiteralPath $EnvFile) { Get-Content -LiteralPath $EnvFile } else { @() }
    $Filtered = @($Existing | Where-Object { $_ -notmatch '^BUZZ_PRIVATE_KEY=' })
    $Filtered + "BUZZ_PRIVATE_KEY=$PlainKey" | Set-Content -LiteralPath $EnvFile -Encoding utf8
    $Acl = Get-Acl -LiteralPath $EnvFile
    $Acl.SetAccessRuleProtection($true, $false)
    $Acl.AddAccessRule([System.Security.AccessControl.FileSystemAccessRule]::new(
        [System.Security.Principal.WindowsIdentity]::GetCurrent().Name,
        [System.Security.AccessControl.FileSystemRights]::FullControl,
        [System.Security.AccessControl.AccessControlType]::Allow
    ))
    Set-Acl -LiteralPath $EnvFile -AclObject $Acl
}
finally {
    if ($Pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Pointer) }
    Remove-Item Env:BUZZ_KEY_CANDIDATE -ErrorAction SilentlyContinue
    Remove-Item Env:HERMES_SOURCE_ROOT -ErrorAction SilentlyContinue
    $PlainKey = $null
}

& $Hermes -p $ProfileId config set gateway.platforms.buzz.enabled true
& $Hermes -p $ProfileId config set gateway.platforms.buzz.extra.relay_url $RelayUrl
& $Hermes -p $ProfileId config set gateway.platforms.buzz.extra.cli_path $BuzzCli
& $Hermes -p $ProfileId config set gateway.platforms.buzz.extra.channels "[$ChannelId]"
& $Hermes -p $ProfileId config set gateway.platforms.buzz.extra.home_channel $ChannelId
& $Hermes -p $ProfileId config set gateway.platforms.buzz.extra.allowed_users "[$OwnerNpub]"
& $Hermes -p $ProfileId config set gateway.platforms.buzz.extra.allow_all_users false
& $Hermes -p $ProfileId config set gateway.platforms.buzz.extra.require_mention true
& $Hermes -p $ProfileId config set display.platforms.buzz.interim_assistant_messages false --force
& $Hermes -p $ProfileId config set display.platforms.buzz.tool_progress off --force

Write-Output "Buzz public identity: $PublicIdentity"
Write-Output 'Buzz gateway settings saved. The private key was not printed. Run doctor.ps1 before start-all.ps1.'
