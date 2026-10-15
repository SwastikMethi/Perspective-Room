"""Request guards (doc 13, T24), pure ASGI so SSE streams pass untouched:
- Host must be a local name or the configured public host (blocks DNS rebinding) → 400;
- a mutation from another site (Sec-Fetch-Site: cross-site, or an Origin that is neither an
  allowed origin nor this server's own origin) → 403 cross_site_rejected;
- a mutation that carries a body must send JSON → 415 json_required.
Requests without Origin/Sec-Fetch-* (CLI, scripts) are allowed; there is no CORS."""

import json
from urllib.parse import urlsplit
from uuid import uuid4

from starlette.types import ASGIApp, Receive, Scope, Send

from app.settings import AppEnv

MUTATIONS = {"POST", "PUT", "PATCH", "DELETE"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]"}


def _host_name(host: str) -> str:
    host = host.strip().lower()
    if host.startswith("["):
        return host.split("]", 1)[0] + "]"
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


class SecurityMiddleware:
    def __init__(self, app: ASGIApp, env: AppEnv) -> None:
        self.app = app
        self.origins = set(env.allowed_origins)
        self.hosts = LOCAL_HOSTS | {env.APP_PUBLIC_HOST.lower()}
        self.hosts |= {(urlsplit(o).hostname or "").lower() for o in self.origins} - {""}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        host = headers.get("host", "")
        if _host_name(host) not in self.hosts:
            await self._reject(
                scope, send, 400, "bad_request", "This server does not answer for that host name."
            )
            return
        if scope["method"] in MUTATIONS:
            origin = headers.get("origin")
            own = f"{scope.get('scheme', 'http')}://{host}"
            cross = headers.get("sec-fetch-site") == "cross-site" or (
                origin is not None and origin not in self.origins and origin != own
            )
            if cross:
                await self._reject(
                    scope,
                    send,
                    403,
                    "cross_site_rejected",
                    "Changes must come from this app’s own pages.",
                )
                return
            has_body = (
                int(headers.get("content-length", "0") or 0) > 0 or "transfer-encoding" in headers
            )
            ctype = headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if has_body and ctype != "application/json":
                await self._reject(
                    scope, send, 415, "json_required", "Send the request body as application/json."
                )
                return
        await self.app(scope, receive, send)

    async def _reject(self, scope: Scope, send: Send, status: int, code: str, message: str) -> None:
        rid = scope.get("state", {}).get("request_id") or uuid4().hex
        body = json.dumps(
            {"code": code, "message": message, "retryable": False, "request_id": rid, "details": {}}
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
