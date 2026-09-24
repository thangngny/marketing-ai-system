"""Operator commands: doctor, workflows, approvals. Human-facing; not exposed over MCP."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .app import build_platform
from .capabilities import connector_status
from .config import Settings
from .constants import Environment
from .credentials import available as credential_store_available
from .credentials import credential_present
from .runtime import RUNTIMES, get_runtime
from .specialists import SPECIALISTS

_OK, _WARN, _FAIL = "OK", "WARN", "FAIL"


def doctor(live: bool = False) -> int:
    settings = Settings.from_env()
    platform = build_platform(settings, runtime=get_runtime("mock"))  # doctor never calls a model
    rows: list[tuple[str, str, str]] = []

    buzz_cli = Path(os.getenv("BUZZ_CLI_PATH", r"D:\Buzz\buzz.exe"))
    rows.append(("Buzz CLI", _OK if buzz_cli.exists() else _FAIL, str(buzz_cli)))
    rows.append(("Conversation Gateway", _OK, "normalize + dedupe (gateway_events table)"))

    active = os.getenv("MARKETING_RUNTIME") or ("mock" if settings.environment is Environment.MOCK else "hermes")
    for name in RUNTIMES:
        if name == "mock":
            continue
        health = RUNTIMES[name]().health()
        caps = RUNTIMES[name]().capabilities()
        state = _OK if health.state == "READY" else (_FAIL if name == active else _WARN)
        detail = f"{health.state} model={health.model or '-'} provider={health.provider or '-'}"
        if health.buzz_transport and health.buzz_transport != "NOT_APPLICABLE":
            detail += f" buzz={health.buzz_transport}"
            if name == active and health.buzz_transport != "CONNECTED":
                state = _FAIL
        detail += " [production]" if caps.production_enabled else " [adapter only]"
        rows.append((f"Runtime {name}{' (ACTIVE)' if name == active else ''}", state, detail))

    missing = [s.id for s in SPECIALISTS.values() if not s.instructions()]
    rows.append(("Specialists (8 logical)", _OK if not missing else _FAIL, "all have skill instructions" if not missing else f"missing: {missing}"))

    wfs = platform.store.list_workflows(limit=1000)
    counts: dict[str, int] = {}
    for wf in wfs:
        counts[wf["state"]] = counts.get(wf["state"], 0) + 1
    rows.append(("Workflow engine", _OK, f"sqlite {settings.data_dir / 'marketing.db'} · {counts or 'no workflows'}"))
    rows.append(("Policy engine", _OK, "deterministic; HIGH_IMPACT phase-gated"))
    verifiers = [(v.name, v.available()) for v in platform.approvals.verifiers]
    buzz_ok = any(ok for _, ok in verifiers)
    rows.append(("Approval engine", _OK if buzz_ok else _WARN,
                 ", ".join(f"{n}={'ready' if ok else 'NEEDS_AUTH'}" for n, ok in verifiers) + " · local_console=ready"))
    pending = platform.store.list_approvals("PENDING")
    rows.append(("Approval queue", _OK, f"{len(pending)} pending"))
    specs = platform.hub.specs()
    namespaces = sorted({s.namespace for s in specs})
    rows.append(("MCP Tool Hub", _OK, f"{len(specs)} tools · {', '.join(namespaces)}"))
    rows.append(("Credential store", _OK if credential_store_available() else _FAIL, "Windows Credential Manager (BuzzMarketing/*)"))
    startup = Path(os.getenv("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "Hermes_Gateway_marketing.vbs"
    rows.append(("Autostart", _OK if startup.exists() else _WARN, str(startup.name) if startup.exists() else "not installed"))

    print(f"Environment: {settings.environment.value} · SAFE_DRY_RUN: {settings.safe_dry_run} · active runtime: {active}\n")
    width = max(len(r[0]) for r in rows)
    for component, state, detail in rows:
        print(f"{component:<{width}}  {state:<4}  {detail}")
    print("\nConnector            AUTH              READ              ANALYTICS         DRAFT             PUBLISH")
    for connector in platform.hub.registry._connectors.values():
        status = connector_status(connector, settings, platform.store, live_probe=live)
        caps = status.capabilities
        print(f"{status.connector:<20} " + " ".join(f"{caps[d]:<17}" for d in ("AUTH", "READ", "ANALYTICS", "DRAFT", "PUBLISH")))
    return 1 if any(state == _FAIL for _, state, _ in rows) else 0


def workflows(action: str, workflow_id: str | None) -> int:
    platform = build_platform()
    if action == "list":
        for wf in platform.store.list_workflows(limit=50):
            print(f"{wf['workflow_id']}  {wf['state']:<17} {wf['workflow_type']:<18} {wf['environment']:<10} {wf['updated_at'][:19]}  {wf['error'] or ''}")
        return 0
    if action == "recover":
        print("recovered:", platform.engine.recover())
        return 0
    if not workflow_id:
        print("workflow_id required", file=sys.stderr)
        return 2
    fn = {"status": platform.engine.status, "resume": platform.engine.resume, "cancel": platform.engine.cancel}[action]
    print(json.dumps(fn(workflow_id), ensure_ascii=False, indent=2, default=str))
    return 0


def approvals(action: str, code: str | None) -> int:
    platform = build_platform()
    if action == "list":
        for a in platform.store.list_approvals():
            print(f"{a['code']}  {a['status']:<9} {a['requested_action']:<32} {a['expires_at'][:16]}  {a['payload_summary'][:80]}")
        return 0
    if not code:
        print("approval code required", file=sys.stderr)
        return 2
    if action == "check":
        record = platform.approvals.refresh(code)
        print(json.dumps(record.model_dump(exclude={"payload_hash"}) if record else {"error": "UNKNOWN"}, ensure_ascii=False, indent=2))
        return 0
    # approve / reject: local console verifier. Requires a human at an interactive terminal.
    if not sys.stdin.isatty():
        print("Refused: local approval needs an interactive terminal (stdin is not a TTY).", file=sys.stderr)
        return 3
    record = platform.approvals.get(code)
    if record is None:
        print("Unknown approval", file=sys.stderr)
        return 2
    print(f"{record.code}: {record.payload_summary}\nAction: {record.requested_action} · expires {record.expires_at}")
    typed = input(f"Type the code {record.code} to {'APPROVE' if action == 'approve' else 'REJECT'}: ").strip()
    if typed != record.code:
        print("Code mismatch; nothing changed.", file=sys.stderr)
        return 4
    decided = platform.approvals.decide_locally(record.approval_id, action == "approve", operator=os.getenv("USERNAME", "local"))
    print(f"{decided.code} → {decided.status}")
    if decided.workflow_id:
        print(json.dumps(platform.engine.resume(decided.workflow_id)["state"]))
    return 0


def reader_key_present() -> bool:
    try:
        return credential_present("BUZZ_APPROVAL_READER_KEY")
    except Exception:
        return False
