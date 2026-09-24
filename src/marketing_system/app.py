"""Composition root: the one place that wires store, approvals, hub, runtime and workflows."""

from __future__ import annotations

from dataclasses import dataclass

from .config import Settings
from .runtime import AgentRuntime, get_runtime
from .tools.catalog import build_hub
from .tools.hub import ToolHub
from .workflows.approvals import ApprovalEngine, ApprovalVerifier, BuzzSignedEventVerifier
from .workflows.definitions import DEFINITIONS
from .workflows.engine import WorkflowEngine
from .workflows.store import WorkflowStore


@dataclass
class Platform:
    settings: Settings
    store: WorkflowStore
    approvals: ApprovalEngine
    hub: ToolHub
    runtime: AgentRuntime
    engine: WorkflowEngine


def build_platform(settings: Settings | None = None, runtime: AgentRuntime | None = None,
                   verifiers: list[ApprovalVerifier] | None = None) -> Platform:
    settings = settings or Settings.from_env()
    settings.ensure_runtime_dirs()
    store = WorkflowStore(settings.data_dir / "marketing.db")
    approvals = ApprovalEngine(store, verifiers if verifiers is not None else [BuzzSignedEventVerifier(settings.owner_pubkey)])
    hub = build_hub(settings, store, approvals)
    runtime = runtime or get_runtime(environment=settings.environment.value)
    engine = WorkflowEngine(settings, store, hub, approvals, runtime, DEFINITIONS)
    return Platform(settings, store, approvals, hub, runtime, engine)
