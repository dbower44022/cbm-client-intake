"""The public addresses the chapter website reads (``/api/website/…``).

Always included, and switched per request by ``WEBSITE_API``: off, every
address answers 404 exactly as an unmounted one would, so the switch needs no
restart. No sign-in, by design (ruling 32: the chapter connector needs no
password); nothing served here is private.

**Cross-origin reads are allowed only from ``WEBSITE_ORIGINS``**, and only on
these addresses — never through the application-wide ``allowed_origins``,
which would open every staff address to the chapter website (plan finding 5).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse

from core.config import Settings, get_settings
from core.espo import EspoError

from . import content
from .images import IMAGE_NAMES
from .service import embed_css, settings_payload

log = logging.getLogger("cbm_intake.website")

public_router = APIRouter(prefix="/api/website", tags=["website"])
# The styles and the search script for the key pages' content, at the
# addresses the chapter connector already loads.
assets_router = APIRouter(prefix="/assets", tags=["website"])
_STATIC = Path(__file__).resolve().parent / "static"
_SLUG = re.compile(r"^[a-z0-9-]{1,120}$")

#: How long the website and the edge may keep an answer. WT-12: a change
#: reaches the website within a few minutes.
SETTINGS_MAX_AGE = 60
IMAGE_MAX_AGE = 300


def _active(request: Request) -> Settings:
    settings = get_settings()
    if not settings.website_api:
        raise HTTPException(status_code=404, detail="Not Found")
    return settings


def _allow_origin(request: Request, response: Response, settings: Settings) -> None:
    """Name the requesting website as allowed when it is one of ours."""
    origin = (request.headers.get("origin") or "").rstrip("/")
    response.headers["Vary"] = "Origin"
    if origin and origin in settings.website_origins_list:
        response.headers["Access-Control-Allow-Origin"] = origin


def public_base(request: Request, settings: Settings) -> str:
    """The applications' public address: the configured one, else the address
    this request arrived on."""
    root = (settings.app_base_url or "").strip().rstrip("/")
    return root or str(request.base_url).rstrip("/")


async def _image_meta(request: Request) -> dict[str, dict[str, Any]]:
    store = getattr(request.app.state, "website_store", None)
    if store is None:
        return {}
    try:
        return await store.image_meta()
    except Exception as exc:  # noqa: BLE001 — the settings must still be served
        log.warning("website images could not be read: %s", exc)
        return {}


@public_router.get("/settings")
async def website_settings(request: Request, response: Response) -> dict[str, Any]:
    settings = _active(request)
    payload = settings_payload(settings, await _image_meta(request), public_base(request, settings))
    _allow_origin(request, response, settings)
    response.headers["Cache-Control"] = f"public, max-age={SETTINGS_MAX_AGE}"
    return payload


@public_router.get("/images/{name}")
async def website_image(name: str, request: Request) -> Response:
    settings = _active(request)
    store = getattr(request.app.state, "website_store", None)
    if name not in IMAGE_NAMES or store is None:
        raise HTTPException(status_code=404, detail="Not Found")
    image = await store.get_image(name)
    if image is None:
        raise HTTPException(status_code=404, detail="Not Found")
    etag = f'"{image["sha256"]}"'
    headers = {
        "ETag": etag,
        "Cache-Control": f"public, max-age={IMAGE_MAX_AGE}",
        "X-Content-Type-Options": "nosniff",
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    response = Response(content=image["data"], media_type=image["contentType"], headers=headers)
    _allow_origin(request, response, settings)
    return response


# --- the key pages (plan piece B) ----------------------------------------------


def _client(request: Request):
    """The org-wide API key client — nothing here runs as a visitor."""
    return request.app.state.events_client_factory()


async def _cached(request: Request, key: str, load) -> Any:
    """A cached CRM read. When the CRM cannot be reached the last copy is
    served (WT-26); with no copy at all the answer is 503, never a 500."""
    ttl = max(0, int(get_settings().website_cache_seconds))
    try:
        return await content.cache.get(key, ttl, load)
    except EspoError as exc:
        stale = content.cache.peek(key)
        if stale is not None:
            log.warning("website %s: CRM unreachable, serving the last copy: %s", key, exc)
            return stale
        log.warning("website %s: CRM unreachable and no copy kept: %s", key, exc)
        raise HTTPException(status_code=503, detail="The chapter applications cannot read the CRM right now.") from exc


async def _mentors(request: Request) -> list[dict[str, Any]]:
    return await _cached(request, "mentors", lambda: content.load_mentors(_client(request)))


def _page_active(settings: Settings, page: str) -> None:
    """A page the website has switched off is not served, so a stale menu
    entry on the website cannot keep it alive."""
    from core.settings_registry import WEBSITE_PAGE_SWITCHES, WEBSITE_PAGES_SERVED

    if page not in WEBSITE_PAGES_SERVED or not getattr(settings, WEBSITE_PAGE_SWITCHES[page], False):
        raise HTTPException(status_code=404, detail="Not Found")


def _send(request: Request, response: Response, settings: Settings, body: Any) -> Any:
    _allow_origin(request, response, settings)
    response.headers["Cache-Control"] = f"public, max-age={SETTINGS_MAX_AGE}"
    return body


@public_router.get("/pages/mentors")
async def page_mentors(request: Request, response: Response) -> dict[str, str]:
    settings = _active(request)
    _page_active(settings, "mentors")
    mentors = await _mentors(request)
    return _send(request, response, settings, content.page_mentors(public_base(request, settings), mentors))


@public_router.get("/pages/mentors/{slug}")
async def page_mentor(slug: str, request: Request, response: Response) -> dict[str, str]:
    settings = _active(request)
    _page_active(settings, "mentors")
    mentor = next((m for m in await _mentors(request) if m["slug"] == slug), None) if _SLUG.match(slug) else None
    if mentor is None:
        raise HTTPException(status_code=404, detail="No such mentor.")
    return _send(request, response, settings, content.page_mentor(public_base(request, settings), mentor))


@public_router.get("/pages/events")
async def page_events(request: Request, response: Response) -> dict[str, str]:
    from events import service as events_service

    settings = _active(request)
    _page_active(settings, "events")
    events = await _cached(request, "events", lambda: events_service.upcoming_payload(
        _client(request), base_url=settings.events_public_base, api_base_url=settings.app_base_url))
    return _send(request, response, settings, content.page_events(events))


@public_router.get("/pages/recordings")
async def page_recordings(request: Request, response: Response) -> dict[str, str]:
    from events import service as events_service

    settings = _active(request)
    _page_active(settings, "recordings")

    async def load() -> list[dict[str, Any]]:
        rows = await events_service.published_recordings(_client(request))
        return [events_service.public_recording(r, base_url=settings.events_public_base,
                                                api_base_url=settings.app_base_url) for r in rows]

    recordings = await _cached(request, "recordings", load)
    return _send(request, response, settings, content.page_recordings(recordings))


@public_router.get("/pages/{key}")
async def page_unserved(key: str, request: Request) -> None:
    """Partners, sponsors, stories and anything unknown: not served (WT-10)."""
    _active(request)
    raise HTTPException(status_code=404, detail="Not Found")


@public_router.get("/sitemap")
async def sitemap(request: Request, response: Response) -> dict[str, list[str]]:
    settings = _active(request)
    paths: list[str] = []
    if settings.website_page_mentors and "mentors" in _served():
        paths = [f"/mentors/{m['slug']}/" for m in await _mentors(request)]
    return _send(request, response, settings, {"paths": paths})


def _served() -> frozenset[str]:
    from core.settings_registry import WEBSITE_PAGES_SERVED

    return WEBSITE_PAGES_SERVED


@public_router.get("/mentors.json")
async def mentor_search(request: Request, response: Response, q: str = "") -> dict[str, list[str]]:
    settings = _active(request)
    _page_active(settings, "mentors")
    slugs = content.search(await _mentors(request), q[:200])
    return _send(request, response, settings, {"slugs": slugs})


@public_router.get("/mentors/{slug}/photo")
async def mentor_photo(slug: str, request: Request) -> Response:
    settings = _active(request)
    _page_active(settings, "mentors")
    mentor = next((m for m in await _mentors(request) if m["slug"] == slug), None) if _SLUG.match(slug) else None
    if mentor is None or not mentor["photoId"]:
        raise HTTPException(status_code=404, detail="Not Found")
    photo_id = mentor["photoId"]
    ttl = max(0, int(settings.website_cache_seconds))
    try:
        data, ctype = await content.cache.get(
            f"photo:{photo_id}", ttl, lambda: _client(request).download_attachment(photo_id))
    except EspoError as exc:
        raise HTTPException(status_code=404, detail="Not Found") from exc
    if not str(ctype).startswith("image/"):
        raise HTTPException(status_code=404, detail="Not Found")
    return Response(content=data, media_type=ctype, headers={
        "Cache-Control": f"public, max-age={IMAGE_MAX_AGE}", "X-Content-Type-Options": "nosniff"})


@assets_router.get("/website.css")
async def website_css(request: Request) -> FileResponse:
    _active(request)
    return FileResponse(_STATIC / "website.css", media_type="text/css",
                        headers={"Cache-Control": f"public, max-age={IMAGE_MAX_AGE}"})


@assets_router.get("/search.js")
async def search_js(request: Request) -> FileResponse:
    _active(request)
    return FileResponse(_STATIC / "search.js", media_type="text/javascript",
                        headers={"Cache-Control": f"public, max-age={IMAGE_MAX_AGE}"})


# --- forms in frames (plan piece C) ----------------------------------------------
# Loaded by every public form page, whatever the switches say, so each answers
# 200 with nothing in it while FORM_FRAMING is off — never a 404 in the
# visitor's console.

_FRAME_JS = (_STATIC / "frame.js").read_text(encoding="utf-8")


@assets_router.get("/frame.js")
async def frame_js() -> Response:
    settings = get_settings()
    body = "/* Forms in website frames is off. */\n"
    if settings.form_framing:
        body = _FRAME_JS.replace("__ORIGINS__", json.dumps(settings.website_origins_list))
    return Response(content=body, media_type="text/javascript",
                    headers={"Cache-Control": f"public, max-age={SETTINGS_MAX_AGE}"})


@assets_router.get("/embed.css")
async def embed_stylesheet() -> Response:
    settings = get_settings()
    body = embed_css(settings) if settings.form_framing else "/* Forms in website frames is off. */\n"
    return Response(content=body, media_type="text/css",
                    headers={"Cache-Control": f"public, max-age={SETTINGS_MAX_AGE}"})
