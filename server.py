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
import re

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


async def _omium_post(path: str, json_body: dict | None = None) -> dict:
    key = _api_key.get()
    if not key:
        raise RuntimeError("no Omium API key bound to this request")
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{OMIUM_API_BASE}{path}",
            headers={"X-API-Key": key, "Content-Type": "application/json"},
            json=json_body or {},
        )
        r.raise_for_status()
        return r.json()


_tenant_slug_cache: dict[str, str] = {}


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "unknown"


async def _resolve_tenant_slug() -> str:
    """Return a trace-friendly slug for the current request's tenant.

    Looks up the bearer token's tenant via GET /api/v1/api-keys/verify once,
    then serves from an in-process cache. Only used to build the default
    agent_id label when create_execution is called without one.
    """
    key = _api_key.get()
    if not key:
        raise RuntimeError("no Omium API key bound to this request")
    cached = _tenant_slug_cache.get(key)
    if cached is not None:
        return cached
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            f"{OMIUM_API_BASE}/api/v1/api-keys/verify",
            headers={"X-API-Key": key},
        )
        r.raise_for_status()
        data = r.json()
    slug = _slugify(data.get("tenant_name") or "")
    _tenant_slug_cache[key] = slug
    return slug


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

@mcp.tool()
async def get_workflows(workflow_id: str) -> dict:
    """Get a specific workflow for the caller's tenant.

    Calls GET /api/v1/workflows/<workflow_id> through Kong. Tenant scope is derived from
    the caller's Omium API key.
    """
    return await _omium_get(f"/api/v1/workflows/{workflow_id}")

@mcp.tool()
async def get_execution(execution_id: str) -> dict:
    """Get a specific execution for the caller's tenant.

    Calls GET /api/v1/executions/<execution_id> through Kong. Tenant scope is derived from
    the caller's Omium API key.
    """
    return await _omium_get(f"/api/v1/executions/{execution_id}")

@mcp.tool()
async def list_checkpoints(execution_id: str) -> dict:
    """List checkpoints for a specific execution.

    Calls GET /api/v1/executions/<execution_id>/checkpoints through Kong. Tenant scope is derived from
    the caller's Omium API key.
    """
    return await _omium_get(f"/api/v1/executions/{execution_id}/checkpoints")

@mcp.tool()
async def list_live_executions() -> dict:
    """List live executions for the caller's tenant.

    Calls GET /api/v1/executions/live through Kong. Tenant scope is derived from
    the caller's Omium API key.
    """
    return await _omium_get("/api/v1/executions/live")


@mcp.tool()
async def create_execution(
    workflow_id: str,
    agent_id: str | None = None,
    input_data: dict | None = None,
    metadata: dict | None = None,
) -> dict:
    """Create and enqueue a new execution.

    Calls POST /api/v1/executions through Kong. Tenant scope is derived from
    the caller's Omium API key — no tenant_id argument is needed or honored.

    workflow_id is required. agent_id is a free-form identity/audit label
    attached to the execution (it surfaces in traces, audit logs, and API
    responses). If omitted, the MCP substitutes "mcp-default-<tenant-slug>"
    derived from your API key so attribution stays tenant-specific.
    input_data and metadata are free-form JSON objects the agent attaches
    to the run.

    Returns the full execution record, including id, status (initially
    "pending"), resolved agent_id, and the upstream-computed cost estimate
    in metadata.
    """
    if not agent_id:
        slug = await _resolve_tenant_slug()
        agent_id = f"mcp-default-{slug}"
    body: dict = {"workflow_id": workflow_id, "agent_id": agent_id}
    if input_data is not None:
        body["input_data"] = input_data
    if metadata is not None:
        body["metadata"] = metadata
    return await _omium_post("/api/v1/executions", body)


app = mcp.streamable_http_app()
app.add_middleware(BearerAuthMiddleware)


if __name__ == "__main__":
    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT)
