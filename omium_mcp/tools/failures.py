"""Failures — events, stats, time series."""

from ..http import omium_get, omium_post
from ..mcp_instance import mcp


@mcp.tool()
async def list_failures(
    limit: int | None = None,
    offset: int | None = None,
    status: str | None = None,
    workflow_id: str | None = None,
) -> dict:
    """List failure events for the tenant.

    Calls GET /api/v1/failures.
    """
    params = {k: v for k, v in {
        "limit": limit, "offset": offset, "status": status, "workflow_id": workflow_id,
    }.items() if v is not None}
    return await omium_get("/api/v1/failures", params=params or None)


@mcp.tool()
async def get_failures_stats() -> dict:
    """Aggregate failure statistics.

    Calls GET /api/v1/failures/stats.
    """
    return await omium_get("/api/v1/failures/stats")


@mcp.tool()
async def get_failures_time_series(
    window: str | None = None,
    bucket: str | None = None,
) -> dict:
    """Failure counts bucketed over time.

    Calls GET /api/v1/failures/time-series. Typical params: `window=24h`,
    `bucket=1h`.
    """
    params = {k: v for k, v in {"window": window, "bucket": bucket}.items() if v is not None}
    return await omium_get("/api/v1/failures/time-series", params=params or None)


@mcp.tool()
async def create_failure_event(body: dict) -> dict:
    """Record a failure event (SDK push path).

    Calls POST /api/v1/failures/events. Typical fields: `execution_id`,
    `failure_type`, `error_message`.
    """
    return await omium_post("/api/v1/failures/events", body)
