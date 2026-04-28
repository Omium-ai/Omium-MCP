"""Entry point — dispatches stdio (default), HTTP, or interactive setup.

Installed as the `omium-mcp` console script via pyproject.toml.

Usage:
    omium-mcp                               # stdio (default, for pip users)
    omium-mcp init                          # interactive setup wizard
    omium-mcp serve                         # HTTP on $MCP_HOST:$MCP_PORT (default 0.0.0.0:9100)
    omium-mcp serve --host 127.0.0.1        # override bind
    omium-mcp serve --port 9200
"""

from __future__ import annotations

import argparse
import sys


def run_stdio() -> None:
    """Populate the API key from env and run the stdio transport."""
    from .auth import init_from_env
    from .mcp_instance import mcp
    from . import tools  # noqa: F401 — import-for-side-effect; registers all @mcp.tool()s

    init_from_env()
    mcp.run("stdio")


def run_http(host: str, port: int) -> None:
    """Run the Streamable-HTTP transport with bearer-token middleware."""
    import uvicorn

    from .auth import BearerAuthMiddleware
    from .mcp_instance import mcp
    from . import tools  # noqa: F401 — registers all @mcp.tool()s

    app = mcp.streamable_http_app()
    app.add_middleware(BearerAuthMiddleware)
    uvicorn.run(app, host=host, port=port)


def main(argv: list[str] | None = None) -> int:
    from .config import MCP_HOST, MCP_PORT

    parser = argparse.ArgumentParser(
        prog="omium-mcp",
        description="Omium MCP server — stdio by default, `serve` for HTTP, `init` for guided setup.",
        epilog="Run `omium-mcp init` for guided setup, or see https://pypi.org/project/omium-mcp/",
    )
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("init", help="Interactive setup wizard (key + Claude Code).")

    serve = sub.add_parser("serve", help="Run as a long-lived HTTP server.")
    serve.add_argument("--host", default=MCP_HOST, help=f"Bind address (default {MCP_HOST})")
    serve.add_argument("--port", type=int, default=MCP_PORT, help=f"Bind port (default {MCP_PORT})")

    args = parser.parse_args(argv)

    if args.cmd == "init":
        from .init import run_init
        return run_init()
    if args.cmd == "serve":
        run_http(args.host, args.port)
    else:
        run_stdio()
    return 0


if __name__ == "__main__":
    sys.exit(main())
