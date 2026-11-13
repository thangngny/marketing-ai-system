"""
Two-Axis Scoring Engine for Minh Van Logistics & Buzz Marketing OS.
Scores prospects on two distinct axes:
1. Data Quality Score (0-100): Separates data completeness from factual verified evidence.
2. Commercial Fit Score (0-100): Strategic ICP fit for Air Cargo & Specialized Clearance.

INVARIANTS:
- A raw unverified string does not award full verification points.
- High commercial fit CANNOT bypass low data quality or missing legal identity.
- Tier 1 qualification strictly requires valid identification, active domain, non-duplicate CRM status.
"""
from __future__ import annotations

from typing import Dict, Literal
from pydantic import BaseModel, Field

from ..models import LeadCandidate, EvidenceStatus


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
        # Evaluate based on evidence quality rather than mere field presence
        evidence_map = {e.field_name: e for e in candidate.evidence}

        # 1. Legal Name / Company Identity (0-25)
        legal_ev = evidence_map.get("legal_name")
        if legal_ev and legal_ev.evidence_status == EvidenceStatus.VERIFIED:
            dq_breakdown["legal_name_verified"] = 25
        elif legal_ev and legal_ev.evidence_status == EvidenceStatus.SOURCE_CORROBORATED:
            dq_breakdown["legal_name_verified"] = 20
        elif legal_ev and legal_ev.evidence_status == EvidenceStatus.SOURCE_OBSERVED:
            dq_breakdown["legal_name_verified"] = 15
        elif candidate.company and len(candidate.company.strip()) >= 3:
            dq_breakdown["legal_name_verified"] = 8  # Raw unverified presence
        else:
            dq_breakdown["legal_name_verified"] = 0

        # 2. VAT Number (Tax Code) (0-25)
        vat_ev = evidence_map.get("vat_number")
        if vat_ev and vat_ev.evidence_status == EvidenceStatus.VERIFIED:
            dq_breakdown["vat_number_verified"] = 25
        elif vat_ev and vat_ev.evidence_status in (EvidenceStatus.FORMAT_VALID, EvidenceStatus.SOURCE_CORROBORATED):
            dq_breakdown["vat_number_verified"] = 20
        elif candidate.vat_number and len(candidate.vat_number.strip()) >= 10:
            dq_breakdown["vat_number_verified"] = 10
        else:
            dq_breakdown["vat_number_verified"] = 0

        # 3. Domain & Web Presence (0-20)
        dom_ev = evidence_map.get("domain_active")
        if dom_ev and dom_ev.evidence_status in (EvidenceStatus.VERIFIED, EvidenceStatus.SOURCE_CORROBORATED):
            dq_breakdown["domain_verified"] = 20
        elif dom_ev and dom_ev.evidence_status in (EvidenceStatus.FORMAT_VALID, EvidenceStatus.SOURCE_OBSERVED):
            dq_breakdown["domain_verified"] = 15
        elif candidate.domain:
            dq_breakdown["domain_verified"] = 8
        else:
            dq_breakdown["domain_verified"] = 0

        # 4. Registered Address / Location (0-15)
        if candidate.registered_address and len(candidate.registered_address.strip()) >= 10:
            dq_breakdown["address_present"] = 15
        elif candidate.registered_address:
            dq_breakdown["address_present"] = 5
        else:
            dq_breakdown["address_present"] = 0

        # 5. Direct Contact Profile (Name + Email / Phone) (0-15)
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
        # 1. Industry ICP Alignment (Minh Van focus: Medical, Pharma, High-tech)
        ind_code = candidate.industry_code or ""
        comp_name = (candidate.company or "").lower()
        if ind_code in ("3250", "4659") or any(k in comp_name for k in ["thiết bị y tế", "y tế", "dược phẩm", "sinh học"]):
            cf_breakdown["industry_icp_alignment"] = 40  # Top tier ICP: Medical/Pharma
        elif ind_code in ("2611", "2620") or any(k in comp_name for k in ["điện tử", "linh kiện", "bán dẫn", "quang điện tử"]):
            cf_breakdown["industry_icp_alignment"] = 35  # High tier ICP: Electronics
        elif ind_code in ("4651", "4652") or "công nghệ" in comp_name:
            cf_breakdown["industry_icp_alignment"] = 25  # Mid tier
        else:
            cf_breakdown["industry_icp_alignment"] = 10  # General cargo

        # 2. Volume Suitability (Air Cargo Fit)
        inferred = candidate.get_inferred_fields()
        air_cargo = inferred.get("air_cargo_flow") or {}
        if not air_cargo:
            for e in candidate.evidence:
                if e.field_name == "air_cargo_flow" and isinstance(e.field_value, dict):
                    air_cargo = e.field_value
                    break
        est_kg = (air_cargo.get("est_monthly_kg") or 0) if isinstance(air_cargo, dict) else 0
        if est_kg >= 1000:
            cf_breakdown["air_volume_fit"] = 25
        elif est_kg >= 300:
            cf_breakdown["air_volume_fit"] = 18
        elif cf_breakdown["industry_icp_alignment"] >= 35:
            cf_breakdown["air_volume_fit"] = 15
        else:
            cf_breakdown["air_volume_fit"] = 5

        # 3. Trade Lane Alignment (JP, KR, CN, EU, US to Vietnam airports)
        route = air_cargo.get("route", "") if isinstance(air_cargo, dict) else ""
        if any(lane in route for lane in ["JP", "KR", "CN", "EU", "US"]):
            cf_breakdown["trade_lane_alignment"] = 20
        elif any(hub in route for hub in ["HAN", "SGN"]):
            cf_breakdown["trade_lane_alignment"] = 15
        elif cf_breakdown["industry_icp_alignment"] >= 35:
            cf_breakdown["trade_lane_alignment"] = 15
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

        # INVARIANT: Strict Tier 1 Gate Requirements
        has_valid_vat = dq_breakdown.get("vat_number_verified", 0) >= 15
        has_valid_domain = dq_breakdown.get("domain_verified", 0) >= 12
        has_valid_company = dq_breakdown.get("legal_name_verified", 0) >= 15
        dedupe_status = getattr(candidate, "crm_dedupe_status", "NOT_CHECKED")
        is_dedupe_cleared = (dedupe_status == "NOT_FOUND_VERIFIED") and (not getattr(candidate, "in_crm", False))

        tier1_eligible = (
            composite >= 75
            and dq_score >= 65
            and cf_score >= 70
            and has_valid_vat
            and has_valid_domain
            and has_valid_company
            and is_dedupe_cleared
        )

        is_authoritative_verified = bool(
            legal_ev and legal_ev.evidence_status == EvidenceStatus.VERIFIED
            and vat_ev and vat_ev.evidence_status == EvidenceStatus.VERIFIED
        )

        if tier1_eligible:
            tier = "Tier 1 - High Priority"
            if is_authoritative_verified:
                reason = "Doanh nghiệp chuẩn ICP Vận tải Hàng không & Thông quan chuyên trách, định danh pháp nhân đã xác thực cơ quan nhà nước, CRM đã xác nhận không trùng lặp."
            else:
                reason = "Doanh nghiệp chuẩn ICP Vận tải Hàng không & Thông quan chuyên trách, định danh cú pháp hợp lệ, CRM đã xác nhận không trùng lặp."
        elif composite >= 55 and dq_score >= 45:
            tier = "Tier 2 - Qualified"
            if dedupe_status not in ("NOT_FOUND_VERIFIED", "NOT_CHECKED") or getattr(candidate, "in_crm", False):
                reason = "Doanh nghiệp tiềm năng tốt nhưng phát hiện trùng lặp hoặc cần đối soát CRM."
            elif dedupe_status == "NOT_CHECKED":
                reason = "Doanh nghiệp tiềm năng thương mại tốt, dữ liệu cơ bản hợp lệ, chưa hoàn tất kiểm tra trùng lặp CRM."
            else:
                reason = "Doanh nghiệp có tiềm năng thương mại tốt, dữ liệu cơ bản hợp lệ, cần bổ sung thêm thông tin vận hành."
        elif composite >= 35 and has_valid_company:
            tier = "Tier 3 - Nurture"
            reason = "Tiềm năng trung bình hoặc chưa đủ thông tin xác thực, đưa vào danh sách nuôi dưỡng dài hạn."
        else:
            tier = "Disqualified"
            reason = "Không phù hợp với năng lực vận tải chuyên trách của Minh Vân hoặc thiếu thông tin định danh pháp lý."

        full_breakdown = {**dq_breakdown, **cf_breakdown}

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
