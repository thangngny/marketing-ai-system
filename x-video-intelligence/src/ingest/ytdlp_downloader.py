from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import yt_dlp


def download_with_ytdlp(url: str, output_dir: Path) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """Download video and metadata using yt-dlp.

    Returns:
        (success, metadata_dict, error_or_warning)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    video_output_template = str(output_dir / "source.%(ext)s")

    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": video_output_template,
        "writeinfojson": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "vi"],
        "subtitlesformat": "srt/vtt/json3",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 3,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return False, None, "VIDEO_NOT_FOUND"

            # Check if actual media file exists
            source_file = None
            for p in output_dir.glob("source.*"):
                if p.suffix.lower() in [".mp4", ".mkv", ".webm", ".mov", ".m4v"]:
                    source_file = p
                    break

            if not source_file:
                # Post might be text-only
                return False, {
                    "title": info.get("title", ""),
                    "description": info.get("description", ""),
                    "uploader": info.get("uploader", ""),
                    "timestamp": info.get("timestamp"),
                }, "NO_VIDEO_IN_POST"

            # Check for downloaded subtitle files
            sub_files = list(output_dir.glob("source*.vtt")) + list(output_dir.glob("source*.srt"))

            return True, {
                "title": info.get("title", ""),
                "description": info.get("description", ""),
                "uploader": info.get("uploader", ""),
                "uploader_id": info.get("uploader_id", ""),
                "timestamp": info.get("timestamp"),
                "duration": info.get("duration", 0.0),
                "media_path": str(source_file),
                "subtitles": [str(s) for s in sub_files],
                "webpage_url": info.get("webpage_url", url),
            }, ""

    except yt_dlp.utils.DownloadError as e:
        err_msg = str(e).lower()
        if "login" in err_msg or "private" in err_msg or "auth" in err_msg:
            return False, None, "BLOCKED_BY_AUTH"
        elif "unsupported url" in err_msg or "not a valid url" in err_msg:
            return False, None, "INVALID_URL"
        elif "no video" in err_msg or "not found" in err_msg:
            return False, None, "VIDEO_NOT_FOUND"
        else:
            return False, None, f"DOWNLOAD_ERROR: {str(e)}"
    except Exception as e:
        return False, None, f"UNEXPECTED_ERROR: {str(e)}"
