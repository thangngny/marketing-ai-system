import json
import shutil
from pathlib import Path

path = Path(r"C:\Users\Admin\AppData\Roaming\xyz.block.buzz.app\agents\managed-agents.json")
backup = Path(r"C:\Users\Admin\AppData\Roaming\xyz.block.buzz.app\agents\managed-agents.json.bak")
shutil.copy2(path, backup)

with open(path, "r", encoding="utf-8") as f:
    agents = json.load(f)

codex_instruction = """

Khả năng sử dụng Codex App trong máy tính:
- Khi người dùng yêu cầu bạn "sử dụng Codex App", "dùng Codex App", hoặc "mở Codex App" để làm tác vụ:
  + Bạn có công cụ MCP codex_run (hoặc lệnh CLI `codex-control exec "..."`) để chuyển giao tác vụ trực tiếp cho OpenAI Codex App/CLI trên máy tính thực thi.
  + Bạn có công cụ MCP codex_open (hoặc lệnh CLI `codex-control open`) để bật/mở giao diện Codex Desktop App trên Windows.
  + Bạn có công cụ MCP codex_status (hoặc `codex-control status`) để kiểm tra trạng thái hoạt động của Codex App và App-Server daemon.
- Sau khi Codex App thực thi xong, bạn lấy kết quả trả về, giải thích và báo cáo lại đầy đủ cho người dùng trong kênh Buzz.
"""

core_instruction = """Bạn là agent trên nền tảng Buzz kết nối với hệ thống Marketing AI của Minh Vân Logistics.
Bạn có quyền truy cập toàn bộ công cụ của MCP server marketing-system, bao gồm các công cụ điều khiển và thực thi OpenAI Codex App trên máy tính:
- codex_run: Giao việc cho OpenAI Codex App/CLI thực thi tác vụ trên máy tính và trả về kết quả.
- codex_open: Bật/mở giao diện ứng dụng Codex Desktop trên Windows.
- codex_status: Kiểm tra trạng thái Codex CLI, Desktop App và daemon.
Khi người dùng yêu cầu sử dụng Codex App để làm bất kỳ tác vụ nào, hãy gọi công cụ này để thực hiện và phản hồi lại cho người dùng."""

specialists = [
    "Marketing Orchestrator", "Strategy", "Research Intelligence", "Knowledge",
    "Content Planner", "Creative Studio", "Organic & Social", "Paid Media",
    "SEO & Web", "CRM & Lifecycle", "Sales Enablement", "Analytics & Finance"
]

core_agents = ["Antigravity", "Claude", "Codex"]

count = 0
for agent in agents:
    name = agent.get("name")
    if name in specialists:
        prompt = agent.get("system_prompt") or ""
        if "Khả năng sử dụng Codex App" not in prompt:
            agent["system_prompt"] = prompt + codex_instruction
            count += 1
    elif name in core_agents:
        prompt = agent.get("system_prompt") or ""
        if not prompt or "Codex App" not in prompt:
            agent["system_prompt"] = (prompt + "\n\n" + core_instruction).strip()
            count += 1

with open(path, "w", encoding="utf-8") as f:
    json.dump(agents, f, ensure_ascii=False, indent=2)

print(f"Successfully updated {count} agent prompts in managed-agents.json")
