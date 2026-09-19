---
name: marketing-market-intelligence
description: "Research competitors, markets, and industry evidence."
version: 1.0.0
author: Workspace owner
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [marketing, research, competitors]
    category: research
    related_skills: [marketing-orchestrator, marketing-strategy]
---

# Marketing Market Intelligence Skill

Produce source-backed competitor and industry findings. It does not present unverified web claims as internal business facts.

## When to Use

Use for competitor analysis, market signals, industry changes, and opportunity scans.

## Prerequisites

Use `web_search`/`web_extract` for current sources and `marketing_handle_request` for routing.

## How to Run

Define the comparison frame before collecting evidence.

## Quick Reference

Prefer primary sources; record source date and confidence.

## Procedure

1. Define competitors and decision criteria.
2. Gather current primary evidence.
3. Compare claims, offers, channels, proof, and gaps.
4. Separate observed facts from inference.
5. Hand strategic implications to `01_strategy`.

## Pitfalls

Do not scrape restricted platforms or copy unsupported claims.

## Verification

Every material external claim has a source and an access date.

