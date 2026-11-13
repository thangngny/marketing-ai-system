"""
V5 Acceptance Invariants Test Suite (Mega Prompt V5).
Verifies:
1. Wave 1: Separated VerificationReport buckets (raw, format_valid, observed, corroborated, verified, inferred, conflicted).
   Format-valid VAT & observed legal name NEVER placed into verified_fields.
   Overall status is VERIFIED only if authoritative verification succeeded.
2. Wave 2: crm_dedupe_status multi-state ('NOT_CHECKED', 'CHECK_FAILED', 'POSSIBLE_DUPLICATE', 'DUPLICATE_CONFIRMED', 'NOT_FOUND_VERIFIED').
   Tier 1 strictly requires 'NOT_FOUND_VERIFIED' and in_crm=False.
   DiscoveryResult records post-execution provider statuses ('SUCCESS', 'SUCCESS_EMPTY', 'NOT_CONFIGURED', etc.).
3. Wave 4: Dashboard true metrics querying from marketing.db (no synthetic wf_count * 5, 150M multipliers).
   Dashboard security & portable paths.
"""
import os
import re
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from marketing_system.constants import Environment
from marketing_system.models import LeadCandidate, EvidenceStatus
from marketing_system.lead_engine.verifier import LeadVerifier, validate_vietnam_vat, check_domain_mx
from marketing_system.lead_engine.scorer import TwoAxisScorer
from marketing_system.lead_engine.discovery import (
    DynamicDiscoveryEngine,
    DiscoveryFilter,
    ApolloDiscoveryProvider,
    TradeManifestDiscoveryProvider,
    MockDiscoveryProvider,
)
from conftest import get_sibling_workspace_path


def test_v5_wave1_separated_verification_fields_and_no_false_verified():
    verifier = LeadVerifier(check_live_dns=False)
    candidate = LeadCandidate(
        company="Công ty Cổ phần Công nghệ ABC",
        vat_number="0107889123",  # Valid checksum and province
        domain="abctech.vn",
        contact_name="Nguyễn Văn A",
        email="a.nguyen@abctech.vn",
        source="apollo",
        environment=Environment.PRODUCTION,
    )
    report = verifier.verify_candidate(candidate)

    # 1. Separated fields existence
    assert hasattr(report, "raw_fields")
    assert hasattr(report, "format_valid_fields")
    assert hasattr(report, "observed_fields")
    assert hasattr(report, "corroborated_fields")
    assert hasattr(report, "verified_fields")
    assert hasattr(report, "inferred_fields")
    assert hasattr(report, "conflicted_fields")

    # 2. Syntax valid VAT must NOT be in verified_fields without authoritative registry check
    assert "vat_number" in report.format_valid_fields
    assert "vat_number" not in report.verified_fields

    # 3. Observed company name must NOT be in verified_fields
    assert "legal_name" in report.observed_fields
    assert "legal_name" not in report.verified_fields

    # 4. Overall status must NOT be VERIFIED
    assert report.status != "VERIFIED"
    assert report.status in ("FORMAT_VALID", "SOURCE_OBSERVED")


def test_v5_wave1_authoritative_registry_confirmation_grants_verified_status():
    mock_registry = MagicMock()
    mock_registry.check_active_business.return_value = (True, "CÔNG TY CỔ PHẦN CÔNG NGHỆ ABC")
    verifier = LeadVerifier(check_live_dns=False, registry_client=mock_registry)

    candidate = LeadCandidate(
        company="Công ty Cổ phần Công nghệ ABC",
        vat_number="0107889123",
        domain="abctech.vn",
        source="apollo",
        environment=Environment.PRODUCTION,
    )
    report = verifier.verify_candidate(candidate)

    assert report.status == "VERIFIED"
    assert "vat_number" in report.verified_fields
    assert "legal_name" in report.verified_fields


def test_v5_wave2_crm_dedupe_status_controls_tier1():
    scorer = TwoAxisScorer()
    
    # Candidate with good data and commercial fit
    candidate = LeadCandidate(
        company="Công ty TNHH Thiết bị Y tế Chuyên Dụng Tâm An",
        vat_number="0107889123",
        domain="tamanmedical.com.vn",
        contact_name="Nguyễn Văn Hùng",
        title="Trưởng phòng Mua hàng",
        email="hung.nv@tamanmedical.com.vn",
        phone="0912345671",
        registered_address="Tầng 5 Charmvit Tower, Cầu Giấy, Hà Nội",
        industry_code="3250",
        source="apollo",
        environment=Environment.MOCK,
    )
    # Add valid evidence items
    candidate.add_evidence("vat_number", candidate.vat_number, "tax_rules", EvidenceStatus.FORMAT_VALID)
    candidate.add_evidence("legal_name", candidate.company, "apollo", EvidenceStatus.SOURCE_OBSERVED)
    candidate.add_evidence("domain_active", candidate.domain, "dns", EvidenceStatus.FORMAT_VALID)
    candidate.add_evidence("air_cargo_flow", {"route": "JP-HAN", "est_monthly_kg": 1500}, "manifest", EvidenceStatus.INFERRED)

    # 1. NOT_CHECKED blocks Tier 1
    candidate.crm_dedupe_status = "NOT_CHECKED"
    sc1 = scorer.score_candidate(candidate)
    assert sc1.tier != "Tier 1 - High Priority"

    # 2. CHECK_FAILED blocks Tier 1
    candidate.crm_dedupe_status = "CHECK_FAILED"
    sc2 = scorer.score_candidate(candidate)
    assert sc2.tier != "Tier 1 - High Priority"

    # 3. POSSIBLE_DUPLICATE blocks Tier 1
    candidate.crm_dedupe_status = "POSSIBLE_DUPLICATE"
    sc3 = scorer.score_candidate(candidate)
    assert sc3.tier != "Tier 1 - High Priority"

    # 4. DUPLICATE_CONFIRMED blocks Tier 1
    candidate.crm_dedupe_status = "DUPLICATE_CONFIRMED"
    sc4 = scorer.score_candidate(candidate)
    assert sc4.tier != "Tier 1 - High Priority"

    # 5. NOT_FOUND_VERIFIED enables Tier 1 (requires corroborating EvidenceItem per FND-V6-009)
    candidate.crm_dedupe_status = "NOT_FOUND_VERIFIED"
    candidate.in_crm = False
    candidate.add_evidence("crm_dedupe", {"status": "NOT_FOUND_VERIFIED"}, "zoho_dedupe", EvidenceStatus.SOURCE_CORROBORATED, confidence=0.95)
    sc5 = scorer.score_candidate(candidate)
    assert sc5.tier == "Tier 1 - High Priority"


def test_v5_wave2_discovery_source_statuses_post_execution():
    mock_apollo = MagicMock()
    mock_apollo.configured.return_value = True
    mock_apollo.search_people.return_value = []  # Empty results

    provider = ApolloDiscoveryProvider(apollo_connector=mock_apollo)
    engine = DynamicDiscoveryEngine(providers=[provider])
    
    filt = DiscoveryFilter(limit=5)
    res = engine.discover_candidates(filt, env=Environment.PRODUCTION)
    
    assert res.total_discovered == 0
    assert "apollo" in res.source_statuses
    assert res.source_statuses["apollo"] == "SUCCESS_EMPTY"


def test_v5_wave4_dashboard_no_synthetic_multipliers():
    dashboard_path = get_sibling_workspace_path("buzz-ai-usage-center/bin/dashboard.py")
    if not dashboard_path or not dashboard_path.exists():
        pytest.skip("dashboard.py not found in sibling workspace")

    content = dashboard_path.read_text(encoding="utf-8")
    
    # Verify synthetic multiplier formulas were permanently deleted
    assert "wf_count * 5" not in content, "Violation: synthetic wf_count * 5 multiplier detected"
    assert "wf_count * 4" not in content, "Violation: synthetic wf_count * 4 multiplier detected"
    assert "wf_count * 3" not in content, "Violation: synthetic wf_count * 3 multiplier detected"
    assert "staged_cnt * 150" not in content, "Violation: synthetic staged_cnt * 150M detected"
    assert "staged_cnt * 1.5" not in content, "Violation: synthetic staged_cnt * 1.5 tons detected"

    # Verify portable paths
    assert 'r"C:\\Users\\Admin' not in content, "Violation: hardcoded Admin path detected"
