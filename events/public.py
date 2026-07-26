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
from forms.event_registration import orchestrator as registration_orchestrator

from . import service
from .tokens import TokenError, read_cancel_token

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


# --- registration (Phase 3) ------------------------------------------------


def make_registration_routes(process) -> APIRouter:
    """Register + self-service cancel.

    ``process`` is the core pipeline entry point, injected by the app factory so
    this module never reaches back into ``core.app``. Registration therefore
    rides the SAME machinery as the five intake forms — durable capture before
    any external call, idempotency by submission token, retries, resumable
    delivery, and Submission Admin visibility — with the event slug taken from
    the URL.
    """
    router = APIRouter(prefix="/api/events", tags=["events"])

    @router.post("/{slug}/register")
    async def register(slug: str, request: Request) -> Any:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 — caller data
            raise HTTPException(
                status_code=422, detail="The request body is not valid JSON."
            )
        if not isinstance(body, dict):
            raise HTTPException(
                status_code=422, detail="The request body must be a JSON object."
            )

        # Pre-flight BEFORE capture. With async delivery on, the HTTP response
        # is sent long before the orchestrator runs, so a refusal raised at
        # delivery time would never reach the visitor (EV-14).
        try:
            await registration_orchestrator.check_open(_client(request), slug)
        except registration_orchestrator.RegistrationRefused as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except EspoError as exc:
            raise _crm_failure(exc, f"register {slug}") from exc

        body["event_slug"] = slug
        return await process(body)

    @router.post("/registrations/{token}/cancel")
    async def cancel(token: str, request: Request) -> dict[str, Any]:
        settings = get_settings()
        try:
            registration_id = read_cancel_token(token, settings.session_secret)
        except TokenError as exc:
            # Every failure mode returns the SAME message, so the endpoint
            # cannot be used to probe which registration ids exist.
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        try:
            result = await service.cancel_registration(
                _client(request), registration_id, settings=settings
            )
        except EspoError as exc:
            raise _crm_failure(exc, "cancel registration") from exc
        if not result.get("ok"):
            raise HTTPException(status_code=404,
                                detail="This cancellation link is not valid.")
        return result

    return router
