from __future__ import annotations

import logging
from typing import Any

from ..constants import Impact
from .base import BaseConnector, Capability

logger = logging.getLogger(__name__)

DEFAULT_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"  # Sarah - Mature, Reassuring
DEFAULT_MODEL_ID = "eleven_v4"  # Eleven v4 flagship model (90+ languages, emotional audio tags)


class ElevenLabsConnector(BaseConnector):
    name = "elevenlabs"
    required_env = ("ELEVENLABS_API_KEY",)
    optional_env = ("ELEVENLABS_VOICE_ID", "ELEVENLABS_MODEL_ID")

    @property
    def capabilities(self) -> list[Capability]:
        return [
            Capability(
                name="get_user_info",
                impact=Impact.READ,
                live_ready=True,
                cost_semantics="none",
                note="Returns ElevenLabs user profile and quota overview."
            ),
            Capability(
                name="get_subscription",
                impact=Impact.READ,
                live_ready=True,
                cost_semantics="none",
                note="Returns detailed character limit, usage, and billing tier."
            ),
            Capability(
                name="list_voices",
                impact=Impact.READ,
                live_ready=True,
                cost_semantics="none",
                note="List premade and custom ElevenLabs voices."
            ),
            Capability(
                name="list_models",
                impact=Impact.READ,
                live_ready=True,
                cost_semantics="none",
                note="List available synthesis models including multilingual v2 and turbo v2.5."
            ),
            Capability(
                name="text_to_speech",
                impact=Impact.DRAFT,
                live_ready=True,
                cost_semantics="ElevenLabs characters",
                note="Generate high quality spoken audio (supports Vietnamese via eleven_multilingual_v2)."
            ),
        ]

    def _headers(self) -> dict[str, str]:
        key = self.env("ELEVENLABS_API_KEY") or ""
        return {
            "xi-api-key": key,
            "Accept": "application/json",
        }

    def probe_live(self) -> tuple[bool, str]:
        response = self.request(
            "GET",
            "https://api.elevenlabs.io/v1/user",
            headers=self._headers(),
            timeout=15.0,
        )
        if response.is_success:
            data = response.json()
            sub = data.get("subscription", {})
            tier = sub.get("tier", "unknown")
            char_count = sub.get("character_count", 0)
            char_limit = sub.get("character_limit", 0)
            remaining = max(0, char_limit - char_count)
            name = data.get("first_name") or "User"
            return True, f"ElevenLabs live verified (tier: {tier}, name: {name}, remaining chars: {remaining}/{char_limit})"
        return False, f"ElevenLabs probe failed with HTTP {response.status_code}: {response.text[:200]}"

    def read(self, resource: str, **kwargs: Any) -> list[Any]:
        if self.settings.environment.value == "mock":
            return self.mock_search(resource, limit=int(kwargs.get("limit", 3)))
        if resource == "user":
            res = self.request(
                "GET",
                "https://api.elevenlabs.io/v1/user",
                headers=self._headers(),
                timeout=15.0,
            )
            res.raise_for_status()
            return [res.json()]
        elif resource == "subscription":
            res = self.request(
                "GET",
                "https://api.elevenlabs.io/v1/user/subscription",
                headers=self._headers(),
                timeout=15.0,
            )
            res.raise_for_status()
            return [res.json()]
        elif resource == "voices":
            res = self.request(
                "GET",
                "https://api.elevenlabs.io/v1/voices",
                headers=self._headers(),
                timeout=20.0,
            )
            res.raise_for_status()
            voices = res.json().get("voices", [])
            query = str(kwargs.get("query", "")).lower()
            gender = str(kwargs.get("gender", "")).lower()
            category = str(kwargs.get("category", "")).lower()
            if query:
                voices = [v for v in voices if query in v.get("name", "").lower()]
            if gender:
                voices = [v for v in voices if v.get("labels", {}).get("gender", "").lower() == gender]
            if category:
                voices = [v for v in voices if v.get("category", "").lower() == category]
            limit = int(kwargs.get("limit", 0))
            if limit > 0:
                voices = voices[:limit]
            return voices
        elif resource == "models":
            res = self.request(
                "GET",
                "https://api.elevenlabs.io/v1/models",
                headers=self._headers(),
                timeout=15.0,
            )
            res.raise_for_status()
            return res.json()
        else:
            raise ValueError(f"Unsupported ElevenLabs resource: {resource}")

    def text_to_speech(
        self,
        text: str,
        voice_id: str | None = None,
        model_id: str | None = None,
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        output_format: str = "mp3_44100_128",
    ) -> bytes:
        """Synthesize text into speech audio bytes."""
        voice = voice_id or self.env("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE_ID
        model = model_id or self.env("ELEVENLABS_MODEL_ID") or DEFAULT_MODEL_ID
        
        headers = self._headers()
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "audio/mpeg"

        payload = {
            "text": text,
            "model_id": model,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity_boost,
            },
        }

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format={output_format}"
        res = self.request("POST", url, headers=headers, json=payload, timeout=60.0)
        res.raise_for_status()
        return res.content
