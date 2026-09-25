from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import httpx


JWT_REFRESH_AGE_SECONDS = 8 * 60


class StellarAPIError(RuntimeError):
    pass


class StellarAuthError(StellarAPIError):
    pass


class StellarPermissionError(StellarAPIError):
    pass


class StellarConnectionError(StellarAPIError):
    pass


class StellarClient:
    def __init__(
        self,
        host: str,
        email: str,
        token: str,
        verify_tls: bool = True,
        transport: httpx.AsyncBaseTransport | None = None,
        on_retry: Callable[[int], None] | None = None,
    ):
        self.host = host.rstrip("/")
        self.email = email
        self.token = token
        self.verify_tls = verify_tls
        self.transport = transport
        self.on_retry = on_retry
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
                raise StellarAuthError(
                    "Authentication failed. Check the account email and All-Access Token."
                )
            if response.status_code == 403:
                raise StellarPermissionError(
                    "Authentication was rejected by policy. Verify the account is a root-scope Super Admin with an All-Access Token."
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

    async def search(self, index: str, body: dict[str, Any]) -> dict[str, Any]:
        encoded_index = quote(index, safe="*,-._")
        url = f"{self.host}/connect/api/data/{encoded_index}/_search"
        timeout = httpx.Timeout(60.0, connect=15.0)

        try:
            async with httpx.AsyncClient(
                verify=self.verify_tls,
                timeout=timeout,
                transport=self.transport,
            ) as client:
                for attempt in range(2):
                    jwt = await self._get_access_token(
                        client,
                        force_refresh=attempt == 1,
                    )
                    response = await client.request(
                        "GET",
                        url,
                        headers={
                            "Authorization": f"Bearer {jwt}",
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                        },
                        json=body,
                    )
                    if response.status_code != 401 or attempt == 1:
                        break
                    if self.on_retry:
                        self.on_retry(1)
        except httpx.RequestError as exc:
            raise StellarConnectionError(
                "Connection to Stellar Cyber failed while querying data. Check the host, network path, and TLS settings."
            ) from exc

        if response.status_code == 401:
            raise StellarAuthError(
                "Stellar Cyber rejected the session token. Recheck the account email and All-Access Token."
            )
        if response.status_code == 403:
            raise StellarPermissionError(
                "Connected, but this account does not have permission to query raw data. Root-scope Super Admin access is required."
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
