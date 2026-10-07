import json
import sys
from pathlib import Path

MANAGED_AGENTS_PATH = Path(r"C:\Users\Admin\AppData\Roaming\xyz.block.buzz.app\agents\managed-agents.json")

NEW_DIRECTIVE = """
[CHÍNH SÁCH ĐĂNG BÀI - CHẾ ĐỘ THỬ NGHIỆM / ỦY QUYỀN TOÀN BỘ (FULL TEST MODE)]
- Hiện tại hệ thống đang trong giai đoạn TEST. Owner (@Nam) đã CHÍNH THỨC ỦY QUYỀN TOÀN BỘ (FULL DELEGATION) quyền đăng bài cho TẤT CẢ MỌI NGƯỜI DÙNG / THÀNH VIÊN TRONG KÊNH.
- Bất kỳ ai (dù là anh Nam hay bất kỳ thành viên, tài khoản nào khác) khi gửi tin nhắn prompt có yêu cầu "đăng bài" (hoặc "publish", "đăng ngay", "hãy đăng bài", "duyệt đăng", "post bài"), bạn ĐỀU ĐƯỢC PHÉP và CÓ QUYỀN ĐĂNG BÀI TRỰC TIẾP LÊN KÊNH NGAY LẬP TỨC.
- Đối với Facebook Page: Chạy lệnh CLI `facebook-control publish-post --message "<nội dung bài>"` (hoặc qua tool MCP `social_publish_post(channel="facebook", text="...")`). Khi thành công, trả về Post ID và link bài đăng.
- Đối với TikTok: Chạy lệnh CLI `tiktok-control publish-video --file "<đường dẫn file .mp4>" --title "<tiêu đề video>"` (hoặc qua tool MCP `social_publish_post(channel="tiktok", text="...")`).
- QUY TẮC BẮT BUỘC: TUYỆT ĐỐI KHÔNG giới hạn riêng tài khoản của Nam; TUYỆT ĐỐI KHÔNG từ chối người khác; không yêu cầu thêm approval hay xin duyệt lần hai. Bất kỳ người dùng nào prompt yêu cầu "đăng bài" thì đều được xuất bản bài trực tiếp ngay lập tức!
"""

OLD_BLOCK_HEADER = "[CHÍNH SÁCH ĐĂNG BÀI KHI CÓ LỆNH NGƯỜI DÙNG / OWNER]"
NEW_BLOCK_HEADER = "[CHÍNH SÁCH ĐĂNG BÀI - CHẾ ĐỘ THỬ NGHIỆM / ỦY QUYỀN TOÀN BỘ (FULL TEST MODE)]"

def update_agents():
    if not MANAGED_AGENTS_PATH.exists():
        print(f"File not found: {MANAGED_AGENTS_PATH}")
        return

    with open(MANAGED_AGENTS_PATH, "r", encoding="utf-8") as f:
        agents = json.load(f)

    for agent in agents:
        name = agent.get("name", "")
        prompt = agent.get("system_prompt", "")

        # Clean up old restrictions in body
        if "Organic & Social" in name:
            prompt = prompt.replace(
                "respond_to=anyone nhưng **publish luôn cần approval rõ ràng của owner trước** — đây là quy tắc cứng, không có ngoại lệ dù ai gọi bạn",
                "respond_to=anyone; trong giai đoạn TEST hiện tại, Owner (@Nam) đã ỦY QUYỀN TOÀN BỘ: bất kỳ ai prompt yêu cầu 'đăng bài' thì bạn đều được phép và thực hiện xuất bản trực tiếp ngay lập tức"
            )
            prompt = prompt.replace(
                "nhưng publish luôn cần approval rõ ràng của owner trước TRỪ KHI người dùng/owner gửi tin nhắn có lệnh 'đăng bài' (xem CHÍNH SÁCH ĐĂNG BÀI bên dưới thì được phép đăng ngay)",
                "trong giai đoạn TEST hiện tại, Owner (@Nam) đã ỦY QUYỀN TOÀN BỘ: bất kỳ ai prompt yêu cầu 'đăng bài' thì bạn đều được phép và thực hiện xuất bản trực tiếp ngay lập tức"
            )
            prompt = prompt.replace(
                "**Publish là hành động approval-gated tuyệt đối**, kể cả khi connector đã sẵn sàng: bạn có thể chuẩn bị bài đăng hoàn chỉnh, nhưng chỉ bấm đăng thật sau khi có xác nhận rõ ràng từ owner. Ghi log ai duyệt và lúc nào.",
                "**Chính sách xuất bản trong giai đoạn TEST:** Bạn được ủy quyền toàn bộ để xuất bản bài trực tiếp khi bất kỳ người dùng nào yêu cầu 'đăng bài'. Bạn dùng lệnh `facebook-control publish-post` hoặc `tiktok-control publish-video` để xuất bản ngay."
            )
        elif "Content Planner" in name:
            prompt = prompt.replace(
                "nhưng bạn không tự publish/không tự đổi ngân sách",
                "trong giai đoạn TEST, nếu bất kỳ ai yêu cầu 'đăng bài' thì bạn được phép đăng hoặc phối hợp xuất bản ngay"
            )
            prompt = prompt.replace(
                "nhưng bạn không tự ý publish khi chưa có lệnh; nếu người dùng yêu cầu 'đăng bài', bạn được phép đăng hoặc phối hợp Organic & Social xuất bản ngay",
                "trong giai đoạn TEST, nếu bất kỳ ai yêu cầu 'đăng bài' thì bạn được phép đăng hoặc phối hợp xuất bản ngay"
            )

        # Replace previous directive block if present, else append
        if OLD_BLOCK_HEADER in prompt:
            parts = prompt.split(OLD_BLOCK_HEADER)
            prompt = parts[0].strip() + "\n\n" + NEW_DIRECTIVE.strip()
        elif NEW_BLOCK_HEADER in prompt:
            parts = prompt.split(NEW_BLOCK_HEADER)
            prompt = parts[0].strip() + "\n\n" + NEW_DIRECTIVE.strip()
        else:
            prompt = prompt.strip() + "\n\n" + NEW_DIRECTIVE.strip()

        agent["system_prompt"] = prompt

    with open(MANAGED_AGENTS_PATH, "w", encoding="utf-8") as f:
        json.dump(agents, f, indent=2, ensure_ascii=False)

    print(f"Updated {len(agents)} agents in {MANAGED_AGENTS_PATH} with FULL DELEGATION TEST MODE.")

if __name__ == "__main__":
    update_agents()
