# Integration Matrix

Snapshot: 2026-09-24 (per-capability view: CAPABILITY_MATRIX.md). `CONNECTED` is used only after a successful live probe.

| SERVICE | PURPOSE | SOFTWARE_READY? | CONNECTOR_READY? | AUTH_READY? | LIVE_TESTED? | CURRENT_MODE | BLOCKER | NEXT_STEP |
|---|---|---|---|---|---|---|---|---|
| Buzz Desktop | Human chat surface | INSTALLED 0.5.23 | Hermes native plugin present | Dedicated bot identity + NIP-OA configured | Yes | LIVE_VERIFIED | Desktop GUI was not automated; relay/CLI events verified | Open `Welcome` and chat normally |
| Hermes | Orchestrator/runtime | INSTALLED 0.21.3 | Profile `marketing` configured | OpenAI Codex OAuth | Yes | CONNECTED | — | Keep profile isolated |
| Hermes ↔ Buzz | Primary transport | Software present | Native gateway configured | Owner allowlist + bot channel role verified | Yes | CONNECTED + LIVE_VERIFIED | — | Monitor with `doctor.ps1` |
| Marketing MCP | Routing/tool boundary | INSTALLED in project `.venv` | 6 tools enabled in profile | Not required | Yes, local stdio | CONNECTED_LOCAL | — | Keep local and pinned |
| SQLite staging | Canonical mock/staging store | Python stdlib | Ready | Not required | Yes | MOCK_READY | — | Use production namespace only after live source verification |
| Zoho CRM | Leads, contacts, accounts, deals, tasks (System of Record) | REST client + hosted-MCP transport | Read + normalization via `ZohoCRM_getRecords`; REST path still available | Hosted-MCP OAuth client registered 2026-09-24; **owner consent pending** | Via Claude Code: count Leads = 0 (success) | AUTHENTICATING | Owner clicks Accept once (`marketing-system oauth zoho-mcp`) | Then `live_read_check.py` → LIVE_READ |
| Microsoft 365 | Mail metadata, calendar, files | REST client ready | PKCE callback, refresh, Graph probe, mail metadata normalization | Outlook/OneDrive session confirmed | No | MOCK_READY + NEEDS_AUTH | Entra portal requires Authenticator code; app registration not created | Complete MFA; register public client with delegated read scopes; run OAuth and probe |
| Apollo | People/company search and enrichment | REST client ready | No-credit auth probe + cost metadata + mocks | Account evidence exists; current Apollo session logged out | No | MOCK_READY + NEEDS_AUTH | Login and scoped API key creation required | Sign in, create scoped key, store in Credential Manager, call `/auth/health` only |
| LinkedIn | Page/account read and post drafts | REST client ready | OAuth/access-state adapter + mocks | Member + developer portal session confirmed | No | MOCK_READY + NEEDS_ACCESS | No developer app; company Page was not offered for association; legal acceptance is owner-only | Verify Page admin/association, accept terms, then create app and request minimal product access |
| YouTube | Channel/video metadata and future analytics | REST client ready | Header-based API-key probe + `recent_videos` live read (search.list, normalized to ChannelPost) | Restricted API key + `YOUTUBE_CHANNEL_ID` stored (channel: Minh Van Logistics, `UCmKIv0NyPUUcE5ZFiaKz_9g`) | Yes | LIVE_VERIFIED — `marketing_sync_readonly(youtube, recent_videos)` returned `LIVE_VERIFIED_READ`, staged 3 real records | — | Keep read-only; revisit for analytics/upload only if a write workflow is approved |
| Meta Ads | Campaign abstractions and metrics | REST client ready | Header-based read-only account probe + mocks | Meta Business session not authenticated | No | MOCK_READY + NEEDS_AUTH | Facebook/Business login, app, token, and ad account access missing | Owner signs in; then start with `ads_read` and no write scopes |
| Google Ads | Metrics and campaign drafts | REST client ready | OAuth refresh + accessible-customer probe + mocks | Live Ads account/session confirmed; customer ID stored securely | No | MOCK_READY + NEEDS_AUTH | Developer token and OAuth client/refresh token missing | Create read-only API credentials after owner confirmation, then run accessible-customer probe |
| Website | Public metadata, form/webhook interface | REST client ready | URL probe + canonical metadata normalization | URL stored in Windows Credential Manager | Yes | CONNECTED + LIVE_VERIFIED | CMS type/write API intentionally not configured | Keep read-only; choose CMS adapter only when a write workflow is approved |

## Capability truth table

- `MOCK_READY`: deterministic synthetic data works locally.
- `NEEDS_AUTH`: code exists but credentials/consent are missing.
- `NEEDS_ACCESS`: credentials alone may be insufficient because product/API approval is required.
- `CONFIG_REQUIRED`: non-secret endpoint information is missing.
- `CONNECTED_LOCAL`: local MCP transport has been exercised successfully; it says nothing about external APIs.
- `LIVE_TESTED`: remains `No` until a provider-specific non-destructive probe succeeds.
