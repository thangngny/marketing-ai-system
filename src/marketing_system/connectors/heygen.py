from __future__ import annotations

import logging
from typing import Any

from ..constants import Impact
from .base import BaseConnector, Capability

logger = logging.getLogger(__name__)


class HeyGenConnector(BaseConnector):
    name = "heygen"
    required_env = ("HEYGEN_API_KEY",)
    optional_env = ("HEYGEN_AVATAR_ID", "HEYGEN_VOICE_ID")

    @property
    def capabilities(self) -> list[Capability]:
        return [
            Capability(
                name="get_account_info",
                impact=Impact.READ,
                live_ready=True,
                cost_semantics="none",
                note="Returns user profile, wallet balance, and quota details."
            ),
            Capability(
                name="list_avatars",
                impact=Impact.READ,
                live_ready=True,
                cost_semantics="none",
                note="List available avatars including Lina and stock avatars."
            ),
            Capability(
                name="list_voices",
                impact=Impact.READ,
                live_ready=True,
                cost_semantics="none",
                note="List Vietnamese voices."
            ),
            Capability(
                name="create_video",
                impact=Impact.DRAFT,
                live_ready=True,
                cost_semantics="HeyGen credits",
                note="Generate avatar video in 9:16 or 16:9 format with custom background."
            ),
            Capability(
                name="get_video_status",
                impact=Impact.READ,
                live_ready=True,
                cost_semantics="none",
                note="Poll video rendering progress and retrieve video URL."
            ),
        ]

    def _headers(self) -> dict[str, str]:
        key = self.env("HEYGEN_API_KEY") or ""
        return {
            "x-api-key": key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def probe_live(self) -> tuple[bool, str]:
        response = self.request(
            "GET",
            "https://api.heygen.com/v3/users/me",
            headers=self._headers(),
            timeout=15.0,
        )
        if response.is_success:
            data = response.json().get("data", {})
            email = data.get("email", "unknown")
            return True, f"HeyGen live verified (account: {email})"
        return False, f"HeyGen probe failed with HTTP {response.status_code}: {response.text[:200]}"

    def read(self, resource: str, **kwargs: Any) -> list[Any]:
        if self.settings.environment.value == "mock":
            return self.mock_search(resource, limit=int(kwargs.get("limit", 3)))
        if resource == "avatars":
            limit = min(max(int(kwargs.get("limit", 10)), 1), 50)
            res = self.request(
                "GET",
                f"https://api.heygen.com/v3/avatars?limit={limit}",
                headers=self._headers(),
                timeout=20.0,
            )
            res.raise_for_status()
            return res.json().get("data", [])
        elif resource == "voices":
            lang = str(kwargs.get("language", "Vietnamese")).lower()
            res = self.request(
                "GET",
                "https://api.heygen.com/v2/voices",
                headers=self._headers(),
                timeout=25.0,
            )
            res.raise_for_status()
            all_voices = res.json().get("data", {}).get("voices", [])
            if lang and lang != "all":
                return [v for v in all_voices if v.get("language", "").lower() == lang]
            return all_voices
        elif resource == "video_status":
            video_id = str(kwargs.get("video_id"))
            res = self.request(
                "GET",
                f"https://api.heygen.com/v3/videos/{video_id}",
                headers=self._headers(),
                timeout=15.0,
            )
            res.raise_for_status()
            return [res.json().get("data", {})]
        else:
            raise ValueError(f"Unsupported HeyGen resource: {resource}")

    def create_video_draft(
        self,
        script: str,
        avatar_id: str = "f9f270fb70a84c669572001ef3aaee17",
        voice_id: str = "6acea87b5a0b45268e410b84a0aef7a1",
        aspect_ratio: str = "9:16",
        background_color: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Generate an avatar video via HeyGen v3 API."""
        payload: dict[str, Any] = {
            "type": "avatar",
            "avatar_id": avatar_id,
            "voice_id": voice_id,
            "script": script,
            "aspect_ratio": aspect_ratio,
            "title": title or f"Minh Van - {script[:30]}",
        }
        if background_color:
            payload["background"] = {
                "type": "color",
                "value": background_color,
            }

        res = self.request(
            "POST",
            "https://api.heygen.com/v3/videos",
            headers=self._headers(),
            json=payload,
            timeout=30.0,
        )
        res.raise_for_status()
        return res.json().get("data", {})

