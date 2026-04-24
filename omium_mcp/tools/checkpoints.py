"""Tenant-wide checkpoints (separate from per-execution checkpoint listing)."""

from ..http import omium_get, omium_post
from ..mcp_instance import mcp


@mcp.tool()
async def create_checkpoint(body: dict) -> dict:
    """Create a checkpoint record.

    Calls POST /api/v1/checkpoints. Typical fields: `execution_id`,
    `step_index`, `checkpoint_name`, `state`, `metadata`.
    """
    return await omium_post("/api/v1/checkpoints", body)


@mcp.tool()
async def list_all_checkpoints(
    execution_id: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> dict:
    """List checkpoints across the tenant (optionally filtered).

    Calls GET /api/v1/checkpoints. Tenant-wide — differs from
    `list_checkpoints` (which is scoped to one execution).
    """
    params: dict = {}
    if execution_id:
        params["execution_id"] = execution_id
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    return await omium_get("/api/v1/checkpoints", params=params or None)


@mcp.tool()
async def get_checkpoint(checkpoint_id: str) -> dict:
    """Get a specific checkpoint.

    Calls GET /api/v1/checkpoints/<checkpoint_id>.
    """
    return await omium_get(f"/api/v1/checkpoints/{checkpoint_id}")
