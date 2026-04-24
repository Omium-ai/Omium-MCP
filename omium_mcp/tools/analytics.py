"""Analytics engine — usage, performance, cost."""

from ..http import omium_get
from ..mcp_instance import mcp


@mcp.tool()
async def get_usage_summary() -> dict:
    """Tenant usage summary (executions, cost, tokens).

    Calls GET /api/v1/usage/summary.
    """
    return await omium_get("/api/v1/usage/summary")


@mcp.tool()
async def get_dashboard_metrics() -> dict:
    """Dashboard landing metrics.

    Calls GET /api/v1/dashboard/metrics.
    """
    return await omium_get("/api/v1/dashboard/metrics")


@mcp.tool()
async def get_recent_activity() -> dict:
    """Recent activity feed for the tenant.

    Calls GET /api/v1/activity/recent.
    """
    return await omium_get("/api/v1/activity/recent")


@mcp.tool()
async def get_performance_metrics() -> dict:
    """Aggregate performance metrics.

    Calls GET /api/v1/performance/metrics.
    """
    return await omium_get("/api/v1/performance/metrics")


@mcp.tool()
async def get_performance_time_series(
    window: str | None = None,
    bucket: str | None = None,
) -> dict:
    """Performance time-series.

    Calls GET /api/v1/performance/time-series.
    """
    params = {k: v for k, v in {"window": window, "bucket": bucket}.items() if v is not None}
    return await omium_get("/api/v1/performance/time-series", params=params or None)


@mcp.tool()
async def get_performance_agents() -> dict:
    """Per-agent performance breakdown.

    Calls GET /api/v1/performance/agents.
    """
    return await omium_get("/api/v1/performance/agents")


@mcp.tool()
async def get_workflow_performance(workflow_id: str) -> dict:
    """Performance metrics for a specific workflow.

    Calls GET /api/v1/performance/workflow/<workflow_id>.
    """
    return await omium_get(f"/api/v1/performance/workflow/{workflow_id}")


@mcp.tool()
async def get_workflow_cost(workflow_id: str) -> dict:
    """Cost breakdown for a specific workflow.

    Calls GET /api/v1/performance/workflow/<workflow_id>/cost.
    """
    return await omium_get(f"/api/v1/performance/workflow/{workflow_id}/cost")


@mcp.tool()
async def get_system_metrics() -> dict:
    """System-level metrics.

    Calls GET /api/v1/metrics/system.
    """
    return await omium_get("/api/v1/metrics/system")
