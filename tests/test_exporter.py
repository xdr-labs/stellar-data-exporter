import json

from app.exporter import flatten_record


def test_flatten_record_flattens_nested_dict_and_serializes_arrays():
    record = {
        "srcip": "10.0.0.1",
        "geo": {"country": "KR", "city": "Seoul"},
        "tags": ["one", "two"],
    }
    flat = flatten_record(record)

    assert flat["srcip"] == "10.0.0.1"
    assert flat["geo.country"] == "KR"
    assert flat["geo.city"] == "Seoul"
    assert json.loads(flat["tags"]) == ["one", "two"]


import gzip
import os

import pytest

from app.exporter import iter_export_part_files, numbered_filename


async def sample_records(count=12):
    for i in range(count):
        yield {
            "timestamp": f"2026-09-25T00:00:{i:02d}Z",
            "message": "x" * 120,
            "n": i,
        }


def test_numbered_filename_preserves_compound_extension():
    assert numbered_filename("alerts.csv.gz", 1) == "alerts-0001.csv.gz"
    assert numbered_filename("events.json", 12) == "events-0012.json"


@pytest.mark.asyncio
async def test_json_split_parts_are_individually_valid():
    parts = [
        part
        async for part in iter_export_part_files(
            sample_records(),
            format="json",
            preferred_fields=None,
            compress=False,
            base_filename="events.json",
            max_bytes=420,
        )
    ]
    try:
        assert len(parts) > 1
        assert parts[0].filename == "events-0001.json"
        assert parts[1].filename == "events-0002.json"
        rows = []
        for part in parts:
            with open(part.path, "rb") as handle:
                rows.extend(json.load(handle))
        assert [row["n"] for row in rows] == list(range(12))
    finally:
        for part in parts:
            if os.path.exists(part.path):
                os.unlink(part.path)


@pytest.mark.asyncio
async def test_gzip_csv_split_parts_are_independently_readable():
    parts = [
        part
        async for part in iter_export_part_files(
            sample_records(),
            format="csv",
            preferred_fields=None,
            compress=True,
            base_filename="events.csv.gz",
            max_bytes=180,
        )
    ]
    try:
        assert len(parts) > 1
        assert parts[0].filename == "events-0001.csv.gz"
        rows = []
        for part in parts:
            with gzip.open(part.path, "rt", encoding="utf-8") as handle:
                lines = handle.read().strip().splitlines()
                assert lines[0].startswith("timestamp,")
                rows.extend(lines[1:])
        assert len(rows) == 12
    finally:
        for part in parts:
            if os.path.exists(part.path):
                os.unlink(part.path)
