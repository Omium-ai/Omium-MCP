"""Replay — step-through view of a past execution."""

from ..http import omium_get, omium_post
from ..mcp_instance import mcp


@mcp.tool()
async def get_replay_state(execution_id: str) -> dict:
    """Get the replay-ready state for an execution.

    Calls GET /api/v1/replay/<execution_id>/state.
    """
    return await omium_get(f"/api/v1/replay/{execution_id}/state")


@mcp.tool()
async def get_replay_step(execution_id: str, step_index: int) -> dict:
    """Get a single step from the replay timeline.

    Calls GET /api/v1/replay/<execution_id>/steps/<step_index>.
    """
    return await omium_get(f"/api/v1/replay/{execution_id}/steps/{step_index}")


@mcp.tool()
async def get_replay_consensus(execution_id: str) -> dict:
    """Get consensus-coordinator output for a replay.

    Calls GET /api/v1/replay/<execution_id>/consensus.
    """
    return await omium_get(f"/api/v1/replay/{execution_id}/consensus")


@mcp.tool()
async def get_replay_diff(execution_id: str, step_index_1: int, step_index_2: int) -> dict:
    """Diff between two steps of a replayed execution.

    Calls GET /api/v1/replay/<execution_id>/diff?step_index_1=&step_index_2=.
    """
    return await omium_get(
        f"/api/v1/replay/{execution_id}/diff",
        params={"step_index_1": step_index_1, "step_index_2": step_index_2},
    )


@mcp.tool()
async def restart_replay(execution_id: str, body: dict | None = None) -> dict:
    """Restart a replay from a checkpoint.

    Calls POST /api/v1/replay/<execution_id>/restart.
    """
    return await omium_post(f"/api/v1/replay/{execution_id}/restart", body)
