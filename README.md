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

The MCP exposes every Kong-reachable Omium endpoint that accepts `X-API-Key`
(~96 tools). JWT-only endpoints (dashboard login/signup, invitations,
Slack OAuth, Stripe webhooks) are intentionally excluded — an MCP client
only holds an API key. All tools forward the caller's bearer token to Kong
as `X-API-Key`; tenant scope is derived server-side so no `tenant_id`
argument is ever accepted.

The complete client-facing endpoint list is maintained in
[`../Kong-Client-Facing-APIs.md`](../Kong-Client-Facing-APIs.md).

### Categories

| Category            | Example tools                                              | Upstream service          |
| ------------------- | ---------------------------------------------------------- | ------------------------- |
| Identity            | `verify_api_key`                                           | auth-service              |
| Workflows           | `list_workflows`, `get_workflows`, `list_workflow_versions`| auth-service              |
| Executions          | `list_executions`, `create_execution`, `execute_execution`, `replay_execution`, `rollback_execution`, `apply_fix_to_execution`, `compare_executions`, `delete_execution`, `update_execution_status`, `get_apply_to_repo_payload` | execution-engine |
| Checkpoints         | `list_checkpoints`, `list_all_checkpoints`, `get_checkpoint`, `create_checkpoint` | execution-engine |
| Failures            | `list_failures`, `get_failures_stats`, `get_failures_time_series`, `create_failure_event` | execution-engine |
| Observability       | `get_observability_metrics`, `list_observability_traces`, `list_alerts`, `acknowledge_alert`, … | execution-engine |
| Scores              | `create_score`, `list_scores`, `get_scores_stats`          | auth-service              |
| Traces              | `ingest_trace`, `list_traces`, `get_trace`, `list_trace_failures`, `list_trace_projects` | auth-service |
| Projects            | `create_project`, `list_projects`, `connect_project_git`, `list_project_files`, `save_project_file`, `commit_project_git` | auth-service |
| GitHub              | `github_status`, `github_setup`, `github_update_repo`, `github_disconnect`, `github_create_fix_pr` | auth-service |
| Recovery            | `list_recovery_failures`, `trigger_recovery`, `create_recovery_command`, `list_recovery_commands`, `get_recovery_command`, `update_recovery_command_status`, `redeliver_recovery_command` | recovery-orchestrator |
| Replay              | `get_replay_state`, `get_replay_step`, `get_replay_consensus`, `get_replay_diff`, `restart_replay` | recovery-orchestrator |
| Analytics           | `get_usage_summary`, `get_dashboard_metrics`, `get_recent_activity`, `get_performance_metrics`, `get_performance_time_series`, `get_performance_agents`, `get_workflow_performance`, `get_workflow_cost`, `get_system_metrics` | analytics-engine |
| Audit               | `create_audit_log`, `list_audit_logs`, `search_audit_logs`, `get_audit_log` | audit-logger |
| Billing             | `get_billing_balance`, `get_billing_usage`, `create_billing_topup`, `list_billing_transactions`, `get_subscription_status`, `estimate_execution_cost`, `get_cost_breakdown`, `get_quotas`, `get_billing_forecast`, `get_billing_recommendations`, `get_cost_analytics`, `list_billing_alerts`, … | billing-service |

### Notable conveniences

- `create_execution` auto-fills `agent_id` as `mcp-default-<tenant-slug>` when omitted.
- `execute_execution` auto-resolves `workflow_type` and `workflow_definition` from the execution's `workflow_id`.
- Tools that take complex bodies (`replay_execution`, `rollback_execution`, `apply_fix_to_execution`, `compare_executions`, project/recovery writes, billing checkouts, `ingest_trace`, audit creation, etc.) accept a pass-through `body: dict` — the docstring enumerates typical fields. This keeps the MCP layer useful while upstream schemas stabilize.
- Non-JSON upstream responses (e.g. `/observability/metrics/prometheus`) are wrapped as `{"ok": true, "text": "..."}`.
- On non-2xx upstream responses, tools raise `Omium API <METHOD> <path> -> <status>: <body>` so the upstream error is visible to the LLM.

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
2. Call the appropriate HTTP helper:
   - `_omium_get(path, params=...)` for GET
   - `_omium_post(path, json_body=..., params=...)` for POST
   - `_omium_patch(path, json_body=..., params=...)` for PATCH
   - `_omium_delete(path)` for DELETE (handles `204 No Content`)
3. Rebuild: `docker compose up -d --build`.

## Docs

- [`docs/transport.md`](docs/transport.md) — why this MCP uses HTTP instead
  of stdio, and what that implies for configuration.
