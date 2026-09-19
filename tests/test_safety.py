import pytest

from marketing_system.constants import Environment, Impact
from marketing_system.safety import authorize, classify_action


@pytest.mark.parametrize(
    "action",
    ["send_email", "publish_content", "launch_ad_campaign", "change_ad_budget", "delete_crm_record", "send_outreach"],
)
def test_high_impact_actions_are_classified(action):
    assert classify_action(action) == Impact.HIGH_IMPACT


def test_mock_mode_blocks_external_write_even_with_approval():
    decision = authorize("send_email", Environment.MOCK, safe_dry_run=True, explicit_approval=True)
    assert decision.allowed is False
    assert decision.approval_required is True


def test_read_and_draft_are_allowed():
    assert authorize("read_metrics", Environment.MOCK, True).allowed is True
    assert authorize("create_draft_post", Environment.MOCK, True).allowed is True


def test_phase_one_still_blocks_high_impact_after_approval():
    decision = authorize("launch_ad_campaign", Environment.PRODUCTION, safe_dry_run=False, explicit_approval=True)
    assert decision.allowed is False
    assert "disabled in Phase 1" in decision.reason

