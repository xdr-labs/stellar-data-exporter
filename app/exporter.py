from __future__ import annotations

import asyncio
import csv
import gzip
import io
import json
import os
import tempfile
import zlib
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .query import build_document_query, hit_identity, hit_source, total_hits
from .stellar import StellarClient


class DenseSliceError(RuntimeError):
    pass


class ExportCancelled(RuntimeError):
    pass


def flatten_record(value: Any, prefix: str = "", out: dict[str, Any] | None = None) -> dict[str, Any]:
    if out is None:
        out = {}
    if isinstance(value, dict):
        for key, child in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            flatten_record(child, next_prefix, out)
    elif isinstance(value, list):
        out[prefix] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        out[prefix] = value
    return out


_MISSING = object()


def _get_path(record: dict[str, Any], path: str) -> Any:
    current: Any = record
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _set_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = target
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def project_record(record: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    for field in fields:
        value = _get_path(record, field)
        if value is not _MISSING:
            _set_path(projected, field, value)
    return projected


def discover_fields(records: list[dict[str, Any]]) -> list[str]:
    fields: list[str] = []
    seen: set[str] = set()
    for record in records:
        for field in flatten_record(record):
            if field and field not in seen:
                seen.add(field)
                fields.append(field)
    return fields


async def project_records(
    records: AsyncIterator[dict[str, Any]],
    fields: list[str],
) -> AsyncIterator[dict[str, Any]]:
    async for record in records:
        yield project_record(record, fields)


class ExportEngine:
    def __init__(
        self,
        client: StellarClient,
        *,
        index: str,
        raw_query: dict[str, Any],
        time_field: str,
        start: datetime,
        end: datetime,
        target_records: int,
        minimum_slice_ms: int,
        max_records: int | None = None,
        on_query: Callable[[], None] | None = None,
        on_slice: Callable[[datetime, datetime], None] | None = None,
        on_record: Callable[[], None] | None = None,
        on_duplicate: Callable[[], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ):
        self.client = client
        self.index = index
        self.raw_query = raw_query
        self.time_field = time_field
        self.start = start
        self.end = end
        self.target_records = target_records
        self.minimum_slice = timedelta(milliseconds=minimum_slice_ms)
        self.max_records = max_records
        self.on_query = on_query
        self.on_slice = on_slice
        self.on_record = on_record
        self.on_duplicate = on_duplicate
        self.cancel_check = cancel_check

    def _check_cancelled(self) -> None:
        if self.cancel_check and self.cancel_check():
            raise ExportCancelled("Export cancelled")

    def _mark_query(self) -> None:
        self._check_cancelled()
        if self.on_query:
            self.on_query()

    async def _count(self, start: datetime, end: datetime) -> int:
        body = build_document_query(
            self.raw_query,
            time_field=self.time_field,
            start=start,
            end=end,
            size=0,
            track_total_hits=True,
        )
        self._mark_query()
        response = await self.client.search(self.index, body)
        count, exact = total_hits(response)
        if not exact:
            raise RuntimeError("Stellar Cyber did not return an exact hit count")
        return count

    async def _fetch(
        self,
        start: datetime,
        end: datetime,
    ) -> tuple[list[tuple[dict[str, Any], tuple[str, str] | None]], int]:
        body = build_document_query(
            self.raw_query,
            time_field=self.time_field,
            start=start,
            end=end,
            size=self.target_records,
            track_total_hits=True,
        )
        self._mark_query()
        response = await self.client.search(self.index, body)
        count, exact = total_hits(response)
        if not exact:
            raise RuntimeError("Stellar Cyber did not return an exact hit count")
        hits = response.get("hits", {}).get("hits", [])
        return [
            (hit_source(hit), hit_identity(hit))
            for hit in hits
        ], count

    async def iter_documents(self) -> AsyncIterator[dict[str, Any]]:
        stack: list[tuple[datetime, datetime]] = [(self.start, self.end)]
        emitted = 0
        seen_identities: set[tuple[str, str]] = set()
        while stack:
            self._check_cancelled()
            start, end = stack.pop()
            if self.on_slice:
                self.on_slice(start, end)
            count = await self._count(start, end)
            if count == 0:
                continue

            duration = end - start
            if count > self.target_records:
                if duration <= self.minimum_slice:
                    raise DenseSliceError(
                        f"{count} records remain inside the minimum "
                        f"{self.minimum_slice.total_seconds() * 1000:.0f} ms slice"
                    )
                midpoint = start + duration / 2
                stack.append((midpoint, end))
                stack.append((start, midpoint))
                continue

            records, actual_count = await self._fetch(start, end)
            if actual_count > self.target_records:
                if duration <= self.minimum_slice:
                    raise DenseSliceError(
                        f"{actual_count} records arrived inside the minimum slice"
                    )
                midpoint = start + duration / 2
                stack.append((midpoint, end))
                stack.append((start, midpoint))
                continue

            for record, identity in records:
                self._check_cancelled()
                if identity is not None:
                    if identity in seen_identities:
                        if self.on_duplicate:
                            self.on_duplicate()
                        continue
                    seen_identities.add(identity)
                if self.max_records is not None and emitted >= self.max_records:
                    return
                emitted += 1
                if self.on_record:
                    self.on_record()
                yield record


async def json_stream(records: AsyncIterator[dict[str, Any]]) -> AsyncIterator[bytes]:
    first = True
    yield b"["
    async for record in records:
        if not first:
            yield b","
        first = False
        yield json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    yield b"]"


async def ndjson_stream(records: AsyncIterator[dict[str, Any]]) -> AsyncIterator[bytes]:
    async for record in records:
        yield (
            json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            + b"\n"
        )


def csv_record(record: dict[str, Any], *, flatten_nested: bool) -> dict[str, Any]:
    if flatten_nested:
        return flatten_record(record)

    prepared: dict[str, Any] = {}
    for key, value in record.items():
        if isinstance(value, (dict, list)):
            prepared[key] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        else:
            prepared[key] = value
    return prepared


def csv_preferred_columns(
    preferred_fields: list[str] | None,
    *,
    flatten_nested: bool,
) -> list[str]:
    if not preferred_fields:
        return []
    if flatten_nested:
        return list(preferred_fields)
    return list(dict.fromkeys(field.split(".", 1)[0] for field in preferred_fields))


async def csv_stream(
    records: AsyncIterator[dict[str, Any]],
    preferred_fields: list[str] | None = None,
    *,
    delimiter: str = ",",
    include_header: bool = True,
    bom: bool = False,
    flatten_nested: bool = True,
) -> AsyncIterator[bytes]:
    buffered: list[dict[str, Any]] = []
    columns = csv_preferred_columns(
        preferred_fields,
        flatten_nested=flatten_nested,
    )

    async for record in records:
        row = csv_record(record, flatten_nested=flatten_nested)
        buffered.append(row)
        if not columns:
            columns = list(row.keys())
        else:
            for key in row:
                if key not in columns and len(buffered) <= 100:
                    columns.append(key)
        if len(buffered) >= 100:
            break

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=columns,
        extrasaction="ignore",
        delimiter=delimiter,
    )
    if bom:
        yield b"\xef\xbb\xbf"
    if include_header and columns:
        writer.writeheader()

    for row in buffered:
        writer.writerow(row)
    if output.tell():
        yield output.getvalue().encode("utf-8")
        output.seek(0)
        output.truncate(0)

    async for record in records:
        writer.writerow(csv_record(record, flatten_nested=flatten_nested))
        yield output.getvalue().encode("utf-8")
        output.seek(0)
        output.truncate(0)


async def gzip_stream(source: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    compressor = zlib.compressobj(wbits=31)
    async for chunk in source:
        compressed = compressor.compress(chunk)
        if compressed:
            yield compressed
    tail = compressor.flush()
    if tail:
        yield tail


@dataclass(frozen=True)
class ExportPart:
    path: str
    filename: str
    size_bytes: int


def numbered_filename(filename: str, part_number: int) -> str:
    path = Path(filename)
    suffixes = path.suffixes
    if len(suffixes) >= 2 and suffixes[-1] == ".gz":
        suffix = "".join(suffixes[-2:])
    elif suffixes:
        suffix = suffixes[-1]
    else:
        suffix = ""
    stem = filename[:-len(suffix)] if suffix else filename
    return f"{stem}-{part_number:04d}{suffix}"


class _PartWriter:
    def __init__(self, *, compress: bool):
        handle = tempfile.NamedTemporaryFile(prefix="stellar-export-", delete=False)
        self.path = handle.name
        self.raw = handle
        self.stream = gzip.GzipFile(fileobj=handle, mode="wb") if compress else handle

    def write(self, data: bytes) -> None:
        self.stream.write(data)

    def size(self) -> int:
        self.stream.flush()
        self.raw.flush()
        return self.raw.tell()

    def close(self) -> int:
        if self.stream is not self.raw:
            self.stream.close()
        self.raw.close()
        return os.path.getsize(self.path)


async def _csv_records(
    buffered: list[dict[str, Any]],
    records: AsyncIterator[dict[str, Any]],
    *,
    flatten_nested: bool,
) -> AsyncIterator[dict[str, Any]]:
    for record in buffered:
        yield record
    async for record in records:
        yield csv_record(record, flatten_nested=flatten_nested)


async def iter_export_part_files(
    records: AsyncIterator[dict[str, Any]],
    *,
    format: str,
    preferred_fields: list[str] | None,
    compress: bool,
    base_filename: str,
    max_bytes: int,
    csv_delimiter: str = ",",
    csv_include_header: bool = True,
    csv_bom: bool = False,
    csv_flatten_nested: bool = True,
) -> AsyncIterator[ExportPart]:
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")

    columns = csv_preferred_columns(
        preferred_fields,
        flatten_nested=csv_flatten_nested,
    )
    buffered_csv: list[dict[str, Any]] = []

    if format == "csv":
        async for record in records:
            row = csv_record(record, flatten_nested=csv_flatten_nested)
            buffered_csv.append(row)
            if not columns:
                columns = list(row.keys())
            else:
                for key in row:
                    if key not in columns and len(buffered_csv) <= 100:
                        columns.append(key)
            if len(buffered_csv) >= 100:
                break
        source = _csv_records(
            buffered_csv,
            records,
            flatten_nested=csv_flatten_nested,
        )
    else:
        source = records

    part_number = 1
    split_happened = False
    writer: _PartWriter | None = None
    json_first = True


    def open_part() -> _PartWriter:
        part = _PartWriter(compress=compress)
        if format == "csv":
            if csv_bom:
                part.write(b"\xef\xbb\xbf")
            if csv_include_header and columns:
                output = io.StringIO()
                csv.DictWriter(
                    output,
                    fieldnames=columns,
                    delimiter=csv_delimiter,
                ).writeheader()
                part.write(output.getvalue().encode("utf-8"))
        elif format == "json":
            part.write(b"[")
        return part

    async for record in source:
        if writer is None:
            writer = open_part()
            json_first = True

        if format == "csv":
            output = io.StringIO()
            csv.DictWriter(
                output,
                fieldnames=columns,
                extrasaction="ignore",
                delimiter=csv_delimiter,
            ).writerow(record)
            writer.write(output.getvalue().encode("utf-8"))
        elif format == "json":
            if not json_first:
                writer.write(b",")
            writer.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            json_first = False
        else:
            writer.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                + b"\n"
            )

        if writer.size() >= max_bytes:
            if format == "json":
                writer.write(b"]")
            size = writer.close()
            split_happened = True
            yield ExportPart(
                path=writer.path,
                filename=numbered_filename(base_filename, part_number),
                size_bytes=size,
            )
            part_number += 1
            writer = None

    if writer is None:
        if part_number == 1:
            writer = open_part()
            if format == "json":
                writer.write(b"]")
            size = writer.close()
            yield ExportPart(
                path=writer.path,
                filename=base_filename,
                size_bytes=size,
            )
        return

    if format == "json":
        writer.write(b"]")
    size = writer.close()
    yield ExportPart(
        path=writer.path,
        filename=(
            numbered_filename(base_filename, part_number)
            if split_happened
            else base_filename
        ),
        size_bytes=size,
    )


async def file_stream(
    path: str,
    *,
    chunk_size: int = 1024 * 1024,
) -> AsyncIterator[bytes]:
    handle = open(path, "rb")
    try:
        while True:
            chunk = await asyncio.to_thread(handle.read, chunk_size)
            if not chunk:
                break
            yield chunk
    finally:
        handle.close()
