"""Dynamic Kinetic Subtitle Generator for TikTok, Shorts & Reels."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BUZZ_TRANSCRIBE_PY = Path(r"C:\Users\Admin\.buzz\tools\transcribe\buzz_transcribe.py")
BUZZ_PYTHON = Path(r"C:\Users\Admin\.buzz\tools\transcribe\.venv\Scripts\python.exe")


def format_ass_time(seconds: float) -> str:
    """Format seconds into ASS timestamp: H:MM:SS.cc"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


class SubtitleGenerator:
    """Generates high-retention, stylish kinetic subtitles for vertical short-form video."""

    def __init__(self, font_name: str = "Arial Black", font_size: int = 50):
        self.font_name = font_name
        self.font_size = font_size

    def extract_timestamps(self, audio_path: Path, script_fallback: str = "") -> list[dict[str, Any]]:
        """Run Whisper or heuristic alignment to get word/segment timestamps."""
        audio_path = Path(audio_path)
        if not audio_path.exists():
            return self._heuristic_timestamps(script_fallback, duration=15.0)

        # 1. Try buzz_transcribe if present
        if BUZZ_PYTHON.exists() and BUZZ_TRANSCRIBE_PY.exists():
            try:
                cmd = [
                    str(BUZZ_PYTHON),
                    str(BUZZ_TRANSCRIBE_PY),
                    str(audio_path),
                    "--json",
                    "-l", "vi",
                    "-q"
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90, encoding="utf-8")
                if proc.returncode == 0 and proc.stdout.strip():
                    data = json.loads(proc.stdout)
                    segments = data.get("segments", [])
                    if segments:
                        parsed = []
                        for s in segments:
                            parsed.append({
                                "start": float(s.get("start", 0)),
                                "end": float(s.get("end", 0)),
                                "text": s.get("text", "").strip()
                            })
                        if parsed:
                            return self._chunk_segments(parsed)
            except Exception as exc:
                logger.warning("buzz_transcribe execution failed: %s; falling back to audio duration probe", exc)

        # 2. Probe audio duration with ffprobe and compute proportional alignment
        duration = self._probe_audio_duration(audio_path)
        return self._heuristic_timestamps(script_fallback, duration=duration)

    def _probe_audio_duration(self, audio_path: Path) -> float:
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path)
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0 and res.stdout.strip():
                return float(res.stdout.strip())
        except Exception:
            pass
        return 20.0

    def _heuristic_timestamps(self, script: str, duration: float) -> list[dict[str, Any]]:
        """Generate evenly spaced, energetic chunks of 3-5 words based on total audio duration."""
        words = [w for w in re.split(r"\s+", script.strip()) if w]
        if not words:
            return []

        # Group words into chunks of 3-4 words
        chunk_size = 4
        chunks = [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]
        total_chunks = len(chunks)
        time_per_chunk = max(0.8, duration / total_chunks)

        results = []
        for i, chunk in enumerate(chunks):
            start = i * time_per_chunk
            end = min(duration, (i + 1) * time_per_chunk)
            results.append({"start": start, "end": end, "text": chunk.upper()})
        return results

    def _chunk_segments(self, segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Break down long Whisper segments into short 2-4 word kinetic bursts."""
        fine_chunks = []
        for seg in segments:
            text = seg["text"].strip()
            start = seg["start"]
            end = seg["end"]
            duration = max(0.5, end - start)
            words = text.split()
            if len(words) <= 4:
                fine_chunks.append({"start": start, "end": end, "text": text.upper()})
                continue

            chunk_size = 3
            groups = [words[i:i + chunk_size] for i in range(0, len(words), chunk_size)]
            step = duration / len(groups)
            for idx, g in enumerate(groups):
                c_start = start + idx * step
                c_end = start + (idx + 1) * step
                fine_chunks.append({"start": c_start, "end": c_end, "text": " ".join(g).upper()})
        return fine_chunks

    def generate_ass(
        self,
        cues: list[dict[str, Any]],
        output_file: Path,
        width: int = 1080,
        height: int = 1920,
        margin_v: int = 340,
    ) -> Path:
        """Write ASS subtitle file styled for maximum mobile retention."""
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TikTokYellow,{self.font_name},{self.font_size},&H0000FFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,5,3,2,60,60,{margin_v},1
Style: TikTokWhite,{self.font_name},{self.font_size},&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,5,3,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        dialogues = []
        for i, cue in enumerate(cues):
            start = format_ass_time(cue["start"])
            end = format_ass_time(cue["end"])
            text = cue["text"].replace("\\", "").replace("\n", " ")
            # Alternate or highlight keywords
            style = "TikTokYellow" if i % 2 == 0 else "TikTokWhite"
            dialogues.append(f"Dialogue: 0,{start},{end},{style},,0,0,0,,{text}")

        content = header + "\n".join(dialogues) + "\n"
        output_file.write_text(content, encoding="utf-8")
        return output_file
