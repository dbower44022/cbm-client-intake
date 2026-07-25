"""FastAPI routes for the Analytics app (``/analytics/api``).

Uses the shared staff session (sign in once at the portal ``/``), gated per
request to ANALYTICS_VIEW_ALLOWED_TEAMS for viewing (authoring endpoints, Phase
B, will gate on the admin team). System pages are computed under the org-wide
API key (analytics are aggregates, not per-row data), so the team gate — plus
per-panel visibility — is the access boundary. The metric cache is read from
``request.app.state.analytics_store`` (set by ``create_app``); without it the
app runs live-only (recompute each view).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from assignments.auth import clear_session, current_user, is_member
from core.config import Settings, get_settings
from core.espo import EspoClient

from . import dashboard  # noqa: F401 — importing registers the metrics + seeded page
from .registry import PAGE_REGISTRY, PageSpec, get_page
from .service import build_time_range, invalidate_page_cache, render_page

log = logging.getLogger("cbm_intake.analytics")

router = APIRouter(prefix="/analytics/api", tags=["analytics"])


def _require_user(request: Request, *, admin: bool = False) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    settings = get_settings()
    teams = (
        settings.analytics_admin_allowed_teams_list
        if admin
        else settings.analytics_view_allowed_teams_list
    )
    if not is_member(user, teams):
        raise HTTPException(
            status_code=403,
            detail=(
                "Your account is not authorized to use Analytics "
                f"(requires the {', '.join(teams) or 'admin'} team)."
            ),
        )
    return user


def _can_view_page(user: dict, page: PageSpec, settings: Settings) -> bool:
    gate = list(page.team_gate) if page.team_gate else settings.analytics_view_allowed_teams_list
    return is_member(user, gate)


def _system_client(settings: Settings) -> Optional[EspoClient]:
    """The org-wide API-key CRM client (None in dry-run / keyless deploys)."""
    if settings.espo_dry_run or not settings.espo_api_key:
        return None
    return EspoClient(
        settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds
    )


def _store(request: Request):
    return getattr(request.app.state, "analytics_store", None)


def _page_summaries(user: dict, settings: Settings) -> list[dict]:
    return [
        {"key": p.key, "title": p.title, "scope": p.scope, "subtitle": p.subtitle}
        for p in PAGE_REGISTRY.values()
        if p.scope == "system" and _can_view_page(user, p, settings)
    ]


@router.post("/logout")
async def logout(request: Request) -> dict:
    clear_session(request)
    return {"status": "ok"}


@router.get("/session")
async def session(request: Request) -> dict:
    user = _require_user(request)
    settings = get_settings()
    return {
        "userName": user["userName"],
        "name": user["name"],
        "isAdmin": user["isAdmin"],
        "crmUrl": settings.espo_base_url,
        "pages": _page_summaries(user, settings),
    }


@router.get("/pages")
async def pages(request: Request) -> dict:
    user = _require_user(request)
    return {"pages": _page_summaries(user, get_settings())}


@router.get("/pages/{key}")
async def page_view(
    key: str,
    request: Request,
    range_key: Optional[str] = Query(None, alias="range"),
    frm: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
) -> dict:
    return await _render(key, request, range_key, frm, to, force=False)


@router.post("/pages/{key}/refresh")
async def page_refresh(
    key: str,
    request: Request,
    range_key: Optional[str] = Query(None, alias="range"),
    frm: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
) -> dict:
    """Recompute the page now: drop its cached metrics for this range, re-render."""
    return await _render(key, request, range_key, frm, to, force=True)


async def _render(
    key: str, request: Request, range_key, frm, to, *, force: bool
) -> dict:
    user = _require_user(request)
    settings = get_settings()
    page = get_page(key)
    if page is None or page.scope != "system":
        raise HTTPException(status_code=404, detail="Analytics page not found.")
    if not _can_view_page(user, page, settings):
        raise HTTPException(status_code=403, detail="You don't have access to this analytics page.")
    time_range = build_time_range(
        range_key or page.default_range, custom_from=frm, custom_to=to
    )
    espo = _system_client(settings)
    store = _store(request)
    try:
        if force and store is not None:
            await invalidate_page_cache(page, store=store, time_range=time_range)
        return await render_page(
            page,
            user=user,
            settings=settings,
            espo=espo,
            store=store,
            time_range=time_range,
            force=force,
        )
    except Exception as exc:  # noqa: BLE001 — per-metric errors are already handled inside
        log.warning("analytics render failed for %s: %s", key, exc)
        raise HTTPException(status_code=502, detail="Could not load analytics — try again.")
