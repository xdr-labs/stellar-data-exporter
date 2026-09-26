import time
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

import app.main as main_app
from app.job_store import JobStore
from app.main import ExportJob
from app.models import ExportInput, ScheduleCreateInput
from app.schedule_store import ScheduleCipher, ScheduleStore


def remote_export():
    end = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
    return ExportInput.model_validate({
        "host": "https://stellar.example.test",
        "email": "admin@example.test",
        "token": "stellar-secret",
        "sources": ["alerts"],
        "tenant_id": "tenant-1",
        "start": (end - timedelta(minutes=5)).isoformat(),
        "end": end.isoformat(),
        "query": {"query": {"term": {"severity": 90}}},
        "format": "json",
        "filename": "scheduled-alerts",
        "max_file_size_bytes": 1024,
        "destination": {
            "type": "s3",
            "endpoint_url": "https://objects.example.test",
            "region": "ap-northeast-2",
            "bucket": "exports",
            "prefix": "scheduled",
            "access_key": "access-secret",
            "secret_key": "secret-secret",
        },
    })


def configure_schedule_globals(monkeypatch, tmp_path):
    store = ScheduleStore(tmp_path / "schedules.sqlite3")
    cipher = ScheduleCipher.from_environment(tmp_path / "schedule.key")
    jobs = JobStore(tmp_path / "jobs.sqlite3")
    monkeypatch.setattr(main_app, "SCHEDULE_STORE", store)
    monkeypatch.setattr(main_app, "SCHEDULE_CIPHER", cipher)
    monkeypatch.setattr(main_app, "JOB_STORE", jobs)
    main_app.EXPORT_JOBS.clear()
    main_app.ACTIVE_SCHEDULE_RUNS.clear()
    return store, cipher, jobs


def test_schedule_model_requires_remote_destination():
    payload = remote_export().model_dump(mode="json")
    payload["destination"] = {"type": "download"}
    with pytest.raises(ValidationError, match="S3 or SFTP"):
        ScheduleCreateInput.model_validate({
            "name": "Invalid",
            "interval_minutes": 60,
            "window_minutes": 60,
            "export": payload,
        })


@pytest.mark.asyncio
async def test_schedule_first_and_followup_windows_are_contiguous(monkeypatch, tmp_path):
    store, cipher, _ = configure_schedule_globals(monkeypatch, tmp_path)
    template = remote_export()
    store.create(
        schedule_id="sched-1",
        name="Hourly alerts",
        interval_minutes=60,
        window_minutes=60,
        next_run_at=time.time() + 3600,
        encrypted_payload=cipher.encrypt(template.model_dump_json().encode()),
    )

    captured = []

    async def fake_create(payload):
        captured.append(payload)
        job_id = f"job-{len(captured)}"
        job = ExportJob(
            job_id=job_id,
            created_at=time.time(),
            payload=None,
            metadata=main_app.sanitized_export_metadata(payload),
            status="completed",
            started_at=time.time(),
            completed_at=time.time(),
            records_exported=10,
            result="remote-result",
        )
        main_app.EXPORT_JOBS[job_id] = job
        main_app.persist_job(job, force=True)
        return {"job_id": job_id, "mode": "background"}

    monkeypatch.setattr(main_app, "create_export_job", fake_create)

    first_end = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
    first = await main_app.execute_schedule("sched-1", now=first_end)
    assert first["status"] == "completed"
    assert captured[0].start == first_end - timedelta(minutes=60)
    assert captured[0].end == first_end
    assert captured[0].overlap_policy == "reject"
    assert captured[0].filename == "scheduled-alerts-20260925T120000Z.json"
    assert main_app.EXPORT_JOBS["job-1"].metadata["schedule_id"] == "sched-1"
    assert main_app.EXPORT_JOBS["job-1"].metadata["schedule_name"] == "Hourly alerts"

    second_end = datetime(2026, 9, 25, 13, 0, tzinfo=UTC)
    second = await main_app.execute_schedule("sched-1", now=second_end)
    assert second["status"] == "completed"
    assert captured[1].start == first_end
    assert captured[1].end == second_end
    assert store.get("sched-1")["last_success_end"] == second_end.isoformat()


@pytest.mark.asyncio
async def test_due_schedule_reserves_next_interval_before_start(monkeypatch, tmp_path):
    store, cipher, _ = configure_schedule_globals(monkeypatch, tmp_path)
    store.create(
        schedule_id="due",
        name="Due schedule",
        interval_minutes=15,
        window_minutes=15,
        next_run_at=100.0,
        encrypted_payload=cipher.encrypt(remote_export().model_dump_json().encode()),
    )
    started = []

    class FakeTask:
        def done(self):
            return False

    def fake_start(schedule_id):
        started.append(schedule_id)
        task = FakeTask()
        main_app.ACTIVE_SCHEDULE_RUNS[schedule_id] = task
        return task

    monkeypatch.setattr(main_app, "start_schedule_run", fake_start)
    result = await main_app.run_due_schedules_once(now=200.0)

    assert result == ["due"]
    assert started == ["due"]
    assert store.get("due")["next_run_at"] == 200.0 + 15 * 60
