from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask

from .destinations import test_s3, test_sftp, upload_s3, upload_sftp
from .exporter import (
    ExportEngine,
    csv_stream,
    discover_fields,
    file_stream,
    gzip_stream,
    iter_export_part_files,
    json_stream,
    project_records,
)
from .models import (
    ConnectionInput,
    DestinationTestInput,
    DownloadDestination,
    ExportInput,
    IndexPlanInput,
    QueryInput,
    S3Destination,
    SFTPDestination,
)
from .index_planner import plan_indices
from .query import build_document_query, compile_user_query, hit_source, total_hits
from .sources import resolve_indices, source_catalog, source_labels
from .stellar import (
    StellarAPIError,
    StellarAuthError,
    StellarConnectionError,
    StellarPermissionError,
    StellarClient,
)


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
DOWNLOAD_JOB_TTL_SECONDS = 600
HISTORY_JOB_TTL_SECONDS = 3600


@dataclass
class ExportJob:
    created_at: float
    payload: ExportInput | None
    status: str = "pending"
    bytes_sent: int = 0
    result: str | None = None
    error: str | None = None
    task: asyncio.Task | None = field(default=None, repr=False)


EXPORT_JOBS: dict[str, ExportJob] = {}
app = FastAPI(title="Stellar Data Exporter", version="0.1.0")


def client_for(payload: ConnectionInput | QueryInput) -> StellarClient:
    return StellarClient(
        str(payload.host),
        payload.email,
        payload.token,
        payload.verify_tls,
    )


def cleanup_jobs() -> None:
    now = time.time()
    for job_id, job in list(EXPORT_JOBS.items()):
        age = now - job.created_at
        if job.status == "pending" and job.payload is not None and age > DOWNLOAD_JOB_TTL_SECONDS:
            EXPORT_JOBS.pop(job_id, None)
        elif job.status in {"completed", "failed"} and age > HISTORY_JOB_TTL_SECONDS:
            EXPORT_JOBS.pop(job_id, None)


def safe_filename(name: str | None, fmt: str, compressed: bool) -> str:
    fallback = f"stellar-export.{fmt}"
    candidate = (name or fallback).strip()
    candidate = re.sub(r"[^A-Za-z0-9._-]+", "-", candidate).strip(".-") or fallback
    if compressed and candidate.lower().endswith(".gz"):
        candidate = candidate[:-3]
    if not candidate.lower().endswith(f".{fmt}"):
        candidate += f".{fmt}"
    if compressed:
        candidate += ".gz"
    return candidate


def build_export_source(payload: ExportInput):
    client = client_for(payload)
    raw_query = compile_user_query(
        payload.query_mode,
        payload.query,
        payload.stellar_query,
    )
    if payload.selected_fields:
        raw_query["_source"] = list(payload.selected_fields)

    engine = ExportEngine(
        client,
        index=plan_indices(payload.sources, start=payload.start, end=payload.end).target,
        raw_query=raw_query,
        time_field=payload.time_field,
        start=payload.start,
        end=payload.end,
        target_records=payload.target_records_per_slice,
        minimum_slice_ms=payload.minimum_slice_ms,
        max_records=payload.record_limit,
    )

    preferred_fields = None
    requested_source = raw_query.get("_source")
    if isinstance(requested_source, list):
        preferred_fields = [str(field) for field in requested_source]

    records = engine.iter_documents()
    if payload.selected_fields:
        records = project_records(records, payload.selected_fields)
        preferred_fields = list(payload.selected_fields)

    content_type = "text/csv" if payload.format == "csv" else "application/json"
    filename = safe_filename(payload.filename, payload.format, payload.compress)
    return records, preferred_fields, content_type, filename


def build_output(payload: ExportInput):
    records, preferred_fields, content_type, filename = build_export_source(payload)
    if payload.format == "csv":
        stream = csv_stream(records, preferred_fields)
    else:
        stream = json_stream(records)

    if payload.compress:
        stream = gzip_stream(stream)

    return stream, content_type, filename


def build_output_parts(payload: ExportInput):
    if payload.max_file_size_bytes is None:
        raise ValueError("Split output requires max_file_size_bytes")
    records, preferred_fields, content_type, filename = build_export_source(payload)
    parts = iter_export_part_files(
        records,
        format=payload.format,
        preferred_fields=preferred_fields,
        compress=payload.compress,
        base_filename=filename,
        max_bytes=payload.max_file_size_bytes,
    )
    return parts, content_type, filename


async def run_destination_job(job_id: str) -> None:
    job = EXPORT_JOBS.get(job_id)
    if job is None or job.payload is None:
        return

    payload = job.payload
    job.status = "running"

    def add_bytes(count: int) -> None:
        job.bytes_sent += count

    async def upload_one(
        filename: str,
        stream,
        content_type: str,
    ) -> str:
        if isinstance(payload.destination, S3Destination):
            return await upload_s3(
                payload.destination,
                filename,
                stream,
                content_type=content_type,
                content_encoding="gzip" if payload.compress else None,
                on_bytes=add_bytes,
            )
        if isinstance(payload.destination, SFTPDestination):
            return await upload_sftp(
                payload.destination,
                filename,
                stream,
                on_bytes=add_bytes,
            )
        raise RuntimeError("Unsupported background destination")

    try:
        if payload.max_file_size_bytes is None:
            stream, content_type, filename = build_output(payload)
            job.result = await upload_one(filename, stream, content_type)
        else:
            parts, content_type, _ = build_output_parts(payload)
            results: list[str] = []
            async for part in parts:
                try:
                    results.append(
                        await upload_one(
                            part.filename,
                            file_stream(part.path),
                            content_type,
                        )
                    )
                finally:
                    if os.path.exists(part.path):
                        os.unlink(part.path)

            if len(results) == 1:
                job.result = results[0]
            else:
                job.result = (
                    f"{len(results)} files: {results[0]} ... {results[-1]}"
                )
        job.status = "completed"
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)[:2000]
    finally:
        job.payload = None


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/app.js")
async def app_js() -> FileResponse:
    return FileResponse(STATIC_DIR / "app.js", media_type="application/javascript")


@app.get("/styles.css")
async def styles_css() -> FileResponse:
    return FileResponse(STATIC_DIR / "styles.css", media_type="text/css")


@app.get("/stellar-cyber-logo.svg")
async def stellar_cyber_logo() -> FileResponse:
    return FileResponse(STATIC_DIR / "stellar-cyber-logo.svg", media_type="image/svg+xml")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "stellar-data-exporter"}


@app.get("/api/data-sources")
async def data_sources() -> list[dict[str, str]]:
    return source_catalog()


def stellar_http_error(exc: StellarAPIError) -> HTTPException:
    if isinstance(exc, StellarAuthError):
        return HTTPException(status_code=401, detail=str(exc))
    if isinstance(exc, StellarPermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, StellarConnectionError):
        return HTTPException(status_code=502, detail=str(exc))
    return HTTPException(status_code=502, detail=str(exc))


@app.post("/api/connection/test")
async def test_connection(payload: ConnectionInput) -> dict[str, Any]:
    body = {"size": 0, "track_total_hits": False, "query": {"match_all": {}}}
    indices = resolve_indices(payload.sources)
    try:
        response = await client_for(payload).search(indices, body)
    except StellarAPIError as exc:
        raise stellar_http_error(exc) from exc
    return {
        "ok": True,
        "sources": source_labels(payload.sources),
        "took_ms": response.get("took"),
    }


@app.post("/api/destination/test")
async def test_destination(payload: DestinationTestInput) -> dict[str, Any]:
    try:
        if isinstance(payload.destination, DownloadDestination):
            return {"ok": True, "message": "Browser download requires no remote connection."}
        if isinstance(payload.destination, S3Destination):
            await test_s3(payload.destination)
            return {"ok": True, "message": f"Bucket {payload.destination.bucket} is reachable."}
        if isinstance(payload.destination, SFTPDestination):
            await test_sftp(payload.destination)
            return {"ok": True, "message": f"SFTP path {payload.destination.remote_path} is reachable."}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)[:2000]) from exc
    raise HTTPException(status_code=400, detail="Unsupported destination")


@app.post("/api/query/index-plan")
async def index_plan(payload: IndexPlanInput) -> dict[str, Any]:
    return plan_indices(
        payload.sources,
        start=payload.start,
        end=payload.end,
    ).as_dict()


@app.post("/api/query/preview")
async def preview(payload: QueryInput) -> dict[str, Any]:
    raw_query = compile_user_query(
        payload.query_mode,
        payload.query,
        payload.stellar_query,
    )
    body = build_document_query(
        raw_query,
        time_field=payload.time_field,
        start=payload.start,
        end=payload.end,
        size=payload.preview_limit,
        track_total_hits=True,
    )
    index_plan_result = plan_indices(payload.sources, start=payload.start, end=payload.end)
    indices = index_plan_result.target
    try:
        response = await client_for(payload).search(indices, body)
    except StellarAPIError as exc:
        raise stellar_http_error(exc) from exc

    total, exact = total_hits(response)
    rows = [hit_source(hit) for hit in response.get("hits", {}).get("hits", [])]
    sample_bytes = sum(
        len(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        for row in rows
    )
    estimated_bytes = int((sample_bytes / max(len(rows), 1)) * total) if rows else 0
    warnings = list(index_plan_result.warnings)
    if (payload.end - payload.start).total_seconds() > 86400:
        warnings.append(
            "A range longer than 24 hours can scan many historical shards across the selected data sources. "
            "Use the shortest practical time range for large exports."
        )

    return {
        "ok": True,
        "total": total,
        "total_exact": exact,
        "took_ms": response.get("took"),
        "preview_bytes": sample_bytes,
        "estimated_bytes": estimated_bytes,
        "rows": rows,
        "fields": discover_fields(rows),
        "warnings": warnings,
        "index_plan": index_plan_result.as_dict(),
    }


@app.post("/api/export/jobs")
async def create_export_job(payload: ExportInput) -> dict[str, str]:
    cleanup_jobs()
    job_id = uuid.uuid4().hex
    job = ExportJob(created_at=time.time(), payload=payload)
    EXPORT_JOBS[job_id] = job

    if isinstance(payload.destination, DownloadDestination):
        return {
            "job_id": job_id,
            "mode": "download",
            "download_url": f"/api/export/jobs/{job_id}/download",
        }

    job.task = asyncio.create_task(run_destination_job(job_id))
    return {
        "job_id": job_id,
        "mode": "background",
        "status_url": f"/api/export/jobs/{job_id}",
    }


@app.get("/api/export/jobs/{job_id}")
async def export_job_status(job_id: str) -> dict[str, Any]:
    cleanup_jobs()
    job = EXPORT_JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Export job not found or expired")
    return {
        "job_id": job_id,
        "status": job.status,
        "bytes_sent": job.bytes_sent,
        "result": job.result,
        "error": job.error,
    }


@app.get("/api/export/jobs/{job_id}/download")
async def download_export(job_id: str):
    cleanup_jobs()
    job = EXPORT_JOBS.pop(job_id, None)
    if job is None or job.payload is None:
        raise HTTPException(status_code=404, detail="Export job not found or expired")
    if not isinstance(job.payload.destination, DownloadDestination):
        raise HTTPException(status_code=400, detail="This job is not a browser download")

    payload = job.payload
    if payload.max_file_size_bytes is None:
        stream, content_type, filename = build_output(payload)
        media_type = "application/gzip" if payload.compress else content_type
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return StreamingResponse(stream, media_type=media_type, headers=headers)

    parts, content_type, filename = build_output_parts(payload)
    completed_parts = [part async for part in parts]

    if len(completed_parts) == 1:
        part = completed_parts[0]
        media_type = "application/gzip" if payload.compress else content_type
        return FileResponse(
            part.path,
            media_type=media_type,
            filename=part.filename,
            background=BackgroundTask(os.unlink, part.path),
        )

    archive = tempfile.NamedTemporaryFile(
        prefix="stellar-export-",
        suffix=".zip",
        delete=False,
    )
    archive_path = archive.name
    archive.close()

    try:
        with zipfile.ZipFile(
            archive_path,
            "w",
            compression=zipfile.ZIP_STORED,
        ) as bundle:
            for part in completed_parts:
                bundle.write(part.path, arcname=part.filename)
    finally:
        for part in completed_parts:
            if os.path.exists(part.path):
                os.unlink(part.path)

    archive_name = re.sub(
        r"(\.csv|\.json)(\.gz)?$",
        "",
        filename,
        flags=re.IGNORECASE,
    )
    archive_name = f"{archive_name}-parts.zip"
    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename=archive_name,
        background=BackgroundTask(os.unlink, archive_path),
    )
