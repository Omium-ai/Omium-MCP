"""Identity / whoami."""

from ..http import omium_get
from ..mcp_instance import mcp


@mcp.tool()
async def verify_api_key() -> dict:
    """Return identity info for the current API key (tenant name, role, scopes).

    Calls GET /api/v1/api-keys/verify. Useful as a `whoami` probe.
    """
    return await omium_get("/api/v1/api-keys/verify")
