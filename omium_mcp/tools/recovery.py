"""Recovery orchestrator — failure triage + command queue."""

from ..http import omium_get, omium_post
from ..mcp_instance import mcp


@mcp.tool()
async def list_recovery_failures() -> dict:
    """List failures seen by the recovery orchestrator.

    Calls GET /api/v1/recovery/failures.
    """
    return await omium_get("/api/v1/recovery/failures")


@mcp.tool()
async def trigger_recovery(body: dict) -> dict:
    """Trigger recovery for a failing execution.

    Calls POST /api/v1/recovery/trigger. Typical fields: `execution_id`,
    `strategy`.
    """
    return await omium_post("/api/v1/recovery/trigger", body)


@mcp.tool()
async def create_recovery_command(body: dict) -> dict:
    """Enqueue a recovery command.

    Calls POST /api/v1/recovery/commands. Required body: `execution_id`,
    `command_type`. Optional: `target_id`, `instructions`, `callback_url`,
    `metadata`.
    """
    return await omium_post("/api/v1/recovery/commands", body)


@mcp.tool()
async def list_recovery_commands(
    status: str | None = None,
    execution_id: str | None = None,
    limit: int | None = None,
) -> dict:
    """List recovery commands, optionally filtered.

    Calls GET /api/v1/recovery/commands.
    """
    params = {k: v for k, v in {
        "status": status, "execution_id": execution_id, "limit": limit,
    }.items() if v is not None}
    return await omium_get("/api/v1/recovery/commands", params=params or None)


@mcp.tool()
async def get_recovery_command(command_id: str) -> dict:
    """Get a recovery command by ID.

    Calls GET /api/v1/recovery/commands/<command_id>.
    """
    return await omium_get(f"/api/v1/recovery/commands/{command_id}")


@mcp.tool()
async def update_recovery_command_status(command_id: str, body: dict) -> dict:
    """Update a recovery command's status.

    Calls POST /api/v1/recovery/commands/<command_id>/status. Required body:
    `status` — one of `pending`, `acknowledged`, `in_progress`, `completed`,
    `failed`, `cancelled`.
    """
    return await omium_post(f"/api/v1/recovery/commands/{command_id}/status", body)


@mcp.tool()
async def redeliver_recovery_command(command_id: str) -> dict:
    """Redeliver a recovery command to its target.

    Calls POST /api/v1/recovery/commands/<command_id>/redeliver.
    """
    return await omium_post(f"/api/v1/recovery/commands/{command_id}/redeliver")
