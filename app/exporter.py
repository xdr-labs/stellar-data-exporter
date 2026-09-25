from __future__ import annotations

import csv
import io
import json
import zlib
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Any

from .query import build_document_query, hit_source, total_hits
from .stellar import StellarClient


class DenseSliceError(RuntimeError):
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
    ):
        self.client = client
        self.index = index
        self.raw_query = raw_query
        self.time_field = time_field
        self.start = start
        self.end = end
        self.target_records = target_records
        self.minimum_slice = timedelta(milliseconds=minimum_slice_ms)

    async def _count(self, start: datetime, end: datetime) -> int:
        body = build_document_query(
            self.raw_query,
            time_field=self.time_field,
            start=start,
            end=end,
            size=0,
            track_total_hits=True,
        )
        response = await self.client.search(self.index, body)
        count, exact = total_hits(response)
        if not exact:
            raise RuntimeError("Stellar Cyber did not return an exact hit count")
        return count

    async def _fetch(self, start: datetime, end: datetime) -> tuple[list[dict[str, Any]], int]:
        body = build_document_query(
            self.raw_query,
            time_field=self.time_field,
            start=start,
            end=end,
            size=self.target_records,
            track_total_hits=True,
        )
        response = await self.client.search(self.index, body)
        count, exact = total_hits(response)
        if not exact:
            raise RuntimeError("Stellar Cyber did not return an exact hit count")
        hits = response.get("hits", {}).get("hits", [])
        return [hit_source(hit) for hit in hits], count

    async def iter_documents(self) -> AsyncIterator[dict[str, Any]]:
        stack: list[tuple[datetime, datetime]] = [(self.start, self.end)]
        while stack:
            start, end = stack.pop()
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

            for record in records:
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


async def csv_stream(
    records: AsyncIterator[dict[str, Any]],
    preferred_fields: list[str] | None = None,
) -> AsyncIterator[bytes]:
    buffered: list[dict[str, Any]] = []
    columns: list[str] = list(preferred_fields or [])

    async for record in records:
        flat = flatten_record(record)
        buffered.append(flat)
        if not columns:
            columns = list(flat.keys())
        else:
            for key in flat:
                if key not in columns and len(buffered) <= 100:
                    columns.append(key)
        if len(buffered) >= 100:
            break

    if not buffered:
        return

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in buffered:
        writer.writerow(row)
    yield output.getvalue().encode("utf-8")
    output.seek(0)
    output.truncate(0)

    async for record in records:
        writer.writerow(flatten_record(record))
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
