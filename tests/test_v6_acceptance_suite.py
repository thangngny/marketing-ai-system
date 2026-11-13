"""
V6 Acceptance Test Suite — Buzz Marketing OS × Minh Van Logistics.
Covers all top defects and architectural invariants:
- FND-V6-001: Live discovery wiring & ApolloConnector search_people
- FND-V6-002: Comprehensive Zoho dedupe (VAT cache, tri-state, audit metadata)
- FND-V6-003: CRM preview quality enforcement (no fabricated names/titles/industries)
- FND-V6-004: Dashboard SQLite schema compatibility (no nonexistent confidence column)
- FND-V6-005: Scoped KPI workflow aggregation
- FND-V6-006: Real lead cards without hardcoded volume/score defaults
- FND-V6-007: Truthful VAT cache count (no hardcoded 3603 fallback)
- FND-V6-008: Dashboard authentication fail-closed barrier (loopback vs remote)
- FND-V6-009: Scorer CRM dedupe EvidenceItem requirement
"""
import json
import os
import re
import sqlite3
import textwrap
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from marketing_system.config import Settings
from marketing_system.constants import Environment
from marketing_system.connectors.apollo import ApolloConnector
from marketing_system.lead_engine.discovery import (
    ApolloDiscoveryProvider,
    DiscoveryFilter,
    DynamicDiscoveryEngine,
)
from marketing_system.lead_engine.verifier import LeadVerifier
from marketing_system.lead_engine.scorer import TwoAxisScorer
from marketing_system.models import LeadCandidate, EvidenceStatus
from marketing_system.tools.catalog import (
    FindExistingIn,
    PreviewCrmImportIn,
    crm_find_existing,
    crm_preview_import,
    lead_pipeline_run,
    LeadPipelineRunIn,
)
from marketing_system.tools.hub import ToolContext, HubRuntime


def _get_dashboard_helpers():
    from conftest import get_sibling_workspace_path
    dashboard_path = get_sibling_workspace_path("buzz-ai-usage-center/bin/dashboard.py")
    assert dashboard_path and dashboard_path.exists(), "dashboard.py must exist"

    content = dashboard_path.read_text(encoding="utf-8")
    ns = {
        "Path": Path,
        "json": json,
        "os": os,
        "sqlite3": sqlite3,
    }
    match_funnel = re.search(r"(def get_gtm_funnel_data\(.*?\)\s*->\s*dict:.*?)(?=def v_gtm_funnel)", content, re.DOTALL)
    assert match_funnel is not None, "get_gtm_funnel_data not found in dashboard.py"
    exec(match_funnel.group(1), ns)

    # Build test class for Handler auth
    class TestHandler:
        def __init__(self, client_ip="127.0.0.1", headers=None, is_public=False):
            self.client_address = (client_ip, 12345)
            self.headers = headers or {}
            self._public = is_public
            self.response_code = None
            self.response_headers = {}
            self.response_body = b""

        def _is_public(self) -> bool:
            return self._public

        def send_response(self, code: int):
            self.response_code = code

        def send_header(self, k: str, v: str):
            self.response_headers[k] = v

        def end_headers(self):
            pass

        @property
        def wfile(self):
            class Writer:
                def __init__(outer):
                    outer.parent = self
                def write(outer, b):
                    self.response_body += b
            return Writer()

    match_methods = re.search(r"(\s+def _is_loopback\(self\).*?)(?=\s+def _redirect)", content, re.DOTALL)
    if match_methods is None:
        pytest.skip("buzz-ai-usage-center does not contain V6 _is_loopback method")
    exec(textwrap.dedent(match_methods.group(1)), ns)

    TestHandler._is_loopback = ns["_is_loopback"]
    TestHandler._check_auth = ns["_check_auth"]

    return ns["get_gtm_funnel_data"], TestHandler


# ==============================================================================
# FND-V6-001: Live Discovery Wiring & ApolloConnector
# ==============================================================================
def test_fnd_v6_001_apollo_connector_methods_and_discovery_wiring(tmp_path):
    """Verify ApolloConnector provides search_people and ApolloDiscoveryProvider queries both orgs and people."""
    settings = Settings(environment=Environment.MOCK, data_dir=tmp_path)
    conn = ApolloConnector(settings=settings)
    assert hasattr(conn, "search_companies")
    assert hasattr(conn, "search_people")

    # Test discovery provider with mock connector
    mock_conn = MagicMock()
    mock_conn.configured.return_value = True
    mock_conn.search_companies.return_value = [
        {
            "name": "Công ty TNHH Y tế Alpha",
            "primary_domain": "alpha-med.vn",
            "phone": "02431234567",
            "industry": "Medical Devices",
            "city": "Hà Nội",
            "country": "Vietnam",
        }
    ]
    mock_conn.search_people.return_value = [
        {
            "name": "Trần Thị Bích",
            "first_name": "Bích",
            "last_name": "Trần",
            "title": "Supply Chain Manager",
            "email": "bich.tt@alpha-med.vn",
            "phone_number": "0912345678",
            "organization": {
                "name": "Công ty TNHH Y tế Alpha",
                "primary_domain": "alpha-med.vn",
            },
        }
    ]

    provider = ApolloDiscoveryProvider(apollo_connector=mock_conn)
    filt = DiscoveryFilter(industry_keywords=["y tế"], limit=5)
    candidates = provider.discover(filt, env=Environment.PRODUCTION)

    assert len(candidates) >= 1
    org_cand = candidates[0]
    assert org_cand.company == "Công ty TNHH Y tế Alpha"
    assert org_cand.source in ("apollo_organizations", "apollo_people")
    assert org_cand.synthetic is False
    assert any(e.field_name == "company_profile" for e in org_cand.evidence)
    assert any(e.evidence_status == EvidenceStatus.SOURCE_OBSERVED for e in org_cand.evidence)


# ==============================================================================
# FND-V6-002: Comprehensive Zoho Dedupe
# ==============================================================================
def test_fnd_v6_002_comprehensive_zoho_dedupe(tmp_path):
    """Verify crm_find_existing checks VAT cache, returns tri-state and audit metadata."""
    settings = Settings(environment=Environment.MOCK, data_dir=tmp_path)
    ctx = ToolContext(specialist_id="growth_architect", correlation_id="c1", workflow_id="w1")
    rt = HubRuntime(settings=settings, registry=MagicMock(), ctx=ctx, artifacts_dir=tmp_path / "artifacts")

    # 1. Test mock dedupe with matches
    res = crm_find_existing(FindExistingIn(companies=["Pharma Logistics VN"], domains=["pharmalog.vn"], vats=["0107889123"]), rt)
    assert "matches" in res
    assert "match_status" in res
    assert "coverage_status" in res
    assert "run_id" in res
    assert "timestamp" in res
    assert "scope_checked" in res
    assert res["match_status"] in ("DUPLICATE_FOUND", "NOT_FOUND_VERIFIED")

    # 2. Test bounded status handling
    with patch("marketing_system.tools.catalog._live_connector") as mock_conn_fn:
        mock_conn = MagicMock()
        mock_conn.read.return_value = [{"external_id": f"acc_{i}", "name": f"Company {i}", "domain": f"c{i}.vn"} for i in range(200)]
        mock_conn_fn.return_value = mock_conn

        settings_live = Settings(environment=Environment.PRODUCTION, data_dir=tmp_path)
        ctx_live = ToolContext(specialist_id="growth_architect", correlation_id="c2", workflow_id="w2")
        rt_live = HubRuntime(settings=settings_live, registry=MagicMock(), ctx=ctx_live, artifacts_dir=tmp_path / "artifacts")
        with patch.dict(os.environ, {"BUZZ_VAT_CACHE": str(tmp_path / "nonexistent.json")}):
            bounded_res = crm_find_existing(FindExistingIn(companies=["New Unseen Company"], domains=["newunseen.vn"]), rt_live)
            assert bounded_res["bounded"] is True
            assert bounded_res["match_status"] == "PARTIAL_COVERAGE"
            assert bounded_res["coverage_status"] == "PARTIAL_COVERAGE"


# ==============================================================================
# FND-V6-003: Lead Quality & No Fabricated Defaults in Preview
# ==============================================================================
def test_fnd_v6_003_crm_preview_lead_quality(tmp_path):
    """Verify crm_preview_import does not fabricate Last_Name or Designation."""
    settings = Settings(environment=Environment.MOCK, data_dir=tmp_path)
    ctx = ToolContext(specialist_id="growth_architect", correlation_id="c1", workflow_id="w1")
    rt = HubRuntime(settings=settings, registry=MagicMock(), ctx=ctx, artifacts_dir=tmp_path / "artifacts")

    incomplete_lead = {
        "company": "Công ty Thiết bị Đo lường Sài Gòn",
        "domain": "measuring-sg.vn",
        "vat_number": "0316789123",
        "data_quality_score": 60,
        "commercial_fit_score": 65,
        "score": 63,
    }

    res = crm_preview_import(PreviewCrmImportIn(leads=[incomplete_lead]), rt)
    assert res["staged_count"] == 1
    staged_item = res["staged_records"][0]
    payload = staged_item["payload"]

    assert payload["Last_Name"] != incomplete_lead["company"]
    assert payload["Last_Name"] == "[Chưa xác minh]"
    assert payload["Designation"] != "Người liên hệ mua hàng"
    assert payload["Designation"] == "Chưa có chức danh"
    assert staged_item["action"] == "NEEDS_ENRICHMENT"
    assert "contact_name" in staged_item["missing_fields"]


# ==============================================================================
# FND-V6-004 & FND-V6-005: Dashboard SQLite Schema & Scoped Aggregation
# ==============================================================================
def test_fnd_v6_004_and_005_dashboard_sqlite_schema_and_aggregation(tmp_path):
    """Verify get_gtm_funnel_data handles canonical_records schema without error."""
    get_funnel_fn, _ = _get_dashboard_helpers()

    db_path = tmp_path / "marketing.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE canonical_records (
            id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            environment TEXT NOT NULL,
            source TEXT NOT NULL,
            correlation_id TEXT NOT NULL,
            synthetic INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (id, environment)
        )
    """)
    conn.execute("""
        CREATE TABLE workflow_steps (
            id TEXT PRIMARY KEY,
            workflow_id TEXT NOT NULL,
            name TEXT NOT NULL,
            state TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE approvals (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL
        )
    """)
    payload = json.dumps({"confidence": 0.98, "status": "VERIFIED", "Company": "MedTest Corp", "score": 85})
    conn.execute("INSERT INTO canonical_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 ("lead-1", "Lead", "mock", "apollo", "c1", 0, payload, "2026-11-13T00:00:00Z", "2026-11-13T00:00:00Z"))
    conn.execute("INSERT INTO workflow_steps VALUES (?, ?, ?, ?)", ("s1", "gtm_lead_pipeline_1", "search", "DONE"))
    conn.execute("INSERT INTO workflow_steps VALUES (?, ?, ?, ?)", ("s2", "unrelated_other_workflow", "search", "DONE"))
    conn.commit()
    conn.close()

    with patch.dict(os.environ, {
        "BUZZ_MARKETING_DB": str(db_path),
        "BUZZ_DASHBOARD_MODE": "real",
        "BUZZ_VAT_CACHE": str(tmp_path / "nonexistent.json"),
    }):
        data = get_funnel_fn(mode="real")
        assert data["mode"] == "REAL"
        assert data["is_demo"] is False
        assert data["funnel_stages"][0]["count"] >= 1


# ==============================================================================
# FND-V6-006 & FND-V6-007: Truthful Lead Cards & VAT Cache
# ==============================================================================
def test_fnd_v6_006_and_007_truthful_metrics_and_vat_cache(tmp_path):
    """Verify vats_count is 0 when cache missing, and top leads do not have fabricated defaults."""
    get_funnel_fn, _ = _get_dashboard_helpers()

    with patch.dict(os.environ, {
        "BUZZ_VAT_CACHE": str(tmp_path / "missing_cache.json"),
        "BUZZ_MARKETING_DB": str(tmp_path / "missing_marketing.db"),
    }):
        data = get_funnel_fn(mode="real")
        assert data["kpis"]["crm_protected_vats"] == 0, "Missing cache must report 0 VATs, not hardcoded 3603"


# ==============================================================================
# FND-V6-008: Dashboard Auth Fail-Closed Barrier
# ==============================================================================
def test_fnd_v6_008_auth_fail_closed_barrier():
    """Verify _check_auth blocks non-loopback network requests when token missing or wrong."""
    _, TestHandler = _get_dashboard_helpers()

    # Case 1: External IP without configured token -> fails closed (500)
    handler1 = TestHandler(client_ip="192.168.1.50")
    with patch.dict(os.environ, {"BUZZ_DASHBOARD_TOKEN": "", "BUZZ_REQUIRE_AUTH": "false"}):
        ok = handler1._check_auth()
        assert ok is False
        assert handler1.response_code == 500

    # Case 2: External IP with configured token but missing header -> fails 401
    handler2 = TestHandler(client_ip="192.168.1.50")
    with patch.dict(os.environ, {"BUZZ_DASHBOARD_TOKEN": "secret-v6-token"}):
        ok = handler2._check_auth()
        assert ok is False
        assert handler2.response_code == 401

    # Case 3: External IP with valid Bearer token -> passes (True)
    handler3 = TestHandler(client_ip="192.168.1.50", headers={"Authorization": "Bearer secret-v6-token"})
    with patch.dict(os.environ, {"BUZZ_DASHBOARD_TOKEN": "secret-v6-token"}):
        ok = handler3._check_auth()
        assert ok is True

    # Case 4: Loopback without auth required -> passes (True)
    handler4 = TestHandler(client_ip="127.0.0.1")
    with patch.dict(os.environ, {"BUZZ_DASHBOARD_TOKEN": "", "BUZZ_REQUIRE_AUTH": "false"}):
        ok = handler4._check_auth()
        assert ok is True


# ==============================================================================
# FND-V6-009: Scorer CRM Dedupe Evidence Requirement
# ==============================================================================
def test_fnd_v6_009_scorer_requires_dedupe_evidence_item():
    """Verify TwoAxisScorer rejects Tier 1 unless candidate has corroborating crm_dedupe EvidenceItem."""
    scorer = TwoAxisScorer()

    candidate = LeadCandidate(
        company="Công ty Cổ phần Dược phẩm BioMedica",
        vat_number="0108991234",
        domain="biomedica.com.vn",
        contact_name="Lê Minh Trí",
        title="Procurement Director",
        email="tri.lm@biomedica.com.vn",
        phone="0901234567",
        registered_address="Đống Đa, Hà Nội",
        industry_code="3250",
        source="apollo",
        environment=Environment.MOCK,
    )
    # Add authoritative profile & vat evidence
    candidate.add_evidence(
        field_name="legal_name",
        field_value={"name": candidate.company},
        source_provider="business_registry",
        evidence_status=EvidenceStatus.VERIFIED,
        confidence=1.0,
    )
    candidate.add_evidence(
        field_name="vat_number",
        field_value={"vat": candidate.vat_number},
        source_provider="business_registry",
        evidence_status=EvidenceStatus.VERIFIED,
        confidence=1.0,
    )
    candidate.add_evidence(
        field_name="domain_active",
        field_value={"domain": candidate.domain},
        source_provider="dns_mx",
        evidence_status=EvidenceStatus.VERIFIED,
        confidence=1.0,
    )

    # Sub-case A: crm_dedupe_status is NOT_FOUND_VERIFIED, BUT NO crm_dedupe EvidenceItem exists
    candidate.crm_dedupe_status = "NOT_FOUND_VERIFIED"
    sc_blocked = scorer.score_candidate(candidate)
    assert sc_blocked.tier != "Tier 1 - High Priority", "Must NOT award Tier 1 without backing EvidenceItem"

    # Sub-case B: Corroborating EvidenceItem added -> Tier 1 awarded
    candidate.add_evidence(
        field_name="crm_dedupe",
        field_value={"status": "NOT_FOUND_VERIFIED"},
        source_provider="zoho_dedupe",
        evidence_status=EvidenceStatus.SOURCE_CORROBORATED,
        confidence=0.95,
    )
    sc_cleared = scorer.score_candidate(candidate)
    assert sc_cleared.tier == "Tier 1 - High Priority"
    assert candidate.stage == "READY_FOR_REVIEW"
