from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import List, Optional
from ..models import FrameMetadata


def extract_adaptive_frames(
    video_path: Path,
    output_dir: Path,
    duration: float,
    density: str = "NORMAL",
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
    max_frames: int = 300,
    ffmpeg_cmd: str = "ffmpeg"
) -> List[FrameMetadata]:
    """Adaptive frame extraction respecting density, timeframe, and quality."""
    frames_dir = output_dir / "frames" / "full"
    frames_dir.mkdir(parents=True, exist_ok=True)

    start = max(0.0, start_time or 0.0)
    end = min(duration, end_time or duration) if duration > 0 else (end_time or 60.0)

    # Calculate fps rate according to density
    density_map = {
        "LOW": 0.5,
        "NORMAL": 1.0,
        "HIGH": 2.0,
        "ULTRA": 4.0
    }
    fps = density_map.get(density.upper(), 1.0)

    # Determine frame timestamps
    timestamps: List[float] = []
    curr = start
    step = 1.0 / fps
    while curr <= end and len(timestamps) < max_frames:
        timestamps.append(round(curr, 2))
        curr += step

    frames: List[FrameMetadata] = []
    for idx, ts in enumerate(timestamps):
        frame_filename = f"frame_{idx:04d}_{ts:.2f}s.jpg"
        frame_path = frames_dir / frame_filename

        # If already extracted, skip re-extracting
        if not frame_path.exists():
            cmd = [
                ffmpeg_cmd,
                "-y",
                "-ss", str(ts),
                "-i", str(video_path),
                "-vframes", "1",
                "-q:v", "2",
                str(frame_path)
            ]
            try:
                subprocess.run(cmd, capture_output=True, check=True)
            except Exception:
                continue

        if frame_path.exists():
            frames.append(FrameMetadata(
                frame_index=idx + 1,
                timestamp=ts,
                path=str(frame_path),
                kind="baseline" if fps <= 1.0 else "high_density",
                category="general"
            ))

    return frames
