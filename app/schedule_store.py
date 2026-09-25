from __future__ import annotations

import os
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


class ScheduleCipher:
    def __init__(self, key: bytes):
        self._fernet = Fernet(key)

    @classmethod
    def from_environment(cls, key_path: str | Path) -> "ScheduleCipher":
        configured = os.environ.get("STELLAR_EXPORTER_SCHEDULE_KEY")
        if configured:
            return cls(configured.strip().encode("ascii"))

        path = Path(key_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            key = path.read_bytes().strip()
        else:
            key = Fernet.generate_key()
            fd, temporary = tempfile.mkstemp(prefix=".schedule-key-", dir=path.parent)
            try:
                os.write(fd, key + b"\n")
                os.fchmod(fd, 0o600)
            finally:
                os.close(fd)
            os.replace(temporary, path)
        os.chmod(path, 0o600)
        return cls(key)

    def encrypt(self, payload: bytes) -> bytes:
        return self._fernet.encrypt(payload)

    def decrypt(self, ciphertext: bytes) -> bytes:
        try:
            return self._fernet.decrypt(ciphertext)
        except InvalidToken as exc:
            raise RuntimeError(
                "Scheduled export payload cannot be decrypted with the configured key"
            ) from exc


class ScheduleStore:
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
                CREATE TABLE IF NOT EXISTS export_schedules (
                    schedule_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    interval_minutes INTEGER NOT NULL,
                    window_minutes INTEGER NOT NULL,
                    next_run_at REAL NOT NULL,
                    last_run_at REAL,
                    last_success_end TEXT,
                    last_job_id TEXT,
                    last_status TEXT,
                    last_error TEXT,
                    encrypted_payload BLOB NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_export_schedules_due "
                "ON export_schedules(enabled, next_run_at)"
            )

    @staticmethod
    def _decode(row: sqlite3.Row | None, *, include_ciphertext: bool = False):
        if row is None:
            return None
        item = dict(row)
        item["enabled"] = bool(item["enabled"])
        if not include_ciphertext:
            item.pop("encrypted_payload", None)
        return item

    def create(
        self,
        *,
        schedule_id: str,
        name: str,
        interval_minutes: int,
        window_minutes: int,
        next_run_at: float,
        encrypted_payload: bytes,
        enabled: bool = True,
    ) -> dict[str, Any]:
        now = time.time()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO export_schedules (
                    schedule_id, name, created_at, updated_at, enabled,
                    interval_minutes, window_minutes, next_run_at, encrypted_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    schedule_id,
                    name,
                    now,
                    now,
                    int(enabled),
                    interval_minutes,
                    window_minutes,
                    next_run_at,
                    encrypted_payload,
                ),
            )
        return self.get(schedule_id)

    def get(
        self,
        schedule_id: str,
        *,
        include_ciphertext: bool = False,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM export_schedules WHERE schedule_id = ?",
                (schedule_id,),
            ).fetchone()
        return self._decode(row, include_ciphertext=include_ciphertext)

    def list(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM export_schedules ORDER BY created_at DESC"
            ).fetchall()
        return [self._decode(row) for row in rows]

    def update(
        self,
        schedule_id: str,
        *,
        enabled: bool | None = None,
        name: str | None = None,
        interval_minutes: int | None = None,
        window_minutes: int | None = None,
        next_run_at: float | None = None,
        encrypted_payload: bytes | None = None,
    ) -> dict[str, Any] | None:
        changes: list[str] = ["updated_at = ?"]
        values: list[Any] = [time.time()]
        for column, value in (
            ("enabled", None if enabled is None else int(enabled)),
            ("name", name),
            ("interval_minutes", interval_minutes),
            ("window_minutes", window_minutes),
            ("next_run_at", next_run_at),
            ("encrypted_payload", encrypted_payload),
        ):
            if value is not None:
                changes.append(f"{column} = ?")
                values.append(value)
        values.append(schedule_id)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE export_schedules SET {', '.join(changes)} WHERE schedule_id = ?",
                values,
            )
        return self.get(schedule_id)

    def delete(self, schedule_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM export_schedules WHERE schedule_id = ?",
                (schedule_id,),
            )
        return cursor.rowcount > 0

    def due(self, now: float) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM export_schedules
                WHERE enabled = 1 AND next_run_at <= ?
                ORDER BY next_run_at ASC
                """,
                (now,),
            ).fetchall()
        return [self._decode(row, include_ciphertext=True) for row in rows]

    def reserve_next_run(self, schedule_id: str, next_run_at: float) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE export_schedules
                SET next_run_at = ?, updated_at = ?
                WHERE schedule_id = ?
                """,
                (next_run_at, time.time(), schedule_id),
            )

    def record_result(
        self,
        schedule_id: str,
        *,
        job_id: str | None,
        status: str,
        last_success_end: str | None = None,
        error: str | None = None,
    ) -> None:
        with self._connect() as connection:
            if last_success_end is None:
                connection.execute(
                    """
                    UPDATE export_schedules
                    SET last_run_at = ?, last_job_id = ?, last_status = ?,
                        last_error = ?, updated_at = ?
                    WHERE schedule_id = ?
                    """,
                    (time.time(), job_id, status, error, time.time(), schedule_id),
                )
            else:
                connection.execute(
                    """
                    UPDATE export_schedules
                    SET last_run_at = ?, last_success_end = ?, last_job_id = ?,
                        last_status = ?, last_error = ?, updated_at = ?
                    WHERE schedule_id = ?
                    """,
                    (
                        time.time(),
                        last_success_end,
                        job_id,
                        status,
                        error,
                        time.time(),
                        schedule_id,
                    ),
                )
