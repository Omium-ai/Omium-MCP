# Omium MCP Server

A persistent [Model Context Protocol](https://modelcontextprotocol.io) server
for the Omium platform. Runs as a long-lived Docker container, speaks MCP over
Streamable HTTP on port 9100, and routes all tool calls through Kong using the
caller's Omium API key for auth + tenant scoping.

> Naming note: the `mcp-control-plane` component inside `Omium-platform/` is a
> **Managed Control Plane** (a Go service), unrelated to the Model Context
> Protocol. This project is the MCP-protocol flavor and lives outside the
> platform repo.

---

## Tools

| Tool              | Upstream call                | Auth     |
| ----------------- | ---------------------------- | -------- |
| `list_workflows`  | `GET /api/v1/workflows`      | required |
| `list_executions` | `GET /api/v1/executions`     | required |

Tenant scope is derived from the API key server-side — no `tenant_id` argument
is accepted.

## Auth model

MCP clients connect with an `Authorization: Bearer omium_...` header on the
HTTP connection. A small ASGI middleware pulls that token into a per-request
`ContextVar`; each tool reads it and forwards the key as `X-API-Key` to Kong.
Missing / non-bearer auth gets a `401`.

## Architecture

```
Claude Code / Desktop
      │  HTTP  (Authorization: Bearer omium_...)
      ▼
  omium-mcp  (this repo, container on port 9100)
      │  HTTP  (X-API-Key: omium_...)
      ▼
     Kong  (http://kong:8000, shared Docker network)
      │
      ▼
  workflow-manager / execution-engine / auth-service / ...
```

The MCP container joins the platform's Docker network
(`omium-platform_omium-network`) as an external network, so it can address
services by name. The container still publishes port 9100 to the host so
Claude Code (running on the host) can reach it at `http://localhost:9100/mcp`.

## Prerequisites

- Docker + Docker Compose
- The Omium platform stack running in the usual way (Kong healthy on
  `http://localhost:8080`):
  ```bash
  cd ../Omium-platform
  docker compose -f infrastructure/docker/docker-compose.local.yml up -d
  ```

## Run

```bash
cd /home/bhavjain/coding_gang/omium/omium-MCP
docker compose up -d --build
docker compose logs -f omium-mcp   # optional
```

Server listens on `http://localhost:9100/mcp`.

Stop with:

```bash
docker compose down
```

## Smoke-test

Reject missing auth:

```bash
curl -i http://localhost:9100/mcp
# HTTP/1.1 401 Unauthorized
```

Full MCP round-trip (uses the Python MCP client from `.venv`):

```bash
python - <<'PY'
import asyncio, json
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

KEY = "omium_..."  # any seeded key from .mcp-test-keys.txt

async def main():
    headers = {"Authorization": f"Bearer {KEY}"}
    async with streamablehttp_client("http://localhost:9100/mcp", headers=headers) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            print([t.name for t in (await s.list_tools()).tools])
            res = await s.call_tool("list_workflows", {})
            print(res.content[0].text[:200])

asyncio.run(main())
PY
```

## Wire into Claude Code

```bash
claude mcp add --transport http omium http://localhost:9100/mcp \
  --header "Authorization: Bearer omium_YOUR_KEY_HERE"
```

Then `/mcp` in Claude Code lists the server and the two tools are callable.

## Wire into Claude Desktop

Edit `~/.config/Claude/claude_desktop_config.json` (Linux):

```json
{
  "mcpServers": {
    "omium": {
      "type": "http",
      "url": "http://localhost:9100/mcp",
      "headers": {
        "Authorization": "Bearer omium_YOUR_KEY_HERE"
      }
    }
  }
}
```

Restart Claude Desktop.

## Configuration

| Env var           | Default              | Purpose                                           |
| ----------------- | -------------------- | ------------------------------------------------- |
| `OMIUM_API_BASE`  | `http://kong:8000`   | Where the MCP sends outbound requests.            |
| `MCP_HOST`        | `0.0.0.0`            | Bind address inside the container.                |
| `MCP_PORT`        | `9100`               | Bind port (also published by compose).            |

## Adding a new tool

1. Add an `async def` in `server.py` decorated with `@mcp.tool()`. The
   docstring becomes the tool description the model reads — keep it accurate.
2. Call `_omium_get("/api/v1/...", params=...)`; it handles auth forwarding.
3. Rebuild: `docker compose up -d --build`.
