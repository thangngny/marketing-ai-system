"""SQLite persistence for workflow state, approvals, tool ledger, idempotency, gateway dedupe.

This is the System of Record for execution state. Zoho is never used for it.
Swappable: WorkflowEngine only talks to the methods below.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

_SCHEMA = """
CREATE TABLE IF NOT EXISTS workflows (
    workflow_id TEXT PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    workflow_type TEXT NOT NULL,
    environment TEXT NOT NULL,
    user_id TEXT,
    channel_id TEXT,
    request TEXT NOT NULL,
    params_json TEXT NOT NULL DEFAULT '{}',
    specialists_json TEXT NOT NULL DEFAULT '[]',
    state TEXT NOT NULL,
    current_step INTEGER NOT NULL DEFAULT 0,
    approval_id TEXT,
    resume_after TEXT,
    result_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_workflows_state ON workflows(state);
CREATE TABLE IF NOT EXISTS workflow_steps (
    workflow_id TEXT NOT NULL,
    step_index INTEGER NOT NULL,
    name TEXT NOT NULL,
    state TEXT NOT NULL,
    output_json TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    started_at TEXT,
    finished_at TEXT,
    PRIMARY KEY (workflow_id, step_index)
);
CREATE TABLE IF NOT EXISTS workflow_transitions (
    workflow_id TEXT NOT NULL,
    from_state TEXT,
    to_state TEXT NOT NULL,
    reason TEXT,
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    workflow_id TEXT,
    requested_action TEXT NOT NULL,
    target_system TEXT NOT NULL,
    impact TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    payload_summary TEXT NOT NULL,
    requested_by_agent TEXT NOT NULL,
    requested_for_user TEXT,
    channel_id TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    decided_at TEXT,
    decided_by TEXT,
    decided_via TEXT,
    evidence TEXT,
    consumed_at TEXT
);
CREATE TABLE IF NOT EXISTS idempotency (
    idempotency_key TEXT PRIMARY KEY,
    tool TEXT NOT NULL,
    workflow_id TEXT,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tool_calls (
    call_id INTEGER PRIMARY KEY AUTOINCREMENT,
    correlation_id TEXT NOT NULL,
    workflow_id TEXT,
    specialist TEXT,
    tool TEXT NOT NULL,
    connector TEXT,
    impact TEXT NOT NULL,
    decision TEXT NOT NULL,
    state TEXT NOT NULL,
    environment TEXT NOT NULL,
    latency_ms REAL,
    error_code TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS gateway_events (
    event_id TEXT PRIMARY KEY,
    channel_id TEXT,
    user_id TEXT,
    correlation_id TEXT NOT NULL,
    received_at TEXT NOT NULL
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # -- workflows ---------------------------------------------------------
    def create_workflow(self, row: dict[str, Any]) -> None:
        now = utcnow()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO workflows (workflow_id, correlation_id, workflow_type, environment, user_id,
                   channel_id, request, params_json, specialists_json, state, current_step, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?)""",
                (row["workflow_id"], row["correlation_id"], row["workflow_type"], row["environment"],
                 row.get("user_id"), row.get("channel_id"), row["request"],
                 json.dumps(row.get("params", {}), ensure_ascii=False),
                 json.dumps(row.get("specialists", [])), row["state"], now, now),
            )
            conn.execute("INSERT INTO workflow_transitions VALUES (?,?,?,?,?)",
                         (row["workflow_id"], None, row["state"], "created", now))

    def get_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM workflows WHERE workflow_id=?", (workflow_id,)).fetchone()
        return _decode_workflow(row) if row else None

    def list_workflows(self, states: tuple[str, ...] | None = None, limit: int = 50) -> list[dict[str, Any]]:
        sql, params = "SELECT * FROM workflows", []
        if states:
            sql += f" WHERE state IN ({','.join('?' * len(states))})"
            params = list(states)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        with self._conn() as conn:
            return [_decode_workflow(r) for r in conn.execute(sql, [*params, limit])]

    def transition(self, workflow_id: str, from_state: str, to_state: str, reason: str = "", **fields: Any) -> None:
        now = utcnow()
        sets = ["state=?", "updated_at=?"]
        values: list[Any] = [to_state, now]
        for key, value in fields.items():
            column = {"result": "result_json"}.get(key, key)
            sets.append(f"{column}=?")
            values.append(json.dumps(value, ensure_ascii=False) if key == "result" else value)
        with self._conn() as conn:
            changed = conn.execute(
                f"UPDATE workflows SET {', '.join(sets)} WHERE workflow_id=? AND state=?",
                [*values, workflow_id, from_state],
            ).rowcount
            if changed != 1:
                raise RuntimeError(f"Concurrent transition refused for {workflow_id}: expected {from_state}")
            conn.execute("INSERT INTO workflow_transitions VALUES (?,?,?,?,?)", (workflow_id, from_state, to_state, reason, now))

    def set_fields(self, workflow_id: str, **fields: Any) -> None:
        sets = [f"{k}=?" for k in fields] + ["updated_at=?"]
        with self._conn() as conn:
            conn.execute(f"UPDATE workflows SET {', '.join(sets)} WHERE workflow_id=?", [*fields.values(), utcnow(), workflow_id])

    def transitions(self, workflow_id: str) -> list[tuple[str | None, str]]:
        with self._conn() as conn:
            return [(r["from_state"], r["to_state"]) for r in conn.execute(
                "SELECT from_state, to_state FROM workflow_transitions WHERE workflow_id=? ORDER BY rowid", (workflow_id,))]

    # -- steps -------------------------------------------------------------
    def start_step(self, workflow_id: str, index: int, name: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO workflow_steps (workflow_id, step_index, name, state, attempts, started_at)
                   VALUES (?,?,?,'RUNNING',1,?)
                   ON CONFLICT(workflow_id, step_index) DO UPDATE SET state='RUNNING', attempts=attempts+1, started_at=excluded.started_at""",
                (workflow_id, index, name, utcnow()),
            )

    def finish_step(self, workflow_id: str, index: int, state: str, output: Any) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE workflow_steps SET state=?, output_json=?, finished_at=? WHERE workflow_id=? AND step_index=?",
                (state, json.dumps(output, ensure_ascii=False, default=str), utcnow(), workflow_id, index),
            )

    def step_outputs(self, workflow_id: str) -> dict[str, Any]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT name, output_json FROM workflow_steps WHERE workflow_id=? AND state='DONE' ORDER BY step_index",
                (workflow_id,),
            ).fetchall()
        return {r["name"]: json.loads(r["output_json"]) if r["output_json"] else None for r in rows}

    def steps(self, workflow_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT step_index, name, state, attempts FROM workflow_steps WHERE workflow_id=? ORDER BY step_index", (workflow_id,))]

    # -- approvals ---------------------------------------------------------
    def insert_approval(self, record: dict[str, Any]) -> None:
        columns = list(record)
        with self._conn() as conn:
            conn.execute(f"INSERT INTO approvals ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
                         [record[c] for c in columns])

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM approvals WHERE approval_id=? OR code=?", (approval_id, approval_id)).fetchone()
        return dict(row) if row else None

    def list_approvals(self, status: str | None = None) -> list[dict[str, Any]]:
        sql, params = "SELECT * FROM approvals", []
        if status:
            sql, params = sql + " WHERE status=?", [status]
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(sql + " ORDER BY created_at DESC", params)]

    def update_approval(self, approval_id: str, expected_status: str, **fields: Any) -> bool:
        sets = [f"{k}=?" for k in fields]
        with self._conn() as conn:
            return conn.execute(
                f"UPDATE approvals SET {', '.join(sets)} WHERE approval_id=? AND status=?",
                [*fields.values(), approval_id, expected_status],
            ).rowcount == 1

    # -- idempotency / ledger / gateway -----------------------------------
    def idempotent_result(self, key: str) -> Any | None:
        with self._conn() as conn:
            row = conn.execute("SELECT result_json FROM idempotency WHERE idempotency_key=?", (key,)).fetchone()
        return json.loads(row["result_json"]) if row else None

    def remember_result(self, key: str, tool: str, workflow_id: str | None, result: Any) -> None:
        with self._conn() as conn:
            conn.execute("INSERT OR IGNORE INTO idempotency VALUES (?,?,?,?,?)",
                         (key, tool, workflow_id, json.dumps(result, ensure_ascii=False, default=str), utcnow()))

    def record_tool_call(self, **row: Any) -> None:
        row.setdefault("created_at", utcnow())
        columns = list(row)
        with self._conn() as conn:
            conn.execute(f"INSERT INTO tool_calls ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
                         [row[c] for c in columns])

    def last_live_success(self, connector: str, impact: str = "READ") -> str | None:
        """Evidence-based liveness: timestamp of the last real (non-mock) successful call."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT MAX(created_at) AS at FROM tool_calls WHERE connector=? AND impact=? AND state='OK' AND environment!='mock'",
                (connector, impact),
            ).fetchone()
        return row["at"] if row and row["at"] else None

    def last_live_state(self, connector: str) -> tuple[str, str] | None:
        """(state, error_code) of the most recent non-mock READ call for a connector."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT state, error_code FROM tool_calls WHERE connector=? AND impact='READ' AND environment!='mock' "
                "ORDER BY call_id DESC LIMIT 1", (connector,)).fetchone()
        return (row["state"], row["error_code"] or "") if row else None

    def tool_calls(self, workflow_id: str | None = None, correlation_id: str | None = None) -> list[dict[str, Any]]:
        sql, params = "SELECT * FROM tool_calls WHERE 1=1", []
        if workflow_id:
            sql, params = sql + " AND workflow_id=?", [*params, workflow_id]
        if correlation_id:
            sql, params = sql + " AND correlation_id=?", [*params, correlation_id]
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(sql + " ORDER BY call_id", params)]

    def claim_event(self, event_id: str, channel_id: str | None, user_id: str | None, correlation_id: str) -> bool:
        """True the first time an inbound Buzz event is seen; False for duplicates."""
        with self._conn() as conn:
            return conn.execute(
                "INSERT OR IGNORE INTO gateway_events VALUES (?,?,?,?,?)",
                (event_id, channel_id, user_id, correlation_id, utcnow()),
            ).rowcount == 1


def _decode_workflow(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["params"] = json.loads(data.pop("params_json") or "{}")
    data["specialists"] = json.loads(data.pop("specialists_json") or "[]")
    raw = data.pop("result_json")
    data["result"] = json.loads(raw) if raw else None
    return data
