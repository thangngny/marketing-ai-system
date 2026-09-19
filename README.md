# Local AI Marketing System

Local-first marketing orchestration for Buzz + Hermes, with an MCP integration boundary, deterministic mock connectors, canonical SQLite staging, and code-enforced safety gates.

Current status: `PASS_WITH_LIMITATIONS`. Local/MCP/mock flows work; the live Buzz round trip is blocked by missing Hermes provider auth and a dedicated Buzz identity/channel membership.

## Quick check

```powershell
cd C:\Users\Admin\marketing-ai-system
.\scripts\status-all.ps1
.\scripts\smoke-test.ps1
```

See `RUNBOOK.md` for provider/Buzz onboarding and daily start/stop commands. See `ACCOUNTS_REQUIRED.md` for external service setup.

