"""Audit logger."""

from ..http import omium_get, omium_post
from ..mcp_instance import mcp


@mcp.tool()
async def create_audit_log(body: dict) -> dict:
    """Record an audit log entry.

    Calls POST /api/v1/audit/log. Typical fields: `action`, `resource_type`,
    `resource_id`, `metadata`.
    """
    return await omium_post("/api/v1/audit/log", body)


@mcp.tool()
async def list_audit_logs(
    limit: int | None = None,
    offset: int | None = None,
    resource_type: str | None = None,
    action: str | None = None,
) -> dict:
    """List audit log entries.

    Calls GET /api/v1/audit/logs.
    """
    params = {k: v for k, v in {
        "limit": limit, "offset": offset,
        "resource_type": resource_type, "action": action,
    }.items() if v is not None}
    return await omium_get("/api/v1/audit/logs", params=params or None)


@mcp.tool()
async def search_audit_logs(
    query: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> dict:
    """Search audit logs.

    Calls GET /api/v1/audit/logs/search.
    """
    params = {k: v for k, v in {
        "query": query, "limit": limit, "offset": offset,
    }.items() if v is not None}
    return await omium_get("/api/v1/audit/logs/search", params=params or None)


@mcp.tool()
async def get_audit_log(log_id: str) -> dict:
    """Get a single audit log entry.

    Calls GET /api/v1/audit/logs/<log_id>.
    """
    return await omium_get(f"/api/v1/audit/logs/{log_id}")
