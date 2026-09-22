---
name: marketing-orchestrator
description: "Route marketing work through safe specialist tools."
version: 1.0.0
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

Route one request to the minimum specialist set and return one coherent result. This skill coordinates work; it does not bypass the MCP safety boundary.

## When to Use

Use for every Buzz marketing request and every system-status question.

## Prerequisites

The `local-ai-marketing-system` MCP server must expose `marketing_handle_request`, `marketing_system_status`, and `marketing_sync_readonly`.

## How to Run

Call `marketing_handle_request` with the user's complete text and `source_channel="buzz"`.

## Quick Reference

- Status → connector registry.
- Leads/accounts → `03_account_intelligence`.
- Content → `04_content`.
- Campaign → `01_strategy` + `07_campaign`.
- Performance → `08_kpi_learning`.

## Procedure

1. Call `marketing_handle_request` before drafting the answer.
2. Use only agents listed in the returned `agents` field.
3. Preserve `MOCK`, approval, and connector-state labels.
4. Return the tool's coherent `response`; add context only when the user asked for it.
5. Use `marketing_sync_readonly` only for explicitly requested live reads after the connector reports `CONNECTED`; never use it in mock mode.

## Pitfalls

- Never call provider APIs directly from `terminal`.
- Never treat `MOCK_READY` as `CONNECTED`.
- Never execute a high-impact action.

## Verification

The answer includes a correlation id when diagnosing, identifies the selected agents when relevant, and reports zero unapproved side effects.
