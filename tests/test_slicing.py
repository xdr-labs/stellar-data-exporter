from datetime import UTC, datetime

import pytest

from app.exporter import ExportEngine


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
