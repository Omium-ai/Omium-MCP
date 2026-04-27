"""Traces — SDK-facing ingest + query."""

from ..http import omium_get, omium_post
from ..mcp_instance import mcp


@mcp.tool()
async def ingest_trace(body: dict) -> dict:
    """Ingest a trace payload (SDK-style).

    Calls POST /api/v1/traces/ingest. Required body: `trace_id`, `project`,
    `spans`.
    """
    return await omium_post("/api/v1/traces/ingest", body)


@mcp.tool()
async def list_traces(
    limit: int | None = None,
    offset: int | None = None,
    project_id: str | None = None,
    workflow_id: str | None = None,
) -> dict:
    """List traces for the tenant, optionally filtered.

    Calls GET /api/v1/traces.
    """
    params = {k: v for k, v in {
        "limit": limit, "offset": offset,
        "project_id": project_id, "workflow_id": workflow_id,
    }.items() if v is not None}
    return await omium_get("/api/v1/traces", params=params or None)


@mcp.tool()
async def get_trace(trace_id: str) -> dict:
    """Get a single trace by ID.

    Calls GET /api/v1/traces/<trace_id>.
    """
    return await omium_get(f"/api/v1/traces/{trace_id}")


@mcp.tool()
async def list_trace_failures() -> dict:
    """List failed traces.

    Calls GET /api/v1/traces/failures.
    """
    return await omium_get("/api/v1/traces/failures")


@mcp.tool()
async def list_trace_projects() -> dict:
    """List trace projects.

    Calls GET /api/v1/traces/projects.
    """
    return await omium_get("/api/v1/traces/projects")
