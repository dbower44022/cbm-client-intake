"""The YouTube integration test (prds/integrations-tab-plan.md § 3; the check
list Doug approved 11-13-26, phase 3 stopping point 1).

YouTube has no switch: the key serves the playlist import. Checks, in order:

1. **Settings present** — the API key and at least one playlist ID.
2. **Read each playlist** — one ``playlists.list`` call for every configured
   ID (``part=snippet,contentDetails``; one quota unit). A refused key or the
   API not enabled on the Google project is failed; ``quotaExceeded`` is
   unknown, because it clears by itself; a playlist absent from the answer is
   failed and named. Facts: each playlist's title and video count.

Confirmed against the YouTube Data API reference 11-13-26: ``snippet.title``,
``contentDetails.itemCount``, ``quotaExceeded (403)``. The key-refused and
API-disabled reasons are Google's general ones, not on YouTube's own page.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from integrations.testing import FAILED, OK, UNKNOWN, Blocked, Check, Context, run_checks

#: Reasons that clear by themselves: the check cannot say yes or no.
TRANSIENT_REASONS = {"quotaExceeded", "rateLimitExceeded", "userRateLimitExceeded",
                     "backendError", "RATE_LIMIT_EXCEEDED"}


def _default_client(settings: Any) -> Any:
    from core.youtube import YouTubeClient

    return YouTubeClient(settings.youtube_api_key, timeout=10)


@dataclass
class Deps:
    client: Callable[[Any], Any] = _default_client


def _ids(settings: Any) -> list[str]:
    return list(getattr(settings, "youtube_playlist_ids", []) or [])


async def _settings(ctx: Context) -> tuple[str, str]:
    missing = []
    if not (ctx.settings.youtube_api_key or "").strip():
        missing.append("the YouTube API key")
    if not _ids(ctx.settings):
        missing.append("a playlist ID")
    if missing:
        return FAILED, "Not set: " + " and ".join(missing) + "."
    ctx.state["settings_ok"] = True
    n = len(_ids(ctx.settings))
    return OK, f"The API key is set, and {n} playlist ID(s)."


async def _playlists(ctx: Context) -> tuple[str, str]:
    if not ctx.state.get("settings_ok"):
        raise Blocked("Not checked: a setting is missing (check 1).")
    ids = _ids(ctx.settings)
    try:
        items = await ctx.deps.client(ctx.settings).playlists(ids)
    except Exception as exc:  # noqa: BLE001
        status = getattr(exc, "status_code", None)
        reason = getattr(exc, "reason", "") or ""
        if status is None or status >= 500 or reason in TRANSIENT_REASONS:
            hint = " The daily quota is used up; it resets at midnight Pacific time." if reason == "quotaExceeded" else ""
            return UNKNOWN, f"Could not read the playlists: {exc}.{hint}"
        if reason in ("accessNotConfigured", "SERVICE_DISABLED"):
            return FAILED, ("The YouTube Data API is not switched on for the key's Google "
                            f"Cloud project ({reason}). Enable it in the Google Cloud console.")
        if status in (400, 401, 403):
            return FAILED, f"YouTube refused the API key: {exc}."
        return FAILED, f"YouTube refused the request: {exc}."
    found: dict[str, dict[str, Any]] = {}
    for item in items or []:
        if isinstance(item, dict) and item.get("id"):
            found[str(item["id"])] = item
    missing = [pid for pid in ids if pid not in found]
    for pid in ids:
        item = found.get(pid)
        if item is None:
            ctx.fact(f"Playlist {pid}", "not found")
            continue
        title = (item.get("snippet") or {}).get("title") or pid
        count = (item.get("contentDetails") or {}).get("itemCount")
        ctx.fact(f"Playlist {pid}", f"{title} ({count if count is not None else 'count not reported'} videos)")
    if missing:
        return FAILED, ("YouTube has no public playlist " + ", ".join(missing)
                        + ". Check the ID, and that the playlist is public or unlisted.")
    return OK, f"Read {len(ids)} playlist(s)."


CHECKS: list[Check] = [
    Check("settings", "Settings present", _settings),
    Check("playlists", "Read each playlist", _playlists),
]


async def run(settings: Any, deps: Optional[Deps] = None) -> dict[str, Any]:
    ctx = Context(settings=settings, deps=deps or Deps())
    return await run_checks("youtube", CHECKS, ctx)
