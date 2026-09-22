from __future__ import annotations

from typing import Any

from ..constants import Impact
from ..credentials import write_credential
from ..normalization import normalize_graph_message
from .base import BaseConnector, Capability


class M365Connector(BaseConnector):
    name = "m365"
    required_env = ("MS_TENANT_ID", "MS_CLIENT_ID", "MS_REFRESH_TOKEN")
    optional_env = ("MS_GRAPH_ACCESS_TOKEN", "MS_CLIENT_SECRET", "MS_REDIRECT_URI")

    def __init__(self, settings):
        super().__init__(settings)
        self._cached_access_token: str | None = None

    @property
    def capabilities(self) -> list[Capability]:
        return [
            Capability(name="read_mail_metadata", impact=Impact.READ, live_ready=True),
            Capability(name="read_calendar", impact=Impact.READ, note="Live normalization is not enabled yet."),
            Capability(name="read_files", impact=Impact.READ, note="Live normalization is not enabled yet."),
            Capability(name="create_email_draft", impact=Impact.DRAFT),
            Capability(name="send_email", impact=Impact.HIGH_IMPACT, available_in_mock=False, note="Explicit approval required."),
        ]

    def _access_token(self) -> str:
        if self._cached_access_token:
            return self._cached_access_token
        existing = self.env("MS_GRAPH_ACCESS_TOKEN")
        if existing:
            self._cached_access_token = existing
            return self._cached_access_token
        tenant = self.env("MS_TENANT_ID") or "organizations"
        data = {
            "client_id": self.env("MS_CLIENT_ID"),
            "grant_type": "refresh_token",
            "refresh_token": self.env("MS_REFRESH_TOKEN"),
            "scope": "openid profile offline_access User.Read Mail.Read Calendars.Read Files.Read",
        }
        if self.env("MS_CLIENT_SECRET"):
            data["client_secret"] = self.env("MS_CLIENT_SECRET")
        response = self.request(
            "POST",
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            data=data,
            timeout=20.0,
        )
        response.raise_for_status()
        body = response.json()
        if body.get("refresh_token"):
            write_credential("MS_REFRESH_TOKEN", str(body["refresh_token"]))
        self._cached_access_token = str(body["access_token"])
        return self._cached_access_token

    def probe_live(self) -> tuple[bool, str]:
        response = self.request(
            "GET",
            "https://graph.microsoft.com/v1.0/me?$select=id,displayName",
            headers={"Authorization": f"Bearer {self._access_token()}"},
            timeout=15.0,
        )
        return response.is_success, f"Microsoft Graph /me probe returned HTTP {response.status_code}."

    def read(self, resource: str, **kwargs: Any) -> list[Any]:
        if self.settings.environment.value == "mock":
            return self.mock_search(resource, limit=int(kwargs.get("limit", 3)))
        limit = min(max(int(kwargs.get("limit", 25)), 1), 100)
        correlation_id = str(kwargs.get("correlation_id") or "m365-read")
        token = self._access_token()
        if resource == "mail_metadata":
            response = self.request(
                "GET",
                "https://graph.microsoft.com/v1.0/me/messages",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "$select": "id,subject,from,receivedDateTime,isRead,webLink",
                    "$top": limit,
                    "$orderby": "receivedDateTime desc",
                },
                timeout=30.0,
            )
            response.raise_for_status()
            return [
                normalize_graph_message(
                    record,
                    environment=self.settings.environment,
                    correlation_id=correlation_id,
                )
                for record in response.json().get("value", [])
            ]
        raise ValueError(f"Unsupported Microsoft 365 resource: {resource}")
