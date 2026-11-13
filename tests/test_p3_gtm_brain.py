"""
Tests for P3: GTM Brain Knowledge Hub & 12 Standardized Skills.
"""
import pytest
from marketing_system.gtm_brain import GTMBrainEngine, BRAIN_DIR


def test_gtm_brain_index_and_skills_count():
    brain = GTMBrainEngine()
    skills = brain.list_skills()
    assert len(skills) == 12
    assert "01_research_market.md" in skills
    assert "03_verify_company.md" in skills
    assert "10_prepare_sales_handoff.md" in skills
    assert "12_propose_brain_update.md" in skills


def test_gtm_brain_query_medical_icp():
    brain = GTMBrainEngine()
    snippets = brain.query("thiết bị y tế 3250", category="icp", limit=2)
    assert len(snippets) > 0
    first = snippets[0]
    assert first.category == "icp"
    assert "3250" in first.content
    assert "y tế" in first.content.lower()


def test_gtm_brain_service_lookup():
    brain = GTMBrainEngine()
    service_text = brain.get_service_info("hàng không air freight")
    assert service_text is not None
    assert "HAN" in service_text or "SGN" in service_text or "NRT" in service_text


def test_gtm_brain_outreach_policy():
    brain = GTMBrainEngine()
    policy = brain.get_outreach_policy()
    assert policy is not None
    assert "91/2020/NĐ-CP" in policy
    assert "Opt-out" in policy or "từ chối" in policy.lower()
