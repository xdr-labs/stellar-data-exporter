import httpx
import pytest

from app.stellar import StellarClient


@pytest.mark.asyncio
async def test_list_tenants_normalizes_and_sorts_accessible_tenants():
    calls = {"token": 0, "tenants": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/connect/api/v1/access_token":
            calls["token"] += 1
            assert request.headers["Authorization"] == "Bearer user-api-key"
            return httpx.Response(200, json={"access_token": "jwt-user"})
        if request.url.path == "/connect/api/v1/tenants":
            calls["tenants"] += 1
            assert request.headers["Authorization"] == "Bearer jwt-user"
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"cust_id": "tenant-b", "cust_name": "Zulu Tenant"},
                        {"cust_id": "tenant-a", "cust_name": "Alpha Tenant"},
                        {"ignored": True},
                    ]
                },
            )
        raise AssertionError(f"Unexpected URL: {request.url}")

    client = StellarClient(
        "https://stellar.example.test",
        None,
        "user-api-key",
        transport=httpx.MockTransport(handler),
        auth_mode="user_scope",
        query_mode="stellar_lucene",
        stellar_query="*:*",
    )
    tenants = await client.list_tenants()

    assert tenants == [
        {"id": "tenant-a", "name": "Alpha Tenant"},
        {"id": "tenant-b", "name": "Zulu Tenant"},
    ]
    assert calls == {"token": 1, "tenants": 1}
