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

    def search_companies(self, keywords: list[str], locations: list[str], per_page: int = 10) -> list[dict]:
        """One page of organization search (1 credit/page). Never calls enrichment."""
        response = self.request(
            "POST",
            "https://api.apollo.io/api/v1/mixed_companies/search",
            headers={"accept": "application/json", "content-type": "application/json",
                     "x-api-key": self.env("APOLLO_API_KEY") or ""},
            json={"q_organization_keyword_tags": keywords, "organization_locations": locations,
                  "page": 1, "per_page": min(max(per_page, 1), 25)},
            timeout=30.0,
        )
        response.raise_for_status()
        body = response.json()
        return list(body.get("organizations") or []) + list(body.get("accounts") or [])

    def probe_live(self) -> tuple[bool, str]:
        response = self.request(
            "GET",
            "https://api.apollo.io/api/v1/auth/health",
            headers={"accept": "application/json", "x-api-key": self.env("APOLLO_API_KEY") or ""},
            timeout=15.0,
        )
        return response.is_success, f"Apollo auth health returned HTTP {response.status_code}; no enrichment was called."
