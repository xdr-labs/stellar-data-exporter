import base64

import httpx
import pytest

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
                "(event_status:New) AND "
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
