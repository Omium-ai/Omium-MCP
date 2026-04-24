# Omium MCP Server

Official [Model Context Protocol](https://modelcontextprotocol.io) server for
the Omium platform. Packaged as `omium-mcp` on PyPI and also runnable as a
Docker container. Routes all tool calls through Kong using the caller's Omium
API key for auth and tenant scoping.

Two transports from one package:

- **stdio** (default) — for end-users installing locally via `pip`/`uvx`.
  Zero-config; the API key is read from `$OMIUM_API_KEY`.
- **Streamable HTTP** (`omium-mcp serve`) — for self-hosted / team deployments.
  Per-request `Authorization: Bearer ...` header.

> Naming note: the `mcp-control-plane` component inside `Omium-platform/` is a
> **Managed Control Plane** (a Go service), unrelated to the Model Context
> Protocol. This project is the MCP-protocol flavor and lives outside the
> platform repo.

## Install

### End-user (stdio)

```bash
pip install omium-mcp     # or: uvx omium-mcp
```

Add to `~/.config/Claude/claude_desktop_config.json` (Linux) or the Windows/macOS
equivalent:

```json
{
  "mcpServers": {
    "omium": {
      "command": "omium-mcp",
      "env": { "OMIUM_API_KEY": "omium_YOUR_KEY_HERE" }
    }
  }
}
```

Claude Code:

```bash
claude mcp add omium omium-mcp --env OMIUM_API_KEY=omium_YOUR_KEY_HERE
```

### Self-hosted (Streamable HTTP / Docker)

```bash
cd /home/bhavjain/coding_gang/omium/omium-MCP
docker compose up -d --build
```

Server listens on `http://localhost:9100/mcp`. Wire into Claude Code:

```bash
claude mcp add --transport http omium http://localhost:9100/mcp \
  --header "Authorization: Bearer omium_YOUR_KEY_HERE"
```

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

Both transports populate the same `_api_key` ContextVar; tools read it and
forward the value as `X-API-Key` to Kong.

| Transport | How the key is bound |
|---|---|
| stdio  | `$OMIUM_API_KEY` read once at process start (`init_from_env`) |
| HTTP   | `Authorization: Bearer ...` extracted per request by `BearerAuthMiddleware` |

Missing / non-bearer auth on HTTP returns `401`. Missing `$OMIUM_API_KEY` for
stdio raises a clear startup error.

## Architecture

```
  Claude Code / Desktop
        │
        │  stdio (subprocess)  OR  HTTP (Bearer header)
        ▼
  omium-mcp  (package: omium_mcp)
        │  HTTP  (X-API-Key: omium_...)
        ▼
    Kong  (api.omium.ai  or  http://kong:8000 in Docker)
        │
        ▼
  workflow-manager / execution-engine / auth-service / ...
```

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

| Env var           | Default                 | Purpose                                           |
| ----------------- | ----------------------- | ------------------------------------------------- |
| `OMIUM_API_KEY`   | —                       | **Required** for stdio transport. Ignored by HTTP (per-request bearer). |
| `OMIUM_API_BASE`  | `https://api.omium.ai`  | Upstream Kong base URL. Overridden to `http://kong:8000` in Docker.     |
| `MCP_HOST`        | `0.0.0.0`               | Bind address for HTTP transport.                  |
| `MCP_PORT`        | `9100`                  | Bind port for HTTP transport.                     |

## Package layout

```
omium_mcp/
├── __init__.py
├── config.py          # env vars
├── auth.py            # ContextVar, BearerAuthMiddleware, init_from_env()
├── http.py            # omium_get / omium_post / omium_patch / omium_delete + _parse()
├── tenant.py          # tenant-slug cache (for agent_id defaulting)
├── mcp_instance.py    # FastMCP("omium-mcp") singleton
├── cli.py             # entry point — stdio (default) or `serve` for HTTP
└── tools/             # 15 modules, one per API category
    ├── identity.py
    ├── workflows.py
    ├── executions.py
    ├── checkpoints.py
    ├── failures.py
    ├── observability.py
    ├── scores.py
    ├── traces.py
    ├── projects.py
    ├── github.py
    ├── recovery.py
    ├── replay.py
    ├── analytics.py
    ├── audit.py
    └── billing.py
```

## Adding a new tool

1. Pick the right `omium_mcp/tools/<category>.py` (or add a new one and import
   it from `tools/__init__.py`).
2. Write an `async def` decorated with `@mcp.tool()`. The docstring becomes
   the tool description the LLM reads — keep it accurate.
3. Call the appropriate helper:
   - `omium_get(path, params=...)` for GET
   - `omium_post(path, json_body=..., params=...)` for POST
   - `omium_patch(path, json_body=..., params=...)` for PATCH
   - `omium_delete(path)` for DELETE (handles `204 No Content`)
4. Rebuild:
   - Docker (HTTP): `docker compose up -d --build`
   - Local stdio test: `.venv/bin/python -m omium_mcp.cli` (reads `$OMIUM_API_KEY`)
5. Test via the harness: `.venv/bin/python scripts/test_all_tools.py`.

## Publishing to PyPI

```bash
.venv/bin/python -m build          # writes dist/omium_mcp-X.Y.Z-py3-none-any.whl + tar.gz
.venv/bin/twine upload dist/*      # needs PyPI credentials
```

Users can then install with `pip install omium-mcp` or run without installing
via `uvx omium-mcp`.

## Docs

- [`docs/transport.md`](docs/transport.md) — why this MCP uses HTTP instead
  of stdio, and what that implies for configuration.
