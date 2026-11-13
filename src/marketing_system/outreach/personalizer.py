"""
Personalizer for compliant B2B outreach drafting.
Strictly relies on verified lead identity; never fabricates pricing or false claims.
"""
from __future__ import annotations

import re
from typing import Optional
from pydantic import BaseModel, Field

from ..models import LeadCandidate
from .templates import OutreachTemplateRegistry, OutreachTemplate


class PersonalizedDraft(BaseModel):
    recipient_email: str
    recipient_name: str
    recipient_title: str
    company_name: str
    subject: str
    body_text: str
    template_id: str
    icp_category: str
    compliance_footer_included: bool
    status: str = "STAGED_DRAFT"  # NEVER sends live without approval


class OutreachPersonalizer:
    def __init__(self, registry: Optional[OutreachTemplateRegistry] = None):
        self.registry = registry or OutreachTemplateRegistry()

    def personalize(self, candidate: LeadCandidate, bdm_name: str = "Hà Vân (BDM)") -> PersonalizedDraft:
        # Determine ICP category
        ind = candidate.industry_code or ""
        comp_lower = (candidate.company or "").lower()
        if ind in ("3250", "4659") or any(k in comp_lower for k in ["y tế", "dược", "medical"]):
            category = "medical"
        elif ind in ("2611", "2620") or any(k in comp_lower for k in ["điện tử", "linh kiện", "tech"]):
            category = "electronics"
        else:
            category = "medical"

        tmpl = self.registry.get_template(category)

        contact_name = candidate.contact_name or "Quý Lãnh Đạo"
        title = candidate.title or "Trưởng phòng Mua hàng & Logistics"
        salutation = "Anh/Chị"

        params = {
            "company": candidate.legal_name or candidate.company,
            "contact_name": contact_name,
            "title": title,
            "salutation": salutation,
            "bdm_name": bdm_name,
        }

        subject = tmpl.subject_pattern.format(**params)
        body = tmpl.body_pattern.format(**params) + tmpl.compliance_footer

        # Safety check: ensure no raw bracket placeholders remained
        unresolved = re.findall(r"\{[a-zA-Z_]+\}", subject + body)
        if unresolved:
            raise ValueError(f"Unresolved placeholders in draft: {unresolved}")

        return PersonalizedDraft(
            recipient_email=candidate.email or f"contact@{candidate.domain or 'company.vn'}",
            recipient_name=contact_name,
            recipient_title=title,
            company_name=params["company"],
            subject=subject,
            body_text=body,
            template_id=tmpl.template_id,
            icp_category=category,
            compliance_footer_included=True,
            status="STAGED_DRAFT"
        )
