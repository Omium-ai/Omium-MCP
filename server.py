"""Back-compat entry point for `python server.py` — runs HTTP mode.

Prefer the installed console script: `omium-mcp` (stdio) / `omium-mcp serve` (HTTP).
This file exists so existing Docker / local `python server.py` invocations
keep working.
"""

from omium_mcp.cli import run_http
from omium_mcp.config import MCP_HOST, MCP_PORT


if __name__ == "__main__":
    run_http(MCP_HOST, MCP_PORT)
