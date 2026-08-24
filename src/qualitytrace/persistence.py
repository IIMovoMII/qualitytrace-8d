from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .models import ActionReceipt, HumanDecision, OutboxEvent, WorkflowSnapshot


class CheckpointStore:
    """Small local durable store; each project owns its own database file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _init(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    case_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(case_id, revision)
                );
                CREATE TABLE IF NOT EXISTS human_decisions (
                    decision_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS outbox_events (
                    event_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    action_version INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(case_id, action_version)
                );
                CREATE TABLE IF NOT EXISTS action_receipts (
                    case_id TEXT NOT NULL,
                    action_version INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(case_id, action_version)
                );
                """
            )

    def save(self, snapshot: WorkflowSnapshot) -> None:
        payload = snapshot.model_dump_json()
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO checkpoints(case_id, revision, status, payload_json) VALUES (?, ?, ?, ?)",
                (snapshot.case_id, snapshot.revision, snapshot.status, payload),
            )

    def latest(self, case_id: str) -> WorkflowSnapshot | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM checkpoints WHERE case_id = ? ORDER BY revision DESC LIMIT 1",
                (case_id,),
            ).fetchone()
        return WorkflowSnapshot.model_validate_json(row["payload_json"]) if row else None

    def record_decision(self, decision: HumanDecision) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO human_decisions(decision_id, case_id, payload_json, created_at) VALUES (?, ?, ?, ?)",
                (decision.decision_id, decision.case_id, decision.model_dump_json(), decision.created_at),
            )

    def decisions(self, case_id: str) -> list[HumanDecision]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM human_decisions WHERE case_id = ? ORDER BY created_at",
                (case_id,),
            ).fetchall()
        return [HumanDecision.model_validate_json(row["payload_json"]) for row in rows]

    def enqueue(self, event: OutboxEvent) -> bool:
        """Return False when the same case/action version already exists."""
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO outbox_events(event_id, case_id, action_version, payload_json, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (event.event_id, event.case_id, event.action_version, event.model_dump_json(), event.status, event.created_at),
            )
        return cursor.rowcount == 1

    def receipt(self, case_id: str, action_version: int) -> ActionReceipt | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM action_receipts WHERE case_id = ? AND action_version = ?",
                (case_id, action_version),
            ).fetchone()
        return ActionReceipt.model_validate_json(row["payload_json"]) if row else None

    def save_receipt(self, receipt: ActionReceipt) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO action_receipts(case_id, action_version, payload_json, created_at) VALUES (?, ?, ?, ?)",
                (receipt.case_id, receipt.action_version, receipt.model_dump_json(), receipt.created_at),
            )

    def export_summary(self) -> dict[str, Any]:
        with self._connect() as connection:
            counts = {}
            for table in ("checkpoints", "human_decisions", "outbox_events", "action_receipts"):
                counts[table] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return {"database": str(self.path), "tables": counts}
