---
name: understand-x-post
description: >
  Reconstruct and comprehend the complete accessible context of an X/Twitter post:
  author identity, full post text, thread continuity, attached media (video/images),
  author follow-ups, ranked community reactions, and external referenced links.
version: 2.0.0
---

# Understand X Post Skill

## Purpose

This skill equips Buzz Codex Agents to fully understand an X (Twitter) post before drawing conclusions. Instead of looking only at the root text or video in isolation, the agent reconstructs the entire accessible context:
- Root post & author claims
- Author follow-up replies (clarifications, parts 2, 3...)
- Multimodal media (video transcription, image summaries)
- Community reactions & technical feedback
- External links & GitHub repository references
- Honest coverage accounting (`coverage.json`)

---

## Tool Workflow

### 1. Ingest Context
Call `x_context_ingest(url="https://x.com/...")`
- Automatically discovers media, author follow-ups, and ranked replies.
- Builds an evidence package in `x-context-intelligence/data/<job_id>`.

### 2. Inspect Post & Author Claims
Call `x_context_root(job_id)`
- Identify author handle, name, verified status.
- Analyze the primary post text and stated goals.

### 3. Review Multimodal Media
Call `x_context_media(job_id)`
- For video: checks transcripts, duration, resolution, and keyframes extracted by `x-video-intelligence`.
- For images: checks dimensions and visual descriptions.

### 4. Inspect Author Follow-ups & Technical Replies
Call `x_context_conversation(job_id, filter_author_only=False, min_rank=10)`
- Examine `author_followups` to see if the author posted setup tips, caveats, or download links.
- Review `top_replies` ranked by technical implementation, debunking, or questions.

### 5. Review Context Graph & Coverage
Call `x_context_summary(job_id)`
- Check `coverage.status`: `COMPLETE` vs `PARTIAL`.
- Read provenance graph to distinguish `ROOT_AUTHOR_CLAIM`, `OBSERVED_IN_VIDEO`, and `COMMUNITY_REPLY`.

---

## Standard Output Format

```markdown
# X CONTEXT ANALYSIS

**URL:** <URL>
**Author:** @<handle> (<name>)
**Coverage:** <COMPLETE | PARTIAL> (<retrieved>/<reported> replies)

### 1. Core Post & Objective
<Summary of author's post and claim>

### 2. Media Evidence
- **Type:** Video / Image
- **Findings:** <Observed demo actions or visual findings>

### 3. Author Clarifications & Follow-ups
- <Important notes posted by the author in the replies>

### 4. Community Insights & Edge Cases
- <Key feedback, bugs reported, or questions from the community>

### 5. Referenced Resources
- <GitHub links, docs, external sites>
```
