# SKILL 02: Tìm kiếm doanh nghiệp tiềm năng đa nguồn

## 1. Mục đích
Tìm kiếm danh sách doanh nghiệp nhập khẩu/xuất khẩu thông qua Apollo, niên giám doanh nghiệp, tờ khai mẫu.

## 2. Đầu vào (Inputs)
- Dữ liệu yêu cầu từ người dùng hoặc bước trước trong quy trình.
- Bộ lọc phân khúc, từ khóa ngành hoặc danh sách ứng viên.

## 3. Công cụ & Dịch vụ sử dụng
- FastMCP Marketing Hub Tools (prospecting.*, crm.*, email.*).
- Engine thẩm định và chấm điểm (LeadVerifier, TwoAxisScorer).
- Bộ nhớ tri thức GTM Brain (gtm-brain/).

## 4. Chốt kiểm soát an toàn (Policy Ceilings)
- Nghiêm cấm phát tán email thật hoặc thay đổi cơ sở dữ liệu production mà không có chữ ký phê duyệt.
- Dữ liệu thu thập phải có nguồn gốc rõ ràng (source_provider).

## 5. Kết quả đầu ra (Outputs)
- Bản ghi dữ liệu có cấu trúc (JSON / Markdown Report).
- Cập nhật nhật ký hành trình workflow.
