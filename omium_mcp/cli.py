"""Entry point — dispatches stdio (default) or HTTP mode.

Installed as the `omium-mcp` console script via pyproject.toml.

Usage:
    omium-mcp                               # stdio (default, for pip users)
    omium-mcp serve                         # HTTP on $MCP_HOST:$MCP_PORT (default 0.0.0.0:9100)
    omium-mcp serve --host 127.0.0.1        # override bind
    omium-mcp serve --port 9200
"""

from __future__ import annotations

import argparse
import sys

from .auth import BearerAuthMiddleware, init_from_env
from .config import MCP_HOST, MCP_PORT
from .mcp_instance import mcp
from . import tools  # noqa: F401 — import-for-side-effect; registers all @mcp.tool()s


def run_stdio() -> None:
    """Populate the API key from env and run the stdio transport."""
    init_from_env()
    mcp.run("stdio")


def run_http(host: str, port: int) -> None:
    """Run the Streamable-HTTP transport with bearer-token middleware."""
    import uvicorn

    app = mcp.streamable_http_app()
    app.add_middleware(BearerAuthMiddleware)
    uvicorn.run(app, host=host, port=port)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="omium-mcp",
        description="Omium MCP server — stdio by default, or `serve` for HTTP.",
    )
    sub = parser.add_subparsers(dest="cmd")

    serve = sub.add_parser("serve", help="Run as a long-lived HTTP server.")
    serve.add_argument("--host", default=MCP_HOST, help=f"Bind address (default {MCP_HOST})")
    serve.add_argument("--port", type=int, default=MCP_PORT, help=f"Bind port (default {MCP_PORT})")

    args = parser.parse_args(argv)

    if args.cmd == "serve":
        run_http(args.host, args.port)
    else:
        run_stdio()
    return 0


if __name__ == "__main__":
    sys.exit(main())
