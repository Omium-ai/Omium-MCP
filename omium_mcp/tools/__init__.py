"""Import every tool module so FastMCP registers all @mcp.tool()s.

Order doesn't matter — each module's decorators attach to the same
`mcp_instance.mcp` singleton.
"""

from . import (  # noqa: F401
    analytics,
    audit,
    billing,
    checkpoints,
    executions,
    failures,
    github,
    identity,
    projects,
    recovery,
    replay,
    scores,
    traces,
    workflows,
)
