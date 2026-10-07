from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import List
from ..models import SceneInfo


def detect_scenes(
    video_path: Path,
    output_dir: Path,
    threshold: float = 0.3,
    duration: float = 0.0,
    ffmpeg_cmd: str = "ffmpeg"
) -> List[SceneInfo]:
    """Detect visual scene changes and save keyframe representations."""
    scenes_dir = output_dir / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)

    # Use ffmpeg scene filter to log pts_time of scene cuts
    log_file = scenes_dir / "scene_cuts.txt"
    cmd = [
        ffmpeg_cmd,
        "-y",
        "-i", str(video_path),
        "-filter_complex", f"select='gt(scene\\,{threshold})',metadata=print:file='{str(log_file)}'",
        "-f", "null",
        "-"
    ]
    scene_timestamps = [0.0]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        if log_file.exists():
            content = log_file.read_text(encoding="utf-8", errors="ignore")
            for line in content.splitlines():
                if "pts_time:" in line:
                    m = re.search(r"pts_time:([0-9.]+)", line)
                    if m:
                        t = float(m.group(1))
                        if t > scene_timestamps[-1] + 1.0:  # Enforce minimum 1.0s scene separation
                            scene_timestamps.append(round(t, 2))
    except Exception:
        pass

    # Ensure last scene reaches duration
    if duration > 0 and (not scene_timestamps or scene_timestamps[-1] < duration):
        scene_timestamps.append(round(duration, 2))

    scenes: List[SceneInfo] = []
    for idx in range(len(scene_timestamps) - 1):
        s_start = scene_timestamps[idx]
        s_end = scene_timestamps[idx + 1]
        keyframe_time = s_start + min(1.0, (s_end - s_start) / 2.0)
        keyframe_path = scenes_dir / f"scene_{idx:03d}.jpg"

        # Extract representative keyframe
        extract_cmd = [
            ffmpeg_cmd,
            "-y",
            "-ss", str(keyframe_time),
            "-i", str(video_path),
            "-vframes", "1",
            "-q:v", "2",
            str(keyframe_path)
        ]
        try:
            subprocess.run(extract_cmd, capture_output=True, check=True)
        except Exception:
            pass

        scenes.append(SceneInfo(
            scene_id=idx + 1,
            start=s_start,
            end=s_end,
            keyframe_path=str(keyframe_path) if keyframe_path.exists() else "",
            related_transcript="",
            context_hint=f"Scene {idx + 1}: {s_start:.1f}s - {s_end:.1f}s"
        ))

    # If no cuts were detected, create at least 1 default scene
    if not scenes and duration > 0:
        single_kf = scenes_dir / "scene_001.jpg"
        subprocess.run([
            ffmpeg_cmd, "-y", "-ss", "0.5", "-i", str(video_path),
            "-vframes", "1", "-q:v", "2", str(single_kf)
        ], capture_output=True)
        scenes.append(SceneInfo(
            scene_id=1,
            start=0.0,
            end=duration,
            keyframe_path=str(single_kf) if single_kf.exists() else "",
            related_transcript="",
            context_hint=f"Full Demo Scene: 0.0s - {duration:.1f}s"
        ))

    return scenes
