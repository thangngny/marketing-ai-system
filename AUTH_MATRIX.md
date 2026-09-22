# Auth Matrix

Snapshot: 2026-09-22. No usernames/passwords/tokens are recorded here — values are
stored only in Windows Credential Manager (`BuzzMarketing/<NAME>`), read via
`uv run marketing-system credentials status`.

| SERVICE | ACCOUNT_DISCOVERED | AUTH_METHOD | AUTH_STATUS | API_ACCESS | READ | DRAFT | WRITE | REFRESH | BLOCKER |
|---|---|---|---|---|---|---|---|---|---|
| Zoho CRM | Yes (Google SSO) | OAuth 2.0 (PKCE, server-based client) | NOT_STARTED | Requires Client ID/Secret from api-console.zoho.com | No | N/A | Disabled | N/A | Owner paused mid-setup; resume with `oauth zoho` once Client ID/Secret stored |
| Apollo | Session logged out | API key (scoped, no-credit health probe) | NOT_STARTED | Requires re-login + scoped key creation | No | N/A | Disabled | N/A | Owner has not re-authenticated |
| Microsoft 365 / Outlook / OneDrive | Yes (existing browser session) | OAuth 2.0 (PKCE, public client, loopback `http://localhost`) | NOT_STARTED | Requires Entra app registration (delegated read scopes) | No | No | Disabled | N/A | Entra app registration not created; MFA/Authenticator required |
| LinkedIn | Yes (member + developer portal) | OAuth 2.0 | API_ACCESS_REQUIRED | No developer app; Page association pending | No | No | Disabled | N/A | Legal/product-access acceptance is owner-only |
| YouTube | Yes (Google account) | API key (restricted) + OAuth for future write | CONNECTED_LIVE_VERIFIED | Restricted API key + `YOUTUBE_CHANNEL_ID` stored (project `mythic-emissary-450814-n8`, channel `UCmKIv0NyPUUcE5ZFiaKz_9g`) | Yes — `recent_videos` returns real channel data via `marketing_sync_readonly` | N/A | Disabled | N/A (API key, no refresh) | None |
| Google Ads | Yes; `GOOGLE_ADS_CUSTOMER_ID` stored | OAuth 2.0 + developer token | NOT_STARTED | Developer token not issued | No | N/A | Disabled | N/A | Developer token application not submitted |
| Meta / Facebook | Business session not authenticated | OAuth 2.0 (Business Manager, system user) | NOT_STARTED | No app / no ad account access confirmed | No | N/A | Disabled | N/A | Owner login + Business Manager app not created |
| TikTok | Not yet assessed | TikTok for Business API (expected) | NOT_STARTED | Unknown | No | N/A | Disabled | N/A | Not yet researched this phase |
| Zalo OA | Not yet assessed | Zalo OpenAPI (expected) | NOT_STARTED | Unknown | No | N/A | Disabled | N/A | Not yet researched this phase |
| Website | Yes (public) | None required (public read) | CONNECTED_READ_ONLY | Public metadata endpoint only | Yes | N/A | Disabled | N/A | None — CMS write API intentionally not configured |
| Microsoft Copilot | N/A | N/A | NOT_REQUIRED_FOR_CURRENT_ARCHITECTURE | N/A | N/A | N/A | N/A | N/A | Hermes is the primary orchestrator; no distinct API role identified |

## States used

`NOT_STARTED` / `AUTH_DISCOVERY` / `AUTHENTICATING` / `MFA_REQUIRED` / `CAPTCHA_REQUIRED` /
`ADMIN_APPROVAL_REQUIRED` / `API_ACCESS_REQUIRED` / `CONNECTED_READ_ONLY` / `CONNECTED_DRAFT` /
`CONNECTED_WRITE` / `CONNECTED_LIVE_VERIFIED` / `DEGRADED` / `ERROR`

## How this file is updated

This table is refreshed by hand alongside `INTEGRATION_MATRIX.md` whenever a connector's
auth state changes. It never contains secret values — only status. Credentials live in
Windows Credential Manager under the `BuzzMarketing/` prefix; check presence with:

```powershell
uv run marketing-system credentials status
```
