from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional
from ..models import JobManifest, ReproductionPlan


def make_job_id(url_or_path: str) -> str:
    """Generate deterministic job_id based on source URL or filename."""
    h = hashlib.sha256(url_or_path.encode("utf-8")).hexdigest()[:12]
    return f"job_{h}"


class EvidencePackage:
    def __init__(self, job_dir: Path):
        self.job_dir = job_dir
        self.job_dir.mkdir(parents=True, exist_ok=True)
        self.media_dir = self.job_dir / "media"
        self.audio_dir = self.job_dir / "audio"
        self.frames_dir = self.job_dir / "frames" / "full"
        self.crops_dir = self.job_dir / "frames" / "crops"
        self.scenes_dir = self.job_dir / "scenes"
        self.analysis_dir = self.job_dir / "analysis"
        self.reproduction_dir = self.job_dir / "reproduction"

        for d in [self.media_dir, self.audio_dir, self.frames_dir, self.crops_dir, self.scenes_dir, self.analysis_dir, self.reproduction_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self.manifest_file = self.job_dir / "manifest.json"
        self.plan_file = self.reproduction_dir / "reproduction_plan.json"
        self.report_file = self.job_dir / "analysis.md"

    def save_manifest(self, manifest: JobManifest):
        with open(self.manifest_file, "w", encoding="utf-8") as f:
            f.write(manifest.model_dump_json(indent=2))

        # Also write post.txt and transcript.json for quick reading
        (self.job_dir / "post.txt").write_text(manifest.post_text, encoding="utf-8")
        with open(self.job_dir / "transcript.json", "w", encoding="utf-8") as f:
            json.dump([s.model_dump() for s in manifest.transcript], f, indent=2)

    def load_manifest(self) -> Optional[JobManifest]:
        if self.manifest_file.exists():
            with open(self.manifest_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return JobManifest(**data)
        return None

    def save_plan(self, plan: ReproductionPlan):
        with open(self.plan_file, "w", encoding="utf-8") as f:
            f.write(plan.model_dump_json(indent=2))

    def load_plan(self) -> Optional[ReproductionPlan]:
        if self.plan_file.exists():
            with open(self.plan_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ReproductionPlan(**data)
        return None

    def generate_user_report(self, manifest: JobManifest, plan: Optional[ReproductionPlan] = None) -> str:
        """Format concise user report adhering to Section 35 format."""
        lines = [
            "# X VIDEO ANALYSIS",
            "",
            f"**Source:** {manifest.source_url}",
            f"**Duration:** {manifest.duration_seconds:.1f}s | **Resolution:** {manifest.resolution}",
            f"**Demo objective:** {plan.demo_objective if plan else 'Video demonstration analysis'}",
            "",
            "### What the video does:"
        ]

        if manifest.extracted_steps:
            for s in manifest.extracted_steps[:5]:
                lines.append(f"{s.step_id}. {s.observed_action}")
        else:
            lines.append("1. Demonstrated feature walkthrough.")

        lines.extend([
            "",
            "### Important tools:",
            "- " + (", ".join([v.component for v in (plan.verifications if plan else [])]) or "Local tools"),
            "",
            "### Observed commands:"
        ])

        cmds = [s.command_candidate for s in manifest.extracted_steps if s.command_candidate]
        if cmds:
            for c in cmds[:5]:
                lines.append(f"- `{c}`")
        else:
            lines.append("- (No explicit shell commands extracted directly from text/audio)")

        lines.extend([
            "",
            "### Current verification:",
            f"- OS: Windows (PowerShell translation active)",
            f"- Tools verified: {len(plan.verifications) if plan else 0} components inspected"
        ])

        if plan and plan.steps:
            lines.extend([
                "",
                "### Recommended implementation plan:",
            ])
            for st in plan.steps:
                lines.append(f"- Step {st.step_id} [{st.risk_level.value}]: `{st.command_or_action}`" + (" (Needs Approval)" if st.requires_approval else ""))

        lines.extend([
            "",
            "### Actions already executed:",
            "- Ingested media, extracted frames, scenes, and audio transcript.",
            "",
            f"### Result: {plan.overall_status if plan else 'ANALYZED'}"
        ])

        report_text = "\n".join(lines)
        self.report_file.write_text(report_text, encoding="utf-8")
        return report_text
