import json
import os
import time

import pytest
from cryptography.fernet import Fernet

from app.schedule_store import ScheduleCipher, ScheduleStore


def test_schedule_state_directory_is_private(tmp_path):
    state_dir = tmp_path / "state"
    key_path = state_dir / "schedule.key"
    db_path = state_dir / "schedules.sqlite3"

    ScheduleCipher.from_environment(key_path)
    ScheduleStore(db_path)

    assert state_dir.stat().st_mode & 0o777 == 0o700
    assert key_path.stat().st_mode & 0o777 == 0o600
    assert db_path.stat().st_mode & 0o777 == 0o600


def test_schedule_cipher_and_store_keep_payload_encrypted_across_reopen(tmp_path):
    key_path = tmp_path / "schedule.key"
    db_path = tmp_path / "schedules.sqlite3"
    cipher = ScheduleCipher.from_environment(key_path)
    store = ScheduleStore(db_path)

    payload = {
        "query": {"query": {"term": {"marker": "raw-query-marker"}}},
        "email": "account-marker@example.test",
        "token": "stellar-marker",
        "destination": {
            "type": "s3",
            "access_key": "access-marker",
            "secret_key": "secret-marker",
        },
    }
    ciphertext = cipher.encrypt(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    )
    created = store.create(
        schedule_id="schedule-1",
        name="Hourly alerts",
        interval_minutes=60,
        window_minutes=60,
        next_run_at=time.time() + 60,
        encrypted_payload=ciphertext,
    )

    assert created["schedule_id"] == "schedule-1"
    assert "encrypted_payload" not in created
    assert oct(os.stat(key_path).st_mode & 0o777) == "0o600"
    assert oct(os.stat(db_path).st_mode & 0o777) == "0o600"

    raw = b"".join(
        candidate.read_bytes()
        for candidate in (
            db_path,
            tmp_path / "schedules.sqlite3-wal",
            tmp_path / "schedules.sqlite3-shm",
        )
        if candidate.exists()
    )
    for marker in (
        b"raw-query-marker",
        b"account-marker@example.test",
        b"stellar-marker",
        b"access-marker",
        b"secret-marker",
    ):
        assert marker not in raw

    reopened = ScheduleStore(db_path)
    stored = reopened.get("schedule-1", include_ciphertext=True)
    decrypted = json.loads(cipher.decrypt(stored["encrypted_payload"]))
    assert decrypted == payload


def test_schedule_cipher_rejects_wrong_key(tmp_path, monkeypatch):
    key_path = tmp_path / "schedule.key"
    cipher = ScheduleCipher.from_environment(key_path)
    ciphertext = cipher.encrypt(b"protected")

    monkeypatch.setenv(
        "STELLAR_EXPORTER_SCHEDULE_KEY",
        Fernet.generate_key().decode("ascii"),
    )
    wrong = ScheduleCipher.from_environment(tmp_path / "ignored.key")
    with pytest.raises(RuntimeError, match="cannot be decrypted"):
        wrong.decrypt(ciphertext)


def test_schedule_store_due_update_result_and_delete(tmp_path):
    store = ScheduleStore(tmp_path / "schedules.sqlite3")
    now = time.time()
    store.create(
        schedule_id="due",
        name="Due",
        interval_minutes=15,
        window_minutes=15,
        next_run_at=now - 1,
        encrypted_payload=b"ciphertext",
    )
    store.create(
        schedule_id="future",
        name="Future",
        interval_minutes=60,
        window_minutes=60,
        next_run_at=now + 3600,
        encrypted_payload=b"ciphertext",
    )

    assert [item["schedule_id"] for item in store.due(now)] == ["due"]

    store.reserve_next_run("due", now + 900)
    assert store.due(now) == []

    store.record_result(
        "due",
        job_id="job-1",
        status="completed",
        last_success_end="2026-09-25T00:15:00+00:00",
    )
    item = store.get("due")
    assert item["last_job_id"] == "job-1"
    assert item["last_status"] == "completed"
    assert item["last_success_end"] == "2026-09-25T00:15:00+00:00"

    updated = store.update("due", enabled=False, name="Paused")
    assert updated["enabled"] is False
    assert updated["name"] == "Paused"
    assert store.delete("due") is True
    assert store.get("due") is None
