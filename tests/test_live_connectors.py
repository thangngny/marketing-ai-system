import os

import pytest

from marketing_system.config import Settings
from marketing_system.connectors import ConnectorRegistry


REQUIRED = {
    "zoho": ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN"),
    "m365": ("MS_GRAPH_ACCESS_TOKEN",),
    "apollo": ("APOLLO_API_KEY",),
    "linkedin": ("LINKEDIN_ACCESS_TOKEN",),
    "youtube": ("YOUTUBE_API_KEY",),
    "meta_ads": ("META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID"),
    "google_ads": ("GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_CUSTOMER_ID", "GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN"),
    "website": ("WEBSITE_URL",),
}


@pytest.mark.parametrize("name", list(REQUIRED))
def test_live_probe_when_authorized(name):
    missing = [key for key in REQUIRED[name] if not os.getenv(key)]
    if missing:
        pytest.skip(f"SKIPPED_NEEDS_AUTH: {name} missing {','.join(missing)}")
    report = ConnectorRegistry(Settings.from_env()).get(name).report(live_probe=True)
    assert report.live_tested is True
    assert report.live_state == "CONNECTED"

