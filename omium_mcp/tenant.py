"""Tenant slug resolver — used by `create_execution` to default agent_id."""

from __future__ import annotations

import re

import httpx

from .auth import get_api_key
from .config import OMIUM_API_BASE

_cache: dict[str, str] = {}


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "unknown"


async def resolve_tenant_slug() -> str:
    """Return a trace-friendly slug for the current request's tenant.

    Looks up the bearer token's tenant via GET /api/v1/api-keys/verify once,
    then serves from an in-process cache.
    """
    k = get_api_key()
    cached = _cache.get(k)
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
    _cache[k] = slug
    return slug
