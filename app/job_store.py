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
                    adaptive_split_count INTEGER NOT NULL DEFAULT 0,
                    duplicates_skipped INTEGER NOT NULL DEFAULT 0,
                    current_slice_start TEXT,
                    current_slice_end TEXT,
                    current_source TEXT,
                    partition_number INTEGER NOT NULL DEFAULT 0,
                    partition_total INTEGER NOT NULL DEFAULT 0,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    worker_pid INTEGER,
                    download_path TEXT,
                    download_filename TEXT,
                    download_media_type TEXT,
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
            migrations = {
                "adaptive_split_count": "INTEGER NOT NULL DEFAULT 0",
                "current_source": "TEXT",
                "partition_number": "INTEGER NOT NULL DEFAULT 0",
                "partition_total": "INTEGER NOT NULL DEFAULT 0",
                "worker_pid": "INTEGER",
                "download_path": "TEXT",
                "download_filename": "TEXT",
                "download_media_type": "TEXT",
            }
            for column, definition in migrations.items():
                if column not in columns:
                    connection.execute(
                        f"ALTER TABLE export_jobs ADD COLUMN {column} {definition}"
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
            "adaptive_split_count": int(record.get("adaptive_split_count") or 0),
            "duplicates_skipped": int(record.get("duplicates_skipped") or 0),
            "current_source": record.get("current_source"),
            "partition_number": int(record.get("partition_number") or 0),
            "partition_total": int(record.get("partition_total") or 0),
            "cancel_requested": int(bool(record.get("cancel_requested"))),
            "worker_pid": record.get("worker_pid"),
            "download_path": record.get("download_path"),
            "download_filename": record.get("download_filename"),
            "download_media_type": record.get("download_media_type"),
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO export_jobs (
                    job_id, created_at, updated_at, status, started_at, completed_at,
                    bytes_sent, records_exported, files_completed, query_count,
                    retry_count, adaptive_split_count, duplicates_skipped,
                    current_slice_start, current_slice_end, current_source,
                    partition_number, partition_total, cancel_requested, worker_pid,
                    download_path, download_filename, download_media_type,
                    result, error, metadata_json, checkpoint_json
                ) VALUES (
                    :job_id, :created_at, :updated_at, :status, :started_at, :completed_at,
                    :bytes_sent, :records_exported, :files_completed, :query_count,
                    :retry_count, :adaptive_split_count, :duplicates_skipped,
                    :current_slice_start, :current_slice_end, :current_source,
                    :partition_number, :partition_total, :cancel_requested, :worker_pid,
                    :download_path, :download_filename, :download_media_type,
                    :result, :error, :metadata_json, :checkpoint_json
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
                    adaptive_split_count=excluded.adaptive_split_count,
                    duplicates_skipped=excluded.duplicates_skipped,
                    current_slice_start=excluded.current_slice_start,
                    current_slice_end=excluded.current_slice_end,
                    current_source=excluded.current_source,
                    partition_number=excluded.partition_number,
                    partition_total=excluded.partition_total,
                    cancel_requested=CASE
                        WHEN export_jobs.cancel_requested = 1 THEN 1
                        ELSE excluded.cancel_requested
                    END,
                    worker_pid=excluded.worker_pid,
                    download_path=excluded.download_path,
                    download_filename=excluded.download_filename,
                    download_media_type=excluded.download_media_type,
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

    def set_worker_pid(self, job_id: str, pid: int | None) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE export_jobs SET worker_pid = ?, updated_at = ? WHERE job_id = ?",
                (pid, time.time(), job_id),
            )

    def clear_cancel_requested(self, job_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE export_jobs SET cancel_requested = 0, updated_at = ? WHERE job_id = ?",
                (time.time(), job_id),
            )

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

    def list_active(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM export_jobs "
                "WHERE status IN ('pending', 'running') "
                "ORDER BY created_at"
            ).fetchall()
        return [self._decode(row) for row in rows if row is not None]

    def request_cancel(self, job_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE export_jobs
                SET cancel_requested = 1,
                    updated_at = ?
                WHERE job_id = ?
                  AND status IN ('pending', 'running')
                """,
                (time.time(), job_id),
            )
        return cursor.rowcount > 0

    def recover_interrupted(self, job_ids: list[str] | None = None) -> int:
        now = time.time()
        where = "status IN ('pending', 'running')"
        params: list[Any] = [now, now]
        if job_ids is not None:
            if not job_ids:
                return 0
            placeholders = ",".join("?" for _ in job_ids)
            where += f" AND job_id IN ({placeholders})"
            params.extend(job_ids)

        with self._connect() as connection:
            cursor = connection.execute(
                f"""
                UPDATE export_jobs
                SET status = 'interrupted',
                    completed_at = COALESCE(completed_at, ?),
                    updated_at = ?,
                    worker_pid = NULL,
                    error = COALESCE(
                        error,
                        'Export worker stopped before this job completed, possibly after the API process restarted. Re-enter the original export settings and credentials to resume.'
                    )
                WHERE {where}
                """,
                params,
            )
        return cursor.rowcount
