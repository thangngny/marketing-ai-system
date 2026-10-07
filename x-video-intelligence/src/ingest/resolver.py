from __future__ import annotations

import shutil
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from ..config import Config, load_config
from ..evidence.package import EvidencePackage, make_job_id
from ..frames.extractor import extract_adaptive_frames
from ..manifest.builder import build_manifest
from ..media.probe import probe_media
from ..models import (
    IngestResult,
    IngestionResolver,
    JobManifest,
    ReproductionPlan,
)
from ..scenes.detector import detect_scenes
from ..transcript.engine import generate_transcript
from ..analysis.demo_analyzer import extract_steps_from_multimodal_evidence
from ..analysis.verifier import build_reproduction_plan
from .browser_fallback import extract_via_browser_fallback
from .x_api import fetch_via_x_api
from .ytdlp_downloader import download_with_ytdlp

_JOB_LOCKS: Dict[str, threading.Lock] = {}
_GLOBAL_LOCK = threading.Lock()


def get_job_lock(job_id: str) -> threading.Lock:
    with _GLOBAL_LOCK:
        if job_id not in _JOB_LOCKS:
            _JOB_LOCKS[job_id] = threading.Lock()
        return _JOB_LOCKS[job_id]


class VideoIngestService:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or load_config()

    def ingest_url(
        self,
        url: str,
        force_refresh: bool = False,
        preferred_language: str = "auto",
        auth_mode: str = "auto"
    ) -> IngestResult:
        """Full layered ingestion: Layer 1 X API -> Layer 2 yt-dlp -> Layer 3 Browser -> Manual File."""
        job_id = make_job_id(url)
        job_dir = self.config.data_dir / job_id
        pkg = EvidencePackage(job_dir)

        lock = get_job_lock(job_id)
        with lock:
            # Check cache
            if not force_refresh:
                cached_manifest = pkg.load_manifest()
                if cached_manifest:
                    return IngestResult(
                        job_id=job_id,
                        source_url=url,
                        post_text=cached_manifest.post_text,
                        author=cached_manifest.author,
                        published_at=cached_manifest.published_at,
                        duration=cached_manifest.duration_seconds,
                        resolver_used=IngestionResolver(cached_manifest.resolver_used),
                        media_status="CACHED",
                        transcript_status="CACHED",
                        frame_status="CACHED",
                        manifest_path=str(pkg.manifest_file),
                        warnings=["Reused existing cached evidence package."]
                    )

            # Layer 1: X API
            post_info: Dict[str, Any] = {}
            resolver_used = IngestionResolver.X_API
            x_api_res = fetch_via_x_api(url)
            if x_api_res:
                post_info = x_api_res

            # Layer 2: yt-dlp
            media_downloaded = False
            ytdlp_err = ""
            if not media_downloaded:
                success, yt_meta, ytdlp_err = download_with_ytdlp(url, pkg.media_dir)
                if success and yt_meta:
                    media_downloaded = True
                    resolver_used = IngestionResolver.YTDLP
                    post_info.update(yt_meta)

            # Layer 3: Browser Fallback
            if not media_downloaded and ytdlp_err == "BLOCKED_BY_AUTH":
                b_success, b_meta, b_err = extract_via_browser_fallback(url, pkg.media_dir)
                if b_success and b_meta:
                    media_downloaded = True
                    resolver_used = IngestionResolver.BROWSER
                    post_info.update(b_meta)
                else:
                    return IngestResult(
                        job_id=job_id,
                        source_url=url,
                        resolver_used=IngestionResolver.MANUAL_FILE_REQUIRED,
                        media_status="BLOCKED_BY_AUTH",
                        transcript_status="PENDING",
                        frame_status="PENDING",
                        manifest_path="",
                        warnings=[f"Access requires login or authorized browser session: {b_err}"]
                    )

            if not media_downloaded:
                return IngestResult(
                    job_id=job_id,
                    source_url=url,
                    resolver_used=IngestionResolver.MANUAL_FILE_REQUIRED,
                    media_status="FAILED",
                    transcript_status="SKIPPED",
                    frame_status="SKIPPED",
                    manifest_path="",
                    warnings=[f"Media download failed: {ytdlp_err}. Provide video file directly via x_video_ingest_file."]
                )

            # Locate source media file
            media_file = None
            for f in pkg.media_dir.glob("source.*"):
                if f.suffix.lower() in [".mp4", ".mkv", ".webm", ".mov", ".m4v"]:
                    media_file = f
                    break

            if not media_file:
                return IngestResult(
                    job_id=job_id,
                    source_url=url,
                    resolver_used=resolver_used,
                    media_status="NO_MEDIA_FOUND",
                    transcript_status="SKIPPED",
                    frame_status="SKIPPED",
                    manifest_path="",
                    warnings=["No playable video stream found in extracted post."]
                )

            # Probe media
            probe_info = probe_media(media_file, self.config.ffprobe_path)
            duration = probe_info.get("duration", 0.0)

            # Extract audio & transcript
            sub_files = [Path(s) for s in post_info.get("subtitles", [])]
            transcript_segs, t_status = generate_transcript(
                media_file, job_dir, sub_files, self.config.ffmpeg_path
            )

            # Extract scenes
            scenes = detect_scenes(
                media_file, job_dir, self.config.scene_threshold, duration, self.config.ffmpeg_path
            )

            # Extract baseline & adaptive frames
            frames = extract_adaptive_frames(
                media_file, job_dir, duration, "NORMAL", max_frames=self.config.max_frames_per_job, ffmpeg_cmd=self.config.ffmpeg_path
            )

            # Assemble manifest
            manifest = build_manifest(
                job_id=job_id,
                source_url=url,
                resolver_used=resolver_used.value,
                post_info=post_info,
                probe_info=probe_info,
                transcript=transcript_segs,
                scenes=scenes,
                frames=frames,
                extracted_steps=[],
                warnings=[]
            )

            # Extract steps and create plan
            manifest.extracted_steps = extract_steps_from_multimodal_evidence(manifest)
            pkg.save_manifest(manifest)

            plan = build_reproduction_plan(manifest, target_os="windows", mode=self.config.default_mode)
            pkg.save_plan(plan)
            pkg.generate_user_report(manifest, plan)

            return IngestResult(
                job_id=job_id,
                source_url=url,
                post_text=manifest.post_text,
                author=manifest.author,
                published_at=manifest.published_at,
                duration=manifest.duration_seconds,
                resolver_used=resolver_used,
                media_status="INGESTED",
                transcript_status=t_status,
                frame_status=f"EXTRACTED_{len(frames)}_FRAMES",
                manifest_path=str(pkg.manifest_file),
                warnings=[]
            )

    def ingest_file(
        self,
        file_path: Path | str,
        title: str = "",
        description: str = ""
    ) -> IngestResult:
        """Direct file fallback ingestion for user-provided video files."""
        src_path = Path(file_path)
        if not src_path.exists():
            return IngestResult(
                job_id="",
                source_url=str(file_path),
                resolver_used=IngestionResolver.MANUAL_FILE_REQUIRED,
                media_status="FILE_NOT_FOUND",
                transcript_status="SKIPPED",
                frame_status="SKIPPED",
                manifest_path="",
                warnings=[f"Specified file does not exist: {file_path}"]
            )

        job_id = make_job_id(str(src_path.name))
        job_dir = self.config.data_dir / job_id
        pkg = EvidencePackage(job_dir)

        lock = get_job_lock(job_id)
        with lock:
            # Copy file to media/source.<ext>
            target_media = pkg.media_dir / f"source{src_path.suffix.lower()}"
            shutil.copy2(src_path, target_media)

            probe_info = probe_media(target_media, self.config.ffprobe_path)
            duration = probe_info.get("duration", 0.0)

            post_info = {
                "title": title or src_path.stem,
                "description": description or f"Local media upload: {src_path.name}",
                "uploader": "local_user",
                "subtitles": []
            }

            transcript_segs, t_status = generate_transcript(
                target_media, job_dir, [], self.config.ffmpeg_path
            )

            scenes = detect_scenes(
                target_media, job_dir, self.config.scene_threshold, duration, self.config.ffmpeg_path
            )

            frames = extract_adaptive_frames(
                target_media, job_dir, duration, "NORMAL", max_frames=self.config.max_frames_per_job, ffmpeg_cmd=self.config.ffmpeg_path
            )

            manifest = build_manifest(
                job_id=job_id,
                source_url=f"file:///{src_path.resolve()}",
                resolver_used=IngestionResolver.MANUAL_FILE_REQUIRED.value,
                post_info=post_info,
                probe_info=probe_info,
                transcript=transcript_segs,
                scenes=scenes,
                frames=frames,
                extracted_steps=[],
                warnings=[]
            )

            manifest.extracted_steps = extract_steps_from_multimodal_evidence(manifest)
            pkg.save_manifest(manifest)

            plan = build_reproduction_plan(manifest, target_os="windows", mode=self.config.default_mode)
            pkg.save_plan(plan)
            pkg.generate_user_report(manifest, plan)

            return IngestResult(
                job_id=job_id,
                source_url=f"file:///{src_path.resolve()}",
                post_text=manifest.post_text,
                author=manifest.author,
                published_at=manifest.published_at,
                duration=manifest.duration_seconds,
                resolver_used=IngestionResolver.MANUAL_FILE_REQUIRED,
                media_status="INGESTED",
                transcript_status=t_status,
                frame_status=f"EXTRACTED_{len(frames)}_FRAMES",
                manifest_path=str(pkg.manifest_file),
                warnings=[]
            )
