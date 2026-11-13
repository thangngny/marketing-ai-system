# tests/test_v7_defect_reproduction.py
"""
Reproduction and verification test suite for Master Mega Prompt V7:
V7-001 through V7-010.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from marketing_system.config import Settings
from marketing_system.constants import Environment
from marketing_system.models import (
    LeadCandidate,
    EvidenceItem,
    EvidenceStatus,
    Lead,
)
from marketing_system.tools.catalog import (
    build_hub,
    crm_find_existing,
    crm_preview_import,
    lead_pipeline_run,
    FindExistingIn,
    PreviewCrmImportIn,
    LeadPipelineRunIn,
)
from marketing_system.storage import StagingStore


from marketing_system.tools.hub import HubRuntime, ToolContext


def test_v7_001_and_002_per_entity_dedupe_and_no_contamination(tmp_path):
    """V7-001 & V7-002: Dedupe must be per-entity and an API error or bounded search must NOT declare NOT_FOUND_VERIFIED."""
    settings = Settings(environment=Environment.SANDBOX, data_dir=tmp_path, log_dir=tmp_path)
    hub = build_hub(settings=settings)
    ctx = ToolContext(correlation_id="test-v7-001")
    rt = HubRuntime(settings=settings, registry=hub.registry, ctx=ctx, artifacts_dir=settings.data_dir / "artifacts")

    # Mock connector where read raises an exception
    mock_conn = MagicMock()
    mock_conn.read.side_effect = RuntimeError("Zoho CRM connection timeout")
    rt.registry._connectors["zoho"] = mock_conn

    # Batch with 2 companies
    args = FindExistingIn(
        companies=["Company A Error", "Company B Normal"],
        vats=["0107889123", "0314567890"]
    )
    res = crm_find_existing(args, rt)

    # Per-entity decisions must exist
    assert "decisions" in res, "crm_find_existing must return per-entity 'decisions'"
    decisions = res["decisions"]
    assert "Company A Error" in decisions
    assert "Company B Normal" in decisions

    # An API error must result in CHECK_FAILED, NEVER NOT_FOUND_VERIFIED
    dec_a = decisions["Company A Error"]
    assert dec_a["decision_status"] in ("CHECK_FAILED", "PARTIAL_COVERAGE")
    assert dec_a["decision_status"] != "NOT_FOUND_VERIFIED"


def test_v7_003_crm_preview_strict_eligibility_no_placeholders(tmp_path):
    """V7-003: Ineligible records (missing contact name, missing verified dedupe) must NOT be STAGED_FOR_INSERT,
    and placeholders like '[Chưa xác minh]' must not be in real insert payload."""
    settings = Settings(environment=Environment.MOCK, data_dir=tmp_path, log_dir=tmp_path)
    hub = build_hub(settings=settings)
    ctx = ToolContext(correlation_id="test-v7-003")
    rt = HubRuntime(settings=settings, registry=hub.registry, ctx=ctx, artifacts_dir=settings.data_dir / "artifacts")

    leads = [
        {
            "company": "Công ty TNHH Ineligible One",
            "vat_number": "0107889123",  # Valid VAT syntax
            "data_quality_score": 85,    # High score
            "commercial_fit_score": 85,
            # Missing contact_name!
            "contact_name": None,
            "crm_dedupe_status": "PARTIAL_COVERAGE",  # Dedupe incomplete!
        }
    ]

    res = crm_preview_import(PreviewCrmImportIn(leads=leads), rt)
    staged = res["staged_records"]
    assert len(staged) == 1
    record = staged[0]

    # Must NOT be STAGED_FOR_INSERT
    assert record["action"] != "STAGED_FOR_INSERT"
    assert record["action"] in ("NEEDS_CONTACT_ENRICHMENT", "NEEDS_ENRICHMENT", "NEEDS_CRM_RECHECK", "REVIEW_REQUIRED_DEDUPE_INCOMPLETE")
    assert record.get("eligible_for_crm_import") is False

    # Real payload for insert must not contain "[Chưa xác minh]" or "Chưa có chức danh"
    payload = record["payload"]
    assert payload.get("Last_Name") != "[Chưa xác minh]"
    assert payload.get("Designation") != "Chưa có chức danh"


def test_v7_004_lead_pipeline_persistence(tmp_path):
    """V7-004: lead_pipeline_run must persist canonical leads to StagingStore without throwing/swallowing import errors."""
    settings = Settings(environment=Environment.MOCK, data_dir=tmp_path, log_dir=tmp_path)
    hub = build_hub(settings=settings)
    ctx = ToolContext(correlation_id="test-v7-004")
    rt = HubRuntime(settings=settings, registry=hub.registry, ctx=ctx, artifacts_dir=settings.data_dir / "artifacts")

    db_path = rt.settings.data_dir / "marketing.db"
    store = StagingStore(db_path)
    store.initialize()

    args = LeadPipelineRunIn(industry_keywords=["medical"], limit=2)
    result = lead_pipeline_run(args, rt)
    assert result is not None

    # Verify canonical_records table actually contains the leads!
    records = store.list_records(environment=rt.settings.environment, entity_type="Lead")
    assert len(records) > 0, "Canonical Lead records MUST be persisted in StagingStore"



def test_v7_005_stable_lead_identity():
    """V7-005: Lead identity must be deterministic and not depend on python hash()."""
    from marketing_system.identity import generate_stable_lead_id

    # Same company and VAT across runs must produce identical ID
    id1 = generate_stable_lead_id(company="Công ty TNHH Thiết bị Y tế Chuyên Dụng Tâm An", domain="tamanmedical.com.vn", vat_number="0107889123")
    id2 = generate_stable_lead_id(company="Công ty TNHH Thiết bị Y tế Chuyên Dụng Tâm An", domain="tamanmedical.com.vn", vat_number="0107889123")
    assert id1 == id2
    assert id1.startswith("lead-")
    assert "hash" not in id1

    # Two companies with different VATs must have different IDs
    id3 = generate_stable_lead_id(company="Công ty TNHH Thiết bị Y tế Chuyên Dụng Tâm An", domain="tamanmedical.com.vn", vat_number="0314567890")
    assert id1 != id3


def test_v7_007_workflow_approval_gate_filters_ineligible():
    """V7-007: GTM Lead Pipeline approval gate must only propose eligible records for staging."""
    from marketing_system.workflows.definitions import step_gtm_gate
    from marketing_system.workflows.engine import StepContext

    # Mock preview where 1 record is eligible and 2 are ineligible
    preview = {
        "staged_records": [
            {"company": "Eligible Co", "action": "STAGED_FOR_INSERT", "eligible_for_crm_import": True, "payload": {"Company": "Eligible Co"}},
            {"company": "Ineligible Co 1", "action": "NEEDS_ENRICHMENT", "eligible_for_crm_import": False, "payload": {}},
            {"company": "Ineligible Co 2", "action": "NEEDS_CRM_RECHECK", "eligible_for_crm_import": False, "payload": {}},
        ],
        "write_enabled": False,
    }

    mock_gate_fn = MagicMock(return_value="GATE_INVOKED")
    ctx = MagicMock(spec=StepContext)
    ctx.outputs = {"crm_preview": preview}
    ctx.gate = mock_gate_fn

    step_gtm_gate(ctx)
    mock_gate_fn.assert_called_once()
    called_args = mock_gate_fn.call_args[0]
    proposed_records = called_args[1]

    # Only 1 record (the eligible one) must be sent to human gate!
    assert len(proposed_records) == 1
    assert proposed_records[0]["company"] == "Eligible Co"
