from datetime import UTC, datetime

import pytest

from app.exporter import ExportCancelled, ExportEngine


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
            return {"hits": {"total": {"value": total, "relation": "eq"}, "hits": []}}

        hits = [{"_source": {"timestamp": start.isoformat(), "n": i}} for i in range(total)]
        return {"hits": {"total": {"value": total, "relation": "eq"}, "hits": hits}}


@pytest.mark.asyncio
async def test_engine_splits_large_time_ranges_until_under_target():
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
    )

    records = [record async for record in engine.iter_documents()]
    assert len(records) == 20
    fetch_sizes = [size for _, _, size in client.calls if size > 0]
    assert fetch_sizes
    assert all(size == 5 for size in fetch_sizes)


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
    fetch_sizes = [size for _, _, size in client.calls if size > 0]
    assert len(fetch_sizes) == 2


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
