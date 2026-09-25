from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .paths import ensure_private_directory


class JobStore:
    """Small SQLite-backed store for sanitized export job metadata."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        ensure_private_directory(self.path.parent)
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
                    duplicates_skipped INTEGER NOT NULL DEFAULT 0,
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
            if "duplicates_skipped" not in columns:
                connection.execute(
                    "ALTER TABLE export_jobs "
                    "ADD COLUMN duplicates_skipped INTEGER NOT NULL DEFAULT 0"
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
            "duplicates_skipped": int(record.get("duplicates_skipped") or 0),
            "cancel_requested": int(bool(record.get("cancel_requested"))),
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO export_jobs (
                    job_id, created_at, updated_at, status, started_at, completed_at,
                    bytes_sent, records_exported, files_completed, query_count,
                    retry_count, duplicates_skipped, current_slice_start, current_slice_end,
                    cancel_requested, result, error, metadata_json, checkpoint_json
                ) VALUES (
                    :job_id, :created_at, :updated_at, :status, :started_at, :completed_at,
                    :bytes_sent, :records_exported, :files_completed, :query_count,
                    :retry_count, :duplicates_skipped, :current_slice_start, :current_slice_end,
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
                    duplicates_skipped=excluded.duplicates_skipped,
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

    @staticmethod
    def _timestamp(value: str) -> float:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.timestamp()

    def find_overlaps(
        self,
        overlap_fingerprint: str,
        start: datetime,
        end: datetime,
        *,
        exclude_job_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        start_ts = start.timestamp()
        end_ts = end.timestamp()
        matches: list[dict[str, Any]] = []
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM export_jobs ORDER BY created_at DESC"
            ).fetchall()

        for row in rows:
            record = self._decode(row)
            if record is None or record["job_id"] == exclude_job_id:
                continue
            metadata = record.get("metadata") or {}
            if metadata.get("overlap_fingerprint") != overlap_fingerprint:
                continue
            if record["status"] == "expired":
                continue
            if record["status"] in {"failed", "cancelled", "interrupted"} and not record.get(
                "completed_parts"
            ):
                continue
            try:
                existing_start = self._timestamp(metadata["start"])
                existing_end = self._timestamp(metadata["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if existing_start < end_ts and existing_end > start_ts:
                matches.append(record)
                if len(matches) >= limit:
                    break
        return matches

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
                        'Exporter restarted before this job completed. Re-enter the original export settings and credentials to resume.'
                    )
                WHERE status IN ('pending', 'running')
                """,
                (now, now),
            )
        return cursor.rowcount
