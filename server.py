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


async def _omium_post(
    path: str,
    json_body: dict | None = None,
    params: dict | None = None,
) -> dict:
    key = _api_key.get()
    if not key:
        raise RuntimeError("no Omium API key bound to this request")
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{OMIUM_API_BASE}{path}",
            headers={"X-API-Key": key, "Content-Type": "application/json"},
            json=json_body or {},
            params=params,
        )
        r.raise_for_status()
        return r.json()


async def _omium_patch(
    path: str,
    json_body: dict | None = None,
    params: dict | None = None,
) -> dict:
    key = _api_key.get()
    if not key:
        raise RuntimeError("no Omium API key bound to this request")
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.patch(
            f"{OMIUM_API_BASE}{path}",
            headers={"X-API-Key": key, "Content-Type": "application/json"},
            json=json_body,
            params=params,
        )
        r.raise_for_status()
        return r.json()


async def _omium_delete(path: str) -> dict:
    key = _api_key.get()
    if not key:
        raise RuntimeError("no Omium API key bound to this request")
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.delete(
            f"{OMIUM_API_BASE}{path}",
            headers={"X-API-Key": key},
        )
        r.raise_for_status()
        if r.status_code == 204 or not r.content:
            return {"deleted": True}
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


@mcp.tool()
async def execute_execution(
    execution_id: str,
    workflow_type: str | None = None,
    workflow_definition: dict | None = None,
    inputs: dict | None = None,
) -> dict:
    """Run a previously-created (pending) execution.

    Calls POST /api/v1/executions/<execution_id>/execute through Kong. Tenant
    scope is derived from the caller's Omium API key.

    Only execution_id is required. If workflow_type or workflow_definition
    are not supplied, the MCP looks up the execution, reads its workflow_id,
    fetches the workflow, and fills them in from the stored record. Pass
    overrides only when you want to run a different definition than the one
    attached to the workflow.

    inputs, when omitted, defaults to the execution's stored input_data so
    the run uses the payload the execution was created with.

    Returns the updated execution record (typically with status flipped out
    of "pending").
    """
    if workflow_type is None or workflow_definition is None or inputs is None:
        execution = await _omium_get(f"/api/v1/executions/{execution_id}")
        if workflow_type is None or workflow_definition is None:
            workflow_id = execution.get("workflow_id")
            if not workflow_id:
                raise RuntimeError(
                    f"execution {execution_id} has no workflow_id; pass workflow_type and workflow_definition explicitly"
                )
            workflow = await _omium_get(f"/api/v1/workflows/{workflow_id}")
            if workflow_type is None:
                workflow_type = workflow.get("workflow_type") or "langgraph"
            if workflow_definition is None:
                workflow_definition = workflow.get("definition") or {}
        if inputs is None:
            inputs = execution.get("input_data") or {}

    return await _omium_post(
        f"/api/v1/executions/{execution_id}/execute",
        json_body={"workflow_definition": workflow_definition, "inputs": inputs},
        params={"workflow_type": workflow_type},
    )


@mcp.tool()
async def update_execution_status(
    execution_id: str,
    status: str,
    output_data: dict | None = None,
    error_message: str | None = None,
) -> dict:
    """Update the status of an execution.

    Calls PATCH /api/v1/executions/<execution_id>/status through Kong. Tenant
    scope is derived from the caller's Omium API key.

    status is a free-form string; the engine writes it through without
    validation. Conventional values are "pending", "running", "completed",
    "failed", "cancelled". output_data and error_message are optional and
    attach context to completed/failed runs.

    Note: this is a direct status write, not a workflow action. It does not
    start, stop, or replay execution — it only mutates the stored status
    field. Most callers should prefer execute_execution, replay_execution,
    or rollback_execution instead. Use this tool mainly for manual cleanup
    (e.g. marking an orphaned "pending" row as "cancelled").

    Returns the updated execution record.
    """
    params: dict = {"status": status}
    if error_message is not None:
        params["error_message"] = error_message
    return await _omium_patch(
        f"/api/v1/executions/{execution_id}/status",
        json_body=output_data,
        params=params,
    )


@mcp.tool()
async def delete_execution(execution_id: str) -> dict:
    """Delete an execution permanently.

    Calls DELETE /api/v1/executions/<execution_id> through Kong. Tenant
    scope is derived from the caller's Omium API key.

    This is a hard delete — the execution row (and associated data, per
    platform cascade rules) is removed. There is no soft-delete or undo.
    Use update_execution_status with status="cancelled" if you want to
    retain the record for audit purposes.

    Returns {"deleted": true, "execution_id": <id>} on success.
    """
    result = await _omium_delete(f"/api/v1/executions/{execution_id}")
    result.setdefault("execution_id", execution_id)
    return result


app = mcp.streamable_http_app()
app.add_middleware(BearerAuthMiddleware)


if __name__ == "__main__":
    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT)
