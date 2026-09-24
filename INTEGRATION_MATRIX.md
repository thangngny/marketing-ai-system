# Integration Matrix

Snapshot: 2026-09-24 (per-capability view: CAPABILITY_MATRIX.md). `CONNECTED` is used only after a successful live probe.

| SERVICE | PURPOSE | SOFTWARE_READY? | CONNECTOR_READY? | AUTH_READY? | LIVE_TESTED? | CURRENT_MODE | BLOCKER | NEXT_STEP |
|---|---|---|---|---|---|---|---|---|
| Buzz Desktop | Human chat surface | INSTALLED 0.5.23 | Hermes native plugin present | Dedicated bot identity + NIP-OA configured | Yes | LIVE_VERIFIED | Desktop GUI was not automated; relay/CLI events verified | Open `Welcome` and chat normally |
| Hermes | Orchestrator/runtime | INSTALLED 0.21.3 | Profile `marketing` configured | OpenAI Codex OAuth | Yes | CONNECTED | — | Keep profile isolated |
| Hermes ↔ Buzz | Primary transport | Software present | Native gateway configured | Owner allowlist + bot channel role verified | Yes | CONNECTED + LIVE_VERIFIED | — | Monitor with `doctor.ps1` |
| Marketing MCP | Routing/tool boundary | INSTALLED in project `.venv` | 6 tools enabled in profile | Not required | Yes, local stdio | CONNECTED_LOCAL | — | Keep local and pinned |
| SQLite staging | Canonical mock/staging store | Python stdlib | Ready | Not required | Yes | MOCK_READY | — | Use production namespace only after live source verification |
| Zoho CRM | Leads, contacts, accounts, deals, tasks (System of Record) | REST + hosted-MCP + Claude-delegate transports | Read + normalization; data taken from raw tool_result only | Owner's Claude Code Zoho session (expires ~1 h, re-auth via /mcp) | Yes 2026-09-24: Leads 0, Accounts 0 (sharing private: user sees only own records) | LIVE_READ / AUTHENTICATING | Session lifetime; a second OAuth client invalidated the first | Durable: Zoho API Console Self Client (owner MFA once) → refresh token, no hourly re-auth |
| Microsoft 365 | Mail metadata, calendar, files | REST client ready | PKCE callback, refresh, Graph probe, mail metadata normalization | Outlook/OneDrive session confirmed | No | MOCK_READY + NEEDS_AUTH | Entra portal requires Authenticator code; app registration not created | Complete MFA; register public client with delegated read scopes; run OAuth and probe |
| Apollo | People/company search and enrichment | REST client ready | No-credit auth probe + cost metadata + mocks | Account evidence exists; current Apollo session logged out | No | MOCK_READY + NEEDS_AUTH | Login and scoped API key creation required | Sign in, create scoped key, store in Credential Manager, call `/auth/health` only |
| LinkedIn | Page/account read and post drafts | REST client ready | OAuth/access-state adapter + mocks | App "Buzz Marketing Hub" created 2026-09-24 (App ID 263861372), Client ID 86vk0dkiykfjsz, bound to Page Minh Van Logistics | No | MOCK_READY + NEEDS_ADMIN_APPROVAL | Company verification link sent to a Page Admin, pending their approval (URL valid until 2026-10-24); Community Management API request stays locked until then | Page Admin opens the verification URL and approves; then request Community Management API access, then implement OAuth code exchange |
| YouTube | Channel/video metadata and future analytics | REST client ready | Header-based API-key probe + `recent_videos` live read (search.list, normalized to ChannelPost) | Restricted API key + `YOUTUBE_CHANNEL_ID` stored (channel: Minh Van Logistics, `UCmKIv0NyPUUcE5ZFiaKz_9g`) | Yes | LIVE_VERIFIED — `marketing_sync_readonly(youtube, recent_videos)` returned `LIVE_VERIFIED_READ`, staged 3 real records | — | Keep read-only; revisit for analytics/upload only if a write workflow is approved |
| Meta Ads | Campaign abstractions and metrics | REST client ready | Header-based read-only account probe + mocks | Meta Business session not authenticated | No | MOCK_READY + NEEDS_AUTH | Facebook/Business login, app, token, and ad account access missing | Owner signs in; then start with `ads_read` and no write scopes |
| Google Ads | Metrics and campaign drafts | REST client ready | OAuth refresh + accessible-customer probe + mocks | Live Ads account/session confirmed (150-914-5225); customer ID stored securely | No | MOCK_READY + NEEDS_ADMIN_APPROVAL | Account is a standard Ads account, not a Manager (MCC); API Center refuses developer-token applications from non-manager accounts | Owner decides whether to create a Google Ads Manager account and link the existing account to it, then apply for a developer token |
| Website | Public metadata, form/webhook interface | REST client ready | URL probe + canonical metadata normalization | URL stored in Windows Credential Manager | Yes | CONNECTED + LIVE_VERIFIED | CMS type/write API intentionally not configured | Keep read-only; choose CMS adapter only when a write workflow is approved |

## Capability truth table

- `MOCK_READY`: deterministic synthetic data works locally.
- `NEEDS_AUTH`: code exists but credentials/consent are missing.
- `NEEDS_ACCESS`: credentials alone may be insufficient because product/API approval is required.
- `CONFIG_REQUIRED`: non-secret endpoint information is missing.
- `CONNECTED_LOCAL`: local MCP transport has been exercised successfully; it says nothing about external APIs.
- `LIVE_TESTED`: remains `No` until a provider-specific non-destructive probe succeeds.
