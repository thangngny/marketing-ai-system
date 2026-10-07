"""
Meta & Facebook Control CLI for Minh Van Logistics Buzz Agents.
Enables agents to query Meta Ads account status, Facebook Page status, and manage drafts.
"""
import sys
import os
import json
import argparse

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.append(r"C:\Users\Admin\marketing-ai-system\src")

from marketing_system.connectors.meta_ads import MetaAdsConnector
from marketing_system.config import Settings
from marketing_system.constants import Environment
from marketing_system.credentials import read_credential

def get_live_conn():
    settings = Settings.from_env()
    settings.environment = Environment.PRODUCTION
    return MetaAdsConnector(settings)

def cmd_status(args):
    conn = get_live_conn()
    ok, probe_msg = conn.probe_live()
    page_id = read_credential("META_PAGE_ID")
    page_token = read_credential("META_PAGE_ACCESS_TOKEN")
    page_ok = False
    page_name = "N/A"
    
    if page_id and page_token:
        try:
            resp = conn.request(
                "GET",
                f"https://graph.facebook.com/v23.0/{page_id}",
                params={"fields": "id,name"},
                headers={"Authorization": f"Bearer {page_token}"},
                timeout=10.0
            )
            if resp.is_success:
                page_ok = True
                page_name = resp.json().get("name", "N/A")
        except Exception:
            pass

    status_data = {
        "status": "CONNECTED" if (ok or page_ok) else "ERROR",
        "ad_account_probe": probe_msg,
        "ad_account_ok": ok,
        "ad_account_id": read_credential("META_AD_ACCOUNT_ID"),
        "page_ok": page_ok,
        "page_id": page_id,
        "page_name": page_name,
    }

    if getattr(args, 'json', False):
        print(json.dumps(status_data, indent=2, ensure_ascii=False))
        return 0 if (ok or page_ok) else 1

    print("==================== META / FACEBOOK STATUS ====================")
    print(f"Trạng thái tổng thể: {'✅ KẾT NỐI HOẠT ĐỘNG' if (ok or page_ok) else '❌ LỖI KẾT NỐI'}")
    print(f"• Facebook Page  : {'✅ LIVE' if page_ok else '❌ LỖI'} -> {page_name} (ID: {page_id})")
    print(f"• Meta Ad Account: {'✅ LIVE' if ok else '❌ LỖI'} -> {probe_msg}")
    print("================================================================")
    return 0 if (ok or page_ok) else 1

def cmd_draft_post(args):
    conn = get_live_conn()
    try:
        res = conn.create_page_post_draft(args.message)
        if getattr(args, 'json', False):
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print("✅ Đã tạo bản nháp bài đăng trên Facebook Page thành công!")
            print(f"Post ID: {res.get('post_id')}")
            print(f"Nội dung: {res.get('message')}")
        return 0
    except Exception as e:
        print(f"Lỗi khi tạo draft post: {e}", file=sys.stderr)
        return 1

def cmd_publish_post(args):
    conn = get_live_conn()
    try:
        res = conn.publish_page_post(args.message, getattr(args, 'link', None))
        if getattr(args, 'json', False):
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print("✅ ĐÃ ĐĂNG BÀI TRỰC TIẾP LÊN FACEBOOK PAGE THÀNH CÔNG!")
            print(f"Post ID: {res.get('post_id')}")
            print(f"Nội dung: {res.get('message')}")
            if res.get('link'):
                print(f"Link: {res.get('link')}")
            print(f"Xem bài đăng: https://facebook.com/{res.get('post_id')}")
        return 0
    except Exception as e:
        print(f"Lỗi khi đăng bài Facebook: {e}", file=sys.stderr)
        return 1

def main():
    parser = argparse.ArgumentParser(description="Meta & Facebook Control CLI for Minh Van Logistics")
    subparsers = parser.add_subparsers(dest="command")

    p_status = subparsers.add_parser("status", help="Kiểm tra kết nối Facebook Page và Meta Ad Account")
    p_status.add_argument("--json", action="store_true", help="Xuất định dạng JSON")

    p_draft = subparsers.add_parser("draft-post", help="Tạo bài viết nháp (unpublished draft) trên Facebook Page")
    p_draft.add_argument("--message", required=True, help="Nội dung bài viết")
    p_draft.add_argument("--json", action="store_true", help="Xuất định dạng JSON")

    p_publish = subparsers.add_parser("publish-post", help="Đăng bài trực tiếp (live public) lên Facebook Page")
    p_publish.add_argument("--message", required=True, help="Nội dung bài viết")
    p_publish.add_argument("--link", default=None, help="Link đính kèm (tùy chọn)")
    p_publish.add_argument("--json", action="store_true", help="Xuất định dạng JSON")

    args = parser.parse_args()
    if not args.command or args.command == "status":
        return cmd_status(args)
    elif args.command == "draft-post":
        return cmd_draft_post(args)
    elif args.command == "publish-post":
        return cmd_publish_post(args)
    else:
        parser.print_help()
        return 0

if __name__ == "__main__":
    sys.exit(main())
