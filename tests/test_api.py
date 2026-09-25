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
    assert preview.json()["fields"] == ["timestamp", "severity", "srcip"]

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


def test_index_plan_endpoint_and_preview_use_date_scoped_target(monkeypatch):
    seen = []

    async def capture_search(self, index, body):
        seen.append(index)
        return {
            "took": 1,
            "hits": {"total": {"value": 0, "relation": "eq"}, "hits": []},
        }

    monkeypatch.setattr(StellarClient, "search", capture_search)
    client = TestClient(app)
    request = payload()
    request["sources"] = ["windows_events"]
    request["start"] = datetime(2026, 9, 23, tzinfo=UTC).isoformat()
    request["end"] = datetime(2026, 9, 26, tzinfo=UTC).isoformat()

    plan = client.post(
        "/api/query/index-plan",
        json={
            "sources": request["sources"],
            "start": request["start"],
            "end": request["end"],
        },
    )
    assert plan.status_code == 200
    assert plan.json()["sources"][0]["day_count"] == 3

    preview = client.post("/api/query/preview", json=request)
    assert preview.status_code == 200
    assert seen == [
        (
            "aella-wineventlog-2026-09-23-*,"
            "aella-wineventlog-2026-09-24-*,"
            "aella-wineventlog-2026-09-25-*"
        )
    ]


def test_stellar_lucene_preview_compiles_query_and_keeps_managed_time_filter(monkeypatch):
    captured = {}

    async def capture_search(self, index, body):
        captured["index"] = index
        captured["body"] = body
        return {
            "took": 4,
            "hits": {"total": {"value": 0, "relation": "eq"}, "hits": []},
        }

    monkeypatch.setattr(StellarClient, "search", capture_search)
    client = TestClient(app)
    request = payload()
    request.update({
        "query_mode": "stellar_lucene",
        "query": {},
        "stellar_query": 'event_status:New AND event_name:"Login Failure"',
    })

    response = client.post("/api/query/preview", json=request)
    assert response.status_code == 200
    must = captured["body"]["query"]["bool"]["must"][0]
    assert must == {
        "query_string": {
            "query": 'event_status:New AND event_name:"Login Failure"'
        }
    }
    assert captured["body"]["query"]["bool"]["filter"][0]["range"]["timestamp"]


def test_selected_fields_filter_stellar_source_and_csv_column_order(monkeypatch):
    captured_bodies = []

    async def selected_search(self, index, body):
        captured_bodies.append(body)
        size = body.get("size", 0)
        if size == 0:
            return {
                "took": 1,
                "hits": {"total": {"value": 2, "relation": "eq"}, "hits": []},
            }
        hits = [
            {
                "_source": {
                    "timestamp": "2026-09-25T00:00:00+00:00",
                    "severity": 80,
                    "srcip": "10.0.0.1",
                    "metadata": {"user": "alice"},
                }
            },
            {
                "_source": {
                    "timestamp": "2026-09-25T00:00:01+00:00",
                    "severity": 90,
                    "srcip": "10.0.0.2",
                    "metadata": {"user": "bob"},
                }
            },
        ]
        return {
            "took": 2,
            "hits": {
                "total": {"value": 2, "relation": "eq"},
                "hits": hits[:size],
            },
        }

    monkeypatch.setattr(StellarClient, "search", selected_search)
    client = TestClient(app)
    request = {
        **payload(),
        "format": "csv",
        "compress": False,
        "filename": "selected",
        "selected_fields": ["srcip", "metadata.user", "timestamp"],
    }

    job = client.post("/api/export/jobs", json=request)
    assert job.status_code == 200
    download = client.get(job.json()["download_url"])
    assert download.status_code == 200
    lines = download.text.strip().splitlines()
    assert lines[0] == "srcip,metadata.user,timestamp"
    assert lines[1].startswith("10.0.0.1,alice,")
    assert captured_bodies
    assert all(
        body["_source"] == ["srcip", "metadata.user", "timestamp"]
        for body in captured_bodies
    )


def test_selected_fields_json_preserves_nested_shape(monkeypatch):
    async def nested_search(self, index, body):
        size = body.get("size", 0)
        if size == 0:
            return {
                "took": 1,
                "hits": {"total": {"value": 1, "relation": "eq"}, "hits": []},
            }
        return {
            "took": 2,
            "hits": {
                "total": {"value": 1, "relation": "eq"},
                "hits": [{
                    "_source": {
                        "timestamp": "2026-09-25T00:00:00+00:00",
                        "srcip": "10.0.0.1",
                        "metadata": {
                            "user": "alice",
                            "geo": {"country": "KR", "city": "Seoul"},
                        },
                    }
                }],
            },
        }

    monkeypatch.setattr(StellarClient, "search", nested_search)
    client = TestClient(app)
    request = {
        **payload(),
        "format": "json",
        "compress": False,
        "filename": "selected-json",
        "selected_fields": ["metadata.geo.country", "srcip"],
    }

    job = client.post("/api/export/jobs", json=request)
    assert job.status_code == 200
    download = client.get(job.json()["download_url"])
    assert download.status_code == 200
    assert download.json() == [
        {"metadata": {"geo": {"country": "KR"}}, "srcip": "10.0.0.1"}
    ]


def test_record_limit_stops_download_at_exact_n(monkeypatch):
    monkeypatch.setattr(StellarClient, "search", fake_search)
    client = TestClient(app)
    request = {
        **payload(),
        "format": "json",
        "compress": False,
        "filename": "limited",
        "record_limit": 1,
    }

    job = client.post("/api/export/jobs", json=request)
    assert job.status_code == 200
    download = client.get(job.json()["download_url"])
    assert download.status_code == 200
    rows = download.json()
    assert len(rows) == 1
    assert rows[0]["srcip"] == "10.0.0.1"
