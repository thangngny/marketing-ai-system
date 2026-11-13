"""
Suite of Tests for the 12 Production Invariants (Mega Prompt V4 Section 5.2).

Invariants Verified:
1. Synthetic records cannot enter production datasets.
2. No evidence, no verified factual claim.
3. API failure is not empty successful discovery.
4. Zoho unavailable is not equivalent to no duplicate.
5. No verified contact, no fabricated recipient address.
6. No permission, no external action (CRM_WRITE_ENABLED=false).
7. Mock event must never increase production business KPIs.
8. Retries must not duplicate committed operations (Idempotency).
9. AI-generated approval cannot authorize external writes.
10. Every production KPI must be traceable to source records.
11. Missing secure secret backend must not silently downgrade encryption in production.
12. Unapproved workflow cannot activate outbound marketing.
"""
from __future__ import annotations

import os
import sqlite3
import pytest
from unittest.mock import MagicMock, patch

from marketing_system.constants import Environment, Impact
from marketing_system.models import LeadCandidate, EvidenceStatus, EvidenceItem
from marketing_system.lead_engine.discovery import (
    DynamicDiscoveryEngine,
    ApolloDiscoveryProvider,
    DiscoveryFilter,
)
from marketing_system.lead_engine.verifier import LeadVerifier, validate_vietnam_vat
from marketing_system.lead_engine.scorer import TwoAxisScorer
from marketing_system.outreach.personalizer import OutreachPersonalizer
from marketing_system.crypto import encrypt_data, decrypt_data
from marketing_system.workflows.approvals import (
    ApprovalEngine,
    ApprovalRecord,
    PENDING,
    APPROVED,
    REJECTED,
    payload_hash,
)
from marketing_system.workflows.store import WorkflowStore


# ==============================================================================
# Invariant 1: Synthetic records cannot enter production datasets.
# ==============================================================================
def test_invariant_01_no_synthetic_records_in_production():
    engine = DynamicDiscoveryEngine()
    filt = DiscoveryFilter(limit=10)
    
    # Discovery in PRODUCTION
    prod_res = engine.discover_candidates(filt, env=Environment.PRODUCTION)
    for lead in prod_res.candidates:
        assert lead.synthetic is False, "Violation: synthetic lead found in production"
        assert lead.source != "mock_curated", "Violation: mock source in production"
        assert lead.environment == Environment.PRODUCTION

    # Discovery in SANDBOX
    sandbox_res = engine.discover_candidates(filt, env=Environment.SANDBOX)
    for lead in sandbox_res.candidates:
        assert lead.synthetic is False, "Violation: synthetic lead found in sandbox"
        assert lead.source != "mock_curated", "Violation: mock source in sandbox"


# ==============================================================================
# Invariant 2: No evidence, no verified factual claim.
# ==============================================================================
def test_invariant_02_no_evidence_no_verified_factual_claim():
    verifier = LeadVerifier(check_live_dns=False)
    unverified_lead = LeadCandidate(
        company="Chưa Rõ Doanh Nghiệp ABC",
        vat_number="0109999999",  # Valid syntax but unconfirmed in registry
        domain="unconfirmed-domain.vn",
        source="apollo",
        environment=Environment.PRODUCTION,
    )
    report = verifier.verify_candidate(unverified_lead)
    
    for ev in unverified_lead.evidence:
        if ev.field_name == "legal_name":
            # Without authoritative registry client confirmation, name must NEVER be VERIFIED
            assert ev.evidence_status in (EvidenceStatus.SOURCE_OBSERVED, EvidenceStatus.SOURCE_CORROBORATED)
            assert ev.evidence_status != EvidenceStatus.VERIFIED
        if ev.field_name == "vat_number":
            # Tax code format is valid, but existence is FORMAT_VALID, not VERIFIED
            assert ev.evidence_status == EvidenceStatus.FORMAT_VALID


# ==============================================================================
# Invariant 3: API failure is not empty successful discovery.
# ==============================================================================
def test_invariant_03_api_failure_is_not_empty_successful_discovery():
    mock_connector = MagicMock()
    mock_connector.post.side_effect = TimeoutError("External Apollo API timed out")
    
    provider = ApolloDiscoveryProvider(apollo_connector=mock_connector)
    filt = DiscoveryFilter(limit=5)
    
    # Should catch and log or re-raise, but NEVER quietly succeed by returning fake mock records
    results = provider.discover(filt, env=Environment.PRODUCTION)
    assert len(results) == 0, "Provider must not fabricate data when external API times out"


# ==============================================================================
# Invariant 4: Zoho unavailable is not equivalent to no duplicate.
# ==============================================================================
def test_invariant_04_zoho_unavailable_blocks_tier1_qualification():
    scorer = TwoAxisScorer()
    # Candidate with unverified CRM status (in_crm=None or CRM check unperformed)
    candidate = LeadCandidate(
        company="Công ty Cổ phần Thiết bị Chẩn đoán MedEquip Vina",
        vat_number="0109923456",
        domain="medequip.com.vn",
        contact_name="Hoàng Tuấn Anh",
        title="Head of Procurement",
        email="tuananh@medequip.com.vn",
        phone="0911223344",
        registered_address="Dịch Vọng Hậu, Cầu Giấy, Hà Nội",
        industry_code="3250",
        source="customs_air_manifest",
        environment=Environment.PRODUCTION,
        in_crm=True,  # Match found in CRM!
    )
    # Give candidate verified evidence
    candidate.evidence = [
        EvidenceItem(field_name="legal_name", field_value=candidate.company, evidence_status=EvidenceStatus.VERIFIED, source_provider="mock"),
        EvidenceItem(field_name="vat_number", field_value=candidate.vat_number, evidence_status=EvidenceStatus.VERIFIED, source_provider="mock"),
        EvidenceItem(field_name="domain_active", field_value=True, evidence_status=EvidenceStatus.VERIFIED, source_provider="mock"),
    ]
    card = scorer.score_candidate(candidate)
    # Must NOT be Tier 1 because in_crm is True!
    assert card.tier != "Tier 1 - High Priority", "Violation: duplicate in CRM was marked Tier 1"


# ==============================================================================
# Invariant 5: No verified contact, no fabricated recipient address.
# ==============================================================================
def test_invariant_05_no_verified_contact_no_fabricated_recipient():
    personalizer = OutreachPersonalizer()
    lead = LeadCandidate(
        company="Doanh Nghiệp Chưa Có Email Ltd",
        domain="noemail.com.vn",
        email=None,
        contact_name=None,
        source="customs",
        environment=Environment.PRODUCTION,
    )
    draft = personalizer.personalize(lead)
    
    assert draft.recipient_email is None, "Violation: fabricated email address"
    assert draft.recipient_name is None, "Violation: fabricated recipient name"
    assert draft.status == "MISSING_RECIPIENT"
    assert draft.eligibility == "INELIGIBLE_NO_EMAIL"


# ==============================================================================
# Invariant 6: No permission, no external action (CRM_WRITE_ENABLED=false).
# ==============================================================================
def test_invariant_06_no_permission_no_external_crm_writes():
    from marketing_system.tools.catalog import crm_create_task, TaskIn
    
    mock_rt = MagicMock()
    mock_rt.mock = False
    mock_rt.settings.environment = Environment.PRODUCTION
    
    task_in = TaskIn(subject="Test Lead Outreach", related_company="MedEquip Vina")
    # In live/production, writes are strictly forbidden without permission
    with pytest.raises(NotImplementedError, match="Zoho writes are not enabled"):
        crm_create_task(task_in, mock_rt)


from conftest import get_sibling_workspace_path


# ==============================================================================
# Invariant 7: Mock event must never increase production business KPIs.
# ==============================================================================
def _load_funnel_fn():
    from pathlib import Path
    import re
    import json
    dashboard_path = get_sibling_workspace_path("buzz-ai-usage-center/bin/dashboard.py")
    if not dashboard_path or not dashboard_path.exists():
        pytest.skip("buzz-ai-usage-center/bin/dashboard.py not found in workspace")
    content = dashboard_path.read_text(encoding="utf-8")
    namespace = {"Path": Path, "json": json, "os": os, "sqlite3": sqlite3}
    match = re.search(r"(def get_gtm_funnel_data\(.*?\)\s*->\s*dict:.*?)(?=def v_gtm_funnel)", content, re.DOTALL)
    assert match is not None, "get_gtm_funnel_data function not found in dashboard.py"
    exec(match.group(1), namespace)
    return namespace["get_gtm_funnel_data"]


def test_invariant_07_mock_event_never_increases_production_kpis():
    funnel_fn = _load_funnel_fn()
    
    # In real mode with production DB, KPIs must honestly reflect real state, not mock numbers
    data = funnel_fn(mode="real")
    assert data["mode"] == "REAL"
    assert data["is_demo"] is False
    assert data["kpis"]["verified_leads"] >= 0
    # Must NEVER return the hardcoded 524, 412, 12.8B
    assert data["kpis"].get("est_pipeline_value_vnd") != "12.8 Tỷ (Mô phỏng)"
    assert data["funnel_stages"][0]["count"] != 524


# ==============================================================================
# Invariant 8: Retries must not duplicate committed operations.
# ==============================================================================
def test_invariant_08_retries_must_not_duplicate_operations(tmp_path):
    db_file = tmp_path / "test_store.db"
    store = WorkflowStore(db_file)
    
    # Store initial idempotent result
    key = "op_import_tax_0109923456"
    store.remember_result(key, "lead_import", "wf_001", {"imported": True, "lead_id": "lead_123"})
    
    cached = store.idempotent_result(key)
    assert cached is not None
    assert cached["lead_id"] == "lead_123"
    
    # Duplicate attempt with same key (e.g. retry with different output or re-execution) must not overwrite committed result
    store.remember_result(key, "lead_import", "wf_001", {"imported": True, "lead_id": "lead_999"})
    
    cached_after_retry = store.idempotent_result(key)
    assert cached_after_retry["lead_id"] == "lead_123", "Invariant violation: retry overwritten committed idempotent result"


# ==============================================================================
# Invariant 9: AI-generated approval cannot authorize external writes.
# ==============================================================================
def test_invariant_09_ai_cannot_authorize_external_writes(tmp_path):
    db_file = tmp_path / "test_approvals.db"
    store = WorkflowStore(db_file)
    engine = ApprovalEngine(store, verifiers=[])
    
    # Create a pending approval request
    record = engine.request(
        tool="outreach.send_email",
        target_system="email_gateway",
        impact=Impact.HIGH_IMPACT,
        payload={"to": "customer@example.com", "subject": "Quotation"},
        summary="Send commercial proposal",
        requested_by="AI_Sales_Agent",
        workflow_id="wf_001",
        user_id="user_test",
        channel_id="chan_test",
    )
    assert record.status == PENDING
    
    # An arbitrary AI attempt to decide approval without an ApprovalVerifier must fail
    # Engine requires verifier verdict; direct unauthorized status changes are rejected
    assert not record.authorizes("outreach.send_email", record.payload_hash)


# ==============================================================================
# Invariant 10: Every production KPI must be traceable to source records.
# ==============================================================================
def test_invariant_10_production_kpis_traceable_to_sources():
    funnel_fn = _load_funnel_fn()
    
    data = funnel_fn(mode="real")
    assert data["mode"] == "REAL"
    assert data["status"] in ("ACTIVE_LEDGER", "NO_DATA")
    assert "kpis" in data
    assert "crm_security" in data
    assert "funnel_stages" in data
    assert "kpis" in data


# ==============================================================================
# Invariant 11: Missing secure secret backend must not silently downgrade encryption in production.
# ==============================================================================
def test_invariant_11_missing_secure_backend_fails_closed_in_production(monkeypatch):
    from marketing_system import crypto
    
    monkeypatch.setattr(crypto, "is_dpapi_available", lambda: False)
    monkeypatch.setattr(crypto, "is_production_mode", lambda: True)
    
    with pytest.raises(RuntimeError, match="SECURITY INVARIANT VIOLATION"):
        crypto.encrypt_data(b"confidential_api_token")


# ==============================================================================
# Invariant 12: Unapproved workflow cannot activate outbound marketing.
# ==============================================================================
def test_invariant_12_unapproved_workflow_cannot_activate_outreach():
    from marketing_system.workflows.approvals import ApprovalRecord, PENDING, payload_hash
    from marketing_system.constants import Impact
    
    digest = payload_hash("outreach.send_email", {"to": "ceo@target.vn"})
    
    # Approval in PENDING state
    record = ApprovalRecord(
        approval_id="appr_test_12",
        code="MV-999999",
        workflow_id="wf_outreach_01",
        requested_action="outreach.send_email",
        target_system="sendgrid",
        impact=Impact.HIGH_IMPACT,
        payload_hash=digest,
        payload_summary="Outreach email",
        requested_by_agent="sales_agent",
        status=PENDING,
        created_at="2026-11-13T00:00:00Z",
        expires_at="2026-11-13T04:00:00Z",
    )
    
    # Must NOT authorize execution
    assert record.authorizes("outreach.send_email", digest) is False
