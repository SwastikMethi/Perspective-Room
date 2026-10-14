"""TypeSafe Jev adapter: a small HTTPX client (doc 13), pinned model, bearer auth.

The official SDK is avoided on purpose: it brings its own retries (we keep one policy in
`providers.calls`) and logs request bodies unredacted.
"""

import json
from typing import Any

import httpx

from app.providers.base import ProviderFailure
from app.providers.calls import classify_http

JEV_BASE_URL = "https://api.typesafe.ai"


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-finite number in Jev response: {name}")


class JevCoordinator:
    name = "jev"

    def __init__(
        self, api_key: str, model: str, *, http_client: httpx.AsyncClient | None = None
    ) -> None:
        self.model = model
        self._auth = {"Authorization": f"Bearer {api_key}"}
        self.client = http_client or httpx.AsyncClient(
            base_url=JEV_BASE_URL, timeout=httpx.Timeout(60.0, connect=10.0)
        )

    async def _send(self, method: str, path: str, **kw: Any) -> httpx.Response:
        try:
            r = await self.client.request(method, path, headers=self._auth, **kw)
        except httpx.ConnectError as e:
            raise ProviderFailure("transient", "Could not reach Jev.", retryable=True) from e
        except httpx.TimeoutException as e:
            raise ProviderFailure(
                "timeout", "Jev did not answer in time.", usage_unknown=True
            ) from e
        except httpx.HTTPError as e:
            raise ProviderFailure(
                "provider_error", "Connection to Jev was lost.", usage_unknown=True
            ) from e
        if r.status_code != 200:
            raise classify_http(
                r.status_code,
                r.text,
                retry_after=r.headers.get("retry-after"),
                request_id=r.headers.get("x-typesafe-request-id"),
            )
        return r

    async def ask(
        self, state: dict[str, Any], questions: dict[str, Any], model: str | None = None
    ) -> dict[str, Any]:
        r = await self._send(
            "POST",
            "/v1/systemone",
            json={"model": model or self.model, "state": state, "questions": questions},
        )
        try:
            body = json.loads(r.content, parse_constant=_reject_constant)
        except ValueError as e:
            raise ProviderFailure("provider_error", "Jev returned invalid JSON.") from e
        if not isinstance(body, dict):
            raise ProviderFailure("provider_error", "Jev returned an unexpected body.")
        return body

    async def check(self) -> None:
        """Explicit connection check (free): lists models with the configured key."""
        await self._send("GET", "/v1/models")
