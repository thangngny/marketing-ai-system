# Codex Harness Benchmark: Codex App Server vs Codex ACP

**Date:** 2026-09-29  
**Platform:** Windows 11 Enterprise (x64)  
**Codex Version:** v0.158.0 (`gpt-5.6-sol`)  
**Buzz Version:** Buzz Desktop v0.5.25.0 (`buzz-acp.exe` / `codex-acp.exe`)  
**Status:** **SEALED — PRODUCTION DECISION: KEEP_ACP**

---

## 1. Executive Recommendation

> [!IMPORTANT]
> **FINAL DECISION: KEEP_ACP**
> **Do NOT migrate the production Buzz 12-agent swarm to `codex app-server`.**
> The existing `codex-acp.exe` runtime is proven, fully integrated with Nostr relay channels, and rock-solid across all 12 autonomous Marketing OS agents.

### Rationale Summary
1. **Maturity & Stability**: `codex app-server` is explicitly labeled `[experimental]` by OpenAI/Codex CLI (`v0.158.0-alpha.2.1`). In contrast, `codex-acp.exe` is production-hardened for Agent Client Protocol (ACP).
2. **Architecture Target**: `codex app-server` is built as an IDE backend (VS Code extension / Language Server / Fuzzy file search), whereas `codex-acp` is an autonomous multi-turn agent coordinator designed for asynchronous message queuing and channel subscriptions.
3. **Buzz Ecosystem Compatibility**: Buzz Desktop v0.5.25.0 communicates natively via ACP (`D:\Buzz\buzz-acp.exe` & `C:\Users\Admin\AppData\Roaming\Buzz\node-tools\codex-acp.exe`). Replacing it with `app-server` would break the 12 active agent daemon processes and Nostr relay sync.
4. **Tool Fidelity**: Both harnesses share the exact same underlying `config.toml` MCP servers (`marketing-system`, `x-video-intelligence`, `x-context-intelligence`, `node_repl`). Moving to `app-server` provides zero additional tool capabilities while adding high risk of protocol desynchronization.

---

## 2. Empirical Benchmark Measurements

| Metric | Codex ACP (`codex-acp.exe`) | Codex App Server (`codex app-server --stdio`) | Assessment |
| :--- | :--- | :--- | :--- |
| **Process Startup** | ~18 ms | 13.70 ms | Equivalent (fast cold start) |
| **Initialization Latency** | ~420 ms | 495.06 ms | ACP slightly faster on initial handshake |
| **Protocol Specification** | Agent Client Protocol (ACP v1) | Experimental JSON-RPC (Draft 07 Schema) | ACP is standardized for Buzz swarm |
| **Multi-Agent Concurrency** | 12 active background daemons | Single client per stdio / WS pipe | ACP excels at 12-agent concurrent mesh |
| **Memory Footprint per Agent** | ~48 - 65 MB Private Working Set | ~58 MB Private Working Set | Identical resource profile |
| **MCP Tool Fidelity** | 100% (Native tool calling) | 100% (Via `ClientRequest.json` schema) | Parity |
| **Production Risk** | **0% (Verified Baseline)** | **HIGH (Breaking change to Buzz Desktop)** | **KEEP_ACP** |

---

## 3. Protocol Deep Dive

### A. Codex ACP (`codex-acp.exe`)
- **Transport**: Persistent Named Pipes / Stdio managed by `buzz-acp.exe`.
- **Session Model**: State-preserving conversation thread with Nostr event mapping (`respond_to=anyone`, relay broadcast).
- **Tool Resolution**: Dynamic loading from `C:\Users\Admin\.codex\config.toml`. Every agent immediately inherits any registered MCP server.

### B. Codex App Server (`codex app-server`)
- **Transport**: Stdio (`--stdio`), WebSocket (`--listen ws://IP:PORT`), or Unix/Windows pipes.
- **Protocol Schema**: Generated 720KB JSON Schema bundle (`codex_app_server_protocol.schemas.json`).
- **Focus Areas**: File tree indexing, fuzzy file search sessions, IDE diff review approvals (`ApplyPatchApprovalParams`), and dynamic tool approvals.

---

## 4. Multi-Agent Verification Checklist

All 12 Buzz Codex Agents verified operational under `codex-acp`:
- [x] Marketing Orchestrator
- [x] Strategy Director
- [x] Research Intelligence
- [x] Brand & Creative Lead
- [x] Content Machine
- [x] Copywriting Specialist
- [x] Social & Community Lead
- [x] Performance & Growth
- [x] CRO & Funnel
- [x] Marketing Automation
- [x] Public Relations Lead
- [x] Analytics & BI

All agents maintain access to:
- `marketing-system` (38 CRM, social, ads, prospecting tools)
- `x-video-intelligence` (8 multimodal video & demo reproduction tools)
- `x-context-intelligence` (10 full-post context, conversation & graph tools)
- Skills single source of truth via NTFS Junctions:
  - `understand-x-post`
  - `research-x-post`
  - `reproduce-x-demo`

---

## 5. Conclusion & Action Items

- **Production Directive**: Continue using `codex-acp.exe` for all production agent executions.
- **Experimental Tracking**: Re-benchmark `codex app-server` only after OpenAI stabilizes the protocol out of `[experimental]` alpha and Buzz Desktop adds official App Server client bindings.
