from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .constants import Environment
from .models import BaseEntity, BusinessEvent, TrustedLegalVerificationDecision


class EventConflictError(ValueError):
    """Raised when an attempt is made to overwrite an immutable business event with different payload."""
    pass


class StagingStore:
    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        # Enable WAL mode for high concurrency read/write safety
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    def initialize(self) -> None:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS canonical_records (
                    id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    environment TEXT NOT NULL CHECK(environment IN ('mock','sandbox','production')),
                    source TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    synthetic INTEGER NOT NULL CHECK(synthetic IN (0,1)),
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (id, environment)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_records_correlation ON canonical_records(correlation_id)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS business_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    workflow_id TEXT NOT NULL,
                    environment TEXT NOT NULL CHECK(environment IN ('mock','sandbox','production')),
                    synthetic INTEGER NOT NULL CHECK(synthetic IN (0,1)),
                    source TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    evidence_ref TEXT,
                    policy_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_entity ON business_events(entity_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_workflow ON business_events(workflow_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_type ON business_events(event_type)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trusted_legal_decisions (
                    decision_id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL,
                    vat_number TEXT NOT NULL,
                    legal_name TEXT NOT NULL,
                    registry_source TEXT NOT NULL,
                    request_ref TEXT NOT NULL,
                    source_data_hash TEXT NOT NULL,
                    decision_status TEXT NOT NULL,
                    verified_at TEXT NOT NULL,
                    expires_at TEXT,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_legal_entity ON trusted_legal_decisions(entity_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_legal_vat ON trusted_legal_decisions(vat_number)"
            )
            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
            raise
        finally:
            conn.close()

    def record_event(self, event: BusinessEvent) -> None:
        if event.environment is not Environment.MOCK and event.synthetic:
            raise ValueError("Synthetic business events may only be recorded in the mock environment")
        self.initialize()
        payload = event.model_dump(mode="json")
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT payload_json FROM business_events WHERE event_id = ?", (event.event_id,)
            ).fetchone()
            if existing:
                existing_payload = json.loads(existing["payload_json"])
                if existing_payload == event.payload_json:
                    conn.execute("ROLLBACK")
                    return  # Idempotent re-recording
                conn.execute("ROLLBACK")
                raise EventConflictError(
                    f"Business event '{event.event_id}' already exists with different payload. Events are immutable."
                )
            try:
                conn.execute(
                    """
                    INSERT INTO business_events
                        (event_id, event_type, entity_id, workflow_id, environment, synthetic,
                         source, occurred_at, correlation_id, evidence_ref, policy_version, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.event_type,
                        event.entity_id,
                        event.workflow_id,
                        event.environment.value,
                        int(event.synthetic),
                        event.source,
                        str(payload["occurred_at"]),
                        event.correlation_id,
                        event.evidence_ref,
                        event.policy_version,
                        json.dumps(event.payload_json, ensure_ascii=False),
                    ),
                )
                conn.execute("COMMIT")
            except sqlite3.IntegrityError:
                conn.execute("ROLLBACK")
                existing = conn.execute(
                    "SELECT payload_json FROM business_events WHERE event_id = ?", (event.event_id,)
                ).fetchone()
                if existing and json.loads(existing["payload_json"]) == event.payload_json:
                    return
                raise EventConflictError(
                    f"Business event '{event.event_id}' already exists with different payload. Events are immutable."
                )
        except Exception:
            if conn.in_transaction:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
            raise
        finally:
            conn.close()

    def persist_lead_with_events(self, entity: BaseEntity, events: list[BusinessEvent]) -> None:
        """
        Atomic persistence for a canonical entity and all associated business events in a single SQLite transaction.
        If any event insertion or the entity upsert fails, the entire transaction is rolled back.
        """
        if entity.environment is not Environment.MOCK and entity.synthetic:
            raise ValueError("Synthetic records may only be stored in the mock environment")
        self.initialize()
        payload = entity.model_dump(mode="json")
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            # 1. Upsert canonical entity
            existing = conn.execute(
                "SELECT environment FROM canonical_records WHERE id = ?", (entity.id,)
            ).fetchall()
            if existing and any(row["environment"] != entity.environment.value for row in existing):
                raise ValueError("Cross-environment record update refused")
            conn.execute(
                """
                INSERT INTO canonical_records
                    (id, entity_type, environment, source, correlation_id, synthetic,
                     payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id, environment) DO UPDATE SET
                    source=excluded.source,
                    correlation_id=excluded.correlation_id,
                    synthetic=excluded.synthetic,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (
                    entity.id,
                    type(entity).__name__,
                    entity.environment.value,
                    entity.source,
                    entity.correlation_id,
                    int(entity.synthetic),
                    json.dumps(payload, ensure_ascii=False),
                    str(payload["created_at"]),
                    str(payload["updated_at"]),
                ),
            )

            # 2. Insert all business events in the same transaction
            for event in events:
                if event.environment is not Environment.MOCK and event.synthetic:
                    raise ValueError("Synthetic business events may only be recorded in the mock environment")
                ev_payload = event.model_dump(mode="json")
                existing_ev = conn.execute(
                    "SELECT payload_json FROM business_events WHERE event_id = ?", (event.event_id,)
                ).fetchone()
                if existing_ev:
                    existing_data = json.loads(existing_ev["payload_json"])
                    if existing_data == event.payload_json:
                        continue  # Idempotent retry
                    raise EventConflictError(
                        f"Business event '{event.event_id}' already exists with different payload. Events are immutable."
                    )
                try:
                    conn.execute(
                        """
                        INSERT INTO business_events
                            (event_id, event_type, entity_id, workflow_id, environment, synthetic,
                             source, occurred_at, correlation_id, evidence_ref, policy_version, payload_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event.event_id,
                            event.event_type,
                            event.entity_id,
                            event.workflow_id,
                            event.environment.value,
                            int(event.synthetic),
                            event.source,
                            str(ev_payload["occurred_at"]),
                            event.correlation_id,
                            event.evidence_ref,
                            event.policy_version,
                            json.dumps(event.payload_json, ensure_ascii=False),
                        ),
                    )
                except sqlite3.IntegrityError:
                    recheck = conn.execute(
                        "SELECT payload_json FROM business_events WHERE event_id = ?", (event.event_id,)
                    ).fetchone()
                    if recheck and json.loads(recheck["payload_json"]) == event.payload_json:
                        continue
                    raise EventConflictError(
                        f"Business event '{event.event_id}' already exists with different payload. Events are immutable."
                    )
            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
            raise
        finally:
            conn.close()

    def list_events(
        self,
        environment: Environment | None = None,
        event_type: str | None = None,
        entity_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self.initialize()
        sql = "SELECT * FROM business_events WHERE 1=1"
        params: list[Any] = []
        if environment:
            sql += " AND environment = ?"
            params.append(environment.value)
        if event_type:
            sql += " AND event_type = ?"
            params.append(event_type)
        if entity_id:
            sql += " AND entity_id = ?"
            params.append(entity_id)
        sql += " ORDER BY occurred_at DESC LIMIT ?"
        params.append(limit)
        conn = self.connect()
        try:
            rows = conn.execute(sql, params).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["payload"] = json.loads(d["payload_json"])
                results.append(d)
            return results
        finally:
            conn.close()

    def upsert(self, entity: BaseEntity) -> None:
        if entity.environment is not Environment.MOCK and entity.synthetic:
            raise ValueError("Synthetic records may only be stored in the mock environment")
        self.initialize()
        payload = entity.model_dump(mode="json")
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT environment FROM canonical_records WHERE id = ?", (entity.id,)
            ).fetchall()
            if existing and any(row["environment"] != entity.environment.value for row in existing):
                raise ValueError("Cross-environment record update refused")
            conn.execute(
                """
                INSERT INTO canonical_records
                    (id, entity_type, environment, source, correlation_id, synthetic,
                     payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id, environment) DO UPDATE SET
                    source=excluded.source,
                    correlation_id=excluded.correlation_id,
                    synthetic=excluded.synthetic,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (
                    entity.id,
                    type(entity).__name__,
                    entity.environment.value,
                    entity.source,
                    entity.correlation_id,
                    int(entity.synthetic),
                    json.dumps(payload, ensure_ascii=False),
                    str(payload["created_at"]),
                    str(payload["updated_at"]),
                ),
            )
            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
            raise
        finally:
            conn.close()

    def save_legal_decision(self, decision: TrustedLegalVerificationDecision) -> None:
        self.initialize()
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO trusted_legal_decisions
                    (decision_id, entity_id, vat_number, legal_name, registry_source,
                     request_ref, source_data_hash, decision_status, verified_at, expires_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(decision_id) DO UPDATE SET
                    entity_id=excluded.entity_id,
                    vat_number=excluded.vat_number,
                    legal_name=excluded.legal_name,
                    registry_source=excluded.registry_source,
                    request_ref=excluded.request_ref,
                    source_data_hash=excluded.source_data_hash,
                    decision_status=excluded.decision_status,
                    verified_at=excluded.verified_at,
                    expires_at=excluded.expires_at,
                    metadata_json=excluded.metadata_json
                """,
                (
                    decision.decision_id,
                    decision.entity_id,
                    decision.vat_number,
                    decision.legal_name,
                    decision.registry_source,
                    decision.request_ref,
                    decision.source_data_hash,
                    decision.decision_status,
                    str(decision.verified_at),
                    str(decision.expires_at) if decision.expires_at else None,
                    json.dumps(decision.metadata, ensure_ascii=False),
                ),
            )
            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
            raise
        finally:
            conn.close()

    def get_legal_decision(
        self,
        entity_id: str | None = None,
        vat_number: str | None = None,
    ) -> TrustedLegalVerificationDecision | None:
        self.initialize()
        conn = self.connect()
        try:
            row = None
            if entity_id and vat_number:
                row = conn.execute(
                    """
                    SELECT * FROM trusted_legal_decisions
                    WHERE entity_id = ? OR vat_number = ?
                    ORDER BY verified_at DESC LIMIT 1
                    """,
                    (entity_id, vat_number),
                ).fetchone()
            elif entity_id:
                row = conn.execute(
                    """
                    SELECT * FROM trusted_legal_decisions
                    WHERE entity_id = ?
                    ORDER BY verified_at DESC LIMIT 1
                    """,
                    (entity_id,),
                ).fetchone()
            elif vat_number:
                row = conn.execute(
                    """
                    SELECT * FROM trusted_legal_decisions
                    WHERE vat_number = ?
                    ORDER BY verified_at DESC LIMIT 1
                    """,
                    (vat_number,),
                ).fetchone()

            if not row:
                return None

            return TrustedLegalVerificationDecision(
                decision_id=row["decision_id"],
                entity_id=row["entity_id"],
                vat_number=row["vat_number"],
                legal_name=row["legal_name"],
                registry_source=row["registry_source"],
                request_ref=row["request_ref"],
                source_data_hash=row["source_data_hash"],
                decision_status=row["decision_status"],
                verified_at=row["verified_at"],
                expires_at=row["expires_at"],
                metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
            )
        finally:
            conn.close()

    def list_records(
        self, environment: Environment, entity_type: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        self.initialize()
        sql = "SELECT payload_json FROM canonical_records WHERE environment = ?"
        params: list[Any] = [environment.value]
        if entity_type:
            sql += " AND entity_type = ?"
            params.append(entity_type)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        conn = self.connect()
        try:
            return [json.loads(row["payload_json"]) for row in conn.execute(sql, params)]
        finally:
            conn.close()


# Alias for backward compatibility across modules
Storage = StagingStore
