"""
GTM Brain Knowledge & RAG Engine for Minh Van Logistics & Buzz Marketing OS.
Provides unified enterprise knowledge indexing, retrieval, and skill routing.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

BRAIN_DIR = Path(r"C:\Users\Admin\marketing-ai-system\gtm-brain")


class BrainSnippet(BaseModel):
    category: str
    source_file: str
    title: str
    content: str
    relevance_score: float = 1.0


class GTMBrainEngine:
    def __init__(self, brain_dir: Path = BRAIN_DIR):
        self.brain_dir = brain_dir
        self._cache: Dict[str, str] = {}
        self._index: List[Dict[str, Any]] = []
        self._build_index()

    def _build_index(self):
        self._index.clear()
        if not self.brain_dir.exists():
            return

        for md_file in self.brain_dir.rglob("*.md"):
            try:
                rel = md_file.relative_to(self.brain_dir)
                category = rel.parts[0] if len(rel.parts) > 1 else "general"
                text = md_file.read_text(encoding="utf-8")
                self._cache[str(rel)] = text

                # Full document entry
                doc_title = text.splitlines()[0].lstrip("#").strip() if text.splitlines() else str(rel)
                self._index.append({
                    "category": category,
                    "source_file": str(rel),
                    "title": doc_title,
                    "content": text.strip(),
                    "text_search": (doc_title + " " + text).lower(),
                })

                # Split by H2 headers for granular chunks
                sections = re.split(r"\n(?=##\s)", text)
                for sec in sections:
                    lines = sec.strip().splitlines()
                    if not lines:
                        continue
                    header = lines[0].lstrip("#").strip()
                    body = "\n".join(lines[1:]).strip()
                    self._index.append({
                        "category": category,
                        "source_file": str(rel),
                        "title": header,
                        "content": sec.strip(),
                        "text_search": (header + " " + body).lower(),
                    })
            except Exception:
                pass

    def query(self, query_text: str, category: Optional[str] = None, limit: int = 3) -> List[BrainSnippet]:
        words = [w.lower() for w in re.findall(r"\w+", query_text) if len(w) > 1]
        results = []

        for item in self._index:
            if category and item["category"] != category:
                continue

            target = item["text_search"]
            matches = sum(1 for w in words if w in target)
            if matches > 0:
                score = matches / max(len(words), 1)
                results.append((score, BrainSnippet(
                    category=item["category"],
                    source_file=item["source_file"],
                    title=item["title"],
                    content=item["content"],
                    relevance_score=round(score, 2),
                )))

        # Sort by relevance descending
        results.sort(key=lambda x: -x[0])
        return [r[1] for r in results[:limit]]

    def get_service_info(self, service_name: str) -> Optional[str]:
        snippets = self.query(service_name, category="services", limit=1)
        return snippets[0].content if snippets else None

    def get_icp(self, industry_or_code: str) -> Optional[str]:
        snippets = self.query(industry_or_code, category="icp", limit=1)
        return snippets[0].content if snippets else None

    def get_outreach_policy(self) -> Optional[str]:
        snippets = self.query("outreach spam policy", category="policies", limit=1)
        return snippets[0].content if snippets else None

    def list_skills(self) -> List[str]:
        return sorted([f.name for f in (self.brain_dir / "skills").glob("*.md")])
