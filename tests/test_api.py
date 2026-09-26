import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main_app
from app import __version__
from app.job_store import JobStore
from app.main import app
from app.stellar import StellarClient


def test_health_exposes_runtime_version():
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "stellar-data-exporter",
        "version": __version__,
    }
    assert app.version == __version__


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
        "tenant_id": "tenant-1",
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
    assert preview.json()["preview_bytes"] > 0
    assert preview.json()["estimated_bytes"] >= preview.json()["preview_bytes"]
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
    status_url = job.json()["status_url"]

    download = client.get(download_url)
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/json")
    assert download.headers["content-disposition"] == 'attachment; filename="alerts.json"'
    rows = download.json()
    assert [row["severity"] for row in rows] == [80, 90]

    status = client.get(status_url)
    assert status.status_code == 200
    metrics = status.json()
    assert metrics["status"] == "completed"
    assert metrics["records_exported"] == 2
    assert metrics["bytes_sent"] > 0
    assert metrics["files_completed"] == 1
    assert metrics["query_count"] == 2
    assert metrics["elapsed_seconds"] >= 0


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


def test_pending_download_job_can_be_cancelled(monkeypatch):
    monkeypatch.setattr(StellarClient, "search", fake_search)
    client = TestClient(app)
    request = {
        **payload(),
        "format": "json",
        "compress": False,
        "filename": "cancel-me",
    }

    created = client.post("/api/export/jobs", json=request)
    assert created.status_code == 200
    body = created.json()
    cancelled = client.post(body["cancel_url"])
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["cancel_requested"] is True

    status = client.get(body["status_url"])
    assert status.status_code == 200
    assert status.json()["status"] == "cancelled"

    download = client.get(body["download_url"])
    assert download.status_code == 409


def test_ndjson_and_csv_advanced_options_flow_through_download_api(monkeypatch):
    monkeypatch.setattr(StellarClient, "search", fake_search)
    client = TestClient(app)

    ndjson_request = {
        **payload(),
        "format": "ndjson",
        "compress": False,
        "filename": "events",
    }
    ndjson_job = client.post("/api/export/jobs", json=ndjson_request)
    ndjson = client.get(ndjson_job.json()["download_url"])
    assert ndjson.status_code == 200
    assert ndjson.headers["content-type"].startswith("application/x-ndjson")
    assert ndjson.headers["content-disposition"] == 'attachment; filename="events.ndjson"'
    lines = ndjson.text.strip().splitlines()
    assert len(lines) == 2
    assert [json.loads(line)["severity"] for line in lines] == [80, 90]

    csv_request = {
        **payload(),
        "format": "csv",
        "compress": False,
        "filename": "events-semicolon",
        "csv_delimiter": ";",
        "csv_include_header": False,
        "csv_bom": True,
    }
    csv_job = client.post("/api/export/jobs", json=csv_request)
    csv_download = client.get(csv_job.json()["download_url"])
    assert csv_download.status_code == 200
    assert csv_download.content.startswith(b"\xef\xbb\xbf")
    first_line = csv_download.content[3:].decode("utf-8").splitlines()[0]
    assert first_line.startswith("2026-09-25T00:00:00+00:00;80;")


def test_persistent_export_history_survives_memory_reset_without_secrets(monkeypatch, tmp_path):
    monkeypatch.setattr(StellarClient, "search", fake_search)
    store_path = tmp_path / "history.sqlite3"
    monkeypatch.setattr(main_app, "JOB_STORE", JobStore(store_path))
    main_app.EXPORT_JOBS.clear()
    client = TestClient(app)

    request = {
        **payload(),
        "token": "api-token-must-not-persist",
        "query": {"query": {"term": {"secret_field": "query-secret-must-not-persist"}}},
        "format": "json",
        "compress": False,
        "filename": "persistent-history",
    }
    created = client.post("/api/export/jobs", json=request)
    assert created.status_code == 200
    body = created.json()
    downloaded = client.get(body["download_url"])
    assert downloaded.status_code == 200

    history = client.get("/api/export/history?limit=10")
    assert history.status_code == 200
    jobs = history.json()["jobs"]
    saved = next(item for item in jobs if item["job_id"] == body["job_id"])
    assert saved["status"] == "completed"
    assert saved["summary"]["destination_type"] == "download"
    assert saved["summary"]["format"] == "json"
    serialized = json.dumps(saved)
    assert "api-token-must-not-persist" not in serialized
    assert "query-secret-must-not-persist" not in serialized

    main_app.EXPORT_JOBS.clear()
    recovered = client.get(body["status_url"])
    assert recovered.status_code == 200
    assert recovered.json()["status"] == "completed"
    assert recovered.json()["records_exported"] == 2

    database_bytes = b"".join(
        candidate.read_bytes()
        for candidate in (store_path, Path(str(store_path) + "-wal"), Path(str(store_path) + "-shm"))
        if candidate.exists()
    )
    assert b"api-token-must-not-persist" not in database_bytes
    assert b"query-secret-must-not-persist" not in database_bytes


def test_user_scope_connection_accepts_api_key_without_email(monkeypatch):
    captured = {}

    async def user_scope_tenants(self):
        captured["auth_mode"] = self.auth_mode
        captured["email"] = self.email
        captured["query_mode"] = self.query_mode
        return [
            {"id": "tenant-1", "name": "Tenant One"},
            {"id": "tenant-2", "name": "Tenant Two"},
        ]

    monkeypatch.setattr(StellarClient, "list_tenants", user_scope_tenants)
    response = TestClient(app).post(
        "/api/connection/test",
        json={
            "host": "https://stellar.example.test",
            "auth_mode": "user_scope",
            "token": "user-api-key",
            "verify_tls": True,
            "sources": ["alerts"],
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["tenant_count"] == 2
    assert response.json()["tenants"][0] == {"id": "tenant-1", "name": "Tenant One"}
    assert captured == {
        "auth_mode": "user_scope",
        "email": None,
        "query_mode": "stellar_lucene",
    }


def test_query_count_preflight_reports_warning_levels(monkeypatch):
    totals = iter([50, 100, 1000])

    async def count_search(self, index, body):
        assert self.tenant_id == "tenant-1"
        assert body["size"] == 0
        assert body["track_total_hits"] is True
        return {
            "took": 7,
            "hits": {
                "total": {"value": next(totals), "relation": "eq"},
                "hits": [],
            },
        }

    monkeypatch.setattr(StellarClient, "search", count_search)
    monkeypatch.setattr(main_app, "LARGE_EXPORT_WARNING_RECORDS", 100)
    monkeypatch.setattr(main_app, "LARGE_EXPORT_CRITICAL_RECORDS", 1000)
    client = TestClient(app)

    normal = client.post("/api/query/count", json=payload())
    warning = client.post("/api/query/count", json=payload())
    critical = client.post("/api/query/count", json=payload())

    assert normal.status_code == 200
    assert normal.json()["total"] == 50
    assert normal.json()["warning_level"] == "normal"
    assert normal.json()["warning"] is None

    assert warning.status_code == 200
    assert warning.json()["total"] == 100
    assert warning.json()["warning_level"] == "warning"
    assert "performance" in warning.json()["warning"].lower()

    assert critical.status_code == 200
    assert critical.json()["total"] == 1000
    assert critical.json()["warning_level"] == "critical"
    assert "significant" in critical.json()["warning"].lower()


def test_query_requires_tenant_selection():
    request = payload()
    request.pop("tenant_id")
    response = TestClient(app).post("/api/query/count", json=request)

    assert response.status_code == 422
    assert "tenant_id" in response.text


def test_web_basic_auth_protects_ui_and_api_but_not_health(monkeypatch):
    monkeypatch.setenv("STELLAR_EXPORTER_UI_AUTH_DISABLED", "0")
    monkeypatch.setenv("STELLAR_EXPORTER_UI_USERNAME", "test-ui-user")
    monkeypatch.setenv("STELLAR_EXPORTER_UI_PASSWORD", "test-ui-password")
    client = TestClient(app)

    health = client.get("/api/health")
    assert health.status_code == 200

    blocked_ui = client.get("/")
    assert blocked_ui.status_code == 401
    assert blocked_ui.headers["www-authenticate"].startswith("Basic ")

    blocked_api = client.get("/api/data-sources")
    assert blocked_api.status_code == 401

    wrong = client.get("/", auth=("test-ui-user", "wrong"))
    assert wrong.status_code == 401

    allowed_ui = client.get("/", auth=("test-ui-user", "test-ui-password"))
    assert allowed_ui.status_code == 200
    assert "Stellar Cyber Data Exporter" in allowed_ui.text

    allowed_api = client.get("/api/data-sources", auth=("test-ui-user", "test-ui-password"))
    assert allowed_api.status_code == 200
