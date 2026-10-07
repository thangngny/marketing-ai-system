from __future__ import annotations

import logging
from typing import Any

from ..constants import Impact
from .base import BaseConnector, Capability

logger = logging.getLogger(__name__)

DEFAULT_VIDEO_MODEL = "kling-video/v3.0-turbo/text-to-video"


class HiggsfieldConnector(BaseConnector):
    name = "higgsfield"
    required_env = ("HF_KEY",)
    optional_env = ("HF_API_KEY", "HF_API_SECRET", "HIGGSFIELD_API_KEY")

    @property
    def capabilities(self) -> list[Capability]:
        return [
            Capability(
                name="probe_live",
                impact=Impact.READ,
                live_ready=True,
                cost_semantics="none",
                note="Verifies Higgsfield API credentials and storage endpoints."
            ),
            Capability(
                name="generate_video",
                impact=Impact.DRAFT,
                live_ready=True,
                cost_semantics="Higgsfield balance",
                note="Generates cinematic b-roll video using Kling 3.0 / Wan / LTX models."
            ),
            Capability(
                name="get_request_status",
                impact=Impact.READ,
                live_ready=True,
                cost_semantics="none",
                note="Polls generation request status and output video URL."
            ),
        ]

    def _headers(self) -> dict[str, str]:
        key = self.env("HF_KEY") or self.env("HIGGSFIELD_API_KEY") or ""
        return {
            "Authorization": f"Key {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def probe_live(self) -> tuple[bool, str]:
        try:
            from higgsfield_client import SyncClient
            key = self.env("HF_KEY") or self.env("HIGGSFIELD_API_KEY")
            client = SyncClient(api_key=key)
            r = client._client.post("/files/generate-upload-url", json={"content_type": "image/jpeg"})
            if r.status_code == 200:
                return True, "Higgsfield API live verified (connected to api.higgsfield.ai)"
            return False, f"Higgsfield probe returned HTTP {r.status_code}: {r.text[:200]}"
        except Exception as exc:
            return False, f"Higgsfield probe error: {exc}"

    def read(self, resource: str, **kwargs: Any) -> list[Any]:
        if self.settings.environment.value == "mock":
            return self.mock_search(resource, limit=int(kwargs.get("limit", 3)))
        if resource == "request_status":
            request_id = str(kwargs.get("request_id"))
            res = self.request(
                "GET",
                f"https://api.higgsfield.ai/requests/{request_id}/status",
                headers=self._headers(),
                timeout=15.0,
            )
            res.raise_for_status()
            return [res.json()]
        else:
            raise ValueError(f"Unsupported Higgsfield resource: {resource}")

    def create_video_draft(
        self,
        prompt: str,
        application: str = DEFAULT_VIDEO_MODEL,
        duration: int = 5,
        aspect_ratio: str = "9:16",
    ) -> dict[str, Any]:
        """Submit an asynchronous video generation task."""
        from higgsfield_client import SyncClient
        key = self.env("HF_KEY") or self.env("HIGGSFIELD_API_KEY")
        client = SyncClient(api_key=key)
        
        arguments = {
            "prompt": prompt,
            "duration": duration,
            "aspect_ratio": aspect_ratio,
        }
        controller = client.submit(application=application, arguments=arguments)
        return {
            "request_id": controller.request_id,
            "status_url": controller.status_url,
            "application": application,
        }
