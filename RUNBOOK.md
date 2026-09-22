# Runbook

## Current state

The native Buzz → Hermes `marketing` profile path is live. `SAFE_DRY_RUN` remains enabled. The public website connector is live-verified; account-backed integrations remain gated until their provider OAuth/MFA steps complete.

- Bot public identity: `8f006f396a54839e0cc320ee2a3b48226ef2c34039fe6f1754e6b7d0e4112cf1`
- Community relay: `https://phamgianam.communities.buzz.xyz`
- Channel: `Welcome` (`6fdc7c8d-8c62-4308-8228-fc3ec44944bb`)
- Provider/model: OpenAI Codex OAuth / `gpt-5.6-sol`

Private identity material and the NIP-OA attestation live only in the restricted Hermes profile secret file outside Git.

## Daily commands

```powershell
cd C:\Users\Admin\marketing-ai-system
.\scripts\status-all.ps1
```

The gateway starts automatically at user login. Manual lifecycle commands are idempotent:

```powershell
.\scripts\start-all.ps1
.\scripts\stop-all.ps1
```

## Diagnostics and tests

```powershell
.\scripts\doctor.ps1
.\scripts\smoke-test.ps1
```

`doctor.ps1` verifies the marketing provider configuration and current native Buzz gateway state. `smoke-test.ps1` is local/mock-only; live relay evidence is recorded in `TEST_REPORT.md`.

## Phase 2 credentials and OAuth

Connector secrets are stored in Windows Credential Manager and are never passed as command-line arguments:

```powershell
uv run marketing-system credentials status
uv run marketing-system credentials set NAME
```

The `set` command uses a hidden prompt. After provider app registration, the supported OAuth flows capture the callback locally and store only the refresh token in Credential Manager:

```powershell
uv run marketing-system oauth zoho
uv run marketing-system oauth m365
```

Read-only live ingestion is exposed to Hermes through `marketing_sync_readonly`. It is refused in `mock`, live-verifies the connector first, normalizes provider records, and writes only to SQLite staging.

## Autostart

Installed through Hermes' Windows user-level Startup-folder fallback because Scheduled Task creation requested UAC and no elevation was granted.

```powershell
.\scripts\install-autostart.ps1
.\scripts\remove-autostart.ps1
```

The startup item contains no private key or OAuth token. Hermes reads the restricted profile files at runtime.

## Logs

- Integration JSONL: `logs\marketing.jsonl` (redacted, Git-ignored).
- Hermes gateway/agent logs: `%LOCALAPPDATA%\hermes\profiles\marketing\logs`.
- Live gateway state: `%LOCALAPPDATA%\hermes\profiles\marketing\gateway_state.json`.

## Safety

- Keep the gateway in `MARKETING_ENVIRONMENT=mock` and `MARKETING_SAFE_DRY_RUN=true` while OAuth onboarding is incomplete. Read-only validation may use an isolated production-scoped process.
- `READ` and local `DRAFT` work are allowed.
- `WRITE` requires human approval.
- Paid ads, public publishing, outreach, email send, permission changes, and production mutations remain blocked.

## Rollback

```powershell
.\scripts\stop-all.ps1
.\scripts\remove-autostart.ps1
```

These commands preserve the marketing profile, its secrets, and all project data. The default Hermes profile is not modified.
