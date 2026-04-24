"""GitHub integration."""

from ..http import omium_delete, omium_get, omium_patch, omium_post
from ..mcp_instance import mcp


@mcp.tool()
async def github_status() -> dict:
    """GitHub integration status for the tenant.

    Calls GET /api/v1/github/status.
    """
    return await omium_get("/api/v1/github/status")


@mcp.tool()
async def github_setup(body: dict) -> dict:
    """Configure the GitHub integration.

    Calls POST /api/v1/github/setup. Typical fields: `installation_id`,
    `repo`, `pat`, `default_branch`.
    """
    return await omium_post("/api/v1/github/setup", body)


@mcp.tool()
async def github_update_repo(body: dict) -> dict:
    """Update the repo attached to the GitHub integration.

    Calls PATCH /api/v1/github/repo.
    """
    return await omium_patch("/api/v1/github/repo", body)


@mcp.tool()
async def github_disconnect() -> dict:
    """Disconnect the GitHub integration.

    Calls DELETE /api/v1/github/disconnect.
    """
    return await omium_delete("/api/v1/github/disconnect")


@mcp.tool()
async def github_create_fix_pr(body: dict) -> dict:
    """Open a PR on GitHub with an Omium-generated fix.

    Calls POST /api/v1/github/create-fix-pr. Typical fields: `execution_id`,
    `solution_id`, `title`, `body`, `branch`.
    """
    return await omium_post("/api/v1/github/create-fix-pr", body)
