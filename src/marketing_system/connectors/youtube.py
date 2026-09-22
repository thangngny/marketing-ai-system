from __future__ import annotations

from typing import Any

from ..constants import Impact
from ..normalization import normalize_youtube_video
from .base import BaseConnector, Capability


class YouTubeConnector(BaseConnector):
    name = "youtube"
    required_env = ("YOUTUBE_API_KEY",)
    optional_env = ("YOUTUBE_CHANNEL_ID", "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")

    @property
    def capabilities(self) -> list[Capability]:
        return [
            Capability(name="read_public_channel_video_metadata", impact=Impact.READ, live_ready=True, cost_semantics="YouTube quota units"),
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

    def read(self, resource: str, **kwargs: Any) -> list[Any]:
        if self.settings.environment.value == "mock":
            return self.mock_search(resource, limit=int(kwargs.get("limit", 3)))
        if resource != "recent_videos":
            raise ValueError(f"Unsupported YouTube resource: {resource}")
        channel_id = self.env("YOUTUBE_CHANNEL_ID")
        if not channel_id:
            raise RuntimeError("YOUTUBE_CHANNEL_ID is not configured")
        limit = min(max(int(kwargs.get("limit", 5)), 1), 50)
        correlation_id = str(kwargs.get("correlation_id") or "youtube-read")
        response = self.request(
            "GET",
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "channelId": channel_id,
                "order": "date",
                "type": "video",
                "maxResults": limit,
            },
            headers={"x-goog-api-key": self.env("YOUTUBE_API_KEY") or ""},
            timeout=15.0,
        )
        response.raise_for_status()
        return [
            normalize_youtube_video(
                item,
                environment=self.settings.environment,
                correlation_id=correlation_id,
            )
            for item in response.json().get("items", [])
        ]
