from marketing_system.logging_utils import redact
from marketing_system.connectors.meta_ads import MetaAdsConnector
from marketing_system.connectors.youtube import YouTubeConnector


def test_secret_fields_are_redacted_recursively():
    payload = {
        "Authorization": "Bearer abc",
        "nested": {"client_secret": "value", "safe": "visible"},
        "apiKey": "value",
    }
    result = redact(payload)
    assert result["Authorization"] == "[REDACTED]"
    assert result["nested"]["client_secret"] == "[REDACTED]"
    assert result["apiKey"] == "[REDACTED]"
    assert result["nested"]["safe"] == "visible"


def test_env_example_has_names_without_fake_secrets():
    text = (__import__("pathlib").Path(__file__).parents[1] / ".env.example").read_text(encoding="utf-8")
    assignments = [line for line in text.splitlines() if line and not line.startswith("#")]
    for line in assignments:
        key, value = line.split("=", 1)
        if key.endswith(("_SECRET", "_TOKEN", "_KEY")) and key not in {"ZOHO_API_DOMAIN"}:
            assert value == ""


def test_provider_secrets_are_not_sent_in_query_parameters(monkeypatch, tmp_path):
    from marketing_system.config import Settings

    captured = []

    class Response:
        is_success = True
        status_code = 200

    def fake_request(_self, method, url, **kwargs):
        captured.append((method, url, kwargs))
        return Response()

    monkeypatch.setenv("META_ACCESS_TOKEN", "meta-secret")
    monkeypatch.setenv("META_AD_ACCOUNT_ID", "123")
    monkeypatch.setenv("YOUTUBE_API_KEY", "youtube-secret")
    monkeypatch.setattr(MetaAdsConnector, "request", fake_request)
    monkeypatch.setattr(YouTubeConnector, "request", fake_request)
    settings = Settings(data_dir=tmp_path, log_dir=tmp_path)
    MetaAdsConnector(settings).probe_live()
    YouTubeConnector(settings).probe_live()
    assert all("meta-secret" not in str(call[2].get("params")) for call in captured)
    assert all("youtube-secret" not in str(call[2].get("params")) for call in captured)
