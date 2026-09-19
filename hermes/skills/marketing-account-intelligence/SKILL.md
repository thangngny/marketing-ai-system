---
name: marketing-account-intelligence
description: "Research, normalize, score, and stage accounts and leads."
version: 1.0.0
author: Workspace owner
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [marketing, leads, accounts, crm]
    category: productivity
    related_skills: [marketing-orchestrator, marketing-sales-copilot]
---

# Marketing Account Intelligence Skill

Convert an ICP into normalized account and lead records with transparent scoring. It stages data locally until live CRM authorization exists.

## When to Use

Use for lead search, account research, enrichment, deduplication, and lead scoring.

## Prerequisites

Use `marketing_handle_request`; Apollo/Zoho tools may report `MOCK_READY` or `NEEDS_AUTH`.

## How to Run

Start with search criteria and an exclusion list.

## Quick Reference

Source data, inferred fields, confidence, score reason, and next action must remain separate.

## Procedure

1. Define ICP filters.
2. Search the allowed connector or deterministic mock.
3. Normalize into canonical Lead/Account records.
4. Check duplicates before proposing CRM creation.
5. Score and explain A/B/C qualification.

## Pitfalls

Apollo enrichment may consume credits. Never run it from a health check.

## Verification

Mock records carry `synthetic=true` and `.example.invalid` domains.

