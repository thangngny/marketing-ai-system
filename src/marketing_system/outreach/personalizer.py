"""
Personalizer for compliant B2B outreach drafting.
Strictly relies on verified lead identity; never fabricates pricing or false claims.

INVARIANTS:
- NEVER fabricates recipient email addresses (e.g. contact@...).
- NEVER invents fake person names or titles when missing.
- Checks global suppression lists and opt-out history before staging drafts.
- If email is missing, marks status as MISSING_RECIPIENT and blocks dispatch.
"""
from __future__ import annotations

import re
from typing import Optional, Set
from pydantic import BaseModel, Field

from ..models import LeadCandidate
from .templates import OutreachTemplateRegistry, OutreachTemplate


class PersonalizedDraft(BaseModel):
    recipient_email: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_title: Optional[str] = None
    company_name: str
    subject: str
    body_text: str
    template_id: str
    icp_category: str
    compliance_footer_included: bool
    status: str = "STAGED_DRAFT"  # "STAGED_DRAFT", "MISSING_RECIPIENT", "SUPPRESSED"
    eligibility: str = "ELIGIBLE"


class OutreachPersonalizer:
    def __init__(
        self,
        registry: Optional[OutreachTemplateRegistry] = None,
        suppression_list: Optional[Set[str]] = None,
    ):
        self.registry = registry or OutreachTemplateRegistry()
        # Default global suppression list (opted-out domains & emails)
        self.suppression_list = set(suppression_list or [
            "dừng", "dung", "stop", "unsubscribe@minhvan.vn"
        ])

    def is_suppressed(self, email: Optional[str], domain: Optional[str]) -> bool:
        if email and email.lower().strip() in self.suppression_list:
            return True
        if domain and domain.lower().strip() in self.suppression_list:
            return True
        return False

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

        # INVARIANT: Do not invent fake contact names
        has_real_contact = bool(candidate.contact_name and candidate.contact_name.strip())
        contact_name = candidate.contact_name.strip() if has_real_contact else None
        title = candidate.title.strip() if (candidate.title and candidate.title.strip()) else None

        salutation = f"Kính gửi Anh/Chị {contact_name}" if contact_name else "Kính gửi Ban Lãnh đạo"

        params = {
            "company": candidate.legal_name or candidate.company,
            "contact_name": contact_name or "Quý Doanh nghiệp",
            "title": f" - {title}" if title else "",
            "salutation": salutation,
            "bdm_name": bdm_name,
        }

        subject = tmpl.subject_pattern.format(**params)
        body = tmpl.body_pattern.format(**params) + tmpl.compliance_footer

        # Safety check: ensure no raw bracket placeholders remained
        unresolved = re.findall(r"\{[a-zA-Z_]+\}", subject + body)
        if unresolved:
            raise ValueError(f"Unresolved placeholders in draft: {unresolved}")

        # INVARIANT: Check suppression list first
        if self.is_suppressed(candidate.email, candidate.domain):
            return PersonalizedDraft(
                recipient_email=candidate.email,
                recipient_name=contact_name,
                recipient_title=title,
                company_name=params["company"],
                subject=subject,
                body_text=body,
                template_id=tmpl.template_id,
                icp_category=category,
                compliance_footer_included=True,
                status="SUPPRESSED",
                eligibility="INELIGIBLE_SUPPRESSED",
            )

        # INVARIANT: Never fabricate recipient email
        if not candidate.email:
            return PersonalizedDraft(
                recipient_email=None,
                recipient_name=contact_name,
                recipient_title=title,
                company_name=params["company"],
                subject=subject,
                body_text=body,
                template_id=tmpl.template_id,
                icp_category=category,
                compliance_footer_included=True,
                status="MISSING_RECIPIENT",
                eligibility="INELIGIBLE_NO_EMAIL",
            )

        return PersonalizedDraft(
            recipient_email=candidate.email.strip().lower(),
            recipient_name=contact_name,
            recipient_title=title,
            company_name=params["company"],
            subject=subject,
            body_text=body,
            template_id=tmpl.template_id,
            icp_category=category,
            compliance_footer_included=True,
            status="STAGED_DRAFT",
            eligibility="ELIGIBLE",
        )
