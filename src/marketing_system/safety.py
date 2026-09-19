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
    return Impact.WRITE


def authorize(
    action: str,
    environment: Environment,
    safe_dry_run: bool,
    explicit_approval: bool = False,
) -> SafetyDecision:
    impact = classify_action(action)
    if impact in {Impact.READ, Impact.DRAFT}:
        return SafetyDecision(allowed=True, impact=impact, approval_required=False, reason="Read/draft is permitted.")
    if environment is Environment.MOCK:
        return SafetyDecision(allowed=False, impact=impact, approval_required=True, reason="External writes are impossible in mock mode.")
    if safe_dry_run:
        return SafetyDecision(allowed=False, impact=impact, approval_required=True, reason="SAFE_DRY_RUN blocks external writes.")
    if not explicit_approval:
        return SafetyDecision(allowed=False, impact=impact, approval_required=True, reason="Explicit human approval is required.")
    if impact is Impact.HIGH_IMPACT:
        return SafetyDecision(allowed=False, impact=impact, approval_required=True, reason="High-impact execution is disabled in Phase 1 after approval capture.")
    return SafetyDecision(allowed=True, impact=impact, approval_required=False, reason="Approved write is allowed by policy.")

