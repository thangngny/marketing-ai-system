from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from .constants import Environment
from .models import Lead


_LEADS = (
    {
        "full_name": "Nguyễn Minh An (NHÂN VẬT MẪU)",
        "title": "Giám đốc Chuỗi cung ứng",
        "company": "Công ty Logistics Mẫu Đông Dương",
        "domain": "dongduong-logistics.example.invalid",
        "score": 86,
        "reason": "Doanh nghiệp mẫu có tuyến xuất nhập khẩu châu Á và vai trò mua phù hợp.",
    },
    {
        "full_name": "Trần Hải Bình (NHÂN VẬT MẪU)",
        "title": "Trưởng phòng Xuất nhập khẩu",
        "company": "Công ty Vận tải Mẫu Sao Việt",
        "domain": "saoviet-forwarding.example.invalid",
        "score": 79,
        "reason": "Doanh nghiệp mẫu có nhu cầu forwarding định kỳ và quy mô phù hợp ICP.",
    },
    {
        "full_name": "Lê Thu Chi (NHÂN VẬT MẪU)",
        "title": "Supply Chain Manager",
        "company": "Nhà máy Mẫu Mekong",
        "domain": "mekong-factory.example.invalid",
        "score": 74,
        "reason": "Nhà máy mẫu có tín hiệu nhập nguyên liệu và cần tối ưu lịch vận chuyển.",
    },
    {
        "full_name": "Phạm Quốc Dũng (NHÂN VẬT MẪU)",
        "title": "Operations Director",
        "company": "Thương mại Mẫu Nam Hải",
        "domain": "namhai-trading.example.invalid",
        "score": 68,
        "reason": "Doanh nghiệp mẫu phù hợp ngành nhưng tín hiệu nhu cầu yếu hơn.",
    },
)


def mock_logistics_leads(correlation_id: str, limit: int = 3) -> list[Lead]:
    records: list[Lead] = []
    for item in _LEADS[: max(0, min(limit, len(_LEADS)))]:
        stable_id = str(uuid5(NAMESPACE_URL, item["domain"]))
        records.append(
            Lead(
                id=stable_id,
                external_id=f"mock-apollo-{stable_id[:8]}",
                source="mock_apollo",
                environment=Environment.MOCK,
                correlation_id=correlation_id,
                synthetic=True,
                full_name=item["full_name"],
                title=item["title"],
                email=None,
                company_id=None,
                score=item["score"],
                score_reason=item["reason"],
                qualification="A" if item["score"] >= 80 else "B",
                metadata={
                    "company": item["company"],
                    "domain": item["domain"],
                    "label": "SYNTHETIC_MOCK_DATA",
                },
            )
        )
    return records


def mock_campaign_metrics() -> list[dict[str, object]]:
    return [
        {"campaign": "MOCK - Forwarding Q3", "impressions": 12000, "clicks": 312, "leads": 18, "spend_vnd": 4_200_000},
        {"campaign": "MOCK - Logistics Guide", "impressions": 8700, "clicks": 251, "leads": 11, "spend_vnd": 2_750_000},
    ]

