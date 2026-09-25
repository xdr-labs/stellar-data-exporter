from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any


DOCUMENT_ONLY_KEYS = {"aggs", "aggregations", "collapse"}


def compile_user_query(
    query_mode: str,
    raw: dict[str, Any],
    stellar_query: str | None = None,
) -> dict[str, Any]:
    if query_mode == "stellar_lucene":
        expression = (stellar_query or "").strip()
        if not expression:
            raise ValueError("Stellar Cyber Query cannot be empty")
        return {"query": {"query_string": {"query": expression}}}
    return deepcopy(raw)


def build_document_query(
    raw: dict[str, Any],
    *,
    time_field: str,
    start: datetime,
    end: datetime,
    size: int,
    track_total_hits: bool = True,
) -> dict[str, Any]:
    body = deepcopy(raw)
    for key in DOCUMENT_ONLY_KEYS:
        body.pop(key, None)

    original_query = body.get("query", {"match_all": {}})
    body["query"] = {
        "bool": {
            "must": [original_query],
            "filter": [
                {
                    "range": {
                        time_field: {
                            "gte": start.isoformat(),
                            "lt": end.isoformat(),
                        }
                    }
                }
            ],
        }
    }
    body["size"] = size
    body["track_total_hits"] = track_total_hits
    body.pop("from", None)
    body.pop("search_after", None)
    return body


def total_hits(response: dict[str, Any]) -> tuple[int, bool]:
    total = response.get("hits", {}).get("total", 0)
    if isinstance(total, int):
        return total, True
    if isinstance(total, dict):
        value = int(total.get("value", 0))
        return value, total.get("relation", "eq") == "eq"
    return 0, False


def hit_identity(hit: dict[str, Any]) -> tuple[str, str] | None:
    index = hit.get("_index")
    document_id = hit.get("_id")
    if isinstance(index, str) and index and isinstance(document_id, str) and document_id:
        return index, document_id
    return None


def hit_source(hit: dict[str, Any]) -> dict[str, Any]:
    source = hit.get("_source")
    if isinstance(source, dict):
        return source
    fields = hit.get("fields")
    if isinstance(fields, dict):
        return fields
    return hit
