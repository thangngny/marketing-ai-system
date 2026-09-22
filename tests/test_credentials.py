from marketing_system import credentials
from marketing_system.oauth import M365_SCOPES, ZOHO_SCOPES


def test_target_is_namespaced_and_normalized():
    assert credentials._target("zoho_refresh_token") == "BuzzMarketing/ZOHO_REFRESH_TOKEN"


def test_target_rejects_unsafe_names():
    try:
        credentials._target("../../secret")
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe credential name was accepted")


def test_oauth_scopes_are_read_only():
    assert ".CREATE" not in ZOHO_SCOPES
    assert ".UPDATE" not in ZOHO_SCOPES
    assert ".DELETE" not in ZOHO_SCOPES
    assert "Mail.Send" not in M365_SCOPES
    assert "Files.ReadWrite" not in M365_SCOPES
