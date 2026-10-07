"""
Meta AI (dev.meta.ai / Muse Spark / Muse Image) Control CLI for Minh Van Logistics Buzz Agents.
"""
import sys
import os
import json
import argparse

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.append(r"C:\Users\Admin\marketing-ai-system\src")

from marketing_system.config import Settings
from marketing_system.constants import Environment
from marketing_system.connectors.meta_ai import MetaAiConnector


def get_connector():
    settings = Settings.from_env()
    settings.environment = Environment.PRODUCTION
    return MetaAiConnector(settings)


def cmd_status(args):
    conn = get_connector()
    configured = conn.configured()
    ok, probe_msg = conn.probe_live() if configured else (False, "Chưa cấu hình META_AI_API_KEY")

    status_data = {
        "status": "CONNECTED" if ok else ("CONFIGURED" if configured else "NOT_CONFIGURED"),
        "probe_ok": ok,
        "detail": probe_msg,
        "api_key_configured": configured,
    }

    if getattr(args, "json", False):
        print(json.dumps(status_data, indent=2, ensure_ascii=False))
        return 0 if ok else 1

    print("==================== META AI (DEV.META.AI) STATUS ====================")
    print(f"Trạng thái kết nối : {'✅ HOẠT ĐỘNG (LIVE)' if ok else '❌ LỖI / CHƯA KẾT NỐI'}")
    print(f"API Key            : {'✅ ĐÃ CẤU HÌNH (Windows Credential Vault)' if configured else '❌ CHƯA CÓ'}")
    print(f"Chi tiết           : {probe_msg}")
    print("Mô hình hỗ trợ     : Muse Spark 1.3 (LLM Reasoning), Muse Image 1.0, SAM 3.1, Muse Voice Transcribe")
    print("=======================================================================")
    return 0 if ok else 1


def cmd_models(args):
    conn = get_connector()
    try:
        models = conn.list_models()
        if getattr(args, "json", False):
            print(json.dumps(models, indent=2, ensure_ascii=False))
            return 0

        print(f"=== DANH SÁCH MÔ HÌNH META AI KHẢ DỤNG ({len(models)} models) ===")
        for m in models:
            mid = m.get("id")
            owner = m.get("owned_by", "meta")
            desc = ""
            if "spark-1.3" in mid:
                desc = " (Flagship LLM - Đa ngữ, Suy luận sâu, Ngữ cảnh cực lớn)"
            elif "image" in mid:
                desc = " (Tạo ảnh chất lượng cao)"
            elif "voice-transcribe" in mid:
                desc = " (Chuyển giọng nói thành văn bản)"
            elif "sam" in mid:
                desc = " (Segment Anything 3.1 - Tách nền, vật thể)"
            print(f"• {mid:<30} [Owner: {owner}]{desc}")
        print("================================================================")
        return 0
    except Exception as e:
        print(f"Lỗi khi lấy danh sách model: {e}", file=sys.stderr)
        return 1


def cmd_chat(args):
    conn = get_connector()
    prompt = args.prompt
    model = getattr(args, "model", None) or "muse-spark-1.3"
    print(f"Đang gửi yêu cầu tới Meta AI ({model})...")
    try:
        messages = [{"role": "user", "content": prompt}]
        res = conn.chat_completion(messages=messages, model=model, max_tokens=getattr(args, "max_tokens", 800))
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            choice = res.get("choices", [{}])[0].get("message", {}).get("content", "")
            print("\n=== KẾT QUẢ TỪ META AI ===")
            print(choice)
        return 0
    except Exception as e:
        err_msg = str(e)
        if "402" in err_msg or "billing" in err_msg.lower():
            print("\n⚠️ THÔNG BÁO TỪ META AI:", file=sys.stderr)
            print("Tài khoản của bạn đã kết nối thành công với dev.meta.ai, nhưng cần thêm Thẻ thanh toán (Billing / Payment Method) tại trang https://dev.meta.ai để mở khóa hạn mức gọi sinh lời (Inference Quota).", file=sys.stderr)
            print("Sau khi thêm thẻ thanh toán trên dev.meta.ai, bạn có thể gọi tạo văn bản và phân tích ngay lập tức!", file=sys.stderr)
        else:
            print(f"Lỗi: {e}", file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(description="Meta AI Control CLI for Minh Van Logistics")
    subparsers = parser.add_subparsers(dest="command")

    p_status = subparsers.add_parser("status", help="Kiểm tra kết nối tới dev.meta.ai")
    p_status.add_argument("--json", action="store_true", help="Xuất định dạng JSON")

    p_models = subparsers.add_parser("models", help="Xem danh sách các model khả dụng (Muse Spark, Muse Image,...)")
    p_models.add_argument("--json", action="store_true", help="Xuất định dạng JSON")

    p_chat = subparsers.add_parser("chat", help="Tạo văn bản hoặc phân tích với Muse Spark 1.3")
    p_chat.add_argument("--prompt", required=True, help="Nội dung yêu cầu / câu hỏi")
    p_chat.add_argument("--model", default="muse-spark-1.3", help="Model sử dụng (mặc định: muse-spark-1.3)")
    p_chat.add_argument("--max-tokens", type=int, default=800, help="Số token tối đa")
    p_chat.add_argument("--json", action="store_true", help="Xuất định dạng JSON")

    args = parser.parse_args()
    if not args.command or args.command == "status":
        return cmd_status(args)
    elif args.command == "models":
        return cmd_models(args)
    elif args.command == "chat":
        return cmd_chat(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
