"""HTTP helpers — every tool calls Kong through one of these."""

from __future__ import annotations

import httpx

from .auth import get_api_key
from .config import OMIUM_API_BASE


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


async def omium_get(path: str, params: dict | None = None, timeout: float = 15.0) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(
            f"{OMIUM_API_BASE}{path}",
            headers={"X-API-Key": get_api_key()},
            params=params,
        )
        return _parse(r)


async def omium_post(
    path: str,
    json_body: dict | list | None = None,
    params: dict | None = None,
    timeout: float = 60.0,
) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            f"{OMIUM_API_BASE}{path}",
            headers={"X-API-Key": get_api_key(), "Content-Type": "application/json"},
            json=json_body if json_body is not None else {},
            params=params,
        )
        return _parse(r)


async def omium_patch(
    path: str,
    json_body: dict | None = None,
    params: dict | None = None,
    timeout: float = 30.0,
) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.patch(
            f"{OMIUM_API_BASE}{path}",
            headers={"X-API-Key": get_api_key(), "Content-Type": "application/json"},
            json=json_body,
            params=params,
        )
        return _parse(r)


async def omium_delete(path: str, params: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.delete(
            f"{OMIUM_API_BASE}{path}",
            headers={"X-API-Key": get_api_key()},
            params=params,
        )
        return _parse(r)
