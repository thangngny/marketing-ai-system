from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import List, Tuple
from ..models import TranscriptSegment


def extract_audio_from_video(video_path: Path, output_wav: Path, ffmpeg_cmd: str = "ffmpeg") -> bool:
    """Extract 16kHz mono PCM wav from video for transcription and analysis."""
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_cmd,
        "-y",
        "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(output_wav)
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True)
        return output_wav.exists() and output_wav.stat().st_size > 0
    except Exception:
        return False


def parse_vtt_or_srt(sub_file: Path) -> List[TranscriptSegment]:
    """Parse WebVTT or SRT subtitles into structured TranscriptSegment list."""
    segments: List[TranscriptSegment] = []
    content = sub_file.read_text(encoding="utf-8", errors="ignore")

    # Regular expressions for VTT/SRT timestamps: 00:00:01.000 --> 00:00:04.500 or 00:01.000 --> 00:04.500
    time_pattern = re.compile(
        r"(?:(\d{1,2}):)?(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(?:(\d{1,2}):)?(\d{2}):(\d{2})[.,](\d{3})"
    )

    def to_seconds(h, m, s, ms):
        hours = float(h) if h else 0.0
        return hours * 3600.0 + float(m) * 60.0 + float(s) + float(ms) / 1000.0

    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        m = time_pattern.search(line)
        if m:
            start_sec = to_seconds(m.group(1), m.group(2), m.group(3), m.group(4))
            end_sec = to_seconds(m.group(5), m.group(6), m.group(7), m.group(8))
            text_lines = []
            i += 1
            while i < len(lines) and lines[i].strip():
                # Clean html tags like <c> </c> <b> </b>
                cleaned = re.sub(r"<[^>]+>", "", lines[i].strip())
                if cleaned:
                    text_lines.append(cleaned)
                i += 1
            full_text = " ".join(text_lines).strip()
            if full_text:
                segments.append(TranscriptSegment(
                    start=round(start_sec, 2),
                    end=round(end_sec, 2),
                    text=full_text,
                    confidence=0.95,
                    source="auto_caption"
                ))
        i += 1
    return segments


def generate_transcript(
    media_path: Path,
    job_dir: Path,
    sub_files: List[Path] | None = None,
    ffmpeg_cmd: str = "ffmpeg"
) -> Tuple[List[TranscriptSegment], str]:
    """Generate or parse transcript segments from video media.

    Returns:
        (segments, status_note)
    """
    audio_dir = job_dir / "audio"
    audio_wav = audio_dir / "source.wav"
    audio_extracted = extract_audio_from_video(media_path, audio_wav, ffmpeg_cmd)

    # 1. Try downloaded subtitles first
    if sub_files:
        for sf in sub_files:
            if sf.exists() and sf.stat().st_size > 0:
                segments = parse_vtt_or_srt(sf)
                if segments:
                    return segments, "PARSED_FROM_SUBTITLES"

    # Also check if any srt or vtt exists in media dir
    existing_subs = list(job_dir.glob("media/*.vtt")) + list(job_dir.glob("media/*.srt"))
    for sf in existing_subs:
        segments = parse_vtt_or_srt(sf)
        if segments:
            return segments, "PARSED_FROM_SUBTITLES"

    if not audio_extracted:
        return [], "NO_AUDIO_TRACK_DETECTED"

    # 2. Local Whisper Speech-to-Text via whisper.cpp
    model_path = Path(r"C:\Users\Admin\.buzz\models\whisper\ggml-tiny.bin")
    if model_path.exists() and audio_wav.exists():
        try:
            from pywhispercpp.model import Model
            whisper_model = Model(str(model_path))
            raw_segments = whisper_model.transcribe(str(audio_wav))
            parsed: List[TranscriptSegment] = []
            for s in raw_segments:
                txt = s.text.strip()
                if txt:
                    parsed.append(TranscriptSegment(
                        start=round(s.t0 / 100.0, 2),
                        end=round(s.t1 / 100.0, 2),
                        text=txt,
                        confidence=0.90,
                        source="speech"
                    ))
            if parsed:
                return parsed, "TRANSCRIBED_VIA_LOCAL_WHISPER"
        except Exception as e:
            return [], f"WHISPER_ERROR: {str(e)}"

    return [], "AUDIO_EXTRACTED_NO_AUTOMATIC_CAPTIONS"
