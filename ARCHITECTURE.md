# AI Marketing System Architecture

## Runtime path

```text
Buzz user/channel
  │
  ▼
Hermes native Buzz gateway
  │  isolated profile: marketing (logical role: marketing_orchestrator)
  ▼
Marketing Orchestrator
  ├─ deterministic intent routing
  ├─ specialist Hermes skills
  ├─ approval and impact policy
  └─ coherent final answer
  │
  ▼
Marketing MCP server (stdio, project-local Python environment)
  ├─ connector registry and status
  ├─ canonical model validation
  ├─ SQLite staging store
  ├─ structured audit log
  └─ mock/live adapter selection
       ├─ Zoho CRM
       ├─ Microsoft Graph
       ├─ Apollo
       ├─ LinkedIn
       ├─ YouTube
       ├─ Meta Ads
       ├─ Google Ads
       └─ Website
```

The integration service does not listen on a TCP port in the default deployment. Hermes launches it over stdio as an MCP server. SQLite is the only local datastore.

## Ownership boundaries

| Layer | Owns | Does not own |
|---|---|---|
| Buzz | Human conversation, membership, visible approvals | Business data or connector credentials |
| Hermes | Conversation, memory, sessions, skill selection, final response | Provider-specific payload formats |
| Router | Maps an intent to the minimum specialist set | Model inference or external authorization |
| Specialist skills | Marketing methods and output expectations | Direct API credentials |
| MCP integration server | Typed tools, safety policy, adapters, canonical mapping | Buzz transport or Hermes sessions |
| SQLite staging | Local canonical mock/staging records | Production system-of-record authority |
| Zoho (future) | CRM source of truth after live verification | Mock/synthetic records |

## Specialist routing

| Intent example | Selected specialist(s) |
|---|---|
| Phân tích đối thủ / thị trường | `02_market_intelligence` (+ `01_strategy` for recommendations) |
| ICP / định vị / mục tiêu | `01_strategy` |
| Tìm lead / nghiên cứu account | `03_account_intelligence` |
| Viết nội dung / landing page / video brief | `04_content` |
| SEO, keyword, AI-search/GEO | `05_seo_geo` |
| Chuẩn bị cuộc gọi / follow-up / deal support | `03_account_intelligence`, `06_sales_copilot` |
| Lập chiến dịch đa kênh | `01_strategy`, `07_campaign` |
| Báo cáo hiệu quả / attribution | `08_kpi_learning` |
| Trạng thái hệ thống | Orchestrator + connector registry only |

## Connector state model

| State | Meaning |
|---|---|
| `CONNECTED` | Credentials exist and a non-destructive live probe succeeded |
| `MOCK_READY` | Deterministic mock capability is usable |
| `NEEDS_AUTH` | Software/config is prepared but credentials or OAuth consent are missing |
| `DISABLED` | Operator policy disables the connector or operation |
| `DEGRADED` | Partially usable; a dependency or capability failed |
| `ERROR` | Probe or request failed and no healthy path exists |

Status must distinguish readiness from proof. Connector code alone is never reported as `CONNECTED`; only a live probe may establish that state.

## Environments

- `mock` (default): deterministic synthetic data only; no external calls.
- `sandbox`: explicit external test environment; no production mutations.
- `production`: explicit opt-in plus credentials; high-impact actions still require approval.

The environment is stored on every canonical record and every structured log event.

## Safety flow

```text
Request
  → classify READ / DRAFT / WRITE / HIGH_IMPACT
  → verify configured environment
  → verify connector capability and auth
  → for WRITE/HIGH_IMPACT: require explicit approval context
  → execute or return an approval-required draft
  → record correlation_id and outcome
```

Phase 1 implements no paid-campaign launch, budget mutation, email send, public publication, outreach send, CRM delete, or permission change.

## Secrets

Secrets live only in the isolated Hermes profile's restricted `.env` or an operator-selected secret manager. Project `.env` files are ignored by Git. Logs redact keys, tokens, authorization headers, cookies, and OAuth codes.

## Operational shape

- `scripts/start-all.ps1`: validates dependencies, starts the isolated Hermes gateway once.
- `scripts/stop-all.ps1`: stops only the marketing profile gateway.
- `scripts/status-all.ps1`: reports process and connector state.
- `scripts/doctor.ps1`: human-readable component diagnostics.
- `scripts/smoke-test.ps1`: unit/contract/mock/routing/security tests and optional Buzz checks.

Linux `.sh` wrappers are portability aids, not the active service mechanism on this audited host.

