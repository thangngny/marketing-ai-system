"""
Zoho CRM Control CLI for Minh Van Logistics Buzz Agents.
Enables agents to query Zoho CRM status, organization details, and records.
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

from marketing_system.connectors.zoho import ZohoConnector
from marketing_system.config import Settings
from marketing_system.constants import Environment
from marketing_system.credentials import read_credential, credential_present

def get_live_conn():
    settings = Settings.from_env()
    settings.environment = Environment.PRODUCTION
    return ZohoConnector(settings)

def get_org_info(conn):
    try:
        token, domain = conn._access_context()
        resp = conn.request(
            'GET',
            f"{domain.rstrip('/')}/crm/v8/org",
            headers={'Authorization': f'Zoho-oauthtoken {token}'},
            timeout=15.0
        )
        if resp.is_success:
            orgs = resp.json().get('org', [])
            if orgs:
                return orgs[0]
    except Exception:
        pass
    return None

def cmd_status(args):
    conn = get_live_conn()
    ok, probe_msg = conn.probe_live()
    org = get_org_info(conn)
    
    status_data = {
        "status": "CONNECTED" if ok else "ERROR",
        "transport": conn.transport(),
        "probe": probe_msg,
        "credentials": {
            "ZOHO_CLIENT_ID": credential_present("ZOHO_CLIENT_ID"),
            "ZOHO_CLIENT_SECRET": credential_present("ZOHO_CLIENT_SECRET"),
            "ZOHO_REFRESH_TOKEN": credential_present("ZOHO_REFRESH_TOKEN"),
        },
        "organization": {
            "name": org.get("company_name", "N/A") if org else "N/A",
            "alias": org.get("alias", "N/A") if org else "N/A",
            "org_id": org.get("id", "N/A") if org else "N/A",
            "domain": org.get("domain_name", "N/A") if org else "N/A",
            "website": org.get("website", "N/A") if org else "N/A",
            "primary_email": org.get("primary_email", "N/A") if org else "N/A",
            "phone": org.get("phone", "N/A") if org else "N/A",
            "license_type": org.get("license_details", {}).get("paid_type", "N/A") if org else "N/A",
            "paid_expiry": org.get("license_details", {}).get("paid_expiry", "N/A") if org else "N/A",
            "user_licenses": org.get("license_details", {}).get("users_license_purchased", 0) if org else 0,
        } if org else None
    }

    if getattr(args, 'json', False):
        print(json.dumps(status_data, indent=2, ensure_ascii=False))
        return 0 if ok else 1

    print("==================== ZOHO CRM CONNECTION STATUS ====================")
    print(f"Trạng thái: {'✅ KẾT NỐI THÀNH CÔNG (LIVE REST API)' if ok else '❌ LỖI KẾT NỐI'}")
    print(f"Transport: {conn.transport().upper()} | Probe: {probe_msg}")
    if org:
        print(f"Doanh nghiệp: {org.get('company_name')} ({org.get('alias')})")
        print(f"Website: {org.get('website')} | Domain: {org.get('domain_name')}")
        print(f"Email quản trị: {org.get('primary_email')} | Hotline: {org.get('phone')}")
        lic = org.get('license_details', {})
        print(f"Gói dịch vụ: {lic.get('paid_type', 'N/A').title()} ({lic.get('users_license_purchased')} users) - Hạn: {lic.get('paid_expiry')}")
        print(f"Org ID: {org.get('id')}")
    else:
        print("Không thể lấy thông tin chi tiết tổ chức.")
    print("====================================================================")
    return 0 if ok else 1

def cmd_count(args):
    conn = get_live_conn()
    modules = [("leads", "Leads"), ("contacts", "Contacts"), ("accounts", "Accounts"), ("deals", "Deals"), ("tasks", "Tasks")]
    counts = {}
    
    try:
        token, domain = conn._access_context()
        for key, mod_api in modules:
            try:
                resp = conn.request(
                    "GET",
                    f"{domain.rstrip('/')}/crm/v8/{mod_api}/actions/count",
                    headers={"Authorization": f"Zoho-oauthtoken {token}"},
                    timeout=15.0
                )
                if resp.is_success:
                    counts[key] = resp.json().get("count", 0)
                else:
                    counts[key] = "N/A"
            except Exception as e:
                counts[key] = f"Error: {e}"
    except Exception as e:
        print(f"Lỗi lấy access context: {e}", file=sys.stderr)
        return 1

    if getattr(args, 'json', False):
        print(json.dumps(counts, indent=2, ensure_ascii=False))
        return 0

    print("==================== ZOHO CRM RECORD COUNTS ====================")
    for m, c in counts.items():
        if isinstance(c, (int, float)):
            print(f"• {m.capitalize():<12}: {c:,} bản ghi")
        else:
            print(f"• {m.capitalize():<12}: {c} bản ghi")
    print("----------------------------------------------------------------")
    print(f"Trạng thái: 🟢 Đã kết nối dữ liệu trực tiếp từ Minh Vân Logistics CRM.")
    print("================================================================")
    return 0

def cmd_list(args):
    conn = get_live_conn()
    module = args.module.lower()
    limit = args.limit or 25
    
    try:
        records = conn.read(module, limit=limit)
    except Exception as e:
        print(f"Lỗi khi đọc module {module}: {e}", file=sys.stderr)
        return 1

    if getattr(args, 'json', False):
        print(json.dumps(records, indent=2, ensure_ascii=False))
        return 0

    print(f"==================== ZOHO CRM - MODULE: {module.upper()} ====================")
    print(f"Tổng số bản ghi tìm thấy: {len(records)}")
    if not records:
        print(f"Không có bản ghi nào trong module '{module}'. Database CRM hiện đang trống.")
    else:
        for idx, r in enumerate(records, 1):
            print(f"[{idx}] {r}")
    print("======================================================================")
    return 0

def cmd_search(args):
    conn = get_live_conn()
    module = args.module.lower()
    query = args.query.lower()
    
    try:
        records = conn.read(module, limit=100)
    except Exception as e:
        print(f"Lỗi truy vấn: {e}", file=sys.stderr)
        return 1

    matched = []
    for r in records:
        text = str(r).lower()
        if query in text:
            matched.append(r)

    if getattr(args, 'json', False):
        try:
            serialized = [r.__dict__ if hasattr(r, '__dict__') else str(r) for r in matched]
            print(json.dumps(serialized, indent=2, ensure_ascii=False, default=str))
        except Exception:
            print(json.dumps([str(r) for r in matched], indent=2, ensure_ascii=False))
        return 0

    print(f"Kết quả tìm kiếm '{query}' trong {module}: {len(matched)} bản ghi")
    for idx, r in enumerate(matched, 1):
        print(f"[{idx}] {r}")
    return 0

def main():
    parser = argparse.ArgumentParser(description="Zoho CRM Control CLI for Minh Van Logistics")
    subparsers = parser.add_subparsers(dest="command")

    p_status = subparsers.add_parser("status", help="Kiểm tra trạng thái kết nối Zoho CRM và tổ chức")
    p_status.add_argument("--json", action="store_true", help="Xuất định dạng JSON")

    p_info = subparsers.add_parser("info", help="Alias cho status")
    p_info.add_argument("--json", action="store_true", help="Xuất định dạng JSON")

    p_org = subparsers.add_parser("org", help="Xem thông tin chi tiết tổ chức Minh Vân Logistics")
    p_org.add_argument("--json", action="store_true", help="Xuất định dạng JSON")

    p_count = subparsers.add_parser("count", help="Đếm số lượng bản ghi trong các module CRM")
    p_count.add_argument("--json", action="store_true", help="Xuất định dạng JSON")

    p_list = subparsers.add_parser("list", help="Liệt kê bản ghi trong một module (leads, contacts, accounts, deals, tasks)")
    p_list.add_argument("--module", required=True, choices=["leads", "contacts", "accounts", "deals", "tasks"], help="Tên module")
    p_list.add_argument("--limit", type=int, default=25, help="Số lượng bản ghi tối đa")
    p_list.add_argument("--json", action="store_true", help="Xuất định dạng JSON")

    p_search = subparsers.add_parser("search", help="Tìm kiếm bản ghi trong module")
    p_search.add_argument("--module", required=True, choices=["leads", "contacts", "accounts", "deals", "tasks"], help="Tên module")
    p_search.add_argument("--query", required=True, help="Từ khóa tìm kiếm")
    p_search.add_argument("--json", action="store_true", help="Xuất định dạng JSON")

    args = parser.parse_args()
    if not args.command or args.command in ["status", "info", "org"]:
        return cmd_status(args)
    elif args.command == "count":
        return cmd_count(args)
    elif args.command == "list":
        return cmd_list(args)
    elif args.command == "search":
        return cmd_search(args)
    else:
        parser.print_help()
        return 0

if __name__ == "__main__":
    sys.exit(main())
