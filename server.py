"""
Omium MCP Server — persistent Streamable-HTTP transport.

Exposes every SDK-reachable Omium endpoint (anything that accepts X-API-Key)
as an MCP tool, routed through Kong. Endpoints that are JWT-only
(dashboard login/signup, invitations, Slack OAuth, billing/api-key admin
screens driven by the UI) are intentionally omitted because an MCP client
only holds an API key.

Auth flow: MCP clients connect to http://<host>:9100/mcp with an
`Authorization: Bearer omium_...` header. A small ASGI middleware captures
that token into a ContextVar; each tool reads the contextvar and forwards
the key as `X-API-Key` to Kong. Tenant scoping is derived server-side from
the key, so no tenant_id parameter is ever accepted or passed.
"""

from __future__ import annotations

import contextvars
import os
import re

import httpx
import uvicorn
from mcp.server.fastmcp import FastMCP

OMIUM_API_BASE = os.environ.get("OMIUM_API_BASE", "http://kong:8000")
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", "9100"))

_api_key: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "omium_api_key", default=None
)


class BearerAuthMiddleware:
    """Extract `Authorization: Bearer <token>` into a ContextVar, reject if missing."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        auth = ""
        for name, value in scope.get("headers") or []:
            if name == b"authorization":
                auth = value.decode("latin-1")
                break

        scheme, _, token = auth.partition(" ")
        if scheme.lower() != "bearer" or not token:
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"www-authenticate", b'Bearer realm="omium-mcp"'),
                    ],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b'{"error":"missing Authorization: Bearer <omium_api_key> header"}',
                }
            )
            return

        reset_token = _api_key.set(token)
        try:
            await self.app(scope, receive, send)
        finally:
            _api_key.reset(reset_token)


def _key() -> str:
    k = _api_key.get()
    if not k:
        raise RuntimeError("no Omium API key bound to this request")
    return k


def _parse(r: httpx.Response) -> dict:
    """Parse an httpx response; include upstream error body on non-2xx."""
    if not r.is_success:
        try:
            detail = r.json()
        except Exception:
            detail = r.text
        raise RuntimeError(
            f"Omium API {r.request.method} {r.request.url.path} -> {r.status_code}: {detail}"
        )
    if r.status_code == 204 or not r.content:
        return {"ok": True}
    try:
        return r.json()
    except Exception:
        return {"ok": True, "text": r.text[:4000]}


async def _omium_get(path: str, params: dict | None = None, timeout: float = 15.0) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(
            f"{OMIUM_API_BASE}{path}",
            headers={"X-API-Key": _key()},
            params=params,
        )
        return _parse(r)


async def _omium_post(
    path: str,
    json_body: dict | list | None = None,
    params: dict | None = None,
    timeout: float = 60.0,
) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            f"{OMIUM_API_BASE}{path}",
            headers={"X-API-Key": _key(), "Content-Type": "application/json"},
            json=json_body if json_body is not None else {},
            params=params,
        )
        return _parse(r)


async def _omium_patch(
    path: str,
    json_body: dict | None = None,
    params: dict | None = None,
    timeout: float = 30.0,
) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.patch(
            f"{OMIUM_API_BASE}{path}",
            headers={"X-API-Key": _key(), "Content-Type": "application/json"},
            json=json_body,
            params=params,
        )
        return _parse(r)


async def _omium_delete(path: str, params: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.delete(
            f"{OMIUM_API_BASE}{path}",
            headers={"X-API-Key": _key()},
            params=params,
        )
        return _parse(r)


_tenant_slug_cache: dict[str, str] = {}


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "unknown"


async def _resolve_tenant_slug() -> str:
    """Return a trace-friendly slug for the current request's tenant."""
    k = _key()
    cached = _tenant_slug_cache.get(k)
    if cached is not None:
        return cached
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            f"{OMIUM_API_BASE}/api/v1/api-keys/verify",
            headers={"X-API-Key": k},
        )
        r.raise_for_status()
        data = r.json()
    slug = _slugify(data.get("tenant_name") or "")
    _tenant_slug_cache[k] = slug
    return slug


mcp = FastMCP("omium-mcp")


# =========================================================================
# Identity
# =========================================================================

@mcp.tool()
async def verify_api_key() -> dict:
    """Return identity info for the current API key (tenant name, role, scopes).

    Calls GET /api/v1/api-keys/verify. Useful as a `whoami` probe.
    """
    return await _omium_get("/api/v1/api-keys/verify")


# =========================================================================
# Workflows
# =========================================================================

@mcp.tool()
async def list_workflows() -> dict:
    """List workflows for the caller's tenant.

    Calls GET /api/v1/workflows through Kong. Tenant scope is derived from
    the caller's Omium API key — no tenant_id argument is needed or honored.
    """
    return await _omium_get("/api/v1/workflows")


@mcp.tool()
async def get_workflows(workflow_id: str) -> dict:
    """Get a specific workflow for the caller's tenant.

    Calls GET /api/v1/workflows/<workflow_id> through Kong.
    """
    return await _omium_get(f"/api/v1/workflows/{workflow_id}")


@mcp.tool()
async def list_workflow_versions(workflow_id: str) -> dict:
    """List all versions of a workflow.

    Calls GET /api/v1/workflows/<workflow_id>/versions through Kong.
    """
    return await _omium_get(f"/api/v1/workflows/{workflow_id}/versions")


# =========================================================================
# Executions
# =========================================================================

@mcp.tool()
async def list_executions() -> dict:
    """List recent executions for the caller's tenant.

    Calls GET /api/v1/executions through Kong.
    """
    return await _omium_get("/api/v1/executions")


@mcp.tool()
async def get_execution(execution_id: str) -> dict:
    """Get a specific execution for the caller's tenant.

    Calls GET /api/v1/executions/<execution_id> through Kong.
    """
    return await _omium_get(f"/api/v1/executions/{execution_id}")


@mcp.tool()
async def list_checkpoints(execution_id: str) -> dict:
    """List checkpoints for a specific execution.

    Calls GET /api/v1/executions/<execution_id>/checkpoints through Kong.
    """
    return await _omium_get(f"/api/v1/executions/{execution_id}/checkpoints")


@mcp.tool()
async def list_live_executions() -> dict:
    """List live executions for the caller's tenant.

    Calls GET /api/v1/executions/live through Kong.
    """
    return await _omium_get("/api/v1/executions/live")


@mcp.tool()
async def create_execution(
    workflow_id: str,
    agent_id: str | None = None,
    input_data: dict | None = None,
    metadata: dict | None = None,
) -> dict:
    """Create and enqueue a new execution.

    Calls POST /api/v1/executions through Kong. workflow_id is required.
    agent_id is a free-form identity/audit label. If omitted, the MCP
    substitutes "mcp-default-<tenant-slug>" derived from the API key.
    input_data and metadata are free-form JSON the agent attaches to the run.

    Returns the full execution record.
    """
    if not agent_id:
        slug = await _resolve_tenant_slug()
        agent_id = f"mcp-default-{slug}"
    body: dict = {"workflow_id": workflow_id, "agent_id": agent_id}
    if input_data is not None:
        body["input_data"] = input_data
    if metadata is not None:
        body["metadata"] = metadata
    return await _omium_post("/api/v1/executions", body)


@mcp.tool()
async def execute_execution(
    execution_id: str,
    workflow_type: str | None = None,
    workflow_definition: dict | None = None,
    inputs: dict | None = None,
) -> dict:
    """Run a previously-created (pending) execution.

    Calls POST /api/v1/executions/<execution_id>/execute. If workflow_type
    or workflow_definition are omitted, the MCP auto-resolves them from the
    execution's workflow_id. inputs defaults to the execution's stored input_data.
    """
    if workflow_type is None or workflow_definition is None or inputs is None:
        execution = await _omium_get(f"/api/v1/executions/{execution_id}")
        if workflow_type is None or workflow_definition is None:
            workflow_id = execution.get("workflow_id")
            if not workflow_id:
                raise RuntimeError(
                    f"execution {execution_id} has no workflow_id; pass workflow_type and workflow_definition explicitly"
                )
            workflow = await _omium_get(f"/api/v1/workflows/{workflow_id}")
            if workflow_type is None:
                workflow_type = workflow.get("workflow_type") or "langgraph"
            if workflow_definition is None:
                workflow_definition = workflow.get("definition") or {}
        if inputs is None:
            inputs = execution.get("input_data") or {}

    return await _omium_post(
        f"/api/v1/executions/{execution_id}/execute",
        json_body={"workflow_definition": workflow_definition, "inputs": inputs},
        params={"workflow_type": workflow_type},
    )


@mcp.tool()
async def update_execution_status(
    execution_id: str,
    status: str,
    output_data: dict | None = None,
    error_message: str | None = None,
) -> dict:
    """Update the status of an execution (direct write, not a workflow action).

    Calls PATCH /api/v1/executions/<execution_id>/status. Conventional status
    values: "pending", "running", "completed", "failed", "cancelled".
    Prefer execute_execution / replay_execution / rollback_execution for
    workflow state changes — use this mainly for manual cleanup.
    """
    params: dict = {"status": status}
    if error_message is not None:
        params["error_message"] = error_message
    return await _omium_patch(
        f"/api/v1/executions/{execution_id}/status",
        json_body=output_data,
        params=params,
    )


@mcp.tool()
async def delete_execution(execution_id: str) -> dict:
    """Delete an execution permanently (hard delete, no undo).

    Calls DELETE /api/v1/executions/<execution_id>. Prefer
    update_execution_status(status="cancelled") if you want to retain the
    record for audit purposes.
    """
    result = await _omium_delete(f"/api/v1/executions/{execution_id}")
    result.setdefault("execution_id", execution_id)
    return result


@mcp.tool()
async def replay_execution(execution_id: str, body: dict | None = None) -> dict:
    """Replay an execution from a checkpoint.

    Calls POST /api/v1/executions/<execution_id>/replay. The `body` dict is
    passed through as-is (typical fields: `checkpoint_id`, `from_step`,
    `inputs`, `override_definition`).
    """
    return await _omium_post(f"/api/v1/executions/{execution_id}/replay", body)


@mcp.tool()
async def compare_executions(body: dict) -> dict:
    """Compare two executions side by side.

    Calls POST /api/v1/executions/compare. Typical body:
    `{"execution_id_a": "...", "execution_id_b": "..."}`.
    """
    return await _omium_post("/api/v1/executions/compare", body)


@mcp.tool()
async def rollback_execution(execution_id: str, body: dict | None = None) -> dict:
    """Roll back an execution to a prior checkpoint.

    Calls POST /api/v1/executions/<execution_id>/rollback. Typical body:
    `{"checkpoint_id": "..."}`.
    """
    return await _omium_post(f"/api/v1/executions/{execution_id}/rollback", body)


@mcp.tool()
async def apply_fix_to_execution(execution_id: str, body: dict | None = None) -> dict:
    """Apply a RIS-generated (or user-supplied) fix to an execution.

    Calls POST /api/v1/executions/<execution_id>/apply-fix. Body typically
    carries fix metadata or patch content; pass through as-is.
    """
    return await _omium_post(f"/api/v1/executions/{execution_id}/apply-fix", body)


@mcp.tool()
async def get_apply_to_repo_payload(execution_id: str) -> dict:
    """Get the git-ready patch payload for an execution's fix.

    Calls GET /api/v1/executions/<execution_id>/apply-to-repo-payload.
    Returns the files + diffs that would be committed if the fix is applied.
    """
    return await _omium_get(f"/api/v1/executions/{execution_id}/apply-to-repo-payload")


# =========================================================================
# Checkpoints (tenant-wide)
# =========================================================================

@mcp.tool()
async def create_checkpoint(body: dict) -> dict:
    """Create a checkpoint record.

    Calls POST /api/v1/checkpoints. Typical body fields: `execution_id`,
    `step_index`, `state`, `metadata`.
    """
    return await _omium_post("/api/v1/checkpoints", body)


@mcp.tool()
async def list_all_checkpoints(
    execution_id: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> dict:
    """List checkpoints across the caller's tenant (optionally filtered).

    Calls GET /api/v1/checkpoints. Differs from list_checkpoints (which is
    scoped to one execution) — this is tenant-wide.
    """
    params: dict = {}
    if execution_id:
        params["execution_id"] = execution_id
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    return await _omium_get("/api/v1/checkpoints", params=params or None)


@mcp.tool()
async def get_checkpoint(checkpoint_id: str) -> dict:
    """Get a specific checkpoint.

    Calls GET /api/v1/checkpoints/<checkpoint_id>.
    """
    return await _omium_get(f"/api/v1/checkpoints/{checkpoint_id}")


# =========================================================================
# Failures (execution-engine)
# =========================================================================

@mcp.tool()
async def list_failures(
    limit: int | None = None,
    offset: int | None = None,
    status: str | None = None,
    workflow_id: str | None = None,
) -> dict:
    """List failure events for the caller's tenant.

    Calls GET /api/v1/failures.
    """
    params = {k: v for k, v in {
        "limit": limit, "offset": offset, "status": status, "workflow_id": workflow_id,
    }.items() if v is not None}
    return await _omium_get("/api/v1/failures", params=params or None)


@mcp.tool()
async def get_failures_stats() -> dict:
    """Aggregate failure statistics for the tenant.

    Calls GET /api/v1/failures/stats.
    """
    return await _omium_get("/api/v1/failures/stats")


@mcp.tool()
async def get_failures_time_series(
    window: str | None = None,
    bucket: str | None = None,
) -> dict:
    """Failure counts bucketed over time.

    Calls GET /api/v1/failures/time-series. Typical params: `window=24h`,
    `bucket=1h`.
    """
    params = {k: v for k, v in {"window": window, "bucket": bucket}.items() if v is not None}
    return await _omium_get("/api/v1/failures/time-series", params=params or None)


@mcp.tool()
async def create_failure_event(body: dict) -> dict:
    """Record a failure event (used by SDKs to push failures into Omium).

    Calls POST /api/v1/failures/events.
    """
    return await _omium_post("/api/v1/failures/events", body)


# =========================================================================
# Observability (execution-engine)
# =========================================================================

@mcp.tool()
async def get_observability_metrics() -> dict:
    """Structured metrics snapshot.

    Calls GET /observability/metrics.
    """
    return await _omium_get("/observability/metrics")


@mcp.tool()
async def get_observability_metrics_summary() -> dict:
    """Human-readable metrics summary.

    Calls GET /observability/metrics/summary.
    """
    return await _omium_get("/observability/metrics/summary")


@mcp.tool()
async def get_observability_metrics_prometheus() -> dict:
    """Prometheus-format metrics (returned as `{"text": ...}`).

    Calls GET /observability/metrics/prometheus.
    """
    return await _omium_get("/observability/metrics/prometheus")


@mcp.tool()
async def list_observability_traces() -> dict:
    """List observability traces.

    Calls GET /observability/traces.
    """
    return await _omium_get("/observability/traces")


@mcp.tool()
async def get_observability_trace(execution_id: str) -> dict:
    """Full trace for one execution.

    Calls GET /observability/traces/<execution_id>.
    """
    return await _omium_get(f"/observability/traces/{execution_id}")


@mcp.tool()
async def get_observability_trace_summary(execution_id: str) -> dict:
    """Summarized trace for one execution.

    Calls GET /observability/traces/<execution_id>/summary.
    """
    return await _omium_get(f"/observability/traces/{execution_id}/summary")


@mcp.tool()
async def list_alerts() -> dict:
    """Current active alerts.

    Calls GET /observability/alerts.
    """
    return await _omium_get("/observability/alerts")


@mcp.tool()
async def list_alerts_history() -> dict:
    """Alert history.

    Calls GET /observability/alerts/history.
    """
    return await _omium_get("/observability/alerts/history")


@mcp.tool()
async def acknowledge_alert(condition_name: str, body: dict | None = None) -> dict:
    """Acknowledge an alert.

    Calls POST /observability/alerts/<condition_name>/acknowledge.
    """
    return await _omium_post(f"/observability/alerts/{condition_name}/acknowledge", body)


@mcp.tool()
async def get_observability_dashboard() -> dict:
    """Aggregate observability dashboard payload.

    Calls GET /observability/dashboard.
    """
    return await _omium_get("/observability/dashboard")


@mcp.tool()
async def get_observability_health() -> dict:
    """Health of the observability subsystem.

    Calls GET /observability/health.
    """
    return await _omium_get("/observability/health")


# =========================================================================
# Scores
# =========================================================================

@mcp.tool()
async def create_score(body: dict) -> dict:
    """Record an evaluation score for a trace/execution.

    Calls POST /api/v1/scores. Typical fields: `trace_id`, `name`, `value`,
    `source`, `metadata`.
    """
    return await _omium_post("/api/v1/scores", body)


@mcp.tool()
async def list_scores(
    trace_id: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> dict:
    """List scores, optionally filtered.

    Calls GET /api/v1/scores.
    """
    params = {k: v for k, v in {
        "trace_id": trace_id, "limit": limit, "offset": offset,
    }.items() if v is not None}
    return await _omium_get("/api/v1/scores", params=params or None)


@mcp.tool()
async def get_scores_stats() -> dict:
    """Aggregate score statistics.

    Calls GET /api/v1/scores/stats.
    """
    return await _omium_get("/api/v1/scores/stats")


# =========================================================================
# Traces (SDK-facing via auth-service)
# =========================================================================

@mcp.tool()
async def ingest_trace(body: dict) -> dict:
    """Ingest a trace payload (SDK-style).

    Calls POST /api/v1/traces/ingest. Body is an OTLP-style trace document.
    """
    return await _omium_post("/api/v1/traces/ingest", body)


@mcp.tool()
async def list_traces(
    limit: int | None = None,
    offset: int | None = None,
    project_id: str | None = None,
    workflow_id: str | None = None,
) -> dict:
    """List traces for the caller's tenant, optionally filtered.

    Calls GET /api/v1/traces.
    """
    params = {k: v for k, v in {
        "limit": limit, "offset": offset,
        "project_id": project_id, "workflow_id": workflow_id,
    }.items() if v is not None}
    return await _omium_get("/api/v1/traces", params=params or None)


@mcp.tool()
async def get_trace(trace_id: str) -> dict:
    """Get a single trace by ID.

    Calls GET /api/v1/traces/<trace_id>.
    """
    return await _omium_get(f"/api/v1/traces/{trace_id}")


@mcp.tool()
async def list_trace_failures() -> dict:
    """List failed traces.

    Calls GET /api/v1/traces/failures.
    """
    return await _omium_get("/api/v1/traces/failures")


@mcp.tool()
async def list_trace_projects() -> dict:
    """List trace projects.

    Calls GET /api/v1/traces/projects.
    """
    return await _omium_get("/api/v1/traces/projects")


# =========================================================================
# Projects
# =========================================================================

@mcp.tool()
async def create_project(body: dict) -> dict:
    """Create a project (CLI-style sync).

    Calls POST /api/v1/projects. Typical fields: `name`, `slug`, `description`,
    `git_url`.
    """
    return await _omium_post("/api/v1/projects", body)


@mcp.tool()
async def list_projects() -> dict:
    """List projects for the caller's tenant.

    Calls GET /api/v1/projects.
    """
    return await _omium_get("/api/v1/projects")


@mcp.tool()
async def connect_project_git(project_id: str, body: dict) -> dict:
    """Attach a git repository to a project.

    Calls POST /api/v1/projects/<project_id>/git/connect. Typical fields:
    `provider`, `repo`, `branch`.
    """
    return await _omium_post(f"/api/v1/projects/{project_id}/git/connect", body)


@mcp.tool()
async def list_project_files(project_id: str) -> dict:
    """List files tracked under a project.

    Calls GET /api/v1/projects/<project_id>/files.
    """
    return await _omium_get(f"/api/v1/projects/{project_id}/files")


@mcp.tool()
async def save_project_file(project_id: str, file_path: str, body: dict) -> dict:
    """Create or update a file inside a project.

    Calls POST /api/v1/projects/<project_id>/files/<file_path>. Body typically
    carries `content` and optional `encoding`/`mode`.
    """
    return await _omium_post(f"/api/v1/projects/{project_id}/files/{file_path}", body)


@mcp.tool()
async def commit_project_git(project_id: str, body: dict) -> dict:
    """Commit tracked project file changes to the attached git repo.

    Calls POST /api/v1/projects/<project_id>/git/commit. Typical fields:
    `message`, `branch`, optional `files`.
    """
    return await _omium_post(f"/api/v1/projects/{project_id}/git/commit", body)


# =========================================================================
# GitHub integration
# =========================================================================

@mcp.tool()
async def github_status() -> dict:
    """GitHub integration status for the tenant.

    Calls GET /api/v1/github/status.
    """
    return await _omium_get("/api/v1/github/status")


@mcp.tool()
async def github_setup(body: dict) -> dict:
    """Configure the GitHub integration.

    Calls POST /api/v1/github/setup. Typical fields: `installation_id`,
    `repo`, `default_branch`.
    """
    return await _omium_post("/api/v1/github/setup", body)


@mcp.tool()
async def github_update_repo(body: dict) -> dict:
    """Update the repo attached to the GitHub integration.

    Calls PATCH /api/v1/github/repo.
    """
    return await _omium_patch("/api/v1/github/repo", body)


@mcp.tool()
async def github_disconnect() -> dict:
    """Disconnect the GitHub integration.

    Calls DELETE /api/v1/github/disconnect.
    """
    return await _omium_delete("/api/v1/github/disconnect")


@mcp.tool()
async def github_create_fix_pr(body: dict) -> dict:
    """Open a PR on GitHub with an Omium-generated fix.

    Calls POST /api/v1/github/create-fix-pr. Typical fields: `execution_id`,
    `title`, `body`, `branch`.
    """
    return await _omium_post("/api/v1/github/create-fix-pr", body)


# =========================================================================
# Recovery orchestrator
# =========================================================================

@mcp.tool()
async def list_recovery_failures() -> dict:
    """List failures seen by the recovery orchestrator.

    Calls GET /api/v1/recovery/failures.
    """
    return await _omium_get("/api/v1/recovery/failures")


@mcp.tool()
async def trigger_recovery(body: dict) -> dict:
    """Trigger a recovery for a failing execution.

    Calls POST /api/v1/recovery/trigger. Typical fields: `execution_id`,
    `strategy`.
    """
    return await _omium_post("/api/v1/recovery/trigger", body)


@mcp.tool()
async def create_recovery_command(body: dict) -> dict:
    """Enqueue a recovery command.

    Calls POST /api/v1/recovery/commands.
    """
    return await _omium_post("/api/v1/recovery/commands", body)


@mcp.tool()
async def list_recovery_commands(
    status: str | None = None,
    execution_id: str | None = None,
    limit: int | None = None,
) -> dict:
    """List recovery commands, optionally filtered.

    Calls GET /api/v1/recovery/commands.
    """
    params = {k: v for k, v in {
        "status": status, "execution_id": execution_id, "limit": limit,
    }.items() if v is not None}
    return await _omium_get("/api/v1/recovery/commands", params=params or None)


@mcp.tool()
async def get_recovery_command(command_id: str) -> dict:
    """Get a recovery command by ID.

    Calls GET /api/v1/recovery/commands/<command_id>.
    """
    return await _omium_get(f"/api/v1/recovery/commands/{command_id}")


@mcp.tool()
async def update_recovery_command_status(command_id: str, body: dict) -> dict:
    """Update a recovery command's status.

    Calls POST /api/v1/recovery/commands/<command_id>/status. Body typically
    carries `status` and optional `result`/`error`.
    """
    return await _omium_post(f"/api/v1/recovery/commands/{command_id}/status", body)


@mcp.tool()
async def redeliver_recovery_command(command_id: str) -> dict:
    """Redeliver a recovery command to its target.

    Calls POST /api/v1/recovery/commands/<command_id>/redeliver.
    """
    return await _omium_post(f"/api/v1/recovery/commands/{command_id}/redeliver")


# =========================================================================
# Replay
# =========================================================================

@mcp.tool()
async def get_replay_state(execution_id: str) -> dict:
    """Get the replay-ready state for an execution.

    Calls GET /api/v1/replay/<execution_id>/state.
    """
    return await _omium_get(f"/api/v1/replay/{execution_id}/state")


@mcp.tool()
async def get_replay_step(execution_id: str, step_index: int) -> dict:
    """Get a single step from the replay timeline.

    Calls GET /api/v1/replay/<execution_id>/steps/<step_index>.
    """
    return await _omium_get(f"/api/v1/replay/{execution_id}/steps/{step_index}")


@mcp.tool()
async def get_replay_consensus(execution_id: str) -> dict:
    """Get consensus-coordinator output for a replay.

    Calls GET /api/v1/replay/<execution_id>/consensus.
    """
    return await _omium_get(f"/api/v1/replay/{execution_id}/consensus")


@mcp.tool()
async def get_replay_diff(execution_id: str) -> dict:
    """Diff between original and replayed execution.

    Calls GET /api/v1/replay/<execution_id>/diff.
    """
    return await _omium_get(f"/api/v1/replay/{execution_id}/diff")


@mcp.tool()
async def restart_replay(execution_id: str, body: dict | None = None) -> dict:
    """Restart a replay from a checkpoint.

    Calls POST /api/v1/replay/<execution_id>/restart.
    """
    return await _omium_post(f"/api/v1/replay/{execution_id}/restart", body)


# =========================================================================
# Analytics (analytics-engine)
# =========================================================================

@mcp.tool()
async def get_usage_summary() -> dict:
    """Tenant usage summary (executions, cost, tokens).

    Calls GET /api/v1/usage/summary.
    """
    return await _omium_get("/api/v1/usage/summary")


@mcp.tool()
async def get_dashboard_metrics() -> dict:
    """Dashboard landing metrics.

    Calls GET /api/v1/dashboard/metrics.
    """
    return await _omium_get("/api/v1/dashboard/metrics")


@mcp.tool()
async def get_recent_activity() -> dict:
    """Recent activity feed for the tenant.

    Calls GET /api/v1/activity/recent.
    """
    return await _omium_get("/api/v1/activity/recent")


@mcp.tool()
async def get_performance_metrics() -> dict:
    """Aggregate performance metrics.

    Calls GET /api/v1/performance/metrics.
    """
    return await _omium_get("/api/v1/performance/metrics")


@mcp.tool()
async def get_performance_time_series(
    window: str | None = None,
    bucket: str | None = None,
) -> dict:
    """Performance time-series.

    Calls GET /api/v1/performance/time-series.
    """
    params = {k: v for k, v in {"window": window, "bucket": bucket}.items() if v is not None}
    return await _omium_get("/api/v1/performance/time-series", params=params or None)


@mcp.tool()
async def get_performance_agents() -> dict:
    """Per-agent performance breakdown.

    Calls GET /api/v1/performance/agents.
    """
    return await _omium_get("/api/v1/performance/agents")


@mcp.tool()
async def get_workflow_performance(workflow_id: str) -> dict:
    """Performance metrics for a specific workflow.

    Calls GET /api/v1/performance/workflow/<workflow_id>.
    """
    return await _omium_get(f"/api/v1/performance/workflow/{workflow_id}")


@mcp.tool()
async def get_workflow_cost(workflow_id: str) -> dict:
    """Cost breakdown for a specific workflow.

    Calls GET /api/v1/performance/workflow/<workflow_id>/cost.
    """
    return await _omium_get(f"/api/v1/performance/workflow/{workflow_id}/cost")


@mcp.tool()
async def get_system_metrics() -> dict:
    """System-level metrics.

    Calls GET /api/v1/metrics/system.
    """
    return await _omium_get("/api/v1/metrics/system")


# =========================================================================
# Audit logger
# =========================================================================

@mcp.tool()
async def create_audit_log(body: dict) -> dict:
    """Record an audit log entry.

    Calls POST /api/v1/audit/log. Typical fields: `action`, `resource_type`,
    `resource_id`, `metadata`.
    """
    return await _omium_post("/api/v1/audit/log", body)


@mcp.tool()
async def list_audit_logs(
    limit: int | None = None,
    offset: int | None = None,
    resource_type: str | None = None,
    action: str | None = None,
) -> dict:
    """List audit log entries.

    Calls GET /api/v1/audit/logs.
    """
    params = {k: v for k, v in {
        "limit": limit, "offset": offset,
        "resource_type": resource_type, "action": action,
    }.items() if v is not None}
    return await _omium_get("/api/v1/audit/logs", params=params or None)


@mcp.tool()
async def search_audit_logs(
    query: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> dict:
    """Search audit logs.

    Calls GET /api/v1/audit/logs/search.
    """
    params = {k: v for k, v in {
        "query": query, "limit": limit, "offset": offset,
    }.items() if v is not None}
    return await _omium_get("/api/v1/audit/logs/search", params=params or None)


@mcp.tool()
async def get_audit_log(log_id: str) -> dict:
    """Get a single audit log entry.

    Calls GET /api/v1/audit/logs/<log_id>.
    """
    return await _omium_get(f"/api/v1/audit/logs/{log_id}")


# =========================================================================
# Billing
# =========================================================================

@mcp.tool()
async def get_billing_balance() -> dict:
    """Current credit balance.

    Calls GET /api/v1/billing/balance.
    """
    return await _omium_get("/api/v1/billing/balance")


@mcp.tool()
async def get_billing_usage() -> dict:
    """Billing-period usage summary.

    Calls GET /api/v1/billing/usage.
    """
    return await _omium_get("/api/v1/billing/usage")


@mcp.tool()
async def create_billing_topup(body: dict) -> dict:
    """Create a credit top-up (direct).

    Calls POST /api/v1/billing/topup. Typical fields: `amount_cents`,
    `currency`.
    """
    return await _omium_post("/api/v1/billing/topup", body)


@mcp.tool()
async def create_billing_topup_checkout(body: dict) -> dict:
    """Create a Stripe checkout session for a top-up.

    Calls POST /api/v1/billing/topup/checkout.
    """
    return await _omium_post("/api/v1/billing/topup/checkout", body)


@mcp.tool()
async def list_billing_transactions(
    limit: int | None = None,
    offset: int | None = None,
) -> dict:
    """List billing transactions.

    Calls GET /api/v1/billing/transactions.
    """
    params = {k: v for k, v in {"limit": limit, "offset": offset}.items() if v is not None}
    return await _omium_get("/api/v1/billing/transactions", params=params or None)


@mcp.tool()
async def create_subscription_checkout(body: dict) -> dict:
    """Create a Stripe checkout for a new subscription.

    Calls POST /api/v1/billing/subscriptions/create-checkout. Typical fields:
    `plan_id`, `return_url`.
    """
    return await _omium_post("/api/v1/billing/subscriptions/create-checkout", body)


@mcp.tool()
async def get_subscription_status() -> dict:
    """Current subscription status.

    Calls GET /api/v1/billing/subscriptions/status.
    """
    return await _omium_get("/api/v1/billing/subscriptions/status")


@mcp.tool()
async def create_subscription_portal(body: dict | None = None) -> dict:
    """Create a Stripe customer-portal session.

    Calls POST /api/v1/billing/subscriptions/portal.
    """
    return await _omium_post("/api/v1/billing/subscriptions/portal", body)


@mcp.tool()
async def cancel_subscription(body: dict | None = None) -> dict:
    """Cancel the current subscription.

    Calls POST /api/v1/billing/subscriptions/cancel.
    """
    return await _omium_post("/api/v1/billing/subscriptions/cancel", body)


@mcp.tool()
async def get_cost_breakdown() -> dict:
    """Cost breakdown by category/workflow.

    Calls GET /api/v1/billing/cost-breakdown.
    """
    return await _omium_get("/api/v1/billing/cost-breakdown")


@mcp.tool()
async def get_usage_details() -> dict:
    """Detailed (line-item) usage for the billing period.

    Calls GET /api/v1/billing/usage-details.
    """
    return await _omium_get("/api/v1/billing/usage-details")


@mcp.tool()
async def get_quotas() -> dict:
    """Quota allocations and current consumption.

    Calls GET /api/v1/billing/quotas.
    """
    return await _omium_get("/api/v1/billing/quotas")


@mcp.tool()
async def estimate_execution_cost(body: dict) -> dict:
    """Pre-flight cost estimate for an execution.

    Calls POST /api/v1/billing/estimate-execution. Typical fields:
    `workflow_id`, `input_data`.
    """
    return await _omium_post("/api/v1/billing/estimate-execution", body)


@mcp.tool()
async def get_billing_forecast() -> dict:
    """Projected end-of-period billing total.

    Calls GET /api/v1/billing/forecast.
    """
    return await _omium_get("/api/v1/billing/forecast")


@mcp.tool()
async def get_billing_recommendations() -> dict:
    """Cost-optimization recommendations.

    Calls GET /api/v1/billing/recommendations.
    """
    return await _omium_get("/api/v1/billing/recommendations")


@mcp.tool()
async def get_cost_analytics() -> dict:
    """Cost analytics payload.

    Calls GET /api/v1/billing/cost-analytics.
    """
    return await _omium_get("/api/v1/billing/cost-analytics")


@mcp.tool()
async def list_billing_alerts() -> dict:
    """Billing alerts (e.g. overrun warnings).

    Calls GET /api/v1/billing/alerts.
    """
    return await _omium_get("/api/v1/billing/alerts")


# =========================================================================
# ASGI wiring
# =========================================================================

app = mcp.streamable_http_app()
app.add_middleware(BearerAuthMiddleware)


if __name__ == "__main__":
    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT)
