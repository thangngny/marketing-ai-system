# Capability Matrix

Source of truth at runtime: `uv run marketing-system doctor` (or MCP `system_connector_status`). A capability is `LIVE_*` only with evidence — a successful non-mock call in the tool ledger or a live probe. Snapshot 2026-09-24, environment `production`, `SAFE_DRY_RUN=true`.

| Connector | AUTH | READ | ANALYTICS | DRAFT | PUBLISH | Evidence / blocker |
|---|---|---|---|---|---|---|
| Zoho CRM | see INTEGRATION_MATRIX | | | NOT_CONFIGURED (local task proposals only) | NOT_CONFIGURED | Transport: official hosted MCP (`oauth zoho-mcp`) or own OAuth client (API Console, owner MFA) |
| Apollo | NOT_CONFIGURED | NOT_CONFIGURED | – | – | – | Owner creates a scoped API key |
| Microsoft 365 | NEEDS_MFA | NEEDS_MFA | – | NEEDS_MFA (Outlook draft code lands M10) | – | Entra app registration needs Authenticator |
| Website | LIVE_READ | LIVE_READ | LIVE_READ | NOT_CONFIGURED | NOT_CONFIGURED | WordPress REST detected; 441 posts; ledger 2026-09-24 |
| YouTube | LIVE_READ | LIVE_READ | LIVE_READ | NOT_CONFIGURED | NEEDS_API_ACCESS | Channel "Minh Van Logistics": 2 subs, 3 videos, 214 views |
| LinkedIn | NEEDS_API_ACCESS | NEEDS_API_ACCESS | NEEDS_API_ACCESS | NEEDS_API_ACCESS | NEEDS_API_ACCESS | Developer app + Page association + product review |
| TikTok | NOT_CONFIGURED | – | – | – | – | No connector code yet (roadmap 8) |
| Zalo OA | NOT_CONFIGURED | – | – | – | – | No connector code yet (roadmap 7) |
| Meta Ads | NOT_CONFIGURED | NOT_CONFIGURED | NOT_CONFIGURED | – | NEEDS_API_ACCESS | Business login, app, `ads_read` token |
| Google Ads | NEEDS_API_ACCESS | NEEDS_API_ACCESS | NEEDS_API_ACCESS | – | NEEDS_API_ACCESS | Developer token (Google review) + OAuth client |

Write capabilities are never reported `LIVE_WRITE` in this phase; HIGH_IMPACT tools are phase-gated in `policy.py`.
