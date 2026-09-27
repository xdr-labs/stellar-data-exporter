import base64
import json

import httpx
import pytest

import app.stellar as stellar_module
from app.stellar import StellarClient


@pytest.mark.asyncio
async def test_stellar_client_exchanges_all_access_token_and_reuses_jwt():
    calls = {"token": 0, "search": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/connect/api/v1/access_token":
            calls["token"] += 1
            expected = "Basic " + base64.b64encode(
                b"admin@example.test:refresh-token"
            ).decode()
            assert request.headers["Authorization"] == expected
            return httpx.Response(200, json={"access_token": "jwt-1"})

        if request.url.path.endswith("/_search"):
            calls["search"] += 1
            assert request.headers["Authorization"] == "Bearer jwt-1"
            body = json.loads(request.content)
            assert body["query"]["bool"]["filter"] == [{"term": {"tenantid": "tenant-1"}}]
            assert body["query"]["bool"]["must"] == [{"match_all": {}}]
            return httpx.Response(
                200,
                json={"hits": {"total": {"value": 0, "relation": "eq"}, "hits": []}},
            )

        raise AssertionError(f"Unexpected URL: {request.url}")

    client = StellarClient(
        "https://stellar.example.test",
        "admin@example.test",
        "refresh-token",
        transport=httpx.MockTransport(handler),
        tenant_id="tenant-1",
    )

    await client.search("aella-ser-*", {"query": {"match_all": {}}})
    await client.search("aella-ser-*", {"query": {"match_all": {}}})

    assert calls == {"token": 1, "search": 2}


@pytest.mark.asyncio
async def test_stellar_client_refreshes_jwt_after_401():
    token_calls = 0
    search_tokens = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if request.url.path == "/connect/api/v1/access_token":
            token_calls += 1
            return httpx.Response(200, json={"access_token": f"jwt-{token_calls}"})

        if request.url.path.endswith("/_search"):
            auth = request.headers["Authorization"]
            search_tokens.append(auth)
            if auth == "Bearer jwt-1":
                return httpx.Response(401, json={"detail": "expired"})
            return httpx.Response(
                200,
                json={"hits": {"total": {"value": 1, "relation": "eq"}, "hits": []}},
            )

        raise AssertionError(f"Unexpected URL: {request.url}")

    client = StellarClient(
        "https://stellar.example.test",
        "admin@example.test",
        "refresh-token",
        transport=httpx.MockTransport(handler),
        tenant_id="tenant-1",
    )

    response = await client.search("aella-ser-*", {"query": {"match_all": {}}})

    assert response["hits"]["total"]["value"] == 1
    assert token_calls == 2
    assert search_tokens == ["Bearer jwt-1", "Bearer jwt-2"]


@pytest.mark.asyncio
async def test_user_scope_api_key_uses_bearer_exchange_and_lucene_search_params():
    calls = {"token": 0, "search": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/connect/api/v1/access_token":
            calls["token"] += 1
            assert request.headers["Authorization"] == "Bearer user-api-key"
            return httpx.Response(200, json={"access_token": "jwt-user"})

        if request.url.path.endswith("/_search"):
            calls["search"] += 1
            assert request.headers["Authorization"] == "Bearer jwt-user"
            assert request.url.params["size"] == "25"
            assert request.url.params["track_total_hits"] == "true"
            assert request.url.params["q"] == (
                '((event_status:New) AND tenantid:"tenant-1") AND '
                "timestamp:[1790294400000 TO 1790298000000}"
            )
            return httpx.Response(
                200,
                json={"hits": {"total": {"value": 2, "relation": "eq"}, "hits": []}},
            )

        raise AssertionError(f"Unexpected URL: {request.url}")

    client = StellarClient(
        "https://stellar.example.test",
        None,
        "user-api-key",
        transport=httpx.MockTransport(handler),
        auth_mode="user_scope",
        query_mode="stellar_lucene",
        stellar_query="event_status:New",
        tenant_id="tenant-1",
    )
    response = await client.search(
        "aella-ser-*",
        {
            "size": 25,
            "track_total_hits": True,
            "query": {
                "bool": {
                    "filter": [{
                        "range": {
                            "timestamp": {
                                "gte": "2026-09-25T00:00:00+00:00",
                                "lt": "2026-09-25T01:00:00+00:00",
                            }
                        }
                    }]
                }
            },
        },
    )

    assert response["hits"]["total"]["value"] == 2
    assert calls == {"token": 1, "search": 1}


@pytest.mark.asyncio
async def test_list_tenants_maps_and_sorts_accessible_tenants():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/connect/api/v1/access_token":
            return httpx.Response(200, json={"access_token": "jwt-1"})
        if request.url.path == "/connect/api/v1/tenants":
            assert request.headers["Authorization"] == "Bearer jwt-1"
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"cust_id": "b", "cust_name": "Zulu"},
                        {"cust_id": "a", "cust_name": "Alpha"},
                        {"cust_name": "Missing ID"},
                    ]
                },
            )
        raise AssertionError(f"Unexpected URL: {request.url}")

    client = StellarClient(
        "https://stellar.example.test",
        "admin@example.test",
        "refresh-token",
        transport=httpx.MockTransport(handler),
    )

    tenants = await client.list_tenants()

    assert tenants == [
        {"id": "a", "name": "Alpha"},
        {"id": "b", "name": "Zulu"},
    ]


@pytest.mark.asyncio
async def test_root_scope_search_injects_server_side_tenant_filter():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/connect/api/v1/access_token":
            return httpx.Response(200, json={"access_token": "jwt-1"})
        if request.url.path.endswith("/_search"):
            captured["body"] = __import__("json").loads(request.content)
            return httpx.Response(
                200,
                json={"hits": {"total": {"value": 0, "relation": "eq"}, "hits": []}},
            )
        raise AssertionError(f"Unexpected URL: {request.url}")

    client = StellarClient(
        "https://stellar.example.test",
        "admin@example.test",
        "refresh-token",
        transport=httpx.MockTransport(handler),
        tenant_id="tenant-42",
    )

    await client.search(
        "aella-ser-*",
        {
            "size": 0,
            "query": {"term": {"severity": 80}},
        },
    )

    scoped = captured["body"]["query"]["bool"]
    assert scoped["must"] == [{"term": {"severity": 80}}]
    assert scoped["filter"] == [{"term": {"tenantid": "tenant-42"}}]


@pytest.mark.asyncio
async def test_search_retries_transient_connection_failure(monkeypatch):
    calls = {"token": 0, "search": 0, "retry": 0}
    monkeypatch.setattr(stellar_module, "QUERY_RETRY_BASE_DELAY_SECONDS", 0)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/connect/api/v1/access_token":
            calls["token"] += 1
            return httpx.Response(200, json={"access_token": "jwt-1"})
        if request.url.path.endswith("/_search"):
            calls["search"] += 1
            if calls["search"] < 3:
                raise httpx.ConnectError("temporary reset", request=request)
            return httpx.Response(
                200,
                json={"hits": {"total": {"value": 1, "relation": "eq"}, "hits": []}},
            )
        raise AssertionError(f"Unexpected URL: {request.url}")

    client = StellarClient(
        "https://stellar.example.test",
        "admin@example.test",
        "refresh-token",
        transport=httpx.MockTransport(handler),
        tenant_id="tenant-1",
        on_retry=lambda count: calls.__setitem__("retry", calls["retry"] + count),
    )

    response = await client.search("aella-ser-*", {"query": {"match_all": {}}})

    assert response["hits"]["total"]["value"] == 1
    assert calls["search"] == 3
    assert calls["retry"] == 2


@pytest.mark.asyncio
async def test_search_retries_transient_http_status(monkeypatch):
    calls = {"search": 0, "retry": 0}
    monkeypatch.setattr(stellar_module, "QUERY_RETRY_BASE_DELAY_SECONDS", 0)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/connect/api/v1/access_token":
            return httpx.Response(200, json={"access_token": "jwt-1"})
        if request.url.path.endswith("/_search"):
            calls["search"] += 1
            if calls["search"] == 1:
                return httpx.Response(503, json={"detail": "temporarily unavailable"})
            return httpx.Response(
                200,
                json={"hits": {"total": {"value": 0, "relation": "eq"}, "hits": []}},
            )
        raise AssertionError(f"Unexpected URL: {request.url}")

    client = StellarClient(
        "https://stellar.example.test",
        "admin@example.test",
        "refresh-token",
        transport=httpx.MockTransport(handler),
        tenant_id="tenant-1",
        on_retry=lambda count: calls.__setitem__("retry", calls["retry"] + count),
    )

    response = await client.search("aella-ser-*", {"query": {"match_all": {}}})

    assert response["hits"]["total"]["value"] == 0
    assert calls == {"search": 2, "retry": 1}


@pytest.mark.asyncio
async def test_search_exhausted_read_timeouts_report_transport_reason(monkeypatch):
    calls = {"search": 0, "retry": 0}
    monkeypatch.setattr(stellar_module, "QUERY_RETRY_ATTEMPTS", 2)
    monkeypatch.setattr(stellar_module, "QUERY_RETRY_BASE_DELAY_SECONDS", 0)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/connect/api/v1/access_token":
            return httpx.Response(200, json={"access_token": "jwt-1"})
        if request.url.path.endswith("/_search"):
            calls["search"] += 1
            raise httpx.ReadTimeout("upstream response stalled", request=request)
        raise AssertionError(f"Unexpected URL: {request.url}")

    client = StellarClient(
        "https://stellar.example.test",
        "admin@example.test",
        "refresh-token",
        transport=httpx.MockTransport(handler),
        tenant_id="tenant-1",
        on_retry=lambda count: calls.__setitem__("retry", calls["retry"] + count),
    )

    with pytest.raises(stellar_module.StellarConnectionError) as excinfo:
        await client.search("aella-ser-*", {"query": {"match_all": {}}})

    message = str(excinfo.value)
    assert "after automatic retries" in message
    assert "accepted the connection" in message
    assert "read timeout (ReadTimeout)" in message
    assert "upstream response stalled" not in message
    assert calls == {"search": 2, "retry": 1}


@pytest.mark.asyncio
async def test_document_read_timeout_is_returned_for_adaptive_split_without_retries():
    calls = {"search": 0, "retry": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/connect/api/v1/access_token":
            return httpx.Response(200, json={"access_token": "jwt-1"})
        if request.url.path.endswith("/_search"):
            calls["search"] += 1
            raise httpx.ReadTimeout("slow document response", request=request)
        raise AssertionError(f"Unexpected URL: {request.url}")

    client = StellarClient(
        "https://stellar.example.test",
        "admin@example.test",
        "refresh-token",
        transport=httpx.MockTransport(handler),
        tenant_id="tenant-1",
        on_retry=lambda count: calls.__setitem__("retry", calls["retry"] + count),
    )

    with pytest.raises(stellar_module.StellarReadTimeoutError) as excinfo:
        await client.search("aella-ser-*", {"size": 250, "query": {"match_all": {}}})

    assert "smaller adaptive time slices" in str(excinfo.value)
    assert calls == {"search": 1, "retry": 0}
