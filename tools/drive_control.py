#!/usr/bin/env python3
"""
Google Drive Control CLI for Buzz Agents & Workstation.
Allows all agents to search, read, list, and export files from Google Drive (minhvanitl@gmail.com).
"""
import sys
import os
import json
import argparse

# Add marketing-ai-system to sys.path
PROJECT_ROOT = r"C:\Users\Admin\marketing-ai-system"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from marketing_system.config import Settings
from marketing_system.connectors.google_drive import GoogleDriveConnector

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def get_connector():
    settings = Settings()
    return GoogleDriveConnector(settings)

def cmd_search(args):
    conn = get_connector()
    results = conn.search_files(query=args.query, limit=args.limit, mime_type=args.type)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    print(f"=== KẾT QUẢ TÌM KIẾM TRÊN GOOGLE DRIVE CHO '{args.query}' ({len(results)} tệp) ===")
    if not results:
        print("Không tìm thấy tệp nào phù hợp.")
        return
    for idx, f in enumerate(results, 1):
        size_str = f"{int(f.get('size', 0)) / 1024:.1f} KB" if f.get('size') else "Cloud Doc"
        print(f"[{idx}] {f.get('name')} | ID: {f.get('id')}")
        print(f"    Loại: {f.get('mimeType')} | Cập nhật: {f.get('modifiedTime')} | Dung lượng: {size_str}")
        print(f"    Link xem: {f.get('webViewLink')}")

def cmd_read(args):
    conn = get_connector()
    res = conn.read_file_content(file_id=args.file_id, max_chars=args.max_chars)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    print(f"=== NỘI DUNG TỆP: {res.get('name')} ===")
    print(f"ID: {res.get('id')} | Loại: {res.get('mime_type')}")
    print(f"Link: {res.get('web_url')}")
    print("--------------------------------------------------------------------------------")
    print(res.get("content", ""))
    print("--------------------------------------------------------------------------------")
    if res.get("truncated"):
        print(f"*(Nội dung đã được cắt bớt do vượt quá {args.max_chars} ký tự. Tổng ký tự: {res.get('total_chars')})*")

def cmd_list(args):
    conn = get_connector()
    results = conn.search_files(query="", limit=args.limit)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    print(f"=== DANH SÁCH TỆP GẦN ĐÂY TRÊN GOOGLE DRIVE ({len(results)} tệp) ===")
    for idx, f in enumerate(results, 1):
        print(f"[{idx}] {f.get('name')} | ID: {f.get('id')} | Loại: {f.get('mimeType')}")
        print(f"    Link xem: {f.get('webViewLink')}")

def cmd_status(args):
    conn = get_connector()
    ok, detail = conn.probe_live()
    token = conn._access_token()
    import httpx
    r = httpx.get("https://www.googleapis.com/drive/v3/about?fields=user,storageQuota", headers={"Authorization": f"Bearer {token}"})
    if r.is_success:
        user = r.json().get("user", {})
        quota = r.json().get("storageQuota", {})
        limit_gb = round(int(quota.get("limit", 0)) / (1024**3), 2)
        usage_gb = round(int(quota.get("usage", 0)) / (1024**3), 2)
        print("=== TRẠNG THÁI KẾT NỐI GOOGLE DRIVE ===")
        print(f"Trạng thái: 🟢 LIVE OK ({detail})")
        print(f"Người dùng: {user.get('displayName')} ({user.get('emailAddress')})")
        print(f"Dung lượng: Đã dùng {usage_gb} GB / {limit_gb} GB")
    else:
        print(f"Lỗi truy vấn: {r.status_code} - {r.text}")

def main():
    parser = argparse.ArgumentParser(description="Google Drive Control CLI for Buzz Agents")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_status = subparsers.add_parser("status", help="Kiểm tra trạng thái kết nối Google Drive")
    p_status.set_defaults(func=cmd_status)

    p_search = subparsers.add_parser("search", help="Tìm kiếm tệp trên Google Drive theo tên")
    p_search.add_argument("query", help="Từ khóa tìm kiếm")
    p_search.add_argument("--limit", type=int, default=15, help="Số lượng kết quả tối đa")
    p_search.add_argument("--type", type=str, default=None, help="MIME type lọc (tùy chọn)")
    p_search.add_argument("--json", action="store_true", help="Xuất kết quả JSON")
    p_search.set_defaults(func=cmd_search)

    p_read = subparsers.add_parser("read", help="Đọc nội dung văn bản/bảng tính của tệp")
    p_read.add_argument("file_id", help="Google Drive File ID")
    p_read.add_argument("--max-chars", type=int, default=50000, help="Số ký tự tối đa cần đọc")
    p_read.add_argument("--json", action="store_true", help="Xuất kết quả JSON")
    p_read.set_defaults(func=cmd_read)

    p_list = subparsers.add_parser("list", help="Danh sách các tệp gần đây trên Google Drive")
    p_list.add_argument("--limit", type=int, default=15, help="Số lượng kết quả")
    p_list.add_argument("--json", action="store_true", help="Xuất kết quả JSON")
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
