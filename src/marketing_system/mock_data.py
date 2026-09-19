from __future__ import annotations

from copy import deepcopy
from typing import Any


_MOCKS: dict[str, list[dict[str, Any]]] = {
    "zoho": [
        {"type": "Lead", "name": "MOCK Lead Logistics A", "status": "New"},
        {"type": "Deal", "name": "MOCK Forwarding Opportunity", "stage": "Qualification", "amount_vnd": 250_000_000},
        {"type": "Task", "name": "MOCK Prepare discovery call", "status": "Not Started"},
    ],
    "m365": [
        {"type": "message", "subject": "MOCK RFQ follow-up", "is_draft": True},
        {"type": "event", "subject": "MOCK Logistics discovery call", "start": "2030-01-02T09:00:00Z"},
        {"type": "file", "name": "MOCK-forwarding-brief.docx", "location": "synthetic://m365/files/1"},
    ],
    "apollo": [
        {"type": "company", "name": "MOCK Đông Dương Logistics", "domain": "dongduong.example.invalid"},
        {"type": "person", "name": "MOCK Nguyễn An", "title": "Supply Chain Director"},
        {"type": "person", "name": "MOCK Trần Bình", "title": "Import Export Manager"},
    ],
    "linkedin": [
        {"type": "page", "name": "MOCK Forwarding Company Page"},
        {"type": "post_draft", "text": "MOCK — draft only", "published": False},
    ],
    "youtube": [
        {"type": "channel", "name": "MOCK Logistics Channel", "subscribers": 1234},
        {"type": "video", "title": "MOCK Forwarding Explained", "views": 5678},
    ],
    "meta_ads": [
        {"type": "campaign_metric", "campaign": "MOCK Meta Forwarding", "impressions": 12000, "clicks": 312, "spend_vnd": 4_200_000},
    ],
    "google_ads": [
        {"type": "campaign_metric", "campaign": "MOCK Google Search Logistics", "impressions": 8700, "clicks": 251, "spend_vnd": 2_750_000},
    ],
    "website": [
        {"type": "page", "url": "https://example.invalid/forwarding", "title": "MOCK Forwarding Landing Page"},
        {"type": "form_submission", "name": "MOCK Prospect", "email": "prospect@example.invalid"},
    ],
}


def connector_mock_records(connector: str, query: str, limit: int) -> list[dict[str, Any]]:
    rows = deepcopy(_MOCKS.get(connector, []))[: max(0, limit)]
    for row in rows:
        row.update(
            {
                "environment": "mock",
                "synthetic": True,
                "label": "SYNTHETIC_MOCK_DATA",
                "query": query,
            }
        )
    return rows

