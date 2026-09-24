from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .config import PROJECT_ROOT, Settings
from .constants import TestState
from .credentials import available as credential_store_available
from .credentials import credential_present, write_credential
from .oauth import authorize_m365, authorize_zoho
from .orchestrator import MarketingOrchestrator
from .routing import route_intent


def _find_hermes() -> str | None:
    explicit = os.getenv("HERMES_BIN")
    if explicit and Path(explicit).exists():
        return explicit
    found = shutil.which("hermes")
    if found:
        return found
    candidate = Path.home() / "AppData" / "Local" / "hermes" / "bin" / "hermes.exe"
    return str(candidate) if candidate.exists() else None


def _find_buzz() -> str | None:
    explicit = os.getenv("BUZZ_CLI_PATH")
    if explicit and Path(explicit).exists():
        return explicit
    found = shutil.which("buzz")
    if found:
        return found
    candidate = Path("D:/Buzz/buzz.exe")
    return str(candidate) if candidate.exists() else None


def command_status(args: argparse.Namespace) -> int:
    orchestrator = MarketingOrchestrator()
    payload = orchestrator.status()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(f"Mode: {payload['environment']} | SAFE_DRY_RUN: {payload['safe_dry_run']}")
    for item in payload["connectors"]:
        print(f"{item['connector']}: {item['current_state']} (live: {item['live_state']})")
    return 0


def _run_redacted(command: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        completed = subprocess.run(command, capture_output=True, text=False, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, type(exc).__name__
    stdout = (completed.stdout or b"").decode("utf-8", errors="replace")
    stderr = (completed.stderr or b"").decode("utf-8", errors="replace")
    output = (stdout + "\n" + stderr).strip()
    return completed.returncode, output


def command_doctor(args: argparse.Namespace) -> int:
    from .ops import doctor

    return doctor(live=args.live)


def command_workflows(args: argparse.Namespace) -> int:
    from .ops import workflows

    return workflows(args.action, args.workflow_id)


def command_approvals(args: argparse.Namespace) -> int:
    from .ops import approvals

    return approvals(args.action, args.code)


def command_route(args: argparse.Namespace) -> int:
    print(route_intent(args.text).model_dump_json(indent=2))
    return 0


def command_connector(args: argparse.Namespace) -> int:
    orchestrator = MarketingOrchestrator()
    report = orchestrator.registry.get(args.name).report(live_probe=args.live)
    print(report.model_dump_json(indent=2))
    if args.live:
        return 0 if report.live_state == "CONNECTED" else 2
    return 0


def command_handle(args: argparse.Namespace) -> int:
    result = MarketingOrchestrator().handle(args.text, source_channel="cli")
    if args.json:
        print(result.model_dump_json(indent=2))
    else:
        print(result.response)
    return 0


def command_acceptance(_: argparse.Namespace) -> int:
    orchestrator = MarketingOrchestrator()
    cases = {
        "B_status": "Kiểm tra trạng thái toàn bộ hệ thống.",
        "C_routing": "Tìm cho tôi 3 khách hàng tiềm năng ngành logistics và cho biết agent nào xử lý.",
        "D_content": "Viết một bài LinkedIn giới thiệu dịch vụ forwarding.",
        "E_campaign": "Tạo chiến dịch quảng cáo Facebook 10 triệu.",
    }
    results: dict[str, str] = {}
    for name, prompt in cases.items():
        result = orchestrator.handle(prompt, source_channel="acceptance")
        results[name] = result.result_state
        print(f"[{result.result_state}] {name}: {result.intent} -> {','.join(result.agents) or 'orchestrator'}")
    print("[SKIPPED] A_Buzz_transport: this command is local-only; see TEST_REPORT.md for live relay evidence")
    print("[SKIPPED] F_restart: this command is local-only; use scripts/stop-all.ps1 + start-all.ps1")
    return 0 if all(state == TestState.PASS_MOCK for state in results.values()) else 1


def command_credentials_status(_: argparse.Namespace) -> int:
    names = sorted(
        {
            key
            for connector in MarketingOrchestrator().registry._connectors.values()
            for key in (*connector.required_env, *connector.optional_env)
        }
    )
    print(f"OS credential store: {'AVAILABLE' if credential_store_available() else 'UNAVAILABLE'}")
    for name in names:
        env_present = bool(os.getenv(name))
        vault_present = credential_present(name) if credential_store_available() else False
        location = "PROCESS_ENV" if env_present else "WINDOWS_CREDENTIAL_MANAGER" if vault_present else "MISSING"
        print(f"{name}: {location}")
    return 0


def command_credentials_set(args: argparse.Namespace) -> int:
    value = getpass.getpass(f"Enter {args.name} (hidden): ")
    if not value:
        print("Credential was not stored: empty input.", file=sys.stderr)
        return 2
    write_credential(args.name, value)
    print(f"{args.name}: stored in Windows Credential Manager (value not displayed)")
    return 0


def command_oauth(args: argparse.Namespace) -> int:
    if args.provider == "zoho-mcp":
        from .connectors.zoho_mcp import authorize as authorize_zoho_mcp

        result = authorize_zoho_mcp()
    else:
        result = authorize_m365() if args.provider == "m365" else authorize_zoho()
    print(f"{result['provider']}: {result['state']} (token value not displayed)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="marketing-system")
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=command_status)
    doctor = sub.add_parser("doctor")
    doctor.add_argument("--live", action="store_true", help="Run non-destructive live connector probes; may consume API quota.")
    doctor.set_defaults(func=command_doctor)
    route = sub.add_parser("route")
    route.add_argument("text")
    route.set_defaults(func=command_route)
    connector = sub.add_parser("connector")
    connector.add_argument("name", choices=["zoho", "m365", "apollo", "linkedin", "youtube", "meta_ads", "google_ads", "website"])
    connector.add_argument("--live", action="store_true", help="Run a non-destructive live probe; provider quota may apply.")
    connector.set_defaults(func=command_connector)
    handle = sub.add_parser("handle")
    handle.add_argument("text")
    handle.add_argument("--json", action="store_true")
    handle.set_defaults(func=command_handle)
    acceptance = sub.add_parser("acceptance")
    acceptance.set_defaults(func=command_acceptance)
    credentials = sub.add_parser("credentials")
    credential_sub = credentials.add_subparsers(dest="credentials_command", required=True)
    credentials_status = credential_sub.add_parser("status")
    credentials_status.set_defaults(func=command_credentials_status)
    credentials_set = credential_sub.add_parser("set")
    credentials_set.add_argument("name")
    credentials_set.set_defaults(func=command_credentials_set)
    workflows = sub.add_parser("workflows")
    workflows.add_argument("action", choices=["list", "status", "resume", "cancel", "recover"])
    workflows.add_argument("workflow_id", nargs="?")
    workflows.set_defaults(func=command_workflows)
    approvals = sub.add_parser("approvals")
    approvals.add_argument("action", choices=["list", "check", "approve", "reject"])
    approvals.add_argument("code", nargs="?")
    approvals.set_defaults(func=command_approvals)
    oauth = sub.add_parser("oauth")
    oauth.add_argument("provider", choices=["m365", "zoho", "zoho-mcp"])
    oauth.set_defaults(func=command_oauth)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
