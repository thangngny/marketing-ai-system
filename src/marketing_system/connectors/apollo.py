from __future__ import annotations

from ..constants import Impact
from .base import BaseConnector, Capability


class ApolloConnector(BaseConnector):
    name = "apollo"
    required_env = ("APOLLO_API_KEY",)

    @property
    def capabilities(self) -> list[Capability]:
        return [
            Capability(name="people_search", impact=Impact.READ, cost_semantics="0 credits per current official documentation"),
            Capability(name="organization_search", impact=Impact.READ, cost_semantics="1 Apollo credit per page"),
            Capability(name="people_enrichment", impact=Impact.READ, cost_semantics="consumes credits", note="Never run from health checks."),
        ]

    def probe_live(self) -> tuple[bool, str]:
        response = self.request(
            "GET",
            "https://api.apollo.io/api/v1/auth/health",
            headers={"accept": "application/json", "x-api-key": self.env("APOLLO_API_KEY") or ""},
            timeout=15.0,
        )
        return response.is_success, f"Apollo auth health returned HTTP {response.status_code}; no enrichment was called."
