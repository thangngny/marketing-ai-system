from datetime import datetime, timedelta, timezone

import pytest

from marketing_system.config import Settings
from marketing_system.constants import Decision, Environment, Impact
from marketing_system.policy import PolicyEngine
from marketing_system.specialists import SPECIALISTS
from marketing_system.workflows.approvals import (
    APPROVED, CONSUMED, EXPIRED, PENDING, REJECTED, ApprovalEngine, BuzzSignedEventVerifier, payload_hash,
)
from marketing_system.workflows.store import WorkflowStore

OWNER = "057f0407663083746eee6457303cead9fe3eec3bbd39a17214d84c52a9080f2f"
AGENT = "b49298c7" + "0" * 56


def decide(tool="crm.create_task", ns="crm", impact=Impact.WRITE_LOW_RISK, who="06_sales_copilot", env=Environment.MOCK,
           dry=True, payload=None, approval=None, enabled=frozenset()):
    return PolicyEngine(enabled).decide(tool=tool, namespace=ns, impact=impact, specialist=SPECIALISTS[who],
                                        environment=env, safe_dry_run=dry,
                                        payload_digest=payload_hash(tool, payload or {"a": 1}), approval=approval)


@pytest.fixture
def engine(tmp_path):
    events: list[dict] = []
    store = WorkflowStore(tmp_path / "wf.db")
    eng = ApprovalEngine(store, [BuzzSignedEventVerifier(OWNER, reader=lambda channel, since: events)])
    eng.events = events  # test handle
    return eng


def request(engine, tool="crm.create_task", payload=None, impact=Impact.WRITE_LOW_RISK, ttl=None):
    return engine.request(tool=tool, target_system="zoho", impact=impact, payload=payload or {"a": 1}, summary="s",
                          requested_by="06_sales_copilot", workflow_id="wf-1", user_id=OWNER, channel_id="chan", ttl=ttl)


def owner_says(engine, text, pubkey=OWNER, delta=5):
    engine.events.append({"id": f"ev{len(engine.events)}", "pubkey": pubkey, "content": text,
                          "created_at": int(datetime.now(timezone.utc).timestamp()) + delta})


# ------------------------------------------------------------------ policy
@pytest.mark.parametrize("impact", [Impact.READ, Impact.DRAFT])
def test_read_and_draft_are_allowed_without_approval(impact):
    assert decide(tool="email.create_draft", ns="email", impact=impact).decision is Decision.ALLOW


def test_specialist_outside_its_namespace_is_denied():
    assert decide(tool="email.create_draft", ns="email", impact=Impact.DRAFT, who="08_kpi_learning").decision is Decision.DENY


def test_write_requires_approval():
    assert decide().decision is Decision.REQUIRE_APPROVAL


def test_high_impact_denied_by_ceiling_for_every_specialist():
    for who in SPECIALISTS:
        assert decide(tool="email.send", ns="email", impact=Impact.HIGH_IMPACT, who=who).decision is Decision.DENY


def test_approved_write_allowed_in_mock_but_denied_by_safe_dry_run_in_production(engine):
    record = request(engine)
    owner_says(engine, f"DUYET {record.code}")
    record = engine.refresh(record.approval_id)
    assert decide(approval=record).decision is Decision.ALLOW
    assert decide(approval=record, env=Environment.PRODUCTION, dry=True).decision is Decision.DENY


def test_changed_payload_invalidates_approval(engine):
    record = request(engine, payload={"a": 1})
    owner_says(engine, f"DUYET {record.code}")
    record = engine.refresh(record.approval_id)
    result = decide(approval=record, payload={"a": 2})
    assert result.decision is Decision.REQUIRE_APPROVAL
    assert "Payload changed" in result.reason


# ------------------------------------------------------------------ approvals
def test_only_owner_signature_approves(engine):
    record = request(engine)
    owner_says(engine, f"DUYET {record.code}", pubkey=AGENT)  # an agent (or LLM) posting the code
    assert engine.refresh(record.approval_id).status == PENDING
    owner_says(engine, f"duyệt {record.code}")
    approved = engine.refresh(record.approval_id)
    assert approved.status == APPROVED and approved.decided_via == "buzz_signed_event" and approved.evidence


def test_owner_can_reject(engine):
    record = request(engine)
    owner_says(engine, f"TUCHOI {record.code}")
    assert engine.refresh(record.approval_id).status == REJECTED


def test_message_before_request_does_not_count(engine):
    record = request(engine)
    owner_says(engine, f"DUYET {record.code}", delta=-3600)
    assert engine.refresh(record.approval_id).status == PENDING


def test_wrong_code_does_not_approve(engine):
    record = request(engine)
    owner_says(engine, "DUYET MV-000000")
    assert engine.refresh(record.approval_id).status == PENDING


def test_expiry(engine):
    record = request(engine, ttl=timedelta(seconds=-1))
    assert engine.refresh(record.approval_id).status == EXPIRED


def test_high_impact_approval_is_single_use(engine):
    record = request(engine, tool="email.send", impact=Impact.HIGH_IMPACT)
    owner_says(engine, f"DUYET {record.code}")
    engine.refresh(record.approval_id)
    assert engine.consume(record.approval_id) is True
    assert engine.consume(record.approval_id) is False
    assert engine.get(record.approval_id).status == CONSUMED
    assert engine.get(record.approval_id).authorizes("email.send", record.payload_hash) is False


def test_verifier_without_reader_key_is_unavailable(monkeypatch):
    monkeypatch.setattr("marketing_system.workflows.approvals._reader_key", lambda: None)
    assert BuzzSignedEventVerifier(OWNER).available() is False


def test_settings_carry_owner_pubkey():
    assert Settings().owner_pubkey == OWNER
