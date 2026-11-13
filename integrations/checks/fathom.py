"""The Fathom integration test (prds/integrations-tab-plan.md § 3; the check
list Doug approved 11-13-26, phase 3 stopping point 1).

Fathom has one feature, so its checks run whether ``fathom_transcripts`` is on
or not. Checks, in order:

1. **Settings present** — the API key.
2. **Read meetings** — one page of ``GET /meetings`` for the last 30 days,
   without summaries or action items. 401/403 failed; unreachable or 5xx
   unknown; an answer with no ``items`` list unknown. Facts: how many meetings
   the key sees on that page, and who recorded them (``recorded_by.email``).

Confirmed against Fathom's OpenAPI reference 11-13-26: the ``X-Api-Key``
header, 401 for a bad key, the response keys ``items`` / ``next_cursor`` /
``limit``, and ``recorded_by`` with ``name`` and ``email``. Fathom has no call
that names the key's own account (plan § 3's proposal, changed), and no
page-size parameter, so the count is of the first page only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from integrations.testing import FAILED, OK, UNKNOWN, Blocked, Check, Context, run_checks

WINDOW_DAYS = 30
RECORDERS_SHOWN = 8


def _default_client(settings: Any) -> Any:
    from core.fathom import DEFAULT_BASE_URL, FathomClient

    return FathomClient(
        settings.fathom_api_key,
        base_url=getattr(settings, "fathom_base_url", "") or DEFAULT_BASE_URL,
        timeout=8,
    )


@dataclass
class Deps:
    client: Callable[[Any], Any] = _default_client


async def _settings(ctx: Context) -> tuple[str, str]:
    if not (ctx.settings.fathom_api_key or "").strip():
        return FAILED, "Not set: the Fathom API key."
    ctx.state["settings_ok"] = True
    return OK, "The Fathom API key is set."


async def _meetings(ctx: Context) -> tuple[str, str]:
    if not ctx.state.get("settings_ok"):
        raise Blocked("Not checked: the API key is not set (check 1).")
    client = ctx.deps.client(ctx.settings)
    since = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    try:
        data = await client.meetings_page(since)
    except Exception as exc:  # noqa: BLE001
        status = getattr(exc, "status_code", None)
        if status in (401, 403):
            return FAILED, f"Fathom refused the API key (HTTP {status}). Check the key in Fathom's settings."
        if status is not None and 400 <= status < 500 and status != 429:
            return FAILED, f"Fathom refused the request: {exc}"
        return UNKNOWN, f"Could not read Fathom's meetings: {exc}"
    items = (data or {}).get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return UNKNOWN, "Fathom answered, but without a list of meetings; its API may have changed."
    recorders = []
    for meeting in items:
        email = ((meeting or {}).get("recorded_by") or {}).get("email")
        if email and email not in recorders:
            recorders.append(str(email))
    more = " or more" if (data or {}).get("next_cursor") else ""
    ctx.fact(f"Meetings seen (last {WINDOW_DAYS} days)", f"{len(items)}{more}")
    if recorders:
        shown = ", ".join(recorders[:RECORDERS_SHOWN])
        extra = len(recorders) - RECORDERS_SHOWN
        ctx.fact("Recorded by", shown + (f" and {extra} more" if extra > 0 else ""))
    else:
        ctx.fact("Recorded by", "no meeting in the window")
    return OK, f"Fathom accepted the key and listed {len(items)}{more} meeting(s) from the last {WINDOW_DAYS} days."


CHECKS: list[Check] = [
    Check("settings", "Settings present", _settings),
    Check("meetings", "Read meetings", _meetings),
]


async def run(settings: Any, deps: Optional[Deps] = None) -> dict[str, Any]:
    ctx = Context(settings=settings, deps=deps or Deps())
    return await run_checks("fathom", CHECKS, ctx)
