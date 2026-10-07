"""Stock Footage Manager with Pexels API and local logistics clip library."""

from __future__ import annotations

import logging
import os
import requests
from pathlib import Path
from typing import Any

from ..credentials import read_credential

logger = logging.getLogger(__name__)

PEXELS_API_URL = "https://api.pexels.com/videos/search"
FALLBACK_CLIPS_DIR = Path(r"C:\Users\Admin\marketing-ai-system\data\stock_clips")


class StockFootageManager:
    """Retrieves high-definition stock footage for B-roll scenes."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("PEXELS_API_KEY") or read_credential("PEXELS_API_KEY")

    def search_and_download(
        self,
        query: str,
        output_dir: Path,
        orientation: str = "portrait",
        max_duration: int = 30,
    ) -> Path | None:
        """Search Pexels for stock video and download the best matching MP4."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if not self.api_key:
            logger.info("No PEXELS_API_KEY found, checking local stock footage...")
            return self._find_local_fallback(query)

        headers = {"Authorization": self.api_key}
        params = {
            "query": query,
            "orientation": orientation,
            "per_page": 5,
        }

        try:
            resp = requests.get(PEXELS_API_URL, headers=headers, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                videos = data.get("videos", [])
                for vid in videos:
                    duration = vid.get("duration", 0)
                    if duration <= max_duration:
                        # Find best video file
                        video_files = vid.get("video_files", [])
                        # Prefer HD/Full HD portrait
                        best_file = None
                        for vf in video_files:
                            if vf.get("quality") == "hd" and vf.get("file_type") == "video/mp4":
                                best_file = vf
                                break
                        if not best_file and video_files:
                            best_file = video_files[0]

                        if best_file and best_file.get("link"):
                            download_url = best_file["link"]
                            target_file = output_dir / f"pexels_{vid['id']}.mp4"
                            logger.info("Downloading Pexels clip %s for query '%s'...", vid['id'], query)
                            with requests.get(download_url, stream=True, timeout=30) as r:
                                r.raise_for_status()
                                with open(target_file, "wb") as f:
                                    for chunk in r.iter_content(chunk_size=8192):
                                        f.write(chunk)
                            return target_file
        except Exception as exc:
            logger.warning("Pexels video download failed: %s", exc)

        return self._find_local_fallback(query)

    def _find_local_fallback(self, query: str) -> Path | None:
        """Look for local existing logistics video clips as fallback."""
        candidates = [
            Path(r"C:\Users\Admin\Desktop\demo_video_tiktok_integration.mp4"),
            Path(r"C:\Users\Admin\minhvan-tiktok-demo.mp4"),
            FALLBACK_CLIPS_DIR / "logistics_default.mp4",
        ]
        for c in candidates:
            if c.exists() and c.stat().st_size > 1000:
                return c
        return None
