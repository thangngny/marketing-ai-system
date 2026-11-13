from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .constants import Environment
from .models import BaseEntity, BusinessEvent


class EventConflictError(ValueError):
    """Raised when an attempt is made to overwrite an immutable business event with different payload."""
    pass


class StagingStore:
    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        # Enable WAL mode for high concurrency read/write safety
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.execute(
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
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_records_correlation ON canonical_records(correlation_id)"
            )
            connection.execute(
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
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_entity ON business_events(entity_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_workflow ON business_events(workflow_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_type ON business_events(event_type)"
            )

    def record_event(self, event: BusinessEvent) -> None:
        if event.environment is not Environment.MOCK and event.synthetic:
            raise ValueError("Synthetic business events may only be recorded in the mock environment")
        self.initialize()
        payload = event.model_dump(mode="json")
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT payload_json FROM business_events WHERE event_id = ?", (event.event_id,)
            ).fetchone()
            if existing:
                existing_payload = json.loads(existing["payload_json"])
                if existing_payload == event.payload_json:
                    return  # Idempotent re-recording
                raise EventConflictError(
                    f"Business event '{event.event_id}' already exists with different payload. Events are immutable."
                )
            connection.execute(
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

    def persist_lead_with_events(self, entity: BaseEntity, events: list[BusinessEvent]) -> None:
        """
        Atomic persistence for a canonical entity and all associated business events in a single SQLite transaction.
        If any event insertion or the entity upsert fails, the entire transaction is rolled back.
        """
        if entity.environment is not Environment.MOCK and entity.synthetic:
            raise ValueError("Synthetic records may only be stored in the mock environment")
        self.initialize()
        payload = entity.model_dump(mode="json")
        with self.connect() as connection:
            # 1. Upsert canonical entity
            existing = connection.execute(
                "SELECT environment FROM canonical_records WHERE id = ?", (entity.id,)
            ).fetchall()
            if existing and any(row["environment"] != entity.environment.value for row in existing):
                raise ValueError("Cross-environment record update refused")
            connection.execute(
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
                existing_ev = connection.execute(
                    "SELECT payload_json FROM business_events WHERE event_id = ?", (event.event_id,)
                ).fetchone()
                if existing_ev:
                    existing_data = json.loads(existing_ev["payload_json"])
                    if existing_data == event.payload_json:
                        continue  # Idempotent retry
                    raise EventConflictError(
                        f"Business event '{event.event_id}' already exists with different payload. Events are immutable."
                    )
                connection.execute(
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
        with self.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["payload"] = json.loads(d["payload_json"])
                results.append(d)
            return results

    def upsert(self, entity: BaseEntity) -> None:
        if entity.environment is not Environment.MOCK and entity.synthetic:
            raise ValueError("Synthetic records may only be stored in the mock environment")
        self.initialize()
        payload = entity.model_dump(mode="json")
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT environment FROM canonical_records WHERE id = ?", (entity.id,)
            ).fetchall()
            if existing and any(row["environment"] != entity.environment.value for row in existing):
                raise ValueError("Cross-environment record update refused")
            connection.execute(
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
        with self.connect() as connection:
            return [json.loads(row["payload_json"]) for row in connection.execute(sql, params)]


# Alias for backward compatibility across modules
Storage = StagingStore


