# Capability Matrix

Source of truth at runtime: `uv run marketing-system doctor` (or MCP `system_connector_status`). A capability is `LIVE_*` only with evidence — a successful non-mock call in the tool ledger or a live probe. Snapshot 2026-09-24, environment `production`, `SAFE_DRY_RUN=true`.

| Connector | AUTH | READ | ANALYTICS | DRAFT | PUBLISH | Evidence / blocker |
|---|---|---|---|---|---|---|
| Zoho CRM | LIVE_READ | LIVE_READ (Leads/Accounts/Contacts/Deals/Tasks = 0 visible — org sharing is **private**) | NOT_CONFIGURED | NOT_CONFIGURED (local task proposals only) | NOT_CONFIGURED | Own OAuth client "Buzz Marketing Hub" (REST, refresh token in vault, read-only scopes) since 2026-09-24; no hourly re-auth |
| Apollo | LIVE_READ | LIVE_READ (mixed_companies/search, 1 credit/page) | – | – | – | Key "Buzz Marketing Hub" scoped to 3 search endpoints; auth/health 200; no enrichment |
| Microsoft 365 | NEEDS_MFA | NEEDS_MFA | – | NEEDS_MFA (Outlook draft code lands M10) | – | Entra app registration needs Authenticator |
| Website | LIVE_READ | LIVE_READ | LIVE_READ | NOT_CONFIGURED | NOT_CONFIGURED | WordPress REST detected; 441 posts; ledger 2026-09-24 |
| YouTube | LIVE_READ | LIVE_READ | LIVE_READ | NOT_CONFIGURED | NEEDS_API_ACCESS | Channel "Minh Van Logistics": 2 subs, 3 videos, 214 views |
| LinkedIn | NEEDS_ADMIN_APPROVAL | NEEDS_ADMIN_APPROVAL | NEEDS_ADMIN_APPROVAL | NEEDS_ADMIN_APPROVAL | NEEDS_ADMIN_APPROVAL | App "Buzz Marketing Hub" created (App ID 263861372), bound to Page Minh Van Logistics; Community Management API request blocked until a Page Admin approves the app-Page verification link (30-day URL generated 2026-09-24) |
| TikTok | NOT_CONFIGURED | – | – | – | – | No connector code yet (roadmap 8) |
| Zalo OA | NOT_CONFIGURED | – | – | – | – | No connector code yet (roadmap 7) |
| Meta Ads | NOT_CONFIGURED | NOT_CONFIGURED | NOT_CONFIGURED | – | NEEDS_API_ACCESS | Business login, app, `ads_read` token |
| Google Ads | NEEDS_ADMIN_APPROVAL | NEEDS_ADMIN_APPROVAL | NEEDS_ADMIN_APPROVAL | – | NEEDS_ADMIN_APPROVAL | Account 150-914-5225 is a standard Ads account, not a Manager (MCC); API Center refuses non-manager accounts. Needs a new Google Ads Manager account (owner decision — account creation) linked to the existing account, then a developer token application |

Write capabilities are never reported `LIVE_WRITE` in this phase; HIGH_IMPACT tools are phase-gated in `policy.py`.
