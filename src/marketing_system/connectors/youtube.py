from __future__ import annotations

import os
from typing import Any
import requests

from ..constants import Impact
from ..normalization import normalize_youtube_video
from ..credentials import write_credential
from .base import BaseConnector, Capability


class YouTubeConnector(BaseConnector):
    name = "youtube"
    required_env = ("YOUTUBE_API_KEY",)
    optional_env = (
        "YOUTUBE_CHANNEL_ID",
        "YOUTUBE_CLIENT_ID",
        "YOUTUBE_CLIENT_SECRET",
        "YOUTUBE_REFRESH_TOKEN",
        "YOUTUBE_ACCESS_TOKEN",
    )

    def __init__(self, settings):
        super().__init__(settings)
        self._cached_access_token: str | None = None

    @property
    def capabilities(self) -> list[Capability]:
        return [
            Capability(name="read_public_channel_video_metadata", impact=Impact.READ, live_ready=True, cost_semantics="YouTube quota units"),
            Capability(name="create_video_metadata_draft", impact=Impact.DRAFT),
            Capability(
                name="upload_or_update_video",
                impact=Impact.HIGH_IMPACT,
                available_in_mock=True,
                live_ready=True,
                cost_semantics="YouTube quota units",
                note="Direct upload to YouTube channel."
            ),
        ]

    def _get_valid_access_token(self) -> str:
        if self._cached_access_token:
            return self._cached_access_token

        access_token = self.env("YOUTUBE_ACCESS_TOKEN")
        if access_token:
            try:
                check = requests.get(f"https://oauth2.googleapis.com/tokeninfo?access_token={access_token}", timeout=10)
                if check.status_code == 200 and int(check.json().get("expires_in", 0)) > 60:
                    self._cached_access_token = access_token
                    return access_token
            except Exception:
                pass

        refresh_token = self.env("YOUTUBE_REFRESH_TOKEN")
        client_id = self.env("YOUTUBE_CLIENT_ID") or self.env("GOOGLE_DRIVE_CLIENT_ID")
        client_secret = self.env("YOUTUBE_CLIENT_SECRET") or self.env("GOOGLE_DRIVE_CLIENT_SECRET")

        if not refresh_token or not client_id or not client_secret:
            raise RuntimeError("YouTube OAuth credentials missing (YOUTUBE_REFRESH_TOKEN, CLIENT_ID, CLIENT_SECRET).")

        res = requests.post("https://oauth2.googleapis.com/token", data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }, timeout=15)
        res.raise_for_status()
        data = res.json()
        new_token = data["access_token"]
        self._cached_access_token = new_token
        write_credential("YOUTUBE_ACCESS_TOKEN", new_token)
        return new_token

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

    def upload_video(
        self,
        file_path: str,
        title: str,
        description: str = "",
        tags: list[str] | None = None,
        privacy: str = "public"
    ) -> dict[str, Any]:
        """Upload a video file directly to YouTube channel."""
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"Video file not found: {file_path}")

        file_size = os.path.getsize(file_path)
        token = self._get_valid_access_token()

        metadata = {
            "snippet": {
                "title": title[:100],
                "description": description,
                "tags": tags or ["Minh Vân Logistics", "Logistics", "Thủ tục hải quan", "HS Code", "Shorts"],
                "categoryId": "22"
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False
            }
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(file_size)
        }

        init_url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
        res_init = requests.post(init_url, headers=headers, json=metadata, timeout=30)
        res_init.raise_for_status()

        upload_url = res_init.headers.get("Location")
        if not upload_url:
            raise RuntimeError("No upload URL returned from YouTube API")

        with open(file_path, "rb") as f:
            upload_headers = {
                "Content-Type": "video/mp4",
                "Content-Length": str(file_size)
            }
            res_upload = requests.put(upload_url, headers=upload_headers, data=f, timeout=180)
            res_upload.raise_for_status()

        res_data = res_upload.json()
        video_id = res_data["id"]
        video_url = f"https://youtu.be/{video_id}"
        return {
            "channel": "youtube",
            "status": "published",
            "video_id": video_id,
            "video_url": video_url,
            "watch_url": f"https://www.youtube.com/watch?v={video_id}",
            "title": title,
            "privacy": privacy
        }
