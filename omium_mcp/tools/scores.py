"""Evaluation scores."""

from ..http import omium_get, omium_post
from ..mcp_instance import mcp


@mcp.tool()
async def create_score(body: dict) -> dict:
    """Record an evaluation score.

    Calls POST /api/v1/scores. Required body: `trace_id`, `name`, `value`.
    Optional: `execution_id`, `score_type`, `source`, `metadata`.
    """
    return await omium_post("/api/v1/scores", body)


@mcp.tool()
async def list_scores(
    trace_id: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> dict:
    """List scores, optionally filtered.

    Calls GET /api/v1/scores.
    """
    params = {k: v for k, v in {
        "trace_id": trace_id, "limit": limit, "offset": offset,
    }.items() if v is not None}
    return await omium_get("/api/v1/scores", params=params or None)


@mcp.tool()
async def get_scores_stats() -> dict:
    """Aggregate score statistics.

    Calls GET /api/v1/scores/stats.
    """
    return await omium_get("/api/v1/scores/stats")
