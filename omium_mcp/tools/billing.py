"""Billing — balance, subscriptions, cost analytics."""

from ..http import omium_get, omium_post
from ..mcp_instance import mcp


@mcp.tool()
async def get_billing_balance() -> dict:
    """Current credit balance.

    Calls GET /api/v1/billing/balance.
    """
    return await omium_get("/api/v1/billing/balance")


@mcp.tool()
async def get_billing_usage() -> dict:
    """Billing-period usage summary.

    Calls GET /api/v1/billing/usage.
    """
    return await omium_get("/api/v1/billing/usage")


@mcp.tool()
async def create_billing_topup(body: dict) -> dict:
    """Create a credit top-up (direct).

    Calls POST /api/v1/billing/topup. Required body: `amount_cents` (NOT
    `amount`; min 1000 = $10). Optional: `currency`.
    """
    return await omium_post("/api/v1/billing/topup", body)


@mcp.tool()
async def create_billing_topup_checkout(body: dict) -> dict:
    """Create a Stripe checkout session for a top-up.

    Calls POST /api/v1/billing/topup/checkout. Required body: `amount_cents`
    (NOT `amount`).
    """
    return await omium_post("/api/v1/billing/topup/checkout", body)


@mcp.tool()
async def list_billing_transactions(
    limit: int | None = None,
    offset: int | None = None,
) -> dict:
    """List billing transactions.

    Calls GET /api/v1/billing/transactions.
    """
    params = {k: v for k, v in {"limit": limit, "offset": offset}.items() if v is not None}
    return await omium_get("/api/v1/billing/transactions", params=params or None)


@mcp.tool()
async def create_subscription_checkout(body: dict) -> dict:
    """Create a Stripe checkout for a new subscription.

    Calls POST /api/v1/billing/subscriptions/create-checkout. Required body:
    `plan_id` — one of `developer`, `pro`, `enterprise`, `developer_annual`,
    `pro_annual`, `enterprise_annual`.
    """
    return await omium_post("/api/v1/billing/subscriptions/create-checkout", body)


@mcp.tool()
async def get_subscription_status() -> dict:
    """Current subscription status.

    Calls GET /api/v1/billing/subscriptions/status.
    """
    return await omium_get("/api/v1/billing/subscriptions/status")


@mcp.tool()
async def create_subscription_portal(body: dict | None = None) -> dict:
    """Create a Stripe customer-portal session.

    Calls POST /api/v1/billing/subscriptions/portal.
    """
    return await omium_post("/api/v1/billing/subscriptions/portal", body)


@mcp.tool()
async def cancel_subscription(body: dict | None = None) -> dict:
    """Cancel the current subscription.

    Calls POST /api/v1/billing/subscriptions/cancel.
    """
    return await omium_post("/api/v1/billing/subscriptions/cancel", body)


@mcp.tool()
async def get_cost_breakdown() -> dict:
    """Cost breakdown by category/workflow.

    Calls GET /api/v1/billing/cost-breakdown.
    """
    return await omium_get("/api/v1/billing/cost-breakdown")


@mcp.tool()
async def get_usage_details() -> dict:
    """Detailed (line-item) usage for the billing period.

    Calls GET /api/v1/billing/usage-details.
    """
    return await omium_get("/api/v1/billing/usage-details")


@mcp.tool()
async def get_quotas() -> dict:
    """Quota allocations and current consumption.

    Calls GET /api/v1/billing/quotas.
    """
    return await omium_get("/api/v1/billing/quotas")


@mcp.tool()
async def estimate_execution_cost(body: dict) -> dict:
    """Pre-flight cost estimate for an execution.

    Calls POST /api/v1/billing/estimate-execution. Typical fields:
    `workflow_id`, `input_data`.
    """
    return await omium_post("/api/v1/billing/estimate-execution", body)


@mcp.tool()
async def get_billing_forecast() -> dict:
    """Projected end-of-period billing total.

    Calls GET /api/v1/billing/forecast.
    """
    return await omium_get("/api/v1/billing/forecast")


@mcp.tool()
async def get_billing_recommendations() -> dict:
    """Cost-optimization recommendations.

    Calls GET /api/v1/billing/recommendations.
    """
    return await omium_get("/api/v1/billing/recommendations")


@mcp.tool()
async def get_cost_analytics() -> dict:
    """Cost analytics payload.

    Calls GET /api/v1/billing/cost-analytics.
    """
    return await omium_get("/api/v1/billing/cost-analytics")


@mcp.tool()
async def list_billing_alerts() -> dict:
    """Billing alerts (e.g. overrun warnings).

    Calls GET /api/v1/billing/alerts.
    """
    return await omium_get("/api/v1/billing/alerts")
