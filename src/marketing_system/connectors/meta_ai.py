from __future__ import annotations

import logging
from typing import Any

from ..constants import Impact
from .base import BaseConnector, Capability

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.meta.ai/v1"
DEFAULT_CHAT_MODEL = "muse-spark-1.3"
DEFAULT_IMAGE_MODEL = "muse-image-1.0"


class MetaAiConnector(BaseConnector):
    name = "meta_ai"
    required_env = ("META_AI_API_KEY",)
    optional_env = ("META_AI_BASE_URL", "META_AI_DEFAULT_MODEL")

    @property
    def capabilities(self) -> list[Capability]:
        return [
            Capability(
                name="probe_live",
                impact=Impact.READ,
                live_ready=True,
                cost_semantics="none",
                note="Verifies Meta AI API credentials and retrieves active model catalog."
            ),
            Capability(
                name="list_models",
                impact=Impact.READ,
                live_ready=True,
                cost_semantics="none",
                note="List Meta AI foundation models (Muse Spark 1.3, Muse Image 1.0, SAM 3.1, etc.)."
            ),
            Capability(
                name="chat_completion",
                impact=Impact.READ,
                live_ready=True,
                cost_semantics="Meta AI tokens",
                note="Execute reasoning, content generation, and strategy using Muse Spark 1.3."
            ),
            Capability(
                name="generate_image",
                impact=Impact.DRAFT,
                live_ready=True,
                cost_semantics="Meta AI image credits",
                note="Generate high-resolution marketing visuals using Muse Image 1.0."
            ),
        ]

    def _base_url(self) -> str:
        return self.env("META_AI_BASE_URL") or DEFAULT_BASE_URL

    def _headers(self) -> dict[str, str]:
        key = self.env("META_AI_API_KEY") or ""
        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def probe_live(self) -> tuple[bool, str]:
        url = f"{self._base_url()}/models"
        try:
            response = self.request(
                "GET",
                url,
                headers=self._headers(),
                timeout=15.0,
            )
            if response.status_code == 200:
                data = response.json()
                models = [m.get("id") for m in data.get("data", [])]
                model_str = ", ".join(models[:4]) if models else "none"
                # Check billing state by checking a lightweight test
                billing_msg = "billing active"
                try:
                    test_chat = self.request(
                        "POST",
                        f"{self._base_url()}/chat/completions",
                        headers=self._headers(),
                        json={"model": DEFAULT_CHAT_MODEL, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1},
                        timeout=5.0,
                    )
                    if test_chat.status_code == 402:
                        billing_msg = "billing pending on dev.meta.ai"
                except Exception:
                    pass
                return True, f"Meta AI live verified (models: {len(models)} [{model_str}]; {billing_msg})"
            return False, f"Meta AI probe failed with HTTP {response.status_code}: {response.text[:200]}"
        except Exception as exc:
            return False, f"Meta AI probe error: {exc}"

    def list_models(self) -> list[dict[str, Any]]:
        url = f"{self._base_url()}/models"
        res = self.request("GET", url, headers=self._headers(), timeout=15.0)
        res.raise_for_status()
        return res.json().get("data", [])

    def read(self, resource: str, **kwargs: Any) -> list[Any]:
        if self.settings.environment.value == "mock":
            return self.mock_search(resource, limit=int(kwargs.get("limit", 3)))
        if resource == "models":
            return self.list_models()
        elif resource == "status":
            ok, msg = self.probe_live()
            return [{"connected": ok, "details": msg}]
        else:
            raise ValueError(f"Unsupported Meta AI resource: {resource}")

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **extra: Any,
    ) -> dict[str, Any]:
        """Generate response via Muse Spark 1.3."""
        selected_model = model or self.env("META_AI_DEFAULT_MODEL") or DEFAULT_CHAT_MODEL
        payload: dict[str, Any] = {
            "model": selected_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            **extra,
        }
        url = f"{self._base_url()}/chat/completions"
        res = self.request("POST", url, headers=self._headers(), json=payload, timeout=60.0)
        if res.status_code == 402:
            raise RuntimeError(
                "Meta AI Billing Pending: Vui lòng thêm phương thức thanh toán tại https://dev.meta.ai để kích hoạt inference quota."
            )
        res.raise_for_status()
        return res.json()

    def generate_image(
        self,
        prompt: str,
        model: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Generate images via Muse Image 1.0."""
        selected_model = model or DEFAULT_IMAGE_MODEL
        payload: dict[str, Any] = {
            "model": selected_model,
            "prompt": prompt,
            **extra,
        }
        url = f"{self._base_url()}/images/generations"
        res = self.request("POST", url, headers=self._headers(), json=payload, timeout=60.0)
        if res.status_code == 402:
            raise RuntimeError(
                "Meta AI Billing Pending: Vui lòng thêm phương thức thanh toán tại https://dev.meta.ai để kích hoạt image quota."
            )
        res.raise_for_status()
        return res.json()
