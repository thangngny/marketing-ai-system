# Security Policy

## Default posture

- Environment: `mock`.
- Execution mode: `SAFE_DRY_RUN`.
- Buzz access: owner-only allowlist, mention required.
- External writes: disabled.
- Paid campaign changes: disabled even after approval capture in Phase 1.
- Shared telemetry: disabled in the inherited Hermes configuration.

## Tool impact classes

| Class | Default behavior | Examples |
|---|---|---|
| READ | May run when access exists | status, CRM read, metrics query |
| DRAFT | May create local/internal drafts | post draft, campaign plan, staged lead |
| WRITE | Requires explicit human approval and non-mock mode | approved CRM create/update |
| HIGH_IMPACT | Always approval-gated; disabled in Phase 1 | send email/outreach, publish, launch ads, change budget, delete CRM data, change permissions |

The code-level `authorize()` gate is authoritative. A prompt asking to bypass it does not change the result.

## Secret storage

- Project credential file: `.env.local`, ignored by Git.
- Hermes/Buzz identity: isolated profile `.env` at `%LOCALAPPDATA%\hermes\profiles\marketing\.env`.
- Never place secrets in source, docs, fixtures, screenshots, logs, command-line arguments, or Buzz messages.
- Structured logging recursively redacts secret/token/password/private-key/authorization/cookie fields.
- Use a dedicated agent Nostr key; never reuse the human owner's key.

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

