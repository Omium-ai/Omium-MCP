"""Workflow CRUD (read-only via SDK)."""

from ..http import omium_get
from ..mcp_instance import mcp


@mcp.tool()
async def list_workflows() -> dict:
    """List workflows for the caller's tenant.

    Calls GET /api/v1/workflows. Tenant scope is derived from the caller's
    API key — no tenant_id argument is needed or honored.
    """
    return await omium_get("/api/v1/workflows")


@mcp.tool()
async def get_workflows(workflow_id: str) -> dict:
    """Get a specific workflow.

    Calls GET /api/v1/workflows/<workflow_id>.
    """
    return await omium_get(f"/api/v1/workflows/{workflow_id}")


@mcp.tool()
async def list_workflow_versions(workflow_id: str) -> dict:
    """List all versions of a workflow.

    Calls GET /api/v1/workflows/<workflow_id>/versions.
    """
    return await omium_get(f"/api/v1/workflows/{workflow_id}/versions")
