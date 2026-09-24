import os

import pytest

from marketing_system.config import Settings
from marketing_system.connectors import ConnectorRegistry


REQUIRED = {
    "zoho": ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN"),
    "m365": ("MS_TENANT_ID", "MS_CLIENT_ID", "MS_REFRESH_TOKEN"),
    "apollo": ("APOLLO_API_KEY",),
    "linkedin": ("LINKEDIN_ACCESS_TOKEN",),
    "youtube": ("YOUTUBE_API_KEY",),
    "meta_ads": ("META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID"),
    "google_ads": ("GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_CUSTOMER_ID", "GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN"),
    "website": ("WEBSITE_URL",),
}


@pytest.mark.live
@pytest.mark.parametrize("name", list(REQUIRED))
def test_live_probe_when_authorized(name):
    if os.getenv("RUN_LIVE_CONNECTOR_TESTS") != "1":
        pytest.skip("SKIPPED_NEEDS_AUTH: set RUN_LIVE_CONNECTOR_TESTS=1 for explicit live probes")
    connector = ConnectorRegistry(Settings.from_env()).get(name)
    _, missing = connector.credential_presence()
    if missing:
        pytest.skip(f"SKIPPED_NEEDS_AUTH: {name} missing {','.join(missing)}")
    report = connector.report(live_probe=True)
    assert report.live_tested is True
    assert report.live_state == "CONNECTED"
