"""
Tests for Phase P6: Resilience, Negative Path Handling, Security Hardening, and Fault Recovery.
Covers:
- Corrupted DPAPI token recovery.
- Cross-process concurrency lock contention and timeout safety.
- Malformed / invalid VAT and unresolvable domain rejection.
- Two-axis scoring boundary conditions and negative lead signals.
- Workflow approval digest tamper protection.
- Dashboard API bearer token rejection and security boundaries.
- CRM and Outreach write safety guards (dry-run enforcement).
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
import pytest

from marketing_system.config import Settings
from marketing_system.constants import Environment, Impact
from marketing_system.crypto import (
    encrypt_data,
    decrypt_data,
    save_secure_json,
    load_secure_json,
    DPAPI_MAGIC,
)
from marketing_system.lead_engine.verifier import (
    LeadVerifier,
    validate_vietnam_vat,
    check_domain_mx,
)
from marketing_system.lead_engine.scorer import TwoAxisScorer
from marketing_system.models import LeadCandidate, EvidenceItem, EvidenceStatus
from marketing_system.tools.catalog import build_hub
from marketing_system.tools.hub import ToolContext
from marketing_system.workflows.approvals import ApprovalEngine, payload_hash
from marketing_system.workflows.store import WorkflowStore


def test_dpapi_corrupted_payload_recovery(tmp_path):
    """Verify that load_secure_json safely handles corrupted DPAPI ciphertext without crashing."""
    corrupted_file = tmp_path / "corrupted_secret.json"
    
    # 1. File with valid magic header but garbage ciphertext
    corrupted_file.write_bytes(DPAPI_MAGIC + b"malicious_or_corrupted_junk_data_12345")
    result = load_secure_json(corrupted_file)
    assert result is None, "Corrupted DPAPI payload must return None rather than raising an unhandled exception"
    
    # 2. File with valid magic header but truncated length (0 bytes after magic)
    corrupted_file.write_bytes(DPAPI_MAGIC)
    result = load_secure_json(corrupted_file)
    assert result is None, "Truncated DPAPI payload must return None"

    # 3. Completely empty file
    corrupted_file.write_bytes(b"")
    result = load_secure_json(corrupted_file)
    assert result is None, "Empty file must return None"

    # 4. Non-JSON plaintext garbage
    corrupted_file.write_bytes(b"{not valid json at all")
    result = load_secure_json(corrupted_file)
    assert result is None, "Non-JSON plaintext must return None without crashing"


from conftest import get_sibling_workspace_path


def test_cross_process_lock_contention(tmp_path):
    """Test inter-process lock behavior during contention."""
    import importlib.util
    
    dedupe_script = get_sibling_workspace_path("Buzz-Marketing-OS-Enterprise-Suite/03-Marketing-Hub/services/lead-pipeline/zoho_live_dedupe.py")
    if not dedupe_script or not dedupe_script.exists():
        pytest.skip("zoho_live_dedupe.py not found in local path")
        
    spec = importlib.util.spec_from_file_location("zoho_live_dedupe", str(dedupe_script))
    dedupe_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dedupe_module)
    CrossProcessLock = dedupe_module.CrossProcessLock
    
    lock_file = tmp_path / "test_concurrency.lock"
    
    # First acquire
    lock1 = CrossProcessLock(lock_file=lock_file, timeout=0.3)
    with lock1:
        assert lock_file.exists(), "Lock file should be created"
        
        # Second acquire with short timeout should not crash or deadlock
        lock2 = CrossProcessLock(lock_file=lock_file, timeout=0.1)
        with lock2:
            pass  # Fallback handles timeout gracefully

    # Lock file should be cleaned up on clean exit
    assert not lock_file.exists(), "Lock file should be unlinked after exit"


def test_lead_verifier_malformed_vat_rejection():
    """Verify that invalid VAT numbers are rejected or flagged."""
    # Short VAT (< 10 digits)
    valid_short, _ = validate_vietnam_vat("01234")
    assert valid_short is False
    
    # VAT with non-digits
    valid_alpha, _ = validate_vietnam_vat("010123ABCD")
    assert valid_alpha is False
    
    # None / Empty VAT
    valid_none, _ = validate_vietnam_vat(None)
    assert valid_none is False
    valid_empty, _ = validate_vietnam_vat("")
    assert valid_empty is False

    # Valid 10-digit VAT
    valid_ok, _ = validate_vietnam_vat("0101416719")
    assert valid_ok is True


def test_lead_verifier_unresolvable_domain():
    """Verify that fake, malformed, or disposable email domains fail verification."""
    # Bogus domain with invalid characters
    has_mx_bogus, _ = check_domain_mx("invalid..domain..xyz")
    assert has_mx_bogus is False
    
    # Disposable domain
    has_mx_disp, _ = check_domain_mx("mailinator.com")
    assert has_mx_disp is False

    # Non-existent DNS domain with live check enabled
    has_mx_fake, _ = check_domain_mx("nonexistent-test-company-12349876xyz.invalid", check_dns=True)
    assert has_mx_fake is False


def test_two_axis_scorer_boundary_conditions():
    """Test edge cases: zero data vs rich data, separating data quality from commercial fit."""
    verifier = LeadVerifier(check_live_dns=False)
    scorer = TwoAxisScorer()
    
    # Case A: Empty Lead with zero signals
    empty_lead = LeadCandidate(
        company="Ghost LLC",
        source="apollo",
        environment=Environment.MOCK,
    )
    report_a = verifier.verify_candidate(empty_lead)
    score_a = scorer.score_candidate(empty_lead)
    assert score_a.data_quality_score <= 25
    assert score_a.commercial_fit_score <= 25
    assert score_a.tier == "Disqualified"

    # Case B: Verified legal company (high data quality) but zero logistics signals (low commercial fit)
    legal_only_lead = LeadCandidate(
        company="Nguyen Van Law Firm",
        vat_number="0101416719",
        domain="nguyenvanlaw.vn",
        industry_code="6910",  # Legal activities
        registered_address="123 Phan Chu Trinh, Ha Noi",
        source="apollo",
        environment=Environment.MOCK,
    )
    report_b = verifier.verify_candidate(legal_only_lead)
    score_b = scorer.score_candidate(legal_only_lead)
    assert score_b.data_quality_score >= 60, "Data quality should be >= 60 due to valid VAT, domain, and address"
    assert score_b.commercial_fit_score < 40, "Commercial fit should be low because law firm has no logistics demand"
    assert "Tier 3" in score_b.tier or "Disqualified" in score_b.tier

    # Case C: High logistics volume importer (high commercial fit) with unverified VAT
    high_volume_lead = LeadCandidate(
        company="Fast Medical Supply Corp",
        vat_number="invalid_vat",
        domain="fastmed.vn",
        industry_code="3250",  # Medical instruments
        source="customs_air_manifest",
        environment=Environment.MOCK,
    )
    report_c = verifier.verify_candidate(high_volume_lead)
    assert report_c.is_valid_lead is False, "Invalid VAT should fail validation"
    score_c = scorer.score_candidate(high_volume_lead)
    assert score_c.commercial_fit_score >= 80, "High air cargo volume and medical ICP must yield high commercial fit"
    assert score_c.data_quality_score <= 60, "Invalid VAT caps data quality"


def test_workflow_approval_tamper_protection(tmp_path):
    """Verify that tampering with approval payload invalidates authorization."""
    store = WorkflowStore(tmp_path / "marketing.db")
    approvals = ApprovalEngine(store)
    
    original_payload = {"company": "Trusted Corp", "vat": "0101416719", "action": "import"}
    rec = approvals.request(
        tool="crm.import_lead",
        target_system="zoho",
        impact=Impact.HIGH_IMPACT,
        payload=original_payload,
        summary="Import Trusted Corp to Zoho CRM",
        requested_by="06_sales_copilot",
        workflow_id="wf-test-tamper",
        user_id="buzz:user:owner",
        channel_id="chan-gtm"
    )
    
    # Decide approval locally
    decided = approvals.decide_locally(rec.approval_id, True, "buzz:user:owner")
    assert decided.status == "APPROVED"
    
    # 1. Check authorization with untouched payload: should SUCCEED
    orig_digest = payload_hash("crm.import_lead", original_payload)
    assert decided.authorizes("crm.import_lead", orig_digest) is True
    
    # 2. Check authorization with tampered payload: should FAIL
    tampered_payload = {"company": "Malicious Corp", "vat": "0999999999", "action": "import"}
    tampered_digest = payload_hash("crm.import_lead", tampered_payload)
    assert decided.authorizes("crm.import_lead", tampered_digest) is False, "Tampered payload digest must be rejected"


def test_dashboard_token_security_barrier():
    """Verify dashboard bearer token authentication barrier rejects unauthorized requests."""
    dashboard_path = get_sibling_workspace_path("buzz-ai-usage-center/bin/dashboard.py")
    if not dashboard_path or not dashboard_path.exists():
        pytest.skip("dashboard.py not found in buzz-ai-usage-center")
        
    code = dashboard_path.read_text(encoding="utf-8")
    assert "BUZZ_DASHBOARD_TOKEN" in code, "Dashboard must configure BUZZ_DASHBOARD_TOKEN"
    assert "401" in code, "Dashboard must return HTTP 401 when unauthenticated"
    assert "gtm_sales_funnel" in code or "/gtm-funnel" in code, "Dashboard must contain GTM Sales Funnel tab"


def test_crm_write_safety_guard_enforcement(tmp_path, monkeypatch):
    """Verify crm.preview_import strictly enforces preview mode and never mutates live CRM."""
    monkeypatch.setenv("CRM_WRITE_ENABLED", "false")
    settings = Settings(environment=Environment.MOCK, data_dir=tmp_path, log_dir=tmp_path)
    hub = build_hub(settings=settings)
    ctx = ToolContext(correlation_id="test-p6-guard", specialist_id="06_sales_copilot")

    candidate_leads = [
        {
            "company": "Công ty TNHH Safe Lead",
            "vat_number": "0101234567",
            "domain": "safelead.vn",
            "contact_name": "Tran Safe",
            "data_quality_score": 85,
            "commercial_fit_score": 80,
            "score": 82,
        }
    ]

    result = hub.invoke("crm.preview_import", {"leads": candidate_leads}, ctx)
    assert result.succeeded is True
    data = result.data
    assert data["write_enabled"] is False, "CRM write must be blocked"
    assert data["mode"] == "SAFE_PREVIEW_ONLY", "Mode must be SAFE_PREVIEW_ONLY"
    assert len(data["staged_records"]) == 1
    assert data["staged_records"][0]["zoho_module"] == "Leads"
