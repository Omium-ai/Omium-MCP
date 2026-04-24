"""Runtime configuration, all overridable via environment variables."""

import os

# Public Kong gateway — the default for pip-installed users. Docker / local
# deployments override this to e.g. "http://kong:8000".
OMIUM_API_BASE = os.environ.get("OMIUM_API_BASE", "https://api.omium.ai")

# HTTP-transport bind settings. Ignored in stdio mode.
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", "9100"))
