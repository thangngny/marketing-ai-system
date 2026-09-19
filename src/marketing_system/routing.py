from __future__ import annotations

import re

from .models import RouteDecision


_RULES: tuple[tuple[str, str, list[str], str], ...] = (
    ("system_status", r"(kiểm tra|kiem tra|check|trạng thái|trang thai|status).*(hệ thống|he thong|connector|toàn bộ|toan bo)", [], "Yêu cầu trạng thái hệ thống."),
    ("campaign", r"(chiến dịch|chien dich|campaign|quảng cáo|quang cao|facebook ads|google ads|ngân sách|ngan sach)", ["01_strategy", "07_campaign"], "Thiết kế chiến dịch cần chiến lược và điều phối kênh."),
    ("sales_call", r"(chuẩn bị|chuan bi).*(cuộc gọi|cuoc goi|meeting)|account brief|proposal|deal support", ["03_account_intelligence", "06_sales_copilot"], "Cần thông tin account và hỗ trợ bán hàng."),
    ("lead_search", r"(tìm|tim|find|search).*(lead|khách hàng tiềm năng|khach hang tiem nang|prospect|account)|apollo|enrichment|lead scoring", ["03_account_intelligence"], "Nghiên cứu và chấm điểm lead/account."),
    ("market_intelligence", r"(đối thủ|doi thu|competitor|thị trường|thi truong|industry intelligence)", ["02_market_intelligence", "01_strategy"], "Nghiên cứu thị trường rồi chuyển thành hàm ý chiến lược."),
    ("seo_geo", r"\bseo\b|\bgeo\b|keyword|từ khóa|tu khoa|ai search|search visibility", ["05_seo_geo"], "Yêu cầu SEO/GEO chuyên biệt."),
    ("content", r"(viết|viet|draft|content|bài linkedin|bai linkedin|landing page|video concept|email copy)", ["04_content"], "Tạo nội dung hoặc bản nháp theo kênh."),
    ("kpi_report", r"(báo cáo|bao cao|kpi|hiệu quả|hieu qua|attribution|metrics|performance)", ["08_kpi_learning"], "Phân tích KPI và vòng học hỏi."),
    ("strategy", r"(icp|positioning|chiến lược|chien luoc|objective|mục tiêu|muc tieu)", ["01_strategy"], "Yêu cầu chiến lược marketing."),
)

_MULTI_AGENT_RULES: tuple[tuple[str, str, list[str], str], ...] = (
    (
        "competitive_campaign_content",
        r"(?=.*(?:đối thủ|doi thu|competitor))(?=.*(?:chiến dịch|chien dich|campaign))(?=.*(?:viết|viet|bài mẫu|bai mau|content))",
        ["02_market_intelligence", "01_strategy", "07_campaign", "04_content"],
        "Nghiên cứu đối thủ, chuyển thành chiến dịch, rồi tạo nội dung mẫu.",
    ),
)


def route_intent(text: str) -> RouteDecision:
    normalized = " ".join(text.lower().split())
    for intent, pattern, agents, reason in _MULTI_AGENT_RULES:
        if re.search(pattern, normalized, flags=re.I):
            return RouteDecision(intent=intent, agents=agents, reason=reason)
    for intent, pattern, agents, reason in _RULES:
        if re.search(pattern, normalized, flags=re.I):
            return RouteDecision(intent=intent, agents=agents, reason=reason)
    return RouteDecision(
        intent="general_marketing",
        agents=["01_strategy"],
        reason="Không khớp intent chuyên biệt; Strategy Agent phân rã trước.",
    )
