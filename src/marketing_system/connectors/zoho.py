from __future__ import annotations

from typing import Any

from ..constants import Impact
from ..normalization import normalize_zoho_record
from .base import BaseConnector, Capability


class ZohoConnector(BaseConnector):
    name = "zoho"
    required_env = ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN")
    optional_env = ("ZOHO_ACCOUNTS_URL", "ZOHO_API_DOMAIN")
    _resources = {
        "leads": ("Leads", "id,First_Name,Last_Name,Full_Name,Company,Designation,Email,Phone,Lead_Status"),
        "contacts": ("Contacts", "id,First_Name,Last_Name,Full_Name,Account_Name,Title,Email,Phone"),
        "accounts": ("Accounts", "id,Account_Name,Website,Industry,Billing_Country,Account_Type,Phone"),
        "deals": ("Deals", "id,Deal_Name,Account_Name,Stage,Amount,Closing_Date"),
        "tasks": ("Tasks", "id,Subject,Due_Date,What_Id,Priority,Status"),
    }

    def __init__(self, settings):
        super().__init__(settings)
        self._cached_access_context: tuple[str, str] | None = None

    # -- transport selection: own OAuth client (REST) first, else Zoho's hosted MCP server --
    def transport(self) -> str | None:
        if all(self.env(key) for key in self.required_env):
            return "rest"
        from . import zoho_mcp

        if zoho_mcp.endpoint() and zoho_mcp.has_tokens():
            return "mcp"
        from . import zoho_delegate

        if zoho_delegate.available():
            return "delegate"
        return None

    def _mcp_call(self, tool: str, arguments: dict[str, Any]) -> Any:
        if self.transport() == "delegate":
            from . import zoho_delegate

            return zoho_delegate.call_tool(tool, arguments)
        from . import zoho_mcp

        return zoho_mcp.call_tool(tool, arguments)

    def configured(self) -> bool:
        return self.transport() is not None

    def credential_presence(self) -> tuple[list[str], list[str]]:
        present, missing = super().credential_presence()
        if self.transport() == "mcp":
            return [*present, "ZOHO_MCP_URL", "ZOHO_MCP_TOKENS"], []
        if self.transport() == "delegate":
            return [*present, "CLAUDE_CODE_ZOHO_AUTH"], []
        return present, missing

    @property
    def capabilities(self) -> list[Capability]:
        return [
            Capability(name="read_crm_records", impact=Impact.READ, live_ready=True),
            Capability(name="stage_lead", impact=Impact.DRAFT),
            Capability(name="create_or_update_record", impact=Impact.WRITE, available_in_mock=False),
            Capability(name="delete_record", impact=Impact.HIGH_IMPACT, available_in_mock=False, note="Disabled in Phase 1."),
        ]

    def _access_context(self) -> tuple[str, str]:
        if self._cached_access_context:
            return self._cached_access_context
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
            raise RuntimeError("Token exchange returned no access token")
        self._cached_access_context = str(access_token), str(api_domain)
        return self._cached_access_context

    def probe_live(self) -> tuple[bool, str]:
        if self.transport() in ("mcp", "delegate"):
            body = self._mcp_call("ZohoCRM_getRecordCount", {"path_variables": {"moduleApiName": "Leads"}})
            ok = isinstance(body, dict) and body.get("status") == "success"
            return ok, f"Zoho {self.transport()} count probe " + ("succeeded." if ok else "failed.")
        access_token, api_domain = self._access_context()
        probe = self.request(
            "GET",
            f"{api_domain.rstrip('/')}/crm/v8/org",
            headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
            timeout=15.0,
        )
        return probe.is_success, f"Zoho organization probe returned HTTP {probe.status_code}."

    def read(self, resource: str, **kwargs: Any) -> list[Any]:
        if self.settings.environment.value == "mock":
            return self.mock_search(resource, limit=int(kwargs.get("limit", 3)))
        if resource not in self._resources:
            raise ValueError(f"Unsupported Zoho resource: {resource}")
        module, fields = self._resources[resource]
        limit = min(max(int(kwargs.get("limit", 25)), 1), 200)
        correlation_id = str(kwargs.get("correlation_id") or "zoho-read")
        if self.transport() in ("mcp", "delegate"):
            body = self._mcp_call("ZohoCRM_getRecords", {
                "path_variables": {"module": module},
                "query_params": {"fields": fields.replace("id,", ""), "per_page": limit},
            })
            if isinstance(body, dict) and body.get("status") == "failure":
                raise RuntimeError(f"Zoho error: {str(body.get('data'))[:200]}")
            data = body.get("data", []) if isinstance(body, dict) else []
            rows = data.get("data", []) if isinstance(data, dict) else data
            return [normalize_zoho_record(module, record, environment=self.settings.environment,
                                          correlation_id=correlation_id) for record in rows]
        access_token, api_domain = self._access_context()
        response = self.request(
            "GET",
            f"{api_domain.rstrip('/')}/crm/v8/{module}",
            headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
            params={"fields": fields, "per_page": limit},
            timeout=30.0,
        )
        response.raise_for_status()
        return [
            normalize_zoho_record(
                module,
                record,
                environment=self.settings.environment,
                correlation_id=correlation_id,
            )
            for record in response.json().get("data", [])
        ]
