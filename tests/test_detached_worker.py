import csv
import io
import json
import os
import threading
import time
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

import app.main as main_app
from app.main import app


class FakeStellarHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        return

    def _json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path == "/connect/api/v1/access_token":
            assert self.headers.get("Authorization") == "Bearer user-api-key"
            self._json(200, {"access_token": "worker-jwt"})
            return
        self._json(404, {"detail": "not found"})

    def do_GET(self):
        parsed = urlparse(self.path)
        if not parsed.path.endswith("/_search"):
            self._json(404, {"detail": "not found"})
            return

        assert self.headers.get("Authorization") == "Bearer worker-jwt"
        params = parse_qs(parsed.query)
        size = int(params.get("size", ["0"])[0])
        track = params.get("track_total_hits", ["false"])[0]

        if size == 0:
            time.sleep(0.25)
            self._json(
                200,
                {"hits": {"total": {"value": 20, "relation": "eq"}, "hits": []}},
            )
            return

        # Keep the detached worker alive long enough to close/re-open the API
        # TestClient and verify it is not tied to the web process lifecycle.
        time.sleep(1.0)
        hits = [
            {
                "_index": "aella-adr-2026.09.25",
                "_id": f"event-{i}",
                "_source": {
                    "timestamp": f"2026-09-25T00:00:{i:02d}+00:00",
                    "event": f"traffic-{i}",
                    "bytes": i,
                },
            }
            for i in range(20)
        ]
        assert track == "false"
        self._json(
            200,
            {
                "hits": {
                    "total": {"value": 20, "relation": "gte"},
                    "hits": hits[:size],
                }
            },
        )


def _payload(port):
    start = datetime(2026, 9, 25, tzinfo=UTC)
    return {
        "host": f"http://127.0.0.1:{port}",
        "auth_mode": "user_scope",
        "email": None,
        "token": "user-api-key",
        "verify_tls": False,
        "sources": ["traffic"],
        "tenant_id": "tenant-1",
        "time_field": "timestamp",
        "start": start.isoformat(),
        "end": (start + timedelta(minutes=5)).isoformat(),
        "query_mode": "stellar_lucene",
        "stellar_query": "*",
        "query": {"query": {"match_all": {}}},
        "preview_limit": 100,
        "target_records_per_slice": 1000,
        "minimum_slice_ms": 1,
        "format": "csv",
        "filename": "detached-restart.csv",
        "destination": {"type": "download"},
    }


def test_detached_browser_download_survives_api_lifecycle(monkeypatch):
    monkeypatch.setenv("STELLAR_EXPORTER_DETACHED_JOBS", "1")
    main_app.EXPORT_JOBS.clear()
    main_app.ACTIVE_SCHEDULE_RUNS.clear()

    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeStellarHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]

    try:
        with TestClient(app) as client:
            created = client.post("/api/export/jobs", json=_payload(port))
            assert created.status_code == 200
            body = created.json()
            job_id = body["job_id"]

            # Detached jobs do not live in the API process task dictionary.
            assert job_id not in main_app.EXPORT_JOBS

            record = main_app.JOB_STORE.get(job_id)
            assert record is not None
            assert record["worker_pid"]
            assert "user-api-key" not in json.dumps(record)

            cmdline = open(
                f"/proc/{record['worker_pid']}/cmdline",
                "rb",
            ).read()
            assert b"user-api-key" not in cmdline
            assert b"app.job_worker" in cmdline

            # A web-process restart must not mark a live worker interrupted.
            assert main_app.recover_orphaned_export_jobs() == 0

        # Closing the TestClient runs FastAPI lifespan shutdown. The worker must
        # continue independently and finish through the same SQLite job store.
        deadline = time.time() + 15
        while time.time() < deadline:
            record = main_app.JOB_STORE.get(job_id)
            if record and record["status"] in {"completed", "failed", "cancelled", "interrupted"}:
                break
            time.sleep(0.05)

        assert record["status"] == "completed", record
        assert record["records_exported"] == 20
        assert record["files_completed"] == 1
        assert record["download_path"]
        assert os.path.exists(record["download_path"])

        # Re-open the API after the simulated restart and download the durable
        # artifact from DB-backed state rather than process memory.
        with TestClient(app) as client:
            status = client.get(body["status_url"])
            assert status.status_code == 200
            assert status.json()["status"] == "completed"
            assert status.json()["records_exported"] == 20

            download = client.get(body["download_url"])
            assert download.status_code == 200
            assert download.headers["content-disposition"] == (
                'attachment; filename="detached-restart.csv"'
            )
            rows = list(csv.DictReader(io.StringIO(download.text)))
            assert len(rows) == 20
            assert rows[0]["event"] == "traffic-0"
            assert rows[-1]["event"] == "traffic-19"
    finally:
        server.shutdown()
        server.server_close()


def test_detached_worker_honors_db_backed_cancel(monkeypatch):
    monkeypatch.setenv("STELLAR_EXPORTER_DETACHED_JOBS", "1")
    main_app.EXPORT_JOBS.clear()
    main_app.ACTIVE_SCHEDULE_RUNS.clear()

    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeStellarHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]

    try:
        with TestClient(app) as client:
            created = client.post("/api/export/jobs", json=_payload(port))
            assert created.status_code == 200
            job_id = created.json()["job_id"]

            cancelled = client.post(f"/api/export/jobs/{job_id}/cancel")
            assert cancelled.status_code == 200
            assert cancelled.json()["cancel_requested"] is True

            deadline = time.time() + 10
            while time.time() < deadline:
                status = client.get(f"/api/export/jobs/{job_id}").json()
                if status["status"] not in {"pending", "running"}:
                    break
                time.sleep(0.1)

            assert status["status"] == "cancelled", status
            assert status["records_exported"] == 0
    finally:
        server.shutdown()
        server.server_close()
