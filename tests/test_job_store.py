import json
import sqlite3
import time
from datetime import UTC, datetime, timedelta

from app.job_store import JobStore
from app.main import sanitized_export_metadata
from app.models import ExportInput


def export_payload(destination):
    start = datetime(2026, 9, 25, tzinfo=UTC)
    return {
        "host": "https://stellar.example.test",
        "email": "admin@example.test",
        "token": "stellar-token-must-not-persist",
        "verify_tls": True,
        "sources": ["alerts"],
        "tenant_id": "tenant-1",
        "time_field": "timestamp",
        "start": start.isoformat(),
        "end": (start + timedelta(minutes=5)).isoformat(),
        "query_mode": "stellar_lucene",
        "query": {},
        "stellar_query": "secret_field:secret-value",
        "format": "csv",
        "filename": "security-export",
        "destination": destination,
    }


def test_sanitized_metadata_excludes_stellar_and_s3_secrets():
    payload = ExportInput.model_validate(export_payload({
        "type": "s3",
        "endpoint_url": "https://objects.example.test",
        "region": "ap-northeast-2",
        "bucket": "exports",
        "prefix": "daily/",
        "access_key": "s3-access-must-not-persist",
        "secret_key": "s3-secret-must-not-persist",
        "session_token": "s3-session-must-not-persist",
    }))
    serialized = json.dumps(sanitized_export_metadata(payload))
    for secret in (
        "stellar-token-must-not-persist",
        "secret_field:secret-value",
        "s3-access-must-not-persist",
        "s3-secret-must-not-persist",
        "s3-session-must-not-persist",
        "admin@example.test",
    ):
        assert secret not in serialized
    assert '"destination_type": "s3"' in serialized


def test_sanitized_metadata_excludes_sftp_secrets():
    payload = ExportInput.model_validate(export_payload({
        "type": "sftp",
        "host": "sftp.example.test",
        "port": 22,
        "username": "exporter",
        "auth_method": "private_key",
        "private_key": "PRIVATE-KEY-MUST-NOT-PERSIST",
        "private_key_passphrase": "KEY-PASSPHRASE-MUST-NOT-PERSIST",
        "remote_path": "/exports",
        "verify_host_key": True,
    }))
    serialized = json.dumps(sanitized_export_metadata(payload))
    assert "PRIVATE-KEY-MUST-NOT-PERSIST" not in serialized
    assert "KEY-PASSPHRASE-MUST-NOT-PERSIST" not in serialized
    assert '"destination_type": "sftp"' in serialized


def test_job_store_creates_private_state_directory(tmp_path):
    state_dir = tmp_path / "state"
    path = state_dir / "jobs.sqlite3"

    JobStore(path)

    assert state_dir.stat().st_mode & 0o777 == 0o700
    assert path.stat().st_mode & 0o777 == 0o600


def test_job_store_survives_reopen_and_marks_active_jobs_interrupted(tmp_path):
    path = tmp_path / "jobs.sqlite3"
    store = JobStore(path)
    store.save({
        "job_id": "job-1",
        "created_at": time.time() - 5,
        "status": "running",
        "started_at": time.time() - 4,
        "completed_at": None,
        "bytes_sent": 1024,
        "records_exported": 10,
        "files_completed": 0,
        "query_count": 2,
        "retry_count": 0,
        "current_slice_start": None,
        "current_slice_end": None,
        "cancel_requested": False,
        "result": None,
        "error": None,
        "metadata": {"destination_type": "download"},
    })

    reopened = JobStore(path)
    assert reopened.get("job-1")["status"] == "running"
    assert reopened.recover_interrupted() == 1
    recovered = reopened.get("job-1")
    assert recovered["status"] == "interrupted"
    assert recovered["completed_at"] is not None
    assert "restarted" in recovered["error"]


def test_job_store_migrates_existing_database_for_completed_part_checkpoints(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE export_jobs (
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
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )

    store = JobStore(path)
    columns = {
        row[1]
        for row in sqlite3.connect(path).execute("PRAGMA table_info(export_jobs)").fetchall()
    }
    assert "checkpoint_json" in columns
    assert "duplicates_skipped" in columns

    record = {
        "job_id": "migrated",
        "created_at": time.time(),
        "status": "failed",
        "started_at": None,
        "completed_at": time.time(),
        "bytes_sent": 10,
        "records_exported": 1,
        "files_completed": 1,
        "query_count": 1,
        "retry_count": 0,
        "current_slice_start": None,
        "current_slice_end": None,
        "cancel_requested": False,
        "result": None,
        "error": "later part failed",
        "metadata": {"destination_type": "s3"},
        "completed_parts": [{
            "part_number": 1,
            "filename": "export-0001.json",
            "size_bytes": 10,
            "sha256": "abc123",
            "result": "s3://exports/export-0001.json",
        }],
    }
    store.save(record)
    assert store.get("migrated")["completed_parts"] == record["completed_parts"]
