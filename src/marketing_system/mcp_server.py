from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from .config import Settings
from .fixtures import mock_logistics_leads
from .models import OrchestratorResult, ReadonlySyncResult, RouteDecision
from .orchestrator import MarketingOrchestrator
from .routing import route_intent
from .safety import SafetyDecision, authorize


settings = Settings.from_env()
orchestrator = MarketingOrchestrator(settings)
server = MCPServer(
    "local-ai-marketing-system",
    title="Local AI Marketing Integration Layer",
    description="Safe local-first marketing router, canonical store, and mock/live connector boundary.",
    version="0.1.0",
)


@server.tool()
def marketing_handle_request(text: str, source_channel: str = "buzz") -> OrchestratorResult:
    """Route a marketing request and return one coherent, safety-checked result."""
    return orchestrator.handle(text, source_channel=source_channel)


@server.tool()
def marketing_system_status() -> dict:
    """Return connector states without making paid or live external calls."""
    return orchestrator.status()


@server.tool()
def marketing_route_intent(text: str) -> RouteDecision:
    """Select only the specialist marketing agents needed for a request."""
    return route_intent(text)


@server.tool()
def marketing_search_leads_mock(industry: str = "logistics", limit: int = 3) -> dict:
    """Return deterministic synthetic leads; never call Apollo or a live CRM."""
    correlation_id = "mcp-direct-mock-search"
    leads = mock_logistics_leads(correlation_id, limit=limit)
    return {
        "environment": "mock",
        "industry": industry,
        "label": "SYNTHETIC_MOCK_DATA",
        "records": [lead.model_dump(mode="json") for lead in leads],
    }


@server.tool()
def marketing_request_execution(action: str, explicit_approval: bool = False) -> SafetyDecision:
    """Evaluate an external action against SAFE_DRY_RUN and approval policy."""
    return authorize(
        action,
        settings.environment,
        settings.safe_dry_run,
        explicit_approval=explicit_approval,
    )


@server.tool()
def marketing_sync_readonly(connector: str, resource: str, limit: int = 25) -> ReadonlySyncResult:
    """Live-verify a connector, read bounded provider data, normalize it, and stage it locally."""
    if connector not in {"zoho", "m365", "website", "youtube"}:
        return ReadonlySyncResult(
            state="UNSUPPORTED_CONNECTOR",
            connector=connector,
            resource=resource,
        )
    return orchestrator.sync_readonly(connector, resource, limit=min(max(limit, 1), 100))


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
