from __future__ import annotations

import asyncio
import time
from copy import deepcopy
from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx


JWT_REFRESH_AGE_SECONDS = 8 * 60
QUERY_RETRY_ATTEMPTS = 4
QUERY_RETRY_BASE_DELAY_SECONDS = 0.5
TRANSIENT_HTTP_STATUSES = {408, 429, 500, 502, 503, 504}


class StellarAPIError(RuntimeError):
    pass


class StellarAuthError(StellarAPIError):
    pass


class StellarPermissionError(StellarAPIError):
    pass


class StellarConnectionError(StellarAPIError):
    pass


def transport_failure_summary(exc: BaseException | None, *, operation: str) -> str:
    current = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, httpx.ReadTimeout):
            return (
                f"Last failure: Stellar Cyber accepted the connection but did not return "
                f"the {operation} response before the read timeout (ReadTimeout)."
            )
        if isinstance(current, httpx.ConnectTimeout):
            return (
                f"Last failure: the connection to Stellar Cyber was not established "
                f"before the connect timeout (ConnectTimeout)."
            )
        if isinstance(current, httpx.PoolTimeout):
            return (
                f"Last failure: the Exporter could not acquire an HTTP connection in time "
                f"(PoolTimeout)."
            )
        if isinstance(current, httpx.WriteTimeout):
            return (
                f"Last failure: the request to Stellar Cyber could not be sent in time "
                f"(WriteTimeout)."
            )
        if isinstance(current, httpx.RemoteProtocolError):
            return (
                f"Last failure: Stellar Cyber or an intermediate proxy closed the connection "
                f"or returned an invalid HTTP response (RemoteProtocolError)."
            )
        if isinstance(current, httpx.ReadError):
            return (
                f"Last failure: the connection dropped while the Exporter was reading the "
                f"{operation} response (ReadError)."
            )
        if isinstance(current, httpx.ConnectError):
            return (
                f"Last failure: the TCP/TLS connection to Stellar Cyber could not be "
                f"established (ConnectError)."
            )
        if isinstance(current, httpx.RequestError):
            return (
                f"Last failure: HTTP transport failed while performing the {operation} "
                f"({type(current).__name__})."
            )
        current = current.__cause__ or current.__context__

    return f"Last failure: the Stellar Cyber {operation} transport was unavailable."


class StellarClient:
    def __init__(
        self,
        host: str,
        email: str | None,
        token: str,
        verify_tls: bool = True,
        transport: httpx.AsyncBaseTransport | None = None,
        on_retry: Callable[[int], None] | None = None,
        auth_mode: str = "root_scope",
        query_mode: str = "elasticsearch_dsl",
        stellar_query: str | None = None,
        tenant_id: str | None = None,
    ):
        self.host = host.rstrip("/")
        self.email = email
        self.token = token
        self.verify_tls = verify_tls
        self.transport = transport
        self.on_retry = on_retry
        self.auth_mode = auth_mode
        self.query_mode = query_mode
        self.stellar_query = (stellar_query or "").strip() or None
        self.tenant_id = (tenant_id or "").strip() or None
        self._jwt: str | None = None
        self._jwt_obtained_at = 0.0
        self._jwt_lock = asyncio.Lock()

    async def _get_access_token(
        self,
        client: httpx.AsyncClient,
        *,
        force_refresh: bool = False,
    ) -> str:
        async with self._jwt_lock:
            age = time.monotonic() - self._jwt_obtained_at
            if not force_refresh and self._jwt and age < JWT_REFRESH_AGE_SECONDS:
                return self._jwt

            url = f"{self.host}/connect/api/v1/access_token"
            try:
                if self.auth_mode == "user_scope":
                    response = await client.post(
                        url,
                        headers={
                            "Authorization": f"Bearer {self.token}",
                            "Accept": "application/json",
                        },
                    )
                else:
                    if not self.email:
                        raise StellarAuthError(
                            "Root Scope authentication requires an account email."
                        )
                    response = await client.post(
                        url,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                        auth=httpx.BasicAuth(self.email, self.token),
                    )
            except httpx.RequestError as exc:
                raise StellarConnectionError(
                    "Cannot reach the Stellar Cyber host. Check the host address, DNS/network path, port, and TLS settings."
                ) from exc

            if response.status_code == 401:
                credential = (
                    "User Scope API Key"
                    if self.auth_mode == "user_scope"
                    else "account email and Root Scope All-Access Token"
                )
                raise StellarAuthError(
                    f"Authentication failed. Check the {credential}."
                )
            if response.status_code == 403:
                raise StellarPermissionError(
                    "Authentication was rejected by Stellar Cyber policy for this credential."
                )
            if response.status_code >= 400:
                raise StellarAPIError(
                    f"Stellar Cyber access-token request failed with HTTP {response.status_code}."
                )

            try:
                access_token = response.json()["access_token"]
            except (ValueError, KeyError, TypeError) as exc:
                raise StellarAPIError(
                    "Stellar Cyber returned an invalid access-token response."
                ) from exc

            if not isinstance(access_token, str) or not access_token:
                raise StellarAPIError("Stellar Cyber returned an empty access token.")

            self._jwt = access_token
            self._jwt_obtained_at = time.monotonic()
            return access_token

    @staticmethod
    def _epoch_millis(value: Any) -> int:
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return int(parsed.timestamp() * 1000)
        raise StellarAPIError("User Scope time range contains an unsupported value.")

    def _user_scope_search_params(self, body: dict[str, Any]) -> dict[str, Any]:
        if self.query_mode != "stellar_lucene" and self.stellar_query:
            raise StellarAPIError(
                "User Scope API Key requires Stellar Cyber Query (Lucene) mode."
            )

        params: dict[str, Any] = {
            "size": int(body.get("size", 10)),
            "track_total_hits": (
                "true" if bool(body.get("track_total_hits", False)) else "false"
            ),
        }
        expression = self.stellar_query or "*:*"
        if not self.tenant_id:
            raise StellarAPIError("Tenant selection is required before querying data.")
        expression = f'({expression}) AND tenantid:"{self.tenant_id}"'

        query = body.get("query")
        if isinstance(query, dict):
            bool_query = query.get("bool")
            if isinstance(bool_query, dict):
                filters = bool_query.get("filter") or []
                if isinstance(filters, dict):
                    filters = [filters]
                for item in filters:
                    if not isinstance(item, dict) or "range" not in item:
                        continue
                    ranges = item.get("range")
                    if not isinstance(ranges, dict) or not ranges:
                        continue
                    field, bounds = next(iter(ranges.items()))
                    if not isinstance(bounds, dict):
                        continue
                    lower_key = "gte" if "gte" in bounds else "gt" if "gt" in bounds else None
                    upper_key = "lt" if "lt" in bounds else "lte" if "lte" in bounds else None
                    if not lower_key or not upper_key:
                        continue
                    lower = self._epoch_millis(bounds[lower_key])
                    upper = self._epoch_millis(bounds[upper_key])
                    left = "[" if lower_key == "gte" else "{"
                    right = "}" if upper_key == "lt" else "]"
                    range_query = f"{field}:{left}{lower} TO {upper}{right}"
                    expression = f"({expression}) AND {range_query}"
                    break

        params["q"] = expression
        return params

    def _tenant_scoped_body(self, body: dict[str, Any]) -> dict[str, Any]:
        if not self.tenant_id:
            raise StellarAPIError("Tenant selection is required before querying data.")
        scoped = deepcopy(body)
        existing_query = scoped.get("query") or {"match_all": {}}
        scoped["query"] = {
            "bool": {
                "must": [existing_query],
                "filter": [{"term": {"tenantid": self.tenant_id}}],
            }
        }
        return scoped

    async def list_tenants(self) -> list[dict[str, str]]:
        url = f"{self.host}/connect/api/v1/tenants"
        timeout = httpx.Timeout(30.0, connect=15.0)
        response: httpx.Response | None = None
        force_refresh = False
        last_connection_error: Exception | None = None

        async with httpx.AsyncClient(
            verify=self.verify_tls,
            timeout=timeout,
            transport=self.transport,
        ) as client:
            for attempt in range(QUERY_RETRY_ATTEMPTS):
                try:
                    jwt = await self._get_access_token(
                        client,
                        force_refresh=force_refresh,
                    )
                    force_refresh = False
                    response = await client.get(
                        url,
                        headers={
                            "Authorization": f"Bearer {jwt}",
                            "Accept": "application/json",
                            "Content-Type": "application/json",
                        },
                    )
                except (httpx.RequestError, StellarConnectionError) as exc:
                    last_connection_error = exc
                    if attempt + 1 >= QUERY_RETRY_ATTEMPTS:
                        raise StellarConnectionError(
                            "Cannot reach the Stellar Cyber tenant API after automatic retries. "
                            + transport_failure_summary(exc, operation="tenant API")
                        ) from exc
                    if self.on_retry:
                        self.on_retry(1)
                    await asyncio.sleep(
                        QUERY_RETRY_BASE_DELAY_SECONDS * (2 ** attempt)
                    )
                    continue

                if response.status_code == 401 and attempt + 1 < QUERY_RETRY_ATTEMPTS:
                    force_refresh = True
                    if self.on_retry:
                        self.on_retry(1)
                    continue
                if (
                    response.status_code in TRANSIENT_HTTP_STATUSES
                    and attempt + 1 < QUERY_RETRY_ATTEMPTS
                ):
                    if self.on_retry:
                        self.on_retry(1)
                    await asyncio.sleep(
                        QUERY_RETRY_BASE_DELAY_SECONDS * (2 ** attempt)
                    )
                    continue
                break

        if response is None:
            raise StellarConnectionError(
                "Cannot reach the Stellar Cyber tenant API."
            ) from last_connection_error
        if response.status_code == 401:
            raise StellarAuthError("Stellar Cyber rejected the session token while loading tenants.")
        if response.status_code == 403:
            raise StellarPermissionError("This credential cannot list accessible Stellar Cyber tenants.")
        if response.status_code >= 400:
            raise StellarAPIError(
                f"Stellar Cyber tenant request failed with HTTP {response.status_code}."
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise StellarAPIError("Stellar Cyber tenant API did not return valid JSON.") from exc

        items = payload if isinstance(payload, list) else payload.get("data", []) if isinstance(payload, dict) else []
        tenants: list[dict[str, str]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            tenant_id = item.get("cust_id") or item.get("tenantid") or item.get("id")
            tenant_name = item.get("cust_name") or item.get("tenant_name") or item.get("name")
            if tenant_id and tenant_name:
                tenants.append({"id": str(tenant_id), "name": str(tenant_name)})
        tenants.sort(key=lambda item: item["name"].casefold())
        return tenants

    async def search(self, index: str, body: dict[str, Any]) -> dict[str, Any]:
        encoded_index = quote(index, safe="*,-._")
        url = f"{self.host}/connect/api/data/{encoded_index}/_search"
        timeout = httpx.Timeout(60.0, connect=15.0)
        response: httpx.Response | None = None
        force_refresh = False
        last_connection_error: Exception | None = None

        async with httpx.AsyncClient(
            verify=self.verify_tls,
            timeout=timeout,
            transport=self.transport,
        ) as client:
            for attempt in range(QUERY_RETRY_ATTEMPTS):
                try:
                    jwt = await self._get_access_token(
                        client,
                        force_refresh=force_refresh,
                    )
                    force_refresh = False
                    headers = {
                        "Authorization": f"Bearer {jwt}",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    }
                    if self.auth_mode == "user_scope":
                        response = await client.request(
                            "GET",
                            url,
                            headers=headers,
                            params=self._user_scope_search_params(body),
                        )
                    else:
                        response = await client.request(
                            "GET",
                            url,
                            headers=headers,
                            json=self._tenant_scoped_body(body),
                        )
                except (httpx.RequestError, StellarConnectionError) as exc:
                    last_connection_error = exc
                    if attempt + 1 >= QUERY_RETRY_ATTEMPTS:
                        raise StellarConnectionError(
                            "Connection to Stellar Cyber remained unavailable after automatic retries. "
                            + transport_failure_summary(exc, operation="query")
                        ) from exc
                    if self.on_retry:
                        self.on_retry(1)
                    await asyncio.sleep(
                        QUERY_RETRY_BASE_DELAY_SECONDS * (2 ** attempt)
                    )
                    continue

                if response.status_code == 401 and attempt + 1 < QUERY_RETRY_ATTEMPTS:
                    force_refresh = True
                    if self.on_retry:
                        self.on_retry(1)
                    continue

                if (
                    response.status_code in TRANSIENT_HTTP_STATUSES
                    and attempt + 1 < QUERY_RETRY_ATTEMPTS
                ):
                    if self.on_retry:
                        self.on_retry(1)
                    await asyncio.sleep(
                        QUERY_RETRY_BASE_DELAY_SECONDS * (2 ** attempt)
                    )
                    continue
                break

        if response is None:
            raise StellarConnectionError(
                "Connection to Stellar Cyber failed while querying data."
            ) from last_connection_error
        if response.status_code == 401:
            raise StellarAuthError(
                "Stellar Cyber rejected the session token. Recheck the selected credential type and credential."
            )
        if response.status_code == 403:
            raise StellarPermissionError(
                "Connected, but Stellar Cyber rejected raw-data access for this credential."
            )
        if response.status_code == 404:
            raise StellarAPIError(
                "The Stellar data API or one of the selected data sources was not found."
            )
        if response.status_code >= 400:
            detail = response.text[:500]
            raise StellarAPIError(
                f"Stellar Cyber query failed with HTTP {response.status_code}: {detail}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise StellarAPIError("Stellar Cyber did not return valid JSON.") from exc
