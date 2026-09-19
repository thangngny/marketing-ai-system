from __future__ import annotations

from ..constants import ConnectorState, Impact
from .base import BaseConnector, Capability, ConnectorReport


class LinkedInConnector(BaseConnector):
    name = "linkedin"
    required_env = ("LINKEDIN_ACCESS_TOKEN",)
    optional_env = ("LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET", "LINKEDIN_REDIRECT_URI")
    access_blocked = True

    @property
    def capabilities(self) -> list[Capability]:
        return [
            Capability(name="read_authorized_profile_or_page", impact=Impact.READ),
            Capability(name="create_post_draft", impact=Impact.DRAFT),
            Capability(name="publish_post", impact=Impact.HIGH_IMPACT, available_in_mock=False, note="Disabled until product access and approval."),
        ]

    def report(self, live_probe: bool = False) -> ConnectorReport:
        report = super().report(live_probe=False)
        if self.configured():
            self.access_blocked = False
            report = super().report(live_probe=live_probe)
        elif report.live_state == ConnectorState.NEEDS_ACCESS:
            report.detail = "OAuth credentials and LinkedIn product/API access are required."
        return report

    def probe_live(self) -> tuple[bool, str]:
        response = self.request(
            "GET",
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {self.env('LINKEDIN_ACCESS_TOKEN')}"},
            timeout=15.0,
        )
        return response.is_success, f"LinkedIn userinfo probe returned HTTP {response.status_code}."
