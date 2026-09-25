from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import quote

import httpx


JWT_REFRESH_AGE_SECONDS = 8 * 60


class StellarAPIError(RuntimeError):
    pass


class StellarClient:
    def __init__(
        self,
        host: str,
        email: str,
        token: str,
        verify_tls: bool = True,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.host = host.rstrip("/")
        self.email = email
        self.token = token
        self.verify_tls = verify_tls
        self.transport = transport
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
            if (
                not force_refresh
                and self._jwt
                and age < JWT_REFRESH_AGE_SECONDS
            ):
                return self._jwt

            url = f"{self.host}/connect/api/v1/access_token"
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            response = await client.post(
                url,
                headers=headers,
                auth=httpx.BasicAuth(self.email, self.token),
            )
            if response.status_code >= 400:
                detail = response.text[:1200]
                raise StellarAPIError(
                    "Failed to obtain Stellar Cyber access token "
                    f"(HTTP {response.status_code}): {detail}"
                )

            try:
                payload = response.json()
                access_token = payload["access_token"]
            except (ValueError, KeyError, TypeError) as exc:
                raise StellarAPIError(
                    "Stellar Cyber access_token response did not contain access_token"
                ) from exc

            if not isinstance(access_token, str) or not access_token:
                raise StellarAPIError("Stellar Cyber returned an empty access token")

            self._jwt = access_token
            self._jwt_obtained_at = time.monotonic()
            return access_token

    async def search(self, index: str, body: dict[str, Any]) -> dict[str, Any]:
        encoded_index = quote(index, safe="*,-._")
        url = f"{self.host}/connect/api/data/{encoded_index}/_search"
        timeout = httpx.Timeout(60.0, connect=15.0)

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
                headers = {
                    "Authorization": f"Bearer {jwt}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                }
                response = await client.request(
                    "GET",
                    url,
                    headers=headers,
                    json=body,
                )
                if response.status_code != 401 or attempt == 1:
                    break

        if response.status_code >= 400:
            detail = response.text[:1200]
            raise StellarAPIError(
                f"Stellar Cyber API returned HTTP {response.status_code}: {detail}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise StellarAPIError("Stellar Cyber API did not return JSON") from exc
