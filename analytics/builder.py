"""Builder metrics — execute a stored entity + filters + aggregation definition.

A builder metric (``source='crm'``, an ``analytics_metric`` DB row) is turned
into a :class:`~analytics.registry.MetricSpec` by :func:`builder_spec`, so panels
reference it by key exactly like a code-registered metric. The definition JSON:

    {
      "filters": [{"type","attribute","value"}, ...],   # EspoCRM where clauses
      "aggregation": {"kind": "count|sum|avg|group_by|bucket|list", ...},
      "time_field": "createdAt"                          # for bucket / range filter
    }

The aggregation ``kind`` determines the result shape (validated on save).
"""

from __future__ import annotations

from typing import Any, Optional

from . import crm
from .registry import (
    SHAPE_BREAKDOWN,
    SHAPE_ROWS,
    SHAPE_SCALAR,
    SHAPE_SERIES,
    VIZ_BAR,
    VIZ_LINE,
    VIZ_STAT,
    VIZ_TABLE,
    MetricContext,
    MetricResult,
    MetricSpec,
    breakdown,
    rows,
    scalar,
    series,
    unavailable,
)

AGG_KINDS = ("count", "sum", "avg", "group_by", "bucket", "list")

_SHAPE_FOR_KIND = {
    "count": SHAPE_SCALAR, "sum": SHAPE_SCALAR, "avg": SHAPE_SCALAR,
    "group_by": SHAPE_BREAKDOWN, "bucket": SHAPE_SERIES, "list": SHAPE_ROWS,
}
_DEFAULT_VIZ = {
    SHAPE_SCALAR: VIZ_STAT, SHAPE_SERIES: VIZ_LINE,
    SHAPE_BREAKDOWN: VIZ_BAR, SHAPE_ROWS: VIZ_TABLE,
}


def shape_for_kind(kind: str) -> Optional[str]:
    return _SHAPE_FOR_KIND.get(kind)


def default_viz_for_shape(shape: str) -> str:
    return _DEFAULT_VIZ.get(shape, VIZ_STAT)


async def execute(row: dict[str, Any], ctx: MetricContext) -> MetricResult:
    entity = row.get("entity")
    fallback_shape = row.get("result_shape") or SHAPE_SCALAR
    if not entity:
        return unavailable(fallback_shape, "This metric has no entity configured.")
    defn = row.get("definition") or {}
    filters = [dict(f) for f in (defn.get("filters") or [])]
    agg = defn.get("aggregation") or {}
    kind = agg.get("kind")

    # Record-scoped injection (Phase C): the page injects the current record id.
    cp = row.get("context_param")
    if ctx.record and cp:
        filters.append({"type": "equals", "attribute": cp, "value": ctx.record.record_id})

    if kind == "count":
        n = await crm.count(ctx.espo, entity, filters)
        return scalar(n, unit=agg.get("unit"))

    if kind in ("sum", "avg"):
        field = agg.get("field")
        if not field:
            return unavailable(SHAPE_SCALAR, "This metric needs a numeric field.")
        recs = await crm.sweep(ctx.espo, entity, field + ",id", where=filters)
        vals: list[float] = []
        for r in recs:
            try:
                vals.append(float(r.get(field)))
            except (TypeError, ValueError):
                continue
        v = sum(vals) if kind == "sum" else (sum(vals) / len(vals) if vals else 0)
        return scalar(round(v, 2), unit=agg.get("unit"))

    if kind == "group_by":
        field = agg.get("field")
        if not field:
            return unavailable(SHAPE_BREAKDOWN, "This metric needs a group-by field.")
        recs = await crm.sweep(ctx.espo, entity, field + ",id", where=filters)
        counts: dict[str, int] = {}
        for r in recs:
            k = r.get(field)
            k = "(none)" if k in (None, "") else str(k)
            counts[k] = counts.get(k, 0) + 1
        items = [{"label": k, "value": v} for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
        topn = agg.get("topN")
        if isinstance(topn, int) and topn > 0 and len(items) > topn:
            head = items[:topn]
            rest = sum(i["value"] for i in items[topn:])
            if rest:
                head.append({"label": "Other", "value": rest})
            items = head
        return breakdown(items)

    if kind == "bucket":
        tf = row.get("time_field") or defn.get("time_field") or "createdAt"
        recs = await crm.sweep(ctx.espo, entity, tf + ",id", where=filters, order_by=tf, order="asc")
        return series(crm.bucket_by_month(recs, tf, ctx.time_range))

    if kind == "list":
        select_fields = agg.get("select") or ["name", "createdAt"]
        columns = agg.get("columns") or [
            {"key": "name", "label": "Name", "link": "record"},
            {"key": "createdAt", "label": "Created"},
        ]
        order_by = agg.get("orderBy") or "createdAt"
        order = agg.get("order") or "desc"
        limit = int(agg.get("limit") or 10)
        sel = ",".join(dict.fromkeys(list(select_fields) + ["id"]))
        recs = await crm.sweep(ctx.espo, entity, sel, where=filters, order_by=order_by, order=order)
        recs = recs[:limit]
        out = []
        for r in recs:
            item = {c["key"]: r.get(c.get("field") or c["key"]) for c in columns}
            item["entity"] = entity
            item["recordId"] = r.get("id")
            out.append(item)
        return rows(columns, out)

    return unavailable(fallback_shape, f"Unknown aggregation {kind!r}.")


def builder_spec(row: dict[str, Any]) -> MetricSpec:
    """Wrap a stored metric row as a MetricSpec (compute = execute the definition)."""

    async def compute(ctx: MetricContext) -> MetricResult:
        return await execute(row, ctx)

    shape = row.get("result_shape") or SHAPE_SCALAR
    return MetricSpec(
        key=row["key"],
        name=row.get("name") or row["key"],
        compute=compute,
        shape=shape,
        source=row.get("source") or "crm",
        default_viz=row.get("default_viz") or default_viz_for_shape(shape),
        applies_to=tuple(row.get("applies_to") or ["system"]),
        cache_mode=row.get("cache_mode") or "cached",
        refresh_seconds=int(row.get("refresh_seconds") or 0),
        time_aware=bool(row.get("time_aware")),
        description=row.get("description") or "",
    )
