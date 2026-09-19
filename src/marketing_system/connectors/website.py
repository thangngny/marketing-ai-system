from __future__ import annotations

from ..constants import ConnectorState, Impact
from .base import BaseConnector, Capability, ConnectorReport


class WebsiteConnector(BaseConnector):
    name = "website"
    required_env = ("WEBSITE_URL",)
    optional_env = ("WEBSITE_WEBHOOK_SECRET",)

    @property
    def capabilities(self) -> list[Capability]:
        return [
            Capability(name="read_public_metadata", impact=Impact.READ),
            Capability(name="ingest_form_webhook", impact=Impact.WRITE, available_in_mock=True, note="Local staging only in Phase 1."),
            Capability(name="create_landing_page_draft", impact=Impact.DRAFT),
        ]

    def report(self, live_probe: bool = False) -> ConnectorReport:
        report = super().report(live_probe=live_probe)
        if not self.configured():
            report.live_state = ConnectorState.CONFIG_REQUIRED
            if self.settings.environment.value != "mock":
                report.current_state = ConnectorState.CONFIG_REQUIRED
            report.detail = "Set WEBSITE_URL to enable a non-destructive public health check."
        return report

    def probe_live(self) -> tuple[bool, str]:
        response = self.request("GET", self.env("WEBSITE_URL") or "", timeout=15.0, follow_redirects=True)
        return response.is_success, f"Website GET probe returned HTTP {response.status_code}."
