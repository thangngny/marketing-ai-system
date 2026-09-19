# ADR-001: Local-first Marketing System Architecture

- Status: Accepted for Phase 1
- Date: 2026-09-19
- Decision owners: workstation owner + implementation agent

## Context

The required interaction path is Buzz → Hermes → specialist marketing capabilities → integration tools → Hermes → Buzz. Most external service credentials do not exist yet, and no external write may happen during bootstrap.

The audited host differs from the original hint: it is Windows 10 with Buzz Desktop 0.5.23 and Hermes Agent 0.21.3 already installed. Hermes has a bundled native Buzz gateway plugin but no configured Buzz identity and no usable inference-provider authentication. The installed Hermes Git worktree is dirty with unrelated changes.

Current official behavior and constraints:

- Buzz is a self-hostable human/agent workspace. Its CLI is JSON-in/JSON-out and the production self-host path is the Compose bundle, while the root development Compose is not a production deployment ([Block Buzz README](https://github.com/block/buzz/blob/main/README.md)).
- Hermes documents three Buzz paths: Desktop-managed ACP, `buzz-acp`, and the native gateway. The native gateway preserves Hermes memory, skills, approvals, cron, and sessions ([Hermes Buzz integration](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/integrations/buzz.md)).
- The native Hermes Buzz gateway supports channels, DMs, mention gating, allowlists, threaded replies, attachments, WebSocket inbound, polling fallback, and CLI outbound ([Hermes Buzz gateway guide](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/messaging/buzz.md)).
- Hermes exposes MCP as its supported external tool boundary. The official MCP Python SDK 2.x is the current stable line and supports stdio plus Streamable HTTP ([MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)).
- Zoho CRM v8 uses OAuth 2.0; access tokens are short-lived, refresh tokens are confidential, and scopes should be limited by module/operation ([Zoho OAuth](https://www.zoho.com/crm/developer/docs/api/v8/oauth-overview.html), [Zoho scopes](https://www.zoho.com/crm/developer/docs/api/v8/scopes.html)).
- Microsoft Graph recommends MSAL and least-privilege permissions; delegated permission is preferred where a signed-in user's scope is sufficient ([Graph best practices](https://learn.microsoft.com/graph/best-practices-concept), [Graph permissions](https://learn.microsoft.com/en-us/graph/permissions-overview)).
- Apollo exposes a no-credit API-key health endpoint, but credit semantics vary by endpoint. People search currently costs zero credits, while organization search currently costs one credit per page; enrichment consumes credits ([Apollo API](https://docs.apollo.io/reference/apollo-api), [people search](https://docs.apollo.io/reference/people-api-search), [organization search](https://docs.apollo.io/reference/organization-search)).
- LinkedIn uses OAuth 2.0 and most marketing capabilities require product approval. Marketing APIs require member authorization, and Advertising/Community access tiers are separately controlled ([LinkedIn access](https://learn.microsoft.com/en-us/linkedin/shared/authentication/getting-access), [LinkedIn Marketing API](https://learn.microsoft.com/en-us/linkedin/marketing/)).
- YouTube Data API requires a Google Cloud project and either an API key or OAuth; mutations/private data require OAuth and every request consumes quota ([YouTube Data API](https://developers.google.com/youtube/v3/getting-started), [API reference](https://developers.google.com/youtube/v3/docs)).
- Meta publishes the official Python Business SDK, and Marketing API use requires a developer app, token, permissions, and an ad account ([Meta Business SDK](https://github.com/facebook/facebook-python-business-sdk), [official Meta Postman collection](https://www.postman.com/meta/facebook-marketing-api/documentation/0zr4mes/facebook-marketing-api-mapi)).
- Google Ads requires OAuth 2.0 plus a developer token, and a customer ID (plus manager ID where applicable). Mutate operations are separate from reads and will remain disabled ([Google Ads authorization](https://developers.google.com/google-ads/api/rest/auth), [mutate operations](https://developers.google.com/google-ads/api/rest/common/mutate)).

## Decision

### 1. Primary chat transport

Use Hermes' native Buzz gateway plugin as the production path.

```text
Human
  → Buzz hosted workspace/channel
  → Hermes native Buzz gateway (isolated marketing profile)
  → Marketing Orchestrator instructions + deterministic router
  → specialist skill selection
  → project-local MCP integration server
  → mock or live connector
  → canonical result
  → Hermes final reply
  → Buzz
```

`buzz-acp` and Desktop-managed ACP are optional diagnostic/fallback paths only. They are not dependencies of normal operation.

### 2. Isolation

Create a Hermes profile whose CLI-safe id is `marketing` and whose logical/display role is `marketing_orchestrator`. Do not modify the default profile or installed Hermes source tree. The project lives in its own Git repository at `C:\Users\Admin\marketing-ai-system`.

The profile will have:

- its own Hermes home/config/state;
- a dedicated Buzz Nostr identity;
- an owner-only Buzz allowlist;
- marketing-only skills and memory;
- terminal working directory set to this project;
- an MCP entry that launches the project-local server over stdio.

### 3. Orchestration and specialist agents

Hermes remains the conversational orchestrator. Specialist agents are implemented as isolated Hermes skills plus a deterministic router/tool trace, not as eight always-running model processes. This reuses Hermes' agent runtime and avoids another agent framework.

Logical specialists:

1. `01_strategy`
2. `02_market_intelligence`
3. `03_account_intelligence`
4. `04_content`
5. `05_seo_geo`
6. `06_sales_copilot`
7. `07_campaign`
8. `08_kpi_learning`

The MCP router returns only the required specialists for an intent. The orchestrator produces one coherent response and includes a compact processing trace when useful.

### 4. Integration boundary

Use one project-local Python MCP server over stdio. It exposes typed tools for:

- system status and connector capability discovery;
- deterministic intent routing;
- mock lead/account search and staging;
- content/campaign draft creation;
- read-only connector probes;
- approval-gated execution requests.

Connector implementations share a contract:

```text
health()
capabilities()
auth_status()
read()/search()
create_draft()
execute(approval_context)
```

Every connector reports one primary state: `CONNECTED`, `MOCK_READY`, `NEEDS_AUTH`, `DISABLED`, `DEGRADED`, or `ERROR`. A connector without credentials may report both `MOCK_READY` capability and `NEEDS_AUTH` as its live blocker.

### 5. Canonical data and staging

Use SQLite in the project runtime data directory. Canonical records include Lead, Contact, Account, Company, Opportunity, Deal, Task, Campaign, ContentAsset, ChannelPost, AdCampaign, Metric, Activity, and SourceReference.

Every record includes an environment discriminator (`mock`, `sandbox`, or `production`) plus source, external id, timestamps, status, confidence, owner, and correlation id. The store rejects cross-environment updates so synthetic records cannot silently become production records.

### 6. Mock mode

Default to `MARKETING_ENVIRONMENT=mock`. Fixtures are deterministic, visibly synthetic, and stable across runs. No mock record is written into a production namespace.

Production mode requires an explicit configuration change and credentials. Presence of credentials alone never switches the environment.

### 7. Safety

Classify every operation as `READ`, `DRAFT`, `WRITE`, or `HIGH_IMPACT`.

- `READ` and local `DRAFT` may execute automatically.
- `WRITE` requires an explicit approval token/context.
- `HIGH_IMPACT` always requires explicit approval and live credentials.
- Email send, public publishing, outreach, ad launch/budget change, CRM delete, permission change, contract signing, and production mutation are always high-impact.

Boot mode is `SAFE_DRY_RUN`. All paid-ad connector mutation methods remain disabled in Phase 1, even if credentials appear.

### 8. Operations

Use PowerShell entry points on the audited Windows host, with shell equivalents kept portable where practical. Scripts are idempotent and expose `start-all`, `stop-all`, `status-all`, `doctor`, and `smoke-test`.

Do not create a Scheduled Task until the native Buzz round trip and restart test pass. No local Buzz relay will be installed because a hosted workspace already exists; introducing Docker/Postgres/Redis only for a relay would violate the minimal-change rule.

## Alternatives considered

### Make `buzz-acp` mandatory

Rejected. It adds a bridge and a second response contract while the installed Hermes supports a native gateway that preserves the desired Hermes features directly.

### Modify Hermes core

Rejected. Hermes already provides Buzz and MCP, its source worktree is dirty, and upstream explicitly prefers third-party integrations at the edge.

### Import the existing seven-agent Buzz team snapshot as the runtime

Rejected as the primary runtime. It is not currently imported, contains seven roles rather than the required eight, and would move orchestration into Buzz-managed agents instead of Hermes. It remains a reference asset.

### One service per connector or an external message bus

Rejected for the MVP. A single stdio MCP server and SQLite store are sufficient and easier to audit.

### Local self-hosted Buzz relay

Deferred. The existing hosted relay is configured and reusable. The official production bundle would require Docker, PostgreSQL, Redis, and MinIO, none of which is installed. A local dev relay would not be an acceptable final production-like deployment.

## Consequences

Positive:

- Existing Hermes/Buzz installations are preserved.
- Live credentials can replace mock adapters without changing agent prompts or canonical models.
- The system remains local-first and has no mandatory open port for the integration layer.
- Safety checks are enforced in code, not only in prompts.

Limitations:

- Live Buzz↔Hermes acceptance cannot pass until the owner completes provider authentication and grants a dedicated Buzz identity membership in a channel.
- The current host is Windows, so systemd user services and Linux-only scripts cannot be the active operational mechanism.
- Live connector behavior remains `SKIPPED_NEEDS_AUTH` until each service is authorized.

## Revisit criteria

Revisit this decision only if:

- the native Hermes Buzz plugin fails on a supported, correctly configured identity after diagnosis;
- a connector requires a long-running webhook listener that cannot be safely represented inside the existing service;
- production scale exceeds a single-host SQLite workload;
- the owner explicitly moves the deployment to the intended Ubuntu workstation.

