from __future__ import annotations

from typing import Any

from ..constants import Impact
from .base import BaseConnector, Capability


class MetaAdsConnector(BaseConnector):
    name = "meta_ads"
    required_env = ("META_AD_ACCOUNT_ID",)
    optional_env = ("META_ACCESS_TOKEN", "META_APP_ID", "META_APP_SECRET", "META_PAGE_ACCESS_TOKEN", "META_PAGE_ID")

    @property
    def capabilities(self) -> list[Capability]:
        return [
            Capability(name="read_ad_metrics", impact=Impact.READ),
            Capability(name="create_campaign_draft", impact=Impact.DRAFT),
            Capability(name="launch_or_modify_campaign", impact=Impact.HIGH_IMPACT, available_in_mock=False, note="Disabled in Phase 1."),
            Capability(name="change_budget", impact=Impact.HIGH_IMPACT, available_in_mock=False, note="Disabled in Phase 1."),
            Capability(name="create_page_post_draft", impact=Impact.DRAFT,
                       note="Creates an unpublished (published=false) Facebook Page post. Never goes public."),
            Capability(name="publish_page_post", impact=Impact.HIGH_IMPACT, available_in_mock=True, live_ready=True,
                       note="Publishes a live public Facebook Page post. Gated by owner approval."),
        ]

    def _effective_ad_token(self) -> str:
        return self.env("META_ACCESS_TOKEN") or self.env("META_PAGE_ACCESS_TOKEN") or ""

    def configured(self) -> bool:
        return bool(self.env("META_AD_ACCOUNT_ID") and (self.env("META_ACCESS_TOKEN") or self.env("META_PAGE_ACCESS_TOKEN")))

    def probe_live(self) -> tuple[bool, str]:
        account = (self.env("META_AD_ACCOUNT_ID") or "").removeprefix("act_")
        for token_key in ("META_ACCESS_TOKEN", "META_PAGE_ACCESS_TOKEN"):
            token = self.env(token_key)
            if not token:
                continue
            response = self.request(
                "GET",
                f"https://graph.facebook.com/v23.0/act_{account}",
                params={"fields": "id,name,account_status"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=15.0,
            )
            if response.is_success:
                account_name = response.json().get("name", f"act_{account}")
                return True, f"Meta ad-account probe succeeded for '{account_name}' (via {token_key})."
        return False, "Meta ad-account read probe failed (all tokens expired or unauthorized)."

    def page_configured(self) -> bool:
        return bool(self.env("META_PAGE_ACCESS_TOKEN") and self.env("META_PAGE_ID"))

    def create_page_post_draft(self, message: str) -> dict[str, Any]:
        """Create an unpublished Facebook Page post (a private draft, not visible to the public).

        Uses a separate Page Access Token/Page ID from the ad-account credentials above, since
        posting to a Page and reading an ad account are different Graph API access grants.
        """
        page_id = self.env("META_PAGE_ID")
        token = self.env("META_PAGE_ACCESS_TOKEN")
        if not page_id or not token:
            raise RuntimeError("META_PAGE_ACCESS_TOKEN / META_PAGE_ID missing: Page posting is not configured.")
        response = self.request(
            "POST",
            f"https://graph.facebook.com/v23.0/{page_id}/feed",
            data={"message": message, "published": "false"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=20.0,
        )
        response.raise_for_status()
        body = response.json()
        return {"connector": self.name, "kind": "page_post", "status": "draft", "published": False,
                "post_id": body.get("id"), "page_id": page_id, "message": message}

    def publish_page_post(self, message: str, link: str | None = None) -> dict[str, Any]:
        """Publish a live public Facebook Page post. Gated by owner approval."""
        page_id = self.env("META_PAGE_ID")
        token = self.env("META_PAGE_ACCESS_TOKEN")
        if not page_id or not token:
            raise RuntimeError("META_PAGE_ACCESS_TOKEN / META_PAGE_ID missing: Page posting is not configured.")
        data: dict[str, Any] = {"message": message, "published": "true"}
        if link:
            data["link"] = link
        response = self.request(
            "POST",
            f"https://graph.facebook.com/v23.0/{page_id}/feed",
            data=data,
            headers={"Authorization": f"Bearer {token}"},
            timeout=20.0,
        )
        response.raise_for_status()
        body = response.json()
        return {"connector": self.name, "kind": "page_post", "status": "published", "published": True,
                "post_id": body.get("id"), "page_id": page_id, "message": message, "link": link}
