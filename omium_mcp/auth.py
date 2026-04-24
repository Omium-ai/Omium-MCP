"""Auth wiring — shared between HTTP and stdio transports.

Both transports end up populating the same `_api_key` ContextVar. Tool code
then reads it via `get_api_key()` and forwards to Kong as `X-API-Key`. Only
the population method differs per transport:

  HTTP  -> `BearerAuthMiddleware` reads `Authorization: Bearer ...` per request
  stdio -> `init_from_env()` reads `$OMIUM_API_KEY` once at process start
"""

from __future__ import annotations

import contextvars
import os

_api_key: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "omium_api_key", default=None
)


def get_api_key() -> str:
    """Return the API key bound to the current request/process.

    Raises if no key has been set — a programming error in either transport
    (middleware didn't run, or env var wasn't set).
    """
    k = _api_key.get()
    if not k:
        raise RuntimeError("no Omium API key bound to this request")
    return k


def init_from_env() -> None:
    """Populate the ContextVar from $OMIUM_API_KEY. Used by stdio transport."""
    key = os.environ.get("OMIUM_API_KEY")
    if not key:
        raise RuntimeError(
            "OMIUM_API_KEY environment variable is not set. "
            "Set it in your MCP client config, e.g. "
            '{"command": "omium-mcp", "env": {"OMIUM_API_KEY": "omium_..."}}'
        )
    _api_key.set(key)


class BearerAuthMiddleware:
    """Extract `Authorization: Bearer <token>` into the ContextVar per HTTP request."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        auth = ""
        for name, value in scope.get("headers") or []:
            if name == b"authorization":
                auth = value.decode("latin-1")
                break

        scheme, _, token = auth.partition(" ")
        if scheme.lower() != "bearer" or not token:
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"www-authenticate", b'Bearer realm="omium-mcp"'),
                    ],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b'{"error":"missing Authorization: Bearer <omium_api_key> header"}',
                }
            )
            return

        reset_token = _api_key.set(token)
        try:
            await self.app(scope, receive, send)
        finally:
            _api_key.reset(reset_token)
