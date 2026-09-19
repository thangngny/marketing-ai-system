from __future__ import annotations

from ..constants import Impact
from .base import BaseConnector, Capability


class M365Connector(BaseConnector):
    name = "m365"
    required_env = ("MS_GRAPH_ACCESS_TOKEN",)
    optional_env = ("MS_TENANT_ID", "MS_CLIENT_ID", "MS_CLIENT_SECRET", "MS_REDIRECT_URI")

    @property
    def capabilities(self) -> list[Capability]:
        return [
            Capability(name="read_mail_metadata", impact=Impact.READ),
            Capability(name="read_calendar", impact=Impact.READ),
            Capability(name="read_files", impact=Impact.READ),
            Capability(name="create_email_draft", impact=Impact.DRAFT),
            Capability(name="send_email", impact=Impact.HIGH_IMPACT, available_in_mock=False, note="Explicit approval required."),
        ]

    def probe_live(self) -> tuple[bool, str]:
        response = self.request(
            "GET",
            "https://graph.microsoft.com/v1.0/me?$select=id,displayName",
            headers={"Authorization": f"Bearer {self.env('MS_GRAPH_ACCESS_TOKEN')}"},
            timeout=15.0,
        )
        return response.is_success, f"Microsoft Graph /me probe returned HTTP {response.status_code}."
