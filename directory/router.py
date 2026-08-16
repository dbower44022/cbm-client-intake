"""FastAPI routes for one Workspace Directory (``/directory/{kind}/api``).

:func:`make_router` builds one router per kind from a
:class:`directory.config.DirectoryConfig`. All three share this code. Uses the
shared staff session (sign in once at the portal), gated per request to the
workspace team (admins always pass). Every read/write runs as the logged-in
user, so EspoCRM enforces their ACL — the team gate is only "who sees the
workspace at all".
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from assignments.auth import clear_session, current_user, is_member, session_expired
from assignments.espo_user import client_for
from core.config import Settings, get_settings
from core.espo import EspoClient, EspoError, forbidden_hint, is_forbidden, validation_message

from . import service
from .config import DirectoryConfig

log = logging.getLogger("cbm_intake.directory")


def _system_client(settings: Settings) -> Optional[EspoClient]:
    """The org-wide API-key CRM client (None in dry-run / keyless deploys).

    Used only for the mentor-availability aggregate, which must not vary with
    the viewing mentor's ACL (they can't read peers' engagements)."""
    if settings.espo_dry_run or not settings.espo_api_key:
        return None
    return EspoClient(
        settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds
    )


class SaveIn(BaseModel):
    changes: dict = {}


def make_router(cfg: DirectoryConfig) -> APIRouter:
    router = APIRouter(prefix=f"/directory/{cfg.slug}/api", tags=[f"directory-{cfg.slug}"])

    def _allowed_teams() -> list[str]:
        return get_settings().workspace_allowed_teams_list

    def _require_user(request: Request) -> dict:
        user = current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated.")
        teams = _allowed_teams()
        if not is_member(user, teams):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Your account is not authorized to use the {cfg.title} directory "
                    f"(requires the {', '.join(teams) or 'admin'} team)."
                ),
            )
        return user

    def _crm_failure(request: Request, exc: EspoError, message: str) -> HTTPException:
        if session_expired(exc):
            clear_session(request)
            return HTTPException(
                status_code=401, detail="Your session has expired — please sign in again."
            )
        actor = (current_user(request) or {}).get("userName", "?")
        log.warning("%s (%s, user=%s): %s", message, cfg.slug, actor, exc)
        friendly = validation_message(exc)
        if friendly:
            return HTTPException(status_code=400, detail=friendly)
        if is_forbidden(exc):
            hint = forbidden_hint(exc)
            return HTTPException(
                status_code=403,
                detail=(
                    f"{message}: your CRM role is missing {hint} — ask CBM staff to grant it."
                    if hint else
                    f"{message}: your account doesn't have permission to do this in "
                    "the CRM — ask CBM staff if you need it."
                ),
            )
        return HTTPException(status_code=502, detail=f"{message}: {exc}")

    @router.get("/session")
    async def session(request: Request) -> dict:
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            filter_defs = await service.filters(client, cfg)
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load the directory")
        return {
            "userName": user["userName"],
            "name": user["name"],
            "isAdmin": user["isAdmin"],
            "kind": cfg.slug,
            "title": cfg.title,
            "entity": cfg.entity,
            "editable": cfg.editable,
            "editHandoff": cfg.edit_handoff,
            "filters": filter_defs,
            # The View Contact page: whether this kind's rows open it, and
            # whether its Communications tab has a live backend (GMAIL_SYNC).
            "contactPage": cfg.contact_page,
            # The Company record page: shares record.html with View Contact
            # but hides Communications (Companies talk through their people).
            "companyPage": cfg.company_page,
            "commsEnabled": get_settings().gmail_sync,
            # True => the record page shows an Analytics tab rendering this
            # record's dashboard from the analytics app (Phase E).
            "analyticsEnabled": get_settings().analytics_active,
            "eventsEnabled": get_settings().events_active,
        }

    @router.post("/logout")
    async def logout(request: Request) -> dict:
        clear_session(request)
        return {"status": "ok"}

    @router.get("/records")
    async def records(
        request: Request,
        q: str = "",
        page: int = 1,
        pageSize: int = 50,
        orderBy: str = "",
        order: str = "asc",
        filters: str = "",
    ) -> dict:
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            applied = json.loads(filters) if filters else {}
            if not isinstance(applied, dict):
                applied = {}
        except ValueError:
            applied = {}
        try:
            return await service.list_records(
                client, cfg, q=q, applied_filters=applied,
                page=page, page_size=pageSize,
                order_by=orderBy or None, order=order,
            )
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load the directory")

    @router.get("/records/{record_id}")
    async def record_detail(record_id: str, request: Request) -> dict:
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            return await service.detail(client, cfg, record_id, user.get("userId"))
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load the record")

    @router.get("/contactdetail/{contact_id}")
    async def contact_detail(contact_id: str, request: Request) -> dict:
        """Read-only Contact detail for the company pop-up's contacts list (the
        name link). Reuses the Contacts directory config, so it's the same
        CRM-arranged view; the ACL read runs as the user."""
        from .config import DIRECTORIES

        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            return await service.detail(client, DIRECTORIES["contacts"], contact_id, user.get("userId"))
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load the contact")

    @router.get("/records/{record_id}/events")
    async def record_events(record_id: str, request: Request) -> dict:
        """EV-71 — this person's CBM event history.

        Served by the DIRECTORY router, not the events app: /events/api is gated
        to the Marketing Admin Team, and the people who read a contact record are
        the Mentor Team. Same computation (events.reporting.contact_history), the
        gate that fits the page. Empty (never an error) when Events is off, so
        the panel simply stays hidden.
        """
        user = _require_user(request)
        settings = get_settings()
        if not settings.events_active:
            return {"events": [], "enabled": False}
        client = client_for(settings, user)
        from events.reporting import contact_history

        try:
            return {"events": await contact_history(client, record_id), "enabled": True}
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load the event history")

    if cfg.mentor_page:
        # The rich read-only mentor profile page (its own browser tab). The
        # curated profile payload + a photo proxy (the browser can't reach the
        # CRM attachment directly). Both run as the signed-in user.
        @router.get("/profile/{record_id}")
        async def mentor_profile_detail(record_id: str, request: Request) -> dict:
            user = _require_user(request)
            settings = get_settings()
            client = client_for(settings, user)
            try:
                payload = await service.mentor_profile(client, record_id)
            except EspoError as exc:
                raise _crm_failure(request, exc, "Could not load the mentor profile")
            # Availability (openings) under the org-wide API key so a peer
            # mentor sees it too — best-effort, never fatal.
            sys_client = _system_client(settings)
            if sys_client is not None:
                try:
                    payload["availability"] = await service.mentor_availability(
                        sys_client, record_id,
                        (payload.get("professional") or {}).get("maxCapacity"),
                    )
                except EspoError as exc:
                    log.debug("availability skipped for %s: %s", record_id, exc)
            return payload

        @router.get("/photo/{record_id}")
        async def mentor_photo(record_id: str, request: Request) -> Response:
            user = _require_user(request)
            client = client_for(get_settings(), user)
            try:
                result = await service.mentor_photo(client, record_id)
            except EspoError as exc:
                raise _crm_failure(request, exc, "Could not load the photo")
            if result is None:
                raise HTTPException(status_code=404, detail="No profile photo.")
            data, content_type = result
            return Response(
                content=data,
                media_type=content_type,
                headers={"Cache-Control": "private, no-store"},
            )

    @router.put("/records/{record_id}")
    async def save_record(record_id: str, body: SaveIn, request: Request) -> dict:
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            result = await service.save(client, cfg, record_id, body.changes)
        except service.DirectoryError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not save the record")
        # Audit: which fields changed (never the values — they may be PII).
        log.info(
            "directory %s save %s/%s by %s (fields: %s)",
            cfg.slug, cfg.entity, record_id, user["userName"],
            ", ".join(sorted(body.changes)) or "-",
        )
        return result

    # /mailbox + /sendmail + /emailwriteback — the shared quick-compose behind
    # every email address shown in the grid/preview/pop-up (product rule: an
    # address is a compose link, not a bare mailto). Falls back to mailto in the
    # frontend when sending is unavailable (GMAIL_SYNC off / no CBM mailbox).
    from comms.quicksend import register_quicksend

    register_quicksend(
        router, _require_user, client_for, _crm_failure, include_mailbox=True
    )

    # The View Contact page's contact-scoped Communications endpoints
    # (conversation list/thread/compose/include/exclude, scoped to ONE
    # contact). Only the kind that opens the page carries them.
    if cfg.contact_page:
        from .comms_router import register_contact_comms

        register_contact_comms(router, cfg, _require_user, _crm_failure)

    return router
