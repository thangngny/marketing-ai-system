from __future__ import annotations

from html.parser import HTMLParser
from typing import Any

from ..constants import ConnectorState, Impact
from ..normalization import normalize_website
from .base import BaseConnector, Capability, ConnectorReport


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_title = False
        self.title_parts: list[str] = []
        self.description: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag.lower() == "title":
            self.in_title = True
        if tag.lower() == "meta" and values.get("name", "").lower() == "description":
            self.description = values.get("content")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)


class WebsiteConnector(BaseConnector):
    name = "website"
    required_env = ("WEBSITE_URL",)
    optional_env = ("WEBSITE_WEBHOOK_SECRET",)

    @property
    def capabilities(self) -> list[Capability]:
        return [
            Capability(name="read_public_metadata", impact=Impact.READ, live_ready=True),
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

    def read(self, resource: str, **kwargs: Any) -> list[Any]:
        if self.settings.environment.value == "mock":
            return self.mock_search(resource, limit=int(kwargs.get("limit", 1)))
        if resource != "metadata":
            raise ValueError(f"Unsupported website resource: {resource}")
        url = self.env("WEBSITE_URL") or ""
        response = self.request("GET", url, timeout=20.0, follow_redirects=True)
        response.raise_for_status()
        parser = _MetadataParser()
        parser.feed(response.text)
        title = " ".join("".join(parser.title_parts).split()) or None
        return [
            normalize_website(
                str(response.url),
                title=title,
                environment=self.settings.environment,
                correlation_id=str(kwargs.get("correlation_id") or "website-read"),
                metadata={"description": parser.description},
            )
        ]
