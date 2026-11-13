# MINH VAN LOGISTICS — GTM BRAIN (ENTERPRISE KNOWLEDGE HUB)

## 1. Giới thiệu
GTM Brain là bộ não tri thức tập trung dùng chung cho toàn bộ hệ sinh thái Buzz Marketing OS và các AI Agent tại Công ty CP Vận tải Quốc tế Minh Vân (Minh Van ITL).
Mọi agent (Account Intelligence, Content, Sales Copilot, Campaign, Orchestrator) khi lập kế hoạch, viết email, thẩm định khách hàng, hoặc tư vấn bán hàng đều phải truy vấn và tuân thủ các nguyên tắc được định nghĩa tại đây.

---

## 2. Cấu trúc thư mục

```
gtm-brain/
├── README.md                  # Bản quy chuẩn chung
├── services/                  # Hồ sơ năng lực dịch vụ logistics cốt lõi
│   ├── air_freight.md         # Vận tải hàng không quốc tế & hỏa tốc
│   └── customs_clearance.md   # Dịch vụ khai báo hải quan & giấy phép chuyên ngành
├── icp/                       # Hồ sơ khách hàng lý tưởng (Ideal Customer Profile)
│   ├── medical_devices.md     # ICP Nhóm 1: Nhập khẩu thiết bị y tế, sinh phẩm
│   └── electronics_hitech.md  # ICP Nhóm 2: Linh kiện điện tử, bán dẫn, vi mạch
├── policies/                  # Quy chuẩn an toàn, bảo mật & chính sách tiếp cận
│   └── outreach_policy.md     # Nghị định 91/2020/NĐ-CP, bảo vệ dữ liệu & quy tắc tiếp cận
├── approved-content/          # Mẫu nội dung, kịch bản email, kịch bản telesale đã phê duyệt
│   └── email_templates.md     # Template email tiếp cận theo từng ngành
└── skills/                    # 12 Kỹ năng chuẩn hóa cho GTM AI Agents
    ├── 01_research_market.md
    ├── 02_discover_companies.md
    ├── 03_verify_company.md
    ├── 04_deduplicate_leads.md
    ├── 05_score_leads.md
    ├── 06_build_segment.md
    ├── 07_prepare_offer.md
    ├── 08_draft_outreach.md
    ├── 09_classify_reply.md
    ├── 10_prepare_sales_handoff.md
    ├── 11_summarize_campaign.md
    └── 12_propose_brain_update.md
```

---

## 3. Nguyên tắc vận hành cốt lõi (GTM Core Rules)
1. **Fact vs Inference**: Phân định rạch ròi giữa dữ liệu định danh pháp lý có bằng chứng (MST, Tên pháp nhân, Domain) và dữ liệu phỏng đoán (Sản lượng ước tính, Tuyến bay phù hợp).
2. **Approval Gate**: Không có bất kỳ email thật, cuộc gọi thật hay bản ghi CRM nào được phát sinh ra bên ngoài mà không có xác nhận của Quản trị viên (Owner).
3. **Traceability**: Mọi lead đưa vào hệ thống phải có đầy đủ nguồn thu thập (`source_provider`) và đường dẫn tham chiếu.
