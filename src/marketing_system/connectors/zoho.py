from __future__ import annotations

from ..constants import Impact
from .base import BaseConnector, Capability


class ZohoConnector(BaseConnector):
    name = "zoho"
    required_env = ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN")
    optional_env = ("ZOHO_ACCOUNTS_URL", "ZOHO_API_DOMAIN")

    @property
    def capabilities(self) -> list[Capability]:
        return [
            Capability(name="read_crm_records", impact=Impact.READ),
            Capability(name="stage_lead", impact=Impact.DRAFT),
            Capability(name="create_or_update_record", impact=Impact.WRITE, available_in_mock=False),
            Capability(name="delete_record", impact=Impact.HIGH_IMPACT, available_in_mock=False, note="Disabled in Phase 1."),
        ]

    def probe_live(self) -> tuple[bool, str]:
        accounts = self.env("ZOHO_ACCOUNTS_URL") or "https://accounts.zoho.com"
        token = self.request(
            "POST",
            f"{accounts.rstrip('/')}/oauth/v2/token",
            data={
                "grant_type": "refresh_token",
                "client_id": self.env("ZOHO_CLIENT_ID"),
                "client_secret": self.env("ZOHO_CLIENT_SECRET"),
                "refresh_token": self.env("ZOHO_REFRESH_TOKEN"),
            },
            timeout=15.0,
        )
        token.raise_for_status()
        body = token.json()
        access_token = body.get("access_token")
        api_domain = body.get("api_domain") or self.env("ZOHO_API_DOMAIN") or "https://www.zohoapis.com"
        if not access_token:
            return False, "Token exchange returned no access token."
        probe = self.request(
            "GET",
            f"{api_domain.rstrip('/')}/crm/v8/org",
            headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
            timeout=15.0,
        )
        return probe.is_success, f"Zoho organization probe returned HTTP {probe.status_code}."
