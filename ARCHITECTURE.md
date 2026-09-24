# Architecture

Decision record: [docs/ADR-runtime-agnostic-marketing-platform.md](docs/ADR-runtime-agnostic-marketing-platform.md). Modular monolith: one Python package, one MCP server process, one SQLite file.

```text
USER
  │  Buzz (chat, approvals, notifications)
  ▼
Wire transport (supplied by the active runtime)
  ├─ Hermes native Buzz gateway  (profile `marketing`, bot 8f006f39…, channel Welcome)   ← production today
  └─ Buzz Desktop ACP agents (Claude / Codex)                                            ← same hub, config only
  ▼
AgentRuntime  runtime/            HermesRuntime · ClaudeRuntime · CodexRuntime · MockRuntime (one contract)
  ▼  MCP stdio  (mcp_server.py — tool boundary only)
Conversation Gateway  gateway.py  normalize · identity · channel · Buzz event dedupe
Orchestrator          orchestrator.py + routing.py
  ├─ fast path  → tool hub → answer
  ├─ workflow   → workflows/engine.py (durable)
  └─ brief      → specialist instructions + allowed tools handed back to the runtime
Specialists           specialists.py   8 logical roles (data, not processes)
Policy                policy.py        ALLOW / DENY / REQUIRE_APPROVAL (code)
Approvals             workflows/approvals.py   payload-bound, expiring, verifier-only
Tool hub              tools/hub.py + tools/catalog.py   26 typed tools, 10 namespaces
Connectors            connectors/*     zoho (REST | hosted MCP) · m365 · apollo · linkedin · youtube · meta_ads · google_ads · website
  ▼
Provider APIs
```

Cross-cutting: `telemetry.py` (OTel-shaped spans in `logs/marketing.jsonl`), `credentials.py` (Windows Credential Manager), `models.py` (canonical entities), `capabilities.py` (per-capability truth), `workflows/store.py` (SQLite system of record for execution).

## Ownership

| Layer | Owns | Never owns |
|---|---|---|
| Buzz | conversation, owner's signed approvals | business data, credentials |
| Runtime (Hermes/Claude/Codex) | language: understanding, drafting, analysis | permission, approval, state |
| Orchestrator | routing, fast reads, starting workflows | provider payloads |
| Workflow engine | state machine, step persistence, resume | provider logic |
| Policy + approvals | whether an action may run | — |
| Tool hub | validation, idempotency, ledger, spans | routing |
| Connectors | auth, retries, pagination, normalization | policy |
| Zoho | CRM relationships (System of Record) | workflow state |
| SQLite | workflows, approvals, tool ledger, dedupe, staging | CRM truth |

## Two execution paths

- **A — fast**: `marketing_handle_request` → route → hub READ tools → answer. Example: status, lead count, KPI snapshot.
- **B — durable**: route → `WorkflowEngine.start` → steps persisted → `WAITING_APPROVAL` → owner replies `DUYET <code>` in Buzz (signed) → `workflow_resume` / restart recovery → `DONE`.

## Switching runtime

Hermes: profile `marketing` registers `marketing-system` MCP. Claude: `claude -p … --mcp-config runtime-configs/claude-mcp.json`. Codex: same server in `~/.codex/config.toml`. `MARKETING_RUNTIME` selects which runtime the workflow engine uses for language steps. Connectors, policy, workflows and models are untouched.

## Deliberately absent

Temporal, Kafka, Redis, containers, vector DB, per-provider MCP servers, per-specialist processes or Buzz bots, analytics warehouse.
