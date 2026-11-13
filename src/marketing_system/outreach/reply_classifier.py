"""
Reply Intent Classifier for inbound outreach responses.
Classifies leads into INTERESTED, QUOTE_REQUEST, NOT_INTERESTED, WRONG_PERSON, or STOP_CONTACT.
"""
from __future__ import annotations

import re
from typing import Literal, Optional
from pydantic import BaseModel, Field

IntentType = Literal[
    "INTERESTED",
    "QUOTE_REQUEST",
    "NOT_INTERESTED",
    "WRONG_PERSON",
    "STOP_CONTACT",
    "UNKNOWN"
]


class ReplyClassification(BaseModel):
    intent: IntentType
    confidence: float = Field(ge=0.0, le=1.0)
    suggested_action: str
    lead_status_update: str
    notes: str = ""


class ReplyClassifier:
    def classify(self, message_text: str) -> ReplyClassification:
        text = message_text.lower().strip()

        # 1. STOP_CONTACT (Highest priority for compliance)
        stop_signals = ["dừng", "dung", "unsubscribe", "stop", "đừng gửi", "dung gui", "làm phiền", "xóa email", "xoa email"]
        if any(sig in text for sig in stop_signals):
            return ReplyClassification(
                intent="STOP_CONTACT",
                confidence=0.98,
                suggested_action="Lập tức đánh dấu Không liên hệ (Opt-out) trong Zoho CRM và đưa vào danh sách chặn tiếp cận.",
                lead_status_update="Opt-Out / Dừng liên hệ",
                notes="Yêu cầu hủy đăng ký nhận thư theo Nghị định 91."
            )

        # 2. QUOTE_REQUEST
        quote_signals = ["báo giá", "bao gia", "biểu phí", "bieu phi", "chi phí", "chi phi", "giá cước", "gia cuoc", "bảng giá", "bang gia", "quote", "rate"]
        if any(sig in text for sig in quote_signals):
            return ReplyClassification(
                intent="QUOTE_REQUEST",
                confidence=0.92,
                suggested_action="Chuyển ngay cho bộ phận Pricing/Sales lập bảng chào giá chi tiết theo tuyến và khối lượng.",
                lead_status_update="Cơ hội mở / Yêu cầu báo giá",
                notes="Khách hàng chủ động yêu cầu báo giá."
            )

        # 3. INTERESTED
        interested_signals = ["quan tâm", "quan tam", "tìm hiểu", "tim hieu", "trao đổi", "trao doi", "liên hệ lại", "lien he lai", "gặp", "gap", "call", "zalo", "hẹn"]
        if any(sig in text for sig in interested_signals):
            return ReplyClassification(
                intent="INTERESTED",
                confidence=0.88,
                suggested_action="Tạo Sales Task cho BDM gọi điện hoặc kết nối Zalo trong vòng 2 giờ làm việc.",
                lead_status_update="Tiềm năng cao / Chờ BDM liên hệ",
                notes="Khách hàng bày tỏ sự quan tâm đến giải pháp logistics."
            )

        # 4. WRONG_PERSON
        wrong_signals = ["không phụ trách", "khong phu trach", "sai người", "sai nguoi", "liên hệ anh", "lien he anh", "liên hệ chị", "lien he chi", "chuyển sang"]
        if any(sig in text for sig in wrong_signals):
            return ReplyClassification(
                intent="WRONG_PERSON",
                confidence=0.85,
                suggested_action="Cập nhật thông tin người liên hệ mới vào Zoho CRM và gửi email tiếp cận người được giới thiệu.",
                lead_status_update="Đang chuyển người liên hệ",
                notes="Người nhận giới thiệu sang nhân sự chuyên trách."
            )

        # 5. NOT_INTERESTED
        not_interested_signals = ["không có nhu cầu", "khong co nhu cau", "đã có đối tác", "da co doi tac", "hợp đồng năm", "hop dong nam", "chưa cần", "chua can", "từ chối"]
        if any(sig in text for sig in not_interested_signals):
            return ReplyClassification(
                intent="NOT_INTERESTED",
                confidence=0.86,
                suggested_action="Ghi nhận trạng thái chưa có nhu cầu, lập lịch tự động hỏi thăm lại sau 90 ngày (Nuôi dưỡng dài hạn).",
                lead_status_update="Chưa có nhu cầu / Nuôi dưỡng 90 ngày",
                notes="Khách hàng đã có đối tác hiện tại hoặc chưa phát sinh lô hàng mới."
            )

        return ReplyClassification(
            intent="UNKNOWN",
            confidence=0.4,
            suggested_action="Chuyển tin nhắn cho Sales BDM xem xét thủ công.",
            lead_status_update="Cần rà soát thủ công",
            notes="Nội dung phản hồi chưa khớp mẫu phân loại tự động."
        )
