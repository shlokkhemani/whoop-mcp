"""WHOOP MCP server exposing v2 endpoints via FastMCP.

Assumes clients always provide an Authorization header with a Bearer token.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from pydantic import BaseModel, Field

from fastmcp import FastMCP
from fastmcp.http import current_request

WHOOP_BASE = os.getenv("WHOOP_API_BASE", "https://api.prod.whoop.com/developer")


class WindowParams(BaseModel):
    start: str | None = Field(None, description="ISO 8601 start datetime (inclusive)")
    end: str | None = Field(None, description="ISO 8601 end datetime (exclusive, defaults to now)")
    limit: int = Field(10, ge=1, le=25, description="Max 25 per WHOOP request")
    next_token: str | None = Field(None, description="WHOOP next_token for pagination")


class ByIdParams(BaseModel):
    id: str = Field(..., description="UUID for sleep/workout; integer for cycle in v2 examples")


class WhoopClient:
    """Lightweight HTTP client wrapper for WHOOP API calls."""

    def __init__(self, access_token: str, timeout_s: float = 30.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=WHOOP_BASE,
            timeout=timeout_s,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query: dict[str, Any] = {}
        if params:
            query.update(params)
        if "next_token" in query and query["next_token"] is not None:
            query["nextToken"] = query.pop("next_token")

        response = await self._client.get(path, params=query)
        if response.status_code == 429:
            reset = response.headers.get("X-RateLimit-Reset")
            raise RuntimeError(
                f"WHOOP rate limit hit; retry after {reset or 'a short delay'} seconds",
            )
        response.raise_for_status()
        if response.content and "application/json" in response.headers.get("content-type", ""):
            return response.json()
        return {}

    async def aclose(self) -> None:
        await self._client.aclose()


def _resolve_bearer_token() -> str:
    request = current_request.get()
    auth_header = request.headers["authorization"]
    return auth_header.split(" ", 1)[1]


mcp = FastMCP(
    name="whoop-mcp",
    instructions=(
        "This server surfaces WHOOP v2 endpoints as MCP tools. "
        "All timestamps returned by WHOOP are in UTC format. Please convert to local time before displaying to the user."
        "Use list_* tools with start/end windows, limit<=25, and next_token to paginate. "
        "For details, use get_* tools by id."
    ),
)


async def _dispatch_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    token = _resolve_bearer_token()
    client = WhoopClient(token)
    try:
        return await client.get(path, params=params)
    finally:
        await client.aclose()


@mcp.tool
async def get_user_profile() -> dict[str, Any]:
    """Return WHOOP basic user profile (requires read:profile scope)."""
    return await _dispatch_get("/v2/user/profile/basic")


@mcp.tool
async def get_body_measurements() -> dict[str, Any]:
    """Return WHOOP body measurements (requires read:body_measurement scope)."""
    return await _dispatch_get("/v2/user/measurement/body")


@mcp.tool
async def list_cycles(params: WindowParams) -> dict[str, Any]:
    """List cycles with pagination (requires read:cycles scope)."""
    return await _dispatch_get(
        "/v2/cycle",
        params={
            "start": params.start,
            "end": params.end,
            "limit": params.limit,
            "next_token": params.next_token,
        },
    )


@mcp.tool
async def get_cycle(params: ByIdParams) -> dict[str, Any]:
    """Get a cycle by id (requires read:cycles scope)."""
    return await _dispatch_get(f"/v2/cycle/{params.id}")


@mcp.tool
async def get_sleep_for_cycle(params: ByIdParams) -> dict[str, Any]:
    """Get the sleep record associated with a cycle (requires read:cycles scope)."""
    return await _dispatch_get(f"/v2/cycle/{params.id}/sleep")


@mcp.tool
async def list_sleep(params: WindowParams) -> dict[str, Any]:
    """List sleeps with pagination (requires read:sleep scope)."""
    return await _dispatch_get(
        "/v2/activity/sleep",
        params={
            "start": params.start,
            "end": params.end,
            "limit": params.limit,
            "next_token": params.next_token,
        },
    )


@mcp.tool
async def get_sleep(params: ByIdParams) -> dict[str, Any]:
    """Get one sleep by UUID (requires read:sleep scope)."""
    return await _dispatch_get(f"/v2/activity/sleep/{params.id}")


@mcp.tool
async def list_workouts(params: WindowParams) -> dict[str, Any]:
    """List workouts with pagination (requires read:workout scope)."""
    return await _dispatch_get(
        "/v2/activity/workout",
        params={
            "start": params.start,
            "end": params.end,
            "limit": params.limit,
            "next_token": params.next_token,
        },
    )


@mcp.tool
async def get_workout(params: ByIdParams) -> dict[str, Any]:
    """Get one workout by UUID (requires read:workout scope)."""
    return await _dispatch_get(f"/v2/activity/workout/{params.id}")


if __name__ == "__main__":
    # Run over HTTP so external clients can connect.
    mcp.run(transport="http", host="0.0.0.0", port=int(os.getenv("PORT", "9000")))
