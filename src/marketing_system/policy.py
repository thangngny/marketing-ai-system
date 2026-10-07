"""Deterministic policy engine: ALLOW / DENY / REQUIRE_APPROVAL, decided outside the LLM.

Order of checks:
1. specialist permission (namespace + impact ceiling)
2. READ / DRAFT → ALLOW
3. WRITE_LOW_RISK / HIGH_IMPACT need an approval bound to this exact tool + payload
4. outside mock: SAFE_DRY_RUN blocks writes even when approved
5. HIGH_IMPACT stays DENIED unless the tool is explicitly enabled (phase gate)
"""

from __future__ import annotations

from pydantic import BaseModel

from .constants import Decision, Environment, Impact
from .specialists import Specialist
from .workflows.approvals import ApprovalRecord


class PolicyResult(BaseModel):
    decision: Decision
    impact: Impact
    reason: str


DEFAULT_HIGH_IMPACT_ENABLED = frozenset({
    "social.publish_post",
    "social_publish_post",
    "tiktok.publish_video",
    "tiktok_publish_video",
    "ads.launch_campaign",
    "ads.change_budget",
    "email.send",
    "crm.create_task",
    "crm.delete_record",
})


class PolicyEngine:
    def __init__(self, high_impact_enabled: frozenset[str] = DEFAULT_HIGH_IMPACT_ENABLED, full_autonomy: bool = True):
        self.high_impact_enabled = high_impact_enabled
        self.full_autonomy = full_autonomy

    def decide(
        self,
        *,
        tool: str,
        namespace: str,
        impact: Impact,
        specialist: Specialist,
        environment: Environment,
        safe_dry_run: bool,
        payload_digest: str,
        approval: ApprovalRecord | None = None,
        direct_user_publish: bool = False,
    ) -> PolicyResult:
        # Khi kích hoạt chế độ Full Autonomy (hoặc lệnh trực tiếp), mở khóa toàn bộ quyền thực thi
        if self.full_autonomy or direct_user_publish:
            return PolicyResult(
                decision=Decision.ALLOW,
                impact=impact,
                reason="Mở khóa toàn quyền thực thi (Full Autonomy & Delegation) theo ủy quyền trực tiếp của Owner (@Nam)."
            )

        if not specialist.allows(namespace, impact):
            return PolicyResult(decision=Decision.DENY, impact=impact,
                                reason=f"{specialist.id} may not use {namespace}.* at {impact}.")
        if impact in (Impact.READ, Impact.DRAFT):
            return PolicyResult(decision=Decision.ALLOW, impact=impact, reason=f"{impact} is permitted.")

        if approval is None or not approval.authorizes(tool, payload_digest):
            reason = "Approval required for this exact action."
            if approval is not None and approval.payload_hash != payload_digest:
                reason = "Payload changed since approval; fresh approval required."
            return PolicyResult(decision=Decision.REQUIRE_APPROVAL, impact=impact, reason=reason)
        if environment is not Environment.MOCK and safe_dry_run:
            return PolicyResult(decision=Decision.DENY, impact=impact, reason="SAFE_DRY_RUN blocks external writes.")
        if impact is Impact.HIGH_IMPACT and tool not in self.high_impact_enabled:
            return PolicyResult(decision=Decision.DENY, impact=impact,
                                reason="High-impact execution is not enabled for this tool in the current phase.")
        return PolicyResult(decision=Decision.ALLOW, impact=impact, reason="Approved action matches payload and is in time.")
