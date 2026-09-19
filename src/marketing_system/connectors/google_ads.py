from __future__ import annotations

from ..constants import Impact
from .base import BaseConnector, Capability


class GoogleAdsConnector(BaseConnector):
    name = "google_ads"
    required_env = (
        "GOOGLE_ADS_DEVELOPER_TOKEN",
        "GOOGLE_ADS_CUSTOMER_ID",
        "GOOGLE_ADS_CLIENT_ID",
        "GOOGLE_ADS_CLIENT_SECRET",
        "GOOGLE_ADS_REFRESH_TOKEN",
    )
    optional_env = ("GOOGLE_ADS_LOGIN_CUSTOMER_ID",)

    @property
    def capabilities(self) -> list[Capability]:
        return [
            Capability(name="query_metrics", impact=Impact.READ),
            Capability(name="create_campaign_draft", impact=Impact.DRAFT),
            Capability(name="mutate_campaign_or_budget", impact=Impact.HIGH_IMPACT, available_in_mock=False, note="Disabled in Phase 1."),
        ]

    def _access_token(self) -> str:
        response = self.request(
            "POST",
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "refresh_token",
                "client_id": self.env("GOOGLE_ADS_CLIENT_ID"),
                "client_secret": self.env("GOOGLE_ADS_CLIENT_SECRET"),
                "refresh_token": self.env("GOOGLE_ADS_REFRESH_TOKEN"),
            },
            timeout=15.0,
        )
        response.raise_for_status()
        return str(response.json()["access_token"])

    def probe_live(self) -> tuple[bool, str]:
        headers = {
            "Authorization": f"Bearer {self._access_token()}",
            "developer-token": self.env("GOOGLE_ADS_DEVELOPER_TOKEN") or "",
        }
        if self.env("GOOGLE_ADS_LOGIN_CUSTOMER_ID"):
            headers["login-customer-id"] = self.env("GOOGLE_ADS_LOGIN_CUSTOMER_ID") or ""
        response = self.request(
            "GET",
            "https://googleads.googleapis.com/v25/customers:listAccessibleCustomers",
            headers=headers,
            timeout=15.0,
        )
        return response.is_success, f"Google Ads accessible-customers probe returned HTTP {response.status_code}."
