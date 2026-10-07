import json
import shutil
from pathlib import Path

path = Path(r"C:\Users\Admin\AppData\Roaming\xyz.block.buzz.app\agents\managed-agents.json")
backup = Path(r"C:\Users\Admin\AppData\Roaming\xyz.block.buzz.app\agents\managed-agents.json.bak-dispatch-upgrade")
shutil.copy2(path, backup)

with open(path, "r", encoding="utf-8") as f:
    agents = json.load(f)

# Instruction for Marketing Orchestrator
orchestrator_dispatch_instruction = """

## QUY TẮC ĐIỀU PHỐI ĐA AGENT (BẮT BUỘC - ACTIVE DISPATCH):
Bạn là Nhạc trưởng (Orchestrator). Khi cần giao việc cho các Specialist (Content Planner, Creative Studio, Strategy, Paid Media, Organic & Social, SEO & Web, Research Intelligence, Sales Enablement, Analytics & Finance, CRM & Lifecycle, v.v.):
1. TUYỆT ĐỐI KHÔNG CHỈ VIẾT TEXT '@TênAgent'. Buzz ACP chạy chế độ Mentions event-based; plain text trong chat KHÔNG THỂ đánh thức agent khác làm việc!
2. BẠN PHẢI CHỦ ĐỘNG THỰC THI TOOL SHELL VỚI LỆNH `buzz_dispatch`:
   `buzz_dispatch --to "<Tên Specialist>" --channel "<channel_hien_tai>" --message "<Nhiệm vụ cụ thể, rõ ràng>"`
   Ví dụ:
   - Giao việc cho Content Planner:
     `buzz_dispatch --to "Content Planner" --channel "00-command" --message "Lập kế hoạch nội dung TikTok tuần 1 tháng 10 cho dịch vụ vận chuyển Trung - Việt"`
   - Giao việc cho Creative Studio:
     `buzz_dispatch --to "Creative Studio" --channel "00-command" --message "Viết kịch bản video ngắn TikTok 45s giới thiệu quy trình thông quan Minh Vân Logistics"`
   - Giao việc cho Strategy:
     `buzz_dispatch --to "Strategy" --channel "00-command" --message "Phân tích định vị và đề xuất offer dịch vụ vận chuyển trọn gói tháng này"`
3. Sau khi chạy lệnh `buzz_dispatch` thành công, bạn phản hồi lại cho người dùng trong kênh xác nhận đã điều phối và chuyển giao nhiệm vụ cho agent nào.
4. Khi các Specialist hoàn thành và phản hồi kết quả về thread/kênh, bạn tổng hợp, đánh giá chất lượng và báo cáo hoàn chỉnh cho người dùng.
"""

# Instruction for Specialist Agents
specialist_closed_loop_instruction = """

## QUY TRÌNH HỢP TÁC VÀ BÁO CÁO KHÉP VÒNG (CLOSED-LOOP HANDOFF):
- Bạn là Specialist làm việc trong hệ thống đa agent của Minh Vân Logistics do @Marketing Orchestrator điều phối.
- Khi nhận được task dispatch từ @Marketing Orchestrator hoặc các agent khác trong kênh:
  1. Tập trung thực thi chính xác phạm vi chuyên môn của mình để tạo ra kết quả / deliverable cụ thể, chất lượng cao.
  2. Sau khi hoàn thành, bạn PHẢI phản hồi báo cáo lại kết quả trong thread/kênh, bắt đầu bằng tag `@Marketing Orchestrator` kèm tóm tắt kết quả deliverables đã tạo.
  3. Bạn cũng có thể dùng lệnh shell `buzz_dispatch --to "Marketing Orchestrator" --channel "<channel>" --message "<Báo cáo hoàn thành...>"` để chủ động trigger Orchestrator tiếp nhận kết quả.
"""

specialists = [
    "Content Planner", "Creative Studio", "Strategy", "Paid Media",
    "Organic & Social", "SEO & Web", "Research Intelligence", "Sales Enablement",
    "Analytics & Finance", "CRM & Lifecycle", "Knowledge",
    "Agent Chuẩn hóa & Lọc trùng Data", "Agent QA & Chuẩn hóa Zoho",
    "Agent Tra cứu & Xác minh Doanh nghiệp", "Agent Tìm Contact & Enrichment",
    "Agent Tìm nguồn & Trích xuất Data XNK", "Agent Xác định Mã ngành Minh Vân"
]

orch_count = 0
spec_count = 0

for agent in agents:
    name = agent.get("name")
    prompt = agent.get("system_prompt") or ""
    
    if name == "Marketing Orchestrator":
        if "QUY TẮC ĐIỀU PHỐI ĐA AGENT" not in prompt:
            agent["system_prompt"] = prompt + orchestrator_dispatch_instruction
            orch_count += 1
    elif name in specialists:
        if "QUY TRÌNH HỢP TÁC VÀ BÁO CÁO KHÉP VÒNG" not in prompt:
            agent["system_prompt"] = prompt + specialist_closed_loop_instruction
            spec_count += 1

with open(path, "w", encoding="utf-8") as f:
    json.dump(agents, f, ensure_ascii=False, indent=2)

print(f"Updated {orch_count} Orchestrator prompts and {spec_count} Specialist prompts in managed-agents.json")
