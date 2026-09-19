from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .constants import Environment
from .models import BaseEntity


class StagingStore:
    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
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

