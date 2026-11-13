"""
Two-Axis Scoring Engine for Minh Van Logistics & Buzz Marketing OS.
Scores prospects on two distinct axes:
1. Data Quality Score (0-100): Verifiable factual completeness (VAT, Domain, Address, Contact).
2. Commercial Fit Score (0-100): Strategic ICP fit for Air Cargo & Specialized Clearance.
"""
from __future__ import annotations

from typing import Dict, Literal
from pydantic import BaseModel, Field

from ..models import LeadCandidate


class ScoreCard(BaseModel):
    data_quality_score: int = Field(ge=0, le=100)
    commercial_fit_score: int = Field(ge=0, le=100)
    composite_score: int = Field(ge=0, le=100)
    tier: Literal["Tier 1 - High Priority", "Tier 2 - Qualified", "Tier 3 - Nurture", "Disqualified"]
    breakdown: Dict[str, int] = Field(default_factory=dict)
    reason: str = ""


class TwoAxisScorer:
    def score_candidate(self, candidate: LeadCandidate) -> ScoreCard:
        candidate.stage = "SCORING"
        dq_breakdown: Dict[str, int] = {}
        cf_breakdown: Dict[str, int] = {}

        # ----------------- Axis 1: Data Quality Score (0-100) -----------------
        # 1. Legal Name
        if candidate.legal_name or (candidate.company and len(candidate.company) > 6):
            dq_breakdown["legal_name_verified"] = 25
        else:
            dq_breakdown["legal_name_verified"] = 0

        # 2. VAT Number (Tax Code)
        verified_fields = candidate.get_verified_fields()
        if "vat_number" in verified_fields:
            dq_breakdown["vat_number_verified"] = 25
        elif candidate.vat_number and len(candidate.vat_number) >= 10:
            dq_breakdown["vat_number_verified"] = 15
        else:
            dq_breakdown["vat_number_verified"] = 0

        # 3. Domain & Web Presence
        if "domain_active" in verified_fields or candidate.domain:
            dq_breakdown["domain_verified"] = 20
        else:
            dq_breakdown["domain_verified"] = 0

        # 4. Registered Address / Location
        if candidate.registered_address and len(candidate.registered_address) > 10:
            dq_breakdown["address_present"] = 15
        else:
            dq_breakdown["address_present"] = 0

        # 5. Direct Contact Profile (Name + Email / Phone)
        contact_pts = 0
        if candidate.contact_name:
            contact_pts += 5
        if candidate.title:
            contact_pts += 3
        if candidate.email or candidate.phone:
            contact_pts += 7
        dq_breakdown["contact_profile"] = min(contact_pts, 15)

        dq_score = sum(dq_breakdown.values())

        # ----------------- Axis 2: Commercial Fit Score (0-100) -----------------
        # 1. Industry ICP Alignment (Minh Van focus: Medical, Pharma, Tech)
        ind_code = candidate.industry_code or ""
        comp_name = (candidate.company or "").lower()
        if ind_code in ("3250", "4659") or any(k in comp_name for k in ["thiết bị y tế", "y tế", "dược phẩm", "sinh học"]):
            cf_breakdown["industry_icp_alignment"] = 40  # Top tier ICP: Medical/Pharma
        elif ind_code == "2611" or any(k in comp_name for k in ["điện tử", "linh kiện", "bán dẫn", "quang điện tử"]):
            cf_breakdown["industry_icp_alignment"] = 35  # High tier ICP: Electronics
        elif ind_code in ("4651", "4652") or "công nghệ" in comp_name:
            cf_breakdown["industry_icp_alignment"] = 25  # Mid tier
        else:
            cf_breakdown["industry_icp_alignment"] = 10  # General cargo

        # 2. Volume Suitability (Air Cargo Fit)
        inferred = candidate.get_inferred_fields()
        air_cargo = inferred.get("air_cargo_flow") or {}
        est_kg = (air_cargo.get("est_monthly_kg") or 0) if isinstance(air_cargo, dict) else 0
        if est_kg >= 1000:
            cf_breakdown["air_volume_fit"] = 25
        elif est_kg >= 300:
            cf_breakdown["air_volume_fit"] = 18
        elif cf_breakdown["industry_icp_alignment"] >= 35:
            cf_breakdown["air_volume_fit"] = 15  # Inferred high air volume from industry
        else:
            cf_breakdown["air_volume_fit"] = 5

        # 3. Trade Lane Alignment (JP, KR, CN, EU, US to Vietnam airports)
        route = air_cargo.get("route", "") if isinstance(air_cargo, dict) else ""
        if any(lane in route for lane in ["JP", "KR", "CN", "EU", "US"]):
            cf_breakdown["trade_lane_alignment"] = 20
        elif any(hub in route for hub in ["HAN", "SGN"]):
            cf_breakdown["trade_lane_alignment"] = 15
        elif cf_breakdown["industry_icp_alignment"] >= 35:
            cf_breakdown["trade_lane_alignment"] = 15  # Major lane standard for these industries
        else:
            cf_breakdown["trade_lane_alignment"] = 5

        # 4. Customs & Value-Added Services Requirement
        if cf_breakdown["industry_icp_alignment"] >= 35:
            cf_breakdown["specialized_clearance_need"] = 15
        else:
            cf_breakdown["specialized_clearance_need"] = 5

        cf_score = sum(cf_breakdown.values())

        # ----------------- Composite Score & Tiering -----------------
        composite = round(dq_score * 0.4 + cf_score * 0.6)
        composite = max(0, min(100, composite))

        if composite >= 80 and dq_score >= 70:
            tier = "Tier 1 - High Priority"
            reason = "Doanh nghiệp chuẩn ICP Vận tải Hàng không & Thông quan chuyên trách, dữ liệu pháp nhân đã xác thực đầy đủ."
        elif composite >= 60 and dq_score >= 50:
            tier = "Tier 2 - Qualified"
            reason = "Doanh nghiệp có tiềm năng thương mại tốt, dữ liệu cơ bản hợp lệ, cần bổ sung thêm thông tin vận hành."
        elif composite >= 40:
            tier = "Tier 3 - Nurture"
            reason = "Tiềm năng trung bình hoặc chưa đủ thông tin xác thực, đưa vào danh sách nuôi dưỡng dài hạn."
        else:
            tier = "Disqualified"
            reason = "Không phù hợp với năng lực vận tải chuyên trách của Minh Vân hoặc thiếu thông tin định danh pháp lý."

        full_breakdown = {**dq_breakdown, **cf_breakdown}

        # Update candidate properties
        candidate.score = composite
        candidate.data_quality_score = dq_score
        candidate.commercial_fit_score = cf_score
        candidate.score_breakdown = full_breakdown
        candidate.score_reason = reason
        candidate.stage = "READY_FOR_REVIEW" if tier in ("Tier 1 - High Priority", "Tier 2 - Qualified") else "SCORING"

        return ScoreCard(
            data_quality_score=dq_score,
            commercial_fit_score=cf_score,
            composite_score=composite,
            tier=tier,
            breakdown=full_breakdown,
            reason=reason,
        )
