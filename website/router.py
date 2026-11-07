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

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from core.config import Settings, get_settings

from .images import IMAGE_NAMES
from .service import settings_payload

log = logging.getLogger("cbm_intake.website")

public_router = APIRouter(prefix="/api/website", tags=["website"])

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
