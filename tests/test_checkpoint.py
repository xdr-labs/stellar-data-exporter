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


def failed_record(payload, checkpoint):
    return {
        "job_id": "resume-job",
        "created_at": time.time() - 30,
        "status": "failed",
        "started_at": time.time() - 20,
        "completed_at": time.time() - 10,
        "bytes_sent": checkpoint["size_bytes"],
        "records_exported": 5,
        "files_completed": 1,
        "query_count": 2,
        "retry_count": 0,
        "current_slice_start": None,
        "current_slice_end": None,
        "cancel_requested": False,
        "result": None,
        "error": "simulated failure",
        "metadata": sanitized_export_metadata(payload),
        "completed_parts": [checkpoint],
    }


@pytest.mark.asyncio
async def test_resume_skips_matching_completed_part_and_uploads_remaining(monkeypatch, tmp_path):
    store = JobStore(tmp_path / "resume.sqlite3")
    monkeypatch.setattr(main_app, "JOB_STORE", store)
    main_app.EXPORT_JOBS.clear()
    payload = remote_payload()
    first_bytes = b"stable-first-part"
    second_bytes = b"remaining-second-part"
    checkpoint = {
        "part_number": 1,
        "filename": "checkpoint-0001.json",
        "size_bytes": len(first_bytes),
        "sha256": hashlib.sha256(first_bytes).hexdigest(),
        "result": "s3://exports/checkpoint/checkpoint-0001.json",
    }
    store.save(failed_record(payload, checkpoint))

    async def part_source():
        first = tmp_path / "resume-part-1"
        second = tmp_path / "resume-part-2"
        first.write_bytes(first_bytes)
        second.write_bytes(second_bytes)
        yield ExportPart(str(first), "checkpoint-0001.json", len(first_bytes))
        yield ExportPart(str(second), "checkpoint-0002.json", len(second_bytes))

    monkeypatch.setattr(
        main_app,
        "build_output_parts",
        lambda payload, job: (part_source(), "application/json", "checkpoint.json"),
    )
    uploaded = []

    async def fake_upload(destination, filename, stream, **kwargs):
        payload_bytes = b""
        async for chunk in stream:
            payload_bytes += chunk
            if kwargs.get("on_bytes"):
                kwargs["on_bytes"](len(chunk))
        uploaded.append((filename, payload_bytes))
        return f"s3://exports/checkpoint/{filename}"

    monkeypatch.setattr(main_app, "upload_s3", fake_upload)

    response = await main_app.resume_export_job("resume-job", payload)
    assert response["resumed_from_parts"] == 1
    task = main_app.EXPORT_JOBS["resume-job"].task
    await task

    job = main_app.EXPORT_JOBS["resume-job"]
    assert job.status == "completed"
    assert [name for name, _ in uploaded] == ["checkpoint-0002.json"]
    assert job.files_completed == 2
    assert len(job.completed_parts) == 2
    assert job.completed_parts[1]["sha256"] == hashlib.sha256(second_bytes).hexdigest()
    assert store.get("resume-job")["status"] == "completed"


@pytest.mark.asyncio
async def test_resume_fails_closed_when_regenerated_checkpoint_part_changes(monkeypatch, tmp_path):
    store = JobStore(tmp_path / "mismatch.sqlite3")
    monkeypatch.setattr(main_app, "JOB_STORE", store)
    main_app.EXPORT_JOBS.clear()
    payload = remote_payload()
    checkpoint = {
        "part_number": 1,
        "filename": "checkpoint-0001.json",
        "size_bytes": len(b"original"),
        "sha256": hashlib.sha256(b"original").hexdigest(),
        "result": "s3://exports/checkpoint/checkpoint-0001.json",
    }
    store.save(failed_record(payload, checkpoint))

    async def changed_source():
        changed = tmp_path / "changed-part"
        changed.write_bytes(b"modified")
        yield ExportPart(str(changed), "checkpoint-0001.json", len(b"modified"))

    monkeypatch.setattr(
        main_app,
        "build_output_parts",
        lambda payload, job: (changed_source(), "application/json", "checkpoint.json"),
    )
    uploads = []

    async def unexpected_upload(*args, **kwargs):
        uploads.append(args)
        return "unexpected"

    monkeypatch.setattr(main_app, "upload_s3", unexpected_upload)

    await main_app.resume_export_job("resume-job", payload)
    task = main_app.EXPORT_JOBS["resume-job"].task
    await task

    job = main_app.EXPORT_JOBS["resume-job"]
    assert job.status == "failed"
    assert "Checkpoint mismatch at part 1" in job.error
    assert uploads == []


def test_resume_fingerprint_changes_with_query_without_persisting_query_text():
    original = remote_payload()
    changed_data = original.model_dump(mode="json")
    changed_data["query"] = {"query": {"term": {"secret_field": "different-secret-value"}}}
    changed = ExportInput.model_validate(changed_data)

    original_meta = sanitized_export_metadata(original)
    changed_meta = sanitized_export_metadata(changed)

    assert original_meta["resume_fingerprint"] != changed_meta["resume_fingerprint"]
    serialized = str(original_meta)
    assert "secret_field" not in serialized
    assert "different-secret-value" not in serialized


def test_resume_payload_fingerprint_rejects_query_change(tmp_path, monkeypatch):
    store = JobStore(tmp_path / "fingerprint.sqlite3")
    monkeypatch.setattr(main_app, "JOB_STORE", store)
    main_app.EXPORT_JOBS.clear()

    original = remote_payload()
    checkpoint = {
        "part_number": 1,
        "filename": "checkpoint-0001.json",
        "size_bytes": 8,
        "sha256": hashlib.sha256(b"original").hexdigest(),
        "result": "s3://exports/checkpoint/checkpoint-0001.json",
    }
    record = failed_record(original, checkpoint)
    store.save(record)

    changed = original.model_copy(
        update={"query": {"query": {"term": {"severity": 90}}}}
    )
    with pytest.raises(Exception) as exc_info:
        main_app.validate_resume_payload(store.get("resume-job"), changed)
    assert getattr(exc_info.value, "status_code", None) == 409
    assert "do not match" in str(getattr(exc_info.value, "detail", ""))


def test_resume_fingerprint_is_secret_free():
    payload = remote_payload()
    fingerprint = main_app.resume_fingerprint(payload)
    metadata = sanitized_export_metadata(payload)
    assert len(fingerprint) == 64
    assert metadata["resume_fingerprint"] == fingerprint
    serialized = str(metadata)
    assert "stellar-secret" not in serialized
    assert "access-secret" not in serialized
    assert "secret-secret" not in serialized
