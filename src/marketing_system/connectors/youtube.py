from __future__ import annotations

from ..constants import Impact
from .base import BaseConnector, Capability


class YouTubeConnector(BaseConnector):
    name = "youtube"
    required_env = ("YOUTUBE_API_KEY",)
    optional_env = ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")

    @property
    def capabilities(self) -> list[Capability]:
        return [
            Capability(name="read_public_channel_video_metadata", impact=Impact.READ, cost_semantics="YouTube quota units"),
            Capability(name="create_video_metadata_draft", impact=Impact.DRAFT),
            Capability(name="upload_or_update_video", impact=Impact.HIGH_IMPACT, available_in_mock=False, cost_semantics="YouTube quota units", note="Disabled in Phase 1."),
        ]

    def probe_live(self) -> tuple[bool, str]:
        response = self.request(
            "GET",
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "id", "chart": "mostPopular", "maxResults": 1},
            headers={"x-goog-api-key": self.env("YOUTUBE_API_KEY") or ""},
            timeout=15.0,
        )
        return response.is_success, f"YouTube read-only probe returned HTTP {response.status_code} and consumed quota."
