from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.config import load_config
from src.core.resolver import XContextResolver

cfg = load_config()
resolver = XContextResolver(cfg)

url = "https://x.com/AlchainHust/status/1971839749724975175"
print("Starting real E2E context resolution for:", url)
manifest = resolver.resolve_context(url=url, max_replies=20, force_refresh=True)

print("=== E2E RESOLUTION RESULT ===")
print("Job ID:", manifest.job_id)
print(f"Author: {manifest.root.author.name} (@{manifest.root.author.handle})")
print("Text Preview:", manifest.root.text[:120] + "...")
print("Media Count:", len(manifest.root.media))
for idx, m in enumerate(manifest.root.media):
    print(f" - Media #{idx}: type={m.type.value} duration={m.duration_seconds}s res={m.width}x{m.height}")
    t_prev = m.transcription_text[:120] if m.transcription_text else "N/A"
    print(f"   Transcription: {t_prev}")

print("Author Followups:", len(manifest.author_followups))
print("Top Replies:", len(manifest.top_replies))
for idx, r in enumerate(manifest.top_replies[:3]):
    print(f" - Reply #{idx} by @{r.author.handle} [{r.category.value} rank={r.rank}]: {r.text[:80]}")

print("Context Graph Nodes:", len(manifest.graph.nodes), "Edges:", len(manifest.graph.edges))
print("Coverage Status:", manifest.coverage.status)
print("Coverage Notes:", manifest.coverage.notes)
if manifest.reproduction_plan:
    print("Reproduction Plan Mode:", manifest.reproduction_plan.mode)
    print("Reproduction Plan Steps:", len(manifest.reproduction_plan.steps))
    for s in manifest.reproduction_plan.steps:
        print(f"   Step {s.step_number} [{s.risk_level}]: {s.name}")
