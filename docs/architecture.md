# omium-MCP — Architecture & Code Walkthrough

**Audience:** Engineers maintaining or extending the MCP, new joiners, anyone reviewing PRs against this package.
**Last updated:** 2026-04-27
**Package version:** 0.1.0

---

## Table of Contents

1. [Mental Model](#1-mental-model)
2. [File Structure](#2-file-structure)
3. [The Two Transports](#3-the-two-transports)
4. [Full Request Lifecycle](#4-full-request-lifecycle)
5. [File-by-File Walkthrough (in flow order)](#5-file-by-file-walkthrough-in-flow-order)
6. [Complete Example Flows](#6-complete-example-flows)
7. [Design Decisions & Subtle Bits](#7-design-decisions--subtle-bits)
8. [Failure Modes](#8-failure-modes)
9. [How to Add a New Tool](#9-how-to-add-a-new-tool)
10. [TL;DR](#10-tldr)

---

## 1. Mental Model

This package is a **bridge** between an MCP client (Claude Desktop, Claude Code, etc.) and Omium's Kong gateway. It speaks the **MCP protocol** to clients and **HTTP + `X-API-Key`** to Kong.

```
  ┌──────────────────┐         MCP protocol        ┌──────────────────┐    HTTP +     ┌──────────────────┐
  │  MCP CLIENT      │  ◄────  (stdio or HTTP) ──► │   omium-mcp      │  X-API-Key ──►│   Kong           │
  │  (Claude Code,   │                             │   (this package) │               │  api.omium.ai    │
  │   Desktop, etc.) │                             │                  │               │                  │
  └──────────────────┘                             └──────────────────┘               └──────────────────┘
                                                                                              │
                                                                                              ▼
                                                                                      ┌──────────────────┐
                                                                                      │ workflow-manager │
                                                                                      │ execution-engine │
                                                                                      │ billing-service  │
                                                                                      │ ...              │
                                                                                      └──────────────────┘
```

Two big design choices:

1. **Two transports, one set of tools.** stdio for `pip install` users, HTTP for self-hosted/Docker. They share everything except how the API key gets in.
2. **The MCP holds no state.** Every tool call is just: read API key → make HTTP call to Kong → parse response → return. Kong does auth & tenant scoping; the MCP is a thin client.

---

## 2. File Structure

```
omium-MCP/
├── pyproject.toml             # package metadata, hatchling build, console script
├── requirements.txt           # legacy; pyproject.toml is canonical
├── README.md                  # user-facing docs
├── Dockerfile                 # python:3.12-slim + `pip install .`
├── docker-compose.yml         # joins omium-platform_omium-network, points at kong:8000
├── .env.example               # OMIUM_API_BASE, MCP_HOST, MCP_PORT
├── server.py                  # legacy entry (`python server.py`) — delegates to cli.run_http
│
├── omium_mcp/                 # ◄── the actual Python package
│   ├── __init__.py            # __version__ = "0.1.0"
│   ├── cli.py                 # ★ ENTRY POINT — argparse, dispatches stdio vs HTTP
│   ├── config.py              # env-var reading (OMIUM_API_BASE, MCP_HOST, MCP_PORT)
│   ├── mcp_instance.py        # ★ the `FastMCP("omium-mcp")` singleton
│   ├── auth.py                # ★ ContextVar + BearerAuthMiddleware + init_from_env
│   ├── http.py                # ★ omium_get/post/patch/delete + _parse — Kong client
│   ├── tenant.py              # tenant-slug cache (used only by create_execution)
│   │
│   └── tools/                 # ◄── 14 modules, ~96 @mcp.tool() functions total
│       ├── __init__.py        # imports all 14 modules so decorators register
│       ├── identity.py        # 1 tool: verify_api_key (whoami)
│       ├── workflows.py       # 3 tools: list/get workflows + versions
│       ├── executions.py      # 11 tools: create/run/replay/rollback/etc.
│       ├── checkpoints.py     # 3 tools (tenant-wide; per-exec is in executions.py)
│       ├── failures.py        # failure stats, time-series, events
│       ├── traces.py          # ingest_trace, list_traces, get_trace, etc.
│       ├── projects.py        # project CRUD + git connect/commit + files
│       ├── github.py          # repo connect/disconnect/setup/PR
│       ├── recovery.py        # 7 tools: failures/trigger/commands
│       ├── replay.py          # replay state/step/diff/consensus
│       ├── scores.py          # score recording + stats
│       ├── analytics.py       # dashboard/performance/cost analytics
│       ├── audit.py           # audit log create/list/search
│       └── billing.py         # 16 tools: balance, top-up, subs, cost analytics, alerts
│
├── docs/
│   ├── quickstart.md
│   ├── tool-coverage-test.md
│   └── architecture.md         # this file
└── scripts/
    └── test_all_tools.py       # smoke-test harness
```

The five files marked **★** are the architectural core. Everything else is metadata, packaging, or thin tool wrappers.

---

## 3. The Two Transports

### stdio transport (default — for `pip install` users)

```
   Claude Desktop config:
     "command": "omium-mcp"
     "env": { "OMIUM_API_KEY": "omium_..." }

   Process is spawned by the client; communicates over stdin/stdout.
   API key is read ONCE from env at process start.

   ┌─────────┐  fork+exec  ┌─────────┐  stdin/stdout  ┌──────────────┐
   │ Claude  │────────────►│omium-mcp│◄──MCP frames──►│  FastMCP     │
   │ Desktop │             │ process │                │  dispatcher  │
   └─────────┘             └─────────┘                └──────────────┘
       (sets OMIUM_API_KEY env)
```

### HTTP transport (`omium-mcp serve` — for Docker/self-hosted)

```
   Long-running server on :9100. Client sends per-request:
     Authorization: Bearer omium_...

   The middleware extracts the bearer per request into a ContextVar.

   ┌─────────┐  HTTP POST   ┌────────────────────┐  MCP frames  ┌─────┐
   │ Claude  │  /mcp        │ BearerAuth-        │  via         │Fast │
   │ Code    │──Bearer ...─►│ Middleware (ASGI)  │──ContextVar─►│MCP  │
   └─────────┘              └────────────────────┘              └─────┘
```

### When to pick which

| Use case | Transport | Why |
|---|---|---|
| Single user with Claude Desktop / Claude Code | stdio | Zero infra; just `pip install omium-mcp` and add env var |
| Internal team behind shared infra | HTTP | One server serves many users, each with their own bearer token |
| CI/CD pipeline issuing tool calls | HTTP | No process per call |
| Plugged into Omium's own Docker stack | HTTP | Already containerized; `docker compose up` |

---

## 4. Full Request Lifecycle

```
   ┌────────────────────────────────────────────────────────────────────────────┐
   │   FLOW MAP — when a client calls list_workflows                             │
   └────────────────────────────────────────────────────────────────────────────┘

   Client                                                       Kong
     │                                                            ▲
     │                                                            │
     │  ① Spawn / connect                                         │
     ▼                                                            │
   server.py / cli.py:main                                         │
     │                                                            │
     │  ② Pick transport                                          │
     ▼                                                            │
     ┌──────────────┐         ┌──────────────────────┐            │
     │ run_stdio()  │   OR    │ run_http(host, port) │            │
     └──────┬───────┘         └────────┬─────────────┘            │
            │                          │                          │
            │ ③ load config            │                          │
            ▼                          ▼                          │
        config.py                 config.py                        │
            │                          │                          │
            │ ④ bind API key           │ ④ register middleware    │
            ▼                          ▼                          │
        auth.init_from_env()      auth.BearerAuthMiddleware       │
            │                          │                          │
            │ ⑤ ensure tools registered                            │
            ▼                          ▼                          │
        tools/__init__ imports all 14 modules                      │
        each does `from ..mcp_instance import mcp`                 │
        each `@mcp.tool()` registers on the singleton              │
            │                          │                          │
            │ ⑥ start protocol         │ ⑥ start uvicorn          │
            ▼                          ▼                          │
        mcp.run("stdio")          uvicorn.run(app)                 │
                                                                  │
                       ⑦ client invokes tool                      │
                                                                  │
            ▼                          ▼                          │
        tools/workflows.py:list_workflows(...)                     │
            │                                                     │
            │ ⑧ call HTTP helper                                  │
            ▼                                                     │
        http.omium_get("/api/v1/workflows")                        │
            │                                                     │
            │ ⑨ pull API key from ContextVar                      │
            ▼                                                     │
        auth.get_api_key() → "omium_..."                           │
            │                                                     │
            │ ⑩ make outbound request                             │
            ▼                                                     │
        httpx.AsyncClient.get(                                     │
            f"{OMIUM_API_BASE}/api/v1/workflows",                  │
            headers={"X-API-Key": key},                            │
        ) ────────────────────────────────────────────────────────┘
            │
            │ ⑪ parse / handle errors
            ▼
        http._parse(response) → dict
            │
            │ ⑫ return up the stack
            ▼
        FastMCP serializes the dict as MCP tool result
            │
            ▼
        Client receives result
```

---

## 5. File-by-File Walkthrough (in flow order)

### 5.1 `pyproject.toml` — what gets installed

Two important fields:

```toml
[project.scripts]
omium-mcp = "omium_mcp.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["omium_mcp"]
```

When `pip install omium-mcp` runs, pip:

1. Copies the `omium_mcp/` directory into site-packages.
2. Generates a small shell script called `omium-mcp` somewhere on `PATH` that calls `omium_mcp.cli.main()`.

So when Claude Desktop runs `"command": "omium-mcp"`, that's effectively `python -m omium_mcp.cli`.

### 5.2 `server.py` — back-compat entry

```python
from omium_mcp.cli import run_http
from omium_mcp.config import MCP_HOST, MCP_PORT

if __name__ == "__main__":
    run_http(MCP_HOST, MCP_PORT)
```

**Why it exists:** before the package was installable, the Docker image ran `python server.py`. Rather than break old setups, this file delegates to the same entry the console script uses. **HTTP only** — stdio doesn't make sense as `python server.py`.

### 5.3 `omium_mcp/__init__.py` — package marker

```python
__version__ = "0.1.0"
```

Tiny but important — `pyproject.toml` declares version `0.1.0`, and any code that imports `omium_mcp.__version__` reads from here. **If you ship a new version, bump both.**

### 5.4 `omium_mcp/cli.py` — the entry point

This is where every invocation actually starts.

```python
def main(argv=None):
    parser = argparse.ArgumentParser(prog="omium-mcp", ...)
    sub = parser.add_subparsers(dest="cmd")
    serve = sub.add_parser("serve", help="Run as a long-lived HTTP server.")
    serve.add_argument("--host", default=MCP_HOST)
    serve.add_argument("--port", type=int, default=MCP_PORT)

    args = parser.parse_args(argv)

    if args.cmd == "serve":
        run_http(args.host, args.port)
    else:
        run_stdio()
    return 0
```

**The two helper functions** are where the transports actually diverge:

```python
def run_stdio() -> None:
    init_from_env()           # ① read $OMIUM_API_KEY into the ContextVar
    mcp.run("stdio")          # ② let FastMCP own stdin/stdout

def run_http(host, port):
    import uvicorn
    app = mcp.streamable_http_app()              # ① get FastMCP's ASGI app
    app.add_middleware(BearerAuthMiddleware)     # ② wrap with bearer-extractor
    uvicorn.run(app, host=host, port=port)       # ③ serve
```

And here's the **side effect** that makes the tools work:

```python
from . import tools  # noqa: F401 — import-for-side-effect
```

That `import tools` triggers `tools/__init__.py`, which imports every tool module, each of which calls `@mcp.tool()` on the singleton. **Without that line, `omium-mcp` would start up advertising zero tools.**

The import is at the top of `cli.py`, not inside `run_*`. So tools are registered the moment `cli` is imported, regardless of which transport the user picks.

### 5.5 `omium_mcp/config.py` — environment plumbing

```python
OMIUM_API_BASE = os.environ.get("OMIUM_API_BASE", "https://api.omium.ai")
MCP_HOST       = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT       = int(os.environ.get("MCP_PORT", "9100"))
```

Three values, evaluated **once at import time**:

| Var | Default | Used by |
|---|---|---|
| `OMIUM_API_BASE` | `https://api.omium.ai` | `http.py` (where Kong lives) |
| `MCP_HOST` | `0.0.0.0` | only HTTP transport |
| `MCP_PORT` | `9100` | only HTTP transport |

In `docker-compose.yml`, `OMIUM_API_BASE` is overridden to `http://kong:8000` because inside the platform's Docker network the gateway is reachable by container name, not by public DNS.

### 5.6 `omium_mcp/mcp_instance.py` — the singleton

```python
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("omium-mcp")
```

**Why a separate file?** To break a circular import.

- Tool modules need `mcp` to decorate their functions.
- `cli.py` needs `mcp` to call `.run()` and `.streamable_http_app()`.
- If `mcp` lived in `cli.py`, tools couldn't import it without dragging argparse and uvicorn along.

So it's its own tiny module that everyone safely imports.

`FastMCP("omium-mcp")` is the official MCP Python SDK's high-level server. The string `"omium-mcp"` is what shows up in `claude mcp list` and in the MCP `initialize` handshake.

### 5.7 `omium_mcp/auth.py` — the cleverest file

Three things in this file:

#### (a) The ContextVar

```python
_api_key: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "omium_api_key", default=None
)
```

A `ContextVar` is like a thread-local that also works correctly across `async`. **Each in-flight request/task has its own value.** This is critical for HTTP mode where multiple clients can hit the server simultaneously with different bearer tokens — they must not bleed into each other.

For stdio, there's only one request "context" anyway (the whole process), so ContextVar is overkill but harmless.

#### (b) `init_from_env()` — stdio's binding

```python
def init_from_env() -> None:
    key = os.environ.get("OMIUM_API_KEY")
    if not key:
        raise RuntimeError("OMIUM_API_KEY environment variable is not set...")
    _api_key.set(key)
```

Reads once, sets once, fails fast if not set. Called from `run_stdio()`.

#### (c) `BearerAuthMiddleware` — HTTP's binding

This is **raw ASGI middleware** (not Starlette `BaseHTTPMiddleware`) — chosen because it sits right at the bottom of the stack, before FastMCP's own routing.

Flow:

```
Request comes in
  │
  ▼
scope["headers"] is a list of (name, value) tuples (bytes)
  │
  ▼
Find b"authorization" header → "Bearer omium_..."
  │
  ├─── If missing/wrong scheme:
  │      send {status: 401, body: {"error": "..."}, www-authenticate: Bearer}
  │      DONE
  │
  └─── If valid:
         reset_token = _api_key.set(token)
         try:
             await self.app(scope, receive, send)   # downstream runs with key bound
         finally:
             _api_key.reset(reset_token)            # restore previous value
```

The `try/finally` with `reset(reset_token)` is the key bit — it guarantees that even if the tool raises, the next request doesn't accidentally inherit this request's token.

#### (d) `get_api_key()` — what tools call

```python
def get_api_key() -> str:
    k = _api_key.get()
    if not k:
        raise RuntimeError("no Omium API key bound to this request")
    return k
```

If this ever raises, it means either `init_from_env()` was skipped (stdio) or middleware didn't run (HTTP) — both bugs. The error message is intentionally programmer-flavored, not user-flavored.

### 5.8 `omium_mcp/tools/__init__.py` — auto-registration

```python
from . import (  # noqa: F401
    analytics, audit, billing, checkpoints, executions,
    failures, github, identity, projects, recovery, replay,
    scores, traces, workflows,
)
```

**Why this is a side-effect import:** Python only runs a module's top-level code the first time it's imported. So importing `omium_mcp.tools.workflows` runs:

```python
@mcp.tool()
async def list_workflows() -> dict:
    ...
```

…which calls `mcp.tool()(list_workflows)`, which is what registers the tool with FastMCP. **The decorator's job is registration, not transformation** — the function itself stays roughly the same.

The `noqa: F401` comment tells linters: "I know these imports look unused; they're not, they're for side effects."

### 5.9 `omium_mcp/tools/identity.py` — the simplest tool

This is the canonical 1-tool module. Every other tool in the codebase is a variation on this:

```python
from ..http import omium_get
from ..mcp_instance import mcp

@mcp.tool()
async def verify_api_key() -> dict:
    """Return identity info for the current API key (tenant name, role, scopes).

    Calls GET /api/v1/api-keys/verify. Useful as a `whoami` probe.
    """
    return await omium_get("/api/v1/api-keys/verify")
```

Three things to notice:

1. **Imports are relative** (`..http`, `..mcp_instance`) — required because this is inside a package.
2. **The docstring is the tool description.** FastMCP feeds it to the LLM as the tool's `description` field. That's why every tool's docstring starts with a one-line summary then explains the upstream call.
3. **The function takes no arguments.** That makes the MCP `inputSchema` empty — `verify_api_key` shows up in clients with no parameters.

### 5.10 `omium_mcp/http.py` — the Kong client

Every tool ends up here. Four functions, all symmetric. Look at `omium_get`:

```python
async def omium_get(path, params=None, timeout=15.0):
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(
            f"{OMIUM_API_BASE}{path}",
            headers={"X-API-Key": get_api_key()},
            params=params,
        )
        return _parse(r)
```

Three responsibilities:

1. **Build the URL** — `OMIUM_API_BASE` (from config) + path. `path` is always something the tool hardcoded like `"/api/v1/workflows"`.
2. **Translate auth** — pull the token out of the ContextVar via `get_api_key()` and send it as `X-API-Key`. The MCP client gave us the token as a Bearer; Kong wants it as X-API-Key. **This translation is the only auth work the MCP does.**
3. **Parse the response** via `_parse()`.

```python
def _parse(r):
    if not r.is_success:
        try:    detail = r.json()
        except: detail = r.text
        raise RuntimeError(
            f"Omium API {r.request.method} {r.request.url.path} -> {r.status_code}: {detail}"
        )
    if r.status_code == 204 or not r.content:
        return {"ok": True}
    try:    return r.json()
    except: return {"ok": True, "text": r.text[:4000]}
```

This is the **error contract**. If Kong/upstream returns 4xx/5xx, the tool raises with a message that includes the upstream status and body. FastMCP catches the exception and surfaces it as a tool error to the LLM, so the LLM sees `Omium API GET /api/v1/workflows -> 401: {"detail":"invalid api key"}` instead of an opaque "internal error".

Edge cases:

- **204 No Content** (DELETE responses) → `{"ok": True}` because the LLM expects a dict.
- **Non-JSON body** (e.g. `/observability/metrics/prometheus` returns `text/plain`) → `{"ok": True, "text": "..."}` so it stays serializable.

### 5.11 `omium_mcp/tenant.py` — the smart helper

Used by exactly one tool: `create_execution`. The flow:

```
   create_execution(workflow_id="...", agent_id=None)
       │
       │ agent_id is None — need to default it
       ▼
   resolve_tenant_slug()
       │
       │ first call this process: cache miss
       ▼
   GET /api/v1/api-keys/verify   ← uses same X-API-Key
       │
       │ response: { tenant_name: "Acme Corp", ... }
       ▼
   _slugify("Acme Corp") → "acme-corp"
       │
       │ cache it: _cache[key] = "acme-corp"
       ▼
   return "acme-corp"
       │
       ▼
   agent_id = "mcp-default-acme-corp"
```

**Why an in-process cache?** Without it, every call to `create_execution` would do two HTTP round-trips instead of one. The cache lives for the lifetime of the process. For HTTP transport, the cache key is the actual API key string, so each tenant gets their own slot.

This is the **only** place where one tool implicitly calls another endpoint. Everything else is a 1-to-1 mapping.

### 5.12 `omium_mcp/tools/executions.py` — the most interesting tools

Most tools are trivial wrappers. `executions.py` has the two non-trivial ones:

#### `create_execution` — auto-fills `agent_id`

```python
async def create_execution(workflow_id, agent_id=None, input_data=None, metadata=None):
    if not agent_id:
        slug = await resolve_tenant_slug()
        agent_id = f"mcp-default-{slug}"
    body = {"workflow_id": workflow_id, "agent_id": agent_id}
    if input_data is not None: body["input_data"] = input_data
    if metadata is not None:   body["metadata"] = metadata
    return await omium_post("/api/v1/executions", body)
```

#### `execute_execution` — auto-resolves missing fields by chaining two GETs

```python
async def execute_execution(execution_id, workflow_type=None, workflow_definition=None, inputs=None):
    if workflow_type is None or workflow_definition is None or inputs is None:
        execution = await omium_get(f"/api/v1/executions/{execution_id}")
        if workflow_type is None or workflow_definition is None:
            workflow_id = execution.get("workflow_id")
            workflow = await omium_get(f"/api/v1/workflows/{workflow_id}")
            workflow_type       = workflow_type       or workflow.get("workflow_type") or "langgraph"
            workflow_definition = workflow_definition or workflow.get("definition") or {}
        if inputs is None:
            inputs = execution.get("input_data") or {}

    return await omium_post(
        f"/api/v1/executions/{execution_id}/execute",
        json_body={"workflow_definition": workflow_definition, "inputs": inputs},
        params={"workflow_type": workflow_type},
    )
```

The reason this matters: an LLM caller doesn't know the workflow's type or definition — it only knows the execution ID. So the tool fetches them on the LLM's behalf. Without this, the LLM would have to call `get_execution` → `get_workflows` → `execute_execution` itself, which is 3 round-trips and 3 chances to make a mistake.

### 5.13 The "passthrough body" pattern — `tools/billing.py`, `recovery.py`, etc.

Some upstream endpoints take complex bodies that change as the platform evolves. Rather than enumerate every field as a typed argument, those tools accept a `body: dict`:

```python
@mcp.tool()
async def create_billing_topup(body: dict) -> dict:
    """Create a credit top-up (direct).

    Calls POST /api/v1/billing/topup. Required body: `amount_cents` (NOT
    `amount`; min 1000 = $10). Optional: `currency`.
    """
    return await omium_post("/api/v1/billing/topup", body)
```

The docstring tells the LLM what fields to put in `body`. **This is a deliberate trade-off**: less type safety, more flexibility. Used wherever upstream schemas were unstable when the MCP was written.

The simple/trivial endpoints get typed args; the sprawling ones get `body`. Pattern is consistent across the codebase.

### 5.14 The other tool modules — same pattern

Quick map of who does what:

| Module | Tools | Upstream service |
|---|---|---|
| `identity.py` | 1 (whoami) | auth-service |
| `workflows.py` | 3 | auth-service |
| `executions.py` | 11 (the rich ones) | execution-engine |
| `checkpoints.py` | 3 (tenant-wide) | execution-engine |
| `failures.py` | 4 | execution-engine |
| `traces.py` | ~5 | tracing-service via auth-service |
| `projects.py` | ~6 | auth-service |
| `github.py` | 5 | auth-service |
| `recovery.py` | 7 | recovery-orchestrator |
| `replay.py` | ~5 | recovery-orchestrator |
| `scores.py` | 3 | auth-service |
| `analytics.py` | ~9 | analytics-engine |
| `audit.py` | 4 | audit-logger |
| `billing.py` | 16 | billing-service |

**Total ~96 tools.** Every single one resolves to one or two `omium_get/post/patch/delete` calls.

---

## 6. Complete Example Flows

### Example A — stdio: `pip install` user calls `verify_api_key`

```
   Claude Desktop config:
     "command": "omium-mcp"
     "env": { "OMIUM_API_KEY": "omium_abc123" }

   ① Claude Desktop spawns subprocess "omium-mcp"
        │
        ▼
   ② Shell finds the console script created by pip → runs python omium_mcp.cli:main
        │
        ▼
   ③ cli.py top-level imports run:
        - import argparse, sys
        - from .auth import BearerAuthMiddleware, init_from_env
        - from .config import MCP_HOST, MCP_PORT
        - from .mcp_instance import mcp                ← FastMCP("omium-mcp") created
        - from . import tools                          ← imports all 14 tool modules
                                                        each runs @mcp.tool() decorators
                                                        ~96 tools registered on `mcp`
        │
        ▼
   ④ main() runs argparse with no args → args.cmd is None → run_stdio()
        │
        ▼
   ⑤ run_stdio():
        - init_from_env() reads OMIUM_API_KEY env → _api_key.set("omium_abc123")
        - mcp.run("stdio") starts MCP protocol on stdin/stdout
        │
        ▼
   ⑥ Claude sends JSON-RPC: { "method": "tools/call", "name": "verify_api_key" }
        │
        ▼
   ⑦ FastMCP dispatches → calls verify_api_key()
        │
        ▼
   ⑧ verify_api_key calls omium_get("/api/v1/api-keys/verify")
        │
        ▼
   ⑨ omium_get:
        - get_api_key() → "omium_abc123"
        - httpx GET https://api.omium.ai/api/v1/api-keys/verify
            with header X-API-Key: omium_abc123
        │
        ▼
   ⑩ Kong validates X-API-Key, forwards to auth-service
        Kong/auth returns 200 { "tenant_name": "Acme", "role": "admin", ... }
        │
        ▼
   ⑪ _parse(r) → r.json()
        │
        ▼
   ⑫ FastMCP serializes the dict, sends as MCP tool result back to Claude
```

### Example B — HTTP: Docker user calls `create_execution`

```
   docker compose up
     ↳ container runs CMD ["omium-mcp", "serve"]
     ↳ environment OMIUM_API_BASE=http://kong:8000

   ① main() with args.cmd == "serve" → run_http("0.0.0.0", 9100)
        │
        ▼
   ② run_http:
        - app = mcp.streamable_http_app()
        - app.add_middleware(BearerAuthMiddleware)
        - uvicorn.run(app, host=..., port=...)
        │
        ▼
   ③ Claude Code config:
        claude mcp add --transport http omium http://localhost:9100/mcp \
          --header "Authorization: Bearer omium_xyz789"
        │
        ▼
   ④ Claude sends:
        POST http://localhost:9100/mcp
          Authorization: Bearer omium_xyz789
          { method: "tools/call", name: "create_execution",
            arguments: { workflow_id: "wf-42" } }
        │
        ▼
   ⑤ uvicorn → BearerAuthMiddleware:
        - scope["headers"] has b"authorization": b"Bearer omium_xyz789"
        - scheme="Bearer", token="omium_xyz789"
        - reset = _api_key.set("omium_xyz789")
        - await self.app(scope, receive, send)
        │
        ▼
   ⑥ FastMCP dispatches → create_execution(workflow_id="wf-42")
        │
        ▼
   ⑦ agent_id is None → resolve_tenant_slug()
        - _cache miss for "omium_xyz789"
        - GET http://kong:8000/api/v1/api-keys/verify
            X-API-Key: omium_xyz789
        - response: { tenant_name: "Acme Corp" }
        - slug = "acme-corp"
        - _cache["omium_xyz789"] = "acme-corp"
        - return "acme-corp"
        │
        ▼
   ⑧ agent_id = "mcp-default-acme-corp"
        │
        ▼
   ⑨ omium_post("/api/v1/executions", { workflow_id, agent_id })
        - POST http://kong:8000/api/v1/executions
            X-API-Key: omium_xyz789
            body: { workflow_id: "wf-42", agent_id: "mcp-default-acme-corp" }
        │
        ▼
   ⑩ Kong → execution-engine
        - returns 201 { id: "exec-99", status: "pending", ... }
        │
        ▼
   ⑪ _parse → dict → FastMCP → HTTP response → Claude Code
        │
        ▼
   ⑫ Middleware finally block:
        - _api_key.reset(reset)   ← next request starts clean
```

---

## 7. Design Decisions & Subtle Bits

These are the design decisions that aren't obvious from reading any single file.

### 7.1 ContextVar, not module-global

Naive version: `API_KEY = "..."` at module level. Would work for stdio, **break disastrously** for HTTP — request A's key would clobber request B's. ContextVar isolates per-request and survives `async`/`await` boundaries automatically.

### 7.2 Auth is not in the tool layer

Tools never see `OMIUM_API_KEY` directly. They call `get_api_key()` → ContextVar. This means:

- You can change auth (e.g. add JWT support) without touching any tool.
- Tools can be tested with `_api_key.set("test-key")` and no env or HTTP setup.
- A tool that forgets to authenticate is a *runtime crash*, not a security hole.

### 7.3 The MCP doesn't know about tenants

There is **no `tenant_id` argument anywhere**. Kong + auth-service derive the tenant from the API key. The MCP just forwards. This matters because:

- An LLM cannot accidentally (or maliciously) query another tenant.
- The MCP doesn't need any DB access of its own.
- Adding a new tenant requires zero MCP changes.

### 7.4 Tool registration is 100% decorator-driven

There's no central tool list to maintain. Adding a new tool is:

```python
# in some tools/foo.py
@mcp.tool()
async def my_new_tool(x: int) -> dict:
    """Description the LLM reads."""
    return await omium_get(f"/api/v1/foo/{x}")
```

…and (if you create a new module) one new line in `tools/__init__.py`. No registry, no manifest. Decorators on the singleton.

### 7.5 Errors from upstream are surfaced verbatim

`_parse` raises `RuntimeError` with the upstream method, path, status, and body. The LLM sees the actual error from Kong / the upstream service. Compare to silently returning `{"error": "something went wrong"}` — that would force the LLM to guess.

### 7.6 Two transports, one decorator-registered tool set

Both `run_stdio` and `run_http` use the same `mcp` singleton. Tools are registered once, at import time, regardless of transport. **This guarantees the two transports advertise identical tools** — impossible for them to drift.

### 7.7 The dual-default for `OMIUM_API_BASE`

- **Code default**: `https://api.omium.ai` — works for `pip install` users with zero config.
- **Docker override**: `http://kong:8000` — works inside the platform's Docker network with zero TLS / DNS hassle.

Same code, two perfect defaults for two different deployments.

### 7.8 Why FastMCP over raw `mcp.server.Server`

FastMCP gives us:

- Decorator-based tool registration (no manual schema-building).
- Automatic JSON Schema derivation from Python type hints (e.g. `workflow_id: str`).
- Both stdio and Streamable HTTP transports out of the box (`mcp.run("stdio")` / `mcp.streamable_http_app()`).
- Docstring → tool description with no extra wiring.

Raw `Server` would force us to hand-write all of that.

---

## 8. Failure Modes

| Failure | Where it surfaces | What the user sees |
|---|---|---|
| `OMIUM_API_KEY` not set (stdio) | `init_from_env()` raises at startup | Process exits with `RuntimeError: OMIUM_API_KEY environment variable is not set...` |
| Bearer header missing (HTTP) | `BearerAuthMiddleware` returns 401 | `HTTP 401 {"error":"missing Authorization: Bearer ..."}` |
| Wrong API key | Kong returns 401, `_parse` raises | `Omium API GET /api/v1/... -> 401: {"detail":"invalid api key"}` (LLM-readable) |
| Upstream 5xx | `_parse` raises | `Omium API POST /api/v1/... -> 500: {...}` |
| Network timeout | httpx raises, propagates | LLM sees the `httpx.TimeoutException` |
| Tenant-slug lookup fails | `resolve_tenant_slug` raises | Only affects `create_execution` when `agent_id` is omitted |
| Non-JSON 2xx response | `_parse` returns `{"ok": True, "text": "..."}` | LLM sees a wrapped text payload |
| 204 No Content (after DELETE) | `_parse` returns `{"ok": True}` | LLM sees a success marker |

---

## 9. How to Add a New Tool

If your platform team adds a new endpoint, e.g. `GET /api/v1/agents`:

### Step 1 — Pick a module

Look at `omium_mcp/tools/`. Does the new endpoint fit an existing category? If yes, edit that file. If no, create a new module (e.g. `agents.py`).

### Step 2 — Write the function

```python
from ..http import omium_get
from ..mcp_instance import mcp

@mcp.tool()
async def list_agents() -> dict:
    """List agents for the caller's tenant.

    Calls GET /api/v1/agents.
    """
    return await omium_get("/api/v1/agents")
```

The docstring is what the LLM reads to decide when to call this. **Be specific about what the tool does and what arguments it expects.**

### Step 3 — Register the module (only if you created a new file)

Edit `tools/__init__.py`:

```python
from . import (  # noqa: F401
    agents,        # ← add this line
    analytics,
    audit,
    ...
)
```

### Step 4 — Bump the version

Both `pyproject.toml` and `omium_mcp/__init__.py` (e.g. `0.1.0` → `0.1.1`).

### Step 5 — Rebuild / redeploy

- **Docker (HTTP):** `docker compose up -d --build`
- **Local stdio test:** `.venv/bin/python -m omium_mcp.cli` (reads `$OMIUM_API_KEY`)
- **PyPI release:** `python -m build && twine upload dist/*`

### Step 6 — Verify

Use the test harness:

```bash
.venv/bin/python scripts/test_all_tools.py
```

…or call the tool from a real client:

```python
import asyncio
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    headers = {"Authorization": "Bearer omium_..."}
    async with streamablehttp_client("http://localhost:9100/mcp", headers=headers) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool("list_agents", {})
            print(res.content[0].text)

asyncio.run(main())
```

That's it. No registry, no schema file, no manifest. **The decorator is the contract.**

---

## 10. TL;DR

```
   Entry:    cli.py:main → run_stdio() OR run_http()
                                │
                                ▼
   Auth bind: env var (stdio)  or  Bearer header (HTTP)
                                │
                                ▼ ContextVar holds it
                                │
   Tools:    @mcp.tool()-decorated functions, auto-registered via tools/__init__.py
                                │
                                ▼
   Helpers:  http.omium_get/post/patch/delete (read ContextVar, send X-API-Key)
                                │
                                ▼
   Upstream: Kong → workflow-manager / execution-engine / billing-service / ...
```

Every tool is one line of HTTP plumbing wrapped in a docstring the LLM reads. The whole package is ~600 lines of Python, half of which is docstrings. **The cleverness is in the architecture, not the code:**

- ContextVar for per-request auth
- Decorators for zero-registration tools
- Two transports sharing one singleton
- A hard rule that the MCP holds no state and never sees a tenant ID

---

## Appendix — Key files to read in order

If you're new to this codebase, read in this order (about 30 minutes total):

1. `omium_mcp/cli.py` — see the two entry paths
2. `omium_mcp/auth.py` — understand how the API key flows
3. `omium_mcp/http.py` — see the only place that talks to Kong
4. `omium_mcp/tools/identity.py` — the simplest tool
5. `omium_mcp/tools/executions.py` — the most complex tools
6. `omium_mcp/tenant.py` — the one bit of cleverness in the tool layer

After that you've seen every architectural pattern in the codebase. The other 13 tool modules are mechanical — same shape as `identity.py` or `billing.py`.
