from __future__ import annotations

from ..config import Settings
from .apollo import ApolloConnector
from .base import BaseConnector, ConnectorReport
from .elevenlabs import ElevenLabsConnector
from .google_ads import GoogleAdsConnector
from .google_drive import GoogleDriveConnector
from .heygen import HeyGenConnector
from .higgsfield import HiggsfieldConnector
from .linkedin import LinkedInConnector
from .m365 import M365Connector
from .meta_ads import MetaAdsConnector
from .meta_ai import MetaAiConnector
from .tiktok import TikTokConnector
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
                MetaAiConnector(settings),
                GoogleAdsConnector(settings),
                WebsiteConnector(settings),
                GoogleDriveConnector(settings),
                TikTokConnector(settings),
                HeyGenConnector(settings),
                ElevenLabsConnector(settings),
                HiggsfieldConnector(settings),
            )
        }

    def get(self, name: str) -> BaseConnector:
        return self._connectors[name]

    def reports(self, live_probe: bool = False) -> list[ConnectorReport]:
        return [connector.report(live_probe=live_probe) for connector in self._connectors.values()]

