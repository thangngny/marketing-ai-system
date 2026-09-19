from __future__ import annotations

import time
from uuid import uuid4

from .config import Settings
from .connectors import ConnectorRegistry
from .fixtures import mock_logistics_leads
from .logging_utils import write_event
from .models import OrchestratorResult
from .routing import route_intent
from .safety import authorize
from .storage import StagingStore


class MarketingOrchestrator:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.from_env()
        self.settings.ensure_runtime_dirs()
        self.registry = ConnectorRegistry(self.settings)
        self.store = StagingStore(self.settings.data_dir / "marketing.db")

    def status(self) -> dict[str, object]:
        reports = self.registry.reports(live_probe=False)
        return {
            "environment": self.settings.environment.value,
            "safe_dry_run": self.settings.safe_dry_run,
            "connectors": [report.model_dump(mode="json") for report in reports],
        }

    def handle(self, text: str, source_channel: str = "local") -> OrchestratorResult:
        started = time.perf_counter()
        correlation_id = str(uuid4())
        route = route_intent(text)
        result = self._dispatch(route.intent, route.agents, text, correlation_id)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        write_event(
            self.settings.log_dir,
            correlation_id=correlation_id,
            source_channel=source_channel,
            orchestrator="marketing_orchestrator",
            agent=route.agents,
            tool="marketing_handle_request",
            connector=self._connector_for_intent(route.intent),
            mode=self.settings.environment.value,
            duration_ms=duration_ms,
            result=result.result_state,
        )
        return result

    def _dispatch(
        self, intent: str, agents: list[str], text: str, correlation_id: str
    ) -> OrchestratorResult:
        if intent == "system_status":
            status = self.status()
            lines = [
                f"Chế độ: {str(status['environment']).upper()} | SAFE_DRY_RUN: {status['safe_dry_run']}",
                "",
                "| Connector | Hiện tại | Live |",
                "|---|---|---|",
            ]
            for item in status["connectors"]:  # type: ignore[index]
                lines.append(f"| {item['connector']} | {item['current_state']} | {item['live_state']} |")
            lines.append("\nCác trạng thái MOCK_READY không phải kết nối live.")
            return self._result(correlation_id, intent, agents, "PASS_MOCK", "\n".join(lines))

        if intent == "lead_search":
            if self.settings.environment.value != "mock":
                return self._result(
                    correlation_id,
                    intent,
                    agents,
                    "SKIPPED_NEEDS_AUTH",
                    "Apollo/Zoho live chưa được xác thực. Không thực hiện tìm kiếm live.",
                )
            leads = mock_logistics_leads(correlation_id, limit=3)
            for lead in leads:
                self.store.upsert(lead)
            rows = [
                "Dữ liệu dưới đây là **MOCK / tổng hợp hoàn toàn**, không phải người hay công ty thật.",
                "",
                "Agent xử lý: `03_account_intelligence` → Mock Apollo → canonical Lead → SQLite staging/mock Zoho.",
                "",
            ]
            for index, lead in enumerate(leads, 1):
                rows.append(
                    f"{index}. **{lead.metadata['company']}** — {lead.full_name}, {lead.title}; "
                    f"điểm {lead.score}/100 ({lead.qualification}). {lead.score_reason}"
                )
            rows.append("\nKhông có outreach hoặc ghi Zoho live nào được thực hiện.")
            return self._result(
                correlation_id,
                intent,
                agents,
                "PASS_MOCK",
                "\n".join(rows),
                records=[lead.model_dump(mode="json") for lead in leads],
            )

        if intent == "content":
            response = (
                "Agent xử lý: `04_content`.\n\n"
                "**BẢN NHÁP — CHƯA ĐĂNG**\n\n"
                "Một lô hàng chậm không chỉ làm trễ lịch giao. Nó còn kéo theo tồn kho, "
                "dòng tiền và niềm tin của khách hàng.\n\n"
                "Dịch vụ forwarding tốt bắt đầu từ khả năng nhìn thấy rủi ro sớm: chọn tuyến phù hợp, "
                "theo dõi mốc vận chuyển và chủ động xử lý ngoại lệ trước khi chúng trở thành sự cố.\n\n"
                "Chúng tôi đang xây cách làm forwarding minh bạch hơn cho doanh nghiệp xuất nhập khẩu: "
                "một đầu mối, trạng thái rõ ràng và phương án dự phòng có căn cứ.\n\n"
                "Nếu doanh nghiệp của bạn đang rà soát tuyến vận chuyển, hãy chia sẻ tuyến đi, tần suất và "
                "điểm nghẽn hiện tại — chúng tôi sẽ chuẩn bị một phương án để cùng trao đổi.\n\n"
                "#Forwarding #Logistics #SupplyChain #XuatNhapKhau\n\n"
                "Trạng thái: DRAFT. Không xuất bản lên LinkedIn."
            )
            return self._result(correlation_id, intent, agents, "PASS_MOCK", response)

        if intent == "campaign":
            decision = authorize(
                "launch_ad_campaign",
                self.settings.environment,
                self.settings.safe_dry_run,
                explicit_approval=False,
            )
            response = (
                "Agent xử lý: `01_strategy` + `07_campaign`.\n\n"
                "**KẾ HOẠCH/BẢN NHÁP — KHÔNG KHỞI CHẠY**\n\n"
                "- Mục tiêu: tạo lead đủ chuẩn cho dịch vụ forwarding.\n"
                "- Ngân sách đề xuất: 10.000.000 VND; chưa phân bổ và chưa cam kết chi.\n"
                "- Cấu trúc thử nghiệm: 2 nhóm đối tượng × 2 thông điệp, ngân sách nhỏ theo giai đoạn.\n"
                "- Tài sản: landing-page brief, 4 mẫu quảng cáo, form lead và UTM plan.\n"
                "- KPI: CPL, tỷ lệ lead→MQL, MQL→meeting; không tối ưu chỉ theo click.\n"
                "- Cổng duyệt: tài khoản Meta, audience, creative, tracking, lịch chạy và ngân sách cuối.\n\n"
                f"Chặn thực thi: {decision.reason} Cần credential live và phê duyệt rõ ràng trước mọi chi tiêu."
            )
            return self._result(
                correlation_id,
                intent,
                agents,
                "PASS_MOCK",
                response,
                approval_required=True,
            )

        response = (
            f"Đã định tuyến tới: {', '.join(f'`{agent}`' for agent in agents)}. "
            "Hệ thống hiện ở MOCK + SAFE_DRY_RUN; đây là kế hoạch nội bộ, không có hành động bên ngoài."
        )
        return self._result(correlation_id, intent, agents, "PASS_MOCK", response)

    def _result(
        self,
        correlation_id: str,
        intent: str,
        agents: list[str],
        state: str,
        response: str,
        records: list[dict[str, object]] | None = None,
        approval_required: bool = False,
    ) -> OrchestratorResult:
        return OrchestratorResult(
            correlation_id=correlation_id,
            environment=self.settings.environment,
            result_state=state,
            intent=intent,
            agents=agents,
            response=response,
            records=records or [],
            approval_required=approval_required,
            side_effects=[],
        )

    @staticmethod
    def _connector_for_intent(intent: str) -> str | None:
        return {
            "lead_search": "apollo+zoho",
            "campaign": "meta_ads/google_ads",
            "content": "linkedin",
        }.get(intent)

