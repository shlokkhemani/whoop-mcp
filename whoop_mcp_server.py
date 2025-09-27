"""WHOOP MCP server with balanced daily insights and flexible querying.

Provides both quick daily readiness checks and detailed historical analysis.
"""

from __future__ import annotations

import os
from typing import Any, Literal, Annotated
from datetime import datetime, timedelta, timezone

import httpx
from pydantic import Field

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_request

WHOOP_BASE = os.getenv("WHOOP_API_BASE", "https://api.prod.whoop.com/developer")


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
    request = get_http_request()
    auth_header = request.headers.get("authorization")
    if not auth_header:
        raise RuntimeError("Authorization header missing from request.")
    return auth_header.split(" ", 1)[1]


mcp = FastMCP(
    name="whoop-mcp",
    instructions=(
        "WHOOP raw data bundles and activity queries. "
        "All timestamps are UTC; convert in the client based on the user's timezone. "
        "Use get_daily_update for a daily update and get_activities for windowed records."
    ),
)


async def _dispatch_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    token = _resolve_bearer_token()
    client = WhoopClient(token)
    try:
        return await client.get(path, params=params)
    finally:
        await client.aclose()


# ---------- Utility functions ----------
def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _days_ago(days: int) -> str:
    """Return ISO timestamp for N days ago from now."""
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return _iso(dt)


def _start_of_day(days_ago: int = 0) -> str:
    """Return ISO timestamp for start of day (UTC midnight) N days ago."""
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    start = datetime(dt.year, dt.month, dt.day, 0, 0, 0, tzinfo=timezone.utc)
    return _iso(start)


async def _collect_all(path: str, params: dict[str, Any], max_pages: int = 10) -> list[dict[str, Any]]:
    """Collect all paginated results up to max_pages."""
    records: list[dict[str, Any]] = []
    next_token: str | None = None
    for _ in range(max_pages):
        qp = dict(params)
        if next_token:
            qp["next_token"] = next_token
        data = await _dispatch_get(path, qp)
        records.extend(data.get("records", []))
        next_token = data.get("next_token")
        if not next_token:
            break
    return records


# ---------- Main Tools ----------

@mcp.tool
async def get_daily_update() -> dict[str, Any]:
    """Return raw records for latest recovery, last completed sleep, recent cycles, and today's workouts (UTC)."""
    
    # Get latest recovery
    now = _iso(datetime.now(timezone.utc))
    recovery_data = await _dispatch_get("/v2/recovery", {"limit": 1, "end": now})
    recovery = (recovery_data.get("records") or [{}])[0]
    
    # Get last completed sleep
    sleep_data = await _dispatch_get("/v2/activity/sleep", {"limit": 1, "end": now})
    sleep = (sleep_data.get("records") or [{}])[0]
    
    # Get recent cycles (last 2 days)
    cycles_start = _days_ago(2)
    cycles_data = await _dispatch_get("/v2/cycle", {"start": cycles_start, "end": now, "limit": 10})
    cycles = cycles_data.get("records", [])
    
    # Get today's workouts
    today_start = _start_of_day(0)
    workouts_data = await _dispatch_get("/v2/activity/workout", {"start": today_start, "end": now, "limit": 10})
    workouts = workouts_data.get("records", [])
    
    return {
        "recovery": recovery,
        "sleep": sleep,
        "recent_cycles": cycles,
        "today_workouts": workouts,
        "window": {
            "today_start": today_start,
            "now": now,
            "cycles_start": cycles_start
        }
    }


@mcp.tool
async def get_activities(
    activity_type: Annotated[
        Literal["all", "sleep", "workouts", "recovery", "cycles"],
        Field(description="Type of activity to retrieve")
    ] = "all",
    days_back: Annotated[
        int | None,
        Field(description="Number of days to look back (default: 7)")
    ] = 7,
    start_date: Annotated[
        str | None,
        Field(description="ISO date string for custom start (overrides days_back)")
    ] = None,
    end_date: Annotated[
        str | None,
        Field(description="ISO date string for custom end (default: now)")
    ] = None
) -> dict[str, Any]:
    """Query any WHOOP data over flexible time periods.
    
    Use days_back for relative queries or start_date/end_date for specific periods."""
    
    # Determine time window
    if start_date:
        start = start_date if "T" in start_date else f"{start_date}T00:00:00Z"
    else:
        start = _days_ago(days_back or 7)
    
    if end_date:
        end = end_date if "T" in end_date else f"{end_date}T23:59:59Z"
    else:
        end = _iso(datetime.now(timezone.utc))
    
    result: dict[str, Any] = {
        "window": {"start": start, "end": end}
    }
    
    # Fetch requested data
    if activity_type in ("all", "sleep"):
        sleeps = await _collect_all("/v2/activity/sleep", {"start": start, "end": end, "limit": 25})
        result["sleep"] = sleeps
    
    if activity_type in ("all", "workouts"):
        workouts = await _collect_all("/v2/activity/workout", {"start": start, "end": end, "limit": 25})
        result["workouts"] = workouts
    
    if activity_type in ("all", "recovery"):
        recoveries = await _collect_all("/v2/recovery", {"start": start, "end": end, "limit": 25})
        result["recovery"] = recoveries
    
    if activity_type in ("all", "cycles"):
        cycles = await _collect_all("/v2/cycle", {"start": start, "end": end, "limit": 25})
        result["cycles"] = cycles
    
    return result


@mcp.tool
async def get_trends(
    period: Annotated[
        Literal["week", "month"],
        Field(description="Period to analyze")
    ] = "week"
) -> dict[str, Any]:
    """Analyze trends by comparing current period metrics to previous period.
    
    Returns raw data for both periods to enable trend analysis."""
    
    now = datetime.now(timezone.utc)
    
    if period == "week":
        # Current week (Monday to now)
        days_since_monday = now.weekday()
        current_start = _start_of_day(days_since_monday)
        current_end = _iso(now)
        
        # Previous week (same days)
        prev_start = _start_of_day(days_since_monday + 7)
        prev_end = _days_ago(7)
    else:  # month
        # Current month so far
        current_start = f"{now.year}-{now.month:02d}-01T00:00:00Z"
        current_end = _iso(now)
        
        # Same days of previous month
        prev_month = now.month - 1 if now.month > 1 else 12
        prev_year = now.year if now.month > 1 else now.year - 1
        prev_start = f"{prev_year}-{prev_month:02d}-01T00:00:00Z"
        prev_end = f"{prev_year}-{prev_month:02d}-{now.day:02d}T23:59:59Z"
    
    # Fetch data for both periods
    current_recovery = await _collect_all("/v2/recovery", {"start": current_start, "end": current_end, "limit": 25})
    current_sleep = await _collect_all("/v2/activity/sleep", {"start": current_start, "end": current_end, "limit": 25})
    current_cycles = await _collect_all("/v2/cycle", {"start": current_start, "end": current_end, "limit": 25})
    current_workouts = await _collect_all("/v2/activity/workout", {"start": current_start, "end": current_end, "limit": 25})
    
    previous_recovery = await _collect_all("/v2/recovery", {"start": prev_start, "end": prev_end, "limit": 25})
    previous_sleep = await _collect_all("/v2/activity/sleep", {"start": prev_start, "end": prev_end, "limit": 25})
    previous_cycles = await _collect_all("/v2/cycle", {"start": prev_start, "end": prev_end, "limit": 25})
    previous_workouts = await _collect_all("/v2/activity/workout", {"start": prev_start, "end": prev_end, "limit": 25})
    
    return {
        "period": period,
        "current": {
            "window": {"start": current_start, "end": current_end},
            "recovery": current_recovery,
            "sleep": current_sleep,
            "cycles": current_cycles,
            "workouts": current_workouts
        },
        "previous": {
            "window": {"start": prev_start, "end": prev_end},
            "recovery": previous_recovery,
            "sleep": previous_sleep,
            "cycles": previous_cycles,
            "workouts": previous_workouts
        }
    }


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=int(os.getenv("PORT", "9000")))
