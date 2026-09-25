from datetime import UTC, datetime

from app.query import build_document_query, compile_user_query, total_hits


def test_build_query_wraps_time_filter_and_preserves_source():
    start = datetime(2026, 9, 1, tzinfo=UTC)
    end = datetime(2026, 9, 2, tzinfo=UTC)
    body = build_document_query(
        {"query": {"term": {"severity": 80}}, "_source": ["timestamp", "severity"]},
        time_field="timestamp",
        start=start,
        end=end,
        size=100,
    )

    assert body["size"] == 100
    assert body["_source"] == ["timestamp", "severity"]
    assert body["query"]["bool"]["must"][0] == {"term": {"severity": 80}}
    time_range = body["query"]["bool"]["filter"][0]["range"]["timestamp"]
    assert time_range["gte"] == start.isoformat()
    assert time_range["lt"] == end.isoformat()


def test_total_hits_supports_object_shape():
    assert total_hits({"hits": {"total": {"value": 42, "relation": "eq"}}}) == (42, True)
    assert total_hits({"hits": {"total": {"value": 10000, "relation": "gte"}}}) == (10000, False)


def test_compile_stellar_lucene_query_to_elasticsearch_query_string():
    compiled = compile_user_query(
        "stellar_lucene",
        {},
        'event_status:New AND event_name:"Login Failure"',
    )
    assert compiled == {
        "query": {
            "query_string": {
                "query": 'event_status:New AND event_name:"Login Failure"'
            }
        }
    }
