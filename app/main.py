from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import tempfile
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from .destinations import (
    build_s3_key,
    build_sftp_path,
    test_s3,
    test_sftp,
    upload_s3,
    upload_sftp,
)
from .exporter import (
    ExportCancelled,
    ExportEngine,
    csv_stream,
    discover_fields,
    file_stream,
    gzip_stream,
    iter_export_part_files,
    json_stream,
    ndjson_stream,
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
    ScheduleCreateInput,
    ScheduleUpdateInput,
    SFTPDestination,
)
from .index_planner import plan_indices
from .job_store import JobStore
from .paths import default_state_dir
from .schedule_store import ScheduleCipher, ScheduleStore
from .query import build_document_query, compile_user_query, hit_source, total_hits
from .sources import resolve_indices, source_catalog, source_labels
from .stellar import (
    StellarAPIError,
    StellarAuthError,
    StellarConnectionError,
    StellarPermissionError,
    StellarClient,
)


PACKAGE_DIR = Path(__file__).resolve().parent
BASE_DIR = PACKAGE_DIR.parent
STATIC_DIR = PACKAGE_DIR / "static"
STATE_DIR = default_state_dir(PACKAGE_DIR)
DOWNLOAD_JOB_TTL_SECONDS = 600
HISTORY_JOB_TTL_SECONDS = 3600
JOB_DB_PATH = Path(os.environ.get("STELLAR_EXPORTER_JOB_DB", str(STATE_DIR / "export-jobs.sqlite3")))
SCHEDULE_DB_PATH = Path(
    os.environ.get(
        "STELLAR_EXPORTER_SCHEDULE_DB",
        str(STATE_DIR / "export-schedules.sqlite3"),
    )
)
SCHEDULE_KEY_PATH = Path(
    os.environ.get(
        "STELLAR_EXPORTER_SCHEDULE_KEY_FILE",
        str(STATE_DIR / "schedule.key"),
    )
)
SCHEDULE_POLL_SECONDS = max(
    1.0,
    float(os.environ.get("STELLAR_EXPORTER_SCHEDULE_POLL_SECONDS", "30")),
)
JOB_STORE = JobStore(JOB_DB_PATH)
JOB_STORE.recover_interrupted()
SCHEDULE_STORE = ScheduleStore(SCHEDULE_DB_PATH)
SCHEDULE_CIPHER = ScheduleCipher.from_environment(SCHEDULE_KEY_PATH)
LOGGER = logging.getLogger("stellar-data-exporter")


@dataclass
class ExportJob:
    job_id: str
    created_at: float
    payload: ExportInput | None
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    started_at: float | None = None
    completed_at: float | None = None
    bytes_sent: int = 0
    records_exported: int = 0
    files_completed: int = 0
    query_count: int = 0
    retry_count: int = 0
    duplicates_skipped: int = 0
    current_slice_start: str | None = None
    current_slice_end: str | None = None
    cancel_requested: bool = False
    result: str | None = None
    error: str | None = None
    completed_parts: list[dict[str, Any]] = field(default_factory=list)
    task: asyncio.Task | None = field(default=None, repr=False)
    last_persisted_at: float = field(default=0.0, repr=False)


EXPORT_JOBS: dict[str, ExportJob] = {}
ACTIVE_SCHEDULE_RUNS: dict[str, asyncio.Task] = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    loop_task = asyncio.create_task(schedule_loop())
    try:
        yield
    finally:
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass
        active = list(ACTIVE_SCHEDULE_RUNS.values())
        for task in active:
            task.cancel()
        if active:
            await asyncio.gather(*active, return_exceptions=True)


app = FastAPI(title="Stellar Data Exporter", version="0.1.0", lifespan=lifespan)


def client_for(
    payload: ConnectionInput | QueryInput,
    *,
    on_retry=None,
) -> StellarClient:
    return StellarClient(
        str(payload.host),
        payload.email,
        payload.token,
        payload.verify_tls,
        on_retry=on_retry,
    )


def destination_fingerprint_target(payload: ExportInput) -> dict[str, Any]:
    if isinstance(payload.destination, S3Destination):
        return {
            "type": "s3",
            "endpoint_url": payload.destination.endpoint_url,
            "region": payload.destination.region,
            "bucket": payload.destination.bucket,
            "prefix": payload.destination.prefix,
            "force_path_style": payload.destination.force_path_style,
        }
    if isinstance(payload.destination, SFTPDestination):
        return {
            "type": "sftp",
            "host": payload.destination.host,
            "port": payload.destination.port,
            "username": payload.destination.username,
            "remote_path": payload.destination.remote_path,
            "verify_host_key": payload.destination.verify_host_key,
        }
    return {"type": "download"}


def resume_fingerprint(payload: ExportInput) -> str:
    identity = {
        "host": str(payload.host),
        "sources": [getattr(source, "value", str(source)) for source in payload.sources],
        "time_field": payload.time_field,
        "start": payload.start.isoformat(),
        "end": payload.end.isoformat(),
        "query_mode": payload.query_mode,
        "query": payload.query,
        "stellar_query": payload.stellar_query,
        "target_records_per_slice": payload.target_records_per_slice,
        "minimum_slice_ms": payload.minimum_slice_ms,
        "format": payload.format,
        "compress": payload.compress,
        "filename": (payload.filename or "stellar-export").strip() or "stellar-export",
        "max_file_size_bytes": payload.max_file_size_bytes,
        "selected_fields": payload.selected_fields,
        "record_limit": payload.record_limit,
        "csv_delimiter": payload.csv_delimiter,
        "csv_include_header": payload.csv_include_header,
        "csv_bom": payload.csv_bom,
        "csv_flatten_nested": payload.csv_flatten_nested,
        "destination": destination_fingerprint_target(payload),
    }
    canonical = json.dumps(
        identity,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def overlap_fingerprint(payload: ExportInput) -> str:
    identity = {
        "host": str(payload.host),
        "sources": [getattr(source, "value", str(source)) for source in payload.sources],
        "time_field": payload.time_field,
        "query_mode": payload.query_mode,
        "query": payload.query,
        "stellar_query": payload.stellar_query,
        "format": payload.format,
        "compress": payload.compress,
        "max_file_size_bytes": payload.max_file_size_bytes,
        "selected_fields": payload.selected_fields,
        "record_limit": payload.record_limit,
        "csv_delimiter": payload.csv_delimiter,
        "csv_include_header": payload.csv_include_header,
        "csv_bom": payload.csv_bom,
        "csv_flatten_nested": payload.csv_flatten_nested,
        "destination": destination_fingerprint_target(payload),
    }
    canonical = json.dumps(
        identity,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def sanitized_export_metadata(payload: ExportInput) -> dict[str, Any]:
    return {
        "host": str(payload.host),
        "sources": [getattr(source, "value", str(source)) for source in payload.sources],
        "start": payload.start.isoformat(),
        "end": payload.end.isoformat(),
        "query_mode": payload.query_mode,
        "format": payload.format,
        "filename": (payload.filename or "stellar-export").strip() or "stellar-export",
        "compress": payload.compress,
        "max_file_size_bytes": payload.max_file_size_bytes,
        "record_limit": payload.record_limit,
        "selected_field_count": len(payload.selected_fields or []),
        "destination_type": payload.destination.type,
        "overlap_policy": payload.overlap_policy,
        "overlap_fingerprint": overlap_fingerprint(payload),
        "resume_fingerprint": resume_fingerprint(payload),
    }


def job_store_record(job: ExportJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "created_at": job.created_at,
        "status": job.status,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "bytes_sent": job.bytes_sent,
        "records_exported": job.records_exported,
        "files_completed": job.files_completed,
        "query_count": job.query_count,
        "retry_count": job.retry_count,
        "duplicates_skipped": job.duplicates_skipped,
        "current_slice_start": job.current_slice_start,
        "current_slice_end": job.current_slice_end,
        "cancel_requested": job.cancel_requested,
        "result": job.result,
        "error": job.error,
        "metadata": job.metadata,
        "completed_parts": job.completed_parts,
    }


def persist_job(job: ExportJob, *, force: bool = False) -> None:
    now = time.time()
    if not force and now - job.last_persisted_at < 1.0:
        return
    JOB_STORE.save(job_store_record(job))
    job.last_persisted_at = now


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def checkpoint_destination_result(
    destination: S3Destination | SFTPDestination,
    filename: str,
) -> str:
    if isinstance(destination, S3Destination):
        return f"s3://{destination.bucket}/{build_s3_key(destination.prefix, filename)}"
    return (
        f"sftp://{destination.host}:{destination.port}"
        f"{build_sftp_path(destination.remote_path, filename)}"
    )


def validate_resume_payload(record: dict[str, Any], payload: ExportInput) -> None:
    expected = record.get("metadata") or {}
    expected_fingerprint = expected.get("resume_fingerprint")
    actual_fingerprint = resume_fingerprint(payload)
    if not expected_fingerprint or actual_fingerprint != expected_fingerprint:
        raise HTTPException(
            status_code=409,
            detail=(
                "Resume settings do not match the original export. "
                "Use the same source, time range, query, output, split, fields, "
                "and destination target."
            ),
        )
    if isinstance(payload.destination, DownloadDestination):
        raise HTTPException(
            status_code=400,
            detail="Checkpoint resume is available only for S3 or SFTP exports.",
        )
    for checkpoint in record.get("completed_parts") or []:
        filename = checkpoint.get("filename")
        if not filename or checkpoint.get("result") != checkpoint_destination_result(
            payload.destination,
            filename,
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Resume destination does not match the destination used by the "
                    "saved completed parts."
                ),
            )


def resumable_status(status: str, summary: dict[str, Any]) -> bool:
    return (
        status in {"failed", "cancelled", "interrupted"}
        and summary.get("destination_type") in {"s3", "sftp"}
        and bool(summary.get("resume_fingerprint"))
    )


def cleanup_jobs() -> None:
    now = time.time()
    for job_id, job in list(EXPORT_JOBS.items()):
        pending_age = now - job.created_at
        terminal_anchor = job.completed_at or job.created_at
        terminal_age = now - terminal_anchor
        if job.status == "pending" and job.payload is not None and pending_age > DOWNLOAD_JOB_TTL_SECONDS:
            job.payload = None
            job.cancel_requested = True
            mark_job_terminal(job, "expired", "Download job expired before it was started.")
            EXPORT_JOBS.pop(job_id, None)
        elif job.status in {"completed", "failed", "cancelled", "expired", "interrupted"} and terminal_age > HISTORY_JOB_TTL_SECONDS:
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


def build_export_source(payload: ExportInput, job: ExportJob | None = None):
    def add_retry(count: int) -> None:
        if job is not None:
            job.retry_count += count

    client = client_for(payload, on_retry=add_retry if job is not None else None)
    raw_query = compile_user_query(
        payload.query_mode,
        payload.query,
        payload.stellar_query,
    )
    if payload.selected_fields:
        raw_query["_source"] = list(payload.selected_fields)

    def on_query() -> None:
        if job is not None:
            job.query_count += 1

    def on_slice(start, end) -> None:
        if job is not None:
            job.current_slice_start = start.isoformat()
            job.current_slice_end = end.isoformat()

    def on_record() -> None:
        if job is not None:
            job.records_exported += 1

    def on_duplicate() -> None:
        if job is not None:
            job.duplicates_skipped += 1

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
        on_query=on_query if job is not None else None,
        on_slice=on_slice if job is not None else None,
        on_record=on_record if job is not None else None,
        on_duplicate=on_duplicate if job is not None else None,
        cancel_check=(lambda: job.cancel_requested) if job is not None else None,
    )

    preferred_fields = None
    requested_source = raw_query.get("_source")
    if isinstance(requested_source, list):
        preferred_fields = [str(field) for field in requested_source]

    records = engine.iter_documents()
    if payload.selected_fields:
        records = project_records(records, payload.selected_fields)
        preferred_fields = list(payload.selected_fields)

    content_type = {
        "csv": "text/csv",
        "json": "application/json",
        "ndjson": "application/x-ndjson",
    }[payload.format]
    filename = safe_filename(payload.filename, payload.format, payload.compress)
    return records, preferred_fields, content_type, filename


def build_output(payload: ExportInput, job: ExportJob | None = None):
    records, preferred_fields, content_type, filename = build_export_source(payload, job)
    if payload.format == "csv":
        stream = csv_stream(
            records,
            preferred_fields,
            delimiter=payload.csv_delimiter,
            include_header=payload.csv_include_header,
            bom=payload.csv_bom,
            flatten_nested=payload.csv_flatten_nested,
        )
    elif payload.format == "ndjson":
        stream = ndjson_stream(records)
    else:
        stream = json_stream(records)

    if payload.compress:
        stream = gzip_stream(stream)

    return stream, content_type, filename


def build_output_parts(payload: ExportInput, job: ExportJob | None = None):
    if payload.max_file_size_bytes is None:
        raise ValueError("Split output requires max_file_size_bytes")
    records, preferred_fields, content_type, filename = build_export_source(payload, job)
    parts = iter_export_part_files(
        records,
        format=payload.format,
        preferred_fields=preferred_fields,
        compress=payload.compress,
        base_filename=filename,
        max_bytes=payload.max_file_size_bytes,
        csv_delimiter=payload.csv_delimiter,
        csv_include_header=payload.csv_include_header,
        csv_bom=payload.csv_bom,
        csv_flatten_nested=payload.csv_flatten_nested,
    )
    return parts, content_type, filename


def mark_job_started(job: ExportJob) -> None:
    if job.started_at is None:
        job.started_at = time.time()
    job.status = "running"
    persist_job(job, force=True)


def mark_job_terminal(job: ExportJob, status: str, error: str | None = None) -> None:
    job.status = status
    job.error = error
    job.completed_at = time.time()
    persist_job(job, force=True)


def job_status_payload(job_id: str, job: ExportJob) -> dict[str, Any]:
    end_time = job.completed_at or time.time()
    elapsed = max(0.0, end_time - job.started_at) if job.started_at else 0.0
    rate = (job.records_exported / elapsed) if elapsed > 0 else 0.0
    return {
        "job_id": job_id,
        "status": job.status,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "summary": job.metadata,
        "records_exported": job.records_exported,
        "bytes_sent": job.bytes_sent,
        "files_completed": job.files_completed,
        "current_slice_start": job.current_slice_start,
        "current_slice_end": job.current_slice_end,
        "query_count": job.query_count,
        "retry_count": job.retry_count,
        "duplicates_skipped": job.duplicates_skipped,
        "elapsed_seconds": elapsed,
        "rate_records_per_second": rate,
        "cancel_requested": job.cancel_requested,
        "result": job.result,
        "error": job.error,
        "completed_parts": list(job.completed_parts),
        "resumable": resumable_status(job.status, job.metadata),
    }


def stored_job_status_payload(record: dict[str, Any]) -> dict[str, Any]:
    end_time = record.get("completed_at") or time.time()
    started_at = record.get("started_at")
    elapsed = max(0.0, end_time - started_at) if started_at else 0.0
    exported = int(record.get("records_exported") or 0)
    return {
        "job_id": record["job_id"],
        "status": record["status"],
        "created_at": record["created_at"],
        "started_at": started_at,
        "completed_at": record.get("completed_at"),
        "summary": record.get("metadata", {}),
        "records_exported": exported,
        "bytes_sent": int(record.get("bytes_sent") or 0),
        "files_completed": int(record.get("files_completed") or 0),
        "current_slice_start": record.get("current_slice_start"),
        "current_slice_end": record.get("current_slice_end"),
        "query_count": int(record.get("query_count") or 0),
        "retry_count": int(record.get("retry_count") or 0),
        "duplicates_skipped": int(record.get("duplicates_skipped") or 0),
        "elapsed_seconds": elapsed,
        "rate_records_per_second": (exported / elapsed) if elapsed > 0 else 0.0,
        "cancel_requested": bool(record.get("cancel_requested")),
        "result": record.get("result"),
        "error": record.get("error"),
        "completed_parts": list(record.get("completed_parts") or []),
        "resumable": resumable_status(record["status"], record.get("metadata") or {}),
    }


async def tracked_download_stream(
    job: ExportJob,
    stream,
    *,
    result: str,
    cleanup_paths: list[str] | None = None,
):
    try:
        async for chunk in stream:
            if job.cancel_requested:
                raise ExportCancelled("Export cancelled")
            job.bytes_sent += len(chunk)
            yield chunk
        if job.cancel_requested:
            raise ExportCancelled("Export cancelled")
        if job.files_completed == 0:
            job.files_completed = 1
        job.result = result
        mark_job_terminal(job, "completed")
    except (ExportCancelled, asyncio.CancelledError):
        mark_job_terminal(job, "cancelled")
        return
    except Exception as exc:
        mark_job_terminal(job, "failed", str(exc)[:2000])
        raise
    finally:
        for path in cleanup_paths or []:
            if os.path.exists(path):
                os.unlink(path)
        job.payload = None
        job.task = None


async def run_destination_job(job_id: str) -> None:
    job = EXPORT_JOBS.get(job_id)
    if job is None or job.payload is None:
        return

    payload = job.payload
    mark_job_started(job)

    def add_bytes(count: int) -> None:
        job.bytes_sent += count

    async def upload_one(filename: str, stream, content_type: str) -> str:
        if job.cancel_requested:
            raise ExportCancelled("Export cancelled")
        if isinstance(payload.destination, S3Destination):
            return await upload_s3(
                payload.destination,
                filename,
                stream,
                content_type=content_type,
                content_encoding="gzip" if payload.compress else None,
                on_bytes=add_bytes,
                cancel_check=lambda: job.cancel_requested,
            )
        if isinstance(payload.destination, SFTPDestination):
            return await upload_sftp(
                payload.destination,
                filename,
                stream,
                on_bytes=add_bytes,
                cancel_check=lambda: job.cancel_requested,
            )
        raise RuntimeError("Unsupported background destination")

    try:
        if payload.max_file_size_bytes is None:
            stream, content_type, filename = build_output(payload, job)
            job.result = await upload_one(filename, stream, content_type)
            job.files_completed = 1
        else:
            parts, content_type, _ = build_output_parts(payload, job)
            checkpoint_parts = list(job.completed_parts)
            results: list[str] = []
            generated_parts = 0
            async for part in parts:
                generated_parts += 1
                try:
                    part_sha256 = await asyncio.to_thread(file_sha256, part.path)
                    if generated_parts <= len(checkpoint_parts):
                        checkpoint = checkpoint_parts[generated_parts - 1]
                        expected_result = checkpoint_destination_result(
                            payload.destination,
                            part.filename,
                        )
                        matches_checkpoint = (
                            checkpoint.get("part_number") == generated_parts
                            and checkpoint.get("filename") == part.filename
                            and checkpoint.get("size_bytes") == part.size_bytes
                            and checkpoint.get("sha256") == part_sha256
                            and checkpoint.get("result") == expected_result
                        )
                        if not matches_checkpoint:
                            raise RuntimeError(
                                f"Checkpoint mismatch at part {generated_parts}; "
                                "the regenerated export no longer matches the saved checkpoint."
                            )
                        results.append(expected_result)
                        job.files_completed += 1
                        persist_job(job, force=True)
                        continue

                    uploaded_result = await upload_one(
                        part.filename,
                        file_stream(part.path),
                        content_type,
                    )
                    results.append(uploaded_result)
                    job.files_completed += 1
                    job.completed_parts.append(
                        {
                            "part_number": generated_parts,
                            "filename": part.filename,
                            "size_bytes": part.size_bytes,
                            "sha256": part_sha256,
                            "result": uploaded_result,
                        }
                    )
                    persist_job(job, force=True)
                finally:
                    if os.path.exists(part.path):
                        os.unlink(part.path)

            if generated_parts < len(checkpoint_parts):
                raise RuntimeError(
                    "Checkpoint mismatch: regenerated export ended before all saved parts."
                )
            if len(results) == 1:
                job.result = results[0]
            elif results:
                job.result = f"{len(results)} files: {results[0]} ... {results[-1]}"
        if job.cancel_requested:
            raise ExportCancelled("Export cancelled")
        mark_job_terminal(job, "completed")
    except (ExportCancelled, asyncio.CancelledError):
        mark_job_terminal(job, "cancelled")
    except Exception as exc:
        mark_job_terminal(job, "failed", str(exc)[:2000])
    finally:
        job.payload = None
        job.task = None


def schedule_public_payload(schedule: dict[str, Any]) -> dict[str, Any]:
    return {
        "schedule_id": schedule["schedule_id"],
        "name": schedule["name"],
        "created_at": schedule["created_at"],
        "updated_at": schedule["updated_at"],
        "enabled": bool(schedule["enabled"]),
        "interval_minutes": schedule["interval_minutes"],
        "window_minutes": schedule["window_minutes"],
        "next_run_at": schedule["next_run_at"],
        "last_run_at": schedule.get("last_run_at"),
        "last_success_end": schedule.get("last_success_end"),
        "last_job_id": schedule.get("last_job_id"),
        "last_status": schedule.get("last_status"),
        "last_error": schedule.get("last_error"),
        "running": schedule["schedule_id"] in ACTIVE_SCHEDULE_RUNS,
    }


def encrypt_schedule_export(payload: ExportInput) -> bytes:
    return SCHEDULE_CIPHER.encrypt(payload.model_dump_json().encode("utf-8"))


def decrypt_schedule_export(schedule: dict[str, Any]) -> ExportInput:
    ciphertext = schedule.get("encrypted_payload")
    if not isinstance(ciphertext, (bytes, bytearray)):
        raise RuntimeError("Scheduled export payload is missing")
    plaintext = SCHEDULE_CIPHER.decrypt(bytes(ciphertext))
    return ExportInput.model_validate_json(plaintext)


def parse_schedule_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def scheduled_filename(payload: ExportInput, end: datetime) -> str:
    filename = safe_filename(payload.filename, payload.format, payload.compress)
    path = Path(filename)
    suffixes = path.suffixes
    if len(suffixes) >= 2 and suffixes[-1].lower() == ".gz":
        suffix = "".join(suffixes[-2:])
    elif suffixes:
        suffix = suffixes[-1]
    else:
        suffix = ""
    stem = filename[:-len(suffix)] if suffix else filename
    stamp = end.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stem}-{stamp}{suffix}"


def schedule_error_text(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, dict):
            return str(detail.get("message") or detail)
        return str(detail)
    return str(exc)


async def execute_schedule(
    schedule_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    schedule = SCHEDULE_STORE.get(schedule_id, include_ciphertext=True)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Scheduled export not found")

    template = decrypt_schedule_export(schedule)
    if isinstance(template.destination, DownloadDestination):
        raise RuntimeError("Scheduled exports require an S3 or SFTP destination")

    run_end = (now or datetime.now(UTC)).astimezone(UTC)
    last_job_id = schedule.get("last_job_id")
    if last_job_id:
        previous = JOB_STORE.get(last_job_id)
        if previous and resumable_status(
            previous["status"],
            previous.get("metadata") or {},
        ):
            metadata = previous.get("metadata") or {}
            payload = template.model_copy(
                update={
                    "start": parse_schedule_time(metadata["start"]),
                    "end": parse_schedule_time(metadata["end"]),
                    "filename": metadata["filename"],
                    "overlap_policy": "reject",
                }
            )
            try:
                resumed = await resume_export_job(last_job_id, payload)
                job = EXPORT_JOBS[last_job_id]
                job.metadata["schedule_id"] = schedule_id
                job.metadata["schedule_name"] = schedule["name"]
                persist_job(job, force=True)
                if job.task is not None:
                    await job.task
                status = job.status
                success_end = payload.end.isoformat() if status == "completed" else None
                SCHEDULE_STORE.record_result(
                    schedule_id,
                    job_id=last_job_id,
                    status=status,
                    last_success_end=success_end,
                    error=job.error,
                )
                return {
                    "schedule_id": schedule_id,
                    "job_id": last_job_id,
                    "status": status,
                    "resumed": True,
                    "resumed_from_parts": resumed["resumed_from_parts"],
                }
            except Exception as exc:
                error = schedule_error_text(exc)
                SCHEDULE_STORE.record_result(
                    schedule_id,
                    job_id=last_job_id,
                    status="failed",
                    error=error,
                )
                return {
                    "schedule_id": schedule_id,
                    "job_id": last_job_id,
                    "status": "failed",
                    "error": error,
                    "resumed": True,
                }

    last_success_end = schedule.get("last_success_end")
    if last_success_end:
        run_start = parse_schedule_time(last_success_end)
        if run_start >= run_end:
            return {
                "schedule_id": schedule_id,
                "job_id": None,
                "status": "no_new_window",
            }
    else:
        run_start = run_end - timedelta(minutes=int(schedule["window_minutes"]))

    payload = template.model_copy(
        update={
            "start": run_start,
            "end": run_end,
            "filename": scheduled_filename(template, run_end),
            "overlap_policy": "reject",
        }
    )

    try:
        created = await create_export_job(payload)
        job_id = created["job_id"]
        job = EXPORT_JOBS[job_id]
        job.metadata["schedule_id"] = schedule_id
        job.metadata["schedule_name"] = schedule["name"]
        persist_job(job, force=True)
        if job.task is not None:
            await job.task
        status = job.status
        success_end = run_end.isoformat() if status == "completed" else None
        SCHEDULE_STORE.record_result(
            schedule_id,
            job_id=job_id,
            status=status,
            last_success_end=success_end,
            error=job.error,
        )
        return {
            "schedule_id": schedule_id,
            "job_id": job_id,
            "status": status,
            "resumed": False,
            "start": run_start.isoformat(),
            "end": run_end.isoformat(),
        }
    except Exception as exc:
        error = schedule_error_text(exc)
        SCHEDULE_STORE.record_result(
            schedule_id,
            job_id=None,
            status="blocked" if isinstance(exc, HTTPException) and exc.status_code == 409 else "failed",
            error=error,
        )
        return {
            "schedule_id": schedule_id,
            "job_id": None,
            "status": "blocked" if isinstance(exc, HTTPException) and exc.status_code == 409 else "failed",
            "error": error,
            "resumed": False,
        }


async def _schedule_run_guarded(schedule_id: str) -> None:
    try:
        await execute_schedule(schedule_id)
    except asyncio.CancelledError:
        raise
    except Exception:
        LOGGER.exception("Scheduled export %s failed unexpectedly", schedule_id)
    finally:
        ACTIVE_SCHEDULE_RUNS.pop(schedule_id, None)


def start_schedule_run(schedule_id: str) -> asyncio.Task:
    existing = ACTIVE_SCHEDULE_RUNS.get(schedule_id)
    if existing is not None and not existing.done():
        raise HTTPException(status_code=409, detail="Scheduled export is already running")
    task = asyncio.create_task(_schedule_run_guarded(schedule_id))
    ACTIVE_SCHEDULE_RUNS[schedule_id] = task
    return task


async def run_due_schedules_once(now: float | None = None) -> list[str]:
    current = time.time() if now is None else now
    started: list[str] = []
    for schedule in SCHEDULE_STORE.due(current):
        schedule_id = schedule["schedule_id"]
        if schedule_id in ACTIVE_SCHEDULE_RUNS:
            continue
        next_run = current + int(schedule["interval_minutes"]) * 60
        SCHEDULE_STORE.reserve_next_run(schedule_id, next_run)
        start_schedule_run(schedule_id)
        started.append(schedule_id)
    return started


async def schedule_loop() -> None:
    while True:
        try:
            await run_due_schedules_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("Scheduled export loop iteration failed")
        await asyncio.sleep(SCHEDULE_POLL_SECONDS)


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


@app.get("/api/schedules")
async def list_schedules() -> dict[str, Any]:
    return {
        "schedules": [
            schedule_public_payload(schedule)
            for schedule in SCHEDULE_STORE.list()
        ]
    }


@app.post("/api/schedules")
async def create_schedule(payload: ScheduleCreateInput) -> dict[str, Any]:
    schedule_id = uuid.uuid4().hex
    encrypted = encrypt_schedule_export(payload.export)
    schedule = SCHEDULE_STORE.create(
        schedule_id=schedule_id,
        name=payload.name.strip(),
        interval_minutes=payload.interval_minutes,
        window_minutes=payload.window_minutes,
        next_run_at=time.time() + payload.interval_minutes * 60,
        encrypted_payload=encrypted,
        enabled=payload.enabled,
    )
    return schedule_public_payload(schedule)


@app.patch("/api/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    payload: ScheduleUpdateInput,
) -> dict[str, Any]:
    current = SCHEDULE_STORE.get(schedule_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Scheduled export not found")

    interval = payload.interval_minutes or current["interval_minutes"]
    next_run_at = None
    if payload.interval_minutes is not None or payload.enabled is True:
        next_run_at = time.time() + interval * 60

    updated = SCHEDULE_STORE.update(
        schedule_id,
        enabled=payload.enabled,
        name=payload.name.strip() if payload.name is not None else None,
        interval_minutes=payload.interval_minutes,
        window_minutes=payload.window_minutes,
        next_run_at=next_run_at,
    )
    return schedule_public_payload(updated)


@app.delete("/api/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str) -> dict[str, bool]:
    task = ACTIVE_SCHEDULE_RUNS.get(schedule_id)
    if task is not None and not task.done():
        raise HTTPException(
            status_code=409,
            detail="Scheduled export is running and cannot be deleted",
        )
    if not SCHEDULE_STORE.delete(schedule_id):
        raise HTTPException(status_code=404, detail="Scheduled export not found")
    return {"deleted": True}


@app.post("/api/schedules/{schedule_id}/run")
async def run_schedule_now(schedule_id: str) -> dict[str, Any]:
    schedule = SCHEDULE_STORE.get(schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Scheduled export not found")
    SCHEDULE_STORE.reserve_next_run(
        schedule_id,
        time.time() + int(schedule["interval_minutes"]) * 60,
    )
    start_schedule_run(schedule_id)
    return {
        **schedule_public_payload(SCHEDULE_STORE.get(schedule_id)),
        "running": True,
    }


@app.post("/api/export/jobs")
async def create_export_job(payload: ExportInput) -> dict[str, str]:
    cleanup_jobs()
    if payload.overlap_policy == "reject":
        conflicts = JOB_STORE.find_overlaps(
            overlap_fingerprint(payload),
            payload.start,
            payload.end,
        )
        if conflicts:
            conflict = conflicts[0]
            metadata = conflict.get("metadata") or {}
            raise HTTPException(
                status_code=409,
                detail={
                    "message": (
                        "This export overlaps an existing matching export "
                        f"({conflict['job_id'][:8]}, {conflict['status']}, "
                        f"{metadata.get('start', '?')} → {metadata.get('end', '?')}). "
                        "Use a non-overlapping range, choose Allow overlap, or Resume the "
                        "existing remote job when applicable."
                    ),
                    "conflicts": [
                        {
                            "job_id": item["job_id"],
                            "status": item["status"],
                            "start": (item.get("metadata") or {}).get("start"),
                            "end": (item.get("metadata") or {}).get("end"),
                        }
                        for item in conflicts
                    ],
                },
            )

    job_id = uuid.uuid4().hex
    job = ExportJob(
        job_id=job_id,
        created_at=time.time(),
        payload=payload,
        metadata=sanitized_export_metadata(payload),
    )
    EXPORT_JOBS[job_id] = job
    persist_job(job, force=True)
    status_url = f"/api/export/jobs/{job_id}"
    cancel_url = f"/api/export/jobs/{job_id}/cancel"

    if isinstance(payload.destination, DownloadDestination):
        return {
            "job_id": job_id,
            "mode": "download",
            "download_url": f"/api/export/jobs/{job_id}/download",
            "status_url": status_url,
            "cancel_url": cancel_url,
        }

    job.task = asyncio.create_task(run_destination_job(job_id))
    return {
        "job_id": job_id,
        "mode": "background",
        "status_url": status_url,
        "cancel_url": cancel_url,
    }


@app.get("/api/export/history")
async def export_history(limit: int = 50) -> dict[str, Any]:
    cleanup_jobs()
    for job in EXPORT_JOBS.values():
        persist_job(job)
    return {
        "jobs": [stored_job_status_payload(record) for record in JOB_STORE.list(limit)],
    }


@app.post("/api/export/jobs/{job_id}/resume")
async def resume_export_job(job_id: str, payload: ExportInput) -> dict[str, Any]:
    cleanup_jobs()
    active = EXPORT_JOBS.get(job_id)
    if active is not None and active.status in {"pending", "running"}:
        raise HTTPException(status_code=409, detail="Export job is already active")

    record = JOB_STORE.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Export job not found")
    if not resumable_status(record["status"], record.get("metadata") or {}):
        raise HTTPException(
            status_code=409,
            detail=f"Export job in status {record['status']} cannot be resumed",
        )

    validate_resume_payload(record, payload)
    checkpoints = list(record.get("completed_parts") or [])
    job = ExportJob(
        job_id=job_id,
        created_at=record["created_at"],
        payload=payload,
        metadata=sanitized_export_metadata(payload),
        bytes_sent=sum(int(part.get("size_bytes") or 0) for part in checkpoints),
        completed_parts=checkpoints,
    )
    EXPORT_JOBS[job_id] = job
    persist_job(job, force=True)
    job.task = asyncio.create_task(run_destination_job(job_id))
    return {
        "job_id": job_id,
        "mode": "background",
        "status_url": f"/api/export/jobs/{job_id}",
        "cancel_url": f"/api/export/jobs/{job_id}/cancel",
        "resumed_from_parts": len(checkpoints),
    }


@app.get("/api/export/jobs/{job_id}")
async def export_job_status(job_id: str) -> dict[str, Any]:
    cleanup_jobs()
    job = EXPORT_JOBS.get(job_id)
    if job is not None:
        persist_job(job)
        return job_status_payload(job_id, job)
    record = JOB_STORE.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Export job not found or expired")
    return stored_job_status_payload(record)


@app.post("/api/export/jobs/{job_id}/cancel")
async def cancel_export_job(job_id: str) -> dict[str, Any]:
    cleanup_jobs()
    job = EXPORT_JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Export job not found or expired")
    if job.status in {"completed", "failed", "cancelled", "expired", "interrupted"}:
        return job_status_payload(job_id, job)

    job.cancel_requested = True
    if job.status == "pending":
        job.payload = None
        job.task = None
        mark_job_terminal(job, "cancelled")
    return job_status_payload(job_id, job)


def cleanup_paths(paths: list[str]) -> None:
    for path in paths:
        if path and os.path.exists(path):
            os.unlink(path)


@app.get("/api/export/jobs/{job_id}/download")
async def download_export(job_id: str):
    cleanup_jobs()
    job = EXPORT_JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Export job not found or expired")
    if job.status == "cancelled":
        raise HTTPException(status_code=409, detail="Export job was cancelled")
    if job.status != "pending" or job.payload is None:
        raise HTTPException(status_code=409, detail="Export job has already started")
    if not isinstance(job.payload.destination, DownloadDestination):
        raise HTTPException(status_code=400, detail="This job is not a browser download")

    payload = job.payload
    mark_job_started(job)

    if payload.max_file_size_bytes is None:
        stream, content_type, filename = build_output(payload, job)
        media_type = "application/gzip" if payload.compress else content_type
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        tracked = tracked_download_stream(job, stream, result=filename)
        return StreamingResponse(tracked, media_type=media_type, headers=headers)

    completed_paths: list[str] = []
    archive_path: str | None = None
    try:
        parts, content_type, filename = build_output_parts(payload, job)
        completed_parts = []
        async for part in parts:
            completed_parts.append(part)
            completed_paths.append(part.path)
            job.files_completed += 1
            if job.cancel_requested:
                raise ExportCancelled("Export cancelled")

        if job.cancel_requested:
            raise ExportCancelled("Export cancelled")

        if len(completed_parts) == 1:
            part = completed_parts[0]
            media_type = "application/gzip" if payload.compress else content_type
            headers = {"Content-Disposition": f'attachment; filename="{part.filename}"'}
            tracked = tracked_download_stream(
                job,
                file_stream(part.path),
                result=part.filename,
                cleanup_paths=[part.path],
            )
            return StreamingResponse(tracked, media_type=media_type, headers=headers)

        archive = tempfile.NamedTemporaryFile(
            prefix="stellar-export-",
            suffix=".zip",
            delete=False,
        )
        archive_path = archive.name
        archive.close()

        with zipfile.ZipFile(
            archive_path,
            "w",
            compression=zipfile.ZIP_STORED,
        ) as bundle:
            for part in completed_parts:
                bundle.write(part.path, arcname=part.filename)

        cleanup_paths(completed_paths)
        completed_paths.clear()

        if job.cancel_requested:
            raise ExportCancelled("Export cancelled")

        archive_name = re.sub(
            r"(\.csv|\.json)(\.gz)?$",
            "",
            filename,
            flags=re.IGNORECASE,
        )
        archive_name = f"{archive_name}-parts.zip"
        headers = {"Content-Disposition": f'attachment; filename="{archive_name}"'}
        tracked = tracked_download_stream(
            job,
            file_stream(archive_path),
            result=archive_name,
            cleanup_paths=[archive_path],
        )
        return StreamingResponse(
            tracked,
            media_type="application/zip",
            headers=headers,
        )
    except (ExportCancelled, asyncio.CancelledError):
        cleanup_paths(completed_paths)
        cleanup_paths([archive_path] if archive_path else [])
        job.payload = None
        job.task = None
        mark_job_terminal(job, "cancelled")
        raise HTTPException(status_code=409, detail="Export job was cancelled")
    except Exception as exc:
        cleanup_paths(completed_paths)
        cleanup_paths([archive_path] if archive_path else [])
        job.payload = None
        job.task = None
        mark_job_terminal(job, "failed", str(exc)[:2000])
        raise
