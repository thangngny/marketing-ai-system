import pytest

from marketing_system.routing import route_intent


@pytest.mark.parametrize(
    ("text", "intent", "agents"),
    [
        ("Kiểm tra trạng thái toàn bộ hệ thống.", "system_status", []),
        ("Tìm 20 lead logistics", "lead_search", ["03_account_intelligence"]),
        ("Viết bài LinkedIn", "content", ["04_content"]),
        ("Lập chiến dịch Facebook Ads", "campaign", ["01_strategy", "07_campaign"]),
        ("Chuẩn bị cuộc gọi với khách X", "sales_call", ["03_account_intelligence", "06_sales_copilot"]),
        ("Báo cáo hiệu quả tuần này", "kpi_report", ["08_kpi_learning"]),
        ("Phân tích 3 đối thủ", "market_intelligence", ["02_market_intelligence", "01_strategy"]),
        (
            "Phân tích nhanh 3 đối thủ forwarding, sau đó đề xuất một chiến dịch LinkedIn và viết 1 bài mẫu.",
            "competitive_campaign_content",
            ["02_market_intelligence", "01_strategy", "07_campaign", "04_content"],
        ),
        ("Lập keyword SEO và GEO", "seo_geo", ["05_seo_geo"]),
    ],
)
def test_routes_to_minimum_specialists(text, intent, agents):
    decision = route_intent(text)
    assert decision.intent == intent
    assert decision.agents == agents
