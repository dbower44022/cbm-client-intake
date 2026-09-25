"""The PUBLIC programme pages, served by this app at ``/webinars/``.

The website's ``/webinars/`` redirects here. That is the whole delivery
mechanism: no WordPress plugin, no proxy, no inline frame (Doug, 2026-09-11).
It is fewer moving parts than either alternative, and it is what makes the two
things below possible at all.

**Why these pages are rendered here rather than served as static files.**

* **A social crawler runs no JavaScript.** An event's title, description and
  image have to be in the ``<head>`` of the response, or a shared link renders
  as a blank card whatever the event is. So the head is filled server-side, per
  event, before the bytes leave.
* **The publish gate has to be the page, not the content.** An unpublished
  event 404s here, exactly as its API endpoint and its image already do — the
  ``CEvent`` entity doubles as the organisation's internal calendar, so a page
  that merely rendered empty would still confirm the record exists.

**The body is still the same renderer the preview uses.** The two panels come
from ``/events-plugin/cbm-events.js`` against the public API, so the staff
preview and the live page are one code path.

Substitution is deliberately dumb: literal replacement of a small, closed set of
placeholders, every value HTML-escaped. Branding tokens are rendered FIRST so
that CRM-authored content substituted afterwards can never itself be scanned for
one.
"""

from __future__ import annotations

import logging
from html import escape
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from core import branding
from core.config import Settings, get_settings
from core.espo import EspoApi, EspoError

from . import service

log = logging.getLogger("cbm_intake.events")

PUBLIC_FRONTEND_DIR = Path(__file__).resolve().parent / "public_frontend"

page_router = APIRouter(tags=["events-public-pages"])

#: Read once per process per file. These are two small files and they change
#: only on deploy; branding is applied per request on top, so a name changed at
#: /setup still takes effect without a restart.
_templates: dict[str, str] = {}


def _template(name: str) -> str:
    cached = _templates.get(name)
    if cached is None:
        path = PUBLIC_FRONTEND_DIR / name
        try:
            cached = path.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - a broken deploy
            log.error("public events template %s unreadable: %s", name, exc)
            raise HTTPException(
                status_code=503, detail="This page is temporarily unavailable."
            ) from exc
        _templates[name] = cached
    return cached


def _nav_html(settings: Settings) -> str:
    """The organisation's own menu, built server-side.

    Server-side rather than fetched, for the same reason the organisation's name
    is substituted on serve: a menu that appears a moment after the page does is
    worse than no menu, and this one is the only way back to the site.
    """
    items = settings.site_nav_items
    if not items:
        return ""
    links = []
    for item in items:
        current = ' aria-current="page"' if item.get("current") else ""
        links.append(
            f'<a class="pub__navlink" href="{escape(item["url"], quote=True)}"{current}>'
            f'{escape(item["label"])}</a>'
        )
    return (
        '<nav class="pub__nav" aria-label="Site">' + "".join(links) + "</nav>"
    )


def _render(
    name: str,
    settings: Settings,
    values: dict[str, str],
    raw: Optional[dict[str, str]] = None,
) -> str:
    """Branding first, then this page's own values, every value escaped.

    ``raw`` carries fragments this module BUILT and escaped itself, piece by
    piece - the menu. Nothing from the CRM or from a setting reaches it without
    going through :func:`escape` on the way in.
    """
    html = branding.render_page(_template(name), settings)
    for token, value in values.items():
        html = html.replace("{{" + token + "}}", escape(value or "", quote=True))
    for token, fragment in (raw or {}).items():
        html = html.replace("{{" + token + "}}", fragment)
    return html


def _chrome(settings: Settings) -> dict[str, str]:
    """The values every public page shares."""
    return {
        "siteUrl": (settings.organization_website_url or "").strip(),
        "logoUrl": (settings.organization_logo_url or "").strip(),
        "contactEmail": settings.events_contact_address,
        "pageUrl": f"{settings.events_public_base}/" if settings.events_public_base else "",
        # The hero strings honour {{org}} and {{abbr}} (rendered as TEXT here,
        # then escaped like every other value by _render).
        "heroTagline": branding.render_text((settings.events_hero_tagline or "").strip(), settings),
        "heroPillars": branding.render_text((settings.events_hero_pillars or "").strip(), settings),
        "heroBand": branding.render_text((settings.events_hero_band or "").strip(), settings),
    }


def _client(request: Request) -> EspoApi:
    factory = getattr(request.app.state, "events_client_factory", None)
    if factory is None:  # pragma: no cover - misconfiguration
        raise HTTPException(status_code=503, detail="Events are not configured.")
    return factory()


def _page(html: str, settings: Settings) -> HTMLResponse:
    resp = HTMLResponse(html)
    ttl = settings.events_cache_seconds
    if ttl > 0:
        # A short public cache. It also means a visitor who reloads during a
        # brief outage of ours is served by their own browser rather than an
        # error — the nearest thing to the stale-on-error a proxy would have
        # given us.
        resp.headers["Cache-Control"] = f"public, max-age={ttl}"
    return resp


def _summary_for_share(event: dict[str, Any]) -> str:
    """One line for the search result and the social card.

    The event's own summary when there is one, else its date and format, so a
    shared link is never a bare title with nothing under it.
    """
    summary = (event.get("summary") or "").strip()
    if summary:
        return summary[:300]
    parts = [event.get("month") or "", event.get("day") or "", event.get("time") or ""]
    when = " ".join(p for p in parts if p).strip()
    return when or "A free workshop."


@page_router.get("/webinars", include_in_schema=False)
async def programme_no_slash() -> RedirectResponse:
    # 307, not 308: a permanent redirect is cached hard by browsers and would
    # outlive any future change to where this lives.
    return RedirectResponse("/webinars/", status_code=307)


@page_router.get("/webinars/", include_in_schema=False)
async def programme() -> Response:
    settings = get_settings()
    html = _render("index.html", settings, _chrome(settings),
                   raw={"siteNav": _nav_html(settings)})
    return _page(html, settings)


@page_router.get("/webinars/{slug}", include_in_schema=False)
async def event_page(slug: str, request: Request) -> Response:
    settings = get_settings()
    try:
        event = await service.get_by_slug(_client(request), slug)
    except EspoError as exc:
        log.warning("public event page %s failed: %s", slug, exc)
        raise HTTPException(
            status_code=502, detail="Event information is temporarily unavailable."
        ) from exc
    if event is None:
        # Unpublished and unknown are the same answer from out here. The CRM
        # entity behind this doubles as the internal calendar.
        raise HTTPException(status_code=404, detail="Event not found.")

    public = service.public_event(
        event,
        base_url=settings.events_public_base,
        api_base_url=settings.app_base_url,
        default_image=settings.events_default_graphic_url,
    )
    values = _chrome(settings)
    values.update(
        {
            "eventTitle": public.get("topic") or "Workshop",
            "eventSummary": _summary_for_share(public),
            "eventImage": public.get("imageUrl") or public.get("thumbnailUrl") or "",
            "eventSlug": public.get("slug") or slug,
            "pageUrl": public.get("url") or "",
        }
    )
    html = _render("event.html", settings, values,
                   raw={"siteNav": _nav_html(settings)})
    return _page(html, settings)
