from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Dict, List
from ..models import (
    ExtractedStep,
    FrameMetadata,
    JobManifest,
    SceneInfo,
    TranscriptSegment,
)
from ..security.policy import redact_secrets


def build_manifest(
    job_id: str,
    source_url: str,
    resolver_used: str,
    post_info: Dict[str, Any],
    probe_info: Dict[str, Any],
    transcript: List[TranscriptSegment],
    scenes: List[SceneInfo],
    frames: List[FrameMetadata],
    extracted_steps: List[ExtractedStep],
    warnings: List[str] | None = None
) -> JobManifest:
    """Assemble verified JobManifest object with scrubbed secrets and complete metadata."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    post_text = redact_secrets(post_info.get("description") or post_info.get("title") or "")
    author = post_info.get("uploader") or post_info.get("uploader_id") or "unknown"
    published_at = str(post_info.get("timestamp") or "")

    return JobManifest(
        job_id=job_id,
        source_url=source_url,
        created_at=now_iso,
        resolver_used=resolver_used,
        post_text=post_text,
        author=author,
        published_at=published_at,
        duration_seconds=float(probe_info.get("duration", 0.0)),
        resolution=str(probe_info.get("resolution", "unknown")),
        fps=float(probe_info.get("fps", 0.0)),
        audio_codec=str(probe_info.get("audio_codec", "unknown")),
        video_codec=str(probe_info.get("video_codec", "unknown")),
        video_checksum=str(probe_info.get("checksum", "")),
        transcript=transcript,
        scenes=scenes,
        frames=frames,
        extracted_steps=extracted_steps,
        extraction_warnings=warnings or [],
        status="COMPLETED"
    )
