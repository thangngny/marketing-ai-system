"""AgentRuntime contract.

Business code (connectors, policy, workflows, models) depends on this module
only. Hermes, Claude, Codex and the mock are interchangeable implementations.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from ..specialists import Specialist


class ConversationInput(BaseModel):
    """Runtime-neutral request, produced by the Conversation Gateway."""

    text: str
    correlation_id: str
    source: str = "local"
    user_id: str | None = None
    channel_id: str | None = None
    buzz_event_id: str | None = None
    session_id: str | None = None
    workflow_id: str | None = None
    expect_json: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeResult(BaseModel):
    runtime: str
    ok: bool
    text: str = ""
    structured: dict[str, Any] | list[Any] | None = None
    session_id: str | None = None
    model: str | None = None
    specialist: str | None = None
    correlation_id: str
    latency_ms: float = 0.0
    error_code: str | None = None


class RuntimeHealth(BaseModel):
    runtime: str
    state: str  # READY | NEEDS_AUTH | NOT_INSTALLED | DEGRADED | ERROR
    model: str | None = None
    provider: str | None = None
    buzz_transport: str | None = None  # CONNECTED | STOPPED | NOT_APPLICABLE | UNKNOWN
    detail: str = ""


class RuntimeCapabilities(BaseModel):
    one_shot: bool = True
    sessions: bool = False
    mcp_tools: bool = False
    buzz_transport: bool = False
    production_enabled: bool = False


class AgentRuntime(ABC):
    name: str = "abstract"

    @abstractmethod
    def run(self, request: ConversationInput) -> RuntimeResult:
        """Execute one turn. Must never raise for provider/process failures."""

    def continue_session(self, session_id: str, request: ConversationInput) -> RuntimeResult:
        if not self.capabilities().sessions:
            return RuntimeResult(runtime=self.name, ok=False, correlation_id=request.correlation_id,
                                 error_code="SESSIONS_UNSUPPORTED")
        return self.run(request.model_copy(update={"session_id": session_id}))

    def invoke_specialist(self, specialist: Specialist, request: ConversationInput) -> RuntimeResult:
        prompt = specialist_prompt(specialist, request)
        result = self.run(request.model_copy(update={"text": prompt}))
        return result.model_copy(update={"specialist": specialist.id})

    def expose_tools(self) -> list[str]:
        from ..tools.catalog import build_hub  # local import: runtime must not depend on hub at import time

        return [spec.name for spec in build_hub().specs()]

    def cancel(self, session_id: str) -> bool:
        return False

    @abstractmethod
    def health(self) -> RuntimeHealth: ...

    @abstractmethod
    def capabilities(self) -> RuntimeCapabilities: ...


def specialist_prompt(specialist: Specialist, request: ConversationInput) -> str:
    lines = [
        f"[correlation_id={request.correlation_id}]",
        f"Bạn đang đóng vai specialist `{specialist.id}` ({specialist.name}): {specialist.purpose}",
        f"Namespace tool được phép: {', '.join(specialist.namespaces)}. Mức tác động tối đa: {specialist.max_impact}.",
        "Không gửi, đăng, chi tiền hay ghi CRM. Không bịa số liệu; ghi rõ khi dữ liệu là MOCK.",
    ]
    instructions = specialist.instructions()
    if instructions:
        lines += ["", "## Hướng dẫn specialist", instructions]
    lines += ["", "## Yêu cầu", request.text]
    if request.expect_json:
        lines += ["", f"Trả về DUY NHẤT một object JSON hợp lệ theo schema `{specialist.output_schema}`, không kèm văn bản khác."]
    return "\n".join(lines)


_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.S)


def extract_json(text: str) -> dict[str, Any] | list[Any] | None:
    """Best-effort structured output: fenced block first, then the outermost {...}."""
    candidates = [m.group(1) for m in _JSON_BLOCK.finditer(text)]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except ValueError:
            continue
    return None
