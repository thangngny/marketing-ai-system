"""
Tests for P1: Dynamic Multi-Source Lead Discovery, Evidence Verification, and Two-Axis Scoring.
"""
import pytest
from marketing_system.constants import Environment
from marketing_system.models import LeadCandidate
from marketing_system.lead_engine.discovery import (
    DynamicDiscoveryEngine,
    DiscoveryFilter,
    ApolloDiscoveryProvider,
    TradeManifestDiscoveryProvider,
)
from marketing_system.lead_engine.verifier import (
    LeadVerifier,
    validate_vietnam_vat,
    check_domain_mx,
)
from marketing_system.lead_engine.scorer import TwoAxisScorer


def test_vat_validation():
    # Valid 10-digit
    ok, res = validate_vietnam_vat("0107889123")
    assert ok is True
    assert res == "0107889123"

    # Valid 13-digit branch
    ok, res = validate_vietnam_vat("0107889123-001")
    assert ok is True
    assert res == "0107889123001"

    # Invalid: non-digit or wrong length
    ok, err = validate_vietnam_vat("12345")
    assert ok is False

    # Invalid: repeated digits
    ok, err = validate_vietnam_vat("0000000000")
    assert ok is False


def test_domain_mx_syntax():
    ok, _ = check_domain_mx("minhvanlogistics.com")
    assert ok is True

    # Disposable rejection
    ok, err = check_domain_mx("tempmail.com")
    assert ok is False
    assert "disposable" in err.lower()


def test_discovery_engine_multisource():
    engine = DynamicDiscoveryEngine()
    filt = DiscoveryFilter(limit=5)
    res = engine.discover_candidates(filt, env=Environment.MOCK)

    assert res.total_discovered >= 2
    assert "apollo" in res.sources_used
    assert "trade_manifest" in res.sources_used
    assert len(res.candidates) > 0


def test_lead_verifier_and_scorer_pipeline():
    verifier = LeadVerifier(check_live_dns=False)
    scorer = TwoAxisScorer()

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
        environment=Environment.MOCK,
    )

    # 1. Verification
    report = verifier.verify_candidate(candidate)
    assert report.is_valid_lead is True
    assert "vat_number" in report.verified_fields
    assert "legal_name" in report.verified_fields
    assert "logistics_classification" in report.inferred_fields

    # 2. Scoring
    score_card = scorer.score_candidate(candidate)
    assert score_card.data_quality_score >= 80
    assert score_card.commercial_fit_score >= 70
    assert score_card.composite_score >= 75
    assert score_card.tier == "Tier 1 - High Priority"
    assert candidate.stage == "READY_FOR_REVIEW"
    assert "industry_icp_alignment" in score_card.breakdown


def test_disqualified_invalid_lead():
    verifier = LeadVerifier()
    scorer = TwoAxisScorer()

    candidate = LeadCandidate(
        company="Unknown Shop",
        vat_number="invalid_123",
        source="web",
        environment=Environment.MOCK,
    )

    report = verifier.verify_candidate(candidate)
    assert report.is_valid_lead is False

    score_card = scorer.score_candidate(candidate)
    assert score_card.composite_score < 40
    assert score_card.tier == "Disqualified"
