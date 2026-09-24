# Security Policy

## Default posture

- Environment: `mock`.
- Execution mode: `SAFE_DRY_RUN`.
- Buzz access: owner-only allowlist, mention required.
- External writes: disabled.
- Paid campaign changes: disabled even after approval capture in Phase 1.
- Shared telemetry: disabled in the inherited Hermes configuration.

## Tool impact classes

Every tool declares its impact in `tools/catalog.py`. `policy.PolicyEngine` decides in code; no prompt changes the result.

| Class | Decision | Examples |
|---|---|---|
| READ | ALLOW (if the specialist may use the namespace) | `crm_search_leads`, `social_get_channel_metrics`, `analytics_snapshot` |
| DRAFT | ALLOW; idempotent | `email_create_draft`, `crm_propose_task`, `content_save_draft` |
| WRITE_LOW_RISK | REQUIRE_APPROVAL; then SAFE_DRY_RUN still blocks outside mock | `crm_create_task` |
| HIGH_IMPACT | REQUIRE_APPROVAL, single-use, and DENY unless the tool is explicitly enabled (none are) | `email_send`, `social_publish_post`, `ads_launch_campaign`, `ads_change_budget`, `crm_delete_record` |

Specialist ceilings: no specialist may request HIGH_IMPACT; `08_kpi_learning` and `02_market_intelligence` are READ-only.

## Approval boundary

- No MCP tool accepts an approval flag (tested: `test_no_mcp_tool_can_assert_approval`). The old `explicit_approval` argument was removed from the MCP surface.
- An approval moves to APPROVED only through a verifier: an owner-**signed** Buzz message `DUYET <code>` (`BuzzSignedEventVerifier`), or `marketing-system approvals approve` at an interactive terminal.
- Approvals bind tool + SHA-256 of the canonical payload + expiry; a changed payload requires a fresh approval.
- The Buzz verifier reads the channel with a dedicated reader identity key (`BuzzMarketing/BUZZ_APPROVAL_READER_KEY`). Hermes' own bot key is sealed by Hermes and is deliberately not reused.
## Secret storage

- Business-service secrets: Windows Credential Manager under the `BuzzMarketing/` namespace.
- `.env.local`, when used, is limited to non-secret local configuration and remains ignored by Git.
- Hermes/Buzz identity: isolated profile `.env` at `%LOCALAPPDATA%\hermes\profiles\marketing\.env`.
- Never place secrets in source, docs, fixtures, screenshots, logs, command-line arguments, or Buzz messages.
- Structured logging recursively redacts secret/token/password/private-key/authorization/cookie fields.
- Use a dedicated agent Nostr key; never reuse the human owner's key.
- `marketing-system credentials set NAME` reads the value through a hidden prompt; the value is never an argument or printed output.
- Values larger than one Credential Manager blob (2,560 bytes) are split into `NAME_0..n` entries (Zoho MCP OAuth client/tokens).
- Zoho hosted-MCP endpoint, OAuth client and tokens: `BuzzMarketing/ZOHO_MCP_URL`, `ZOHO_MCP_CLIENT*`, `ZOHO_MCP_TOKENS*`.

## Data separation

- Every canonical record has `environment` and `synthetic` fields.
- Synthetic data is accepted only in `mock`.
- The SQLite store rejects the same record id crossing environments.
- Mock domains use `.example.invalid` and names are visibly labeled `MOCK`.
- Zoho is not called the source of truth until live auth and mapping tests pass.

## Connector safety

- Health checks never call Apollo enrichment.
- YouTube live health consumes minimal read quota and runs only with `--live`.
- Meta/Google Ads health checks are read-only.
- Retries are bounded to three attempts for 429/5xx with a maximum one-second delay per retry.
- No connector logs response bodies containing potential credentials.

## Buzz gateway

- `allowed_users` must contain the owner's npub/hex key.
- `allow_all_users=false` and `require_mention=true`.
- Intermediate assistant/tool-progress messages are suppressed for the Buzz platform.
- Do not enable autostart until the Buzz round trip and restart acceptance tests pass.

## Incident response

1. Run `scripts\stop-all.ps1`.
2. Revoke affected provider tokens and the dedicated Buzz agent key.
3. Inspect `%LOCALAPPDATA%\hermes\profiles\marketing\logs` and project `logs\marketing.jsonl` for correlation ids; do not paste raw logs into public channels.
4. Restore Hermes from snapshot `20260919-104853-pre-marketing-system` if profile changes must be rolled back.
