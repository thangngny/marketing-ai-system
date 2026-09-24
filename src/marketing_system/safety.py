"""Legacy action classifier kept for backward compatibility.

Authorization now lives in policy.PolicyEngine + workflows.approvals. A boolean
`explicit_approval` can no longer grant anything: approvals must be verified
by an ApprovalVerifier (owner-signed Buzz message or local console).
"""

from __future__ import annotations

from pydantic import BaseModel

from .constants import Environment, Impact


HIGH_IMPACT_ACTIONS = {
    "send_email",
    "publish_content",
    "launch_ad_campaign",
    "change_ad_budget",
    "delete_crm_record",
    "change_permissions",
    "sign_contract",
    "send_outreach",
    "modify_production_system",
    "upload_youtube_video",
}


class SafetyDecision(BaseModel):
    allowed: bool
    impact: Impact
    approval_required: bool
    reason: str


def classify_action(action: str) -> Impact:
    if action in HIGH_IMPACT_ACTIONS:
        return Impact.HIGH_IMPACT
    if action.startswith(("create_draft", "stage_", "plan_")):
        return Impact.DRAFT
    if action.startswith(("read_", "search_", "health", "status")):
        return Impact.READ
    return Impact.WRITE_LOW_RISK


def authorize(
    action: str,
    environment: Environment,
    safe_dry_run: bool,
    explicit_approval: bool = False,  # accepted for signature compatibility; never grants
) -> SafetyDecision:
    impact = classify_action(action)
    if impact in {Impact.READ, Impact.DRAFT}:
        return SafetyDecision(allowed=True, impact=impact, approval_required=False, reason="Read/draft is permitted.")
    if environment is Environment.MOCK:
        return SafetyDecision(allowed=False, impact=impact, approval_required=True, reason="External writes are impossible in mock mode.")
    if safe_dry_run:
        return SafetyDecision(allowed=False, impact=impact, approval_required=True, reason="SAFE_DRY_RUN blocks external writes.")
    if impact is Impact.HIGH_IMPACT:
        return SafetyDecision(allowed=False, impact=impact, approval_required=True, reason="High-impact execution is disabled in Phase 1 after approval capture.")
    return SafetyDecision(allowed=False, impact=impact, approval_required=True,
                          reason="Writes run only through a workflow with a verified owner approval (DUYET <code> in Buzz).")
