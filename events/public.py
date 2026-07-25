"""Public, unauthenticated read API for the website (Phase 1).

Three endpoints, consumed by the CBM WordPress plugin (which proxies and caches
server-side, so visitors' browsers never call us directly):

    GET /api/events/upcoming              the calendar
    GET /api/events/recordings?q=&limit=  the recorded library
    GET /api/events/{slug}                one event, for its own page

Design notes:

* **Read-only.** Registration arrives in Phase 3 as a durable-capture form kind.
* **No PII, ever** (EV-82). These responses carry event facts and a
  seats-remaining number — never a registrant name, address, or headcount of
  who registered.
* **Cached** in-process for ``events_cache_seconds`` and marked cacheable
  downstream, so a burst of traffic costs the CRM one query (EV-81).
* Reads run through the **API-key client** — there is no session here.
* The router is only mounted when the feature is switched on, so an unconfigured
  deploy exposes nothing at all.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, Response

from core.config import get_settings
from core.espo import EspoApi, EspoError

from . import service

log = logging.getLogger("cbm_intake.events")

api_router = APIRouter(prefix="/api/events", tags=["events"])


class _TTLCache:
    """Tiny in-process cache.

    The app runs a single web instance (the same assumption the idempotency
    cache and folder caches already make), so this needs no coordination. Values
    are whole response bodies keyed by endpoint + arguments.
    """

    def __init__(self) -> None:
        self._entries: dict[str, tuple[float, Any]] = {}

    def get(self, key: str, ttl: int) -> Optional[Any]:
        entry = self._entries.get(key)
        if not entry:
            return None
        stamped, value = entry
        if ttl <= 0 or (time.monotonic() - stamped) > ttl:
            return None
        return value

    def put(self, key: str, value: Any) -> None:
        self._entries[key] = (time.monotonic(), value)

    def clear(self) -> None:
        self._entries.clear()


_cache = _TTLCache()


def _client(request: Request) -> EspoApi:
    """The API-key CRM client. Set on app.state by the factory so tests can
    substitute a fake without patching module internals."""
    factory = getattr(request.app.state, "events_client_factory", None)
    if factory is None:  # pragma: no cover - misconfiguration
        raise HTTPException(status_code=503, detail="Events are not configured.")
    return factory()


def _cacheable(response: Response, seconds: int) -> None:
    if seconds > 0:
        response.headers["Cache-Control"] = f"public, max-age={seconds}"


def _crm_failure(exc: EspoError, what: str) -> HTTPException:
    """Never leak CRM internals to the public. Log the detail, return a plain
    502 — the WordPress plugin serves its cached copy when we fail (EV-07)."""
    log.warning("public events %s failed: %s", what, exc)
    return HTTPException(
        status_code=502, detail="Event information is temporarily unavailable."
    )


@api_router.get("/upcoming")
async def upcoming(request: Request, response: Response) -> dict[str, Any]:
    settings = get_settings()
    ttl = settings.events_cache_seconds
    cached = _cache.get("upcoming", ttl)
    if cached is None:
        try:
            cached = await service.upcoming_payload(
                _client(request), base_url=settings.events_public_base_url
            )
        except EspoError as exc:
            raise _crm_failure(exc, "upcoming") from exc
        _cache.put("upcoming", cached)
    _cacheable(response, ttl)
    # `success` + `webinars` mirror the shape the page already consumes.
    return {"success": True, "webinars": cached}


@api_router.get("/recordings")
async def recordings(
    request: Request, response: Response, q: str = "", limit: int = 50
) -> dict[str, Any]:
    settings = get_settings()
    ttl = settings.events_cache_seconds
    limit = max(1, min(limit, 200))
    key = f"recordings:{q.strip().lower()}:{limit}"
    cached = _cache.get(key, ttl)
    if cached is None:
        try:
            rows = await service.list_recordings(_client(request), query=q, limit=limit)
        except EspoError as exc:
            raise _crm_failure(exc, "recordings") from exc
        cached = [
            service.public_recording(r, base_url=settings.events_public_base_url)
            for r in rows
        ]
        _cache.put(key, cached)
    _cacheable(response, ttl)
    return {"success": True, "query": q, "recordings": cached}


@api_router.get("/{slug}")
async def event_detail(slug: str, request: Request, response: Response) -> dict[str, Any]:
    settings = get_settings()
    ttl = settings.events_cache_seconds
    key = f"event:{slug}"
    cached = _cache.get(key, ttl)
    if cached is None:
        client = _client(request)
        try:
            event = await service.get_by_slug(client, slug)
            if event is None:
                # Unpublished and unknown look identical from outside - an
                # internal calendar entry must not be discoverable by URL.
                raise HTTPException(status_code=404, detail="Event not found.")
            seats_left = None
            if event.get("venueCapacity"):
                seats_left = (await service.event_summary(client, event))["seatsRemaining"]
            cached = service.public_event_detail(
                event,
                base_url=settings.events_public_base_url,
                seats_left=seats_left,
            )
        except EspoError as exc:
            raise _crm_failure(exc, f"event {slug}") from exc
        _cache.put(key, cached)
    _cacheable(response, ttl)
    return {"success": True, "event": cached}
