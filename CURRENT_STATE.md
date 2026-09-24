# Current State — audit 2026-09-24

Everything below was re-verified on the host on 2026-09-24. Earlier notes and memory were not trusted.
Baseline tag: `pre-runtime-agnostic-architecture` (commit `8f2a78b`).

## WHAT EXISTS

| Component | Location | Verified fact |
|---|---|---|
| Buzz Desktop 0.5.23 | `D:\Buzz` | Running. Relay `phamgianam.communities.buzz.xyz`. `buzz.exe` CLI present; every read needs a Nostr private key. |
| Buzz ACP agents | `%APPDATA%\xyz.block.buzz.app\agents\managed-agents.json` | Codex, Claude, Antigravity: `respond_to=anyone`, autostart, 21–22 channels, relay reconnects 3/3 OK in last 24h. Fizz/Honey/Pollen: autostart off. |
| Hermes Agent 0.21.3 | `%LOCALAPPDATA%\hermes\hermes-agent` | Default profile has **no provider** (`hermes -z` fails). Profile **`marketing`** works: `openai-codex` OAuth, model `gpt-5.6-sol`, one-shot reply in 26 s. |
| Hermes ↔ Buzz gateway | profile `marketing` | Native Buzz platform, dedicated bot identity, listens on channel `Welcome` (`6fdc7c8d…`) only, owner-only allowlist, `require_mention: true`. **Was not running at audit time** (last state write 2026-09-23 15:01). Restarted with `scripts/start-all.ps1`; reports `buzz=connected`. |
| Marketing system (this repo) | `C:\Users\Admin\marketing-ai-system` | Python 3.11 / uv / `.venv`. Branch `marketing-system-phase1`. Git clean. |
| MCP server | `src/marketing_system/mcp_server.py` | 6 tools, stdio, registered in Hermes `marketing` profile as `marketing-system`. |
| Connectors (Python) | `src/marketing_system/connectors/` | zoho, m365, apollo, linkedin, youtube, meta_ads, google_ads, website. |
| Storage | `data/marketing.db` | SQLite `canonical_records` staging table only. |
| Logs | `logs/marketing.jsonl` | Structured events with `correlation_id`, redaction. No spans, no latency per connector. |
| Credentials | Windows Credential Manager `BuzzMarketing/*` | Entry names present: `GOOGLE_ADS_CUSTOMER_ID`, `YOUTUBE_API_KEY`, `YOUTUBE_CHANNEL_ID`, `WEBSITE_URL`. No Zoho/Apollo/M365/LinkedIn/Meta entries. Values not read. |
| Zoho hosted MCP | `mcp.zoho.com`, registered to Claude Code (user scope) only | 23 read-only CRM tools. `getRecordCount(Leads)` → `success, count 0` today. Profile "Sales – Standard": several modules `NO_PERMISSION`. Not reachable from this repo's hub. |
| Node connector scripts | `C:\Users\Admin\buzz-marketing\connectors` | youtube.js, website.js, zoho.js, doctor.js. Referenced by `buzz-marketing/AGENTS.md` for the ACP agents. |
| Microsoft session | Credential Manager | Only a OneDrive **browser cookie** for `minhvanlogistics-my.sharepoint.com`. Not a Graph OAuth app. |

## WHAT IS WORKING

- Hermes `marketing` provider (live model call).
- Hermes Buzz gateway after restart (`connected`).
- Website read (HTTP 200, WordPress site) and YouTube `recent_videos` read — both previously LIVE_VERIFIED.
- Test suite: **40 PASS / 8 SKIPPED (live, opt-in) / 0 FAIL** after the hermetic-test fix (commit `e552a26`).
- Claude Code → Zoho hosted MCP read (outside this repo).

## WHAT IS MOCK

- Every "specialist" answer in `orchestrator.py` is a **hard-coded Vietnamese template** (LinkedIn post, campaign plan). No specialist actually runs.
- Lead search returns synthetic `mock_logistics_leads`.
- All connectors except website/youtube run on deterministic mock data.

## WHAT IS MISSING

- `AgentRuntime` abstraction — Hermes is reached only through its own gateway; nothing in the repo can swap runtimes.
- Specialist registry with per-specialist tool permissions / impact ceiling.
- Durable workflow engine and persisted approval records.
- Per-tool policy declaration (impact is inferred from action-name prefixes).
- Namespaced tool hub (`crm.*`, `prospecting.*`, …) with typed specs.
- Idempotency keys for draft/write operations.
- Trace spans (gateway → runtime → specialist → tool → connector) with latency.
- Zoho live path through the hub (API Console / Self Client still owner-MFA blocked).

## DEFECTS FOUND

| Severity | Defect |
|---|---|
| **P0 security** | `marketing_request_execution(action, explicit_approval=True)` lets the LLM assert its own approval. Approval is not bound to a human, a payload, or an expiry. |
| P1 | `doctor` reports `Hermes - Buzz: OK - gateway live` from a stale `gateway_state.json` even when `gateway status` says *No gateway process detected*. |
| P1 | Tests were not hermetic (fixed in `e552a26`). |
| P2 | Two connector stacks for the same services (Python here, Node in `buzz-marketing/connectors`). |

## WHAT IS OBSOLETE

- `buzz-marketing/connectors/*.js` duplicates this repo's Python connectors; keep read-only until the ACP agents are pointed at the hub, then retire.
- Memory claims that Hermes config lives at `~/.hermes` or uses `gpt-5.5-codex` — actual: `%LOCALAPPDATA%\hermes\profiles\marketing`, `gpt-5.6-sol`.
- `ConnectorState.CONNECTED` as a single word for a service (replace with per-capability states).

## WHAT SHOULD BE PRESERVED

- Hermes `marketing` profile, its Buzz identity, allowlist and autostart login item.
- Canonical pydantic models, environment isolation (`mock` records can never enter `production`), secret redaction.
- Windows Credential Manager secret store (`credentials.py`), OAuth PKCE helpers (`oauth.py`).
- Existing MCP tool names used by the Hermes skill (`marketing_handle_request`, `marketing_system_status`, `marketing_sync_readonly`).
- Scripts `start-all / stop-all / status-all / doctor / smoke-test` (idempotent start already proven).
