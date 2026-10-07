from marketing_system.config import Settings
from marketing_system.connectors import ConnectorRegistry
from marketing_system.connectors.youtube import YouTubeConnector
from marketing_system.constants import ConnectorState, Environment


def test_every_connector_is_mock_ready_without_credentials(monkeypatch, tmp_path):
    monkeypatch.setattr("marketing_system.connectors.base.read_credential", lambda _: None)
    for name in list(__import__("os").environ):
        if name.startswith(("ZOHO_", "MS_", "APOLLO_", "LINKEDIN_", "YOUTUBE_", "META_", "GOOGLE_ADS_", "GOOGLE_DRIVE_", "WEBSITE_", "TIKTOK_", "HEYGEN_", "ELEVENLABS_", "ELEVEN_", "HF_", "HIGGSFIELD_")):
            monkeypatch.delenv(name, raising=False)
    settings = Settings(environment=Environment.MOCK, data_dir=tmp_path, log_dir=tmp_path)
    reports = ConnectorRegistry(settings).reports()
    assert len(reports) == 13
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


def test_youtube_read_recent_videos_normalizes_to_channel_posts(monkeypatch, tmp_path):
    class Response:
        status_code = 200
        is_success = True

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "items": [
                    {
                        "id": {"videoId": "abc123"},
                        "snippet": {
                            "title": "Ra mắt dịch vụ forwarding mới",
                            "description": "Video giới thiệu",
                            "publishedAt": "2026-09-20T10:00:00Z",
                            "channelId": "UC_test",
                            "channelTitle": "Công ty Test",
                        },
                    }
                ]
            }

    captured = {}

    def fake_request(_self, method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["params"] = kwargs.get("params")
        return Response()

    monkeypatch.setattr(YouTubeConnector, "request", fake_request)
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setenv("YOUTUBE_CHANNEL_ID", "UC_test")
    settings = Settings(environment=Environment.PRODUCTION, data_dir=tmp_path, log_dir=tmp_path)
    connector = YouTubeConnector(settings)

    records = connector.read("recent_videos", limit=5, correlation_id="test-corr")

    assert len(records) == 1
    post = records[0]
    assert post.source == "youtube"
    assert post.channel_post_id == "abc123"
    assert post.title == "Ra mắt dịch vụ forwarding mới"
    assert post.metadata["url"] == "https://www.youtube.com/watch?v=abc123"
    assert captured["params"]["channelId"] == "UC_test"


def test_youtube_read_requires_channel_id(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.delenv("YOUTUBE_CHANNEL_ID", raising=False)
    settings = Settings(environment=Environment.PRODUCTION, data_dir=tmp_path, log_dir=tmp_path)
    connector = YouTubeConnector(settings)
    try:
        connector.read("recent_videos")
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass


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
