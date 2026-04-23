"""
Omium MCP Server — persistent Streamable-HTTP transport.

Two authorized tools, both routed through Kong:
  - list_workflows   -> GET /api/v1/workflows
  - list_executions  -> GET /api/v1/executions

Auth flow: MCP clients connect to http://<host>:9000/mcp with an
`Authorization: Bearer omium_...` header. A small ASGI middleware captures
that token into a ContextVar; each tool reads the contextvar and forwards
the key as `X-API-Key` to Kong. Tenant scoping is derived server-side from
the key, so no tenant_id parameter is ever accepted or passed.
"""

from __future__ import annotations

import contextvars
import os

import httpx
import uvicorn
from mcp.server.fastmcp import FastMCP

OMIUM_API_BASE = os.environ.get("OMIUM_API_BASE", "http://kong:8000")
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", "9100"))

_api_key: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "omium_api_key", default=None
)


class BearerAuthMiddleware:
    """Extract `Authorization: Bearer <token>` into a ContextVar, reject if missing."""

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


async def _omium_get(path: str, params: dict | None = None) -> dict:
    key = _api_key.get()
    if not key:
        raise RuntimeError("no Omium API key bound to this request")
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            f"{OMIUM_API_BASE}{path}",
            headers={"X-API-Key": key},
            params=params,
        )
        r.raise_for_status()
        return r.json()


mcp = FastMCP("omium-mcp")


@mcp.tool()
async def list_workflows() -> dict:
    """List workflows for the caller's tenant.

    Calls GET /api/v1/workflows through Kong. Tenant scope is derived from
    the caller's Omium API key — no tenant_id argument is needed or honored.
    """
    return await _omium_get("/api/v1/workflows")


@mcp.tool()
async def list_executions() -> dict:
    """List recent executions for the caller's tenant.

    Calls GET /api/v1/executions through Kong. Tenant scope is derived from
    the caller's Omium API key.
    """
    return await _omium_get("/api/v1/executions")


app = mcp.streamable_http_app()
app.add_middleware(BearerAuthMiddleware)


if __name__ == "__main__":
    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT)
