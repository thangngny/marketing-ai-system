"""Orchestrator: route → fast path (tools) | durable workflow | specialist brief for the runtime.

Deterministic parts (routing, data reads, policy, workflow state) happen here.
Language work (drafting, analysis) is handed back to whichever AgentRuntime is
serving the conversation, as a specialist brief with its allowed tools.
"""

from __future__ import annotations

import os
from uuid import uuid4

from . import gateway
from .app import Platform, build_platform
from .capabilities import connector_status
from .config import Settings
from .connectors import ConnectorRegistry
from .logging_utils import write_event
from .models import OrchestratorResult, ReadonlySyncResult
from .routing import route_intent
from .specialists import get_specialist
from .storage import StagingStore
from .telemetry import span
from .tools.hub import ToolContext


class MarketingOrchestrator:
    def __init__(self, settings: Settings | None = None, platform: Platform | None = None):
        self.platform = platform or build_platform(settings)
        self.settings = self.platform.settings
        self.registry: ConnectorRegistry = self.platform.hub.registry
        self.store = StagingStore(self.settings.data_dir / "marketing.db")

    # ------------------------------------------------------------------ status
    def status(self) -> dict[str, object]:
        reports = self.registry.reports(live_probe=False)
        return {
            "environment": self.settings.environment.value,
            "safe_dry_run": self.settings.safe_dry_run,
            "runtime": self.platform.runtime.name,
            "connectors": [report.model_dump(mode="json") for report in reports],
            "capabilities": [connector_status(c, self.settings, self.platform.store).model_dump()
                             for c in self.registry._connectors.values()],
        }

    def overview(self) -> dict[str, object]:
        store = self.platform.store
        waiting = store.list_workflows(("WAITING_APPROVAL",))
        blocked = store.list_workflows(("BLOCKED", "FAILED"), limit=10)
        return {
            "environment": self.settings.environment.value,
            "runtime": self.platform.runtime.name,
            "capabilities": [connector_status(c, self.settings, store).model_dump() for c in self.registry._connectors.values()],
            "pending_approvals": [
                {k: a[k] for k in ("code", "requested_action", "payload_summary", "expires_at")}
                for a in store.list_approvals("PENDING")
            ],
            "waiting_workflows": [w["workflow_id"] for w in waiting],
            "alerts": [f"{w['workflow_id']} {w['state']}: {w['error']}" for w in blocked],
        }

    # ------------------------------------------------------------------ legacy live read
    def sync_readonly(self, connector_name: str, resource: str, limit: int = 25) -> ReadonlySyncResult:
        correlation_id = str(uuid4())
        if self.settings.environment.value == "mock":
            return ReadonlySyncResult(correlation_id=correlation_id, state="BLOCKED_MOCK_MODE", connector=connector_name,
                                      resource=resource, detail="Live reads are disabled while MARKETING_ENVIRONMENT=mock.")
        connector = self.registry.get(connector_name)
        report = connector.report(live_probe=True)
        if report.live_state.value != "CONNECTED":
            return ReadonlySyncResult(correlation_id=correlation_id, state="BLOCKED_NOT_CONNECTED", connector=connector_name,
                                      resource=resource, detail=report.detail)
        records = connector.read(resource, limit=limit, correlation_id=correlation_id)
        canonical = []
        for record in records:
            if not hasattr(record, "model_dump"):
                raise TypeError("Live connector returned a non-canonical record")
            self.store.upsert(record)
            canonical.append(record.model_dump(mode="json"))
        write_event(self.settings.log_dir, correlation_id=correlation_id, source_channel="mcp", tool="marketing_sync_readonly",
                    connector=connector_name, resource=resource, mode=self.settings.environment.value,
                    result="LIVE_VERIFIED_READ", record_count=len(canonical))
        return ReadonlySyncResult(correlation_id=correlation_id, state="LIVE_VERIFIED_READ", connector=connector_name,
                                  resource=resource, records=canonical,
                                  detail=f"Staged {len(canonical)} normalized record(s); no external writes were performed.")

    # ------------------------------------------------------------------ main entry
    def handle(self, text: str, source_channel: str = "local", *, event_id: str | None = None,
               channel_id: str | None = None, user_id: str | None = None) -> OrchestratorResult:
        request, duplicate = gateway.ingest(self.platform.store, text, source=source_channel, event_id=event_id,
                                            channel_id=channel_id, user_id=user_id)
        route = route_intent(request.text)
        if duplicate:
            return self._result(request.correlation_id, route.intent, route.agents, "DUPLICATE_EVENT",
                                "Sự kiện Buzz này đã được xử lý; bỏ qua bản lặp.")
        with span("orchestrator.handle", self.settings.log_dir, trace_id=request.correlation_id, source=source_channel,
                  buzz_event_id=request.buzz_event_id, channel_id=request.channel_id, user_id=request.user_id,
                  runtime=self.platform.runtime.name, environment=self.settings.environment.value,
                  intent=route.intent, specialists=",".join(route.agents)) as sp:
            result = self._dispatch(route, request)
            sp.set(result=result.result_state)
        return result

    def _dispatch(self, route, request) -> OrchestratorResult:
        cid, intent, agents = request.correlation_id, route.intent, route.agents
        env = self.settings.environment.value
        mock = env == "mock"

        if intent == "system_overview":
            data = self.overview()
            return self._result(cid, intent, agents, "PASS_MOCK" if mock else "PASS", _format_overview(data), data=data)

        if intent == "system_status":
            caps = self.status()["capabilities"]
            lines = [f"Chế độ: {env.upper()} | SAFE_DRY_RUN: {self.settings.safe_dry_run} | runtime: {self.platform.runtime.name}", "",
                     "| Connector | AUTH | READ | ANALYTICS | DRAFT | PUBLISH |", "|---|---|---|---|---|---|"]
            for c in caps:
                k = c["capabilities"]
                lines.append(f"| {c['connector']} | {k['AUTH']} | {k['READ']} | {k['ANALYTICS']} | {k['DRAFT']} | {k['PUBLISH']} |")
            lines.append("\nCác trạng thái MOCK_READY không phải kết nối live. LIVE_* chỉ có khi đã có lần đọc thật thành công.")
            return self._result(cid, intent, agents, "PASS_MOCK" if mock else "PASS", "\n".join(lines))

        if route.workflow_type:
            if os.getenv("MARKETING_NESTED") == "1":
                return self._result(cid, intent, agents, "REFUSED_NESTED",
                                    "Yêu cầu này đến từ bên trong một lần gọi runtime; không tạo workflow lồng nhau.")
            status = self.platform.engine.start(route.workflow_type, request.text, params=_params_from(request.text),
                                                correlation_id=cid, user_id=request.user_id,
                                                channel_id=request.channel_id or self.settings.buzz_channel)
            return self._result(cid, intent, agents, _state_label(status["state"], mock), _format_workflow(status),
                                data={"workflow": status}, approval_required=status["state"] == "WAITING_APPROVAL")

        if intent == "lead_search":
            ctx = ToolContext(correlation_id=cid, specialist_id="03_account_intelligence", runtime=self.platform.runtime.name)
            found = self.platform.hub.invoke("prospecting.search_companies", {"limit": 3}, ctx)
            if not found.succeeded:
                return self._result(cid, intent, agents, found.state,
                                    f"Không tìm được lead: `prospecting.search_companies` → **{found.state}**. {found.detail}")
            rows = ["Dữ liệu dưới đây là **MOCK / tổng hợp hoàn toàn**, không phải người hay công ty thật." if mock else "Dữ liệu live:",
                    "", "Agent xử lý: `03_account_intelligence` → prospecting → CRM dedupe.", ""]
            for index, lead in enumerate(found.data, 1):
                rows.append(f"{index}. **{lead['company']}** — {lead.get('contact_name')}, {lead.get('title')}. {lead.get('score_reason', '')}")
            rows.append("\nKhông có outreach hoặc ghi Zoho live nào được thực hiện.")
            return self._result(cid, intent, agents, "PASS_MOCK" if mock else "PASS", "\n".join(rows), records=found.data)

        if intent == "kpi_report":
            ctx = ToolContext(correlation_id=cid, specialist_id="08_kpi_learning", runtime=self.platform.runtime.name)
            snap = self.platform.hub.invoke("analytics.snapshot", {}, ctx)
            brief = self._brief(agents, request.text, extra="Chỉ dùng số liệu trong `data.metrics` (FACT). Phân biệt FACT / INFERENCE / HYPOTHESIS / RECOMMENDATION. "
                                                             "Nêu rõ các nguồn trong `data.unavailable` là chưa đo được, không ước đoán.")
            return self._result(cid, intent, agents, "PASS_MOCK" if mock else "PASS", brief["text"],
                                data={"snapshot": snap.data, "specialist_brief": brief["specialists"]})

        extra = ""
        if intent == "publish_social":
            extra = ("**LỆNH ĐĂNG BÀI TỪ NGƯỜI DÙNG.** Người dùng đã yêu cầu đăng bài: "
                     "Bạn ĐƯỢC PHÉP và CÓ QUYỀN xuất bản bài trực tiếp lên kênh ngay lập tức "
                     "(dùng `social_publish_post` hoặc CLI `facebook-control publish-post`, `tiktok-control publish-video`). "
                     "Hãy thực hiện đăng bài và trả lời người dùng kèm link/ID bài đăng.")
        elif intent in {"content", "competitive_campaign_content"}:
            extra = ("**BẢN NHÁP — CHƯA ĐĂNG.** Viết nội dung theo brief, lưu bằng `content_save_draft`. "
                     "Không xuất bản lên bất kỳ kênh nào.")
        if intent in {"campaign", "competitive_campaign_content"}:
            extra += (" **KẾ HOẠCH/BẢN NHÁP — KHÔNG KHỞI CHẠY.** Không tạo chiến dịch, không đổi ngân sách; "
                      "cần credential live và phê duyệt rõ ràng của owner trước mọi chi tiêu.")
        brief = self._brief(agents, request.text, extra=extra.strip())
        return self._result(cid, intent, agents, "PASS_MOCK" if mock else "PASS", brief["text"],
                            data={"specialist_brief": brief["specialists"]},
                            approval_required=False if intent == "publish_social" else (intent in {"campaign", "competitive_campaign_content"}))

    # ------------------------------------------------------------------ helpers
    def _brief(self, agents: list[str], text: str, extra: str = "") -> dict[str, object]:
        specialists = []
        for agent in agents:
            s = get_specialist(agent)
            tools = [t.mcp_name for t in self.platform.hub.specs() if s.allows(t.namespace, t.impact)]
            specialists.append({"id": s.id, "name": s.name, "purpose": s.purpose, "skill": s.skill,
                                "max_impact": str(s.max_impact), "tools": tools})
        lines = [f"Specialist: {', '.join(f'`{a}`' for a in agents) or '`01_strategy`'}.",
                 "Runtime hãy thực hiện yêu cầu theo skill của từng specialist, chỉ dùng tool được liệt kê trong `data.specialist_brief`."]
        if extra:
            lines += ["", extra]
        lines += ["", f"Yêu cầu: {text}"]
        return {"text": "\n".join(lines), "specialists": specialists}

    def _result(self, correlation_id: str, intent: str, agents: list[str], state: str, response: str,
                records: list | None = None, data: dict | None = None, approval_required: bool = False) -> OrchestratorResult:
        return OrchestratorResult(correlation_id=correlation_id, environment=self.settings.environment, result_state=state,
                                  intent=intent, agents=agents, response=response, records=records or [],
                                  approval_required=approval_required, side_effects=[], data=data or {},
                                  runtime=self.platform.runtime.name)


def _params_from(text: str) -> dict[str, object]:
    import re

    numbers = [int(n) for n in re.findall(r"\b(\d{1,3})\b", text)]
    params: dict[str, object] = {"industry": "logistics"}
    if numbers:
        params["count"] = min(max(numbers[0], 1), 25)
    if len(numbers) > 1:
        params["top_n"] = min(max(numbers[1], 1), 10)
    if re.search(r"xuất nhập khẩu|xuat nhap khau|import|export", text, re.I):
        params["industry"] = "import-export"
    return params


def _state_label(state: str, mock: bool) -> str:
    return {"DONE": "PASS_MOCK" if mock else "PASS", "WAITING_APPROVAL": "WAITING_APPROVAL"}.get(state, state)


def _format_workflow(status: dict) -> str:
    lines = [f"Workflow `{status['workflow_id']}` ({status['type']}) — **{status['state']}**"
             + (" · dữ liệu MOCK" if status["environment"] == "mock" else "")]
    for step in status["steps"]:
        lines.append(f"- {step['name']}: {step['state']}")
    if status["state"] == "WAITING_APPROVAL" and status["approval"]:
        a = status["approval"]
        lines += ["", f"**Cần owner duyệt:** {a['payload_summary']}",
                  f"Owner trả lời trong Buzz: `DUYET {a['code']}` hoặc `TUCHOI {a['code']}` (hết hạn {a['expires_at'][:16]} UTC).",
                  "Chỉ tin nhắn có chữ ký của owner mới được chấp nhận."]
    if status["error"]:
        lines += ["", f"Lý do dừng: {status['error']}"]
    if status["result"]:
        r = status["result"]
        lines += ["", f"Tìm thấy {r.get('found')} · loại vì đã có trong CRM: {', '.join(r.get('excluded_in_crm') or []) or 'không'}"]
        for c in r.get("top", []):
            lines.append(f"- **{c['company']}** — {c['score']}/100 ({c['reason']})")
        lines.append(f"Draft đã tạo: {len(r.get('drafts', []))} · đề xuất task: {len(r.get('task_proposals', []))} · "
                     f"email đã gửi: {r.get('emails_sent', 0)} · ghi CRM: {r.get('crm_writes', 0)}")
    return "\n".join(lines)


def _format_overview(data: dict) -> str:
    lines = [f"Chế độ {data['environment'].upper()} · runtime `{data['runtime']}`", "", "**Kết nối**"]
    for c in data["capabilities"]:
        k = c["capabilities"]
        lines.append(f"- {c['connector']}: READ {k['READ']} · PUBLISH {k['PUBLISH']}")
    lines += ["", f"**Chờ duyệt:** {len(data['pending_approvals'])}"]
    for a in data["pending_approvals"]:
        lines.append(f"- `{a['code']}` {a['payload_summary'][:140]}")
    if data["alerts"]:
        lines += ["", "**Cảnh báo**"] + [f"- {x}" for x in data["alerts"]]
    return "\n".join(lines)
