"""The client-intake form's one extra public route: the mentor roster.

Why a live endpoint rather than a value baked into ``frontend/options.js`` (the
repo's usual pattern for CRM-backed dropdowns): the roster is *operational*
data, not a schema enum. Mentors toggle "accepting new clients" as their
capacity changes, and a stale list would invite a client to request someone who
is full — which is the disappointment this whole feature exists to avoid. The
sync-script pattern still fits the enum lists it was built for.

Exposure: the endpoint returns NAMES ONLY, and only for mentors whose
``publicProfile`` is already true — i.e. people already listed on
clevelandbusinessmentors.org. No email, phone, capacity or status is returned,
so this publishes nothing that is not already public.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from fastapi import APIRouter

from core.espo import EspoApi

log = logging.getLogger("cbm_intake.client_intake.roster")

MENTOR_PROFILE = "CMentorProfile"
MENTOR_STATUS_ACTIVE = "Active"

# The roster changes rarely and this endpoint is public, so a short in-process
# cache keeps a burst of form loads (or a bot) off the CRM. Matches the app's
# other storeless caches: a plain module-level dict, reset on redeploy.
_CACHE_SECONDS = 300
_cache: dict[str, Any] = {"at": 0.0, "mentors": None}


def _visible(record: dict[str, Any]) -> bool:
    """Active + accepting + already public (Doug's ruling 2026-07-27)."""
    return bool(
        record.get("publicProfile")
        and record.get("acceptingNewClients")
        and record.get("mentorStatus") == MENTOR_STATUS_ACTIVE
    )


async def fetch_mentors(client: EspoApi) -> list[dict[str, str]]:
    """The selectable roster, sorted by name. Filtering is done in Python: the
    boolean columns are cheap to evaluate here and it keeps this immune to the
    ``equals``-vs-``isTrue`` filter subtlety that makes a bad where-clause
    silently return almost nothing."""
    env = await client.list(
        MENTOR_PROFILE,
        select="id,name,mentorStatus,acceptingNewClients,publicProfile",
        max_size=200,
    )
    mentors = [
        {"id": r["id"], "name": r.get("name") or ""}
        for r in env.get("list", [])
        if _visible(r) and r.get("id") and r.get("name")
    ]
    mentors.sort(key=lambda m: m["name"].lower())
    return mentors


def make_router(client_factory) -> APIRouter:
    """``client_factory`` is called per request to build an EspoApi (the app
    already owns credential handling; this module never sees them)."""
    router = APIRouter(prefix="/api/client-intake", tags=["client-intake"])

    @router.get("/mentors")
    async def mentors() -> dict:
        """Never fails the form: on any error the form simply renders without
        the dropdown (the applicant can still describe their request in
        writing, exactly as before this feature existed)."""
        now = time.monotonic()
        cached: Optional[list] = _cache["mentors"]
        if cached is not None and now - _cache["at"] < _CACHE_SECONDS:
            return {"mentors": cached}
        try:
            found = await fetch_mentors(client_factory())
        except Exception as exc:  # noqa: BLE001 — degrade, never 500
            log.warning("mentor roster unavailable: %s", exc)
            # Serve a stale list if we have one — better than an empty dropdown.
            return {"mentors": cached or []}
        _cache["mentors"] = found
        _cache["at"] = now
        return {"mentors": found}

    return router
