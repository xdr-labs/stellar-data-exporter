from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.stellar import StellarClient


async def fake_search(self, index, body):
    assert index == "aella-ser-*"
    size = body.get("size", 0)
    if size == 0:
        return {"took": 1, "hits": {"total": {"value": 2, "relation": "eq"}, "hits": []}}

    hits = [
        {"_source": {"timestamp": "2026-09-25T00:00:00+00:00", "severity": 80, "srcip": "10.0.0.1"}},
        {"_source": {"timestamp": "2026-09-25T00:00:01+00:00", "severity": 90, "srcip": "10.0.0.2"}},
    ]
    return {
        "took": 2,
        "hits": {
            "total": {"value": 2, "relation": "eq"},
            "hits": hits[:size],
        },
    }


def payload():
    start = datetime(2026, 9, 25, tzinfo=UTC)
    end = start + timedelta(minutes=5)
    return {
        "host": "https://stellar.example.test",
        "email": "admin@example.test",
        "token": "test-token",
        "verify_tls": True,
        "sources": ["alerts"],
        "time_field": "timestamp",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "query": {"query": {"term": {"severity": 80}}},
        "preview_limit": 100,
        "target_records_per_slice": 100,
        "minimum_slice_ms": 1,
    }


def test_preview_and_json_download(monkeypatch):
    monkeypatch.setattr(StellarClient, "search", fake_search)
    client = TestClient(app)

    preview = client.post("/api/query/preview", json=payload())
    assert preview.status_code == 200
    assert preview.json()["total"] == 2
    assert len(preview.json()["rows"]) == 2

    request = {
        **payload(),
        "format": "json",
        "compress": False,
        "filename": "alerts",
    }
    job = client.post("/api/export/jobs", json=request)
    assert job.status_code == 200
    download_url = job.json()["download_url"]

    download = client.get(download_url)
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/json")
    assert download.headers["content-disposition"] == 'attachment; filename="alerts.json"'
    rows = download.json()
    assert [row["severity"] for row in rows] == [80, 90]
