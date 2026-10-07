from __future__ import annotations

from typing import Any

from ..constants import Impact
from ..credentials import write_credential
from .base import BaseConnector, Capability


class TikTokConnector(BaseConnector):
    name = "tiktok"
    required_env = ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN")
    optional_env = ("TIKTOK_ACCESS_TOKEN", "TIKTOK_OPEN_ID", "TIKTOK_ADVERTISER_ID")

    def __init__(self, settings):
        super().__init__(settings)
        self._cached_access_token: str | None = None

    @property
    def capabilities(self) -> list[Capability]:
        return [
            Capability(name="read_channel_metrics", impact=Impact.READ, live_ready=True),
            Capability(name="read_recent_videos", impact=Impact.READ, live_ready=True),
            Capability(name="upload_video_draft", impact=Impact.DRAFT, available_in_mock=True, live_ready=True,
                       note="Uploads video draft to TikTok inbox."),
            Capability(
                name="publish_video",
                impact=Impact.HIGH_IMPACT,
                available_in_mock=True,
                live_ready=True,
                note="Directly publishes or uploads video to TikTok. Gated by owner approval.",
            ),
        ]

    def _access_token(self, force_refresh: bool = False) -> str:
        if not force_refresh and self._cached_access_token:
            return self._cached_access_token
        if not force_refresh:
            existing = self.env("TIKTOK_ACCESS_TOKEN")
            if existing:
                self._cached_access_token = existing
                return self._cached_access_token

        client_key = self.env("TIKTOK_CLIENT_KEY")
        client_secret = self.env("TIKTOK_CLIENT_SECRET")
        refresh_token = self.env("TIKTOK_REFRESH_TOKEN")

        response = self.request(
            "POST",
            "https://open.tiktokapis.com/v2/oauth/token/",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key": client_key,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=20.0,
        )
        response.raise_for_status()
        body = response.json()
        data = body.get("data") if isinstance(body.get("data"), dict) else body
        if data.get("refresh_token"):
            write_credential("TIKTOK_REFRESH_TOKEN", str(data["refresh_token"]))
        if data.get("access_token"):
            self._cached_access_token = str(data["access_token"])
            write_credential("TIKTOK_ACCESS_TOKEN", self._cached_access_token)
        return self._cached_access_token or ""

    def _authed_request(self, method: str, url: str, **kwargs: Any) -> Any:
        headers = dict(kwargs.pop("headers", {}))
        for attempt in (1, 2):
            token = self._access_token(force_refresh=(attempt == 2))
            headers["Authorization"] = f"Bearer {token}"
            response = self.request(method, url, headers=headers, **kwargs)
            if response.status_code == 401 and attempt == 1:
                self._cached_access_token = None
                continue
            return response
        return response

    def probe_live(self) -> tuple[bool, str]:
        try:
            response = self._authed_request(
                "GET",
                "https://open.tiktokapis.com/v2/user/info/?fields=open_id,display_name,avatar_url",
                timeout=15.0,
            )
            if response.is_success:
                user_data = response.json().get("data", {}).get("user", {})
                name = user_data.get("display_name", "TikTok User")
                return True, f"TikTok /v2/user/info/ probe succeeded for '{name}'."
            return False, f"TikTok probe returned HTTP {response.status_code}."
        except Exception as exc:
            return False, f"TikTok probe error: {exc}"

    def get_channel_metrics(self) -> dict[str, Any]:
        response = self._authed_request(
            "GET",
            "https://open.tiktokapis.com/v2/user/info/?fields=open_id,display_name,avatar_url",
            timeout=15.0,
        )
        response.raise_for_status()
        user = response.json().get("data", {}).get("user", {})
        followers = following = likes = videos = 0
        try:
            stats_resp = self._authed_request(
                "GET",
                "https://open.tiktokapis.com/v2/user/info/?fields=follower_count,following_count,likes_count,video_count",
                timeout=10.0,
            )
            if stats_resp.is_success:
                stats_user = stats_resp.json().get("data", {}).get("user", {})
                followers = int(stats_user.get("follower_count", 0))
                following = int(stats_user.get("following_count", 0))
                likes = int(stats_user.get("likes_count", 0))
                videos = int(stats_user.get("video_count", 0))
        except Exception:
            pass

        return {
            "channel": user.get("display_name"),
            "avatar_url": user.get("avatar_url"),
            "followers": followers,
            "following": following,
            "likes": likes,
            "videos": videos,
        }

    def get_recent_videos(self, limit: int = 10) -> list[dict[str, Any]]:
        response = self._authed_request(
            "POST",
            "https://open.tiktokapis.com/v2/video/list/?fields=id,title,video_description,duration,cover_image_url,embed_link,like_count,comment_count,share_count,view_count",
            headers={"Content-Type": "application/json"},
            json={"max_count": min(limit, 20)},
            timeout=20.0,
        )
        response.raise_for_status()
        videos = response.json().get("data", {}).get("videos", [])
        return [
            {
                "id": v.get("id"),
                "title": v.get("title") or v.get("video_description"),
                "duration": v.get("duration"),
                "cover_url": v.get("cover_image_url"),
                "embed_link": v.get("embed_link"),
                "views": v.get("view_count", 0),
                "likes": v.get("like_count", 0),
                "comments": v.get("comment_count", 0),
                "shares": v.get("share_count", 0),
            }
            for v in videos
        ]


    def read(self, resource: str, **kwargs: Any) -> list[Any]:
        if resource == "recent_videos":
            return self.get_recent_videos(limit=kwargs.get("limit", 10))
        if resource == "metrics":
            return [self.get_channel_metrics()]
        raise ValueError(f"Unsupported TikTok resource: {resource}")

    def upload_video_file(
        self,
        file_path: str,
        title: str = "",
        privacy_level: str = "SELF_ONLY",
        publish_mode: str = "auto",
    ) -> dict[str, Any]:
        """Upload a video file to TikTok.

        - 'inbox': Uploads to creator's TikTok Inbox (Share to TikTok draft).
        - 'direct': Attempts direct publish to account.
        - 'auto': Attempts direct publish; if app is unaudited, automatically falls back to inbox draft.
        """
        from pathlib import Path
        p = Path(file_path)
        if not p.is_file():
            raise FileNotFoundError(f"Video file not found at {file_path}")
        size = p.stat().st_size
        token = self._access_token()
        if not token:
            raise RuntimeError("TikTok access token missing or refresh failed.")

        mode_used = "inbox"
        publish_id = None
        upload_url = None

        if publish_mode in ("direct", "auto"):
            direct_body = {
                "post_info": {
                    "title": title or p.stem,
                    "privacy_level": privacy_level,
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": size,
                    "chunk_size": size,
                    "total_chunk_count": 1,
                },
            }
            try:
                resp = self.request(
                    "POST",
                    "https://open.tiktokapis.com/v2/post/publish/video/init/",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
                    json=direct_body,
                    timeout=20.0,
                )
                if resp.is_success:
                    data = resp.json().get("data", {})
                    publish_id = data.get("publish_id")
                    upload_url = data.get("upload_url")
                    mode_used = "direct_publish"
            except Exception:
                pass

        if not upload_url:
            inbox_body = {
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": size,
                    "chunk_size": size,
                    "total_chunk_count": 1,
                }
            }
            resp = self.request(
                "POST",
                "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
                json=inbox_body,
                timeout=20.0,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            publish_id = data.get("publish_id")
            upload_url = data.get("upload_url")
            mode_used = "inbox_draft"

        if not upload_url:
            raise RuntimeError("Failed to obtain TikTok upload URL.")

        with open(p, "rb") as f:
            content = f.read()

        put_headers = {
            "Content-Range": f"bytes 0-{size - 1}/{size}",
            "Content-Type": "video/mp4",
        }
        put_resp = self.request("PUT", upload_url, content=content, headers=put_headers, timeout=120.0)
        put_resp.raise_for_status()

        status_info = "UPLOADED"
        try:
            status_resp = self.request(
                "POST",
                "https://open.tiktokapis.com/v2/post/publish/status/fetch/",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"publish_id": publish_id},
                timeout=10.0,
            )
            if status_resp.is_success:
                status_info = status_resp.json().get("data", {}).get("status", "UPLOADED")
        except Exception:
            pass

        return {
            "connector": self.name,
            "status": "success",
            "mode": mode_used,
            "publish_id": publish_id,
            "tiktok_status": status_info,
            "file": str(p),
            "size_bytes": size,
            "title": title or p.stem,
        }
