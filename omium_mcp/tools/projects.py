"""Projects — CRUD + git connection + files."""

from ..http import omium_get, omium_post
from ..mcp_instance import mcp


@mcp.tool()
async def create_project(body: dict) -> dict:
    """Create a project.

    Calls POST /api/v1/projects. Typical fields: `name`, `slug`,
    `description`, `git_url`.
    """
    return await omium_post("/api/v1/projects", body)


@mcp.tool()
async def list_projects() -> dict:
    """List projects for the tenant.

    Calls GET /api/v1/projects.
    """
    return await omium_get("/api/v1/projects")


@mcp.tool()
async def connect_project_git(project_id: str, body: dict) -> dict:
    """Attach a git repository to a project.

    Calls POST /api/v1/projects/<project_id>/git/connect. Typical fields:
    `provider`, `repo_url`, `access_token`, `branch`.
    """
    return await omium_post(f"/api/v1/projects/{project_id}/git/connect", body)


@mcp.tool()
async def list_project_files(project_id: str) -> dict:
    """List files tracked under a project.

    Calls GET /api/v1/projects/<project_id>/files.
    """
    return await omium_get(f"/api/v1/projects/{project_id}/files")


@mcp.tool()
async def save_project_file(project_id: str, file_path: str, body: dict) -> dict:
    """Create or update a file inside a project.

    Calls POST /api/v1/projects/<project_id>/files/<file_path>. Body typically
    carries `content`, `file_path`, and optional `encoding`/`mode`.
    """
    return await omium_post(f"/api/v1/projects/{project_id}/files/{file_path}", body)


@mcp.tool()
async def commit_project_git(project_id: str, body: dict) -> dict:
    """Commit tracked project file changes to the attached git repo.

    Calls POST /api/v1/projects/<project_id>/git/commit. Typical fields:
    `message`, `branch`, optional `files`.
    """
    return await omium_post(f"/api/v1/projects/{project_id}/git/commit", body)
