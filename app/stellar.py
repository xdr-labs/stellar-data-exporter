from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx


class StellarAPIError(RuntimeError):
    pass


class StellarClient:
    def __init__(self, host: str, token: str, verify_tls: bool = True):
        self.host = host.rstrip("/")
        self.token = token
        self.verify_tls = verify_tls

    async def search(self, index: str, body: dict[str, Any]) -> dict[str, Any]:
        encoded_index = quote(index, safe="*,-._")
        url = f"{self.host}/connect/api/data/{encoded_index}/_search"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        timeout = httpx.Timeout(60.0, connect=15.0)
        async with httpx.AsyncClient(verify=self.verify_tls, timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=body)

        if response.status_code >= 400:
            detail = response.text[:1200]
            raise StellarAPIError(
                f"Stellar Cyber API returned HTTP {response.status_code}: {detail}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise StellarAPIError("Stellar Cyber API did not return JSON") from exc
