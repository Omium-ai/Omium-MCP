"""Execution-engine observability surface."""

from ..http import omium_get, omium_post
from ..mcp_instance import mcp


@mcp.tool()
async def get_observability_metrics() -> dict:
    """Structured metrics snapshot.

    Calls GET /observability/metrics.
    """
    return await omium_get("/observability/metrics")


@mcp.tool()
async def get_observability_metrics_summary() -> dict:
    """Human-readable metrics summary.

    Calls GET /observability/metrics/summary.
    """
    return await omium_get("/observability/metrics/summary")


@mcp.tool()
async def get_observability_metrics_prometheus() -> dict:
    """Prometheus-format metrics (wrapped as `{"text": ...}`).

    Calls GET /observability/metrics/prometheus.
    """
    return await omium_get("/observability/metrics/prometheus")


@mcp.tool()
async def list_observability_traces() -> dict:
    """List observability traces.

    Calls GET /observability/traces.
    """
    return await omium_get("/observability/traces")


@mcp.tool()
async def get_observability_trace(execution_id: str) -> dict:
    """Full trace for one execution.

    Calls GET /observability/traces/<execution_id>.
    """
    return await omium_get(f"/observability/traces/{execution_id}")


@mcp.tool()
async def get_observability_trace_summary(execution_id: str) -> dict:
    """Summarized trace for one execution.

    Calls GET /observability/traces/<execution_id>/summary.
    """
    return await omium_get(f"/observability/traces/{execution_id}/summary")


@mcp.tool()
async def list_alerts() -> dict:
    """Currently-active alerts.

    Calls GET /observability/alerts.
    """
    return await omium_get("/observability/alerts")


@mcp.tool()
async def list_alerts_history() -> dict:
    """Alert history.

    Calls GET /observability/alerts/history.
    """
    return await omium_get("/observability/alerts/history")


@mcp.tool()
async def acknowledge_alert(condition_name: str, body: dict | None = None) -> dict:
    """Acknowledge an alert.

    Calls POST /observability/alerts/<condition_name>/acknowledge.
    """
    return await omium_post(f"/observability/alerts/{condition_name}/acknowledge", body)


@mcp.tool()
async def get_observability_dashboard() -> dict:
    """Aggregate observability dashboard payload.

    Calls GET /observability/dashboard.
    """
    return await omium_get("/observability/dashboard")


@mcp.tool()
async def get_observability_health() -> dict:
    """Health of the observability subsystem.

    Calls GET /observability/health.
    """
    return await omium_get("/observability/health")
