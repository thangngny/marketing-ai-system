from marketing_system.config import Settings
from marketing_system.connectors import ConnectorRegistry
from marketing_system.constants import ConnectorState, Environment


def test_every_connector_is_mock_ready_without_credentials(monkeypatch, tmp_path):
    for name in list(__import__("os").environ):
        if name.startswith(("ZOHO_", "MS_", "APOLLO_", "LINKEDIN_", "YOUTUBE_", "META_", "GOOGLE_ADS_", "WEBSITE_")):
            monkeypatch.delenv(name, raising=False)
    settings = Settings(environment=Environment.MOCK, data_dir=tmp_path, log_dir=tmp_path)
    reports = ConnectorRegistry(settings).reports()
    assert len(reports) == 8
    assert all(report.current_state == ConnectorState.MOCK_READY for report in reports)
    assert all(report.live_state in {ConnectorState.NEEDS_AUTH, ConnectorState.NEEDS_ACCESS, ConnectorState.CONFIG_REQUIRED} for report in reports)
    assert all(report.live_tested is False for report in reports)


def test_apollo_declares_credit_semantics(tmp_path):
    settings = Settings(environment=Environment.MOCK, data_dir=tmp_path, log_dir=tmp_path)
    apollo = ConnectorRegistry(settings).get("apollo")
    costs = {cap.name: cap.cost_semantics for cap in apollo.capabilities}
    assert "0 credits" in costs["people_search"]
    assert "1 Apollo credit" in costs["organization_search"]
    assert "consumes credits" in costs["people_enrichment"]


def test_every_connector_has_deterministic_labeled_mock_data(tmp_path):
    settings = Settings(environment=Environment.MOCK, data_dir=tmp_path, log_dir=tmp_path)
    registry = ConnectorRegistry(settings)
    for name in ("zoho", "m365", "apollo", "linkedin", "youtube", "meta_ads", "google_ads", "website"):
        first = registry.get(name).mock_search("logistics", 2)
        second = registry.get(name).mock_search("logistics", 2)
        assert first == second
        assert first
        assert all(row["synthetic"] is True for row in first)
        assert all(row["environment"] == "mock" for row in first)
