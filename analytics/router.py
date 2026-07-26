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
from pydantic import BaseModel, Field

from assignments import auth
from assignments.auth import clear_session, current_user, is_member
from assignments.espo_user import client_for
from core import action_log
from core.config import Settings, get_settings
from core.espo import EspoClient, EspoError, forbidden_hint, is_forbidden

from . import computed  # noqa: F401 — registers operational/computed metrics
from . import dashboard  # noqa: F401 — importing registers the metrics + seeded page
from .builder import (
    AGG_KINDS,
    builder_spec,
    default_viz_for_shape,
    shape_for_kind,
)
from .registry import (
    COMPATIBLE_VIZ,
    METRIC_REGISTRY,
    PAGE_REGISTRY,
    MetricSpec,
    PageSpec,
    RecordRef,
    get_metric,
    get_page,
)
from .service import (
    build_time_range,
    invalidate_page_cache,
    page_spec_from_row,
    render_page,
)

log = logging.getLogger("cbm_intake.analytics")

router = APIRouter(prefix="/analytics/api", tags=["analytics"])

# CRM entities offered in the builder (entity, display label). Curated so the
# picker shows the domain records, not every EspoCRM scope.
BUILDER_ENTITIES = [
    ("CEngagement", "Client Engagements"),
    ("CMentorProfile", "Mentors"),
    ("Account", "Companies"),
    ("Contact", "Contacts"),
    ("CPartnerProfile", "Partners"),
    ("CSponsorProfile", "Funders"),
    ("CSession", "Sessions"),
    ("CContribution", "Contributions"),
    ("CInformationRequest", "Information Requests"),
]
_BUILDER_ENTITY_SET = {e for e, _ in BUILDER_ENTITIES}

# Field types the builder surfaces, tagged by role.
_NUMERIC_TYPES = {"int", "float", "currency", "currencyConverted"}
_DATE_TYPES = {"date", "datetime", "datetimeOptional"}
_ENUM_TYPES = {"enum", "multiEnum"}
_FIELD_TYPES = _NUMERIC_TYPES | _DATE_TYPES | _ENUM_TYPES | {
    "varchar", "text", "bool", "url", "phone", "email",
}


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


def _sub_store(request: Request):
    """The durable submission store — feeds store/computed metrics (Phase D)."""
    return getattr(request.app.state, "submission_store", None)


async def _db_metric_specs(store) -> dict[str, MetricSpec]:
    """All DB (builder) metrics as {key: MetricSpec}. Empty without a store."""
    if store is None:
        return {}
    try:
        rows = await store.list_metrics()
    except Exception as exc:  # noqa: BLE001 — a store hiccup falls back to code metrics
        log.warning("analytics: list_metrics failed: %s", exc)
        return {}
    return {r["key"]: builder_spec(r) for r in rows}


def _make_lookup(db_specs: dict[str, MetricSpec]):
    """DB metrics take precedence, falling back to the code registry."""

    def lookup(key: str) -> Optional[MetricSpec]:
        return db_specs.get(key) or get_metric(key)

    return lookup


async def _all_page_specs(store) -> list[PageSpec]:
    """Authored DB pages + code-seeded pages. A DB page OVERRIDES a built-in of
    the same key (a "customized" built-in), so the seeded pages are editable."""
    out: list[PageSpec] = []
    seen: set = set()
    if store is not None:
        try:
            rows = await store.list_pages()
        except Exception as exc:  # noqa: BLE001
            log.warning("analytics: list_pages failed: %s", exc)
            rows = []
        for r in rows:
            out.append(page_spec_from_row(r))
            seen.add(r.get("key"))
    for p in PAGE_REGISTRY.values():
        if p.key not in seen:
            out.append(p)
    return out


async def _resolve_page(key: str, store) -> Optional[PageSpec]:
    # DB override wins over the built-in of the same key.
    if store is not None:
        row = await store.get_page_by_key(key)
        if row is not None:
            return page_spec_from_row(row)
    return get_page(key)


async def _page_summaries(user: dict, settings: Settings, store) -> list[dict]:
    return [
        {"key": p.key, "title": p.title, "scope": p.scope, "subtitle": p.subtitle}
        for p in await _all_page_specs(store)
        if p.scope == "system" and _can_view_page(user, p, settings)
    ]


@router.post("/logout")
async def logout(request: Request) -> dict:
    clear_session(request)
    return {"status": "ok"}


def _can_author(user: dict, settings: Settings) -> bool:
    return is_member(user, settings.analytics_admin_allowed_teams_list)


@router.get("/session")
async def session(request: Request) -> dict:
    user = _require_user(request)
    settings = get_settings()
    store = _store(request)
    return {
        "userName": user["userName"],
        "name": user["name"],
        "isAdmin": user["isAdmin"],
        "crmUrl": settings.espo_base_url,
        "pages": await _page_summaries(user, settings, store),
        # Whether to show the authoring UI (member of the admin team / admin).
        "canAuthor": _can_author(user, settings),
        # Authoring needs the durable store (definitions live there).
        "authoringAvailable": store is not None,
    }


@router.get("/pages")
async def pages(request: Request) -> dict:
    user = _require_user(request)
    return {"pages": await _page_summaries(user, get_settings(), _store(request))}


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
    store = _store(request)
    page = await _resolve_page(key, store)
    if page is None or page.scope != "system":
        raise HTTPException(status_code=404, detail="Analytics page not found.")
    if not _can_view_page(user, page, settings):
        raise HTTPException(status_code=403, detail="You don't have access to this analytics page.")
    time_range = build_time_range(
        range_key or page.default_range, custom_from=frm, custom_to=to
    )
    espo = _system_client(settings)
    lookup = _make_lookup(await _db_metric_specs(store))
    try:
        if force and store is not None:
            await invalidate_page_cache(
                page, store=store, time_range=time_range, metric_lookup=lookup
            )
        return await render_page(
            page,
            user=user,
            settings=settings,
            espo=espo,
            store=store,
            time_range=time_range,
            force=force,
            metric_lookup=lookup,
            submission_store=_sub_store(request),
        )
    except Exception as exc:  # noqa: BLE001 — per-metric errors are already handled inside
        log.warning("analytics render failed for %s: %s", key, exc)
        raise HTTPException(status_code=502, detail="Could not load analytics — try again.")


@router.get("/portal")
async def portal_dashboard(request: Request) -> dict:
    """The dashboard shown on the portal home (Phase D). Renders the system page
    flagged ``portal_dashboard`` that the signed-in user may view — gated by that
    page's team gate (or the analytics view team), so non-analytics staff simply
    get ``available: false`` and the portal shows no dashboard."""
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    settings = get_settings()
    store = _store(request)
    candidates = [
        p for p in await _all_page_specs(store)
        if p.scope == "system" and p.portal_dashboard and _can_view_page(user, p, settings)
    ]
    if not candidates:
        return {"available": False}
    page = candidates[0]
    time_range = build_time_range(page.default_range)
    lookup = _make_lookup(await _db_metric_specs(store))
    body = await render_page(
        page, user=user, settings=settings, espo=_system_client(settings),
        store=store, time_range=time_range, metric_lookup=lookup,
        submission_store=_sub_store(request),
    )
    body["available"] = True
    body["crmUrl"] = settings.espo_base_url
    return body


# =============================================================================
# Record-scoped analytics (Phase C) — embedded on a record's detail tab.
# =============================================================================
def _signed_in(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return user


def _can_view_record_page(user: dict, page: PageSpec, settings: Settings) -> bool:
    # For a record page the RECORD's ACL is the gate (checked by the parent read);
    # an author may still add an explicit team gate on top.
    return is_member(user, list(page.team_gate)) if page.team_gate else True


def _record_crm_failure(request: Request, exc: EspoError) -> HTTPException:
    if auth.session_expired(exc):
        clear_session(request)
        return HTTPException(status_code=401, detail="Your session has expired — please sign in again.")
    if is_forbidden(exc):
        return HTTPException(status_code=403, detail="You don't have permission to view this record.")
    log.warning("analytics record read failed: %s", exc)
    return HTTPException(status_code=502, detail="Could not load this record's analytics — try again.")


@router.get("/record/{entity}/{record_id}")
async def record_view(
    entity: str,
    record_id: str,
    request: Request,
    page_key: Optional[str] = Query(None, alias="page"),
    range_key: Optional[str] = Query(None, alias="range"),
) -> dict:
    """Record-scoped analytics for one CRM record — embedded on that record's
    detail (e.g. the Mentor Administration Analytics tab). Runs AS THE USER: the
    parent record is read as them first (the ACL gate), and every metric query is
    ACL-bounded. The gate is the record ACL + per-panel visibility — NOT the
    analytics view team, so any staffer who can open the record sees its
    analytics."""
    user = _signed_in(request)
    settings = get_settings()
    if entity not in _BUILDER_ENTITY_SET:
        raise HTTPException(status_code=404, detail="Unknown record type.")
    client = client_for(settings, user)
    try:
        rec = await client.get(entity, record_id, select="id,name")
    except EspoError as exc:
        raise _record_crm_failure(request, exc)
    store = _store(request)
    pages = [
        p for p in await _all_page_specs(store)
        if p.scope == entity and _can_view_record_page(user, p, settings)
    ]
    record = {"entity": entity, "id": record_id, "name": rec.get("name")}
    if not pages:
        return {"available": False, "record": record, "pages": []}
    selected = next((p for p in pages if p.key == page_key), pages[0])
    time_range = build_time_range(range_key or selected.default_range)
    lookup = _make_lookup(await _db_metric_specs(store))
    ref = RecordRef(entity=entity, record_id=record_id, value=record_id)
    body = await render_page(
        selected, user=user, settings=settings, espo=client, store=store,
        time_range=time_range, record=ref, metric_lookup=lookup,
        submission_store=_sub_store(request),
    )
    body["available"] = True
    body["record"] = record
    body["crmUrl"] = settings.espo_base_url
    body["pages"] = [{"key": p.key, "title": p.title} for p in pages]
    return body


# =============================================================================
# Authoring (Phase B) — gated on ANALYTICS_ADMIN_ALLOWED_TEAMS; needs the store.
# =============================================================================
def _admin(request: Request) -> dict:
    return _require_user(request, admin=True)


def _admin_store(request: Request):
    store = _store(request)
    if store is None:
        raise HTTPException(
            status_code=503,
            detail="Authoring needs the analytics database (DATABASE_URL) — not configured.",
        )
    return store


def _slug(text: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "_", (text or "").strip().lower()).strip("_")


def _humanize(name: str) -> str:
    import re

    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    s = s.replace("_", " ").strip()
    return s[:1].upper() + s[1:] if s else name


async def _log_authoring(user: dict, action: str, key: str, summary: str) -> None:
    try:
        await action_log.log_action(
            app=action_log.APP_ANALYTICS,
            category=action_log.CAT_CONFIG,
            action=action,
            parent_type="Analytics",
            parent_id=key,
            summary=summary,
            actor_name=user.get("name") or user["userName"],
        )
    except Exception as exc:  # noqa: BLE001 — reporting side channel
        log.warning("analytics action-log failed (%s %s): %s", action, key, exc)


@router.get("/admin/entities")
async def admin_entities(request: Request) -> dict:
    _admin(request)
    return {"entities": [{"entity": e, "label": lbl} for e, lbl in BUILDER_ENTITIES]}


@router.get("/admin/fields")
async def admin_fields(request: Request, entity: str = Query(...)) -> dict:
    """Metadata-driven field list for the builder (types, labels, enum options)."""
    _admin(request)
    if entity not in _BUILDER_ENTITY_SET:
        raise HTTPException(status_code=400, detail=f"Unsupported entity {entity!r}.")
    settings = get_settings()
    espo = _system_client(settings)
    if espo is None:
        return {"fields": [], "reason": "CRM metadata isn't available on this deployment."}
    try:
        defs = await espo.metadata(f"entityDefs.{entity}.fields")
    except EspoError as exc:
        log.warning("analytics fields metadata failed for %s: %s", entity, exc)
        raise HTTPException(status_code=502, detail="Could not read CRM field metadata.")
    fields = []
    for name, spec in (defs or {}).items():
        ftype = (spec or {}).get("type")
        if ftype not in _FIELD_TYPES:
            continue
        fields.append({
            "name": name,
            "type": ftype,
            "label": _humanize(name),
            "numeric": ftype in _NUMERIC_TYPES,
            "date": ftype in _DATE_TYPES,
            "enum": ftype in _ENUM_TYPES,
            "options": (spec or {}).get("options") if ftype in _ENUM_TYPES else None,
        })
    fields.sort(key=lambda f: f["label"])
    # belongsTo links → candidate context params ({link}Id) for record-scoped
    # metrics (the field that equals a parent record's id). Best-effort.
    links = []
    try:
        link_defs = await espo.metadata(f"entityDefs.{entity}.links")
        for name, spec in (link_defs or {}).items():
            if (spec or {}).get("type") == "belongsTo":
                links.append({"param": name + "Id", "label": _humanize(name),
                              "foreign": (spec or {}).get("entity")})
    except EspoError:
        pass
    links.sort(key=lambda ln: ln["label"])
    return {"entity": entity, "fields": fields, "links": links}


class MetricIn(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    entity: str
    definition: dict = Field(default_factory=dict)  # {filters, aggregation, time_field}
    default_viz: Optional[str] = None
    cache_mode: str = "cached"
    applies_to: list[str] = Field(default_factory=lambda: ["system"])
    context_param: Optional[str] = None


def _metric_values_from(body: MetricIn) -> dict:
    """Validate + normalize a MetricIn into a stored metric row's values.
    Server derives result_shape + time_aware from the aggregation kind."""
    if body.entity not in _BUILDER_ENTITY_SET:
        raise HTTPException(status_code=422, detail=f"Unsupported entity {body.entity!r}.")
    agg = (body.definition or {}).get("aggregation") or {}
    kind = agg.get("kind")
    if kind not in AGG_KINDS:
        raise HTTPException(
            status_code=422,
            detail=f"Aggregation kind must be one of: {', '.join(AGG_KINDS)}.",
        )
    if kind in ("sum", "avg", "group_by") and not agg.get("field"):
        raise HTTPException(status_code=422, detail=f"A {kind} metric needs a field.")
    shape = shape_for_kind(kind)
    viz = body.default_viz or default_viz_for_shape(shape)
    if viz not in COMPATIBLE_VIZ.get(shape, ()):
        viz = default_viz_for_shape(shape)
    if body.cache_mode not in ("live", "cached"):
        raise HTTPException(status_code=422, detail="cache_mode must be 'live' or 'cached'.")
    applies = [a for a in (body.applies_to or ["system"]) if a] or ["system"]
    for a in applies:
        if a != "system" and a not in _BUILDER_ENTITY_SET:
            raise HTTPException(status_code=422, detail=f"Unknown record type {a!r} in applies-to.")
    record_scoped = any(a != "system" for a in applies)
    ctx_param = (body.context_param or "").strip()
    if record_scoped and not ctx_param:
        raise HTTPException(
            status_code=422,
            detail="A record-scoped metric needs a record link field "
                   "(e.g. mentorProfileId — the field that equals the record's id).",
        )
    return {
        "name": body.name.strip(),
        "description": body.description or "",
        "source": "crm",
        "result_shape": shape,
        "default_viz": viz,
        "entity": body.entity,
        "definition": body.definition or {},
        "applies_to": applies,
        "context_param": ctx_param or None,
        "cache_mode": body.cache_mode,
        "refresh_seconds": 0,
        "time_aware": kind == "bucket",
    }


@router.get("/admin/metrics")
async def admin_list_metrics(request: Request) -> dict:
    _admin(request)
    store = _admin_store(request)
    metrics = await store.list_metrics()
    db_keys = {m["key"] for m in metrics}
    # Annotate each with how many pages use it, and whether it customizes a
    # built-in (so the UI shows "Reset to default" rather than "Delete").
    for m in metrics:
        m["usedBy"] = await store.metric_key_in_use(m["key"])
        m["overridesBuiltin"] = m["key"] in METRIC_REGISTRY
    # Built-in metrics are shown so authors can place/customize them. A built-in
    # is `customizable` when it has a builder definition (its logic fits the
    # builder); `customized` means a DB override already exists.
    code = [
        {"key": s.key, "name": s.name, "result_shape": s.shape,
         "default_viz": s.default_viz, "applies_to": list(s.applies_to),
         "source": "code", "builtin": True,
         "customizable": s.builder_definition is not None,
         "customized": s.key in db_keys}
        for s in METRIC_REGISTRY.values()
    ]
    return {"metrics": metrics, "builtins": code, "recordTypes": [
        {"entity": e, "label": lbl} for e, lbl in BUILDER_ENTITIES]}


@router.post("/admin/metrics")
async def admin_create_metric(body: MetricIn, request: Request) -> dict:
    user = _admin(request)
    store = _admin_store(request)
    values = _metric_values_from(body)
    key = _slug(values["name"])
    if not key:
        raise HTTPException(status_code=422, detail="A metric needs a name.")
    if key in METRIC_REGISTRY or await store.get_metric_by_key(key):
        raise HTTPException(status_code=409, detail=f"A metric with key {key!r} already exists.")
    values["key"] = key
    values["created_by"] = user["userName"]
    values["updated_by"] = user["userName"]
    row = await store.create_metric(values)
    await _log_authoring(user, action_log.ACT_ANALYTICS_METRIC_SAVED, key, f"Created metric “{values['name']}”")
    return {"metric": row}


@router.put("/admin/metrics/{metric_id}")
async def admin_update_metric(metric_id: str, body: MetricIn, request: Request) -> dict:
    user = _admin(request)
    store = _admin_store(request)
    existing = await store.get_metric(metric_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Metric not found.")
    values = _metric_values_from(body)  # key is immutable
    values["updated_by"] = user["userName"]
    row = await store.update_metric(metric_id, values)
    await _log_authoring(user, action_log.ACT_ANALYTICS_METRIC_SAVED, existing["key"], f"Updated metric “{values['name']}”")
    return {"metric": row}


@router.delete("/admin/metrics/{metric_id}")
async def admin_delete_metric(metric_id: str, request: Request) -> dict:
    user = _admin(request)
    store = _admin_store(request)
    existing = await store.get_metric(metric_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Metric not found.")
    used = await store.metric_key_in_use(existing["key"])
    # A customized built-in can always be reset (the built-in takes over); a
    # purely custom metric that's in use must be removed from its page(s) first.
    if used and existing["key"] not in METRIC_REGISTRY:
        raise HTTPException(
            status_code=409,
            detail=f"This metric is used by page(s): {', '.join(used)}. Remove it there first.",
        )
    await store.delete_metric(metric_id)
    await _log_authoring(user, action_log.ACT_ANALYTICS_METRIC_DELETED, existing["key"], f"Deleted metric “{existing.get('name')}”")
    return {"status": "deleted"}


class PreviewIn(BaseModel):
    entity: str
    definition: dict = Field(default_factory=dict)
    context_param: Optional[str] = None
    range_key: Optional[str] = Field(None, alias="range")

    model_config = {"populate_by_name": True}


@router.post("/admin/preview")
async def admin_preview(body: PreviewIn, request: Request) -> dict:
    """Compute a draft metric live (no save) so the builder can show a preview."""
    _admin(request)
    if body.entity not in _BUILDER_ENTITY_SET:
        raise HTTPException(status_code=422, detail=f"Unsupported entity {body.entity!r}.")
    agg = (body.definition or {}).get("aggregation") or {}
    kind = agg.get("kind")
    if kind not in AGG_KINDS:
        raise HTTPException(status_code=422, detail=f"Aggregation kind must be one of: {', '.join(AGG_KINDS)}.")
    shape = shape_for_kind(kind)
    settings = get_settings()
    row = {
        "key": "__preview__", "name": "Preview", "entity": body.entity,
        "definition": body.definition or {}, "result_shape": shape,
        "default_viz": default_viz_for_shape(shape), "source": "crm",
        "applies_to": ["system"], "context_param": body.context_param,
        "cache_mode": "live", "refresh_seconds": 0, "time_aware": kind == "bucket",
    }
    spec = builder_spec(row)
    espo = _system_client(settings)
    if espo is None:
        raise HTTPException(status_code=503, detail="No CRM data source on this deployment.")
    from .registry import MetricContext

    tr = build_time_range(body.range_key or "last12mo")
    ctx = MetricContext(settings=settings, espo=espo, store=None, time_range=tr)
    result = await spec.compute(ctx)
    from datetime import datetime, timezone

    return {
        "shape": result.shape, "viz": row["default_viz"],
        "result": result.as_payload(computed_at=datetime.now(timezone.utc), cached=False),
    }


class PanelIn(BaseModel):
    title: str = ""
    metric_key: str
    viz: Optional[str] = None
    width: int = 4
    visibility: list[str] = Field(default_factory=list)
    config: dict = Field(default_factory=dict)


class PageIn(BaseModel):
    title: str = Field(min_length=1)
    subtitle: str = ""
    scope: str = "system"                 # 'system' or a record entity type (Phase C)
    default_range: str = "last12mo"
    team_gate: list[str] = Field(default_factory=list)
    portal_dashboard: bool = False
    panels: list[PanelIn] = Field(default_factory=list)


async def _page_values_from(body: PageIn, store) -> dict:
    scope = body.scope or "system"
    if scope != "system" and scope not in _BUILDER_ENTITY_SET:
        raise HTTPException(status_code=422, detail=f"Unknown page scope {scope!r}.")
    db_specs = await _db_metric_specs(store)
    lookup = _make_lookup(db_specs)
    panels = []
    for p in body.panels:
        spec = lookup(p.metric_key)
        if spec is None:
            raise HTTPException(status_code=422, detail=f"Unknown metric {p.metric_key!r}.")
        if scope != "system" and scope not in spec.applies_to:
            raise HTTPException(
                status_code=422,
                detail=f"Metric {p.metric_key!r} isn't available on a {scope} page.",
            )
        viz = p.viz if p.viz in COMPATIBLE_VIZ.get(spec.shape, ()) else spec.default_viz
        panels.append({
            "key": _slug(p.title) or p.metric_key,
            "title": p.title or spec.name,
            "metric_key": p.metric_key,
            "viz": viz,
            "width": max(3, min(12, int(p.width or 4))),
            "visibility": p.visibility or None,
            "config": p.config or {},
        })
    return {
        "scope": scope,
        "title": body.title.strip(),
        "subtitle": body.subtitle or "",
        "default_range": body.default_range or "last12mo",
        "team_gate": body.team_gate or [],
        "portal_dashboard": bool(body.portal_dashboard),
        "panels": panels,
    }


@router.get("/admin/pages")
async def admin_list_pages(request: Request) -> dict:
    _admin(request)
    store = _admin_store(request)
    db_pages = await store.list_pages()
    db_keys = {p["key"] for p in db_pages}
    for p in db_pages:
        p["overridesBuiltin"] = p["key"] in PAGE_REGISTRY
    return {
        "pages": db_pages,
        # Built-in pages are always customizable (materialized to a DB copy on
        # first Edit); `customized` means an override already exists.
        "builtins": [
            {"key": p.key, "title": p.title, "scope": p.scope, "builtin": True,
             "customizable": True, "customized": p.key in db_keys}
            for p in PAGE_REGISTRY.values()
        ],
    }


@router.post("/admin/pages")
async def admin_create_page(body: PageIn, request: Request) -> dict:
    user = _admin(request)
    store = _admin_store(request)
    values = await _page_values_from(body, store)
    key = _slug(values["title"])
    if not key:
        raise HTTPException(status_code=422, detail="A page needs a title.")
    if key in PAGE_REGISTRY or await store.get_page_by_key(key):
        raise HTTPException(status_code=409, detail=f"A page with key {key!r} already exists.")
    values["key"] = key
    values["created_by"] = user["userName"]
    values["updated_by"] = user["userName"]
    row = await store.create_page(values)
    await _log_authoring(user, action_log.ACT_ANALYTICS_PAGE_SAVED, key, f"Created page “{values['title']}”")
    return {"page": row}


@router.put("/admin/pages/{page_id}")
async def admin_update_page(page_id: str, body: PageIn, request: Request) -> dict:
    user = _admin(request)
    store = _admin_store(request)
    existing = await store.get_page(page_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    values = await _page_values_from(body, store)  # key immutable
    values["updated_by"] = user["userName"]
    row = await store.update_page(page_id, values)
    await _log_authoring(user, action_log.ACT_ANALYTICS_PAGE_SAVED, existing["key"], f"Updated page “{values['title']}”")
    return {"page": row}


@router.delete("/admin/pages/{page_id}")
async def admin_delete_page(page_id: str, request: Request) -> dict:
    user = _admin(request)
    store = _admin_store(request)
    existing = await store.get_page(page_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    await store.delete_page(page_id)
    await _log_authoring(user, action_log.ACT_ANALYTICS_PAGE_DELETED, existing["key"], f"Deleted page “{existing.get('title')}”")
    return {"status": "deleted"}


# --- customize a built-in (materialize an editable DB copy that overrides it) ---
@router.post("/admin/pages/customize/{key}")
async def customize_page(key: str, request: Request) -> dict:
    """Copy a built-in page into an editable DB row (same key, which overrides
    the built-in). Idempotent: if already customized, returns the existing row.
    This is how a seeded dashboard (e.g. the System page) becomes editable —
    add/remove/reorder panels, place your own metrics."""
    user = _admin(request)
    store = _admin_store(request)
    existing = await store.get_page_by_key(key)
    if existing is not None:
        return {"page": existing, "alreadyCustomized": True}
    code = get_page(key)
    if code is None:
        raise HTTPException(status_code=404, detail="Built-in page not found.")
    values = {
        "key": code.key, "scope": code.scope, "title": code.title,
        "subtitle": code.subtitle, "team_gate": list(code.team_gate),
        "portal_dashboard": bool(code.portal_dashboard), "default_range": code.default_range,
        "panels": [
            {"key": p.key, "title": p.title, "metric_key": p.metric_key, "viz": p.viz,
             "width": p.width, "visibility": list(p.visibility) if p.visibility else None,
             "config": p.config}
            for p in code.panels
        ],
        "created_by": user["userName"], "updated_by": user["userName"],
    }
    row = await store.create_page(values)
    await _log_authoring(user, action_log.ACT_ANALYTICS_PAGE_SAVED, key, f"Customized built-in page “{code.title}”")
    return {"page": row}


@router.post("/admin/metrics/customize/{key}")
async def customize_metric(key: str, request: Request) -> dict:
    """Copy a built-in metric into an editable builder DB metric (same key,
    which overrides the built-in). Only built-ins with a builder definition can
    be customized (store/computed built-ins can't be expressed by the builder)."""
    user = _admin(request)
    store = _admin_store(request)
    existing = await store.get_metric_by_key(key)
    if existing is not None:
        return {"metric": existing, "alreadyCustomized": True}
    spec = get_metric(key)
    if spec is None:
        raise HTTPException(status_code=404, detail="Built-in metric not found.")
    defn = spec.builder_definition
    if not defn:
        raise HTTPException(
            status_code=400,
            detail="This built-in metric can't be edited — its data isn't a simple "
                   "entity + filter + aggregation. You can still place it on a page.",
        )
    values = {
        "key": spec.key, "name": spec.name, "description": spec.description,
        "source": "crm", "result_shape": spec.shape, "default_viz": spec.default_viz,
        "entity": defn.get("entity"),
        "definition": {"filters": defn.get("filters", []),
                       "aggregation": defn.get("aggregation", {}),
                       "time_field": defn.get("time_field")},
        "applies_to": list(spec.applies_to), "context_param": None,
        "cache_mode": spec.cache_mode, "refresh_seconds": spec.refresh_seconds,
        "time_aware": spec.time_aware,
        "created_by": user["userName"], "updated_by": user["userName"],
    }
    row = await store.create_metric(values)
    await _log_authoring(user, action_log.ACT_ANALYTICS_METRIC_SAVED, key, f"Customized built-in metric “{spec.name}”")
    return {"metric": row}
