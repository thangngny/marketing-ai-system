from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Dict


def compute_file_sha256(file_path: Path) -> str:
    """Compute sha256 checksum of a file in chunks."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def probe_media(file_path: Path, ffprobe_cmd: str = "ffprobe") -> Dict[str, Any]:
    """Run ffprobe on a video file to retrieve streams, duration, resolution, codecs, fps."""
    cmd = [
        ffprobe_cmd,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(file_path)
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(proc.stdout)
    except Exception as e:
        # Fallback minimal metadata if ffprobe fails
        return {
            "duration": 0.0,
            "width": 0,
            "height": 0,
            "resolution": "unknown",
            "fps": 0.0,
            "video_codec": "unknown",
            "audio_codec": "unknown",
            "checksum": compute_file_sha256(file_path),
            "error": str(e)
        }

    format_info = data.get("format", {})
    streams = data.get("streams", [])

    duration = float(format_info.get("duration", 0.0))
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    width = int(video_stream.get("width", 0)) if video_stream else 0
    height = int(video_stream.get("height", 0)) if video_stream else 0
    video_codec = video_stream.get("codec_name", "unknown") if video_stream else "none"
    audio_codec = audio_stream.get("codec_name", "unknown") if audio_stream else "none"

    # Compute fps
    fps = 0.0
    if video_stream and "r_frame_rate" in video_stream:
        rate = video_stream["r_frame_rate"]
        if "/" in rate:
            num, den = rate.split("/")
            if float(den) > 0:
                fps = round(float(num) / float(den), 2)
        else:
            fps = float(rate)

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "resolution": f"{width}x{height}" if width and height else "unknown",
        "fps": fps,
        "video_codec": video_codec,
        "audio_codec": audio_codec,
        "checksum": compute_file_sha256(file_path),
        "streams_count": len(streams)
    }
