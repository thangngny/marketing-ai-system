from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from mcp.server.mcpserver import MCPServer

# Relative imports or package imports
import sys
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.config import load_config
from src.evidence.package import EvidencePackage
from src.frames.extractor import extract_adaptive_frames
from src.ingest.resolver import VideoIngestService
from src.models import ExecutionMode

config = load_config()
ingest_service = VideoIngestService(config)

server = MCPServer(
    "x-video-intelligence",
    title="X Video Intelligence",
    description="Multimodal X video ingestion, frame extraction, transcription, and demo reproduction layer.",
    version="1.0.0",
)


@server.tool()
def x_video_ingest(
    url: str,
    force_refresh: bool = False,
    preferred_language: str = "auto",
    auth_mode: str = "auto"
) -> Dict[str, Any]:
    """Ingest an X/Twitter post containing a video, download media, extract audio/transcript and baseline frames."""
    res = ingest_service.ingest_url(url, force_refresh, preferred_language, auth_mode)
    return res.model_dump()


@server.tool()
def x_video_ingest_file(
    file_path: str,
    title: str = "",
    description: str = ""
) -> Dict[str, Any]:
    """Fallback: Ingest a locally provided video file when X URL download requires login or fails."""
    res = ingest_service.ingest_file(file_path, title, description)
    return res.model_dump()


@server.tool()
def x_video_manifest(job_id: str) -> Dict[str, Any]:
    """Get the full manifest of an ingested video job including duration, resolution, transcript, scenes, and extracted steps."""
    job_dir = config.data_dir / job_id
    pkg = EvidencePackage(job_dir)
    manifest = pkg.load_manifest()
    if not manifest:
        return {"error": "JOB_NOT_FOUND", "job_id": job_id}
    return manifest.model_dump()


@server.tool()
def x_video_transcript(
    job_id: str,
    start: Optional[float] = None,
    end: Optional[float] = None
) -> Dict[str, Any]:
    """Get timestamped transcript segments for a video job, optionally filtered by timeframe (start, end in seconds)."""
    job_dir = config.data_dir / job_id
    pkg = EvidencePackage(job_dir)
    manifest = pkg.load_manifest()
    if not manifest:
        return {"error": "JOB_NOT_FOUND", "job_id": job_id}

    segments = manifest.transcript
    if start is not None or end is not None:
        s_min = start if start is not None else 0.0
        s_max = end if end is not None else float("inf")
        segments = [s for s in segments if s.start >= s_min and s.end <= s_max]

    return {
        "job_id": job_id,
        "segments": [s.model_dump() for s in segments],
        "count": len(segments)
    }


@server.tool()
def x_video_frames(
    job_id: str,
    start: Optional[float] = None,
    end: Optional[float] = None,
    density: str = "NORMAL"
) -> Dict[str, Any]:
    """Get extracted frame file paths for visual inspection by Codex. Density options: LOW, NORMAL, HIGH, ULTRA."""
    job_dir = config.data_dir / job_id
    pkg = EvidencePackage(job_dir)
    manifest = pkg.load_manifest()
    if not manifest:
        return {"error": "JOB_NOT_FOUND", "job_id": job_id}

    # If higher density or specific timeframe requested that isn't yet extracted, run extractor
    source_media = next(pkg.media_dir.glob("source.*"), None)
    if density.upper() in ["HIGH", "ULTRA"] and source_media:
        new_frames = extract_adaptive_frames(
            source_media, job_dir, manifest.duration_seconds, density.upper(),
            start_time=start, end_time=end, ffmpeg_cmd=config.ffmpeg_path
        )
        return {
            "job_id": job_id,
            "density": density.upper(),
            "frames": [f.model_dump() for f in new_frames],
            "count": len(new_frames)
        }

    frames = manifest.frames
    if start is not None or end is not None:
        s_min = start if start is not None else 0.0
        s_max = end if end is not None else float("inf")
        frames = [f for f in frames if f.timestamp >= s_min and f.timestamp <= s_max]

    return {
        "job_id": job_id,
        "density": density,
        "frames": [f.model_dump() for f in frames],
        "count": len(frames)
    }


@server.tool()
def x_video_scene(job_id: str, scene_id: int) -> Dict[str, Any]:
    """Get details of a specific scene, including keyframe path, timeframe, and related context."""
    job_dir = config.data_dir / job_id
    pkg = EvidencePackage(job_dir)
    manifest = pkg.load_manifest()
    if not manifest:
        return {"error": "JOB_NOT_FOUND", "job_id": job_id}

    scene = next((s for s in manifest.scenes if s.scene_id == scene_id), None)
    if not scene:
        return {"error": "SCENE_NOT_FOUND", "job_id": job_id, "scene_id": scene_id}

    return scene.model_dump()


@server.tool()
def x_video_reproduce_plan(
    job_id: str,
    target_os: str = "windows",
    mode: str = "PLAN_ONLY"
) -> Dict[str, Any]:
    """Get or regenerate the reproduction plan with OS translations, version verifications, and risk assessment."""
    job_dir = config.data_dir / job_id
    pkg = EvidencePackage(job_dir)
    manifest = pkg.load_manifest()
    if not manifest:
        return {"error": "JOB_NOT_FOUND", "job_id": job_id}

    plan = pkg.load_plan()
    if not plan or plan.target_os != target_os or plan.mode.value != mode:
        from src.analysis.verifier import build_reproduction_plan
        plan = build_reproduction_plan(manifest, target_os=target_os, mode=ExecutionMode(mode))
        pkg.save_plan(plan)
        pkg.generate_user_report(manifest, plan)

    return plan.model_dump()


@server.tool()
def x_video_cleanup(job_id: str) -> Dict[str, Any]:
    """Clean up job cache/temporary files according to retention policy."""
    job_dir = config.data_dir / job_id
    if not job_dir.exists():
        return {"status": "NOT_FOUND", "job_id": job_id}

    import shutil
    shutil.rmtree(job_dir, ignore_errors=True)
    return {"status": "DELETED", "job_id": job_id}


def main():
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
