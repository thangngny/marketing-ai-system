from __future__ import annotations

from ..constants import Impact
from .base import BaseConnector, Capability


class MetaAdsConnector(BaseConnector):
    name = "meta_ads"
    required_env = ("META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID")
    optional_env = ("META_APP_ID", "META_APP_SECRET")

    @property
    def capabilities(self) -> list[Capability]:
        return [
            Capability(name="read_ad_metrics", impact=Impact.READ),
            Capability(name="create_campaign_draft", impact=Impact.DRAFT),
            Capability(name="launch_or_modify_campaign", impact=Impact.HIGH_IMPACT, available_in_mock=False, note="Disabled in Phase 1."),
            Capability(name="change_budget", impact=Impact.HIGH_IMPACT, available_in_mock=False, note="Disabled in Phase 1."),
        ]

    def probe_live(self) -> tuple[bool, str]:
        account = (self.env("META_AD_ACCOUNT_ID") or "").removeprefix("act_")
        response = self.request(
            "GET",
            f"https://graph.facebook.com/v23.0/act_{account}",
            params={"fields": "id,name,account_status"},
            headers={"Authorization": f"Bearer {self.env('META_ACCESS_TOKEN')}"},
            timeout=15.0,
        )
        return response.is_success, f"Meta ad-account read probe returned HTTP {response.status_code}."
