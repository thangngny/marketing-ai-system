# Workflow Matrix

States: `NEW → PLANNED → RUNNING → (WAITING_APPROVAL → APPROVED → RESUMING → RUNNING)* → DONE | BLOCKED | FAILED | CANCELLED`. Transition table: `workflows/engine.py::TRANSITIONS`. Every transition is logged in `workflow_transitions`.

| Workflow | Trigger | Steps (specialist) | Approval gate | Side effects | Status |
|---|---|---|---|---|---|
| `prospect_to_draft` | "Tìm … doanh nghiệp/lead … email/draft" | search (03) → dedupe vs Zoho (03) → score in code (03) → draft emails via runtime (04) → **owner gate** (06) → Outlook drafts (06, idempotent) → Sales task proposals (06, local) | `workflow.create_outlook_drafts`, bound to the exact drafts | drafts only; 0 emails sent; 0 CRM writes | PASS_MOCK end-to-end; production BLOCKED at step 1 (Apollo `NOT_CONFIGURED`) |
| `tool_approval` | any WRITE_LOW_RISK / HIGH_IMPACT tool call over MCP | call (requesting specialist) | the tool + exact payload | only after verified approval; HIGH_IMPACT still phase-gated | PASS_MOCK |

## Approval

- Code `MV-XXXXXX`; owner replies `DUYET <code>` / `TUCHOI <code>` in the workflow's Buzz channel.
- Verified by `BuzzSignedEventVerifier`: the event must be signed by the owner pubkey and posted after the request. Agents or the LLM posting the code do not count.
- Alternative: `marketing-system approvals approve <code>` in an interactive terminal (refuses non-TTY).
- TTL: 24 h (WRITE_LOW_RISK), 4 h (HIGH_IMPACT). HIGH_IMPACT approvals are single-use. A changed payload needs a fresh approval.

## Recovery

`mcp_server.main()` calls `engine.recover()` on start: interrupted `RUNNING` steps re-run (idempotency keys prevent duplicate drafts/tasks) and decided approvals resume. Also: `marketing-system workflows recover`.
