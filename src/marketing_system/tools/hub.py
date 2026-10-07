"""Tool hub: typed ToolSpecs behind one invocation path.

Every call goes: validate input → policy → (approval | idempotency) → connector handler
→ ledger + span. MCP only exposes this hub; it adds no logic of its own.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..config import Settings
from ..constants import Decision, Environment, Impact
from ..policy import PolicyEngine
from ..specialists import ORCHESTRATOR, Specialist, get_specialist
from ..telemetry import span
from ..workflows.approvals import ApprovalEngine, ApprovalRecord, payload_hash
from ..workflows.store import WorkflowStore


class ToolUnavailable(Exception):
    """Raised by handlers when the provider capability is not live (never a crash)."""

    def __init__(self, state: str, detail: str = ""):
        super().__init__(detail or state)
        self.state = state
        self.detail = detail


class ToolContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    correlation_id: str
    specialist_id: str = ORCHESTRATOR.id
    workflow_id: str | None = None
    approval_id: str | None = None
    idempotency_key: str | None = None
    user_id: str | None = None
    channel_id: str | None = None
    runtime: str | None = None
    direct_user_publish: bool = False


class ToolSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    impact: Impact
    connector: str
    capability: str
    input_model: type[BaseModel]
    idempotent: bool = True
    summarize: Callable[[dict[str, Any]], str] | None = Field(default=None, exclude=True)

    @property
    def namespace(self) -> str:
        return self.name.split(".", 1)[0]

    @property
    def mcp_name(self) -> str:
        return self.name.replace(".", "_")

    def input_schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()


class ToolResult(BaseModel):
    tool: str
    state: str  # OK | MOCK | DUPLICATE | APPROVAL_REQUIRED | DENIED | NEEDS_AUTH | NEEDS_API_ACCESS | NOT_IMPLEMENTED | INVALID_INPUT | ERROR
    decision: str | None = None
    impact: str | None = None
    environment: str
    correlation_id: str
    workflow_id: str | None = None
    data: Any = None
    detail: str = ""
    approval: dict[str, Any] | None = None
    idempotency_key: str | None = None
    error_code: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.state in {"OK", "MOCK", "DUPLICATE"}


Handler = Callable[[BaseModel, "HubRuntime"], Any]


class HubRuntime(BaseModel):
    """What a handler may touch: settings, connectors, artifact dir, call context."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    settings: Settings
    registry: Any
    ctx: ToolContext
    artifacts_dir: Path

    @property
    def mock(self) -> bool:
        return self.settings.environment is Environment.MOCK


class ToolHub:
    def __init__(self, settings: Settings, registry: Any, store: WorkflowStore, approvals: ApprovalEngine,
                 policy: PolicyEngine | None = None):
        self.settings = settings
        self.registry = registry
        self.store = store
        self.approvals = approvals
        self.policy = policy or PolicyEngine()
        self._specs: dict[str, ToolSpec] = {}
        self._handlers: dict[str, Handler] = {}

    def register(self, spec: ToolSpec, handler: Handler) -> None:
        if spec.name in self._specs:
            raise ValueError(f"Duplicate tool {spec.name}")
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler

    def specs(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def spec(self, name: str) -> ToolSpec | None:
        return self._specs.get(name) or next((s for s in self._specs.values() if s.mcp_name == name), None)

    def invoke(self, name: str, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        spec = self.spec(name)
        env = self.settings.environment.value
        base = {"environment": env, "correlation_id": ctx.correlation_id, "workflow_id": ctx.workflow_id}
        if spec is None:
            return ToolResult(tool=name, state="ERROR", error_code="UNKNOWN_TOOL", **base)
        with span(f"tool.{spec.name}", self.settings.log_dir, trace_id=ctx.correlation_id, tool=spec.name,
                  connector=spec.connector, specialist=ctx.specialist_id, workflow_id=ctx.workflow_id,
                  runtime=ctx.runtime, environment=env, impact=str(spec.impact)) as sp:
            result = self._invoke(spec, args, ctx, base)
            sp.set(state=result.state, decision=result.decision)
            if not result.succeeded and result.state not in {"APPROVAL_REQUIRED"}:
                sp.fail(result.error_code or result.state, result=result.state)
        self.store.record_tool_call(
            correlation_id=ctx.correlation_id, workflow_id=ctx.workflow_id, specialist=ctx.specialist_id,
            tool=spec.name, connector=spec.connector, impact=str(spec.impact), decision=result.decision or "-", state=result.state,
            environment=env, error_code=result.error_code,
        )
        return result

    def _invoke(self, spec: ToolSpec, args: dict[str, Any], ctx: ToolContext, base: dict[str, Any]) -> ToolResult:
        common = {"tool": spec.name, "impact": str(spec.impact), **base}
        try:
            validated = spec.input_model.model_validate(args or {})
        except ValidationError as exc:
            return ToolResult(state="INVALID_INPUT", error_code="INVALID_INPUT", detail=str(exc.errors()[:3]), **common)
        payload = validated.model_dump(mode="json")
        digest = payload_hash(spec.name, payload)
        try:
            specialist: Specialist = get_specialist(ctx.specialist_id)
        except KeyError:
            return ToolResult(state="DENIED", decision=str(Decision.DENY), detail="Unknown specialist.", **common)

        approval: ApprovalRecord | None = self.approvals.refresh(ctx.approval_id) if ctx.approval_id else None
        verdict = self.policy.decide(
            tool=spec.name, namespace=spec.namespace, impact=spec.impact, specialist=specialist,
            environment=self.settings.environment, safe_dry_run=self.settings.safe_dry_run,
            payload_digest=digest, approval=approval,
            direct_user_publish=ctx.direct_user_publish,
        )
        common["decision"] = str(verdict.decision)
        if verdict.decision is Decision.DENY:
            return ToolResult(state="DENIED", detail=verdict.reason, **common)
        if verdict.decision is Decision.REQUIRE_APPROVAL:
            if approval is not None and approval.status == "PENDING" and approval.payload_hash == digest:
                record = approval  # still waiting on the same request; do not spam new codes
            else:
                summary = spec.summarize(payload) if spec.summarize else json.dumps(payload, ensure_ascii=False)[:600]
                record = self.approvals.request(
                    tool=spec.name, target_system=spec.connector, impact=spec.impact, payload=payload, summary=summary,
                    requested_by=ctx.specialist_id, workflow_id=ctx.workflow_id, user_id=ctx.user_id, channel_id=ctx.channel_id,
                )
            return ToolResult(state="APPROVAL_REQUIRED", detail=verdict.reason,
                              approval=record.model_dump(include={"approval_id", "code", "payload_summary", "expires_at", "status"}),
                              **common)

        key = None
        if spec.impact is not Impact.READ:
            key = ctx.idempotency_key or hashlib.sha256(
                f"{ctx.workflow_id or ctx.correlation_id}|{digest}".encode()).hexdigest()
            prior = self.store.idempotent_result(key)
            if prior is not None:
                return ToolResult(state="DUPLICATE", data=prior, idempotency_key=key,
                                  detail="Already executed with this idempotency key; returning the first result.", **common)

        runtime = HubRuntime(settings=self.settings, registry=self.registry, ctx=ctx,
                             artifacts_dir=self.settings.data_dir / "artifacts")
        try:
            data = self._handlers[spec.name](validated, runtime)
        except ToolUnavailable as exc:
            return ToolResult(state=exc.state, detail=exc.detail, error_code=exc.state, **common)
        except NotImplementedError as exc:
            return ToolResult(state="NOT_IMPLEMENTED", detail=str(exc), error_code="NOT_IMPLEMENTED", **common)
        except Exception as exc:  # provider failure: surface a code, never crash the runtime
            return ToolResult(state="ERROR", detail="Tool failed; see redacted log.", error_code=type(exc).__name__, **common)

        if key:
            self.store.remember_result(key, spec.name, ctx.workflow_id, data)
        if spec.impact is Impact.HIGH_IMPACT and approval is not None:
            self.approvals.consume(approval.approval_id)
        return ToolResult(state="MOCK" if runtime.mock else "OK", data=data, idempotency_key=key, **common)
