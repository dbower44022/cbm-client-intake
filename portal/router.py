"""FastAPI routes for the portal (``/api/portal``).

The portal is the single sign-in for everything: login accepts any **active
internal CRM user** (no team gate — ``authenticate(..., gate=False)``), stores
the user + their team names in the shared staff session, and returns the links
that user is entitled to. The staff apps stay individually protected — each
enforces its own team per request — so the portal listing is a convenience,
never the security boundary.

Entitlements (team names come from settings, so they match the app gates):
- any signed-in user: the public intake-form links
- Mentor Team: a link to the CRM itself + ``/mentorprofile/`` (My Mentor Profile)
- Client Administration Team: ``/assignments/``
- Mentor Administration Team: ``/mentoradmin/``
- Marketing Admin Team: ``/ops/`` (Submission Admin) + ``/events/`` (Event Administration)
- CRM admins: everything.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from assignments.auth import (
    AuthError,
    authenticate,
    clear_session,
    current_user,
    is_member,
    refresh_membership,
    request_password_reset,
    set_session,
)
from assignments.espo_user import client_for
from core import attention as attn
from core.config import Settings, get_settings

from . import birthday as birthday_check

log = logging.getLogger("cbm_intake.portal")

router = APIRouter(prefix="/api/portal", tags=["portal"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class ForgotPasswordIn(BaseModel):
    username: str = Field(min_length=1)
    emailAddress: str = Field(min_length=3)


def _public_pages(request: Request, settings: Settings) -> list[dict[str, str]]:
    """The pages a member of the public can open, which staff need to hand out.

    The intake forms come from the registered specs, so a new form appears here
    without anyone remembering to add it. The workshops-and-webinars programme
    is not a form - it is a page this app serves at ``/webinars/``, and the
    marketing site redirects to it - but it belongs in the same list for the
    same reason: it is a public address staff are asked for.
    """
    specs = getattr(request.app.state, "form_specs", []) or []
    pages = [
        {"title": s.title, "url": f"/{s.slug}/"}
        for s in specs
        if s.frontend_dir is not None
    ]
    if settings.events_public_active:
        pages.insert(0, {"title": "Workshops and Webinars", "url": "/webinars/"})
    return pages


def _directories_for(user: dict[str, Any], settings: Settings) -> list[dict[str, str]]:
    """The Workspace directory links, derived from the directory registry so a
    new kind appears here automatically. Gated to the workspace team; the real
    data scope is each user's CRM ACL. ``target`` is the stable browser-tab name
    the launcher opens each in (so re-clicking reuses the tab, not a duplicate)."""
    if not is_member(user, settings.workspace_allowed_teams_list):
        return []
    from directory import DIRECTORIES

    return [
        {"title": cfg.title, "url": f"/directory/{cfg.slug}/", "target": f"cbm-{cfg.slug}"}
        for cfg in DIRECTORIES.values()
    ]


def _apps_for(user: dict[str, Any], settings: Settings) -> list[dict[str, str]]:
    """The staff-app links this user's teams entitle them to (admins: all). Each
    carries a stable ``target`` tab name so the launcher de-duplicates windows."""
    apps = []
    if is_member(user, settings.assign_allowed_teams_list, settings.assign_allowed_roles_list):
        apps.append({"title": "Client Administration", "url": "/assignments/", "target": "cbm-assignments"})
    if is_member(user, settings.mentor_admin_allowed_teams_list):
        apps.append({"title": "Mentor Administration", "url": "/mentoradmin/", "target": "cbm-mentoradmin"})
    if is_member(user, settings.ops_allowed_teams_list):
        apps.append({"title": "Submission Admin", "url": "/ops/", "target": "cbm-ops"})
    # Event Administration — the public workshop/webinar programme.
    if settings.events_active and is_member(user, settings.events_allowed_teams_list):
        apps.append({"title": "Event Administration", "url": "/events/", "target": "cbm-events"})
    # Campaign Management — prospect marketing (CM-10, CM-11). Read per request:
    # the switch needs no restart, and the tile appears the moment it is on.
    if settings.campaigns_active and is_member(user, settings.campaigns_allowed_teams_list):
        apps.append({"title": "Marketing Management", "url": "/campaigns/", "target": "cbm-campaigns"})
    # A mentor's self-service profile editor (own record + website preview).
    if is_member(user, settings.mentor_profile_allowed_teams_list):
        apps.append({"title": "My Mentor Profile", "url": "/mentorprofile/", "target": "cbm-mentorprofile"})
    # Session Management tools — each gated to its own team. Display names
    # renamed 2026-07-19 (Doug): Client / Partner / Funder Management — the
    # routes and team gates are unchanged.
    if is_member(user, settings.session_mentor_allowed_teams_list):
        apps.append({"title": "Client Management", "url": "/mentorsessions/", "target": "cbm-mentorsessions"})
    if is_member(user, settings.session_partner_allowed_teams_list):
        apps.append({"title": "Partner Management", "url": "/partnersessions/", "target": "cbm-partnersessions"})
    if is_member(user, settings.session_sponsor_allowed_teams_list):
        apps.append({"title": "Funder Management", "url": "/sponsorsessions/", "target": "cbm-sponsorsessions"})
    # My Email — the unified inbox across the records those tools manage.
    # Shown only where the Gmail integration is on (the page 503s otherwise).
    if settings.gmail_sync and any(
        is_member(user, getattr(settings, attr))
        for attr in (
            "session_mentor_allowed_teams_list",
            "session_partner_allowed_teams_list",
            "session_sponsor_allowed_teams_list",
        )
    ):
        apps.append({"title": "My Email", "url": "/myemail/", "target": "cbm-myemail"})
    # Analytics — dashboards over the CRM + operational data. Shown only where
    # the app is enabled and the user may view it (per-panel visibility is
    # applied inside the app on top of this).
    if settings.analytics_active and (
            is_member(user, settings.analytics_view_allowed_teams_list)
            or _analytics_feedback_viewer(user, settings)):
        apps.append({"title": "Analytics", "url": "/analytics/", "target": "cbm-analytics"})
    # The activity page — every change by a person or in a date range
    # (mentor login integrity step 6). Read per request.
    if settings.activity_page and is_member(user, settings.system_management_allowed_teams_list):
        apps.append({"title": "Activity", "url": "/activity/", "target": "cbm-activity"})
    # Chapter News (prds/home-page-plan.md § 6.2): its own page, shown only
    # to publishers. Read per request.
    if settings.chapter_news and is_member(user, settings.news_publish_allowed_teams_list):
        apps.append({"title": "Chapter News", "url": "/news/", "target": "cbm-news"})
    # System Settings — EspoCRM administrators only (ruling 1). Not team-gated:
    # this page can reconfigure the platform, so the smallest audience wins.
    if settings.setup_active and user.get("isAdmin"):
        apps.append({"title": "System Settings", "url": "/setup/", "target": "cbm-setup"})
    return apps


async def _campaign_calls_tile(user: dict[str, Any], settings: Settings) -> dict[str, str] | None:
    """*Campaign calls* for a caller outside the Marketing Admin Team (ruling
    114): shown when a Running call campaign names a team the user is in, which
    is the same split the Calls tab applies (``calls.may_call``). Read under the
    org-wide key — the campaigns are the chapter's data, not the caller's — and
    best-effort: no key, or a failing read, means no tile."""
    if not (settings.campaigns_active and settings.campaigns_calls):
        return None
    if is_member(user, settings.campaigns_allowed_teams_list):
        return None  # the Marketing Management tile already opens every tab
    if settings.espo_dry_run or not settings.espo_api_key:
        return None
    from campaigns import calls
    from core.espo import EspoClient

    client = EspoClient(settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds)
    try:
        if await calls.may_call_any(client, user, settings):
            return {"title": "Campaign calls", "url": "/campaigns/#calls", "target": "cbm-campaigns"}
    except Exception as exc:  # noqa: BLE001 — a tile is never worth a failed sign-in
        log.warning("campaign calls tile skipped for %s: %s", user.get("userName"), exc)
    return None


async def _extra_tiles(payload: dict, user: dict[str, Any], settings: Settings) -> dict:
    """The tiles that need a CRM read; appended after the entitlement tiles."""
    tile = await _campaign_calls_tile(user, settings)
    if tile:
        payload["apps"].append(tile)
    return payload


def _home_sections(user: dict[str, Any], settings: Settings) -> list[str]:
    """The new home page's section frames this member is entitled to, in the
    plan's order (prds/home-page-plan.md § 4.1, ruling 2: one page that adapts
    by role). Chapter News is everyone's (phase 5, behind CHAPTER_NEWS); Today
    and My clients are a mentor's; Needs you is a mentor's or a staff queue's;
    At the chapter is everyone's; the public pages frame shows when there are
    pages."""
    mentoring = is_member(user, settings.session_mentor_allowed_teams_list)
    queues = any(
        is_member(user, teams)
        for teams in (
            settings.assign_allowed_teams_list,
            settings.mentor_admin_allowed_teams_list,
            settings.ops_allowed_teams_list,
            settings.session_partner_allowed_teams_list,
            settings.session_sponsor_allowed_teams_list,
        )
    )
    sections = []
    # Chapter News, first on the page (§ 4.1; decision 9 of the phases 5 to 7
    # prompt). Every member; the section hides itself where the CRM has no
    # Chapter News yet.
    if settings.chapter_news:
        sections.append("news")
    if mentoring:
        sections.append("today")
    if mentoring or queues:
        sections.append("needs")
    if mentoring:
        sections.append("clients")
    sections.append("chapter")
    # The events rail has its own frame (Doug, 11-18-26), shown where the
    # portal calendar is on.
    if settings.portal_calendar_active:
        sections.append("events")
    sections.append("pages")
    # The Analytics dashboard has its own panel at the end (phase 4,
    # answer 5); it self-gates, and the page hides the frame when it does
    # not come up for this member.
    if settings.analytics_active:
        sections.append("analytics")
    return sections


def _home_payload(user: dict[str, Any], request: Request, settings: Settings) -> dict:
    mentor = is_member(user, [settings.mentor_team_name])
    payload = _home_payload_v1(user, request, settings, mentor)
    # The new home page (HOME_V2, phase 1). Read per request; off, the page
    # renders exactly as before and only this flag is added.
    payload["homeV2"] = bool(settings.home_v2)
    if settings.home_v2:
        name = (user.get("name") or user["userName"]).strip()
        payload["home"] = {
            "firstName": name.split()[0] if name else user["userName"],
            "sections": _home_sections(user, settings),
        }
    return payload


def _home_payload_v1(
    user: dict[str, Any], request: Request, settings: Settings, mentor: bool
) -> dict:
    return {
        "user": {
            "userName": user["userName"],
            "name": user.get("name") or user["userName"],
            "isAdmin": bool(user.get("isAdmin")),
        },
        "directories": _directories_for(user, settings),
        "apps": _apps_for(user, settings),
        # The CRM itself, for mentors (and admins) — the deploy's own target,
        # so the crm-test app links to crm-test and prod to production.
        "crmUrl": settings.espo_base_url if mentor else None,
        # The documentation site — every signed-in user gets it (the app user
        # guides live there). Empty setting => no link.
        "docsUrl": settings.docs_site_url or None,
        # True => the home page tries to render the analytics portal dashboard
        # (GET /analytics/api/portal; it self-gates, so non-analytics users just
        # get available:false and no dashboard shows). Phase D.
        "analyticsEnabled": settings.analytics_active,
        # True => the home page renders the events rail (F5) from
        # GET /api/portal/events and offers the member page. Per-request, so
        # /setup switches it without a restart.
        "eventsCalendar": settings.portal_calendar_active,
        "forms": _public_pages(request, settings),
    }


async def _birthdays(user: dict[str, Any], settings: Settings) -> Any:
    """What this sign-in should celebrate: the viewer's OWN birthday and/or
    today's other CBM members, for the "wish them a happy birthday" notice.

    Every signed-in member is in scope (CBM member = their ``CMentorProfile``,
    whatever team they're on) — a user with no member record simply has no own
    greeting, but still sees the announcement. The roster read is cached
    process-wide for the day, so this costs no CRM call per request; it never
    raises."""
    return await birthday_check.greetings_for(settings, user)


@router.post("/login")
async def login(body: LoginIn, request: Request) -> dict:
    settings = get_settings()
    try:
        # gate=False: any active internal user may sign in to the portal; what
        # they can DO is decided per app, per request (is_member).
        user = await authenticate(settings, body.username, body.password, gate=False)
    except AuthError as exc:
        # Audit: failed sign-ins were previously invisible (the staff front
        # door had no log at all). Username only — never the password.
        log.warning("portal login FAILED for %s: %s", body.username, exc)
        raise HTTPException(status_code=401, detail=str(exc))
    set_session(request, user)
    log.info("portal login ok: %s (admin=%s)", user["userName"], user.get("isAdmin"))
    payload = await _extra_tiles(_home_payload(user, request, settings), user, settings)
    payload["birthdays"] = await _birthdays(user, settings)
    return payload


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordIn) -> dict:
    """Email the user a CRM password-reset link (EspoCRM's own recovery flow).

    Unauthenticated by nature; the CRM does the matching, throttling, and the
    email itself. Failures come back as a readable ``detail`` string (exact
    messages per the project error policy — the CRM's own login page reports
    not-found the same way).
    """
    settings = get_settings()
    try:
        await request_password_reset(
            settings, body.username.strip(), body.emailAddress.strip()
        )
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "status": "ok",
        "message": (
            "A password reset email is on its way. Follow the link in it to "
            "choose a new password, then come back here to sign in."
        ),
    }


@router.get("/session")
async def session(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    settings = get_settings()
    # Re-read team/role membership from the CRM on every session restore: the
    # cookie caches teams at login time, so without this a team granted (or
    # removed) in the CRM never showed until the user signed out and back in.
    # The refreshed session is re-saved, so the staff apps' per-request gates
    # see the same up-to-date membership.
    try:
        user = await refresh_membership(settings, user)
    except AuthError as exc:
        clear_session(request)
        raise HTTPException(status_code=401, detail=str(exc))
    set_session(request, user)
    payload = await _extra_tiles(_home_payload(user, request, settings), user, settings)
    payload["birthdays"] = await _birthdays(user, settings)
    return payload


@router.get("/attention")
async def attention(request: Request) -> dict:
    """Per-app counts of items awaiting processing — the portal tile badges
    (Doug's request 2026-07-26). Definitions live in :mod:`core.attention`;
    CRM counts run AS THE SIGNED-IN USER (their ACL = what each app will show
    them) and only for the apps their teams entitle them to, so the badge set
    mirrors the tile set. Best-effort throughout: a failing count is omitted
    (no badge), never an error the home page must handle."""
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return {"items": await _attention_items(request, user, get_settings())}


async def _attention_items(request: Request, user: dict[str, Any],
                           settings: Settings) -> list[dict[str, Any]]:
    """The staff queue counts this member's teams entitle them to: the bar's
    badges on today's page, the purple Staff rows of Needs you on the new
    one (HOME_V2, phase 3). Ruling 3 holds here: the waiting-clients count
    is Client Administration's alone."""
    wanted: list[attn.AttentionType] = []
    if is_member(user, settings.assign_allowed_teams_list, settings.assign_allowed_roles_list):
        wanted.append(attn.ENGAGEMENTS)
    if is_member(user, settings.mentor_admin_allowed_teams_list):
        wanted.append(attn.MENTORS)
    if is_member(user, settings.session_partner_allowed_teams_list):
        wanted.append(attn.PARTNERS)
    if is_member(user, settings.session_sponsor_allowed_teams_list):
        wanted.append(attn.FUNDERS)

    items: list[dict[str, Any]] = []
    if wanted:
        client = client_for(settings, user)

        async def one(t: attn.AttentionType) -> dict[str, Any] | None:
            try:
                return {"url": t.app_url, "count": await attn.crm_count(client, t),
                        "label": t.label}
            except Exception as exc:  # noqa: BLE001 — a badge never breaks the portal
                log.warning("attention count failed (%s) for %s: %s",
                            t.key, user.get("userName"), exc)
                return None

        items.extend(r for r in await asyncio.gather(*(one(t) for t in wanted)) if r)

    # Login faults (mentor login integrity plan § 4.2, step 4b): open faults
    # nobody has acknowledged, as a second badge on the Mentor Administration
    # tile beside its new-applications count.
    if settings.integrity_digest and is_member(user, settings.mentor_admin_allowed_teams_list):
        try:
            from integrity.store import get_store as integrity_store

            fstore = integrity_store(settings)
            if fstore is not None:
                items.append({"url": attn.MENTORS.app_url, "kind": "fault",
                              "count": await fstore.open_count(),
                              "label": "Login faults to look at"})
        except Exception as exc:  # noqa: BLE001 — a badge never breaks the portal
            log.warning("attention count failed (login faults) for %s: %s",
                        user.get("userName"), exc)

    # Feedback to follow up (feedback surveys, phases 8 and 9, decision 4):
    # the Mentor Administration Team's mentoring and evaluation responses,
    # the Marketing Admin Team's event responses. The row opens the oldest.
    if settings.feedback_surveys:
        items.extend(await _feedback_items(user, settings))

    store = getattr(request.app.state, "submission_store", None)
    if store is not None and is_member(user, settings.ops_allowed_teams_list):
        try:
            items.append({"url": attn.OPS_APP_URL,
                          "count": await store.open_review_count(),
                          "label": attn.OPS_LABEL})
        except Exception as exc:  # noqa: BLE001
            log.warning("attention count failed (ops) for %s: %s",
                        user.get("userName"), exc)
    return items


def _analytics_feedback_viewer(user: dict[str, Any], settings: Settings) -> bool:
    """The Analytics tile for the Feedback page's teams (decision 8)."""
    from analytics.router import feedback_viewer

    return feedback_viewer(user, settings)


async def _feedback_items(user: dict[str, Any], settings: Settings) -> list[dict[str, Any]]:
    from feedback import config as fb_cfg
    from feedback import views as fb_views
    from feedback.alerts import response_path

    groups = []
    if is_member(user, settings.mentor_admin_allowed_teams_list):
        groups.append((fb_cfg.SURVEY_MENTORING, fb_cfg.SURVEY_EVALUATION))
    if is_member(user, settings.ops_allowed_teams_list):
        groups.append((fb_cfg.SURVEY_EVENT,))
    out: list[dict[str, Any]] = []
    if not groups:
        return out
    client = client_for(settings, user)
    for keys in groups:
        try:
            count, oldest = await fb_views.oldest_open(client, keys)
        except Exception as exc:  # noqa: BLE001 — a row never breaks the portal
            log.warning("attention count failed (feedback) for %s: %s",
                        user.get("userName"), exc)
            continue
        if count and oldest:
            url = response_path(oldest)
            out.append({"url": url, "kind": "feedback", "count": count,
                        "label": "Feedback to follow up"})
    return out


# --- the new home page: Today and My clients (HOME_V2, phase 2) ---------------

#: How far ahead the Today section's "Coming up" line looks, plus a day's
#: margin for every UTC offset; the browser picks the member's own days.
HOME_SESSION_DAYS_AHEAD = 8


def _home_client_name(row: dict[str, Any]) -> str:
    """The name a mentor knows the client by: the company, else the client
    profile, else the engagement's own name."""
    return row.get("company") or row.get("client") or row.get("name") or "(unnamed)"


def _home_mentoring(result: dict[str, Any]) -> dict[str, Any]:
    """Client Management's own list (``sessions.service.list_records``, read
    as the member) cut down to what Today and My clients show.

    My clients: the engagements in an active status (``ACTIVE_CLIENT_STATUSES``,
    Doug's ruling 2026-09-29; phase 2 question 1, option A), each marked
    ``coMentor`` when its mentor is not the member's own profile. Today: every
    Scheduled session of any of the member's engagements, from 36 hours ago to
    ``HOME_SESSION_DAYS_AHEAD`` days ahead, as UTC stamps; the browser decides
    which fall on the member's today. The next session per client comes from
    those same sessions, never ``CEngagement.nextSessionDateTime``."""
    from datetime import datetime, timedelta, timezone

    from assignments.service import ACTIVE_CLIENT_STATUSES

    if result.get("profileChoice", {}).get("blocked"):
        return {"profile": "blocked", "clients": [], "sessions": []}
    if result.get("profileFound") is False:
        return {"profile": "none", "clients": [], "sessions": []}
    own = result.get("profileId")
    until = (datetime.now(timezone.utc) + timedelta(days=HOME_SESSION_DAYS_AHEAD)).strftime(
        "%Y-%m-%d %H:%M:%S")
    clients: list[dict[str, Any]] = []
    sessions: list[dict[str, Any]] = []
    for row in result.get("records") or []:
        name = _home_client_name(row)
        scheduled = [s for s in row.get("upcomingSessions") or [] if s.get("status") == "Scheduled"]
        for s in scheduled:
            if (s.get("dateStart") or "") <= until:
                sessions.append({**s, "recordId": row["id"], "client": name})
        if row.get("status") in ACTIVE_CLIENT_STATUSES:
            clients.append({
                "id": row["id"],
                "name": name,
                "status": row.get("status"),
                "lastContact": row.get("lastContact"),
                "assignedDate": row.get("engagementAssignedDate"),
                "coMentor": bool(own and row.get("mentorId") and row["mentorId"] != own),
                "sessions": [s.get("dateStart") for s in scheduled if s.get("dateStart")],
            })
    sessions.sort(key=lambda s: s.get("dateStart") or "")
    return {"profile": "found", "clients": clients, "sessions": sessions}


@router.get("/home/mentoring")
async def home_mentoring(request: Request) -> dict:
    """Today and My clients for the new home page (prds/home-page-plan.md
    § 4.1; phase 2 question 5, option A). One call of Client Management's own
    list, as the member: their token, their ACL, owned and co-mentored. Not
    there while ``HOME_V2`` is off; refused to a member outside the mentor
    team, whose page draws neither section."""
    settings = get_settings()
    if not settings.home_v2:
        raise HTTPException(status_code=404, detail="Not found.")
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    if not is_member(user, settings.session_mentor_allowed_teams_list):
        raise HTTPException(status_code=403, detail="Your clients show here for members of the mentor team.")
    from core.espo import EspoError

    try:
        result = await _member_records(request, settings, user)
    except EspoError as exc:
        log.warning("home mentoring read failed for %s: %s", user.get("userName"), exc)
        raise HTTPException(status_code=502, detail="Your clients could not be read from the CRM just now.")
    return _home_mentoring(result)


#: How long one member's Client Management list is shared between the home
#: page's two reads (Today and My clients, and Needs you), which the page
#: starts together. Short: a sign-in, not a cache.
HOME_SHARED_READ_SECONDS = 20


async def _member_records(request: Request, settings: Settings,
                          user: dict[str, Any]) -> dict[str, Any]:
    """Client Management's own list for this member, read once and shared
    by the home page's two reads (phase 3, answer 8: Needs you adds no
    second engagement read). Kept on the application per sign-in token for
    ``HOME_SHARED_READ_SECONDS``; a failed read is never kept."""
    import time

    from sessions import service as sessions_service
    from sessions.config import MENTOR

    memo = request.app.state.__dict__.setdefault("home_shared_reads", {})
    now = time.monotonic()
    for k in [k for k, (at, _) in memo.items() if now - at > HOME_SHARED_READ_SECONDS]:
        memo.pop(k, None)
    key = (user.get("userId"), user.get("token"))
    hit = memo.get(key)
    if hit is None:
        task = asyncio.ensure_future(
            sessions_service.list_records(MENTOR, client_for(settings, user), user))
        memo[key] = hit = (now, task)
    try:
        return await asyncio.shield(hit[1])
    except Exception:
        memo.pop(key, None)
        raise


# --- the new home page: Needs you (HOME_V2, phase 3) --------------------------

#: How far back the Completed-session read looks (the Notes kind's window,
#: the widest of the two session kinds).
HOME_SESSION_DAYS_BACK = 30


async def _needs_sessions(settings: Settings, user: dict[str, Any],
                          names: dict[str, str], now) -> list[dict[str, Any]]:
    """The Notes and Summary rows: one read of the member's Completed
    sessions of the last ``HOME_SESSION_DAYS_BACK`` days, kept to their own
    engagements (an administrator's read would return everyone's)."""
    from datetime import timedelta

    from portal import needs
    from sessions.config import AI_SUMMARY_FIELD

    if not names:
        return []
    client = client_for(settings, user)
    try:
        fields = await client.metadata("entityDefs.CSession.fields") or {}
    except Exception:  # noqa: BLE001 — no summary field known: Notes only
        fields = {}
    summary = AI_SUMMARY_FIELD if isinstance(fields, dict) and AI_SUMMARY_FIELD in fields else None
    since = (now - timedelta(days=HOME_SESSION_DAYS_BACK)).strftime("%Y-%m-%d %H:%M:%S")
    select = "name,status,dateStart,engagementId,sessionNotes,nextSteps" + (f",{summary}" if summary else "")
    data = await client.list(
        "CSession",
        select=select,
        where=[{"type": "equals", "attribute": "status", "value": "Completed"},
               {"type": "after", "attribute": "dateStart", "value": since}],
        order_by="dateStart",
        order="desc",
        max_size=200,
    )
    mine = [s for s in data.get("list") or [] if s.get("engagementId") in names]
    return needs.session_items(mine, names, now, summary_field=summary)


async def _needs_email(settings: Settings, user: dict[str, Any]) -> tuple[list[dict[str, Any]], Optional[int]]:
    """The Email rows and the My Email badge's unread count, from ONE run
    of My Email's own inbox (answer 3). Nothing where My Email is not open
    to this member."""
    from datetime import datetime, timezone

    from comms import service as comms_service
    from myemail import service as myemail_service
    from portal import needs

    if not settings.gmail_sync or not any(
        is_member(user, getattr(settings, attr))
        for attr in ("session_mentor_allowed_teams_list",
                     "session_partner_allowed_teams_list",
                     "session_sponsor_allowed_teams_list")):
        return [], None
    store = comms_service.get_store(settings)
    if store is None:
        return [], None
    data = await myemail_service.build_inbox(settings, client_for(settings, user), store, user)
    convs = data.get("conversations") or []
    unread = sum(1 for c in convs if c.get("unread"))
    return needs.email_items(convs, datetime.now(timezone.utc)), unread


@router.get("/home/needs")
async def home_needs(request: Request) -> dict:
    """Needs you for the new home page (prds/home-page-plan.md § 4.2; phase 3,
    answer 8: its own read, so a failure here never takes Today down). Every
    kind is read as the member and fails on its own: a kind whose read fails
    is left out with a logged warning, and named in ``unavailable``.

    ``items``: the rows, most urgent first (``portal.needs.ordered``).
    ``unreadTotal``: My Email's unread count from the same inbox run, so the
    page badges My Email without a second run; null when not read."""
    from datetime import datetime, timezone

    from portal import needs

    settings = get_settings()
    if not settings.home_v2:
        raise HTTPException(status_code=404, detail="Not found.")
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    now = datetime.now(timezone.utc)
    items: list[dict[str, Any]] = []
    unavailable: list[str] = []

    def failed(kind: str, exc: BaseException) -> None:
        log.warning("needs you: %s failed for %s: %s", kind, user.get("userName"), exc)
        unavailable.append(kind)

    async def mentoring() -> None:
        if not is_member(user, settings.session_mentor_allowed_teams_list):
            return
        try:
            mine = _home_mentoring(await _member_records(request, settings, user))
        except Exception as exc:  # noqa: BLE001 — this kind only
            failed("clients", exc)
            return
        clients = mine["clients"]
        items.extend(needs.no_contact_items(clients, now, settings.home_no_contact_days))
        items.extend(needs.new_items(clients, now))
        names = {c["id"]: c["name"] for c in clients}
        try:
            items.extend(await _needs_sessions(settings, user, names, now))
        except Exception as exc:  # noqa: BLE001
            failed("sessions", exc)

    async def email() -> Optional[int]:
        try:
            rows, unread = await _needs_email(settings, user)
        except Exception as exc:  # noqa: BLE001
            failed("email", exc)
            return None
        items.extend(rows)
        return unread

    async def staff() -> None:
        try:
            items.extend(needs.staff_items(await _attention_items(request, user, settings)))
        except Exception as exc:  # noqa: BLE001
            failed("staff", exc)

    _, unread, _ = await asyncio.gather(mentoring(), email(), staff())
    return {"items": needs.ordered(items), "unreadTotal": unread,
            "unavailable": sorted(unavailable)}


# --- per-user preferences (F3) ------------------------------------------------

#: The preferences a member may store. A whitelist, so the table holds only
#: what some screen reads back: the portal calendar's filter and the home
#: page's sections.
PREFERENCE_KEYS = frozenset({
    "events.calendar",
    # The new home page's collapsed and hidden sections (HOME_V2),
    # {"collapsed": [...], "hidden": [...]} of section keys.
    "home.sections",
    # The member's text size on every application page: "standard",
    # "large" or "larger" (/shared/textsize.js; Doug, 11-18-26, option A).
    "ui.textSize",
})
#: A preference is a few choices, never a document.
MAX_PREFERENCE_BYTES = 2048


class PreferenceIn(BaseModel):
    value: Any = None


def _preference_key(key: str) -> str:
    if key not in PREFERENCE_KEYS:
        raise HTTPException(status_code=404, detail="Unknown preference.")
    return key


@router.get("/preferences/{key}")
async def get_preference(key: str, request: Request) -> dict:
    """The member's saved value, or null. Without a database there is nowhere
    to keep one, so the answer is null and ``stored`` says why."""
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    key = _preference_key(key)
    store = getattr(request.app.state, "submission_store", None)
    if store is None:
        return {"key": key, "value": None, "stored": False}
    try:
        value = await store.get_user_preference(user.get("userId") or "", key)
    except Exception as exc:  # noqa: BLE001 — a preference never breaks the portal
        log.warning("preference read failed (%s) for %s: %s", key, user.get("userName"), exc)
        return {"key": key, "value": None, "stored": False}
    return {"key": key, "value": value, "stored": True}


@router.put("/preferences/{key}")
async def put_preference(key: str, body: PreferenceIn, request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    key = _preference_key(key)
    import json

    if len(json.dumps(body.value)) > MAX_PREFERENCE_BYTES:
        raise HTTPException(status_code=400, detail="That preference is too large to save.")
    store = getattr(request.app.state, "submission_store", None)
    if store is None:
        raise HTTPException(
            status_code=503,
            detail="Preferences cannot be saved on this deployment (it has no database).",
        )
    await store.set_user_preference(user.get("userId") or "", key, body.value)
    return {"key": key, "value": body.value, "stored": True}


@router.post("/logout")
async def logout(request: Request) -> dict:
    clear_session(request)
    return {"status": "ok"}


# --- the new home page: At the chapter (HOME_V2, phase 4) ---------------------

#: How long the chapter's figures and its running call campaigns are kept for
#: every member (phase 4, answer 8): they are the same for everyone.
HOME_CHAPTER_SECONDS = 15 * 60


def _org_client(settings: Settings):
    """The chapter-wide CRM key's client (the Mentors directory's
    availability is the precedent): totals with no names. None where there
    is no key."""
    if settings.espo_dry_run or not settings.espo_api_key:
        return None
    from core.espo import EspoClient

    return EspoClient(settings.espo_base_url, settings.espo_api_key,
                      settings.request_timeout_seconds)


async def _shared(request: Request, key: str, load):
    """One value for the whole application, kept ``HOME_CHAPTER_SECONDS``;
    concurrent first reads share one load, and a failed load is never kept."""
    import time

    memo = request.app.state.__dict__.setdefault("home_chapter_shared", {})
    now = time.monotonic()
    hit = memo.get(key)
    if hit is None or now - hit[0] > HOME_CHAPTER_SECONDS:
        hit = (now, asyncio.ensure_future(load()))
        memo[key] = hit
    try:
        return await asyncio.shield(hit[1])
    except Exception:
        if memo.get(key) is hit:
            memo.pop(key, None)
        raise


async def _year_sessions(client, since: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        data = await client.list(
            "CSession",
            select="dateStart,dateEnd,engagementId",
            where=[{"type": "equals", "attribute": "status", "value": "Completed"},
                   {"type": "after", "attribute": "dateStart", "value": since}],
            order_by="dateStart", order="asc", max_size=200, offset=offset,
        )
        page = data.get("list") or []
        rows.extend(page)
        if len(page) < 200 or len(rows) >= 20000:
            return rows
        offset += 200


@router.get("/home/chapter")
async def home_chapter(request: Request) -> dict:
    """At the chapter for the new home page (prds/home-page-plan.md § 4.1;
    phase 4). Three parts, each failing on its own and named in
    ``unavailable``: the chapter's figures for the calendar year (every
    member, the chapter-wide key, kept 15 minutes for everyone), the
    member's own (mentors, from Client Management's list shared with Today),
    and the asks (Running call campaigns naming the member's team)."""
    from datetime import datetime, timezone

    from portal import chapter

    settings = get_settings()
    if not settings.home_v2:
        raise HTTPException(status_code=404, detail="Not found.")
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    year, since = chapter.year_start(datetime.now(timezone.utc))
    out: dict[str, Any] = {"year": year, "chapter": None, "own": None, "asks": None,
                           "unavailable": []}

    def failed(part: str, exc: BaseException) -> None:
        log.warning("at the chapter: %s failed for %s: %s", part, user.get("userName"), exc)
        out["unavailable"].append(part)

    org = _org_client(settings)
    facts = None
    if org is not None:
        try:
            facts = await _shared(request, f"sessions:{since}", lambda: _facts(org, since))
            out["chapter"] = chapter.figures(facts)
        except Exception as exc:  # noqa: BLE001 — this part only
            failed("chapter", exc)

    if facts is not None and is_member(user, settings.session_mentor_allowed_teams_list):
        try:
            result = await _member_records(request, settings, user)
            if result.get("profileFound") and not result.get("profileChoice", {}).get("blocked"):
                mine = {r["id"] for r in result.get("records") or []}
                out["own"] = chapter.figures(facts, mine)
        except Exception as exc:  # noqa: BLE001
            failed("own", exc)

    if org is not None and settings.campaigns_active and settings.campaigns_calls:
        try:
            out["asks"] = await _asks(request, settings, user, org)
        except Exception as exc:  # noqa: BLE001
            failed("asks", exc)
    return out


async def _facts(client, since: str) -> list[tuple[str, float]]:
    from portal import chapter

    return chapter.session_facts(await _year_sessions(client, since))


async def _asks(request: Request, settings: Settings, user: dict[str, Any], org) -> list[dict[str, Any]]:
    """The Running call campaigns naming one of the member's teams, each
    with the calls still to make, read as the member (as the Calls tab
    reads them)."""
    from campaigns import calls
    from campaigns import config as ccfg
    from portal import chapter

    campaigns = await _shared(request, "call-campaigns", lambda: calls.running_call_campaigns(org))
    default = settings.campaigns_allowed_teams_list
    mine = [c for c in campaigns if calls.may_call(user, calls.campaign_team_names(c, default))]
    if not mine:
        return []
    client = client_for(settings, user)
    rows = []
    for c in mine:
        touches: list[dict[str, Any]] = []
        offset = 0
        while True:
            data = await client.list(
                ccfg.TOUCH, select="touchStatus,assignedUserId", max_size=200, offset=offset,
                where=[{"type": "equals", "attribute": "outreachCampaignId", "value": c["id"]},
                       {"type": "equals", "attribute": "touchStatus", "value": ccfg.TOUCH_PLANNED}],
            )
            page = data.get("list") or []
            touches.extend(page)
            if len(page) < 200 or len(touches) >= 5000:
                break
            offset += 200
        n = chapter.calls_to_make(touches, user.get("userId") or "")
        if n:
            rows.append(chapter.ask_row(c, n))
    rows.sort(key=lambda r: (-r["calls"], r["name"]))
    return rows
