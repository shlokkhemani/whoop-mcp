"""Utility helpers shared by WHOOP MCP tools."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Mapping, MutableMapping, Sequence

JsonDict = Dict[str, Any]
FetchFn = Callable[[MutableMapping[str, Any]], Awaitable[JsonDict]]


def isoformat_utc(dt: datetime) -> str:
    """Return an ISO 8601 string in UTC with trailing Z."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def days_ago(days: int) -> str:
    """UTC timestamp for now minus `days` days."""
    return isoformat_utc(datetime.now(timezone.utc) - timedelta(days=days))


def start_of_day(days_back: int = 0) -> str:
    """UTC midnight for the current day minus `days_back` days."""
    now = datetime.now(timezone.utc)
    target_day = (now - timedelta(days=days_back)).date()
    midnight = datetime.combine(target_day, datetime.min.time(), tzinfo=timezone.utc)
    return isoformat_utc(midnight)


async def collect_paginated(
    fetch: FetchFn,
    base_params: Mapping[str, Any] | None = None,
) -> List[JsonDict]:
    """Fetch WHOOP pages until pagination tokens run out."""
    params = dict(base_params or {})
    items: List[JsonDict] = []
    next_token: Any | None = None

    while True:
        call_params = dict(params)
        if next_token:
            call_params["next_token"] = next_token

        data = await fetch(call_params)
        records = data.get("records")
        if isinstance(records, Sequence):
            # WHOOP returns a list of dicts; accept any sequence
            items.extend(records)  # type: ignore[arg-type]

        next_token = data.get("next_token") or data.get("nextToken")
        if not next_token:
            break

    return items

