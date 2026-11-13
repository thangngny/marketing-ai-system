"""
Master Mega Prompt V10 - Forensic Remediation & Adversarial Acceptance Test Suite.
Validates:
- V10-001: Zoho Search Completeness & ZohoQueryReceipt (no false FULL_COVERAGE on bounded/missing metadata).
- V10-002: Disable Production/Sandbox Mock Fallback (non-mock environments require live connector).
- V10-003: Spoof-Proof Legal Verification via TrustedLegalVerificationDecision (rejects caller-crafted evidence).
- V10-004: Approval Engine as the ONLY Authority (zero context bypass, atomic conditional consume).
- V10-005: Approval + Staging Consistency (staging failure must never report APPROVED_FOR_CRM).
- V10-006: Event Idempotency with Deterministic Business Operation Keys (prevents retry inflation).
- V10-007: Dashboard KPI Semantics (dedupe_cleared strictly excludes duplicate_confirmed).
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pytest

from marketing_system.config import Settings
from marketing_system.constants import Environment, Impact
from marketing_system.models import (
    BusinessEvent,
    DedupeDecision,
    Lead,
    TrustedLegalVerificationDecision,
    ZohoQueryReceipt,
    utc_now,
)
from marketing_system.storage import EventConflictError, StagingStore
from marketing_system.tools.catalog import (
    FindExistingIn,
    PreviewCrmImportIn,
    crm_find_existing,
    crm_preview_import,
)
from marketing_system.tools.hub import HubRuntime, ToolContext
from marketing_system.workflows.approvals import (
    APPROVED,
    CONSUMED,
    PENDING,
    ApprovalEngine,
    ApprovalRecord,
    payload_hash,
)
from marketing_system.workflows.definitions import (
    step_gtm_finalize_stage,
    step_gtm_gate,
)
from marketing_system.workflows.engine import StepContext, StepOutcome
from marketing_system.workflows.store import WorkflowStore


def _make_runtime(tmp_path: Path, env: Environment = Environment.MOCK, connector=None) -> HubRuntime:
    settings = Settings(environment=env, data_dir=tmp_path)
    ctx = ToolContext(correlation_id="v10-test-corr")
    rt = HubRuntime(settings=settings, ctx=ctx, registry=None, artifacts_dir=tmp_path / "artifacts")
    if connector is not None:
        rt._connectors["zoho"] = connector
    return rt


# ==============================================================================
# V10-001: ZOHO SEARCH COMPLETENESS & QUERY RECEIPT
# ==============================================================================

def test_v10_001_more_records_true_must_not_grant_full_coverage(tmp_path):
    """
    V10-001 T2: If Zoho API indicates more_records=True (or pagination incomplete),
    coverage_status MUST be PARTIAL_COVERAGE, not FULL_COVERAGE.
    """
    rt = _make_runtime(tmp_path, env=Environment.MOCK)
    find_in = FindExistingIn(
        companies=["Công ty TNHH Cần Kiểm Tra Toàn Diện"],
        vats=["0107889123"],
    )

    # Simulate connector returning 200 records with more_records=True
    mock_connector = mock.MagicMock()
    mock_connector.configured.return_value = True
    mock_connector.read.return_value = [{"id": f"acc-{i}", "name": f"Other {i}"} for i in range(200)]
    mock_connector.query_receipt = mock.MagicMock(return_value=ZohoQueryReceipt(
        run_id="run-1",
        organization="Minh Van Logistics",
        module="Accounts",
        api_operation="get_records",
        requested_page=1,
        returned_count=200,
        more_records=True,
        explicit_completion_status="INCOMPLETE_MORE_RECORDS",
    ))

    with mock.patch("marketing_system.tools.catalog._live_connector", return_value=mock_connector):
        res = crm_find_existing(find_in, rt)

    assert res["coverage_status"] == "PARTIAL_COVERAGE"
    assert res["bounded"] is True
    dec = res["decisions"]["Công ty TNHH Cần Kiểm Tra Toàn Diện"]
    assert dec["decision_status"] == "PARTIAL_COVERAGE"


def test_v10_001_missing_pagination_metadata_rejects_full_coverage(tmp_path):
    """
    V10-001 T1: If query receipt is missing or reports unverified completion,
    coverage_status cannot be FULL_COVERAGE.
    """
    rt = _make_runtime(tmp_path, env=Environment.MOCK)
    find_in = FindExistingIn(companies=["Công ty Thiếu Metadata"])

    mock_connector = mock.MagicMock()
    mock_connector.configured.return_value = True
    mock_connector.read.return_value = [{"id": "acc-1", "name": "Some Company"}]
    # Receipt with FAILED or missing explicit completion
    mock_connector.query_receipt = mock.MagicMock(return_value=ZohoQueryReceipt(
        run_id="run-2",
        organization="Minh Van Logistics",
        module="Accounts",
        api_operation="get_records",
        requested_page=1,
        returned_count=50,
        more_records=False,
        explicit_completion_status="PARTIAL",
        error_status="Provider metadata omitted",
    ))

    with mock.patch("marketing_system.tools.catalog._live_connector", return_value=mock_connector):
        res = crm_find_existing(find_in, rt)

    assert res["coverage_status"] == "PARTIAL_COVERAGE"


# ==============================================================================
# V10-002: DISABLE PRODUCTION / SANDBOX MOCK FALLBACK
# ==============================================================================

def test_v10_002_sandbox_without_connector_refuses_mock_fallback(tmp_path):
    """
    V10-002: In SANDBOX environment without a configured connector,
    the system must NOT silently fall back to mock accounts.
    Must return NOT_CONFIGURED / CHECK_FAILED, and coverage PARTIAL_COVERAGE.
    """
    rt = _make_runtime(tmp_path, env=Environment.SANDBOX)
    find_in = FindExistingIn(companies=["Công ty Môi Trường Thật"])

    # Force connector to None or unconfigured in sandbox
    with mock.patch("marketing_system.tools.catalog._live_connector", return_value=None):
        res = crm_find_existing(find_in, rt)

    assert res["coverage_status"] == "PARTIAL_COVERAGE"
    assert "mock_accounts" not in res.get("scope_checked", [])
    assert res["match_status"] in ("CHECK_FAILED", "SOURCE_UNAVAILABLE", "NOT_CONFIGURED")
    dec = res["decisions"]["Công ty Môi Trường Thật"]
    assert dec["decision_status"] in ("CHECK_FAILED", "NOT_CONFIGURED", "PARTIAL_COVERAGE")


# ==============================================================================
# V10-003: SPOOF-PROOF LEGAL ENTITY VERIFICATION
# ==============================================================================

def test_v10_003_caller_evidence_dict_alone_is_rejected_without_trusted_decision(tmp_path):
    """
    V10-003 T2 & T3: A caller sending a crafted evidence dictionary
    claiming SOURCE_CORROBORATED or national_tax_registry_vietnam
    MUST BE REJECTED if no TrustedLegalVerificationDecision exists in trusted store.
    """
    rt = _make_runtime(tmp_path, env=Environment.MOCK)
    lead_crafted = {
        "company": "Công ty Tự Nhận Có Bằng Chứng",
        "vat_number": "0107889123",
        "domain": "tunhan.vn",
        "contact_name": "Trần Văn Spoof",
        "email": "spoof@tunhan.vn",
        "data_quality_score": 85,
        "commercial_fit_score": 85,
        "evidence": [
            {
                "field_name": "vat_number",
                "evidence_status": "SOURCE_CORROBORATED",
                "source_provider": "national_tax_registry_vietnam",
            }
        ],
    }

    # Simulate clean dedupe
    with mock.patch("marketing_system.tools.catalog.crm_find_existing") as mock_find:
        mock_find.return_value = {
            "matches": {},
            "decisions": {
                "Công ty Tự Nhận Có Bằng Chứng": {
                    "decision_status": "NOT_FOUND_IN_CHECKED_SCOPE",
                    "candidate_key": "Công ty Tự Nhận Có Bằng Chứng",
                }
            },
            "coverage_status": "FULL_COVERAGE",
            "bounded": False,
            "match_status": "NOT_FOUND_VERIFIED",
            "modules_checked": ["Accounts", "Leads"],
        }
        res = crm_preview_import(PreviewCrmImportIn(leads=[lead_crafted]), rt)

    staged = res["staged_records"][0]
    # Without a TrustedLegalVerificationDecision in trusted store, must be rejected
    assert staged["eligible_for_crm_import"] is False
    assert staged["action"] == "NEEDS_VERIFICATION"
    assert staged["eligibility_status"] == "NEEDS_IDENTITY_VERIFICATION"


def test_v10_003_trusted_legal_decision_in_store_qualifies_lead(tmp_path):
    """
    V10-003 T8: When an authoritative TrustedLegalVerificationDecision
    exists in trusted store matching the entity and VAT, legal verification succeeds.
    """
    db_path = tmp_path / "marketing.db"
    store = StagingStore(db_path)
    store.initialize()

    legal_dec = TrustedLegalVerificationDecision(
        entity_id="Công ty Xác Thực Chuẩn",
        vat_number="0107889123",
        legal_name="Công ty Xác Thực Chuẩn",
        registry_source="national_tax_registry_vietnam",
        request_ref="req-tax-99",
        source_data_hash="sha256-abc12345",
        decision_status="VERIFIED",
    )
    store.save_legal_decision(legal_dec)

    settings = Settings(environment=Environment.MOCK, data_dir=tmp_path)
    ctx = ToolContext(correlation_id="v10-legal-auth")
    rt = HubRuntime(settings=settings, ctx=ctx, registry=None, artifacts_dir=tmp_path / "artifacts")

    lead_valid = {
        "company": "Công ty Xác Thực Chuẩn",
        "vat_number": "0107889123",
        "domain": "xacthuc.vn",
        "contact_name": "Nguyễn Văn Thật",
        "email": "that@xacthuc.vn",
        "data_quality_score": 85,
        "commercial_fit_score": 85,
    }

    with mock.patch("marketing_system.tools.catalog.crm_find_existing") as mock_find:
        mock_find.return_value = {
            "matches": {},
            "decisions": {
                "Công ty Xác Thực Chuẩn": {
                    "decision_status": "NOT_FOUND_IN_CHECKED_SCOPE",
                    "candidate_key": "Công ty Xác Thực Chuẩn",
                }
            },
            "coverage_status": "FULL_COVERAGE",
            "bounded": False,
            "match_status": "NOT_FOUND_VERIFIED",
            "modules_checked": ["Accounts", "Leads"],
        }
        res = crm_preview_import(PreviewCrmImportIn(leads=[lead_valid]), rt)

    staged = res["staged_records"][0]
    assert staged["eligible_for_crm_import"] is True
    assert staged["action"] == "STAGED_FOR_INSERT"
    assert staged["eligibility_status"] == "APPROVED_FOR_STAGING"


# ==============================================================================
# V10-004: APPROVAL ENGINE MUST BE THE ONLY AUTHORITY (ZERO BYPASS)
# ==============================================================================

def test_v10_004_no_engine_returns_approval_service_unavailable():
    """
    V10-004: If engine is None, finalize_stage must return
    APPROVAL_SERVICE_UNAVAILABLE and approved_count=0.
    Context approval_record injection must be ignored.
    """
    eligible_lead = {
        "company": "Công ty Thử Nghiệm Bypass",
        "eligible_for_crm_import": True,
        "payload_hash": "hash-valid",
    }
    ctx = StepContext(
        engine=None,  # No engine
        workflow={"workflow_id": "wf-bypass-v10", "correlation_id": "corr-bypass", "params": {}},
        outputs={
            "crm_preview": {"staged_records": [eligible_lead]},
            "approval_gate": {"approval_id": "fake-appr-id"},
        },
        specialist="06_sales_copilot",
    )
    # Attempting to inject approval_record directly into context
    ctx.approval_record = mock.MagicMock(
        authorizes=lambda a, d: True,
        status="APPROVED",
        payload_hash="hash-valid",
        consumed_at=None,
    )

    outcome = step_gtm_finalize_stage(ctx)
    assert outcome.output["approved_count"] == 0
    assert outcome.output["stage_status"] == "APPROVAL_SERVICE_UNAVAILABLE"


def test_v10_004_atomic_consume_prevents_concurrent_reuse(tmp_path):
    """
    V10-004: ApprovalEngine.consume() must be an atomic conditional update.
    Second call returns False and cannot re-authorize.
    """
    wf_store = WorkflowStore(tmp_path / "workflows.db")
    engine = ApprovalEngine(wf_store)

    rec = engine.request(
        tool="workflow.stage_leads_for_crm",
        target_system="zoho",
        impact=Impact.WRITE_LOW_RISK,
        payload=[{"company": "Single Use Test"}],
        summary="Test single use",
        requested_by="agent",
        workflow_id="wf-single-1",
        user_id="user-1",
        channel_id=None,
    )
    engine.decide_locally(rec.approval_id, approve=True, operator="owner")

    # First consume succeeds
    assert engine.consume(rec.approval_id) is True

    # Second consume MUST return False
    assert engine.consume(rec.approval_id) is False


# ==============================================================================
# V10-005: APPROVAL + STAGING CONSISTENCY (NO EXCEPT PASS)
# ==============================================================================

def test_v10_005_staging_store_failure_must_not_report_success(tmp_path):
    """
    V10-005: If StagingStore fails during event persistence,
    step_gtm_finalize_stage MUST NOT report APPROVED_FOR_CRM or approved_count > 0.
    It must return STAGING_FAILED_RECOVERABLE.
    """
    wf_store = WorkflowStore(tmp_path / "workflows.db")
    engine = ApprovalEngine(wf_store)
    settings = Settings(environment=Environment.MOCK, data_dir=tmp_path)
    engine.settings = settings

    eligible_lead = {
        "company": "Công ty Thất Bại Ghi Staging",
        "eligible_for_crm_import": True,
        "payload_hash": "hash-v10",
    }
    digest = payload_hash("workflow.stage_leads_for_crm", [eligible_lead])

    rec = engine.request(
        tool="workflow.stage_leads_for_crm",
        target_system="zoho",
        impact=Impact.WRITE_LOW_RISK,
        payload=[eligible_lead],
        summary="Staging test",
        requested_by="agent",
        workflow_id="wf-stage-fail",
        user_id="user-1",
        channel_id=None,
    )
    engine.decide_locally(rec.approval_id, approve=True, operator="owner")

    ctx = StepContext(
        engine=engine,
        workflow={"workflow_id": "wf-stage-fail", "correlation_id": "corr-fail", "params": {}},
        outputs={
            "crm_preview": {"staged_records": [eligible_lead]},
            "approval_gate": {"approval_id": rec.approval_id},
        },
        specialist="06_sales_copilot",
    )

    # Force StagingStore to fail
    with mock.patch("marketing_system.storage.StagingStore.persist_lead_with_events", side_effect=sqlite3.OperationalError("database is locked")):
        outcome = step_gtm_finalize_stage(ctx)

    assert outcome.output["approved_count"] == 0
    assert outcome.output["stage_status"] == "STAGING_FAILED_RECOVERABLE"
    assert "error_detail" in outcome.output


# ==============================================================================
# V10-006: EVENT IDEMPOTENCY WITH DETERMINISTIC OPERATION KEY
# ==============================================================================

def test_v10_006_deterministic_event_id_prevents_retry_inflation(tmp_path):
    """
    V10-006: Retrying a pipeline operation with identical business operation key
    must produce the SAME event_id, succeeding idempotently without duplicating events.
    """
    db_path = tmp_path / "marketing.db"
    store = StagingStore(db_path)
    store.initialize()

    from marketing_system.identity import generate_event_id

    ev_id = generate_event_id(
        workflow_id="wf-idem-1",
        entity_id="comp-123",
        event_type="lead.crm_dedupe_completed",
        attempt_key="attempt-1",
        policy_version="v10.0",
    )

    ev1 = BusinessEvent(
        event_id=ev_id,
        event_type="lead.crm_dedupe_completed",
        entity_id="comp-123",
        workflow_id="wf-idem-1",
        environment=Environment.MOCK,
        synthetic=True,
        payload_json={"outcome": "CLEARED", "dedupe_status": "NOT_FOUND_VERIFIED", "cleared": 1},
    )

    store.record_event(ev1)
    # Retry identical event
    store.record_event(ev1)

    events = store.list_events(entity_id="comp-123")
    assert len(events) == 1  # Not duplicated!


# ==============================================================================
# V10-007: DASHBOARD KPI SEMANTICS (CLEARED VS DUPLICATE)
# ==============================================================================

def test_v10_007_dashboard_dedupe_cleared_strictly_excludes_duplicates(tmp_path):
    """
    V10-007: Dashboard metric for dedupe cleared MUST NOT count DUPLICATE_CONFIRMED.
    """
    from marketing_system.identity import generate_event_id
    import importlib.util

    dash_candidates = [
        Path(os.environ.get("BUZZ_BUZZ_AI_USAGE_CENTER_DIR", "")) / "bin" / "dashboard.py",
        Path(__file__).resolve().parent.parent / "buzz-ai-usage-center" / "bin" / "dashboard.py",
        Path(__file__).resolve().parent.parent.parent / "buzz-ai-usage-center" / "bin" / "dashboard.py",
        Path.home() / "buzz-ai-usage-center" / "bin" / "dashboard.py",
    ]
    dash_path = None
    for c in dash_candidates:
        if c.exists():
            dash_path = c
            break
    assert dash_path and dash_path.exists(), f"dashboard.py not found in {dash_candidates}"

    spec = importlib.util.spec_from_file_location("dash_v10", str(dash_path))
    dash_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dash_mod)
    get_gtm_funnel_data = dash_mod.get_gtm_funnel_data

    db_path = tmp_path / "marketing.db"
    store = StagingStore(db_path)
    store.initialize()

    # Lead 1: Duplicate confirmed
    ev_dup = BusinessEvent(
        event_id=generate_event_id("wf-1", "lead-dup", "lead.crm_dedupe_completed"),
        event_type="lead.crm_dedupe_completed",
        entity_id="lead-dup",
        workflow_id="wf-1",
        environment=Environment.PRODUCTION,
        synthetic=False,
        payload_json={"outcome": "DUPLICATE_CONFIRMED", "dedupe_status": "DUPLICATE_CONFIRMED", "cleared": 0},
    )

    # Lead 2: Cleared
    ev_cleared = BusinessEvent(
        event_id=generate_event_id("wf-1", "lead-clean", "lead.crm_dedupe_completed"),
        event_type="lead.crm_dedupe_completed",
        entity_id="lead-clean",
        workflow_id="wf-1",
        environment=Environment.PRODUCTION,
        synthetic=False,
        payload_json={"outcome": "CLEARED", "dedupe_status": "NOT_FOUND_VERIFIED", "cleared": 1},
    )

    store.record_event(ev_dup)
    store.record_event(ev_cleared)

    with mock.patch.dict(os.environ, {"BUZZ_MARKETING_DB": str(db_path)}):
        data = get_gtm_funnel_data(mode="real")

    assert data["funnel"]["deduped"] == 1, "Only the 1 cleared lead must count in deduped"
    assert data["kpis"].get("duplicates_prevented") == 1 or data["funnel"].get("duplicate_confirmed") == 1
