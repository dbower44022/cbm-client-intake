# CBM Analytics — Product Requirements & Build Plan

**Status:** DRAFT for review (authored 2026-07-25 from Doug's interview).
**Owner:** Doug. **Author surface:** power users only. **App name/route:** Analytics / `/analytics`.
**Supersedes:** nothing. **Related:** `prds/funder-contributions-plan.md` (the on-the-fly
in-app aggregation precedent), `prds/v2/` (durable-store + worker platform this rides on).

---

## 1. Executive summary

A configurable **analytics platform** for the CBM app suite. A power user **defines a
metric** (a reusable, named data definition — "active engagements", "emails sent per
mentor this month", "sessions in the last 90 days"), wraps it in a **panel** (a metric +
a visualization: stat / time-series / bar-or-pie / list), and places panels onto
**pages**. Pages come in two flavors:

- **System pages** — org-wide dashboards (the v1 flagship), living in a new standalone
  `/analytics` app and optionally surfaced on the portal home.
- **Record-scoped pages** — an **Analytics tab** embedded on a company / contact / mentor /
  engagement (etc.) record, showing that record's slice of the data via auto-injected
  record context.

The definition layer is a **named metric library**: metrics are authored once and reused
across any number of panels and pages. Two authoring mechanisms coexist (Doug's ruling):
a **data-driven builder** (CRM entity + filters + aggregation, stored in Postgres) for
simple CRM metrics, and **code-registered** Python metrics (referenced by key) for
cross-source / computed metrics a dropdown builder can't express. Panels reference either
kind uniformly by key.

Data is **hybrid**: cheap counts run **live** against EspoCRM as the signed-in user (CRM
ACL is the gate); heavy aggregations are **cached** in the app's Postgres and refreshed on
a per-metric cadence by the worker. Metrics can draw from **EspoCRM entities**, the app's
own **Postgres operational data** (submissions, comms, documents, action log, worker
health), or **computed cross-source** blends. v1 ships **drill-through** (click a number to
see the underlying rows, click a row to open the record); file export is future work.

---

## 2. Goals / non-goals

### Goals
- G1. A power user can define a **reusable named metric** without a deploy for CRM
  entity + filter + aggregation cases (builder), and a developer can add a **code metric**
  by key for anything more complex.
- G2. Panels render four visualization types at v1: **stat/count**, **time-series
  (line/area)**, **bar/column + pie/donut**, and **list/table**.
- G3. Admins curate **pages** (choose panels + order); everyone entitled sees that same
  curated layout.
- G4. Analytics appear on **three surfaces**: a standalone `/analytics` app, an embedded
  **Analytics tab** on record detail views, and the **portal home** dashboard.
- G5. **Record-scoped** panels automatically show the current record's data (context
  injection) and never leak data past the viewer's CRM ACL.
- G6. **Per-panel visibility rules** (teams/roles) plus record-ACL inheritance gate who
  sees what.
- G7. **Hybrid freshness**: live for cheap metrics, per-metric cached refresh (default
  hourly-class cadence) for heavy ones; a manual "Refresh" is always available.
- G8. **Drill-through** on every applicable panel.
- G9. Rides the existing conventions (per-request team gates, Alembic-owned schema, worker
  timers, vanilla-JS frontends, `busy.js`, footer/version parity) with no new
  infrastructure classes.

### Non-goals (v1)
- N1. No **user-personalized** dashboards (drag-drop per-user layouts). Pages are
  admin-curated only. (Revisit later.)
- N2. No **CSV/Excel export**. Drill-through only.
- N3. No **raw-SQL / free-expression escape hatch inside the builder** — cross-source and
  arbitrary joins are handled by **code-registered** metrics, not by an in-app SQL box.
- N4. No **write-back** to the CRM. Analytics are read-only.
- N5. No **scheduled email/PDF report delivery**. (The worker refresh is internal only.)
- N6. No **new external charting service** or build step; visualization is self-hosted
  (see §11).

---

## 3. Core concepts & data model

Three nouns, addressable and reusable, plus a cache:

```
Metric   — a reusable named data definition. Produces a typed RESULT SHAPE.
Panel    — a Metric + a visualization type + display config + visibility rules.
Page     — an ordered collection of Panels; scope = 'system' or a record entity type.
Cache    — materialized metric results, keyed by (metric, context, time-range).
```

### 3.1 Result shapes (the contract between metric and panel)

A metric declares exactly one **result shape**; a panel may only choose a visualization
compatible with it.

| Result shape | Produces | Compatible viz |
|---|---|---|
| `scalar` | one number (+ optional prior-period value for a delta) | **stat/count** |
| `series` | ordered `[{bucket, value}]` over time | **time-series (line/area)**, bar |
| `breakdown` | `[{label, value}]` over categories | **bar/column**, **pie/donut** |
| `rows` | `[{...}]` list of records/dicts (+ column spec) | **list/table** |

This taxonomy is the whole engine's spine: the builder produces one of these, code metrics
return one of these, the cache stores one of these, and the frontend has exactly four
renderers.

### 3.2 Metric definition

Every metric — builder or code — is addressable by a stable **`key`** (e.g.
`active_engagements`, `emails_sent_by_mentor`). Panels reference metrics by key, so the two
kinds are interchangeable at the panel layer (Doug's requirement).

**Common metric attributes:**
- `key` (unique, stable), `name`, `description`
- `source`: `crm` | `store` | `computed`
- `result_shape`: `scalar | series | breakdown | rows`
- `default_viz`: the panel type suggested when composing
- `cache_mode`: `live` | `cached`
- `refresh_seconds`: per-metric cadence when `cached` (0 ⇒ inherit the global default)
- `applies_to`: `["system"]` and/or record entity types (`["CMentorProfile","CEngagement"]`)
  — declares where the metric may be placed
- `context_param`: for record-scoped metrics, the filter key the page injects the current
  record id into (e.g. `mentorProfileId`, `accountId`) — see §3.4
- `time_field`: for time-aware metrics, the CRM/DB field the range filter and bucketing
  apply to (e.g. `createdAt`, `dateStart`)

**Builder metric (`source=crm`, stored in Postgres):**
- `entity`: e.g. `CEngagement`
- `filters`: a list of EspoCRM `where` clauses (`{type, attribute, value}`) — authored via
  the guided builder using live enum options from metadata
- `aggregation`: one of
  - `count` — number of matching rows (uses the list `total` envelope; cheap, live-able)
  - `sum(field)` / `avg(field)` — scalar rollups (Python)
  - `group_by(field)` — breakdown by a field's values (Python)
  - `bucket(time_field, granularity)` — time-series (Python)
  - `list(select, order, limit)` — rows
- The builder never emits SQL; it emits a JSON definition the CRM resolver executes.

**Code metric (`source=store` or `computed`, defined in Python):**
- Registered in an in-code `METRIC_REGISTRY` keyed by `key`, so it lives in version
  control. Each registration declares the common attributes above **in code** and provides
  a `compute(ctx) -> MetricResult` async function.
- `ctx: MetricContext` carries: an as-the-user `EspoClient`, the app `store` (and comms/docs
  stores), the resolved **time range**, the **record context** (`entity`, `record_id`,
  injected value) when record-scoped, and `settings`.
- This is where cross-source blends live (e.g. "avg days from intake to first session" =
  submission `received_at` from the store joined to the first `CSession.dateStart` from the
  CRM).

> **Storage note.** Builder metrics get a DB row (`analytics_metric`). Code metrics are
> pure code addressed by key; they do **not** require a DB row. The metric library UI lists
> the union of DB rows and registry entries. (Optional later: a DB overlay row that lets an
> admin tune a code metric's `cache_mode`/`refresh_seconds`/visibility without a deploy —
> deferred.)

### 3.3 Panel

A panel = `metric_key` + `viz_type` (compatible with the metric's result shape) +
`config_json` (viz options: number format, top-N, bucket granularity, color, **per-panel
time-window override**) + `visibility_json` (allowed teams/roles) + `title`. Panels are
stored rows (`analytics_panel`), reusable across pages.

### 3.4 Record context (record-scoped binding) — **recommended model (Doug: "recommend one")**

**Auto-inject record context.** A record-scoped page has `scope = <entity type>` (e.g.
`CMentorProfile`). When the Analytics tab renders on a given record, the engine injects the
current record's id into each panel's metric via the metric's declared `context_param`:

- Builder metric: the injected value becomes an implicit `where` clause
  `{type: equals, attribute: <context_param>, value: <recordId>}` merged with the metric's
  own filters.
- Code metric: the value arrives on `ctx.record` (`entity`, `record_id`, `value`).

A metric declares which record types it supports via `applies_to`, so the **same** metric
(e.g. "sessions over time", `context_param=parentId`) can drive the Analytics tab on an
engagement, a partner, and a sponsor — authored once. If a metric's `applies_to` doesn't
include a page's scope, it can't be added to that page (the composer filters the list).

This is strictly better than per-record-type metrics (the rejected alternative): one
definition, N record types, no authoring multiplication.

### 3.5 Page

- `key` (stable), `scope` (`system` | entity type), `title`, `team_gate` (for system pages;
  record pages inherit the record's ACL — see §10), ordered panel placements
  (`analytics_page_panel`: `page_id`, `panel_id`, `position`, `width`/layout hint).
- Multiple system pages allowed (e.g. `system-overview`, `system-intake`,
  `system-fundraising`). Exactly one record page per entity type at v1 (the entity's
  Analytics tab); more can come later keyed by name.
- A designated system page (`portal_dashboard` flag or a settings key) renders as the
  **portal home** dashboard. **Doug's ruling (2026-07-25): the full flagship page** renders
  on portal home (not a compact subset) — the portal dashboard IS the system-overview page.

### 3.6 Storage tables (App Postgres — **recommended, Doug: "recommend one"**)

New tables on the shared `core/store.py` `metadata`, created by **Alembic `0021`**
(current head is `0020_record_comment`; next number is `0021`). Rationale: fits the stack
(comms/docs/ops config all live here), no CRM entity build, editable at runtime, and the
cache genuinely belongs in Postgres. Follow the `record_comment` table as the template
(the newest, cleanest small-table pattern).

```
analytics_metric        -- builder metrics (code metrics are code, not rows)
  id (uuid) PK, key (unique), name, description, source, result_shape,
  default_viz, cache_mode, refresh_seconds, applies_to (json), context_param,
  time_field, entity, definition (json: filters+aggregation),
  created_at, created_by, updated_at, updated_by

analytics_panel
  id PK, metric_key, viz_type, title, config (json), visibility (json),
  created_at, created_by, updated_at, updated_by

analytics_page
  id PK, key (unique), scope, title, team_gate (json/nullable),
  portal_dashboard (bool), created_at, created_by, updated_at, updated_by

analytics_page_panel
  id PK, page_id FK, panel_id FK, position (int), width (int/enum)
  -- unique (page_id, panel_id); index (page_id, position)

analytics_cache
  metric_key, context_key (e.g. 'system' or 'CMentorProfile:<id>'),
  range_key (e.g. 'last30d' | 'ytd' | 'default'),
  result (json), computed_at, expires_at
  -- PK/unique (metric_key, context_key, range_key); index on expires_at
```

Store surface follows the Protocol + `PostgresStore` pattern (declare signatures on the
`SubmissionStore` Protocol, implement on `PostgresStore`; tests duck-type a `FakeStore`).
Methods: metric/panel/page CRUD + `list_*`; `get_cached(metric_key, context_key, range_key)`,
`put_cached(...)` (upsert via `on_conflict_do_update`, the `heartbeat`/`record_presence`
pattern), `due_cached_metrics()` for the worker, `invalidate_cache(...)`. Aggregate queries
over the app's own operational data reuse the existing `func.count`/`group_by` idioms
already in `core/store.py` (`metrics()`, `counts_by_status()`).

---

## 4. Decisions locked (from the interview)

| # | Decision | Choice |
|---|---|---|
| 1 | Author profile | Power users only; expert definition surface OK |
| 2 | Data source | **Hybrid** — CRM-live for cheap, cached Postgres for heavy |
| 3 | Surfaces | Standalone `/analytics` app **+** record-detail tabs **+** portal dashboard |
| 4 | Definition model | **Named metric library** (metrics → panels → pages) |
| 5 | Panel types (v1) | stat/count, time-series line/area, bar/column + pie/donut, list/table |
| 6 | Record binding | **Auto-inject record context** (recommended) |
| 7 | Persistence | **App Postgres** (Alembic `0021`) (recommended) |
| 8 | Refresh cadence | **Per-metric configurable** (hourly-class default; `live` bypasses) |
| 9 | Page authoring | **Admin-curated templates** |
| 10 | View gating | **Per-panel visibility rules** + record-ACL inheritance |
| 11 | Data domains | CRM entities **+** app Postgres operational **+** computed/cross-source |
| 12 | Export/drill | **Drill-through only** in v1 |
| 13 | Metric engine | **Builder + code-registered split** |
| 14 | Time controls | **Global page selector + per-panel override** |
| 15 | First page | **System analytics dashboard** (flagship) |
| 16 | Name/route | **Analytics / `/analytics`**; gate `Analytics Admin Team` (authoring) |

---

## 5. Architecture & integration points (grounded in the codebase)

New package **`analytics/`**, mounted like the other staff apps. Nothing here needs new
infrastructure — every seam already exists.

### 5.1 Package layout
```
analytics/
  __init__.py            # exports `router as api_router` (portal/ops pattern)
  router.py              # FastAPI router: /analytics/api/*, per-request _require_user gate
  service.py             # the engine: resolve metric -> MetricResult (crm/store/computed)
  registry.py            # METRIC_REGISTRY + @metric decorator; built-in code metrics
  builder.py             # builder-metric JSON -> CRM query plan -> MetricResult
  cache.py               # get/put/invalidate + due-metric selection helpers
  config.py              # (optional) any analytics-specific constants
  frontend/              # index.html, app.js, styles.css (vanilla, no build)
    vendor/…             # charting (see §11)
```

### 5.2 Mount + gate (`core/app.py`, `assignments/auth.py`)
- Inside the existing `if settings.assignments_active:` block: `from analytics import api_router`
  and `app.include_router(api_router)`; add `ANALYTICS_FRONTEND_DIR` constant and
  `app.mount("/analytics", StaticFiles(ANALYTICS_FRONTEND_DIR, html=True))` (guarded by
  `assignments_active and dir.is_dir()`); add the `GET /analytics/record/{entity}/{id}`
  page route mirroring the sessions record-page recipe (`<base href="/analytics/">`,
  `Cache-Control: no-store`) if a full-page record view is ever wanted (the embedded tab
  needs no route).
- Auth: reuse the shared `staff_user` session (`SESSION_KEY`), `current_user`, `is_member`.
  `router.py` builds its own `_require_user(request)` → 401 (unauth, redirect
  `/?next=/analytics/`) / 403 (names the required team). **Authoring** endpoints gate on
  `settings.analytics_admin_allowed_teams_list` (default `Analytics Admin Team`, admins
  pass). **Viewing** a system page gates on the page's `team_gate` (or the app team);
  **each panel** additionally filters on its `visibility_json`. Record-page viewing gates on
  the record read (§10).

### 5.3 Portal tile (`portal/router.py`)
- `_apps_for`: append `{"title": "Analytics", "url": "/analytics/", "target": "cbm-analytics"}`
  guarded by `is_member(user, settings.analytics_view_allowed_teams_list)` (a broader
  view-team than the admin/authoring team). The tile is convenience; the per-request gate is
  the boundary.
- Portal dashboard: `_home_payload` gains an `analytics` block carrying the **full**
  `portal_dashboard` page (its panels, respecting per-panel visibility), rendered on the
  portal home when the user may view it — the same renderers as the `/analytics` viewer.

### 5.4 Record-tab embedding (`sessions/` + the directory/record surfaces)
Follow the **`discussion_enabled` / `contributions_link` precedent** exactly — a
`DomainConfig` flag that gates BOTH endpoint registration and the frontend tab:
- Add `analytics_enabled: bool` (or `analytics_page_key`) to `sessions/config.py:DomainConfig`.
- `sessions/router.py:_detail_tabs(cfg)` inserts `{"key":"analytics","label":"Analytics"}`
  when set; the `/session` payload carries `analyticsEnabled`.
- Register `GET /{slug}/api/records/{parent_id}/analytics` under `if cfg.analytics_enabled:`
  in `make_router`. The handler reads the parent **as the user first** (the ACL gate — same
  as contributions/discussion), resolves the record page for `scope=<parent entity>`, injects
  the record id as context (§3.4), and returns rendered panel results.
- Frontend: `buildDetailTabs()` already renders config tabs; add a `data-dpanel="analytics"`
  panel and an `activateDetailTab` branch `if (tab === "analytics") renderAnalytics()` that
  reuses the shared panel renderers.
- The same embedding applies to the **directory** record views (company/contact) and
  `/mentoradmin` (mentor) via the equivalent per-app hook. Record types targeted at v1+:
  `Account` (company), `Contact`, `CMentorProfile` (mentor), `CEngagement`,
  `CPartnerProfile`, `CSponsorProfile`.

### 5.5 The engine (`analytics/service.py`)
`resolve_metric(key, ctx) -> MetricResult`:
1. Look up the metric (DB row or registry entry) by key.
2. If `cache_mode == cached`: try `store.get_cached(key, context_key, range_key)`; on hit
   and not expired, return it. On miss/expired, compute, `put_cached`, return.
3. If `cache_mode == live`: compute now.
4. Compute dispatches by `source`:
   - `crm` → `builder.execute(definition, ctx)` — builds `where` (metric filters + injected
     record context + time-range clause on `time_field`), then:
     - `count` → one `list(entity, where, max_size=1)`; read the **`total`** field of the
       `{total, list}` envelope (cheap, no sweep — good for live stat panels).
     - `sum/avg/group_by/bucket/list` → paginated `list` sweep (the
       `mentor_engagement_metrics` pattern: `max_size=200`, offset loop, aggregate in
       Python). Record-scoped metrics are naturally bounded (one record's related set); system
       metrics that sweep a whole entity should be `cached`.
   - `store` → SQL aggregate over app Postgres (reuse `func.count`/`group_by`).
   - `computed` → the registry `compute(ctx)` function (arbitrary cross-source).
5. Return a `MetricResult` (result_shape + payload + `computed_at` + freshness).

**As-the-user vs API-key.** Live CRM metrics and record-scoped reads run as the signed-in
user (`EspoClient.for_user_token`) so ACL is enforced automatically. Cached system-metric
refresh in the worker runs under the **service API key** (no user session), which is why
system pages carry an explicit `team_gate` + per-panel visibility rather than relying on
per-row ACL (system metrics are org-level aggregates by design — §10).

### 5.6 Worker refresh timer (`worker.py`, `core/config.py`)
Add a periodic job following the **docs-reconciliation template**: seed `next_analytics`
before the loop; inside `while not stop.is_set():`, when
`settings.analytics_enabled and settings.analytics_refresh_seconds > 0 and now >= next_analytics`,
lazily `from analytics.cache import refresh_due_metrics` and `await refresh_due_metrics(store, settings)`
inside a `try/except Exception` that only logs (`# noqa: BLE001 — never crashes delivery`);
reschedule `next_analytics = now + timedelta(seconds=settings.analytics_refresh_seconds)`.
`refresh_due_metrics` selects cached metrics whose `expires_at` has passed (respecting each
metric's `refresh_seconds`), recomputes each (system context; record-scoped cached metrics
are computed lazily on view, not swept for every record), and upserts the cache. Runs
regardless of `async_delivery` (the loop always turns).

### 5.7 Config / flags (`core/config.py`)
New `# --- Analytics ---` block:
```
analytics_enabled: bool = False                 # master flag (gdrive_docs pattern)
analytics_refresh_seconds: int = 3600           # global cached-refresh cadence; 0 disables the worker job
analytics_default_cache_ttl_seconds: int = 3600 # per-metric refresh_seconds=0 inherits this
analytics_admin_allowed_teams: str = "Analytics Admin Team"   # authoring gate (CSV)
analytics_view_allowed_teams: str = "Analytics Admin Team"    # default view gate (CSV; widen per deploy)
```
Plus `@property` list parsers (`analytics_admin_allowed_teams_list`, etc.) and an
`analytics_active` property (`analytics_enabled and store_enabled and assignments_active`).
Empty `DATABASE_URL` ⇒ inert (the feature needs the store).

---

## 6. Panel / visualization spec (v1)

Four renderers, each consuming one result shape. All theme-aware (CBM tokens), responsive,
and self-hosted (§11).

1. **Stat / count** — one large number, label, optional unit and **delta** vs the prior
   equivalent period (▲/▼ + %). Config: number format, delta on/off, delta polarity color.
   Consumes `scalar`.
2. **Time-series (line/area)** — a line or filled area over the page's time range. Config:
   line vs area, bucket granularity (day/week/month, else auto from range), point markers,
   y-format. Consumes `series`.
3. **Bar/column + pie/donut** — a breakdown. Config: bar vs pie/donut, orientation, **top-N +
   "other" rollup**, sort, value/percent labels. Consumes `breakdown`.
4. **List / table** — rows with a column spec. Config: columns, order, page size, which
   column links to a record (deep link to the CRM or the app record page). Consumes `rows`.

Every panel chrome shows: title, freshness (`computed_at`, "as of …" for cached; "live" for
live), a manual **Refresh** (invalidates that metric's cache entry and recomputes), and — where
applicable — a **drill-through** affordance (§9). Panels honor the page time range unless a
per-panel window override is set (§8).

---

## 7. Metric definition spec

### 7.1 Builder metrics (guided, stored, no deploy)
The metric builder (authoring UI, §12) produces the `analytics_metric` row:
- Pick **entity** (from a curated allowlist of CRM entities the app knows).
- Add **filters**: attribute (metadata-driven field list), operator, value (enum values
  pulled live from `metadata_enum_options`, dates, numbers). Drift-tolerant like the rest of
  the app (unknown enum values flagged, never silently mis-saved).
- Pick **aggregation** (`count` / `sum` / `avg` / `group_by` / `bucket` / `list`) →
  determines the **result shape** and which panels are compatible.
- For time-aware aggregations pick the **`time_field`**.
- For record-scoping, pick the **`context_param`** (the field the record id is injected into)
  and the `applies_to` record types.
- Choose `cache_mode` + `refresh_seconds` (default: `count` = live; sweeps = cached).

### 7.2 Code metrics (registry, version-controlled)
```python
@metric(
    key="days_intake_to_first_session",
    name="Avg days: intake → first session",
    source="computed", result_shape="scalar",
    applies_to=["system"], cache_mode="cached", refresh_seconds=3600,
)
async def _(ctx: MetricContext) -> MetricResult:
    # ctx.store, ctx.espo (as-user or API key), ctx.time_range, ctx.record, ctx.settings
    ...
    return scalar(value, prior=prior_value)
```
Registry entries appear in the library UI alongside builder metrics (read-only definition;
config like visibility is set at the panel layer). Seed the flagship system dashboard with
code metrics so Phase A ships without the builder (§13).

### 7.3 Metric editing safety
A metric is referenced by many panels. Edits are allowed (power users), but the composer
shows a metric's usage count, and deleting a metric in use is blocked with a list of
dependent panels/pages. Renaming `key` is disallowed once created (panels reference by key).

---

## 8. Time-range model

- Each **system page** has a **global time-range selector**: presets (Last 7 / 30 / 90 days,
  This quarter, YTD, Last 12 months) + custom from/to. The selected range (`from`, `to`,
  derived `granularity`) is passed to every time-aware panel's metric compute and becomes part
  of the cache `range_key`.
- Non-time-aware metrics (a plain count, a current breakdown) ignore the range.
- **Per-panel override**: a panel may pin its own fixed window (e.g. "always last 12 months")
  regardless of the page selector; the chrome shows the pinned window.
- Record pages: same selector, scoped to the record's data.
- Cache keys therefore include `range_key`; presets cache cleanly, custom ranges compute
  live (or cache with a short TTL).

---

## 9. Drill-through (v1)

- **Stat / series point / bar slice** → clicking opens a **rows** view of the underlying
  records. Implemented by pairing a metric with a companion `rows` query: builder metrics
  derive it from the same entity+filters (+ the clicked bucket/category as an extra clause);
  code metrics may declare a `drill(ctx, selection) -> rows` function.
- **A row** → deep-links to the CRM record (`espo_base_url/#Entity/view/id`) and/or the app
  record page (`/{slug}/record/{id}`) when one exists.
- Drill-through respects the same ACL as the panel (as-the-user read for record data).
- No file export in v1 (N2).

---

## 10. Security & ACL model

- **Authoring** (create/edit/delete metrics, panels, pages): `Analytics Admin Team` (or
  admin). Never available to plain viewers.
- **System page viewing**: the page's `team_gate` (defaulting to the app view team) gates the
  page; **each panel's `visibility_json`** (allowed teams/roles) further filters which panels a
  given viewer sees on that page. A panel the viewer can't see is omitted entirely (no
  placeholder that leaks its existence — Doug's per-panel model).
- **Record page viewing**: the embedded Analytics tab reads the **parent record as the user
  first** (the contributions/discussion precedent) — if the viewer can't read the record, the
  tab 403s/hides. Record-scoped metrics run as the user, so CRM ACL bounds the data
  automatically; per-panel visibility still applies on top.
- **Cached system data caveat**: cached results are computed under the service API key and
  are org-level aggregates, so they intentionally bypass per-row ACL. This is acceptable
  **only** because system pages/panels carry explicit team+visibility gates. A record-scoped
  metric must **never** be served from a context-blind cache — its `context_key` includes the
  record id, and it is computed as the viewing user (or cached per-record after an as-user
  read gate).
- All mutating authoring actions are recorded via `core/action_log.py` (the product-wide
  convention): a stream note is N/A (no CRM record), so use the `CActionLog` reporting half
  (feature-gated) to log metric/panel/page create/edit/delete with the actor.

---

## 11. Visualization technology — **DECIDED: hand-rolled SVG (option A, Doug 2026-07-25)**

There is **no charting infrastructure** today (no canvas, no d3/Chart.js, no build step;
only Jodit is vendored). Decision: **option A** — hand-rolled inline SVG, no vendored chart
library. Two paths were considered:

- **A. Hand-rolled inline SVG renderers (recommended).** The four v1 shapes are simple: a
  stat is text; bar/pie/line are a few dozen lines of SVG each. Zero dependency, matches the
  no-build vanilla-JS ethos, full theme control, tiny payload, no license/upgrade surface.
  Interactivity (hover tooltips, click-to-drill) is straightforward on SVG elements. Risk:
  we own the rendering code (bounded — four shapes).
- **B. Vendor one small MIT chart library** (e.g. a UMD build alongside Jodit under
  `frontend/shared/vendor/`). Faster to reach polished interactive charts; costs a vendored
  dependency, a larger payload, and an upgrade/security surface. Justified only if the
  visualization ambition grows well beyond the four v1 types.

**Decided:** ship **A** for v1 (a shared `frontend/shared/charts.js` with
`renderStat/renderSeries/renderBreakdown/renderTable`), and revisit **B** only if later
panel types demand richer interactive charts.

---

## 12. Authoring UX (`/analytics` app)

Three authoring surfaces plus the viewer, all vanilla-JS (three-file frontend, `busy.js`
first, footer/version parity):

1. **Metric library** — searchable list of all metrics (builder rows ∪ code registry),
   showing key/name/source/shape/cache mode/usage count. "New metric" opens the **builder**;
   code metrics are read-only here.
2. **Metric builder** — entity → filters (metadata-driven, live enum options) → aggregation →
   time field / context param / applies-to → cache config. Live **preview** of the result
   (runs the metric against current data) before save.
3. **Panel composer** — pick a metric, pick a compatible viz, set display config + visibility
   rules; live preview. Panels are reusable and listed for reuse.
4. **Page composer** — pick scope (system / a record entity type), add panels, order them
   (up/down; simple ordered list, not drag-drop-personalized), set the page `team_gate` and
   the `portal_dashboard` flag; preview renders the page.
5. **Viewer** — the rendered system page(s) with the global time-range selector, panel
   refresh, and drill-through. The same renderers back the embedded record tabs and the
   portal dashboard.

---

## 13. Phasing / delivery plan

Each phase is independently shippable and gated OFF until activated (`analytics_enabled`).

> **BUILT 2026-07-25 (v0.160.0).** See CHANGELOG 0.160.0. One deviation from the
> table plan below, by the repo's "migrations ship with the code that uses them"
> rule: **migration `0021` creates the `analytics_cache` table only** — the
> metric/panel/page **definition** tables are deferred to Phase B, where the
> authoring UI that fills them lands (Phase A's pages/metrics are code-seeded, so
> those tables would be dead schema now). Everything else in Phase A shipped:
> engine, seeded dashboard, `/analytics` app + gate + portal tile, the four SVG/
> HTML renderers, the worker warm job, and the config flags (all gated OFF by
> `ANALYTICS_ENABLED`).

### Phase A — Flagship system dashboard (code-seeded), engine + storage
- Alembic `0021`: the cache table (definition tables → Phase B). Store methods (cache get/put/due/invalidate).
- Engine (`service.py`, `builder.py`, `registry.py`, `cache.py`): result-shape model,
  crm/store/computed resolvers, live vs cached, the `total`-envelope cheap-count path.
- Config flags + the worker refresh timer.
- The `/analytics` app mount + portal tile + per-request gate.
- **Seed one system page in code** (`system-overview`) with **code metrics** spanning all
  four panel types. The two must-have v1 stat metrics (Doug 2026-07-25):
  - **Total Active Mentors** — `CMentorProfile` where `mentorStatus="Active"` [stat].
  - **Total Active Client Engagements** — `CEngagement` in active statuses [stat].
  Plus, to exercise the other three renderers: intakes per month [series], engagements by
  status [breakdown], oldest unassigned engagements [rows]. (Counts use the cheap `total`
  envelope; the sweeps are `cached`.)
- The four **SVG renderers** (§11-A) + the viewer with the global time-range selector +
  manual refresh.
- **Proves the engine end-to-end** (Doug's flagship) without the authoring UI or record
  context. CRM prereq: create `Analytics Admin Team` (+ a view team) in both CRMs.

### Phase B — Authoring UI (self-serve metrics/panels/pages)
- Metric builder (CRM entity+filter+aggregation), panel composer, page composer.
- Per-panel visibility rules; page `team_gate`; action-log on authoring writes.
- Live previews; metric-usage safety (§7.3). Drill-through (§9).
- After B, admins create metrics/panels/pages in-app without a deploy.

### Phase C — Record-scoped analytics + embedded tabs
- Record context model (`context_param` injection); `applies_to` gating in the composer.
- **First record type: Mentor** (`CMentorProfile`, Doug 2026-07-25) — prove record-scoping
  on the mentor surface (`/mentoradmin` detail and/or the mentor directory record view)
  first, then extend to `CEngagement`, `Account`/company, `Contact`, partner, sponsor.
- The Analytics detail tab with the parent-read-as-user ACL gate; on `sessions` domains via
  `DomainConfig.analytics_enabled`, and the equivalent hook on the mentor/directory surfaces.
- Per-record cache keying; record-scoped drill-through.

### Phase D — Portal dashboard + computed-metric expansion + polish
- The **full** `portal_dashboard` page surfaced on portal home (Doug: full page, not a
  compact summary).
- A library of cross-source **computed** metrics (intake→first-session latency, email
  volume per mentor, submission backlog trends, contribution trends).
- Polish: refresh-all, empty/permission states, freshness UX, number formatting.
- (Future / explicitly deferred: CSV export, personalized dashboards, scheduled report
  delivery.)

---

## 14. CRM prerequisites

- **`Analytics Admin Team`** (authoring gate) and a **view team** (broaden per deploy)
  created in **both** crm-test and prod — mirrors the `Marketing Admin Team` precedent for
  `/ops`. Add staff to the teams. (Names overridable via the settings env vars.)
- No new CRM entities or fields are required — analytics read existing CRM data and store
  their definitions/cache in the app's Postgres.
- (Optional, later) the `CActionLog` entity for the authoring audit trail — already
  feature-gated and inert until built.

---

## 15. Testing & verification

- **Unit**: result-shape builders (`scalar/series/breakdown/rows`); the CRM builder's
  where-clause + record-context injection + time-range clause; the cheap `total`-count path;
  the store cache upsert/expiry/due-selection (round-trip on live local Postgres, migration
  0021 up/down, like the `record_comment`/`0020` precedent); per-panel visibility filtering;
  the record-page parent-read ACL gate (403/hide).
- **Engine**: each resolver (crm/store/computed) with a stubbed `EspoClient` and a `FakeStore`;
  cached vs live; worker `refresh_due_metrics` selecting only expired metrics.
- **Frontend**: the four SVG renderers + the viewer/time-range/drill-through in the
  sessions-style stub-browser harness (fetch-stub the API, verify no console errors,
  computed styles, click-to-drill), following `[[sessions-frontend-stub-harness]]` and the
  `[[harness-js-clicks-bypass-overlays]]` real-click discipline.
- **Live (per env, after deploy)**: seed the system page renders as an admin; a non-admin in
  the view team sees only visible panels; a record's Analytics tab shows that record's data
  and 403s/hides for a user who can't read the record; a cached metric's freshness advances
  after a worker refresh; manual Refresh recomputes.

---

## 16. Risks & open questions

- **R1 — CRM sweep cost.** Group-by/bucket over a whole entity is a full paginated scan
  (`mentor_engagement_metrics` cost). Mitigation: those metrics are `cached`; cheap counts
  use the `total` envelope; record-scoped metrics are bounded to one record's related set.
  Open: do any system metrics need a scan too large for an hourly refresh? (Measure on prod
  entity sizes.)
- **R2 — Cached-data ACL.** Cached system aggregates bypass per-row ACL by design; the
  safety net is explicit team + per-panel visibility gates. Record-scoped metrics must stay
  context-keyed and as-user. Confirm this boundary is acceptable for the org-level pages.
- **R3 — Charting build vs buy (§11).** Recommendation is hand-rolled SVG; needs Doug's
  confirmation before Phase A.
- **R4 — Deploy fan-out.** All three App Platform apps build from `main`; Phase A ships to
  prod + crm-test on push. The feature is gated OFF (`analytics_enabled`) until activated per
  env, and the CRM teams must exist first.
- **R5 — Metric/version drift.** Enum/field drift in builder metrics (the product-wide
  concern) — reuse the existing drift-tolerant handling; flag unknown enum values in the
  builder.

**Resolved with Doug (2026-07-25):**
1. **Charting** → hand-rolled inline SVG (§11-A); no vendored chart library in v1.
2. **View team** → `Analytics Admin Team` only for system-page viewing (per-panel visibility
   applies on top). The `analytics_view_allowed_teams` default therefore equals the admin
   team; widen per deploy later if needed.
3. **First record type (Phase C)** → **Mentor** (`CMentorProfile`).
4. **Portal dashboard** → the **full** flagship page on portal home (not a compact summary).
5. **Must-have v1 metrics** → **Total Active Mentors** and **Total Active Client
   Engagements** (both stat panels), seeded in Phase A alongside the three renderer-exercising
   metrics.

**Remaining open (design-time, not blocking Phase A):**
- R1 measurement: confirm no system group-by/bucket metric sweeps an entity too large for an
  hourly refresh once prod entity sizes are known.
- Whether to add the optional DB-overlay row for tuning a code metric's cache/visibility
  without a deploy (§3.2 note) — deferred unless needed.
