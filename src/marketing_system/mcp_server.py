"""MCP tool boundary.

Exposes the tool hub (namespaced tools, e.g. `crm_search_leads`) plus workflow
and orchestration entry points. It holds no routing, policy, or state of its
own. No tool here can approve anything: approval only comes from an
ApprovalVerifier (owner-signed Buzz message or local console).
"""

from __future__ import annotations

import inspect
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from .app import build_platform
from .constants import Impact
from .models import OrchestratorResult, ReadonlySyncResult, RouteDecision
from .orchestrator import MarketingOrchestrator
from .routing import route_intent
from .safety import SafetyDecision, authorize
from .specialists import SPECIALISTS
from .telemetry import new_correlation_id
from .tools.hub import ToolContext, ToolSpec

platform = build_platform()
settings = platform.settings
orchestrator = MarketingOrchestrator(platform=platform)
server = MCPServer(
    "local-ai-marketing-system",
    title="Marketing Tool Hub",
    description="Typed marketing tools behind a deterministic policy/approval boundary, plus durable workflows.",
    version="0.2.0",
)


# ----------------------------------------------------------------------------- orchestration
@server.tool()
def marketing_handle_request(text: str, source_channel: str = "buzz", buzz_event_id: str | None = None,
                             channel_id: str | None = None, user_id: str | None = None) -> OrchestratorResult:
    """Route one user request: fast read, durable workflow, or a specialist brief for you to execute."""
    return orchestrator.handle(text, source_channel=source_channel, event_id=buzz_event_id,
                               channel_id=channel_id, user_id=user_id)


@server.tool()
def marketing_system_status() -> dict[str, Any]:
    """Connector capability states (AUTH/READ/ANALYTICS/DRAFT/PUBLISH), runtime and environment."""
    return orchestrator.status()


@server.tool()
def marketing_system_overview() -> dict[str, Any]:
    """One-screen overview: connector health, pending approvals, waiting workflows, alerts."""
    return orchestrator.overview()


@server.tool()
def marketing_route_intent(text: str) -> RouteDecision:
    """Select only the specialist roles needed for a request."""
    return route_intent(text)


@server.tool()
def marketing_request_execution(action: str) -> SafetyDecision:
    """Classify an external action. Informational only: it cannot grant approval."""
    return authorize(action, settings.environment, settings.safe_dry_run)


@server.tool()
def marketing_sync_readonly(connector: str, resource: str, limit: int = 25) -> ReadonlySyncResult:
    """Live-verify a connector, read bounded provider data, normalize it, and stage it locally."""
    if connector not in {"zoho", "m365", "website", "youtube"}:
        return ReadonlySyncResult(state="UNSUPPORTED_CONNECTOR", connector=connector, resource=resource)
    return orchestrator.sync_readonly(connector, resource, limit=min(max(limit, 1), 100))


# ----------------------------------------------------------------------------- workflows
@server.tool()
def workflow_start(workflow_type: str, request: str, params: dict[str, Any] | None = None,
                   channel_id: str | None = None, user_id: str | None = None) -> dict[str, Any]:
    """Start a durable workflow (types: prospect_to_draft). Runs until done or until owner approval is needed."""
    if workflow_type not in platform.engine.definitions or workflow_type == "tool_approval":
        return {"error": "UNKNOWN_WORKFLOW", "known": [k for k in platform.engine.definitions if k != "tool_approval"]}
    return platform.engine.start(workflow_type, request, params=params or {}, user_id=user_id,
                                 channel_id=channel_id or settings.buzz_channel)


@server.tool()
def workflow_status(workflow_id: str) -> dict[str, Any]:
    """Current state, steps, approval request and result of a workflow."""
    return platform.engine.status(workflow_id)


@server.tool()
def workflow_resume(workflow_id: str) -> dict[str, Any]:
    """Continue a workflow. Resumes only if the owner's signed approval is found; otherwise stays waiting."""
    return platform.engine.resume(workflow_id)


@server.tool()
def workflow_cancel(workflow_id: str, reason: str = "cancelled by request") -> dict[str, Any]:
    """Cancel a workflow and its pending approval."""
    return platform.engine.cancel(workflow_id, reason)


@server.tool()
def approval_status(code_or_id: str) -> dict[str, Any]:
    """Check an approval (by code MV-XXXXXX or id). Looks for the owner's signed reply; cannot approve by itself."""
    record = platform.approvals.refresh(code_or_id)
    return record.model_dump(exclude={"payload_hash"}) if record else {"error": "UNKNOWN_APPROVAL"}


# ----------------------------------------------------------------------------- hub tools
def _default_specialist(spec: ToolSpec) -> str:
    for specialist in SPECIALISTS.values():
        if specialist.allows(spec.namespace, spec.impact):
            return specialist.id
    return "00_orchestrator"


def _hub_tool(spec: ToolSpec):
    fields = spec.input_model.model_fields

    def call(**kwargs: Any) -> dict[str, Any]:
        specialist = kwargs.pop("specialist", None) or _default_specialist(spec)
        correlation_id = kwargs.pop("correlation_id", None) or new_correlation_id()
        args = {k: v for k, v in kwargs.items() if v is not None or k not in fields or fields[k].is_required()}
        if spec.impact in (Impact.WRITE_LOW_RISK, Impact.HIGH_IMPACT):
            # Writes are never executed inline: they become a durable workflow waiting for owner approval.
            return platform.engine.start("tool_approval", f"{spec.name} {args}", params={
                "tool": spec.name, "args": args, "specialist": specialist}, correlation_id=correlation_id,
                channel_id=settings.buzz_channel)
        ctx = ToolContext(correlation_id=correlation_id, specialist_id=specialist, runtime=platform.runtime.name)
        return platform.hub.invoke(spec.name, args, ctx).model_dump(mode="json")

    params = [inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY, annotation=field.annotation,
                                default=inspect.Parameter.empty if field.is_required() else field.get_default(call_default_factory=True))
              for name, field in fields.items()]
    params += [inspect.Parameter("specialist", inspect.Parameter.KEYWORD_ONLY, annotation=str | None, default=None),
               inspect.Parameter("correlation_id", inspect.Parameter.KEYWORD_ONLY, annotation=str | None, default=None)]
    call.__signature__ = inspect.Signature(params, return_annotation=dict[str, Any])
    call.__annotations__ = {p.name: p.annotation for p in params} | {"return": dict[str, Any]}
    call.__name__ = spec.mcp_name
    call.__doc__ = f"{spec.description} [impact={spec.impact}, connector={spec.connector}]"
    return call


for _spec in platform.hub.specs():
    server.add_tool(
        _hub_tool(_spec), name=_spec.mcp_name, description=f"{_spec.description} [impact={_spec.impact}]",
        annotations=ToolAnnotations(readOnlyHint=_spec.impact is Impact.READ,
                                    destructiveHint=_spec.impact is Impact.HIGH_IMPACT,
                                    idempotentHint=_spec.impact is not Impact.HIGH_IMPACT),
        meta={"impact": str(_spec.impact), "namespace": _spec.namespace, "connector": _spec.connector},
        structured_output=True,
    )


def main() -> None:
    touched = platform.engine.recover()  # restart recovery: finish anything a previous process left mid-flight
    if touched:
        from .logging_utils import write_event

        write_event(settings.log_dir, kind="recovery", workflows=touched)
    server.run("stdio")


if __name__ == "__main__":
    main()
