"""Approval engine.

Invariant: nothing reachable by the LLM can set an approval to APPROVED.
Only an ApprovalVerifier can, and each verifier reads evidence the LLM cannot
forge (an owner-signed Buzz event, or an interactive local console).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Protocol
from uuid import uuid4

from pydantic import BaseModel

from ..constants import Impact
from .store import WorkflowStore, utcnow

PENDING, APPROVED, REJECTED, EXPIRED, CANCELLED, CONSUMED = (
    "PENDING", "APPROVED", "REJECTED", "EXPIRED", "CANCELLED", "CONSUMED")

DEFAULT_TTL = {Impact.WRITE_LOW_RISK: timedelta(hours=24), Impact.HIGH_IMPACT: timedelta(hours=4)}


def payload_hash(tool: str, payload: Any) -> str:
    canonical = json.dumps({"tool": tool, "payload": payload}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ApprovalRecord(BaseModel):
    approval_id: str
    code: str
    workflow_id: str | None
    requested_action: str
    target_system: str
    impact: str
    payload_hash: str
    payload_summary: str
    requested_by_agent: str
    requested_for_user: str | None = None
    channel_id: str | None = None
    status: str
    created_at: str
    expires_at: str
    decided_at: str | None = None
    decided_by: str | None = None
    decided_via: str | None = None
    evidence: str | None = None
    consumed_at: str | None = None

    def expired(self, now: datetime | None = None) -> bool:
        return (now or datetime.now(timezone.utc)) >= datetime.fromisoformat(self.expires_at)

    def authorizes(self, tool: str, digest: str, now: datetime | None = None) -> bool:
        """Bound to the exact action: same tool, same payload hash, not expired, not used."""
        return (
            self.status == APPROVED
            and self.requested_action == tool
            and self.payload_hash == digest
            and not self.expired(now)
        )


class Verdict(BaseModel):
    status: str  # APPROVED | REJECTED
    actor: str
    via: str
    evidence: str


class ApprovalVerifier(Protocol):
    name: str

    def available(self) -> bool: ...

    def verify(self, record: ApprovalRecord) -> Verdict | None: ...


# ---------------------------------------------------------------------------
# Buzz: owner-signed message "DUYET <code>" / "TUCHOI <code>" in the workflow channel.
# ---------------------------------------------------------------------------
EventReader = Callable[[str, int], list[dict[str, Any]]]

_APPROVE = r"(?:DUYET|DUYỆT|APPROVE)"
_REJECT = r"(?:TUCHOI|TỪ\s*CHỐI|TU\s*CHOI|REJECT)"


class BuzzSignedEventVerifier:
    name = "buzz_signed_event"

    def __init__(self, owner_pubkey: str, reader: EventReader | None = None):
        self.owner_pubkey = owner_pubkey.lower()
        self._reader = reader

    def available(self) -> bool:
        return self._reader is not None or _reader_key() is not None

    def verify(self, record: ApprovalRecord) -> Verdict | None:
        if not record.channel_id:
            return None
        reader = self._reader or _buzz_cli_reader
        since = int(datetime.fromisoformat(record.created_at).timestamp())
        try:
            events = reader(record.channel_id, since)
        except Exception:
            return None
        code = re.escape(record.code)
        approve = re.compile(rf"\b{_APPROVE}\s+{code}\b", re.I)
        reject = re.compile(rf"\b{_REJECT}\s+{code}\b", re.I)
        for event in sorted(events, key=lambda e: int(e.get("created_at", 0))):
            if str(event.get("pubkey", "")).lower() != self.owner_pubkey:
                continue  # only the owner's signature counts; agents and other members are ignored
            if int(event.get("created_at", 0)) < since:
                continue
            content = str(event.get("content", ""))
            if reject.search(content):
                return Verdict(status=REJECTED, actor=self.owner_pubkey, via=self.name, evidence=str(event.get("id")))
            if approve.search(content):
                return Verdict(status=APPROVED, actor=self.owner_pubkey, via=self.name, evidence=str(event.get("id")))
        return None


def _reader_key() -> str | None:
    from ..credentials import read_credential

    try:
        return read_credential("BUZZ_APPROVAL_READER_KEY")
    except Exception:
        return None


def _buzz_cli_reader(channel_id: str, since: int) -> list[dict[str, Any]]:
    key = _reader_key()
    if not key:
        raise RuntimeError("BUZZ_APPROVAL_READER_KEY missing")
    cli = os.getenv("BUZZ_CLI_PATH", r"D:\Buzz\buzz.exe")
    relay = os.getenv("BUZZ_RELAY_URL", "https://phamgianam.communities.buzz.xyz")
    env = {**os.environ, "BUZZ_PRIVATE_KEY": key, "BUZZ_RELAY_URL": relay}  # env, never argv
    done = subprocess.run([cli, "messages", "get", "--channel", channel_id, "--since", str(since), "--limit", "200"],
                          capture_output=True, timeout=30, env=env, stdin=subprocess.DEVNULL, check=False)
    if done.returncode != 0:
        raise RuntimeError(f"buzz messages get exit {done.returncode}")
    body = json.loads(done.stdout.decode("utf-8", errors="replace") or "[]")
    if isinstance(body, dict):
        body = body.get("messages") or body.get("events") or body.get("data") or []
    return [e for e in body if isinstance(e, dict)]


# ---------------------------------------------------------------------------
class ApprovalEngine:
    def __init__(self, store: WorkflowStore, verifiers: list[ApprovalVerifier] | None = None):
        self.store = store
        self.verifiers = verifiers or []

    def request(self, *, tool: str, target_system: str, impact: Impact, payload: Any, summary: str,
                requested_by: str, workflow_id: str | None, user_id: str | None, channel_id: str | None,
                ttl: timedelta | None = None) -> ApprovalRecord:
        now = datetime.now(timezone.utc)
        record = ApprovalRecord(
            approval_id=str(uuid4()),
            code="MV-" + secrets.token_hex(3).upper(),
            workflow_id=workflow_id,
            requested_action=tool,
            target_system=target_system,
            impact=str(impact),
            payload_hash=payload_hash(tool, payload),
            payload_summary=summary[:2000],
            requested_by_agent=requested_by,
            requested_for_user=user_id,
            channel_id=channel_id,
            status=PENDING,
            created_at=now.isoformat(),
            expires_at=(now + (ttl or DEFAULT_TTL.get(impact, timedelta(hours=24)))).isoformat(),
        )
        self.store.insert_approval(record.model_dump())
        return record

    def get(self, approval_id: str) -> ApprovalRecord | None:
        row = self.store.get_approval(approval_id)
        return ApprovalRecord(**row) if row else None

    def refresh(self, approval_id: str) -> ApprovalRecord | None:
        """Expire or verify a pending approval. Safe for the LLM to call: it can only *ask*."""
        record = self.get(approval_id)
        if not record or record.status != PENDING:
            return record
        if record.expired():
            self.store.update_approval(record.approval_id, PENDING, status=EXPIRED, decided_at=utcnow(), decided_via="ttl")
            return self.get(approval_id)
        for verifier in self.verifiers:
            if not verifier.available():
                continue
            verdict = verifier.verify(record)
            if verdict:
                self._decide(record, verdict)
                break
        return self.get(approval_id)

    def decide_locally(self, approval_id: str, approve: bool, operator: str) -> ApprovalRecord:
        """Interactive console path only (see cli.approvals). Never exposed over MCP."""
        record = self.get(approval_id)
        if not record or record.status != PENDING:
            raise ValueError("Approval is not pending")
        if record.expired():
            self.refresh(approval_id)
            raise ValueError("Approval expired")
        self._decide(record, Verdict(status=APPROVED if approve else REJECTED, actor=operator,
                                     via="local_console", evidence="interactive-tty"))
        return self.get(approval_id)  # type: ignore[return-value]

    def consume(self, approval_id: str) -> bool:
        """HIGH_IMPACT approvals are single-use."""
        return self.store.update_approval(approval_id, APPROVED, status=CONSUMED, consumed_at=utcnow())

    def cancel(self, approval_id: str) -> bool:
        return self.store.update_approval(approval_id, PENDING, status=CANCELLED, decided_at=utcnow(), decided_via="system")

    def _decide(self, record: ApprovalRecord, verdict: Verdict) -> None:
        self.store.update_approval(record.approval_id, PENDING, status=verdict.status, decided_at=utcnow(),
                                   decided_by=verdict.actor, decided_via=verdict.via, evidence=verdict.evidence)
