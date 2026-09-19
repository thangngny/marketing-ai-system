from __future__ import annotations

from ..config import Settings
from .apollo import ApolloConnector
from .base import BaseConnector, ConnectorReport
from .google_ads import GoogleAdsConnector
from .linkedin import LinkedInConnector
from .m365 import M365Connector
from .meta_ads import MetaAdsConnector
from .website import WebsiteConnector
from .youtube import YouTubeConnector
from .zoho import ZohoConnector


class ConnectorRegistry:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._connectors: dict[str, BaseConnector] = {
            connector.name: connector
            for connector in (
                ZohoConnector(settings),
                M365Connector(settings),
                ApolloConnector(settings),
                LinkedInConnector(settings),
                YouTubeConnector(settings),
                MetaAdsConnector(settings),
                GoogleAdsConnector(settings),
                WebsiteConnector(settings),
            )
        }

    def get(self, name: str) -> BaseConnector:
        return self._connectors[name]

    def reports(self, live_probe: bool = False) -> list[ConnectorReport]:
        return [connector.report(live_probe=live_probe) for connector in self._connectors.values()]

