from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

from src.models.types import ExternalLink, MediaItem, MediaType

logger = logging.getLogger("x_context.media_router")


class MediaRouter:
    """
    Handles media dispatch:
    - Delegates video processing directly to verified x-video-intelligence via isolated runner
    - Handles images, dimensions, downloads cache
    - Resolves external URLs and extracts metadata / GitHub repo details
    """

    def __init__(self, x_video_dir: Path, data_dir: Path):
        self.x_video_dir = x_video_dir
        self.data_dir = data_dir

    def process_video_item(self, media_item: MediaItem, post_url: str) -> MediaItem:
        """Delegate video media processing to x-video-intelligence in an isolated sub-runner."""
        target_url = media_item.url or post_url
        logger.info(f"Delegating video ingestion to x-video-intelligence for {target_url}")

        worker_script = f"""
import sys, json
sys.path.insert(0, r"{self.x_video_dir}")
from src.config import load_config
from src.ingest.resolver import VideoIngestService

try:
    svc = VideoIngestService(load_config())
    res = svc.ingest_url({repr(target_url)})
    print("###JSON_RESULT###" + json.dumps(res.model_dump()))
except Exception as e:
    print("###JSON_ERROR###" + str(e), file=sys.stderr)
    sys.exit(1)
"""
        try:
            proc = subprocess.run(
                [sys.executable, "-c", worker_script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=120,
            )
            if proc.returncode != 0:
                logger.warning(f"Video worker exited with code {proc.returncode}: {proc.stderr}")
                media_item.summary = f"Video ingestion failed: {proc.stderr[:100]}"
                return media_item

            stdout = proc.stdout
            if "###JSON_RESULT###" in stdout:
                raw_json = stdout.split("###JSON_RESULT###")[1].strip()
                res_data = json.loads(raw_json)
                media_item.video_job_id = res_data.get("job_id")
                media_item.duration_seconds = res_data.get("duration")

                # Read full JobManifest from manifest_path
                manifest_path_str = res_data.get("manifest_path")
                if manifest_path_str and Path(manifest_path_str).exists():
                    with open(manifest_path_str, "r", encoding="utf-8") as f:
                        job_manifest = json.load(f)

                    res_str = job_manifest.get("resolution", "")
                    if "x" in res_str:
                        parts = res_str.split("x")
                        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                            media_item.width = int(parts[0])
                            media_item.height = int(parts[1])

                    transcript = job_manifest.get("transcript", [])
                    if transcript:
                        transcript_text = " ".join([s.get("text", "") for s in transcript if s.get("text")])
                        media_item.transcription_text = transcript_text
                        media_item.summary = f"Video transcribed: {len(transcript)} segments. Duration: {media_item.duration_seconds:.1f}s."

                    media_file = Path(manifest_path_str).parent / "media.mp4"
                    if media_file.exists():
                        media_item.local_path = str(media_file)

                logger.info(f"Successfully delegated video. Job ID: {media_item.video_job_id} ({media_item.width}x{media_item.height})")
            else:
                media_item.summary = "No JSON result received from video worker"

            return media_item
        except Exception as e:
            logger.error(f"Error executing video worker subprocess: {e}")
            media_item.summary = f"Video ingestion failed: {e}"
            return media_item

    def resolve_external_link(self, link_url: str) -> ExternalLink:
        """Fetch title, description, and status code for an external link."""
        parsed = urlparse(link_url)
        domain = parsed.netloc.lower()
        link_obj = ExternalLink(url=link_url, domain=domain)

        # Check for GitHub link
        if "github.com" in domain:
            parts = [p for p in parsed.path.strip("/").split("/") if p]
            if len(parts) >= 2:
                owner, repo = parts[0], parts[1].replace(".git", "")
                link_obj.repo_info = {
                    "owner": owner,
                    "repo": repo,
                    "full_name": f"{owner}/{repo}",
                    "api_url": f"https://api.github.com/repos/{owner}/{repo}",
                }

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            resp = requests.get(link_url, headers=headers, timeout=8, allow_redirects=True)
            link_obj.resolved = True
            link_obj.http_status = resp.status_code
            link_obj.expanded_url = resp.url

            if resp.status_code == 200 and "text/html" in resp.headers.get("Content-Type", ""):
                soup = BeautifulSoup(resp.text[:50000], "html.parser")
                title_tag = soup.find("title")
                if title_tag and title_tag.string:
                    link_obj.title = title_tag.string.strip()
                desc_tag = soup.find("meta", attrs={"name": "description"}) or soup.find(
                    "meta", attrs={"property": "og:description"}
                )
                if desc_tag and desc_tag.get("content"):
                    link_obj.description = desc_tag["content"].strip()
        except Exception as e:
            logger.debug(f"Failed to fetch metadata for link {link_url}: {e}")
            link_obj.resolved = False

        return link_obj
