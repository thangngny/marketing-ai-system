"""
Approved outreach email templates for Minh Van Logistics B2B outreach.
Strictly compliant with Decree 91/2020/ND-CP and GTM Brain standards.
"""
from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class OutreachTemplate(BaseModel):
    template_id: str
    icp_category: str  # "medical", "electronics", "pharma", "general"
    subject_pattern: str
    body_pattern: str
    approved_by: str = "Owner"
    compliance_footer: str = (
        "\n\n---\n"
        "Minh Van International Transport & Logistics JSC (Minh Van ITL)\n"
        "Văn phòng hiện trường: Sân bay Quốc tế Nội Bài & Sân bay Quốc tế Tân Sơn Nhất\n"
        "Hotline: +84 981 003344 | Website: minhvanlogistics.com\n"
        "Nếu Quý đơn vị không muốn nhận các thông tin cập nhật logistics từ Minh Vân, "
        "vui lòng phản hồi với nội dung 'DỪNG' để chúng tôi lập tức xóa khỏi danh sách liên hệ."
    )


class OutreachTemplateRegistry:
    def __init__(self):
        self.templates: Dict[str, OutreachTemplate] = {}
        self._load_defaults()

    def _load_defaults(self):
        # 1. Medical Devices
        self.templates["medical_cold_1"] = OutreachTemplate(
            template_id="medical_cold_1",
            icp_category="medical",
            subject_pattern="Giải pháp thông quan hỏa tốc & vận tải hàng không cho thiết bị y tế của {company}",
            body_pattern=(
                "Kính gửi {salutation} {contact_name} — {title},\n\n"
                "Em là {bdm_name} từ Công ty CP Vận tải Quốc tế Minh Vân (Minh Van ITL).\n\n"
                "Được biết {company} đang phân phối các dòng trang thiết bị và sinh phẩm y tế cao cấp tại Việt Nam. "
                "Do đặc thù mặt hàng này đòi hỏi điều kiện bảo quản nhiệt độ khắt khe cũng như thời gian thông quan gấp để kịp bàn giao cho bệnh viện/phòng khám, "
                "Minh Vân hiện đang triển khai giải pháp vận tải hàng không chuyên trách:\n\n"
                "1. Trục bay thẳng ưu tiên từ Nhật Bản, Hàn Quốc, Châu Âu về Nội Bài (HAN) và Tân Sơn Nhất (SGN).\n"
                "2. Đội ngũ hải quan hiện trường 24/7 am hiểu sâu Nghị định 98 & Nghị định 07, hỗ trợ giải phóng hàng trong 4 giờ.\n"
                "3. Trang bị thùng giữ nhiệt chuyên dụng và thiết bị giám sát nhiệt độ IoT hành trình.\n\n"
                "Em xin phép được gửi bảng so sánh thời gian chuyển tải và biểu phí tham khảo cho tuyến hàng chủ lực của bên mình trong tuần này được không ạ?\n\n"
                "Trân trọng cảm ơn {salutation},"
            )
        )

        # 2. Electronics & Hi-Tech
        self.templates["electronics_cold_1"] = OutreachTemplate(
            template_id="electronics_cold_1",
            icp_category="electronics",
            subject_pattern="Tối ưu chi phí & thời gian air freight tuyến Đông Bắc Á cho {company}",
            body_pattern=(
                "Kính gửi {salutation} {contact_name},\n\n"
                "Qua theo dõi hoạt động sản xuất linh kiện công nghệ cao của {company} tại KCN, "
                "em hiểu rằng việc bảo đảm lịch bay cố định và giao hàng đúng hạn vào dây chuyền sản xuất là yếu tố sống còn để tránh rủi ro dừng chuyền.\n\n"
                "Minh Vân Logistics hiện đang sở hữu hạn ngạch tải cố định (Allotted Space) trên các chuyến bay hằng ngày từ Tokyo, Seoul, Thượng Hải về Nội Bài, "
                "kết hợp đoàn xe tải chuyên dụng giao thẳng nhà máy trước 08:00 sáng.\n\n"
                "Nếu {salutation} đang có nhu cầu tối ưu chi phí vận chuyển hoặc tìm kiếm forwarder dự phòng đáng tin cậy cho mùa cao điểm tới, "
                "em xin phép được kết nối nhanh qua Zalo hoặc cuộc gọi ngắn 5 phút để trao đổi thêm.\n\n"
                "Kính chúc {salutation} một ngày làm việc hiệu quả!"
            )
        )

    def get_template(self, icp_category: str) -> OutreachTemplate:
        for t in self.templates.values():
            if t.icp_category == icp_category:
                return t
        return self.templates.get("medical_cold_1")
