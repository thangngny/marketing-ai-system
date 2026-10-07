"""
TikTok Control CLI for Minh Van Logistics Buzz Agents.
Enables agents to query TikTok channel status, profile information, and recent videos.
"""
import sys
import os
import json
import argparse
from pathlib import Path

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add marketing-system to path for connector reuse
sys.path.append(r"C:\Users\Admin\marketing-ai-system\src")

from marketing_system.connectors.tiktok import TikTokConnector
from marketing_system.config import Settings
from marketing_system.credentials import read_credential

def get_live_conn():
    settings = Settings.from_env()
    settings.environment = "production"
    return TikTokConnector(settings)

def cmd_status(args):
    conn = get_live_conn()
    ok, msg = conn.probe_live()
    open_id = read_credential("TIKTOK_OPEN_ID") or "N/A"
    refresh_token = read_credential("TIKTOK_REFRESH_TOKEN")
    has_token = bool(refresh_token)
    
    if args.json:
        print(json.dumps({
            "status": "CONNECTED" if ok else "ERROR",
            "live_probe_ok": ok,
            "message": msg,
            "channel": "Minh Van Logistics",
            "open_id": open_id,
            "credentials_present": has_token,
            "scopes": ["user.info.basic", "video.publish", "video.upload"]
        }, indent=2, ensure_ascii=False))
        return 0 if ok else 1

    print("=== TIKTOK CHANNEL STATUS ===")
    print(f"Status: {'CONNECTED (LIVE)' if ok else 'ERROR'}")
    print(f"Probe: {msg}")
    print(f"Channel: Minh Van Logistics (@minhvanlogistics)")
    print(f"Open ID: {open_id}")
    print(f"Active Scopes: user.info.basic, video.publish, video.upload")
    print(f"Token Stored: {'Yes (Windows Credential Manager)' if has_token else 'No'}")
    return 0 if ok else 1

def cmd_channel(args):
    conn = get_live_conn()
    metrics = conn.get_channel_metrics()
    if args.json:
        print(json.dumps(metrics, indent=2, ensure_ascii=False))
    else:
        print(f"Channel: {metrics.get('channel')}")
        print(f"Avatar: {metrics.get('avatar_url')}")
        print(f"Followers: {metrics.get('followers')}")
        print(f"Likes: {metrics.get('likes')}")
        print(f"Videos: {metrics.get('videos')}")
    return 0

def cmd_videos(args):
    conn = get_live_conn()
    try:
        videos = conn.get_recent_videos(limit=args.limit)
        if args.json:
            print(json.dumps(videos, indent=2, ensure_ascii=False))
        else:
            print(f"Recent videos ({len(videos)} found):")
            for v in videos:
                print(f"- [{v.get('id')}] {v.get('title')} ({v.get('duration')}s) - Views: {v.get('views')}")
    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}, indent=2))
        else:
            print(f"Could not fetch recent videos: {e}")
            print("Note: video.list scope may be required or no videos uploaded yet.")
    return 0

def cmd_publish_video(args):
    conn = get_live_conn()
    try:
        res = conn.upload_video_file(
            file_path=args.file,
            title=args.title or "",
            privacy_level=args.privacy,
            publish_mode=args.mode
        )
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print("✅ ĐÃ UPLOAD / XUẤT BẢN VIDEO LÊN TIKTOK THÀNH CÔNG!")
            print(f"Publish ID: {res.get('publish_id')}")
            print(f"Chế độ: {res.get('mode')}")
            print(f"Tiêu đề: {args.title or args.file}")
        return 0
    except Exception as e:
        print(f"Lỗi khi xuất bản video TikTok: {e}", file=sys.stderr)
        return 1

def main():
    parser = argparse.ArgumentParser(prog="tiktok-control", description="TikTok Channel Control for Buzz Agents")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    sub = parser.add_subparsers(dest="command", required=True)
    
    sub.add_parser("status", help="Probe connection and channel status")
    sub.add_parser("channel", help="Get channel details and avatar")
    
    vid = sub.add_parser("videos", help="List recent videos")
    vid.add_argument("--limit", type=int, default=10, help="Max videos to return")

    pub = sub.add_parser("publish-video", help="Tải lên và xuất bản video lên TikTok")
    pub.add_argument("--file", required=True, help="Đường dẫn file video (.mp4)")
    pub.add_argument("--title", default="", help="Tiêu đề video / caption")
    pub.add_argument("--privacy", default="PUBLIC_TO_EVERYONE", choices=["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"], help="Quyền riêng tư")
    pub.add_argument("--mode", default="auto", choices=["auto", "direct", "inbox"], help="Chế độ xuất bản")
    
    args = parser.parse_args()
    if args.command == "status":
        sys.exit(cmd_status(args))
    elif args.command == "channel":
        sys.exit(cmd_channel(args))
    elif args.command == "videos":
        sys.exit(cmd_videos(args))
    elif args.command == "publish-video":
        sys.exit(cmd_publish_video(args))

if __name__ == "__main__":
    main()
