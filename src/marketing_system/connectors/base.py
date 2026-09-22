from __future__ import annotations

import os
import time
import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx
from pydantic import BaseModel, Field

from ..config import Settings
from ..constants import ConnectorState, Impact
from ..credentials import read_credential
from ..mock_data import connector_mock_records


# httpx emits full request URLs at INFO; query strings can contain provider data.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class Capability(BaseModel):
    name: str
    impact: Impact
    available_in_mock: bool = True
    live_ready: bool = False
    cost_semantics: str = "none"
    note: str = ""


class ConnectorReport(BaseModel):
    connector: str
    current_state: ConnectorState
    live_state: ConnectorState
    mode: str
    configured: bool
    credentials_present: list[str] = Field(default_factory=list)
    credentials_missing: list[str] = Field(default_factory=list)
    capabilities: list[Capability] = Field(default_factory=list)
    detail: str = ""
    live_tested: bool = False
    error_code: str | None = None


class BaseConnector(ABC):
    name: str
    required_env: tuple[str, ...] = ()
    optional_env: tuple[str, ...] = ()
    access_blocked: bool = False

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    @abstractmethod
    def capabilities(self) -> list[Capability]:
        raise NotImplementedError

    def env(self, name: str) -> str | None:
        value = os.getenv(name)
        if not value:
            value = read_credential(name)
        return value.strip() if value and value.strip() else None

    def configured(self) -> bool:
        return bool(self.required_env) and all(self.env(key) for key in self.required_env)

    def credential_presence(self) -> tuple[list[str], list[str]]:
        present = [key for key in (*self.required_env, *self.optional_env) if self.env(key)]
        missing = [key for key in self.required_env if not self.env(key)]
        return present, missing

    def report(self, live_probe: bool = False) -> ConnectorReport:
        present, missing = self.credential_presence()
        live_state = ConnectorState.NEEDS_ACCESS if self.access_blocked else ConnectorState.NEEDS_AUTH
        detail = "Mock adapter ready; live credentials are missing."
        tested = False
        error_code = None
        if self.configured() and not self.access_blocked:
            live_state = ConnectorState.DEGRADED
            detail = "Credentials are present but have not been live-verified."
            if live_probe:
                tested = True
                try:
                    ok, detail = self.probe_live()
                    live_state = ConnectorState.CONNECTED if ok else ConnectorState.ERROR
                except Exception as exc:  # exact provider errors are normalized here
                    live_state = ConnectorState.ERROR
                    error_code = type(exc).__name__
                    detail = "Live probe failed; see redacted structured log."
        current = ConnectorState.MOCK_READY if self.settings.environment.value == "mock" else live_state
        return ConnectorReport(
            connector=self.name,
            current_state=current,
            live_state=live_state,
            mode=self.settings.environment.value,
            configured=self.configured(),
            credentials_present=present,
            credentials_missing=missing,
            capabilities=self.capabilities,
            detail=detail,
            live_tested=tested,
            error_code=error_code,
        )

    def probe_live(self) -> tuple[bool, str]:
        return False, "No live probe is implemented."

    def health(self, live_probe: bool = False) -> ConnectorReport:
        return self.report(live_probe=live_probe)

    def auth_status(self) -> ConnectorState:
        return self.report(live_probe=False).live_state

    def read(self, resource: str, **kwargs: Any) -> Any:
        raise NotImplementedError(f"{self.name} read({resource}) is not enabled")

    def search(self, query: str, **kwargs: Any) -> Any:
        if self.settings.environment.value == "mock":
            return self.mock_search(query, limit=int(kwargs.get("limit", 3)))
        raise NotImplementedError(f"{self.name} live search is not enabled")

    def create_draft(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"connector": self.name, "kind": kind, "status": "draft", "payload": payload}

    def execute(self, action: str, payload: dict[str, Any], approval_context: dict[str, Any] | None = None) -> Any:
        raise PermissionError(f"{self.name} execution is disabled in Phase 1")

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Make a bounded request with retry for 429/5xx; never retry other 4xx."""
        last: httpx.Response | None = None
        for attempt in range(3):
            response = httpx.request(method, url, **kwargs)
            last = response
            if response.status_code not in {429, 500, 502, 503, 504}:
                return response
            if attempt < 2:
                retry_after = response.headers.get("retry-after", "0")
                try:
                    delay = min(max(float(retry_after), 0.05), 1.0)
                except ValueError:
                    delay = 0.25 * (attempt + 1)
                time.sleep(delay)
        assert last is not None
        return last

    def mock_search(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        return connector_mock_records(self.name, query, limit)
