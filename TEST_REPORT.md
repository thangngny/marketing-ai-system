# Test Report — architecture hardening, 2026-09-24

Earlier reports (Phase 1/2, 2026-09-19/22) are in git history (`git show pre-runtime-agnostic-architecture:TEST_REPORT.md`).

## Baseline

`pre-runtime-agnostic-architecture`: 38 pass / **2 FAIL** / 8 skipped. Both failures were non-hermetic tests (real `.env.local` + real Credential Manager; one unit test called the live YouTube API with a fake key). Fixed in `e552a26` → 40 pass / 0 fail.

## Automated suite (`scripts\test.ps1`)

**119 PASS · 9 SKIPPED (opt-in live) · 0 FAIL.** Tests write only to a temp directory.

| Layer | File | Result |
|---|---|---|
| Runtime adapter contract (Mock/Hermes/Claude/Codex × input, specialist, JSON, correlation, fail-safe, timeout, empty, sessions, health) | `test_runtime_contract.py` | PASS (35) |
| Specialists, routing, permission ceilings | `test_specialists.py`, `test_routing.py` | PASS |
| Policy (READ/DRAFT/WRITE/HIGH, ceilings, SAFE_DRY_RUN, payload change) | `test_policy_approval.py` | PASS |
| Approval (owner-signature only, agent-posted code ignored, reject, stale message, wrong code, expiry, single-use) | `test_policy_approval.py` | PASS |
| Workflow (North Star mock E2E, restart recovery, crash mid-step without duplicates, rejection, runtime failure → BLOCKED, production w/o creds → exact state, write → approval workflow) | `test_workflows.py` | PASS |
| Tool hub (invalid input, unknown tool, DENY, spans + ledger) | `test_workflows.py` | PASS |
| MCP contract (namespaced/typed/annotated tools, **no tool accepts an approval flag**, write → WAITING workflow) | `test_mcp_server.py` | PASS |
| Zoho transport (vault chunking, REST→MCP→none selection, canonical normalization) | `test_zoho_transport.py` | PASS |
| Connectors, storage, security/redaction, skills, legacy safety | existing files | PASS |

## Live checks

| Check | Result | Evidence |
|---|---|---|
| HermesRuntime round trip (`hermes -p marketing -z`) | PASS | `test_live_hermes_marketing_profile_round_trip` |
| Hermes gateway restart + double start | PASS | stop → start → "already running"; `buzz=connected` |
| Path A via Hermes: "Hôm nay hệ thống thế nào?" → MCP → hub | PASS_LIVE_READ | correlation `c0d97074-43cd-4e34-bebc-243796f8d46b`, 50 s |
| Same request via Claude runtime, same hub, no code change | PASS_LIVE_READ | correlation `1585cc4e-0a64-42d5-a3e9-1ad18d03dbb0`, 15 s |
| `social.get_channel_metrics` / `get_recent_videos` | PASS_LIVE_READ | Minh Van Logistics: 2 subs, 3 videos, 214 views |
| `website.get_metadata` / `get_recent_content` | PASS_LIVE_READ | WordPress REST, 441 posts |
| `analytics.snapshot` | PASS_LIVE_READ | 4 FACT metrics; `crm_leads` listed unavailable, not guessed |
| `crm.search_leads` | PASS_LIVE_READ, later NEEDS_AUTH | Via Claude Code delegate: Leads 0 / Accounts 0; ~1 h later the Claude Zoho session expired and the hub reported NEEDS_AUTH (correct) |
| `prospecting.search_companies` | NOT_CONFIGURED | Apollo key |
| `email.get_unread_count` | NEEDS_MFA | Entra |
| `ads.get_campaign_performance` | NOT_CONFIGURED | Meta |
| North Star in production | PARTIAL → WAITING_APPROVAL | `wf-e974988ea873`: Apollo LIVE → Zoho LIVE dedupe → code scoring → 3 drafts by Hermes (language-only) → owner gate `MV-1CF5A5`. Outlook draft step will block on M365 (NEEDS_MFA). Earlier run exposed a recursion bug (see commit af934fe); ≈6 Apollo credits used in total, 0 external writes |

## Buzz E2E

| Item | Result |
|---|---|
| BUZZ_TRANSPORT (gateway connected to relay) | PASS |
| Owner message → Hermes → hub → reply in Buzz | NEEDS_HUMAN: the gateway answers only the owner's signed messages; no owner key is available to the implementer by design |
| Buzz-signed approval verifier | NEEDS_AUTH: `BUZZ_APPROVAL_READER_KEY` not provisioned (logic PASS in tests) |

## External side effects

Emails sent 0 · posts 0 · ad changes 0 · money 0 · CRM writes 0. One Zoho OAuth client was registered (read-only scopes requested by Zoho's MCP server).
