# Integration Matrix

Snapshot: 2026-09-19. `CONNECTED` is used only after a successful live probe. No external connector has been live-tested in this phase.

| SERVICE | PURPOSE | SOFTWARE_READY? | CONNECTOR_READY? | AUTH_READY? | LIVE_TESTED? | CURRENT_MODE | BLOCKER | NEXT_STEP |
|---|---|---|---|---|---|---|---|---|
| Buzz Desktop | Human chat surface | INSTALLED 0.5.23 | Hermes native plugin present | Dedicated bot identity + NIP-OA configured | Yes | LIVE_VERIFIED | Desktop GUI was not automated; relay/CLI events verified | Open `Welcome` and chat normally |
| Hermes | Orchestrator/runtime | INSTALLED 0.21.3 | Profile `marketing` configured | OpenAI Codex OAuth | Yes | CONNECTED | — | Keep profile isolated |
| Hermes ↔ Buzz | Primary transport | Software present | Native gateway configured | Owner allowlist + bot channel role verified | Yes | CONNECTED + LIVE_VERIFIED | — | Monitor with `doctor.ps1` |
| Marketing MCP | Routing/tool boundary | INSTALLED in project `.venv` | 5 tools enabled in profile | Not required | Yes, local stdio | CONNECTED_LOCAL | — | Keep local and pinned |
| SQLite staging | Canonical mock/staging store | Python stdlib | Ready | Not required | Yes | MOCK_READY | — | Use production namespace only after live source verification |
| Zoho CRM | Leads, contacts, accounts, deals, tasks | REST client ready | OAuth refresh + org probe + mock adapter | No | No | MOCK_READY + NEEDS_AUTH | CRM account/app/tokens missing | Create Zoho app, grant least privilege, run connector probe |
| Microsoft 365 | Mail drafts/metadata, calendar, files | REST client ready | Graph token probe + mock adapter | No | No | MOCK_READY + NEEDS_AUTH | Tenant/app/OAuth missing | Register Entra app, consent delegated scopes, run probe |
| Apollo | People/company search and enrichment | REST client ready | No-credit auth probe + cost metadata + mocks | No | No | MOCK_READY + NEEDS_AUTH | Account/API key missing | Add API key; probe uses `/auth/health` only |
| LinkedIn | Page/account read and post drafts | REST client ready | OAuth/access-state adapter + mocks | No | No | MOCK_READY + NEEDS_ACCESS | App, OAuth, and product approval missing | Create app and request required product access |
| YouTube | Channel/video metadata and future analytics | REST client ready | API-key read probe + mocks | No | No | MOCK_READY + NEEDS_AUTH | Google project/API key/OAuth missing | Enable Data API; add key; OAuth later for private/write |
| Meta Ads | Campaign abstractions and metrics | REST client ready | Read-only account probe + mocks | No | No | MOCK_READY + NEEDS_AUTH | Meta app/token/ad account missing | Start with `ads_read`; do not grant/execute writes yet |
| Google Ads | Metrics and campaign drafts | REST client ready | OAuth refresh + accessible-customer probe + mocks | No | No | MOCK_READY + NEEDS_AUTH | Developer token, OAuth, customer ID missing | Configure test/read access and run probe |
| Website | Public metadata, form/webhook interface | REST client ready | URL probe + mock page/form data | No config | No | MOCK_READY + CONFIG_REQUIRED | Website URL/CMS unknown | Set `WEBSITE_URL`; choose CMS adapter later if needed |

## Capability truth table

- `MOCK_READY`: deterministic synthetic data works locally.
- `NEEDS_AUTH`: code exists but credentials/consent are missing.
- `NEEDS_ACCESS`: credentials alone may be insufficient because product/API approval is required.
- `CONFIG_REQUIRED`: non-secret endpoint information is missing.
- `CONNECTED_LOCAL`: local MCP transport has been exercised successfully; it says nothing about external APIs.
- `LIVE_TESTED`: remains `No` until a provider-specific non-destructive probe succeeds.
