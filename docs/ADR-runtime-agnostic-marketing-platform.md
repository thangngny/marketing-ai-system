# ADR-002: Runtime-agnostic marketing platform (modular monolith)

- Status: Accepted
- Date: 2026-09-24
- Supersedes: nothing; extends ADR-001 (transport and connector decisions stay valid)
- Baseline: tag `pre-runtime-agnostic-architecture`

## Problem

Phase 1 proved the Buzz → Hermes → MCP path, but the application **is** Hermes-shaped:

1. The only way a request reaches business logic is the Hermes Buzz gateway calling an MCP tool. No code in the repo can run the same request through another runtime.
2. The eight "specialists" are regex routes whose answers are hard-coded templates.
3. Approval is a boolean argument the LLM passes (`explicit_approval=True`). That is a prompt, not a boundary.
4. Workflow state lives only in the LLM session. A restart loses long work.
5. Tool impact is guessed from action-name prefixes; nothing binds a tool to an impact level, a specialist, or an idempotency key.

## Current architecture (audited, see CURRENT_STATE.md)

```text
Buzz ─► Hermes native gateway (profile marketing, gpt-5.6-sol) ─► MCP stdio (6 tools)
                                                                 └► orchestrator.py (regex + templates)
                                                                    └► connectors (mock | website, youtube live)
Buzz ─► Desktop ACP agents (Claude, Codex, Antigravity) ─► shell ─► buzz-marketing/connectors/*.js (duplicate)
Claude Code ─► Zoho hosted MCP (read)
```

## Decision

### 1. Target shape

```text
Buzz ──► Conversation Gateway (normalize, dedupe, identity)
           ──► Orchestrator (route → RouteDecision; fast path | workflow)
                 ──► AgentRuntime  [HermesRuntime | ClaudeRuntime | CodexRuntime | MockRuntime]
                 ──► Specialist registry (8 logical roles: instructions, allowed tools, impact ceiling)
                 ──► Workflow engine (SQLite state machine) + Approval engine (verifier-bound)
                 ──► Policy engine (deterministic ALLOW / DENY / REQUIRE_APPROVAL)
                 ──► Tool hub (typed ToolSpec, namespaced crm.* email.* …) ── exposed via one MCP server
                       ──► Connector adapters ──► provider APIs
cross-cutting: telemetry spans · Credential Manager · canonical models · idempotency ledger
```

One Python package, one MCP server process launched by whichever runtime is active, one SQLite file.

### 2. Hermes is a runtime, not the architecture

`AgentRuntime` contract: `run(input) → RuntimeResult`, `continue_session(session_id, input)`, `invoke_specialist(spec, input)`, `expose_tools()`, `cancel(session_id)`, `health()`, `capabilities()`.

- `HermesRuntime` (first, production): `hermes -p marketing -z …` for one-shot/specialist calls; health reads the gateway **process**, not a state file.
- `ClaudeRuntime`, `CodexRuntime`: same contract over `claude -p` / `codex exec`. Both CLIs work on this host, so they are implemented thinly and contract-tested, but not production-enabled.
- `MockRuntime`: deterministic, used by tests and mock-mode workflows.

All four share one contract test suite. Connectors, policy, workflows, and models import nothing runtime-specific.

Transport caveat, accepted knowingly: the **Buzz wire transport** today is either Hermes' native gateway or Buzz Desktop's `buzz-acp`. Both terminate in the same MCP tool hub, so swapping runtime means pointing a different agent at the same hub — no business code changes. We do not build our own relay client now.

### 3. Eight specialists are logical roles

A specialist is a record: id, Vietnamese name, instructions (the existing `hermes/skills/*/SKILL.md`), allowed tool namespaces, max impact, output schema name. No process, identity, or database per specialist. Promotion to a separate runtime requires evidence (isolation, different model, long autonomy).

### 4. MCP is the tool boundary only

MCP exposes the hub's tools. It does not route, hold workflow state, or decide policy. One server (`marketing-system`), namespaced tools. Legacy tool names stay for the existing Hermes skill.

### 5. Deterministic policy and approval

- Every `ToolSpec` declares `impact ∈ {READ, DRAFT, WRITE_LOW_RISK, HIGH_IMPACT}`.
- `PolicyEngine.decide(tool, specialist, environment, safe_dry_run, approval)` → `ALLOW | DENY | REQUIRE_APPROVAL`. Order: specialist permission → environment → impact → approval match.
- Approval record binds `workflow_id + tool + sha256(canonical payload)`, has `expires_at`, is single-use for HIGH_IMPACT, and becomes invalid if the payload hash changes.
- **Only an `ApprovalVerifier` can move an approval to APPROVED.** No MCP tool accepts "approved=true". Verifiers:
  - `BuzzSignedEventVerifier`: finds a message in the workflow's Buzz channel **signed by the owner pubkey** containing `DUYET <code>` / `TUCHOI <code>` after the request time. The LLM cannot forge a Nostr signature. Needs a reader identity key in Credential Manager (`BuzzMarketing/BUZZ_APPROVAL_READER_KEY`); Hermes' own bot key is sealed by Hermes and deliberately not tunnelled.
  - `LocalOperatorVerifier`: `marketing-system approvals approve <id>` in an interactive console.
- Phase rule kept: HIGH_IMPACT execution stays disabled in code even after approval until a connector explicitly enables it.

### 6. Durable workflow

SQLite tables `workflows`, `workflow_steps`, `approvals`, `idempotency`, `gateway_events`. States: `NEW → PLANNED → RUNNING → (WAITING_APPROVAL → APPROVED → RESUMING → RUNNING)* → DONE | BLOCKED | FAILED | CANCELLED`. Transitions are validated by a table, not by the LLM. Steps are deterministic functions registered per workflow type; a step may call the runtime for language work, but its output is persisted before the next step. Engine is re-entrant: a new process resumes from the store. Interfaces (`WorkflowStore`, `WorkflowEngine`, `WorkflowStep`, `ApprovalRequest`) keep Temporal possible later.

### 7. LLM vs code

LLM: intent nuance, research, drafting, qualitative scoring rationale, summaries. Code: permission, approval, money, send, CRM mutation, retries, timeouts, state transitions, idempotency, auth.

### 8. Systems of record

Zoho = CRM relationships (Lead/Contact/Account/Deal/Task). Workflow DB (SQLite) = workflow, approval, tool ledger, gateway dedupe. Artifact store = `data/artifacts/` files referenced by workflow rows. No analytics warehouse until KPI history volume requires it.

### 9. Capability model

Per-capability states replace one-word service states: `NOT_CONFIGURED, MOCK_READY, AUTHENTICATING, NEEDS_MFA, NEEDS_CAPTCHA, NEEDS_ADMIN_APPROVAL, NEEDS_API_ACCESS, LIVE_READ, LIVE_DRAFT, LIVE_WRITE, DEGRADED, ERROR`, reported for AUTH / READ / ANALYTICS / DRAFT / PUBLISH.

### 10. Observability

`correlation_id` per request, `workflow_id` per durable job, span per hop with `latency_ms`, `runtime`, `model`, `specialist`, `tool`, `connector`, `environment`, `result`, `error_code`, written to `logs/marketing.jsonl` in an OpenTelemetry-shaped record (`trace_id`, `span_id`, `parent_span_id`, `name`, `attributes`). Redaction unchanged.

## Why a modular monolith

Single operator, one Windows host, low volume. Separate services would add process supervision, auth between services, and failure modes with no benefit today. Module boundaries (imports only through interfaces) keep the split possible.

## Intentionally NOT introduced

Temporal, Kafka, Redis, Kubernetes/Docker, vector DB, one MCP server per provider, one process or Buzz bot per specialist, custom broker, analytics warehouse, a home-grown Buzz relay client.

## Migration strategy

Milestones, each ending with the full suite green and the Hermes gateway still `connected`:
1. Audit + ADR + hermetic baseline.
2. `AgentRuntime` + Hermes/Claude/Codex/Mock adapters + contract tests; doctor uses process truth.
3. Specialist registry; routing returns registry objects.
4. Policy + approval engine; remove LLM-asserted approval.
5. Tool hub with typed specs; MCP exposes it.
6. Workflow engine with restart recovery.
7. Canonical models extended (Approval, Workflow, ToolResult, ConnectorStatus, MetricSnapshot, LeadCandidate).
8+. Zoho live → Apollo → Microsoft → others.

## Rollback

Each milestone is a separate commit on `marketing-system-phase1`. `git checkout pre-runtime-agnostic-architecture` restores the audited system; the Hermes profile is not modified except for MCP tool additions, which are backward compatible (old tool names retained).
