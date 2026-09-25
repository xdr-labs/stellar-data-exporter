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
