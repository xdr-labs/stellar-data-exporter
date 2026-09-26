from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

import app.main as main_app
from app.job_store import JobStore
from app.main import app


def export_request(start, end, *, policy="allow", query=None):
    return {
        "host": "https://stellar.example.test",
        "email": "admin@example.test",
        "token": "x",
        "verify_tls": True,
        "sources": ["alerts"],
        "tenant_id": "tenant-1",
        "time_field": "timestamp",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "query": query or {"query": {"match_all": {}}},
        "format": "json",
        "filename": "overlap-export",
        "overlap_policy": policy,
        "destination": {"type": "download"},
    }


def test_reject_overlap_blocks_matching_pipeline_but_allows_adjacent_and_different_query(monkeypatch, tmp_path):
    store = JobStore(tmp_path / "overlap.sqlite3")
    monkeypatch.setattr(main_app, "JOB_STORE", store)
    main_app.EXPORT_JOBS.clear()
    client = TestClient(app)

    start = datetime(2026, 9, 25, 0, 0, tzinfo=UTC)
    end = start + timedelta(hours=1)

    first = client.post("/api/export/jobs", json=export_request(start, end))
    assert first.status_code == 200

    overlapping = client.post(
        "/api/export/jobs",
        json=export_request(
            start + timedelta(minutes=30),
            end + timedelta(minutes=30),
            policy="reject",
        ),
    )
    assert overlapping.status_code == 409
    detail = overlapping.json()["detail"]
    assert "overlaps an existing matching export" in detail["message"]
    assert detail["conflicts"][0]["job_id"] == first.json()["job_id"]

    adjacent = client.post(
        "/api/export/jobs",
        json=export_request(end, end + timedelta(hours=1), policy="reject"),
    )
    assert adjacent.status_code == 200

    different_query = client.post(
        "/api/export/jobs",
        json=export_request(
            start + timedelta(minutes=15),
            end + timedelta(minutes=15),
            policy="reject",
            query={"query": {"term": {"severity": 90}}},
        ),
    )
    assert different_query.status_code == 200


def test_failed_without_checkpoint_does_not_block_but_partial_failed_export_does(tmp_path):
    store = JobStore(tmp_path / "partial-overlap.sqlite3")
    start = datetime(2026, 9, 25, 0, 0, tzinfo=UTC)
    end = start + timedelta(hours=1)
    fingerprint = "pipeline-fingerprint"

    base = {
        "created_at": start.timestamp(),
        "started_at": start.timestamp(),
        "completed_at": end.timestamp(),
        "bytes_sent": 0,
        "records_exported": 0,
        "files_completed": 0,
        "query_count": 0,
        "retry_count": 0,
        "duplicates_skipped": 0,
        "current_slice_start": None,
        "current_slice_end": None,
        "cancel_requested": False,
        "result": None,
        "error": "failed",
        "metadata": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "overlap_fingerprint": fingerprint,
        },
    }

    store.save({
        **base,
        "job_id": "empty-failure",
        "status": "failed",
        "completed_parts": [],
    })
    assert store.find_overlaps(fingerprint, start, end) == []

    completed_part = {
        "part_number": 1,
        "filename": "part-0001.json",
        "size_bytes": 100,
        "sha256": "abc",
        "result": "remote-part-0001",
    }
    store.save({
        **base,
        "job_id": "partial-failure",
        "status": "failed",
        "files_completed": 1,
        "completed_parts": [completed_part],
    })
    conflicts = store.find_overlaps(fingerprint, start, end)
    assert [item["job_id"] for item in conflicts] == ["partial-failure"]
