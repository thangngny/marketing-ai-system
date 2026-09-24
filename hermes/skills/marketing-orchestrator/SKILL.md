---
name: marketing-orchestrator
description: "Route work via tool hub, workflows and approvals."
version: 2.0.0
author: Workspace owner
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [marketing, orchestration, safety]
    category: productivity
    related_skills: [marketing-strategy, marketing-market-intelligence, marketing-account-intelligence, marketing-content, marketing-seo-geo, marketing-sales-copilot, marketing-campaign, marketing-kpi-learning]
---

# Marketing Orchestrator Skill

Route one request to the minimum specialist set and return one coherent result. Routing, data reads, policy, approvals and workflow state are decided by code in the `marketing-system` MCP server; you do the language work.

## When to Use

Use for every Buzz marketing request and every system-status question.

## Prerequisites

MCP server `marketing-system` exposes `marketing_handle_request`, `marketing_system_overview`, the namespaced tool hub (`crm_*`, `prospecting_*`, `email_*`, `files_*`, `website_*`, `social_*`, `ads_*`, `content_*`, `analytics_*`, `system_*`) and `workflow_*` / `approval_status`.

## Procedure

1. Call `marketing_handle_request` with the full user text, `source_channel="buzz"`, and when known the Buzz `buzz_event_id`, `channel_id` and sender `user_id`.
2. Read `result_state` and `data`:
   - **Workflow** (`data.workflow`): relay the step list. If `WAITING_APPROVAL`, show the summary and tell the owner to reply `DUYET <code>` or `TUCHOI <code>`. Later, call `workflow_resume` when asked to continue.
   - **Specialist brief** (`data.specialist_brief`): do the work yourself as those specialists, using only the tools listed for each. Save drafts with `content_save_draft`. Keep every `BẢN NHÁP` / `KHÔNG KHỞI CHẠY` label.
   - **Fast result** (status, leads, KPI snapshot): answer from the returned data only.
3. Never present `MOCK` data as real, never convert `NEEDS_*` / `NOT_CONFIGURED` into "connected".
4. Answer in Vietnamese, one coherent message, no tool chatter.

## Approvals — the hard rule

You cannot approve anything. No tool accepts an approval flag. Writes (`crm_create_task`, `email_send`, `social_publish_post`, `ads_*` changes) automatically become a workflow that waits for the owner's **signed** Buzz message. Do not post `DUYET …` yourself; it would not count and must not be attempted.

## Pitfalls

- Never call provider APIs from `terminal`.
- Never call all eight specialists by default.
- Never invent metrics; KPI answers separate FACT / INFERENCE / HYPOTHESIS / RECOMMENDATION.

## Verification

The answer cites the workflow id or correlation id when diagnosing, names the specialists used, and reports zero unapproved side effects.
