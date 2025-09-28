"""WHOOP MCP server with balanced daily insights and flexible querying.

Adds an OAuth proxy so clients authenticate via WHOOP's Authorization Code flow instead of pasting bearer tokens.
"""

from __future__ import annotations

import os
import time
from functools import partial
from typing import Any, Literal, Annotated, Optional, Tuple
from datetime import datetime, timezone

import httpx
from pydantic import Field
from dotenv import load_dotenv

from fastmcp import FastMCP
from fastmcp.server.auth import OAuthProxy
from fastmcp.server.auth.auth import TokenVerifier, AccessToken
from fastmcp.server.dependencies import get_access_token, get_http_request
from utils import collect_paginated, days_ago, isoformat_utc, start_of_day

# Load environment variables from .env file
load_dotenv()

WHOOP_BASE = os.getenv("WHOOP_API_BASE", "https://api.prod.whoop.com/developer")
WHOOP_OAUTH_AUTHZ = "https://api.prod.whoop.com/oauth/oauth2/auth"
WHOOP_OAUTH_TOKEN = "https://api.prod.whoop.com/oauth/oauth2/token"

REQUIRED_SCOPES = [
    "offline",
    "read:profile",
    "read:body_measurement",
    "read:cycles",
    "read:sleep",
    "read:workout",
    "read:recovery"
]


class WhoopTokenVerifier(TokenVerifier):
    """Verifies WHOOP access tokens via a lightweight profile fetch with short-lived caching."""

    def __init__(
        self,
        cache_ttl_s: int = 300,
        required_scopes: Optional[list[str]] = None,
        client_id_hint: Optional[str] = None,
    ) -> None:
        super().__init__(required_scopes=required_scopes)
        self._cache_ttl_s = cache_ttl_s
        self._cache: dict[str, Tuple[float, dict[str, Any]]] = {}
        self._client_id_hint = client_id_hint or os.getenv("WHOOP_CLIENT_ID") or "whoop"

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        now = time.time()
        if token in self._cache:
            expires_at, _claims = self._cache[token]
            if now < expires_at:
                return AccessToken(token=token, client_id=self._client_id_hint, scopes=self.required_scopes)

        url = f"{WHOOP_BASE}/v2/user/profile/basic"
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {token}"})

        if response.status_code != 200:
            return None

        data = response.json() if response.content else {}
        self._cache[token] = (now + self._cache_ttl_s, data)
        return AccessToken(token=token, client_id=self._client_id_hint, scopes=self.required_scopes)


auth = OAuthProxy(
    upstream_authorization_endpoint=WHOOP_OAUTH_AUTHZ,
    upstream_token_endpoint=WHOOP_OAUTH_TOKEN,
    upstream_client_id=os.environ["WHOOP_CLIENT_ID"],
    upstream_client_secret=os.environ["WHOOP_CLIENT_SECRET"],
    token_endpoint_auth_method="client_secret_post",
    forward_pkce=True,
    token_verifier=WhoopTokenVerifier(
        required_scopes=REQUIRED_SCOPES,
        client_id_hint=os.environ.get("WHOOP_CLIENT_ID"),
    ),
    valid_scopes=REQUIRED_SCOPES,
    base_url=os.environ["PUBLIC_BASE_URL"],
    redirect_path=os.getenv("OAUTH_REDIRECT_PATH", "/auth/callback"),
)


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


def _bearer_for_upstream() -> str:
    """Prefer the validated OAuth token, fall back to raw Authorization header for dev paths."""

    token = get_access_token()
    if token and token.token:
        return token.token

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
    auth=auth,
)


async def _dispatch_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    token = _bearer_for_upstream()
    client = WhoopClient(token)
    try:
        return await client.get(path, params=params)
    finally:
        await client.aclose()


# ---------- Main Tools ----------

@mcp.tool
async def get_user_profile() -> dict[str, Any]:
    """Return WHOOP basic user profile (requires read:profile scope)."""
    return await _dispatch_get("/v2/user/profile/basic")


@mcp.tool
async def get_daily_update() -> dict[str, Any]:
    """Return raw records for latest recovery, last completed sleep, recent cycles, and today's workouts (UTC)."""
    
    # Get latest recovery
    now = isoformat_utc(datetime.now(timezone.utc))
    recovery_data = await _dispatch_get("/v2/recovery", {"limit": 1, "end": now})
    recovery = (recovery_data.get("records") or [{}])[0]
    
    # Get last completed sleep
    sleep_data = await _dispatch_get("/v2/activity/sleep", {"limit": 1, "end": now})
    sleep = (sleep_data.get("records") or [{}])[0]
    
    # Get recent cycles (last 2 days)
    cycles_start = days_ago(2)
    cycles_data = await _dispatch_get("/v2/cycle", {"start": cycles_start, "end": now, "limit": 10})
    cycles = cycles_data.get("records", [])
    
    # Get today's workouts
    today_start = start_of_day()
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
        start = days_ago(days_back or 7)
    
    if end_date:
        end = end_date if "T" in end_date else f"{end_date}T23:59:59Z"
    else:
        end = isoformat_utc(datetime.now(timezone.utc))
    
    result: dict[str, Any] = {
        "window": {"start": start, "end": end}
    }
    
    # Fetch requested data
    if activity_type in ("all", "sleep"):
        sleeps = await collect_paginated(
            partial(_dispatch_get, "/v2/activity/sleep"),
            {"start": start, "end": end, "limit": 25},
        )
        result["sleep"] = sleeps
    
    if activity_type in ("all", "workouts"):
        workouts = await collect_paginated(
            partial(_dispatch_get, "/v2/activity/workout"),
            {"start": start, "end": end, "limit": 25},
        )
        result["workouts"] = workouts
    
    if activity_type in ("all", "recovery"):
        recoveries = await collect_paginated(
            partial(_dispatch_get, "/v2/recovery"),
            {"start": start, "end": end, "limit": 25},
        )
        result["recovery"] = recoveries
    
    if activity_type in ("all", "cycles"):
        cycles = await collect_paginated(
            partial(_dispatch_get, "/v2/cycle"),
            {"start": start, "end": end, "limit": 25},
        )
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
        current_start = start_of_day(days_since_monday)
        current_end = isoformat_utc(now)
        
        # Previous week (same days)
        prev_start = start_of_day(days_since_monday + 7)
        prev_end = days_ago(7)
    else:  # month
        # Current month so far
        current_start = f"{now.year}-{now.month:02d}-01T00:00:00Z"
        current_end = isoformat_utc(now)
        
        # Same days of previous month
        prev_month = now.month - 1 if now.month > 1 else 12
        prev_year = now.year if now.month > 1 else now.year - 1
        prev_start = f"{prev_year}-{prev_month:02d}-01T00:00:00Z"
        prev_end = f"{prev_year}-{prev_month:02d}-{now.day:02d}T23:59:59Z"
    
    # Fetch data for both periods
    current_recovery = await collect_paginated(
        partial(_dispatch_get, "/v2/recovery"),
        {"start": current_start, "end": current_end, "limit": 25},
    )
    current_sleep = await collect_paginated(
        partial(_dispatch_get, "/v2/activity/sleep"),
        {"start": current_start, "end": current_end, "limit": 25},
    )
    current_cycles = await collect_paginated(
        partial(_dispatch_get, "/v2/cycle"),
        {"start": current_start, "end": current_end, "limit": 25},
    )
    current_workouts = await collect_paginated(
        partial(_dispatch_get, "/v2/activity/workout"),
        {"start": current_start, "end": current_end, "limit": 25},
    )

    previous_recovery = await collect_paginated(
        partial(_dispatch_get, "/v2/recovery"),
        {"start": prev_start, "end": prev_end, "limit": 25},
    )
    previous_sleep = await collect_paginated(
        partial(_dispatch_get, "/v2/activity/sleep"),
        {"start": prev_start, "end": prev_end, "limit": 25},
    )
    previous_cycles = await collect_paginated(
        partial(_dispatch_get, "/v2/cycle"),
        {"start": prev_start, "end": prev_end, "limit": 25},
    )
    previous_workouts = await collect_paginated(
        partial(_dispatch_get, "/v2/activity/workout"),
        {"start": prev_start, "end": prev_end, "limit": 25},
    )
    
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
