from marketing_system.logging_utils import redact


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

