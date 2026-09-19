from marketing_system.config import Settings
from marketing_system.constants import Environment
from marketing_system.orchestrator import MarketingOrchestrator


def make_orchestrator(tmp_path):
    return MarketingOrchestrator(
        Settings(environment=Environment.MOCK, safe_dry_run=True, data_dir=tmp_path / "data", log_dir=tmp_path / "logs")
    )


def test_status_is_truthful(tmp_path):
    result = make_orchestrator(tmp_path).handle("Kiểm tra trạng thái toàn bộ hệ thống.")
    assert result.result_state == "PASS_MOCK"
    assert "MOCK_READY không phải kết nối live" in result.response
    assert result.side_effects == []


def test_mock_lead_workflow_is_canonical_and_labeled(tmp_path):
    orchestrator = make_orchestrator(tmp_path)
    result = orchestrator.handle("Tìm cho tôi 3 khách hàng tiềm năng ngành logistics và cho biết agent nào xử lý.")
    assert result.agents == ["03_account_intelligence"]
    assert len(result.records) == 3
    assert all(record["synthetic"] for record in result.records)
    assert all(record["environment"] == "mock" for record in result.records)
    assert "MOCK" in result.response
    assert "Không có outreach" in result.response


def test_content_is_draft_and_not_published(tmp_path):
    result = make_orchestrator(tmp_path).handle("Viết một bài LinkedIn giới thiệu dịch vụ forwarding.")
    assert result.agents == ["04_content"]
    assert "CHƯA ĐĂNG" in result.response
    assert "Không xuất bản" in result.response
    assert result.side_effects == []


def test_campaign_never_launches_or_spends(tmp_path):
    result = make_orchestrator(tmp_path).handle("Tạo chiến dịch quảng cáo Facebook 10 triệu.")
    assert result.agents == ["01_strategy", "07_campaign"]
    assert result.approval_required is True
    assert "KHÔNG KHỞI CHẠY" in result.response
    assert "trước mọi chi tiêu" in result.response
    assert result.side_effects == []


def test_competitor_campaign_content_uses_only_relevant_agents(tmp_path):
    result = make_orchestrator(tmp_path).handle(
        "Phân tích nhanh 3 đối thủ forwarding, sau đó đề xuất một chiến dịch LinkedIn và viết 1 bài mẫu."
    )
    assert result.agents == [
        "02_market_intelligence",
        "01_strategy",
        "07_campaign",
        "04_content",
    ]
    assert result.side_effects == []
