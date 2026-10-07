---
name: research-x-post
description: >
  Conduct deep investigation into claims, technical libraries, GitHub repositories,
  and community discussions mentioned in or stemming from an X/Twitter post.
version: 2.0.0
---

# Research X Post Skill

## Purpose

When an X post discusses an emerging technical tool, breakthrough, or controversial topic, this skill enables Buzz Codex Agents (especially **Research Intelligence**) to:
1. Verify external repository activity (latest commits, releases, open issues).
2. Distinguish between marketing hype and verified code capabilities.
3. Cross-reference community replies for reported failure modes or bugs.
4. Synthesize findings with official documentation.

---

## Tool Workflow

### 1. Ingest Post & Extract Links
Call `x_context_ingest(url="https://x.com/...")`
Then call `x_context_links(job_id)` to list referenced domains and GitHub repositories.

### 2. Verify External Repositories & Packages
For any detected GitHub link or npm/pip package:
- Use web search or read tools to check:
  - Repository status (active, archived, forks)
  - Current version vs version demonstrated in the post
  - Known issues related to Windows support or breaking changes

### 3. Check Community Debunks & Corrections
Call `x_context_conversation(job_id, min_rank=30)`
- Focus on replies categorized as `CORRECTION_OR_DEBUNK` or `TECHNICAL_IMPLEMENTATION`.
- Identify edge cases not mentioned in the author's primary post.

### 4. Synthesize Evidence
Classify all claims into the 8 truth categories:
- `OBSERVED_IN_VIDEO`
- `ROOT_AUTHOR_CLAIM`
- `ROOT_AUTHOR_REPLY`
- `VISIBLE_TEXT`
- `COMMUNITY_REPLY`
- `OFFICIAL_DOC_VERIFIED`
- `INFERRED`
- `UNKNOWN`

---

## Output Template

```markdown
# X RESEARCH DOSSIER

**Source:** <URL>
**Subject:** <Topic or Tool Name>
**Truth Assessment:** VERIFIED / PARTIAL / UNVERIFIED / DEBUNKED

### Author Claims vs External Reality
- **Claim:** ...
- **Verification:** ... (from official docs/repo)

### Community Findings & Caveats
- ...

### Technical Recommendations
- ...
```
