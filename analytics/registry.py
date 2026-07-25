"""Analytics core types + the metric registry (Analytics Phase A).

The whole engine's spine is the RESULT SHAPE taxonomy — a metric produces exactly
one of ``scalar`` / ``series`` / ``breakdown`` / ``rows``, and a panel may only
render a visualization compatible with it. Every metric — builder (Phase B, DB
row) or code (this registry) — is addressable by a stable ``key`` so panels
reference either kind uniformly.

Phase A ships code-registered metrics only (see :mod:`analytics.dashboard`); the
builder + DB-backed metrics arrive in Phase B.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

# --- result shapes -----------------------------------------------------------
SHAPE_SCALAR = "scalar"       # one number (+ optional prior for a delta)
SHAPE_SERIES = "series"       # ordered [{bucket,label,value}] over time
SHAPE_BREAKDOWN = "breakdown" # [{label,value}] over categories
SHAPE_ROWS = "rows"           # {columns, rows} record list

# --- metric sources ----------------------------------------------------------
SRC_CRM = "crm"               # EspoCRM entities
SRC_STORE = "store"           # the app's own Postgres operational data (Phase D)
SRC_COMPUTED = "computed"     # cross-source blend (Phase D)

# --- visualization types (a panel's chosen renderer) -------------------------
VIZ_STAT = "stat"
VIZ_LINE = "line"
VIZ_AREA = "area"
VIZ_BAR = "bar"
VIZ_PIE = "pie"
VIZ_TABLE = "table"

# Which viz types each result shape may be rendered with (composer + validation).
COMPATIBLE_VIZ: dict[str, tuple[str, ...]] = {
    SHAPE_SCALAR: (VIZ_STAT,),
    SHAPE_SERIES: (VIZ_LINE, VIZ_AREA, VIZ_BAR),
    SHAPE_BREAKDOWN: (VIZ_BAR, VIZ_PIE),
    SHAPE_ROWS: (VIZ_TABLE,),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- request context ---------------------------------------------------------
@dataclass
class TimeRange:
    """The window a page's time-aware panels compute over."""

    key: str                    # cache/label key: 'last30d','ytd','all','custom:…'
    label: str                  # human label for the UI
    start: Optional[datetime]   # None => unbounded (all time)
    end: Optional[datetime]     # None => now
    granularity: str            # 'day' | 'week' | 'month'


@dataclass
class RecordRef:
    """The current record for a record-scoped panel (Phase C)."""

    entity: str
    record_id: str
    value: str


@dataclass
class MetricContext:
    """Everything a metric's ``compute`` needs. ``store`` is the analytics CACHE
    (managed by the engine — metrics never read it); ``submission_store`` feeds
    store-domain metrics (Phase D)."""

    settings: Any
    espo: Any                                  # EspoApi (system: API key; record: as-user) or None
    store: Any = None                          # AnalyticsStore | None (cache)
    submission_store: Any = None               # SubmissionStore | None (Phase D)
    time_range: Optional[TimeRange] = None
    record: Optional[RecordRef] = None


# --- results -----------------------------------------------------------------
@dataclass
class MetricResult:
    shape: str
    data: Any
    error: Optional[str] = None

    def as_payload(self, *, computed_at: datetime, cached: bool) -> dict[str, Any]:
        """The JSON-safe panel payload (also what the cache stores)."""
        return {
            "shape": self.shape,
            "data": self.data,
            "computedAt": computed_at.isoformat(),
            "cached": cached,
            "error": self.error,
        }


def scalar(value, *, prior=None, unit=None, fmt: str = "number") -> MetricResult:
    return MetricResult(SHAPE_SCALAR, {"value": value, "prior": prior, "unit": unit, "format": fmt})


def series(points: list[dict[str, Any]], *, unit=None, fmt: str = "number") -> MetricResult:
    """points: [{"bucket": "2026-01", "label": "Jan 2026", "value": n}, ...]"""
    return MetricResult(SHAPE_SERIES, {"points": points, "unit": unit, "format": fmt})


def breakdown(items: list[dict[str, Any]], *, fmt: str = "number") -> MetricResult:
    """items: [{"label": ..., "value": ...}, ...] (author-sorted)."""
    return MetricResult(SHAPE_BREAKDOWN, {"items": items, "format": fmt})


def rows(columns: list[dict[str, Any]], rows_: list[dict[str, Any]]) -> MetricResult:
    """columns: [{"key","label","link"?,"align"?}], rows: [{col->value, recordId?, entity?}]"""
    return MetricResult(SHAPE_ROWS, {"columns": columns, "rows": rows_})


def unavailable(shape: str, message: str) -> MetricResult:
    """A metric that couldn't compute (CRM down, no data source, forbidden). The
    panel renders the message instead of a value — never a 500."""
    return MetricResult(shape, None, error=message)


# --- metric registry ---------------------------------------------------------
@dataclass
class MetricSpec:
    key: str
    name: str
    compute: Callable[[MetricContext], Awaitable[MetricResult]]
    shape: str
    source: str = SRC_CRM
    default_viz: str = VIZ_STAT
    applies_to: tuple[str, ...] = ("system",)
    cache_mode: str = "live"          # 'live' | 'cached'
    refresh_seconds: int = 0          # 0 => inherit analytics_default_cache_ttl_seconds
    time_aware: bool = False          # honors the page time range (else caches under 'all')
    description: str = ""


METRIC_REGISTRY: dict[str, MetricSpec] = {}


def register_metric(spec: MetricSpec) -> MetricSpec:
    METRIC_REGISTRY[spec.key] = spec
    return spec


def metric(**kw) -> Callable[[Callable], MetricSpec]:
    """Decorator: register the decorated async fn as a metric's ``compute``."""

    def deco(fn: Callable) -> MetricSpec:
        return register_metric(MetricSpec(compute=fn, **kw))

    return deco


def get_metric(key: str) -> Optional[MetricSpec]:
    return METRIC_REGISTRY.get(key)


# --- panels + pages (Phase A: code-seeded; Phase B: DB-backed, same shape) ---
@dataclass
class PanelSpec:
    key: str                             # unique within the page
    title: str
    metric_key: str
    viz: str
    width: int = 4                       # grid columns out of 12
    config: dict = field(default_factory=dict)
    # None => the panel inherits the page gate; a team list => per-panel gate on
    # top of the page (Doug's per-panel visibility model). Empty tuple = same.
    visibility: Optional[tuple[str, ...]] = None


@dataclass
class PageSpec:
    key: str
    title: str
    scope: str = "system"                # 'system' | a record entity type (Phase C)
    subtitle: str = ""
    # Teams allowed to VIEW this page; empty => the app's analytics_view gate.
    team_gate: tuple[str, ...] = ()
    portal_dashboard: bool = False       # render on the portal home (Phase D)
    default_range: str = "last12mo"
    panels: list[PanelSpec] = field(default_factory=list)


PAGE_REGISTRY: dict[str, PageSpec] = {}


def register_page(page: PageSpec) -> PageSpec:
    PAGE_REGISTRY[page.key] = page
    return page


def get_page(key: str) -> Optional[PageSpec]:
    return PAGE_REGISTRY.get(key)
