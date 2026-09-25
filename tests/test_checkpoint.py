import hashlib
import time
from datetime import UTC, datetime, timedelta

import pytest

import app.main as main_app
from app.exporter import ExportPart
from app.job_store import JobStore
from app.main import ExportJob, sanitized_export_metadata
from app.models import ExportInput


def remote_payload():
    start = datetime(2026, 9, 25, tzinfo=UTC)
    return ExportInput.model_validate({
        "host": "https://stellar.example.test",
        "email": "admin@example.test",
        "token": "stellar-secret",
        "sources": ["alerts"],
        "start": start.isoformat(),
        "end": (start + timedelta(minutes=5)).isoformat(),
        "format": "json",
        "filename": "checkpoint",
        "max_file_size_bytes": 256,
        "destination": {
            "type": "s3",
            "bucket": "exports",
            "prefix": "checkpoint",
            "access_key": "access-secret",
            "secret_key": "secret-secret",
        },
    })


@pytest.mark.asyncio
async def test_completed_remote_part_is_persisted_before_later_part_failure(monkeypatch, tmp_path):
    store = JobStore(tmp_path / "jobs.sqlite3")
    monkeypatch.setattr(main_app, "JOB_STORE", store)
    main_app.EXPORT_JOBS.clear()

    first = tmp_path / "part-1"
    second = tmp_path / "part-2"
    first.write_bytes(b"first-part-bytes")
    second.write_bytes(b"second-part-bytes")
    parts = [
        ExportPart(str(first), "checkpoint-0001.json", first.stat().st_size),
        ExportPart(str(second), "checkpoint-0002.json", second.stat().st_size),
    ]

    async def part_source():
        for part in parts:
            yield part

    def fake_build_output_parts(payload, job):
        return part_source(), "application/json", "checkpoint.json"

    async def fake_upload(destination, filename, stream, **kwargs):
        async for chunk in stream:
            if kwargs.get("on_bytes"):
                kwargs["on_bytes"](len(chunk))
        if filename.endswith("0002.json"):
            raise RuntimeError("simulated second-part failure")
        return f"s3://exports/checkpoint/{filename}"

    monkeypatch.setattr(main_app, "build_output_parts", fake_build_output_parts)
    monkeypatch.setattr(main_app, "upload_s3", fake_upload)

    payload = remote_payload()
    job_id = "checkpoint-job"
    job = ExportJob(
        job_id=job_id,
        created_at=time.time(),
        payload=payload,
        metadata=sanitized_export_metadata(payload),
    )
    main_app.EXPORT_JOBS[job_id] = job
    main_app.persist_job(job, force=True)

    await main_app.run_destination_job(job_id)

    assert job.status == "failed"
    assert job.files_completed == 1
    assert len(job.completed_parts) == 1
    checkpoint = job.completed_parts[0]
    assert checkpoint["part_number"] == 1
    assert checkpoint["filename"] == "checkpoint-0001.json"
    assert checkpoint["size_bytes"] == len(b"first-part-bytes")
    assert checkpoint["sha256"] == hashlib.sha256(b"first-part-bytes").hexdigest()

    persisted = store.get(job_id)
    assert persisted["completed_parts"] == job.completed_parts
    assert "stellar-secret" not in str(persisted)
    assert "access-secret" not in str(persisted)
    assert "secret-secret" not in str(persisted)
