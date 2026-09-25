from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any


class JobStore:
    """Small SQLite-backed store for sanitized export job metadata."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        os.chmod(self.path, 0o600)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS export_jobs (
                    job_id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    status TEXT NOT NULL,
                    started_at REAL,
                    completed_at REAL,
                    bytes_sent INTEGER NOT NULL DEFAULT 0,
                    records_exported INTEGER NOT NULL DEFAULT 0,
                    files_completed INTEGER NOT NULL DEFAULT 0,
                    query_count INTEGER NOT NULL DEFAULT 0,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    current_slice_start TEXT,
                    current_slice_end TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    result TEXT,
                    error TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    checkpoint_json TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(export_jobs)").fetchall()
            }
            if "checkpoint_json" not in columns:
                connection.execute(
                    "ALTER TABLE export_jobs "
                    "ADD COLUMN checkpoint_json TEXT NOT NULL DEFAULT '[]'"
                )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_export_jobs_created_at "
                "ON export_jobs(created_at DESC)"
            )

    def save(self, record: dict[str, Any]) -> None:
        values = {
            **record,
            "updated_at": time.time(),
            "metadata_json": json.dumps(
                record.get("metadata", {}),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            "checkpoint_json": json.dumps(
                record.get("completed_parts", []),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            "cancel_requested": int(bool(record.get("cancel_requested"))),
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO export_jobs (
                    job_id, created_at, updated_at, status, started_at, completed_at,
                    bytes_sent, records_exported, files_completed, query_count,
                    retry_count, current_slice_start, current_slice_end,
                    cancel_requested, result, error, metadata_json, checkpoint_json
                ) VALUES (
                    :job_id, :created_at, :updated_at, :status, :started_at, :completed_at,
                    :bytes_sent, :records_exported, :files_completed, :query_count,
                    :retry_count, :current_slice_start, :current_slice_end,
                    :cancel_requested, :result, :error, :metadata_json, :checkpoint_json
                )
                ON CONFLICT(job_id) DO UPDATE SET
                    updated_at=excluded.updated_at,
                    status=excluded.status,
                    started_at=excluded.started_at,
                    completed_at=excluded.completed_at,
                    bytes_sent=excluded.bytes_sent,
                    records_exported=excluded.records_exported,
                    files_completed=excluded.files_completed,
                    query_count=excluded.query_count,
                    retry_count=excluded.retry_count,
                    current_slice_start=excluded.current_slice_start,
                    current_slice_end=excluded.current_slice_end,
                    cancel_requested=excluded.cancel_requested,
                    result=excluded.result,
                    error=excluded.error,
                    metadata_json=excluded.metadata_json,
                    checkpoint_json=excluded.checkpoint_json
                """,
                values,
            )

    def _decode(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["cancel_requested"] = bool(item["cancel_requested"])
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        item["completed_parts"] = json.loads(item.pop("checkpoint_json", "[]") or "[]")
        return item

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM export_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return self._decode(row)

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        bounded = max(1, min(int(limit), 200))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM export_jobs ORDER BY created_at DESC LIMIT ?",
                (bounded,),
            ).fetchall()
        return [self._decode(row) for row in rows if row is not None]

    def recover_interrupted(self) -> int:
        now = time.time()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE export_jobs
                SET status = 'interrupted',
                    completed_at = COALESCE(completed_at, ?),
                    updated_at = ?,
                    error = COALESCE(
                        error,
                        'Exporter restarted before this job completed; resume is not available yet.'
                    )
                WHERE status IN ('pending', 'running')
                """,
                (now, now),
            )
        return cursor.rowcount
