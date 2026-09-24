"""Deterministic workflow engine.

State lives in SQLite (WorkflowStore), never in an LLM context. Each step's
output is persisted before the next step starts, so any process can resume a
workflow after a crash or restart. Transitions are validated against a table.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Literal
from uuid import uuid4

from pydantic import BaseModel

from ..config import Settings
from ..runtime import AgentRuntime, ConversationInput, RuntimeResult
from ..specialists import get_specialist
from ..telemetry import new_correlation_id, span
from ..tools.hub import ToolContext, ToolHub, ToolResult
from .approvals import APPROVED, EXPIRED, PENDING, REJECTED, ApprovalEngine, payload_hash
from .store import WorkflowStore

NEW, PLANNED, RUNNING, WAITING_APPROVAL, APPROVED_S, RESUMING, DONE, BLOCKED, FAILED, CANCELLED = (
    "NEW", "PLANNED", "RUNNING", "WAITING_APPROVAL", "APPROVED", "RESUMING", "DONE", "BLOCKED", "FAILED", "CANCELLED")

TRANSITIONS: dict[str, set[str]] = {
    NEW: {PLANNED, CANCELLED, FAILED},
    PLANNED: {RUNNING, CANCELLED},
    RUNNING: {WAITING_APPROVAL, DONE, BLOCKED, FAILED, CANCELLED},
    WAITING_APPROVAL: {APPROVED_S, CANCELLED, BLOCKED},
    APPROVED_S: {RESUMING},
    RESUMING: {RUNNING, FAILED},
    BLOCKED: {RESUMING, CANCELLED},
    DONE: set(), FAILED: set(), CANCELLED: set(),
}
TERMINAL = {DONE, FAILED, CANCELLED}


class StepOutcome(BaseModel):
    status: Literal["done", "wait_approval", "blocked", "failed"]
    output: Any = None
    detail: str = ""
    approval_id: str | None = None


@dataclass
class StepContext:
    engine: "WorkflowEngine"
    workflow: dict[str, Any]
    outputs: dict[str, Any]
    specialist: str

    @property
    def params(self) -> dict[str, Any]:
        return self.workflow["params"]

    @property
    def environment(self) -> str:
        return self.workflow["environment"]

    def tool(self, name: str, args: dict[str, Any], *, idempotency_key: str | None = None,
             use_approval: bool = False, specialist: str | None = None) -> ToolResult:
        ctx = ToolContext(
            correlation_id=self.workflow["correlation_id"], workflow_id=self.workflow["workflow_id"],
            specialist_id=specialist or self.specialist, user_id=self.workflow.get("user_id"),
            channel_id=self.workflow.get("channel_id"), runtime=self.engine.runtime.name,
            approval_id=self.workflow.get("approval_id") if use_approval else None,
            idempotency_key=idempotency_key,
        )
        return self.engine.hub.invoke(name, args, ctx)

    def ask(self, text: str, *, specialist: str | None = None, expect_json: bool = False) -> RuntimeResult:
        who = get_specialist(specialist or self.specialist)
        request = ConversationInput(text=text, correlation_id=self.workflow["correlation_id"],
                                    workflow_id=self.workflow["workflow_id"], source="workflow",
                                    user_id=self.workflow.get("user_id"), channel_id=self.workflow.get("channel_id"),
                                    expect_json=expect_json, metadata={"language_only": True})
        with span("runtime.invoke_specialist", self.engine.settings.log_dir, trace_id=self.workflow["correlation_id"],
                  runtime=self.engine.runtime.name, specialist=who.id, workflow_id=self.workflow["workflow_id"]) as sp:
            result = self.engine.runtime.invoke_specialist(who, request)
            sp.set(model=result.model, ok=result.ok)
            if not result.ok:
                sp.fail(result.error_code or "RUNTIME_ERROR")
        return result

    def gate(self, action: str, payload: Any, summary: str) -> StepOutcome:
        """Human approval gate bound to `payload`. Re-entrant: on resume it checks the same approval."""
        digest = payload_hash(action, payload)
        approval_id = self.workflow.get("approval_id")
        if approval_id:
            record = self.engine.approvals.get(approval_id)
            if record and record.requested_action == action:
                if record.status == APPROVED and record.payload_hash == digest and not record.expired():
                    return StepOutcome(status="done", output={"approval_id": record.approval_id, "decided_by": record.decided_by,
                                                              "decided_via": record.decided_via})
                if record.status == PENDING and record.payload_hash == digest:
                    return StepOutcome(status="wait_approval", approval_id=record.approval_id, detail=record.code)
        record = self.engine.approvals.request(
            tool=action, target_system="workflow", impact=_gate_impact(), payload=payload, summary=summary,
            requested_by=self.specialist, workflow_id=self.workflow["workflow_id"],
            user_id=self.workflow.get("user_id"), channel_id=self.workflow.get("channel_id"))
        return StepOutcome(status="wait_approval", approval_id=record.approval_id, detail=record.code)


def _gate_impact():
    from ..constants import Impact

    return Impact.WRITE_LOW_RISK


StepFn = Callable[[StepContext], StepOutcome]


@dataclass
class WorkflowStep:
    name: str
    specialist: str
    run: StepFn


@dataclass
class WorkflowDefinition:
    workflow_type: str
    description: str
    steps: list[WorkflowStep]
    finalize: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] = field(default=lambda wf, out: out)

    @property
    def specialists(self) -> list[str]:
        seen: list[str] = []
        for step in self.steps:
            if step.specialist not in seen:
                seen.append(step.specialist)
        return seen


class WorkflowEngine:
    def __init__(self, settings: Settings, store: WorkflowStore, hub: ToolHub, approvals: ApprovalEngine,
                 runtime: AgentRuntime, definitions: dict[str, WorkflowDefinition]):
        self.settings = settings
        self.store = store
        self.hub = hub
        self.approvals = approvals
        self.runtime = runtime
        self.definitions = definitions
        # When True (MCP server), advance/resume run on a background thread and return immediately;
        # state is durable, so callers poll with status(). Tests and CLI keep synchronous behaviour.
        self.background = False
        self._active: set[str] = set()
        self._active_lock = threading.Lock()

    # ------------------------------------------------------------------ API
    def start(self, workflow_type: str, request: str, *, params: dict[str, Any] | None = None,
              correlation_id: str | None = None, user_id: str | None = None, channel_id: str | None = None,
              run: bool = True) -> dict[str, Any]:
        if os.getenv("MARKETING_NESTED") == "1":
            raise RuntimeError("Refusing to start a workflow from inside a runtime call (recursion guard).")
        definition = self.definitions[workflow_type]
        for active in self.store.list_workflows((NEW, PLANNED, RUNNING, RESUMING), limit=200):
            if active["workflow_type"] == workflow_type and active["request"] == request:
                return self.status(active["workflow_id"])  # same request already in flight: never fan out
        workflow_id = "wf-" + uuid4().hex[:12]
        self.store.create_workflow({
            "workflow_id": workflow_id, "correlation_id": correlation_id or new_correlation_id(),
            "workflow_type": workflow_type, "environment": self.settings.environment.value,
            "user_id": user_id, "channel_id": channel_id, "request": request, "params": params or {},
            "specialists": definition.specialists, "state": NEW,
        })
        self._move(workflow_id, NEW, PLANNED, "plan: " + ", ".join(s.name for s in definition.steps))
        if not run:
            return self.status(workflow_id)
        return self._dispatch(self.advance, workflow_id)

    def _dispatch(self, fn, workflow_id: str) -> dict[str, Any]:
        if not self.background:
            return fn(workflow_id)
        with self._active_lock:
            if workflow_id in self._active:
                return self.status(workflow_id)  # already being advanced in this process
            self._active.add(workflow_id)

        def run() -> None:
            try:
                fn(workflow_id)
            except Exception:  # state is persisted; a failed thread leaves the workflow resumable
                pass
            finally:
                with self._active_lock:
                    self._active.discard(workflow_id)

        threading.Thread(target=run, name=f"workflow-{workflow_id}", daemon=True).start()
        return self.status(workflow_id)

    def resume_async(self, workflow_id: str) -> dict[str, Any]:
        return self._dispatch(self.resume, workflow_id)

    def advance(self, workflow_id: str) -> dict[str, Any]:
        wf = self._require(workflow_id)
        if wf["state"] in (PLANNED, RESUMING):
            self._move(workflow_id, wf["state"], RUNNING, "run")
        elif wf["state"] != RUNNING:  # RUNNING here means recovery after a crash mid-step
            return self.status(workflow_id)
        definition = self.definitions[wf["workflow_type"]]
        with span("workflow.advance", self.settings.log_dir, trace_id=wf["correlation_id"], workflow_id=workflow_id,
                  workflow_type=wf["workflow_type"], runtime=self.runtime.name, environment=wf["environment"]):
            while True:
                wf = self._require(workflow_id)
                index = wf["current_step"]
                if index >= len(definition.steps):
                    outputs = self.store.step_outputs(workflow_id)
                    self._move(workflow_id, RUNNING, DONE, "all steps done", result=definition.finalize(wf, outputs))
                    break
                step = definition.steps[index]
                self.store.start_step(workflow_id, index, step.name)
                ctx = StepContext(self, wf, self.store.step_outputs(workflow_id), step.specialist)
                with span(f"workflow.step.{step.name}", self.settings.log_dir, trace_id=wf["correlation_id"],
                          workflow_id=workflow_id, specialist=step.specialist) as sp:
                    try:
                        outcome = step.run(ctx)
                    except Exception as exc:
                        outcome = StepOutcome(status="failed", detail=type(exc).__name__)
                    sp.set(step_status=outcome.status)
                if outcome.status == "done":
                    self.store.finish_step(workflow_id, index, "DONE", outcome.output)
                    self.store.set_fields(workflow_id, current_step=index + 1, approval_id=None)
                    continue
                if outcome.status == "wait_approval":
                    self.store.finish_step(workflow_id, index, "WAITING_APPROVAL", {"approval_id": outcome.approval_id})
                    self._move(workflow_id, RUNNING, WAITING_APPROVAL, f"approval {outcome.detail}", approval_id=outcome.approval_id)
                    break
                state = BLOCKED if outcome.status == "blocked" else FAILED
                self.store.finish_step(workflow_id, index, state, {"detail": outcome.detail, "output": outcome.output})
                self._move(workflow_id, RUNNING, state, f"{step.name}: {outcome.detail}", error=f"{step.name}: {outcome.detail}")
                break
        return self.status(workflow_id)

    def resume(self, workflow_id: str) -> dict[str, Any]:
        """Deterministic: resumes only if the bound approval was verified by an ApprovalVerifier."""
        wf = self._require(workflow_id)
        if wf["state"] == WAITING_APPROVAL and wf["approval_id"]:
            record = self.approvals.refresh(wf["approval_id"])
            if record is None or record.status == PENDING:
                return self.status(workflow_id)
            if record.status == APPROVED:
                self._move(workflow_id, WAITING_APPROVAL, APPROVED_S, f"approved via {record.decided_via}")
                self._move(workflow_id, APPROVED_S, RESUMING, "resume")
                return self.advance(workflow_id)
            if record.status in (REJECTED,):
                self._move(workflow_id, WAITING_APPROVAL, CANCELLED, "rejected by owner", error="REJECTED")
            elif record.status == EXPIRED:
                self._move(workflow_id, WAITING_APPROVAL, BLOCKED, "approval expired", error="APPROVAL_EXPIRED",
                           approval_id=None)
            return self.status(workflow_id)
        if wf["state"] == BLOCKED:
            self._move(workflow_id, BLOCKED, RESUMING, "retry after block", error=None)
            return self.advance(workflow_id)
        if wf["state"] == RUNNING:
            return self.advance(workflow_id)
        return self.status(workflow_id)

    def cancel(self, workflow_id: str, reason: str = "cancelled") -> dict[str, Any]:
        wf = self._require(workflow_id)
        if wf["state"] in TERMINAL:
            return self.status(workflow_id)
        if wf.get("approval_id"):
            self.approvals.cancel(wf["approval_id"])
        self._move(workflow_id, wf["state"], CANCELLED, reason, error=reason)
        return self.status(workflow_id)

    def recover(self) -> list[str]:
        """Called at process start: finish interrupted steps and pick up decided approvals."""
        touched = []
        for wf in self.store.list_workflows((RUNNING, RESUMING, PLANNED, WAITING_APPROVAL), limit=500):
            before = wf["state"]
            if before in (PLANNED, RESUMING, RUNNING):
                self.advance(wf["workflow_id"])
            else:
                self.resume(wf["workflow_id"])
            if self._require(wf["workflow_id"])["state"] != before:
                touched.append(wf["workflow_id"])
        return touched

    def status(self, workflow_id: str) -> dict[str, Any]:
        wf = self._require(workflow_id)
        approval = self.approvals.get(wf["approval_id"]) if wf.get("approval_id") else None
        return {
            "workflow_id": wf["workflow_id"], "correlation_id": wf["correlation_id"], "type": wf["workflow_type"],
            "state": wf["state"], "environment": wf["environment"], "current_step": wf["current_step"],
            "specialists": wf["specialists"], "steps": self.store.steps(workflow_id),
            "approval": approval.model_dump(include={"approval_id", "code", "status", "payload_summary", "expires_at"}) if approval else None,
            "result": wf["result"], "error": wf["error"],
        }

    # --------------------------------------------------------------- internals
    def _require(self, workflow_id: str) -> dict[str, Any]:
        wf = self.store.get_workflow(workflow_id)
        if wf is None:
            raise KeyError(f"Unknown workflow {workflow_id}")
        return wf

    def _move(self, workflow_id: str, from_state: str, to_state: str, reason: str, **fields: Any) -> None:
        if to_state not in TRANSITIONS[from_state]:
            raise RuntimeError(f"Illegal transition {from_state} -> {to_state}")
        self.store.transition(workflow_id, from_state, to_state, reason, **fields)
