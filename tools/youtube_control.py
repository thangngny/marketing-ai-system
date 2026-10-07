"""
YouTube Control CLI for Minh Van Logistics Buzz Agents.
Enables agents to query YouTube channel status and recent videos.
"""
import sys
import os
import json
import argparse

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.append(r"C:\Users\Admin\marketing-ai-system\src")

from marketing_system.connectors.youtube import YouTubeConnector
from marketing_system.config import Settings
from marketing_system.constants import Environment
from marketing_system.credentials import read_credential

def get_live_conn():
    settings = Settings.from_env()
    settings.environment = Environment.PRODUCTION
    return YouTubeConnector(settings)

def cmd_status(args):
    conn = get_live_conn()
    ok, probe_msg = conn.probe_live()
    api_key_present = bool(read_credential("YOUTUBE_API_KEY"))
    channel_id = read_credential("YOUTUBE_CHANNEL_ID") or os.environ.get("YOUTUBE_CHANNEL_ID")

    status_data = {
        "status": "CONNECTED" if ok else "ERROR",
        "probe": probe_msg,
        "channel_id": channel_id,
        "credentials_present": api_key_present,
    }

    if getattr(args, 'json', False):
        print(json.dumps(status_data, indent=2, ensure_ascii=False))
        return 0 if ok else 1

    print("==================== YOUTUBE CONNECTOR STATUS ====================")
    print(f"Trạng thái: {'✅ KẾT NỐI THÀNH CÔNG (LIVE)' if ok else '❌ LỖI KẾT NỐI'}")
    print(f"Probe: {probe_msg}")
    print(f"Channel ID: {channel_id or 'Chưa cấu hình'}")
    print(f"API Key: {'Đã lưu trong Windows Credential Manager' if api_key_present else 'Chưa cấu hình'}")
    print("==================================================================")
    return 0 if ok else 1

def cmd_recent_videos(args):
    conn = get_live_conn()
    limit = args.limit or 5
    try:
        results = conn.read("recent_videos", limit=limit)
        if getattr(args, 'json', False):
            vids_data = [
                {
                    "id": v.external_id,
                    "title": v.title,
                    "url": v.metadata.get("url"),
                    "channel_title": v.metadata.get("channel_title"),
                    "published_at": v.created_at.isoformat() if v.created_at else None,
                }
                for v in results
            ]
            print(json.dumps(vids_data, indent=2, ensure_ascii=False))
        else:
            print(f"--- Top {len(results)} video gần nhất trên kênh YouTube Minh Vân Logistics ---")
            for idx, v in enumerate(results, 1):
                url = v.metadata.get("url", f"https://www.youtube.com/watch?v={v.external_id}")
                print(f"[{idx}] {v.title}")
                print(f"    URL: {url}")
                print(f"    Published: {v.created_at.strftime('%Y-%m-%d %H:%M:%S UTC') if v.created_at else 'N/A'}")
        return 0
    except Exception as e:
        print(f"Lỗi truy vấn YouTube: {e}", file=sys.stderr)
        return 1

def main():
    parser = argparse.ArgumentParser(description="YouTube Control CLI for Minh Van Logistics")
    subparsers = parser.add_subparsers(dest="command")

    p_status = subparsers.add_parser("status", help="Kiểm tra kết nối YouTube API")
    p_status.add_argument("--json", action="store_true", help="Xuất định dạng JSON")

    p_videos = subparsers.add_parser("videos", help="Xem danh sách video gần đây")
    p_videos.add_argument("--limit", type=int, default=5, help="Số lượng video cần lấy")
    p_videos.add_argument("--json", action="store_true", help="Xuất định dạng JSON")

    args = parser.parse_args()
    if not args.command or args.command == "status":
        return cmd_status(args)
    elif args.command == "videos":
        return cmd_recent_videos(args)
    else:
        parser.print_help()
        return 0

if __name__ == "__main__":
    sys.exit(main())
