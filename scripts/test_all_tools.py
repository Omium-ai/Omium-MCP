"""
Round-trip every MCP tool against the running omium-mcp container.

Categorizes each tool into one of:
  PASS              — MCP reached Kong and the upstream service returned 2xx.
  BACKEND_ERROR     — MCP reached Kong/service; upstream returned a non-2xx
                      (4xx validation, 5xx bug, etc.). MCP layer itself is fine.
  MCP_OR_ROUTING    — Kong returned "no Route matched" (route missing) OR
                      MCP-side failure (unexpected exception, wrong shape).
  SKIPPED           — Destructive ops intentionally not tested.

Writes a JSON report to scripts/test_all_tools_report.json and prints a summary.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

API_KEY = "omium_De5g-pMx78IZ49IkQBnRQXrRFEIphEXy3w39gcYrCv4"  # Alice / Acme Corp
MCP_URL = "http://localhost:9100/mcp"
FAKE_UUID = "00000000-0000-0000-0000-000000000001"
REPORT_PATH = Path(__file__).parent / "test_all_tools_report.json"

# Destructive writes we deliberately don't run.
DESTRUCTIVE = {
    "delete_execution",
    "update_execution_status",
    "execute_execution",
    "replay_execution",
    "rollback_execution",
    "apply_fix_to_execution",
    "github_disconnect",
    "cancel_subscription",
    "update_recovery_command_status",
    "redeliver_recovery_command",
}


def _parse_error(text: str) -> tuple[str, int | None, str]:
    """Return (category, status_code, detail) for a tool error text."""
    m = re.search(r"Omium API \w+ (\S+) -> (\d+):\s*(.*)", text, re.DOTALL)
    if not m:
        return ("MCP_OR_ROUTING", None, text[:500])
    path = m.group(1)
    status = int(m.group(2))
    body = m.group(3).strip()
    low = body.lower()
    if status == 404 and ("no route matched" in low or "no routes matched" in low):
        return ("MCP_OR_ROUTING", status, f"Kong says no route for {path}")
    return ("BACKEND_ERROR", status, body[:400])


async def _call(session: ClientSession, name: str, args: dict | None) -> dict:
    try:
        res = await session.call_tool(name, args or {})
    except Exception as e:
        return {"category": "MCP_OR_ROUTING", "detail": f"call_tool raised: {e!r}"}

    if res.isError:
        text = ""
        for c in res.content:
            if hasattr(c, "text"):
                text += c.text
        cat, status, detail = _parse_error(text)
        return {"category": cat, "status": status, "detail": detail}

    # Success
    text = ""
    for c in res.content:
        if hasattr(c, "text"):
            text += c.text
    return {"category": "PASS", "preview": text[:200]}


async def _get_id(session: ClientSession, tool: str, path: str) -> str | None:
    """Call a list tool, walk a dotted path to pull the first ID."""
    r = await session.call_tool(tool, {})
    if r.isError:
        return None
    try:
        data = json.loads(r.content[0].text)
    except Exception:
        return None
    cur: Any = data
    for part in path.split("."):
        if isinstance(cur, list):
            if not cur:
                return None
            cur = cur[0]
        if isinstance(cur, dict):
            cur = cur.get(part)
        if cur is None:
            return None
    return str(cur) if cur else None


async def main() -> None:
    headers = {"Authorization": f"Bearer {API_KEY}"}
    async with streamablehttp_client(MCP_URL, headers=headers) as (r, w, _):
        async with ClientSession(r, w) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            print(f"MCP exposes {len(tools)} tools")

            # Pre-fetch real IDs so ID-requiring tools get a fair shot.
            wf = await _get_id(session, "list_workflows", "workflows.id") \
                or await _get_id(session, "list_workflows", "0.id") \
                or FAKE_UUID
            ex = await _get_id(session, "list_executions", "executions.id") \
                or await _get_id(session, "list_executions", "0.id") \
                or FAKE_UUID
            ck = await _get_id(session, "list_all_checkpoints", "checkpoints.id") \
                or await _get_id(session, "list_all_checkpoints", "0.id") \
                or FAKE_UUID
            pr = await _get_id(session, "list_projects", "projects.id") \
                or await _get_id(session, "list_projects", "0.id") \
                or FAKE_UUID
            tr = await _get_id(session, "list_traces", "traces.id") \
                or await _get_id(session, "list_traces", "0.id") \
                or FAKE_UUID
            rc = await _get_id(session, "list_recovery_commands", "commands.id") \
                or await _get_id(session, "list_recovery_commands", "0.id") \
                or FAKE_UUID
            al = await _get_id(session, "list_audit_logs", "logs.id") \
                or await _get_id(session, "list_audit_logs", "0.id") \
                or FAKE_UUID

            print(f"IDs: workflow={wf[:8]} exec={ex[:8]} ckpt={ck[:8]} "
                  f"proj={pr[:8]} trace={tr[:8]} recov={rc[:8]} audit={al[:8]}")

            plan: list[tuple[str, dict | None]] = [
                # Identity
                ("verify_api_key", None),

                # Workflows
                ("list_workflows", None),
                ("get_workflows", {"workflow_id": wf}),
                ("list_workflow_versions", {"workflow_id": wf}),

                # Executions
                ("list_executions", None),
                ("get_execution", {"execution_id": ex}),
                ("list_checkpoints", {"execution_id": ex}),
                ("list_live_executions", None),
                ("create_execution", {"workflow_id": wf, "input_data": {"test": True}}),
                ("compare_executions", {"body": {"execution_id_a": ex, "execution_id_b": ex}}),
                ("get_apply_to_repo_payload", {"execution_id": ex}),

                # Checkpoints
                ("list_all_checkpoints", None),
                ("get_checkpoint", {"checkpoint_id": ck}),
                ("create_checkpoint", {"body": {"execution_id": ex, "step_index": 0, "state": {}}}),

                # Failures
                ("list_failures", None),
                ("get_failures_stats", None),
                ("get_failures_time_series", None),
                ("create_failure_event", {"body": {"execution_id": ex, "error_type": "mcp-smoke"}}),

                # Observability
                ("get_observability_metrics", None),
                ("get_observability_metrics_summary", None),
                ("get_observability_metrics_prometheus", None),
                ("list_observability_traces", None),
                ("get_observability_trace", {"execution_id": ex}),
                ("get_observability_trace_summary", {"execution_id": ex}),
                ("list_alerts", None),
                ("list_alerts_history", None),
                ("acknowledge_alert", {"condition_name": "mcp-smoke", "body": {}}),
                ("get_observability_dashboard", None),
                ("get_observability_health", None),

                # Scores
                ("list_scores", None),
                ("get_scores_stats", None),
                ("create_score", {"body": {"trace_id": tr, "name": "mcp-smoke", "value": 1.0}}),

                # Traces
                ("list_traces", None),
                ("get_trace", {"trace_id": tr}),
                ("list_trace_failures", None),
                ("list_trace_projects", None),
                ("ingest_trace", {"body": {"traces": []}}),

                # Projects
                ("list_projects", None),
                ("list_project_files", {"project_id": pr}),
                ("create_project", {"body": {"name": "mcp-smoke", "slug": "mcp-smoke"}}),
                ("connect_project_git", {"project_id": pr, "body": {"provider": "github", "repo": "x/y"}}),
                ("save_project_file", {"project_id": pr, "file_path": "README.md", "body": {"content": "x"}}),
                ("commit_project_git", {"project_id": pr, "body": {"message": "smoke"}}),

                # GitHub
                ("github_status", None),
                ("github_setup", {"body": {"installation_id": "0", "repo": "x/y"}}),
                ("github_update_repo", {"body": {"repo": "x/y"}}),
                ("github_create_fix_pr", {"body": {"execution_id": ex}}),

                # Recovery
                ("list_recovery_failures", None),
                ("list_recovery_commands", None),
                ("get_recovery_command", {"command_id": rc}),
                ("trigger_recovery", {"body": {"execution_id": ex}}),
                ("create_recovery_command", {"body": {"execution_id": ex, "command_type": "retry"}}),

                # Replay
                ("get_replay_state", {"execution_id": ex}),
                ("get_replay_step", {"execution_id": ex, "step_index": 0}),
                ("get_replay_consensus", {"execution_id": ex}),
                ("get_replay_diff", {"execution_id": ex}),
                ("restart_replay", {"execution_id": ex, "body": {}}),

                # Analytics
                ("get_usage_summary", None),
                ("get_dashboard_metrics", None),
                ("get_recent_activity", None),
                ("get_performance_metrics", None),
                ("get_performance_time_series", None),
                ("get_performance_agents", None),
                ("get_workflow_performance", {"workflow_id": wf}),
                ("get_workflow_cost", {"workflow_id": wf}),
                ("get_system_metrics", None),

                # Audit
                ("list_audit_logs", None),
                ("search_audit_logs", None),
                ("get_audit_log", {"log_id": al}),
                ("create_audit_log", {"body": {"action": "mcp.smoke", "resource_type": "test", "resource_id": "x"}}),

                # Billing
                ("get_billing_balance", None),
                ("get_billing_usage", None),
                ("list_billing_transactions", None),
                ("get_subscription_status", None),
                ("get_cost_breakdown", None),
                ("get_usage_details", None),
                ("get_quotas", None),
                ("get_billing_forecast", None),
                ("get_billing_recommendations", None),
                ("get_cost_analytics", None),
                ("list_billing_alerts", None),
                ("create_billing_topup", {"body": {"amount_cents": 0}}),
                ("create_billing_topup_checkout", {"body": {"amount_cents": 0}}),
                ("create_subscription_checkout", {"body": {"plan_id": "x"}}),
                ("create_subscription_portal", None),
                ("estimate_execution_cost", {"body": {"workflow_id": wf}}),
            ]

            # Sanity check — plan covers every tool we're not marking destructive.
            planned = {n for n, _ in plan}
            missing = tools - planned - DESTRUCTIVE
            if missing:
                print(f"WARNING — tools not in plan: {sorted(missing)}")
            extra = planned - tools
            if extra:
                print(f"WARNING — plan has unknown tools: {sorted(extra)}")

            results: dict[str, dict] = {}
            for name, args in plan:
                if name in DESTRUCTIVE:
                    results[name] = {"category": "SKIPPED", "detail": "destructive"}
                    continue
                r = await _call(session, name, args)
                results[name] = r
                tag = r["category"]
                extra = r.get("status") or r.get("detail", "")[:60]
                print(f"  [{tag:16}] {name:42} {extra}")

            # Fill destructive skips explicitly
            for name in DESTRUCTIVE:
                results[name] = {"category": "SKIPPED", "detail": "destructive"}

            buckets: dict[str, list[str]] = {
                "PASS": [], "BACKEND_ERROR": [], "MCP_OR_ROUTING": [], "SKIPPED": [],
            }
            for name, r in results.items():
                buckets.setdefault(r["category"], []).append(name)

            print()
            for k, v in buckets.items():
                print(f"{k}: {len(v)}")

            REPORT_PATH.write_text(json.dumps(
                {"buckets": buckets, "details": results}, indent=2, sort_keys=True
            ))
            print(f"\nReport -> {REPORT_PATH}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
