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

## Quickstart

Get from `pip install` to a working integration in under 5 minutes.

### Prerequisites

- Python **3.10 or newer** (`python3 --version` on macOS/Linux, `python --version` on Windows)
- An Omium API key — copy it from your Omium dashboard

### 1. Install

You have two options — both leave you with the `omium-mcp` CLI on your PATH. Pick one.

#### Option A — MCP only (`pip install omium-mcp`)

Install just the MCP server. Pick this if you only want to plug Omium into Claude Code / Cursor / Claude Desktop and aren't writing Python code against the Omium SDK.

**macOS / Linux:**

```bash
python3 -m venv ~/omium
~/omium/bin/pip install --upgrade pip
~/omium/bin/pip install omium-mcp
export PATH="$HOME/omium/bin:$PATH"
```

**Windows (PowerShell):**

```powershell
python -m venv $HOME\omium
& "$HOME\omium\Scripts\pip" install --upgrade pip
& "$HOME\omium\Scripts\pip" install omium-mcp
$env:PATH = "$HOME\omium\Scripts;$env:PATH"
```

#### Option B — SDK + MCP bundle (`pip install omium`)

Install the Omium Python SDK, which has `omium-mcp` as a hard dependency. Pick this if you're also building agents/workflows in Python — you get both `omium` and `omium-mcp` console scripts in one install.

**macOS / Linux:**

```bash
python3 -m venv ~/omium
~/omium/bin/pip install --upgrade pip
~/omium/bin/pip install omium
export PATH="$HOME/omium/bin:$PATH"
```

**Windows (PowerShell):**

```powershell
python -m venv $HOME\omium
& "$HOME\omium\Scripts\pip" install --upgrade pip
& "$HOME\omium\Scripts\pip" install omium
$env:PATH = "$HOME\omium\Scripts;$env:PATH"
```

> Either option lands the same `omium-mcp` binary. The rest of this guide applies to both.

### 2. Quickest path — `omium-mcp init`

```
omium-mcp init
```

This interactive wizard prompts for your API key (input hidden), validates it against the Omium platform, and — if Claude Code is installed on your machine — auto-configures it via `claude mcp add`. No env vars to set, no config files to edit.

After it finishes, open Claude Code and ask: *"Show me my Omium workflows."*

For Claude Desktop or Cursor, the wizard prints the JSON snippet you need to paste — see **Manual setup** below for the full reference.

### Manual setup (alternative)

If you prefer not to use the wizard, or you're on Claude Desktop / Cursor where `init` only prints instructions:

#### Set your API key

**macOS / Linux:**

```bash
read -rs OMIUM_API_KEY && export OMIUM_API_KEY
echo "key length: ${#OMIUM_API_KEY}"   # sanity check; doesn't print the key
```

**Windows (PowerShell):**

```powershell
$secure = Read-Host "OMIUM_API_KEY" -AsSecureString
$env:OMIUM_API_KEY = [System.Net.NetworkCredential]::new("", $secure).Password
"key length: $($env:OMIUM_API_KEY.Length)"
```

#### Wire it into your AI client

##### Claude Code

**macOS / Linux:**

```bash
claude mcp add omium omium-mcp --env OMIUM_API_KEY="$OMIUM_API_KEY"
claude mcp list   # should show "omium"
```

**Windows (PowerShell):**

```powershell
claude mcp add omium omium-mcp --env "OMIUM_API_KEY=$env:OMIUM_API_KEY"
claude mcp list
```

##### Claude Desktop

Edit your Claude Desktop config:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "omium": {
      "command": "omium-mcp",
      "env": {
        "OMIUM_API_KEY": "omium_..."
      }
    }
  }
}
```

Replace `omium_...` with your actual key, then fully restart Claude Desktop.

##### Cursor

Add an MCP server in Cursor's settings: command `omium-mcp`, env var `OMIUM_API_KEY`. Exact UI varies by Cursor version — see Cursor's MCP docs.

### Troubleshooting

- **`pip install` fails with `Requires-Python >=3.10`** — Python 3.10+ is required because the upstream Anthropic `mcp` package needs 3.10+. Install via `pyenv` / `uv` / your OS package manager.
- **All tool calls return 401** — `OMIUM_API_KEY` is wrong or unset. Confirm with `echo "len: ${#OMIUM_API_KEY}"` (macOS/Linux) — should be > 30.
- **Pointing at a non-prod backend** — set `OMIUM_API_BASE` (e.g. `http://localhost:8000`) before starting the MCP.
- **AI client doesn't see Omium tools** — fully restart the client after editing config (not just close the window).

### Self-hosted (Streamable HTTP / Docker)

For team deployments behind a load balancer:

```bash
cd /path/to/omium-MCP
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
(~84 tools). JWT-only endpoints (dashboard login/signup, invitations,
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
| Scores              | `create_score`, `list_scores`, `get_scores_stats`          | auth-service              |
| Traces              | `ingest_trace`, `list_traces`, `get_trace`, `list_trace_failures`, `list_trace_projects` | auth-service |
| Projects            | `create_project`, `list_projects`, `connect_project_git`, `list_project_files`, `save_project_file`, `commit_project_git` | auth-service |
| GitHub              | `github_status`, `github_setup`, `github_update_repo`, `github_disconnect`, `github_create_fix_pr` | auth-service |
| Recovery            | `list_recovery_failures`, `trigger_recovery`, `create_recovery_command`, `list_recovery_commands`, `get_recovery_command`, `update_recovery_command_status`, `redeliver_recovery_command` | recovery-orchestrator |
| Replay              | `get_replay_state`, `get_replay_step`, `get_replay_consensus`, `get_replay_diff`, `restart_replay` | recovery-orchestrator |
| Analytics           | `get_usage_summary`, `get_dashboard_metrics`, `get_recent_activity`, `get_performance_metrics`, `get_performance_time_series`, `get_performance_agents`, `get_workflow_performance`, `get_workflow_cost`, `get_system_metrics` | analytics-engine |
| Audit               | `list_audit_logs`, `search_audit_logs`, `get_audit_log` | audit-logger |
| Billing             | `get_billing_balance`, `get_billing_usage`, `create_billing_topup`, `list_billing_transactions`, `get_subscription_status`, `estimate_execution_cost`, `get_cost_breakdown`, `get_quotas`, `get_billing_forecast`, `get_billing_recommendations`, `get_cost_analytics`, `list_billing_alerts`, … | billing-service |

### Notable conveniences

- `create_execution` auto-fills `agent_id` as `mcp-default-<tenant-slug>` when omitted.
- `execute_execution` auto-resolves `workflow_type` and `workflow_definition` from the execution's `workflow_id`.
- Tools that take complex bodies (`replay_execution`, `rollback_execution`, `apply_fix_to_execution`, `compare_executions`, project/recovery writes, billing checkouts, `ingest_trace`, audit creation, etc.) accept a pass-through `body: dict` — the docstring enumerates typical fields. This keeps the MCP layer useful while upstream schemas stabilize.
- Non-JSON upstream responses are wrapped as `{"ok": true, "text": "..."}`.
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
└── tools/             # 14 modules, one per API category
    ├── identity.py
    ├── workflows.py
    ├── executions.py
    ├── checkpoints.py
    ├── failures.py
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
