"""
Sales Handoff Engine for Minh Van Logistics BDM & AI Telesale Copilot.
Generates comprehensive prospect briefing dossiers and Sales Task proposals.
"""
from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from ..models import LeadCandidate, TaskProposal
from ..constants import Environment
from .reply_classifier import ReplyClassification


class SalesBriefingDossier(BaseModel):
    company_name: str
    vat_number: str
    contact_name: str
    contact_title: str
    contact_email: str
    contact_phone: str
    domain: str
    data_quality_score: int
    commercial_fit_score: int
    composite_score: int
    tier: str
    trade_lane: str
    est_monthly_volume: str
    recommended_service: str
    talking_points: List[str]
    objection_prep: Dict[str, str]
    task_proposal: TaskProposal


class SalesHandoffEngine:
    def generate_dossier(
        self,
        candidate: LeadCandidate,
        classification: Optional[ReplyClassification] = None,
        env: Environment = Environment.MOCK
    ) -> SalesBriefingDossier:
        # Extract verified facts
        vat = candidate.vat_number or "Chưa rõ"
        verified = candidate.get_verified_fields()
        inferred = candidate.get_inferred_fields()

        # Air flow & volume
        cargo = inferred.get("air_cargo_flow") or {}
        route = cargo.get("route", "Đông Bắc Á / Châu Âu -> HAN/SGN") if isinstance(cargo, dict) else "Đông Bắc Á -> HAN/SGN"
        est_kg = cargo.get("est_monthly_kg", 1500) if isinstance(cargo, dict) else 1500

        ind_code = candidate.industry_code or ""
        if ind_code == "3250" or "y tế" in (candidate.company or "").lower():
            recommended_svc = "Dịch vụ thông quan hỏa tốc & vận tải hàng không chuyên trách thiết bị y tế (Nghị định 98/07)"
            talking_points = [
                "Nhấn mạnh năng lực giải tỏa hàng trong 4 giờ tại sân bay Nội Bài/Tân Sơn Nhất.",
                "Đội ngũ am hiểu sâu thủ tục phân loại trang thiết bị y tế loại A/B/C/D.",
                "Cam kết trang bị thùng giữ nhiệt và thiết bị ghi nhiệt độ IoT hành trình (Cold chain).",
            ]
            objection_prep = {
                "Khách bảo đã có forwarder": "Hỏi về tỷ lệ bị trễ hạn thông quan hàng kiểm tra chuyên ngành và đề xuất chạy thử nghiệm 1 lô đối chứng.",
                "Khách chê giá cao": "Giải thích chi phí lưu kho sân bay 1 ngày đắt hơn nhiều so với chênh lệch cước của Minh Vân; Minh Vân bao trọn giải tỏa nhanh."
            }
        else:
            recommended_svc = "Dịch vụ Air Freight Express tuyến Đông Bắc Á giao hàng xuyên đêm KCN trước 08:00 sáng"
            talking_points = [
                "Cam kết hạn ngạch tải (Allotted Space) giữ chỗ ổn định mùa cao điểm.",
                "Xe tải chuyên dụng giao hàng thẳng dây chuyền sản xuất KCN.",
                "Cập nhật trạng thái chuyến bay tự động theo thời gian thực.",
            ]
            objection_prep = {
                "Khách bảo đã có hợp đồng năm": "Đề xuất làm forwarder dự phòng (Backup Partner) cho các lô hàng khẩn cấp khi đối tác cũ hết chỗ tải.",
            }

        # Create task proposal for sales copilot
        reason_text = (
            f"Ứng viên {candidate.company} đạt {candidate.score}/100 ({candidate.score_reason}). "
            f"Phản hồi: {classification.intent if classification else 'Tiềm năng cao'}"
        )
        task = TaskProposal(
            subject=f"Gọi tư vấn dịch vụ Air Freight cho {candidate.company}",
            related_company=candidate.legal_name or candidate.company,
            due_in_days=1,
            owner_hint="BDM Chuyên Trách",
            reason=reason_text,
            environment=env
        )

        return SalesBriefingDossier(
            company_name=candidate.legal_name or candidate.company,
            vat_number=vat,
            contact_name=candidate.contact_name or "Người phụ trách Logistics/XNK",
            contact_title=candidate.title or "Trưởng phòng Mua hàng",
            contact_email=candidate.email or "",
            contact_phone=candidate.phone or "",
            domain=candidate.domain or "",
            data_quality_score=candidate.data_quality_score,
            commercial_fit_score=candidate.commercial_fit_score,
            composite_score=candidate.score,
            tier="Tier 1 - High Priority" if candidate.score >= 80 else "Tier 2 - Qualified",
            trade_lane=route,
            est_monthly_volume=f"{est_kg:,} kg/tháng",
            recommended_service=recommended_svc,
            talking_points=talking_points,
            objection_prep=objection_prep,
            task_proposal=task
        )
