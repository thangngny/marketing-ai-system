from datetime import datetime, timezone

import pytest

from marketing_system.app import build_platform
from marketing_system.config import Settings
from marketing_system.constants import Environment
from marketing_system.runtime import MockRuntime
from marketing_system.tools.hub import ToolContext
from marketing_system.workflows.approvals import BuzzSignedEventVerifier
from marketing_system.workflows.engine import TRANSITIONS

OWNER = "057f0407663083746eee6457303cead9fe3eec3bbd39a17214d84c52a9080f2f"
REQUEST = ("Tìm 10 doanh nghiệp xuất nhập khẩu phù hợp, loại các doanh nghiệp đã có trong CRM, xếp hạng lead, "
           "chuẩn bị email cho 3 lead tốt nhất, lưu thành Outlook draft, và tạo đề xuất task cho Sales. Không gửi email.")


@pytest.fixture
def env(tmp_path):
    events: list[dict] = []
    settings = Settings(environment=Environment.MOCK, data_dir=tmp_path, log_dir=tmp_path)

    def make(runtime=None):
        return build_platform(settings, runtime or MockRuntime(),
                              [BuzzSignedEventVerifier(OWNER, reader=lambda c, s: events)])

    def owner_says(text):
        events.append({"id": f"ev{len(events)}", "pubkey": OWNER, "content": text,
                       "created_at": int(datetime.now(timezone.utc).timestamp()) + 5})

    return make, owner_says


def start(platform):
    return platform.engine.start("prospect_to_draft", REQUEST, params={"count": 10, "top_n": 3},
                                 user_id=OWNER, channel_id="chan-1")


def test_north_star_mock_flow_waits_for_approval_then_completes(env):
    make, owner_says = env
    platform = make()
    status = start(platform)
    assert status["state"] == "WAITING_APPROVAL"
    assert [s["name"] for s in status["steps"]] == ["search", "dedupe", "score", "draft_emails", "approve_drafts"]
    code = status["approval"]["code"]
    assert "không gửi" in status["approval"]["payload_summary"].lower()

    assert platform.engine.resume(status["workflow_id"])["state"] == "WAITING_APPROVAL"  # no owner message yet
    owner_says(f"DUYET {code}")
    done = platform.engine.resume(status["workflow_id"])
    assert done["state"] == "DONE"
    result = done["result"]
    assert "Công ty Vận tải Mẫu Sao Việt" in result["excluded_in_crm"]
    assert len(result["top"]) == 3 and result["top"][0]["score"] >= result["top"][-1]["score"]
    assert len(result["drafts"]) == 3 and all(d["state"] == "MOCK" for d in result["drafts"])
    assert len(result["task_proposals"]) == 3
    assert result["emails_sent"] == 0 and result["crm_writes"] == 0
    transitions = platform.store.transitions(status["workflow_id"])
    assert all(b in TRANSITIONS[a] for a, b in transitions if a)
    tools = [c["tool"] for c in platform.store.tool_calls(workflow_id=status["workflow_id"])]
    assert "email.send" not in tools and "crm.create_task" not in tools


def test_workflow_state_survives_restart(env):
    make, owner_says = env
    first = make()
    status = start(first)
    del first  # "process exits"
    owner_says(f"DUYET {status['approval']['code']}")
    second = make()  # new process, same database
    touched = second.engine.recover()
    assert status["workflow_id"] in touched
    assert second.engine.status(status["workflow_id"])["state"] == "DONE"


def test_crash_mid_step_is_recovered_without_duplicates(env):
    make, owner_says = env
    platform = make()
    status = start(platform)
    owner_says(f"DUYET {status['approval']['code']}")
    platform.engine.resume(status["workflow_id"])
    wf_id = status["workflow_id"]
    # Simulate a crash after create_drafts had already executed: rewind to that step while RUNNING.
    platform.store._conn  # noqa: B018 (documenting that we poke the store directly)
    with platform.store._conn() as conn:
        conn.execute("UPDATE workflows SET state='RUNNING', current_step=5 WHERE workflow_id=?", (wf_id,))
    make().engine.recover()
    calls = [c for c in platform.store.tool_calls(workflow_id=wf_id) if c["tool"] == "email.create_draft"]
    assert [c["state"] for c in calls].count("MOCK") == 3
    assert [c["state"] for c in calls].count("DUPLICATE") == 3


def test_owner_rejection_cancels(env):
    make, owner_says = env
    platform = make()
    status = start(platform)
    owner_says(f"TUCHOI {status['approval']['code']}")
    assert platform.engine.resume(status["workflow_id"])["state"] == "CANCELLED"


def test_runtime_failure_blocks_instead_of_fabricating(env):
    make, _ = env
    platform = make(MockRuntime(fail_with="PROVIDER_DOWN"))
    status = start(platform)
    assert status["state"] == "BLOCKED"
    assert "PROVIDER_DOWN" in status["error"]


def test_production_without_credentials_blocks_with_exact_state(tmp_path, monkeypatch):
    settings = Settings(environment=Environment.PRODUCTION, data_dir=tmp_path, log_dir=tmp_path)
    platform = build_platform(settings, MockRuntime(), [])
    status = start(platform)
    assert status["state"] == "BLOCKED"
    assert "prospecting.search_companies → NOT_CONFIGURED" in status["error"]


def test_write_tool_goes_through_tool_approval_workflow(env):
    make, owner_says = env
    platform = make()
    args = {"subject": "Gọi lại khách", "related_company": "ACME", "due_in_days": 2, "reason": "test"}
    status = platform.engine.start("tool_approval", "tạo task", params={"tool": "crm.create_task", "args": args,
                                                                        "specialist": "06_sales_copilot"},
                                   user_id=OWNER, channel_id="chan-1")
    assert status["state"] == "WAITING_APPROVAL"
    owner_says(f"DUYET {status['approval']['code']}")
    done = platform.engine.resume(status["workflow_id"])
    assert done["state"] == "DONE"
    assert done["result"]["call"]["state"] == "MOCK"


def test_hub_rejects_bad_input_and_unknown_tools(env):
    make, _ = env
    hub = make().hub
    ctx = ToolContext(correlation_id="c1", specialist_id="06_sales_copilot")
    assert hub.invoke("email.create_draft", {"subject": "x"}, ctx).state == "INVALID_INPUT"
    assert hub.invoke("does.not_exist", {}, ctx).state == "ERROR"
    assert hub.invoke("email.send", {"to_email": "a@b.c", "subject": "s", "body": "b"}, ctx).state == "DENIED"


def test_hub_records_spans_and_ledger(env):
    make, _ = env
    platform = make()
    ctx = ToolContext(correlation_id="corr-span", specialist_id="08_kpi_learning")
    result = platform.hub.invoke("analytics.snapshot", {}, ctx)
    assert result.state == "MOCK"
    assert platform.store.tool_calls(correlation_id="corr-span")[0]["tool"] == "analytics.snapshot"
    log = (platform.settings.log_dir / "marketing.jsonl").read_text(encoding="utf-8")
    assert '"trace_id": "corr-span"' in log and '"name": "tool.analytics.snapshot"' in log


def test_background_mode_returns_immediately_and_finishes(env):
    import time

    make, owner_says = env
    platform = make()
    platform.engine.background = True
    first = start(platform)
    assert first["state"] in {"PLANNED", "RUNNING", "WAITING_APPROVAL"}
    for _ in range(100):
        status = platform.engine.status(first["workflow_id"])
        if status["state"] == "WAITING_APPROVAL":
            break
        time.sleep(0.05)
    assert status["state"] == "WAITING_APPROVAL"
    owner_says(f"DUYET {status['approval']['code']}")
    platform.engine.resume_async(first["workflow_id"])
    for _ in range(100):
        if platform.engine.status(first["workflow_id"])["state"] == "DONE":
            break
        time.sleep(0.05)
    assert platform.engine.status(first["workflow_id"])["state"] == "DONE"
