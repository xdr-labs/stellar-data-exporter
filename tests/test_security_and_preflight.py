from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

import app.main as main_app
from app.main import app
from app.stellar import StellarClient


def query_payload():
    start = datetime(2026, 9, 25, tzinfo=UTC)
    return {
        "host": "https://stellar.example.test",
        "email": "admin@example.test",
        "token": "test-token",
        "verify_tls": True,
        "sources": ["alerts"],
        "tenant_id": "tenant-1",
        "time_field": "timestamp",
        "start": start.isoformat(),
        "end": (start + timedelta(hours=1)).isoformat(),
        "query": {"query": {"match_all": {}}},
        "preview_limit": 100,
        "target_records_per_slice": 5000,
        "minimum_slice_ms": 1,
    }


def test_ui_and_read_only_api_need_no_exporter_login_even_with_legacy_auth_env(monkeypatch):
    # Legacy Exporter account variables must not restore an obsolete Basic Auth gate.
    monkeypatch.setenv("STELLAR_EXPORTER_UI_AUTH_DISABLED", "0")
    monkeypatch.setenv("STELLAR_EXPORTER_UI_USERNAME", "old-user")
    monkeypatch.setenv("STELLAR_EXPORTER_UI_PASSWORD", "old-password")
    monkeypatch.setenv("STELLAR_EXPORTER_WEB_USERNAME", "old-user")
    monkeypatch.setenv("STELLAR_EXPORTER_WEB_PASSWORD", "old-password")
    client = TestClient(app)

    for path in ("/", "/api/health", "/api/data-sources", "/api/export/history", "/api/schedules"):
        result = client.get(path)
        assert result.status_code == 200, (path, result.text)
        assert "www-authenticate" not in result.headers
    assert "Stellar Cyber Data Exporter" in client.get("/").text


def test_count_preflight_is_tenant_scoped_and_returns_critical_warning(monkeypatch):
    captured = {}

    async def fake_search(self, index, body):
        captured["tenant_id"] = self.tenant_id
        captured["index"] = index
        captured["size"] = body["size"]
        captured["track_total_hits"] = body["track_total_hits"]
        return {
            "took": 17,
            "hits": {
                "total": {"value": 1_500_000, "relation": "eq"},
                "hits": [],
            },
        }

    monkeypatch.setattr(StellarClient, "search", fake_search)
    response = TestClient(app).post("/api/query/count", json=query_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1_500_000
    assert body["warning_level"] == "critical"
    assert "performance degradation" in body["warning"].lower()
    assert captured == {
        "tenant_id": "tenant-1",
        "index": "aella-ser-*",
        "size": 0,
        "track_total_hits": True,
    }


def test_query_and_export_require_tenant_selection():
    payload = query_payload()
    payload.pop("tenant_id")

    response = TestClient(app).post("/api/query/count", json=payload)
    assert response.status_code == 422
    assert "tenant_id" in response.text


def test_server_does_not_expose_shared_connection_settings():
    client = TestClient(app)
    payload = {
        "host": "https://stellar.example.test",
        "auth_mode": "user_scope",
        "email": None,
        "token": "must-remain-browser-session-only",
        "verify_tls": True,
        "tenant_id": "tenant-42",
        "tenant_name": "Tenant 42",
    }

    assert client.get("/api/settings/stellar-connection").status_code == 404
    assert client.put("/api/settings/stellar-connection", json=payload).status_code == 404
    assert client.delete("/api/settings/stellar-connection").status_code == 404
