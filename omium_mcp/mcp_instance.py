"""Singleton FastMCP instance — every tool module imports `mcp` from here."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("omium-mcp")
