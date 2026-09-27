from datetime import UTC, datetime

import pytest

from app.exporter import ExportCancelled, ExportEngine
from app.stellar import StellarReadTimeoutError


class FakeClient:
    def __init__(self):
        self.calls = []

    async def search(self, index, body):
        time_range = body["query"]["bool"]["filter"][0]["range"]["timestamp"]
        start = datetime.fromisoformat(time_range["gte"])
        end = datetime.fromisoformat(time_range["lt"])
        seconds = (end - start).total_seconds()
        self.calls.append((start, end, body["size"]))
        total = int(seconds * 2)
        if body["size"] == 0:
            assert body["track_total_hits"] is True
            return {"hits": {"total": {"value": total, "relation": "eq"}, "hits": []}}

        assert body["track_total_hits"] is False
        hits = [
            {"_source": {"timestamp": start.isoformat(), "n": i}}
            for i in range(min(total, body["size"]))
        ]
        return {"hits": {"total": {"value": total, "relation": "gte"}, "hits": hits}}


@pytest.mark.asyncio
async def test_engine_splits_large_time_ranges_until_under_target():
    client = FakeClient()
    adaptive_splits = 0

    def on_adaptive_split():
        nonlocal adaptive_splits
        adaptive_splits += 1

    engine = ExportEngine(
        client,
        index="aella-ser-*",
        raw_query={"query": {"match_all": {}}},
        time_field="timestamp",
        start=datetime(2026, 9, 1, 0, 0, tzinfo=UTC),
        end=datetime(2026, 9, 1, 0, 0, 10, tzinfo=UTC),
        target_records=5,
        minimum_slice_ms=1,
        on_adaptive_split=on_adaptive_split,
    )

    records = [record async for record in engine.iter_documents()]
    assert len(records) == 20
    assert adaptive_splits == 0
    count_calls = [size for _, _, size in client.calls if size == 0]
    fetch_sizes = [size for _, _, size in client.calls if size > 0]
    assert count_calls == [0]
    assert fetch_sizes == [6, 6, 6, 6, 6]


@pytest.mark.asyncio
async def test_engine_stops_exactly_at_global_record_limit():
    client = FakeClient()
    engine = ExportEngine(
        client,
        index="aella-ser-*",
        raw_query={"query": {"match_all": {}}},
        time_field="timestamp",
        start=datetime(2026, 9, 1, 0, 0, tzinfo=UTC),
        end=datetime(2026, 9, 1, 0, 0, 10, tzinfo=UTC),
        target_records=5,
        minimum_slice_ms=1,
        max_records=7,
    )

    records = [record async for record in engine.iter_documents()]
    assert len(records) == 7
    count_calls = [size for _, _, size in client.calls if size == 0]
    fetch_sizes = [size for _, _, size in client.calls if size > 0]
    assert count_calls == [0]
    assert fetch_sizes == [6, 6]


@pytest.mark.asyncio
async def test_engine_honors_cancellation_during_record_iteration():
    client = FakeClient()
    cancelled = False
    emitted = 0

    def on_record():
        nonlocal cancelled, emitted
        emitted += 1
        if emitted == 1:
            cancelled = True

    engine = ExportEngine(
        client,
        index="aella-ser-*",
        raw_query={"query": {"match_all": {}}},
        time_field="timestamp",
        start=datetime(2026, 9, 1, 0, 0, tzinfo=UTC),
        end=datetime(2026, 9, 1, 0, 0, 2, tzinfo=UTC),
        target_records=10,
        minimum_slice_ms=1,
        on_record=on_record,
        cancel_check=lambda: cancelled,
    )

    records = []
    with pytest.raises(ExportCancelled):
        async for record in engine.iter_documents():
            records.append(record)

    assert len(records) == 1
    assert emitted == 1


class DuplicateIdentityClient:
    async def search(self, index, body):
        if body["size"] == 0:
            return {
                "hits": {
                    "total": {"value": 4, "relation": "eq"},
                    "hits": [],
                }
            }
        return {
            "hits": {
                "total": {"value": 4, "relation": "eq"},
                "hits": [
                    {"_index": "idx-a", "_id": "1", "_source": {"n": 1}},
                    {"_index": "idx-a", "_id": "1", "_source": {"n": 1}},
                    {"_index": "idx-b", "_id": "1", "_source": {"n": 2}},
                    {"_source": {"n": 3}},
                ],
            }
        }


@pytest.mark.asyncio
async def test_engine_deduplicates_only_stable_index_and_document_identity():
    duplicates = 0

    def on_duplicate():
        nonlocal duplicates
        duplicates += 1

    engine = ExportEngine(
        DuplicateIdentityClient(),
        index="idx-*",
        raw_query={"query": {"match_all": {}}},
        time_field="timestamp",
        start=datetime(2026, 9, 1, 0, 0, tzinfo=UTC),
        end=datetime(2026, 9, 1, 0, 0, 1, tzinfo=UTC),
        target_records=10,
        minimum_slice_ms=1,
        on_duplicate=on_duplicate,
    )
    records = [record async for record in engine.iter_documents()]

    assert records == [{"n": 1}, {"n": 2}, {"n": 3}]
    assert duplicates == 1


class SlowDocumentClient:
    def __init__(self):
        self.calls = []

    async def search(self, index, body):
        time_range = body["query"]["bool"]["filter"][0]["range"]["timestamp"]
        start = datetime.fromisoformat(time_range["gte"])
        end = datetime.fromisoformat(time_range["lt"])
        seconds = int((end - start).total_seconds())
        self.calls.append((start, end, body["size"]))

        if body["size"] == 0:
            return {"hits": {"total": {"value": seconds, "relation": "eq"}, "hits": []}}

        if seconds > 2:
            raise StellarReadTimeoutError("slow document response")

        hits = [
            {
                "_index": "idx-a",
                "_id": f"{start.timestamp()}-{i}",
                "_source": {"timestamp": start.isoformat(), "n": i},
            }
            for i in range(seconds)
        ]
        return {"hits": {"total": {"value": seconds, "relation": "eq"}, "hits": hits}}


@pytest.mark.asyncio
async def test_engine_bisects_slow_document_fetches_until_they_succeed():
    client = SlowDocumentClient()
    adaptive_splits = 0

    def on_adaptive_split():
        nonlocal adaptive_splits
        adaptive_splits += 1

    engine = ExportEngine(
        client,
        index="idx-*",
        raw_query={"query": {"match_all": {}}},
        time_field="timestamp",
        start=datetime(2026, 9, 1, 0, 0, tzinfo=UTC),
        end=datetime(2026, 9, 1, 0, 0, 4, tzinfo=UTC),
        target_records=10,
        minimum_slice_ms=1,
        on_adaptive_split=on_adaptive_split,
    )

    records = [record async for record in engine.iter_documents()]

    assert len(records) == 4
    assert adaptive_splits == 1
    fetch_ranges = [
        (end - start).total_seconds()
        for start, end, size in client.calls
        if size > 0
    ]
    assert fetch_ranges == [4, 2, 2]
