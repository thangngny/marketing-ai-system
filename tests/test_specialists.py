import pytest

from marketing_system.constants import SPECIALISTS as SPECIALIST_IDS, Impact
from marketing_system.routing import _MULTI_AGENT_RULES, _RULES, route_intent
from marketing_system.specialists import SPECIALISTS, get_specialist


def test_exactly_eight_logical_specialists_with_instructions():
    assert tuple(SPECIALISTS) == SPECIALIST_IDS
    for specialist in SPECIALISTS.values():
        assert specialist.instructions(), f"{specialist.id} has no skill instructions"


def test_every_route_targets_registered_specialists():
    for _intent, _pattern, agents, _reason in (*_RULES, *_MULTI_AGENT_RULES):
        for agent in agents:
            get_specialist(agent)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Phân tích thị trường forwarding", {"02_market_intelligence", "01_strategy"}),
        ("Tìm lead logistics", {"03_account_intelligence"}),
        ("Viết bài LinkedIn", {"04_content"}),
        ("Tối ưu SEO cho website", {"05_seo_geo"}),
        ("Chuẩn bị cuộc gọi khách hàng", {"03_account_intelligence", "06_sales_copilot"}),
        ("Lập chiến dịch quý 4", {"01_strategy", "07_campaign"}),
        ("Báo cáo hiệu quả tuần này", {"08_kpi_learning"}),
    ],
)
def test_routing_selects_minimum_set_not_all_eight(text, expected):
    decision = route_intent(text)
    assert set(decision.agents) == expected
    assert len(decision.agents) < 8


def test_permission_ceilings_are_code_not_prompt():
    assert not SPECIALISTS["08_kpi_learning"].allows("email", Impact.DRAFT)
    assert not SPECIALISTS["04_content"].allows("social", Impact.HIGH_IMPACT)
    assert SPECIALISTS["06_sales_copilot"].allows("email", Impact.DRAFT)
    assert not any(s.allows(ns, Impact.HIGH_IMPACT) for s in SPECIALISTS.values() for ns in s.namespaces)
