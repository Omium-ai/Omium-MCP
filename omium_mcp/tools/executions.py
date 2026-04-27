"""Execution lifecycle — create, run, inspect, mutate."""

from ..http import omium_delete, omium_get, omium_patch, omium_post
from ..mcp_instance import mcp
from ..tenant import resolve_tenant_slug


@mcp.tool()
async def list_executions() -> dict:
    """List recent executions for the caller's tenant.

    Calls GET /api/v1/executions.
    """
    return await omium_get("/api/v1/executions")


@mcp.tool()
async def get_execution(execution_id: str) -> dict:
    """Get a specific execution.

    Calls GET /api/v1/executions/<execution_id>.
    """
    return await omium_get(f"/api/v1/executions/{execution_id}")


@mcp.tool()
async def list_checkpoints(execution_id: str) -> dict:
    """List checkpoints for a specific execution.

    Calls GET /api/v1/executions/<execution_id>/checkpoints.
    """
    return await omium_get(f"/api/v1/executions/{execution_id}/checkpoints")


@mcp.tool()
async def list_live_executions() -> dict:
    """List live executions for the caller's tenant.

    Calls GET /api/v1/executions/live.
    """
    return await omium_get("/api/v1/executions/live")


@mcp.tool()
async def create_execution(
    workflow_id: str,
    agent_id: str | None = None,
    input_data: dict | None = None,
    metadata: dict | None = None,
) -> dict:
    """Create and enqueue a new execution.

    Calls POST /api/v1/executions. workflow_id is required. agent_id is a
    free-form identity/audit label — if omitted, the MCP substitutes
    "mcp-default-<tenant-slug>" derived from the API key. input_data and
    metadata are free-form JSON attached to the run.
    """
    if not agent_id:
        slug = await resolve_tenant_slug()
        agent_id = f"mcp-default-{slug}"
    body: dict = {"workflow_id": workflow_id, "agent_id": agent_id}
    if input_data is not None:
        body["input_data"] = input_data
    if metadata is not None:
        body["metadata"] = metadata
    return await omium_post("/api/v1/executions", body)


@mcp.tool()
async def execute_execution(
    execution_id: str,
    workflow_type: str | None = None,
    workflow_definition: dict | None = None,
    inputs: dict | None = None,
) -> dict:
    """Run a previously-created (pending) execution.

    Calls POST /api/v1/executions/<execution_id>/execute. If workflow_type
    or workflow_definition are omitted, auto-resolves them from the
    execution's stored workflow_id. inputs defaults to the execution's
    stored input_data.
    """
    if workflow_type is None or workflow_definition is None or inputs is None:
        execution = await omium_get(f"/api/v1/executions/{execution_id}")
        if workflow_type is None or workflow_definition is None:
            workflow_id = execution.get("workflow_id")
            if not workflow_id:
                raise RuntimeError(
                    f"execution {execution_id} has no workflow_id; pass workflow_type and workflow_definition explicitly"
                )
            workflow = await omium_get(f"/api/v1/workflows/{workflow_id}")
            if workflow_type is None:
                workflow_type = workflow.get("workflow_type") or "langgraph"
            if workflow_definition is None:
                workflow_definition = workflow.get("definition") or {}
        if inputs is None:
            inputs = execution.get("input_data") or {}

    return await omium_post(
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
    """Update the status of an execution (direct write, not a workflow action).

    Calls PATCH /api/v1/executions/<execution_id>/status. Conventional values:
    "pending", "running", "completed", "failed", "cancelled". Prefer
    execute_execution / replay_execution / rollback_execution for workflow
    state changes.
    """
    params: dict = {"status": status}
    if error_message is not None:
        params["error_message"] = error_message
    return await omium_patch(
        f"/api/v1/executions/{execution_id}/status",
        json_body=output_data,
        params=params,
    )


@mcp.tool()
async def delete_execution(execution_id: str) -> dict:
    """Delete an execution permanently (hard delete, no undo).

    Calls DELETE /api/v1/executions/<execution_id>.
    """
    result = await omium_delete(f"/api/v1/executions/{execution_id}")
    result.setdefault("execution_id", execution_id)
    return result


@mcp.tool()
async def replay_execution(execution_id: str, body: dict | None = None) -> dict:
    """Replay an execution from a checkpoint.

    Calls POST /api/v1/executions/<execution_id>/replay. Typical body fields:
    `checkpoint_id`, `from_step`, `inputs`, `override_definition`.
    """
    return await omium_post(f"/api/v1/executions/{execution_id}/replay", body)


@mcp.tool()
async def compare_executions(body: dict) -> dict:
    """Compare two executions side by side.

    Calls POST /api/v1/executions/compare. Required body: `execution_id_1`,
    `execution_id_2` (singular pair — NOT a list under `execution_ids`).
    """
    return await omium_post("/api/v1/executions/compare", body)


@mcp.tool()
async def rollback_execution(execution_id: str, body: dict | None = None) -> dict:
    """Roll back an execution to a prior checkpoint.

    Calls POST /api/v1/executions/<execution_id>/rollback.
    """
    return await omium_post(f"/api/v1/executions/{execution_id}/rollback", body)


@mcp.tool()
async def apply_fix_to_execution(execution_id: str, body: dict | None = None) -> dict:
    """Apply a RIS-generated (or user-supplied) fix to an execution.

    Calls POST /api/v1/executions/<execution_id>/apply-fix.
    """
    return await omium_post(f"/api/v1/executions/{execution_id}/apply-fix", body)


@mcp.tool()
async def get_apply_to_repo_payload(execution_id: str) -> dict:
    """Get the git-ready patch payload for an execution's fix.

    Calls GET /api/v1/executions/<execution_id>/apply-to-repo-payload.
    """
    return await omium_get(f"/api/v1/executions/{execution_id}/apply-to-repo-payload")
