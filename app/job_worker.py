from __future__ import annotations

import asyncio
import os
import sys

from . import main as main_app
from .models import DownloadDestination, ExportInput


def build_job(job_id: str, payload: ExportInput) -> main_app.ExportJob:
    record = main_app.JOB_STORE.get(job_id)
    if record is None:
        raise RuntimeError(f"job not found: {job_id}")

    return main_app.ExportJob(
        job_id=job_id,
        created_at=float(record["created_at"]),
        payload=payload,
        metadata=dict(record.get("metadata") or {}),
        status=record.get("status") or "pending",
        started_at=record.get("started_at"),
        completed_at=record.get("completed_at"),
        bytes_sent=int(record.get("bytes_sent") or 0),
        records_exported=int(record.get("records_exported") or 0),
        files_completed=int(record.get("files_completed") or 0),
        query_count=int(record.get("query_count") or 0),
        retry_count=int(record.get("retry_count") or 0),
        adaptive_split_count=int(record.get("adaptive_split_count") or 0),
        duplicates_skipped=int(record.get("duplicates_skipped") or 0),
        current_slice_start=record.get("current_slice_start"),
        current_slice_end=record.get("current_slice_end"),
        current_source=record.get("current_source"),
        partition_number=int(record.get("partition_number") or 0),
        partition_total=int(record.get("partition_total") or 0),
        cancel_requested=bool(record.get("cancel_requested")),
        worker_pid=os.getpid(),
        result=record.get("result"),
        error=record.get("error"),
        completed_parts=list(record.get("completed_parts") or []),
        download_path=record.get("download_path"),
        download_filename=record.get("download_filename"),
        download_media_type=record.get("download_media_type"),
    )


async def execute(job_id: str, payload: ExportInput) -> int:
    job = build_job(job_id, payload)
    main_app.EXPORT_JOBS[job_id] = job
    main_app.JOB_STORE.set_worker_pid(job_id, os.getpid())

    try:
        if isinstance(payload.destination, DownloadDestination):
            await main_app.run_download_job(job_id)
        else:
            await main_app.run_destination_job(job_id)
    finally:
        main_app.EXPORT_JOBS.pop(job_id, None)

    return 0


async def run(job_id: str) -> int:
    payload_bytes = sys.stdin.buffer.read()
    if not payload_bytes:
        print("worker payload missing", file=sys.stderr)
        return 2

    try:
        payload = ExportInput.model_validate_json(payload_bytes)
    except Exception:
        print("worker payload is invalid", file=sys.stderr)
        return 65

    try:
        return await execute(job_id, payload)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 3


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m app.job_worker <job_id>", file=sys.stderr)
        return 64
    return asyncio.run(run(sys.argv[1]))


if __name__ == "__main__":
    raise SystemExit(main())
