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


def test_web_basic_auth_protects_ui_and_api_but_not_health(monkeypatch):
    monkeypatch.delenv("STELLAR_EXPORTER_UI_AUTH_DISABLED", raising=False)
    monkeypatch.setenv("STELLAR_EXPORTER_WEB_USERNAME", "test-user")
    monkeypatch.setenv("STELLAR_EXPORTER_WEB_PASSWORD", "test-password")
    client = TestClient(app)

    health = client.get("/api/health")
    assert health.status_code == 200

    unauthenticated = client.get("/")
    assert unauthenticated.status_code == 401
    assert unauthenticated.headers["www-authenticate"].startswith("Basic ")

    wrong = client.get("/", auth=("test-user", "wrong"))
    assert wrong.status_code == 401

    authenticated = client.get("/", auth=("test-user", "test-password"))
    assert authenticated.status_code == 200
    assert "Stellar Cyber Data Exporter" in authenticated.text


def test_web_auth_defaults_to_stellar_credentials(monkeypatch):
    monkeypatch.delenv("STELLAR_EXPORTER_UI_AUTH_DISABLED", raising=False)
    monkeypatch.delenv("STELLAR_EXPORTER_UI_USERNAME", raising=False)
    monkeypatch.delenv("STELLAR_EXPORTER_UI_PASSWORD", raising=False)
    monkeypatch.delenv("STELLAR_EXPORTER_WEB_USERNAME", raising=False)
    monkeypatch.delenv("STELLAR_EXPORTER_WEB_PASSWORD", raising=False)
    client = TestClient(app)

    unauthenticated = client.get("/")
    assert unauthenticated.status_code == 401

    wrong = client.get("/", auth=("stellar", "wrong"))
    assert wrong.status_code == 401

    authenticated = client.get("/", auth=("stellar", "stellar"))
    assert authenticated.status_code == 200


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


def test_saved_stellar_connection_is_encrypted_and_round_trips():
    client = TestClient(app)
    client.delete("/api/settings/stellar-connection")
    payload = {
        "host": "https://stellar.example.test",
        "auth_mode": "user_scope",
        "email": None,
        "token": "saved-user-api-key",
        "verify_tls": True,
        "tenant_id": "tenant-42",
        "tenant_name": "Tenant 42",
    }

    saved = client.put("/api/settings/stellar-connection", json=payload)
    assert saved.status_code == 200
    assert saved.json()["saved"] is True

    raw = main_app.CONNECTION_SETTINGS_PATH.read_bytes()
    assert b"saved-user-api-key" not in raw
    assert b"tenant-42" not in raw
    assert main_app.CONNECTION_SETTINGS_PATH.stat().st_mode & 0o777 == 0o600

    loaded = client.get("/api/settings/stellar-connection")
    assert loaded.status_code == 200
    connection = loaded.json()["connection"]
    assert connection["auth_mode"] == "user_scope"
    assert connection["token"] == "saved-user-api-key"
    assert connection["tenant_id"] == "tenant-42"
    assert connection["tenant_name"] == "Tenant 42"

    deleted = client.delete("/api/settings/stellar-connection")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get("/api/settings/stellar-connection").json() == {
        "saved": False,
        "connection": None,
    }
