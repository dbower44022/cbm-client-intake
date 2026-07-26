"""The analytics engine: time-range building + metric resolution + page render.

``resolve_metric`` dispatches to the metric's ``compute`` (wrapped so a CRM
outage / missing grant / dry-run stub never 500s — it degrades to an
``unavailable`` result the panel shows as a message), applying the hybrid
cache: ``cached`` metrics are served from :class:`analytics.store.AnalyticsStore`
and recomputed on miss/expiry; ``live`` metrics always compute now.

``render_page`` resolves every panel the viewer may see (per-panel visibility on
top of the page gate) and returns the panel payloads for the frontend renderers.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from assignments.auth import is_member

from typing import Callable

from .registry import (
    MetricContext,
    MetricSpec,
    PageSpec,
    PanelSpec,
    RecordRef,
    TimeRange,
    get_metric,
    unavailable,
)

log = logging.getLogger("cbm_intake.analytics")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- time ranges -------------------------------------------------------------
# Preset key -> (label, days back). "all"/"ytd"/"quarter" are computed specially.
_RANGE_DAYS = {
    "last7d": ("Last 7 days", 7),
    "last30d": ("Last 30 days", 30),
    "last90d": ("Last 90 days", 90),
    "last12mo": ("Last 12 months", 365),
}
RANGE_PRESETS = ("last7d", "last30d", "last90d", "quarter", "ytd", "last12mo", "all")
DEFAULT_RANGE = "last12mo"


def _granularity(start: Optional[datetime], end: datetime) -> str:
    if start is None:
        return "month"
    span = (end - start).days
    if span <= 31:
        return "day"
    if span <= 120:
        return "week"
    return "month"


def build_time_range(
    key: Optional[str],
    *,
    custom_from: Optional[str] = None,
    custom_to: Optional[str] = None,
    now: Optional[datetime] = None,
) -> TimeRange:
    """Resolve a range key (or a custom from/to pair) into a concrete window."""
    now = now or _now()
    key = key or DEFAULT_RANGE

    if key == "custom" and (custom_from or custom_to):
        start = _parse_dt(custom_from)
        end = _parse_dt(custom_to) or now
        ck = f"custom:{custom_from or ''}:{custom_to or ''}"
        return TimeRange(ck, "Custom range", start, end, _granularity(start, end))
    if key == "all":
        return TimeRange("all", "All time", None, now, "month")
    if key == "ytd":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return TimeRange("ytd", "Year to date", start, now, _granularity(start, now))
    if key == "quarter":
        q_start_month = 3 * ((now.month - 1) // 3) + 1
        start = now.replace(
            month=q_start_month, day=1, hour=0, minute=0, second=0, microsecond=0
        )
        return TimeRange("quarter", "This quarter", start, now, _granularity(start, now))
    label, days = _RANGE_DAYS.get(key, _RANGE_DAYS[DEFAULT_RANGE])
    key = key if key in _RANGE_DAYS else DEFAULT_RANGE
    start = now - timedelta(days=days)
    return TimeRange(key, label, start, now, _granularity(start, now))


def range_payload(tr: TimeRange) -> dict[str, Any]:
    return {
        "key": tr.key,
        "label": tr.label,
        "start": tr.start.isoformat() if tr.start else None,
        "end": tr.end.isoformat() if tr.end else None,
        "granularity": tr.granularity,
        "presets": list(RANGE_PRESETS),
    }


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[: len(fmt) + 2].strip(), fmt).replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue
    return None


# --- cache keys --------------------------------------------------------------
def _context_key(ctx: MetricContext) -> str:
    if ctx.record is None:
        return "system"
    return f"{ctx.record.entity}:{ctx.record.record_id}"


def _range_key(spec: MetricSpec, ctx: MetricContext) -> str:
    if not spec.time_aware or ctx.time_range is None:
        return "all"
    return ctx.time_range.key


# --- resolution --------------------------------------------------------------
async def _safe_compute(spec: MetricSpec, ctx: MetricContext):
    if spec.source == "crm" and ctx.espo is None:
        return unavailable(
            spec.shape,
            "Analytics data source isn't configured on this deployment.",
        )
    try:
        return await spec.compute(ctx)
    except Exception as exc:  # noqa: BLE001 — a metric error must never 500 the page
        log.warning("metric %s failed: %s", spec.key, exc)
        return unavailable(spec.shape, "This metric couldn't be computed right now.")


async def resolve_metric(
    spec: MetricSpec, ctx: MetricContext, *, force: bool = False
) -> dict[str, Any]:
    """Compute (or serve from cache) one metric; returns the panel payload."""
    context_key = _context_key(ctx)
    range_key = _range_key(spec, ctx)
    # Record-scoped metrics run AS THE USER (ACL-bounded), so they are NEVER
    # cached — a shared per-record cache could leak one viewer's ACL scope to
    # another. They're bounded to one record's related set, so live is cheap.
    cached_ok = (
        spec.cache_mode == "cached" and ctx.store is not None and ctx.record is None
    )

    if cached_ok and not force:
        hit = await ctx.store.get_cached(spec.key, context_key, range_key)
        if hit and hit["expires_at"] > _now():
            payload = dict(hit["result"])
            payload["cached"] = True
            return payload

    result = await _safe_compute(spec, ctx)
    payload = result.as_payload(computed_at=_now(), cached=False)
    if cached_ok and result.error is None:
        ttl = spec.refresh_seconds or ctx.settings.analytics_default_cache_ttl_seconds
        await ctx.store.put_cached(
            spec.key,
            context_key,
            range_key,
            result=payload,
            expires_at=_now() + timedelta(seconds=max(ttl, 1)),
        )
    return payload


async def invalidate_page_cache(
    page: PageSpec,
    *,
    store,
    time_range: TimeRange,
    record: Optional[RecordRef] = None,
    metric_lookup: Optional[Callable[[str], Optional[MetricSpec]]] = None,
) -> None:
    """Drop cached results for a page's metrics (manual Refresh) so the next
    render recomputes them."""
    if store is None:
        return
    lookup = metric_lookup or get_metric
    context_key = "system" if record is None else f"{record.entity}:{record.record_id}"
    for panel in page.panels:
        spec = lookup(panel.metric_key)
        if spec is None or spec.cache_mode != "cached":
            continue
        rk = time_range.key if spec.time_aware else "all"
        await store.invalidate(spec.key, context_key, rk)


def page_spec_from_row(row: dict) -> PageSpec:
    """Build a PageSpec from a stored ``analytics_page`` row (inline panels)."""
    panels = []
    for p in row.get("panels") or []:
        vis = p.get("visibility")
        panels.append(
            PanelSpec(
                key=p.get("key") or p.get("metric_key") or "panel",
                title=p.get("title") or "",
                metric_key=p.get("metric_key") or "",
                viz=p.get("viz") or "stat",
                width=int(p.get("width") or 4),
                config=p.get("config") or {},
                visibility=tuple(vis) if vis else None,
            )
        )
    return PageSpec(
        key=row["key"],
        title=row.get("title") or row["key"],
        scope=row.get("scope") or "system",
        subtitle=row.get("subtitle") or "",
        team_gate=tuple(row.get("team_gate") or ()),
        portal_dashboard=bool(row.get("portal_dashboard")),
        default_range=row.get("default_range") or "last12mo",
        panels=panels,
    )


async def render_page(
    page: PageSpec,
    *,
    user: dict,
    settings,
    espo,
    store,
    time_range: TimeRange,
    record: Optional[RecordRef] = None,
    force: bool = False,
    metric_lookup: Optional[Callable[[str], Optional[MetricSpec]]] = None,
    submission_store=None,
) -> dict[str, Any]:
    """Resolve every panel the viewer may see; panels compute concurrently."""
    lookup = metric_lookup or get_metric
    visible = [
        p
        for p in page.panels
        if not p.visibility or is_member(user, list(p.visibility))
    ]

    async def _one(panel):
        spec = lookup(panel.metric_key)
        if spec is None:
            # The metric was deleted/hidden (or never existed) — drop the panel
            # cleanly rather than showing a broken tile.
            return None
        ctx = MetricContext(
            settings=settings,
            espo=espo,
            store=store,
            submission_store=submission_store,
            time_range=time_range,
            record=record,
        )
        result = await resolve_metric(spec, ctx, force=force)
        return {
            "key": panel.key,
            "title": panel.title,
            "viz": panel.viz,
            "width": panel.width,
            "config": panel.config,
            "result": result,
        }

    panels = [p for p in await asyncio.gather(*(_one(p) for p in visible)) if p is not None]
    return {
        "page": {
            "key": page.key,
            "title": page.title,
            "subtitle": page.subtitle,
            "scope": page.scope,
            "defaultRange": page.default_range,
        },
        "timeRange": range_payload(time_range),
        "panels": list(panels),
    }
