"""
Tests for P2: Workflow Engine & Safe Zoho CRM Staging Bridge.
Verifies end-to-end pipeline: Discovery → Verification → Dedupe → Scoring → Safe CRM Preview → Human Approval Gate → Staged.
"""
import pytest
from marketing_system.constants import Environment, Impact
from marketing_system.tools.hub import ToolContext
from marketing_system.workflows.definitions import GTM_LEAD_PIPELINE, DEFINITIONS

OWNER = "buzz:user:owner"


def test_crm_preview_import_tool(tmp_path, monkeypatch):
    from marketing_system.config import Settings
    from marketing_system.tools.catalog import build_hub

    monkeypatch.setenv("CRM_WRITE_ENABLED", "false")
    settings = Settings(environment=Environment.MOCK, data_dir=tmp_path, log_dir=tmp_path)
    hub = build_hub(settings=settings)

    ctx = ToolContext(correlation_id="test-p2-crm", specialist_id="06_sales_copilot")

    candidate_leads = [
        {
            "company": "Công ty TNHH Thiết bị Y tế Chuyên Dụng Tâm An",
            "vat_number": "0107889123",
            "domain": "tamanmedical.com.vn",
            "contact_name": "Nguyễn Văn Hùng",
            "title": "Trưởng phòng XNK",
            "email": "hung.nv@tamanmedical.com.vn",
            "phone": "0912345671",
            "industry_code": "3250",
            "data_quality_score": 90,
            "commercial_fit_score": 85,
            "score": 87,
            "score_reason": "Chuẩn ICP Thiết bị Y tế",
        },
        {
            "company": "Minh Van ITL Logistics",  # Should trigger dedupe exclusion
            "vat_number": "0101416719",
            "domain": "minhvanlogistics.com",
            "contact_name": "Nguyen Van B",
        }
    ]

    result = hub.invoke("crm.preview_import", {"leads": candidate_leads}, ctx)
    assert result.succeeded is True
    data = result.data
    assert data["total_input"] == 2
    assert data["write_enabled"] is False
    assert data["mode"] == "SAFE_PREVIEW_ONLY"
    assert len(data["staged_records"]) >= 1

    staged = data["staged_records"][0]
    assert staged["zoho_module"] == "Leads"
    assert staged["payload"]["Company"] == "Công ty TNHH Thiết bị Y tế Chuyên Dụng Tâm An"
    assert staged["payload"]["VAT_Number"] == "0107889123"
    assert staged["payload"]["Lead_Source"] == "GTM_AI_Discovery"


def test_gtm_lead_pipeline_workflow_end_to_end(tmp_path, monkeypatch):
    from marketing_system.config import Settings
    from marketing_system.workflows.store import WorkflowStore
    from marketing_system.workflows.approvals import ApprovalEngine
    from marketing_system.policy import PolicyEngine
    from marketing_system.workflows.engine import WorkflowEngine
    from marketing_system.tools.catalog import build_hub
    from marketing_system.runtime.mock import MockRuntime

    settings = Settings(environment=Environment.MOCK, data_dir=tmp_path, log_dir=tmp_path)
    settings.ensure_runtime_dirs()
    store = WorkflowStore(settings.data_dir / "marketing.db")
    approvals = ApprovalEngine(store)
    policy = PolicyEngine()
    hub = build_hub(settings=settings, store=store, approvals=approvals, policy=policy)
    runtime = MockRuntime()
    engine = WorkflowEngine(settings, store, hub, approvals, runtime, DEFINITIONS)

    # 1. Start GTM Lead Pipeline workflow
    start_res = engine.start(
        "gtm_lead_pipeline",
        "Tìm kiếm và thẩm định lead thiết bị y tế hàng không",
        params={"limit": 3},
        user_id=OWNER,
        channel_id="buzz:channel:gtm-leads",
    )

    # 2. Workflow must advance to approval gate and pause safely
    assert start_res["state"] == "WAITING_APPROVAL"
    assert "approval" in start_res
    code = start_res["approval"]["code"]
    assert code.startswith("MV-")

    # 3. Simulate owner approval decision
    approvals.decide_locally(start_res["approval"]["approval_id"], True, OWNER)

    # 4. Resume workflow
    resumed = engine.resume(start_res["workflow_id"])
    assert resumed["state"] == "DONE"

    result = resumed["result"]
    assert result["status"] == "COMPLETED"
    assert result["total_discovered"] >= 1
    assert result["final_staging"]["stage_status"] == "APPROVED_FOR_CRM"
    assert result["final_staging"]["crm_write_executed"] is False
