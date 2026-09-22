# Local AI Marketing System

Local-first marketing orchestration for Buzz + Hermes, with an MCP integration boundary, deterministic mock connectors, canonical SQLite staging, and code-enforced safety gates.

Current status: `PHASE_2_IN_PROGRESS`. Buzz → Hermes → Marketing Orchestrator → MCP is live. The public website connector is `CONNECTED` and has completed a normalized read; account-backed providers remain approval/MFA-gated as listed in `INTEGRATION_MATRIX.md`.

## Quick check

```powershell
cd C:\Users\Admin\marketing-ai-system
.\scripts\status-all.ps1
.\scripts\smoke-test.ps1
```

See `RUNBOOK.md` for provider/Buzz onboarding and daily start/stop commands. See `ACCOUNTS_REQUIRED.md` for external service setup.
