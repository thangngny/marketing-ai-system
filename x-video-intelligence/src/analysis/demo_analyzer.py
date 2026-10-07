from __future__ import annotations

import re
from typing import List, Tuple
from ..models import ExtractedStep, JobManifest, TruthClassification, TranscriptSegment


COMMAND_REGEX = re.compile(
    r"(?:^|\n|\s)(?:[$#>]\s*|)(npm\s+[^\n;]+|pip\s+install\s+[^\n;]+|git\s+clone\s+[^\n;]+|python\s+[^\n;]+|node\s+[^\n;]+|uv\s+[^\n;]+|docker\s+[^\n;]+|brew\s+[^\n;]+|curl\s+[^\n;]+|wget\s+[^\n;]+|cargo\s+[^\n;]+)",
    re.IGNORECASE
)


def extract_steps_from_multimodal_evidence(manifest: JobManifest) -> List[ExtractedStep]:
    """Synthesize video post text, audio transcript, and visual scenes into structured steps."""
    steps: List[ExtractedStep] = []
    step_counter = 1

    # 1. Analyze post text for declared objective / instructions
    if manifest.post_text:
        commands_in_post = COMMAND_REGEX.findall(manifest.post_text)
        for cmd in commands_in_post:
            steps.append(ExtractedStep(
                step_id=step_counter,
                start=0.0,
                end=0.0,
                observed_action=f"Command specified in post description: {cmd}",
                spoken_content="",
                command_candidate=cmd.strip(),
                status=TruthClassification.VISIBLE_TEXT,
                confidence=0.95
            ))
            step_counter += 1

    # 2. Analyze transcript segments
    for seg in manifest.transcript:
        # Search for spoken commands or tool actions
        spoken_cmds = COMMAND_REGEX.findall(seg.text)
        if spoken_cmds:
            for sc in spoken_cmds:
                steps.append(ExtractedStep(
                    step_id=step_counter,
                    start=seg.start,
                    end=seg.end,
                    observed_action=f"Mentioned in audio: {sc}",
                    spoken_content=seg.text,
                    command_candidate=sc.strip(),
                    status=TruthClassification.SPOKEN_IN_AUDIO,
                    confidence=seg.confidence
                ))
                step_counter += 1
        elif any(verb in seg.text.lower() for verb in ["install", "clone", "run", "setup", "configure", "open", "deploy", "build"]):
            steps.append(ExtractedStep(
                step_id=step_counter,
                start=seg.start,
                end=seg.end,
                observed_action=f"Action spoken in walkthrough: {seg.text}",
                spoken_content=seg.text,
                command_candidate="",
                status=TruthClassification.SPOKEN_IN_AUDIO,
                confidence=seg.confidence
            ))
            step_counter += 1

    # 3. Analyze visual scenes
    for sc in manifest.scenes:
        steps.append(ExtractedStep(
            step_id=step_counter,
            start=sc.start,
            end=sc.end,
            observed_action=f"Visual transition at {sc.start:.1f}s - {sc.end:.1f}s (keyframe: {Path(sc.keyframe_path).name if sc.keyframe_path else 'none'})",
            spoken_content="",
            command_candidate="",
            status=TruthClassification.OBSERVED_IN_VIDEO,
            confidence=0.85,
            evidence_frames=[sc.keyframe_path] if sc.keyframe_path else []
        ))
        step_counter += 1

    return steps
from pathlib import Path
