"""Deterministic runtime for tests and MARKETING_ENVIRONMENT=mock workflows."""

from __future__ import annotations

import json
import re
from typing import Callable
from uuid import NAMESPACE_URL, uuid5

from .base import AgentRuntime, ConversationInput, RuntimeCapabilities, RuntimeHealth, RuntimeResult, extract_json

Responder = Callable[[ConversationInput], str]

_SPECIALIST = re.compile(r"specialist `([0-9a-z_]+)`")


def _default_responder(request: ConversationInput) -> str:
    match = _SPECIALIST.search(request.text)
    who = match.group(1) if match else "general"
    if "SCHEMA:EmailDraft" in request.text:
        company = "Quý công ty"
        for line in request.text.splitlines():
            if line.startswith("{") and '"company"' in line:
                company = json.loads(line).get("company") or company
                break
        return json.dumps({
            "subject": f"[MOCK] Minh Vân hỗ trợ vận chuyển cho {company}",
            "body": f"[MOCK – bản nháp tổng hợp] Kính gửi {company}, Minh Vân Logistics xin phép giới thiệu dịch vụ "
                    "forwarding door-to-door và thủ tục hải quan. Rất mong được trao đổi 15 phút vào tuần tới.",
        }, ensure_ascii=False)
    if request.expect_json:
        return json.dumps({"mock": True, "specialist": who, "summary": f"MOCK output for {who}"}, ensure_ascii=False)
    return f"MOCK[{who}] {request.text.splitlines()[-1][:200]}"


class MockRuntime(AgentRuntime):
    name = "mock"

    def __init__(self, responder: Responder | None = None, fail_with: str | None = None):
        self.responder = responder or _default_responder
        self.fail_with = fail_with
        self.calls: list[ConversationInput] = []
        self._sessions: dict[str, list[str]] = {}

    def run(self, request: ConversationInput) -> RuntimeResult:
        self.calls.append(request)
        if self.fail_with:
            return RuntimeResult(runtime=self.name, ok=False, correlation_id=request.correlation_id, error_code=self.fail_with)
        session_id = request.session_id or str(uuid5(NAMESPACE_URL, f"mock-session:{request.correlation_id}"))
        history = self._sessions.setdefault(session_id, [])
        history.append(request.text)
        text = self.responder(request)
        return RuntimeResult(
            runtime=self.name,
            ok=True,
            text=text,
            structured=extract_json(text) if request.expect_json else None,
            session_id=session_id,
            model="mock",
            correlation_id=request.correlation_id,
        )

    def session_turns(self, session_id: str) -> int:
        return len(self._sessions.get(session_id, []))

    def health(self) -> RuntimeHealth:
        return RuntimeHealth(runtime=self.name, state="READY", model="mock", buzz_transport="NOT_APPLICABLE")

    def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(one_shot=True, sessions=True, mcp_tools=False, buzz_transport=False, production_enabled=False)
