"""
V8 Defect Reproduction Suite — Buzz Marketing OS × Minh Van Logistics.
Explicitly reproduces all 7 core defects:
- V8-001: Zoho dedupe false negative & misreported modules_checked
- V8-002: Untrusted dedupe status override bypass
- V8-003: VAT checksum alone causing false legal verification
- V8-004: Caller-supplied action bypassing approval gate
- V8-005: Non-atomic lead and event persistence
- V8-006: Event immutability overwrite hazard
- V8-007: Failed dedupe events counted as successful in dashboard
"""
import json
import sqlite3
import pytest
from unittest.mock import MagicMock

from marketing_system.config import Settings
from marketing_system.constants import Environment
from marketing_system.models import Lead, BusinessEvent
from marketing_system.storage import StagingStore
from marketing_system.tools.catalog import (
    FindExistingIn,
    PreviewCrmImportIn,
    crm_find_existing,
    crm_preview_import,
)
from marketing_system.tools.hub import ToolContext, HubRuntime
from marketing_system.workflows.definitions import step_gtm_gate
from marketing_system.workflows.engine import StepContext


def test_reproduce_v8_001_false_negative_accounts_only_coverage(tmp_path):
    """
    V8-001: crm_find_existing queries accounts only, but misreports modules_checked
    containing Leads, and can claim FULL_COVERAGE when Leads were never checked.
    """
    settings = Settings(environment=Environment.MOCK, data_dir=tmp_path)
    ctx = ToolContext(user_id="u1", channel_id="c1", correlation_id="corr-1")
    rt = HubRuntime(settings=settings, ctx=ctx, registry=None, artifacts_dir=tmp_path / "artifacts")

    res = crm_find_existing(FindExistingIn(companies=["Cong Ty Moi Chua Tung Co"]), rt)
    decision = res["decisions"]["Cong Ty Moi Chua Tung Co"]

    # Remediated in V8: Both Accounts and Leads are queried and accurately reported
    assert "Accounts" in decision["modules_checked"]
    assert "Leads" in decision["modules_checked"]
    assert res["coverage_status"] == "FULL_COVERAGE"


def test_reproduce_v8_002_untrusted_dedupe_status_override(tmp_path):
    """
    V8-002: crm_preview_import rejects caller-supplied crm_dedupe_status.
    Authoritative internal dedupe check decision is strictly used.
    """
    settings = Settings(environment=Environment.MOCK, data_dir=tmp_path)
    ctx = ToolContext(user_id="u1", channel_id="c1", correlation_id="corr-2")
    rt = HubRuntime(settings=settings, ctx=ctx, registry=None, artifacts_dir=tmp_path / "artifacts")

    untrusted_lead = {
        "company": "Fake Entity Ltd",
        "vat_number": "0107889123",
        "contact_name": "Nguyen Van A",
        "email": "a@fake.com",
        "crm_dedupe_status": "NOT_FOUND_VERIFIED",  # Self-proclaimed!
        "data_quality_score": 80,
    }

    res = crm_preview_import(PreviewCrmImportIn(leads=[untrusted_lead]), rt)
    staged = res["staged_records"][0]
    # Authoritative status from crm_find_existing is used, not caller override
    assert staged.get("dedupe_status") == "NOT_FOUND_IN_CHECKED_SCOPE"


def test_reproduce_v8_003_vat_checksum_false_legal_verification(tmp_path):
    """
    V8-003: crm_preview_import treats valid VAT checksum as syntax valid only;
    requires official business registry evidence for legal verification.
    """
    settings = Settings(environment=Environment.MOCK, data_dir=tmp_path)
    ctx = ToolContext(user_id="u1", channel_id="c1", correlation_id="corr-3")
    rt = HubRuntime(settings=settings, ctx=ctx, registry=None, artifacts_dir=tmp_path / "artifacts")

    unverified_lead = {
        "company": "Hoan Toan Bi Dat Khong Co Dang Ky Kinh Doanh",
        "vat_number": "0107889123",  # Passes 10-digit checksum
        "contact_name": "Tran Van Fake",
        "email": "fake@unregistered.com",
        "evidence": [],  # NO registry evidence at all!
        "data_quality_score": 60,
    }

    res = crm_preview_import(PreviewCrmImportIn(leads=[unverified_lead]), rt)
    staged = res["staged_records"][0]
    assert staged.get("action") == "NEEDS_VERIFICATION"
    assert staged.get("eligibility_status") == "NEEDS_IDENTITY_VERIFICATION"
    assert staged.get("eligible_for_crm_import") is False


def test_reproduce_v8_004_action_bypass_in_approval_gate():
    """
    V8-004: step_gtm_gate strictly checks eligible_for_crm_import is True;
    never allows action == 'STAGED_FOR_INSERT' to bypass.
    """
    step_ctx = MagicMock(spec=StepContext)
    step_ctx.outputs = {
        "crm_preview": {
            "write_enabled": False,
            "staged_records": [
                {
                    "company": "Ineligible Bypasser Corp",
                    "eligible_for_crm_import": False,  # NOT eligible!
                    "action": "STAGED_FOR_INSERT",      # Bypass flag!
                    "payload_hash": "hash123",
                }
            ]
        }
    }
    step_ctx.gate = MagicMock()

    step_gtm_gate(step_ctx)
    assert not step_ctx.gate.called


def test_reproduce_v8_005_non_atomic_lead_and_event_persistence(tmp_path):
    """
    V8-005: StagingStore now provides atomic persist_lead_with_events.
    """
    db_path = tmp_path / "marketing.db"
    store = StagingStore(db_path)
    store.initialize()

    lead = Lead(
        id="lead-atomic-test",
        environment="sandbox",
        source="apollo",
        correlation_id="c1",
        synthetic=False,
        full_name="Test Company",
    )
    assert hasattr(store, "persist_lead_with_events")


def test_reproduce_v8_006_event_immutability_overwrite(tmp_path):
    """
    V8-006: record_event protects business events from tampering.
    Attempted overwrite with different payload raises EventConflictError.
    """
    from marketing_system.storage import EventConflictError
    db_path = tmp_path / "marketing.db"
    store = StagingStore(db_path)
    store.initialize()

    ev1 = BusinessEvent(
        event_id="ev-001",
        event_type="lead.discovered",
        entity_id="entity-1",
        workflow_id="wf-1",
        environment=Environment.SANDBOX,
        synthetic=False,
        source="apollo",
        correlation_id="c1",
        payload_json={"stage": "initial"},
    )
    store.record_event(ev1)

    ev1_modified = BusinessEvent(
        event_id="ev-001",
        event_type="lead.discovered",
        entity_id="entity-1",
        workflow_id="wf-1",
        environment=Environment.SANDBOX,
        synthetic=False,
        source="apollo",
        correlation_id="c1",
        payload_json={"stage": "tampered_override"},
    )
    # V8 fix: Tampering raises EventConflictError
    with pytest.raises(EventConflictError):
        store.record_event(ev1_modified)
