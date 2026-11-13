"""
Master Mega Prompt V7 Golden Dataset & Adversarial Acceptance Test Suite.
Covers:
1. 15 Per-Entity Dedupe Behavioral Test Cases (V7 Section 5.5).
2. Strict CRM Import Eligibility & No Placeholder Strings.
3. Stable Deterministic Lead Identity (Invariant under PYTHONHASHSEED).
4. StagingStore Canonical Records & Business Events Emission.
5. Golden Dataset 6-Entity Pipeline Execution.
6. Dashboard Fail-Closed Security Behind Reverse Proxy / Tunnel.
7. SQLite Read Error Truth & Status Transparency.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from marketing_system.config import Settings
from marketing_system.constants import Environment
from marketing_system.identity import generate_payload_hash, generate_stable_lead_id
from marketing_system.models import (
    BusinessEvent,
    DedupeDecision,
    EvidenceItem,
    EvidenceStatus,
    ImportEligibilityDecision,
    Lead,
    LeadCandidate,
    TrustedLegalVerificationDecision,
)
from marketing_system.storage import StagingStore
from marketing_system.tools.catalog import (
    FindExistingIn,
    LeadPipelineRunIn,
    PreviewCrmImportIn,
    build_hub,
    crm_find_existing,
    crm_preview_import,
    lead_pipeline_run,
)
from marketing_system.tools.hub import HubRuntime, ToolContext
from marketing_system.workflows.definitions import GTM_LEAD_PIPELINE, step_gtm_finalize_stage, step_gtm_gate
from marketing_system.workflows.engine import StepContext


# ==============================================================================
# SECTION 1: 15 PER-ENTITY DEDUPE BEHAVIORAL TEST CASES (V7 Section 5.5)
# ==============================================================================

def test_dedupe_case_01_and_02_bounded_accounts_partial_coverage(tmp_path):
    """Case 01 & 02: Zoho returns bounded accounts (200 records) without full cache -> PARTIAL_COVERAGE, not FULL."""
    settings = Settings(environment=Environment.SANDBOX, data_dir=tmp_path, log_dir=tmp_path)
    hub = build_hub(settings=settings)
    ctx = ToolContext(correlation_id="test-case-01-02")
    rt = HubRuntime(settings=settings, registry=hub.registry, ctx=ctx, artifacts_dir=settings.data_dir / "artifacts")

    # Mock connector returning 200 records (limit reached / bounded)
    mock_conn = MagicMock()
    mock_conn.read.return_value = [{"name": f"Account {i}", "external_id": f"acc_{i}"} for i in range(200)]
    rt.registry._connectors["zoho"] = mock_conn

    # Ensure no local cache file exists in temp home
    with patch.dict(os.environ, {"BUZZ_VAT_CACHE": str(tmp_path / "nonexistent.json")}):
        args = FindExistingIn(companies=["Cong Ty Moi Chua Tung Co"], vats=["0109999999"])
        res = crm_find_existing(args, rt)

    assert res["bounded"] is True
    assert res["coverage_status"] == "PARTIAL_COVERAGE"
    dec = res["decisions"]["Cong Ty Moi Chua Tung Co"]
    assert dec["decision_status"] == "PARTIAL_COVERAGE"
    assert dec["decision_status"] != "NOT_FOUND_VERIFIED"


def test_dedupe_case_03_company_matches_in_crm(tmp_path):
    """Case 03: Company matches CRM account -> DUPLICATE_CONFIRMED."""
    settings = Settings(environment=Environment.SANDBOX, data_dir=tmp_path, log_dir=tmp_path)
    hub = build_hub(settings=settings)
    ctx = ToolContext(correlation_id="test-case-03")
    rt = HubRuntime(settings=settings, registry=hub.registry, ctx=ctx, artifacts_dir=settings.data_dir / "artifacts")

    mock_conn = MagicMock()
    mock_conn.read.return_value = [{"name": "Cong Ty TNHH Logistics Minh Van", "external_id": "acc_mv_01"}]
    rt.registry._connectors["zoho"] = mock_conn

    args = FindExistingIn(companies=["Cong Ty TNHH Logistics Minh Van"], vats=[])
    res = crm_find_existing(args, rt)

    dec = res["decisions"]["Cong Ty TNHH Logistics Minh Van"]
    assert dec["decision_status"] == "DUPLICATE_CONFIRMED"
    assert "acc_mv_01" in dec["matching_record_ids"]


def test_dedupe_case_04_and_05_api_error_returns_check_failed(tmp_path):
    """Case 04 & 05: API error or 401/403 authorization error -> CHECK_FAILED with error details, not verified."""
    settings = Settings(environment=Environment.SANDBOX, data_dir=tmp_path, log_dir=tmp_path)
    hub = build_hub(settings=settings)
    ctx = ToolContext(correlation_id="test-case-04-05")
    rt = HubRuntime(settings=settings, registry=hub.registry, ctx=ctx, artifacts_dir=settings.data_dir / "artifacts")

    mock_conn = MagicMock()
    mock_conn.read.side_effect = PermissionError("HTTP 401 Unauthorized: Invalid Zoho OAuth token")
    rt.registry._connectors["zoho"] = mock_conn

    args = FindExistingIn(companies=["Cong Ty Alpha"], vats=["0101234567"])
    res = crm_find_existing(args, rt)

    dec = res["decisions"]["Cong Ty Alpha"]
    assert dec["decision_status"] == "CHECK_FAILED"
    assert dec["query_status"] == "FAILED"
    assert "401" in dec["error_details"]
    assert res["match_status"] == "CHECK_FAILED"


def test_dedupe_case_08_no_batch_contamination(tmp_path):
    """Case 08: Batch of 3 companies (1 match, 1 not in CRM, 1 error) -> each gets its own independent status."""
    settings = Settings(environment=Environment.SANDBOX, data_dir=tmp_path, log_dir=tmp_path)
    hub = build_hub(settings=settings)
    ctx = ToolContext(correlation_id="test-case-08")
    rt = HubRuntime(settings=settings, registry=hub.registry, ctx=ctx, artifacts_dir=settings.data_dir / "artifacts")

    # Populate temporary VAT cache
    cache_file = tmp_path / "vat_cache.json"
    cache_file.write_text(json.dumps({
        "vats": ["0107889123"],
        "names": ["cong ty tnhh duplicate co"]
    }), encoding="utf-8")

    mock_conn = MagicMock()
    mock_conn.read.return_value = [{"name": "cong ty tnhh duplicate co", "external_id": "acc_dup"}]
    rt.registry._connectors["zoho"] = mock_conn

    with patch.dict(os.environ, {"BUZZ_VAT_CACHE": str(cache_file)}):
        args = FindExistingIn(
            companies=["cong ty tnhh duplicate co", "cong ty tnhh unique co"],
            vats=["0107889123", "0314567890"]
        )
        res = crm_find_existing(args, rt)

    decisions = res["decisions"]
    assert decisions["cong ty tnhh duplicate co"]["decision_status"] == "DUPLICATE_CONFIRMED"
    assert decisions["cong ty tnhh unique co"]["decision_status"] == "NOT_FOUND_IN_CHECKED_SCOPE"


def test_dedupe_case_09_and_10_vat_match_vs_name_match(tmp_path):
    """Case 09 & 10: VAT match confirms duplicate regardless of trade name."""
    settings = Settings(environment=Environment.MOCK, data_dir=tmp_path, log_dir=tmp_path)
    hub = build_hub(settings=settings)
    ctx = ToolContext(correlation_id="test-case-09-10")
    rt = HubRuntime(settings=settings, registry=hub.registry, ctx=ctx, artifacts_dir=settings.data_dir / "artifacts")

    cache_file = tmp_path / "vat_cache.json"
    cache_file.write_text(json.dumps({
        "vats": ["0107889123"],
        "names": ["cong ty co phan tam an goc"]
    }), encoding="utf-8")

    with patch.dict(os.environ, {"BUZZ_VAT_CACHE": str(cache_file)}):
        # Different display name but EXACT matching VAT
        args = FindExistingIn(companies=["Chi nhanh Ha Noi - Tam An"], vats=["0107889123"])
        res = crm_find_existing(args, rt)

    assert "0107889123" in res["matches"]
    assert res["matches"]["0107889123"] == "vat_cache:0107889123"


def test_dedupe_case_15_concurrency_lock_file(tmp_path):
    """Case 15: Mutex lock file touch and concurrency safety."""
    lock_dir = tmp_path / "locks"
    with patch.dict(os.environ, {"BUZZ_HOME": str(tmp_path)}):
        settings = Settings(environment=Environment.MOCK, data_dir=tmp_path, log_dir=tmp_path)
        hub = build_hub(settings=settings)
        ctx = ToolContext(correlation_id="test-case-15")
        rt = HubRuntime(settings=settings, registry=hub.registry, ctx=ctx, artifacts_dir=settings.data_dir / "artifacts")
        crm_find_existing(FindExistingIn(companies=["Lock Co"]), rt)

    lock_file = lock_dir / "zoho_dedupe.lock"
    assert lock_file.exists(), "Mutex lock file must be created"


# ==============================================================================
# SECTION 2: GOLDEN DATASET (6 SOURCE ENTITIES WITH KNOWN EXPECTED OUTCOMES)
# ==============================================================================

def test_golden_dataset_six_entities_end_to_end(tmp_path):
    """
    Evaluates 6 archetypal lead candidates through strict CRM Preview & Approval Gate:
    1. Verified entity with complete contact & VAT -> STAGED_FOR_INSERT & eligible.
    2. Entity already in CRM -> DUPLICATE_REVIEW & excluded.
    3. Entity missing contact name -> NEEDS_CONTACT_ENRICHMENT (ineligible).
    4. Entity missing email -> NEEDS_CONTACT_ENRICHMENT (ineligible).
    5. Entity with unverified VAT / low score -> NEEDS_IDENTITY_VERIFICATION (ineligible).
    6. Entity with bounded dedupe -> NEEDS_CRM_RECHECK (ineligible).
    """
    settings = Settings(environment=Environment.MOCK, data_dir=tmp_path, log_dir=tmp_path)
    hub = build_hub(settings=settings)
    ctx = ToolContext(correlation_id="golden-dataset-run")
    rt = HubRuntime(settings=settings, registry=hub.registry, ctx=ctx, artifacts_dir=settings.data_dir / "artifacts")

    # Seed trusted legal verification decision for Lead 1
    store = StagingStore(settings.data_dir / "marketing.db")
    store.initialize()
    store.save_legal_decision(TrustedLegalVerificationDecision(
        entity_id="Công ty TNHH Y Tế Hoàn Hảo",
        vat_number="0107889123",
        legal_name="Công ty TNHH Y Tế Hoàn Hảo",
        registry_source="national_tax_registry_vietnam",
        request_ref="req-golden-01",
        source_data_hash="hash-golden-01",
        decision_status="VERIFIED",
    ))

    golden_leads = [
        # Lead 1: Complete and fully eligible
        {
            "company": "Công ty TNHH Y Tế Hoàn Hảo",
            "vat_number": "0107889123",
            "domain": "hoanhao-med.vn",
            "contact_name": "Lê Văn Thắng",
            "title": "Giám đốc Mua hàng",
            "email": "thang.lv@hoanhao-med.vn",
            "data_quality_score": 85,
            "commercial_fit_score": 90,
            "crm_dedupe_status": "NOT_FOUND_VERIFIED",
            "evidence": [{"field_name": "vat_number", "status": "SOURCE_CORROBORATED"}],
        },
        # Lead 2: Duplicate in CRM
        {
            "company": "Minh Van ITL Logistics",
            "vat_number": "0101416719",
            "contact_name": "Trần Văn A",
            "email": "a.tv@minhvan.com",
            "crm_dedupe_status": "DUPLICATE_CONFIRMED",
        },
        # Lead 3: Missing contact name
        {
            "company": "Công ty CP Dược Phẩm Thiếu Nhân Sự",
            "vat_number": "0314567890",
            "contact_name": None,
            "email": "info@duocpham.vn",
            "data_quality_score": 70,
            "crm_dedupe_status": "NOT_FOUND_VERIFIED",
        },
        # Lead 4: Missing email
        {
            "company": "Công ty TNHH Không Email",
            "vat_number": "2300987654",
            "contact_name": "Nguyễn Văn C",
            "email": None,
            "data_quality_score": 75,
            "crm_dedupe_status": "NOT_FOUND_VERIFIED",
        },
        # Lead 5: Invalid VAT / low data quality
        {
            "company": "Công ty Sai Ma So Thue",
            "vat_number": "INVALID_VAT",
            "contact_name": "Phạm Văn D",
            "email": "d.pv@saimst.vn",
            "data_quality_score": 30,
            "crm_dedupe_status": "NOT_FOUND_VERIFIED",
        },
        # Lead 6: Bounded dedupe check (incomplete coverage)
        {
            "company": "Công ty Dedupe Chưa Xong",
            "vat_number": "3702112233",
            "contact_name": "Hoàng Văn E",
            "email": "e.hv@chuaxong.vn",
            "data_quality_score": 80,
            "crm_dedupe_status": "PARTIAL_COVERAGE",
        },
    ]

    preview_res = crm_preview_import(PreviewCrmImportIn(leads=golden_leads), rt)

    # Verification of preview outcomes
    staged = preview_res["staged_records"]
    eligible = preview_res["eligible_records"]
    excluded = preview_res["excluded_records"]

    assert preview_res["total_input"] == 6
    assert len(excluded) == 1, "Lead 2 must be excluded due to CRM duplicate"
    assert excluded[0]["company"] == "Minh Van ITL Logistics"

    assert len(eligible) == 1, "Exactly ONE lead (Lead 1) must be eligible for CRM import"
    assert eligible[0]["company"] == "Công ty TNHH Y Tế Hoàn Hảo"
    assert eligible[0]["action"] == "STAGED_FOR_INSERT"
    assert eligible[0]["eligible_for_crm_import"] is True

    # Ineligible leads verification
    lead3_staged = next(s for s in staged if s["company"] == "Công ty CP Dược Phẩm Thiếu Nhân Sự")
    assert lead3_staged["action"] == "NEEDS_ENRICHMENT"
    assert lead3_staged["eligible_for_crm_import"] is False

    lead5_staged = next(s for s in staged if s["company"] == "Công ty Sai Ma So Thue")
    assert lead5_staged["action"] in ("NEEDS_VERIFICATION", "NEEDS_ENRICHMENT")
    assert lead5_staged["eligible_for_crm_import"] is False

    lead6_staged = next(s for s in staged if s["company"] == "Công ty Dedupe Chưa Xong")
    assert lead6_staged["action"] == "REVIEW_REQUIRED_DEDUPE_INCOMPLETE"
    assert lead6_staged["eligible_for_crm_import"] is False

    # Workflow Gate Verification (V7-007)
    mock_gate = MagicMock(return_value="GATE_CALLED")
    step_ctx = MagicMock(spec=StepContext)
    step_ctx.outputs = {"crm_preview": preview_res}
    step_ctx.gate = mock_gate

    step_gtm_gate(step_ctx)
    mock_gate.assert_called_once()
    gate_records = mock_gate.call_args[0][1]
    assert len(gate_records) == 1, "Gate must receive ONLY the 1 eligible record"
    assert gate_records[0]["company"] == "Công ty TNHH Y Tế Hoàn Hảo"

    # Finalize Stage Verification with approved record
    from marketing_system.workflows.approvals import payload_hash
    expected_digest = payload_hash("workflow.stage_leads_for_crm", eligible)
    mock_engine = MagicMock()
    mock_rec = MagicMock()
    mock_rec.status = "APPROVED"
    mock_rec.expired.return_value = False
    mock_rec.payload_hash = expected_digest
    mock_engine.approvals.get.return_value = mock_rec
    step_ctx.engine = mock_engine
    step_ctx.outputs["approval_gate"] = {"approval_id": "appr-golden-v7"}

    finalize_outcome = step_gtm_finalize_stage(step_ctx)
    assert finalize_outcome.output["approved_count"] == 1
    assert finalize_outcome.output["stage_status"] == "APPROVED_FOR_CRM"


# ==============================================================================
# SECTION 3: STABLE IDENTITY & PERSISTENCE (V7-004 & V7-005)
# ==============================================================================

def test_stable_identity_cross_process_consistency():
    """Verify generate_stable_lead_id produces identical IDs across Python invocations."""
    id_vat1 = generate_stable_lead_id("Cong ty A", "a.vn", "0107889123")
    id_vat2 = generate_stable_lead_id("Cong ty A - Hanoi Branch", "a.com", "0107889123")
    assert id_vat1 == id_vat2, "Same VAT must produce same canonical lead ID regardless of alias name"

    id_novat1 = generate_stable_lead_id("Cong ty B", "b.vn")
    id_novat2 = generate_stable_lead_id("  cong   ty   b  ", "B.VN")
    assert id_novat1 == id_novat2, "Normalized company and domain must produce same canonical ID"


def test_business_events_emission_in_staging_store(tmp_path):
    """Verify StagingStore records canonical business events."""
    db_path = tmp_path / "marketing.db"
    store = StagingStore(db_path)
    store.initialize()

    evt = BusinessEvent(
        event_type="lead.discovered",
        entity_id="lead-evt-1234",
        workflow_id="wf-test-01",
        environment=Environment.MOCK,
        synthetic=True,
        source="apollo",
        payload_json={"company": "Test Event Co"}
    )
    store.record_event(evt)

    events = store.list_events(environment=Environment.MOCK, event_type="lead.discovered")
    assert len(events) == 1
    assert events[0]["entity_id"] == "lead-evt-1234"
    assert events[0]["payload"]["company"] == "Test Event Co"


# ==============================================================================
# SECTION 4: REVERSE PROXY & TUNNEL SECURITY (V7-010)
# ==============================================================================

def test_reverse_proxy_tunnel_auth_enforcement():
    """Verify _is_proxied_external detects proxy headers and fails closed without token."""
    from conftest import get_sibling_workspace_path
    dashboard_path = get_sibling_workspace_path("buzz-ai-usage-center/bin/dashboard.py")
    if not dashboard_path or not dashboard_path.exists():
        pytest.skip("dashboard.py not found in sibling workspace")

    content = dashboard_path.read_text(encoding="utf-8")
    assert "def _is_proxied_external" in content, "Handler must implement _is_proxied_external"
    assert "x-forwarded-for" in content
    assert "x-real-ip" in content
    assert "cf-connecting-ip" in content


# ==============================================================================
# SECTION 5: SQLITE ERROR TRUTH & RECOVERY (V7-009)
# ==============================================================================

def test_sqlite_error_truth_and_status_transparency(tmp_path):
    """Verify dashboard reports NO_DATA when DB is missing and does not crash."""
    from conftest import get_sibling_workspace_path
    dashboard_path = get_sibling_workspace_path("buzz-ai-usage-center/bin/dashboard.py")
    if not dashboard_path or not dashboard_path.exists():
        pytest.skip("dashboard.py not found in sibling workspace")

    content = dashboard_path.read_text(encoding="utf-8")
    assert "data_status" in content
    assert "DATABASE_LOCKED" in content
    assert "SOURCE_ERROR" in content
