# Analytics — Deployment & Activation Runbook

Engineer-facing guide to turning the **Analytics** app on for a deployment. The
code ships **gated OFF** (`ANALYTICS_ENABLED` defaults `false`), so pushing/deploying
it changes nothing until you activate it. Plan/design: `prds/analytics-app-plan.md`.
End-user guide: `analytics-guide.md`.

---

## 0. TL;DR

1. Create an **`Analytics Admin Team`** in the CRM (both crm-test and prod) and add
   staff.
2. Make sure the deploy already has `SESSION_SECRET`, `ESPO_API_KEY`, and a
   `DATABASE_URL` (all standard for the staff-stack apps — they do).
3. In the deployment's gitignored `.do` overlay, set **`ANALYTICS_ENABLED=true`** on
   **both the web and worker** components.
4. Apply the overlay with `doctl apps update <app-id> --spec … --wait`. The
   PRE_DEPLOY `migrate` job runs `alembic upgrade head`, which creates the analytics
   tables (`0021_analytics_cache`, `0022_analytics_definitions`).
5. Verify (§5). Roll back by removing `ANALYTICS_ENABLED` (§6).

---

## 1. What "on" requires

Analytics is mounted only when **`analytics_active`** is true, which means:

```
ANALYTICS_ENABLED = true      AND      the staff stack is on (SESSION_SECRET set)
```

So it rides the existing staff-app session — no new auth. Beyond the flag it uses
infrastructure the staff apps already have:

| Needs | Why | Already present? |
|---|---|---|
| `SESSION_SECRET` | Shared portal session (sign-in + team gates) | Yes (web + worker) |
| `ESPO_API_KEY` (live, not dry-run) | System dashboards read the CRM org-wide under the API key | Yes on crm-test/prod |
| `DATABASE_URL` | The metric **cache**, the **definition** tables (authored metrics/pages), and the **operational metrics** (submissions/queue) | Yes on crm-test/prod (V2 store) |
| The `Analytics Admin Team` CRM team | Gates authoring (and, by default, viewing) | **You create this** |

Without `DATABASE_URL` the app still runs **view-only against live CRM counts**
(recomputing each view); but authoring, the cache, and the operational metrics all
need the database. On crm-test/prod the database is already attached, so this is a
non-issue there.

---

## 2. CRM prerequisite — the Analytics Admin Team

In the EspoCRM UI (crm-test first, then prod):

1. **Administration → Teams → Create Team**, name it exactly **`Analytics Admin
   Team`** (or pick your own name and set the env vars in §3 to match).
2. Add the staff who should build and view analytics. **CRM admins always pass** the
   gate regardless of team membership.

No custom entities, fields, or roles are needed — analytics reads existing CRM data
and stores its own definitions/cache in the app's Postgres.

> **Viewing vs authoring.** By default both the view gate and the author gate are
> `Analytics Admin Team`. To let a broader audience *view* dashboards while keeping
> *authoring* restricted, set `ANALYTICS_VIEW_ALLOWED_TEAMS` to a wider team (§3).

---

## 3. Environment variables

Set on the deployment's gitignored overlay (`.do/app.prod.yaml` = crm-test,
`.do/app.prod-crm.yaml` = prod). **`ANALYTICS_ENABLED` must be on both the web and
the worker component** (web serves the app; the worker warms cached metrics).

| Variable | Default | Scope | Notes |
|---|---|---|---|
| `ANALYTICS_ENABLED` | `false` | **web + worker** | Master switch. |
| `ANALYTICS_ADMIN_ALLOWED_TEAMS` | `Analytics Admin Team` | web | CSV of team names allowed to author. Admins always pass. |
| `ANALYTICS_VIEW_ALLOWED_TEAMS` | `Analytics Admin Team` | web | CSV of team names allowed to view. Widen to open dashboards to more staff. |
| `ANALYTICS_REFRESH_SECONDS` | `3600` | worker | How often the worker recomputes cached system-dashboard metrics. `0` disables the warm job (cache still fills lazily on first view). |
| `ANALYTICS_DEFAULT_CACHE_TTL_SECONDS` | `3600` | web + worker | TTL for a cached metric that doesn't set its own refresh interval. |

Example overlay snippet (web component envs):

```yaml
      - { key: ANALYTICS_ENABLED, scope: RUN_TIME, value: "true" }
      # optional overrides:
      # - { key: ANALYTICS_VIEW_ALLOWED_TEAMS, scope: RUN_TIME, value: "Analytics Admin Team,Marketing Admin Team" }
```

And on the **worker** component:

```yaml
      - { key: ANALYTICS_ENABLED, scope: RUN_TIME, value: "true" }
      # - { key: ANALYTICS_REFRESH_SECONDS, scope: RUN_TIME, value: "3600" }
```

Apply:

```bash
doctl apps update <app-id> --spec .do/app.prod.yaml --wait      # crm-test
doctl apps update <app-id> --spec .do/app.prod-crm.yaml --wait  # prod
```

App IDs (see DEPLOYMENT.md): crm-test `509b4370-b9ca-42c7-b251-04d6820fe88e`,
prod `aa1ddf69-f359-4b53-91ba-035cbed7bd53`.

---

## 4. Database migrations

Two migrations back the feature:

- **`0021_analytics_cache`** — the `analytics_cache` table (materialized metric
  results).
- **`0022_analytics_definitions`** — `analytics_metric` (the metric library) +
  `analytics_page` (authored pages; panels inline as JSON).

They run automatically via the overlay's **PRE_DEPLOY `migrate` job** (`alembic
upgrade head`) on the next deploy. Both create **new tables only** — no changes to
existing data, safe to apply ahead of turning the flag on. To run manually against a
database:

```bash
DATABASE_URL=postgresql://… uv run alembic upgrade head
```

(Boot does **not** create tables — Alembic is the sole schema authority. A fresh
environment must migrate before first boot.)

---

## 5. Verification (after deploy)

Sign in to the portal as a member of the Analytics Admin Team.

1. **App loads.** Open **Analytics** (portal tile or `/analytics`). The **System
   Analytics** dashboard renders five panels against real CRM data (active mentors,
   active engagements, engagements/month, engagements by status, oldest unassigned).
   `/healthz` shows the current version.
2. **Time range + refresh.** Change the time range (trend panels update); click
   **Refresh** (panels recompute; cached ones then read "as of …").
3. **Authoring.** Click **Manage → + New metric**: pick a record type + a `count`
   measure + a filter, click **Preview** (a value appears), **Save**. Then
   **Pages → + New page**, add a panel using your metric, save, and confirm it shows
   in the viewer.
4. **Operational metric.** Add a panel using **Submissions received per month** or
   **Submission queue by status** and confirm it renders (proves the database path).
5. **Portal dashboard.** Edit a system page (or the System Analytics page via a copy)
   and tick **Show on portal home**, or confirm the seeded dashboard shows on the
   portal landing page for analytics viewers.
6. **Record tab.** Build a mentor-scoped metric (**Applies to → Mentors**, record
   link field `mentorProfileId`) + a page with **Where it appears → Record tab:
   Mentors**. Open a mentor in **Mentor Administration** (`/mentoradmin`) → the
   **Analytics** tab shows that mentor's numbers. Confirm a staffer who *can't* open
   the mentor is denied.
7. **Worker warm job.** In the worker logs, look for `analytics warm: N refreshed`
   on the `ANALYTICS_REFRESH_SECONDS` cadence.

---

## 6. Rollback

Analytics is fully gated — to turn it off, **remove `ANALYTICS_ENABLED`** (or set it
`false`) on both components and re-apply the overlay. The app disappears from the
portal and routes; **no data is lost**. The `analytics_cache` / `analytics_metric` /
`analytics_page` tables remain (harmless); a later re-enable picks up right where it
left off. There is no destructive step to undo.

---

## 7. How it fits the architecture (reference)

- **Package** `analytics/` — one FastAPI router mounted at `/analytics` under the
  `analytics_active` gate; endpoints under `/analytics/api/*`.
- **Engine** — a metric produces one of four result shapes (`scalar` / `series` /
  `breakdown` / `rows`). System metrics compute under the **API key** (org-wide);
  record-tab metrics compute **as the signed-in user** (ACL-bounded) and are never
  cached. Cheap counts run live; sweeps are cached in `analytics_cache`.
- **Metrics** — code-registered (`analytics/dashboard.py`, `analytics/computed.py`)
  **plus** author-built "builder" metrics (`analytics/builder.py`) stored in
  `analytics_metric`. Both are referenced by key, uniformly.
- **Storage** — `analytics/store.py` (`AnalyticsStore`, own engine, migrations
  0021/0022). Operational metrics read the durable submission store
  (`core/store.py`, `submissions_by_month` / `counts_by_status`).
- **Worker** — `analytics/refresh.py` warms cached system-dashboard metrics on
  `ANALYTICS_REFRESH_SECONDS` (added to the worker loop in `worker.py`). Inert
  without a store or a live CRM client.
- **Embedding** — the record tab and the portal dashboard fetch
  `GET /analytics/api/record/{entity}/{id}` and `GET /analytics/api/portal` and
  render with the shared `frontend/shared/charts.js` / `charts.css` (loaded by any
  host that embeds panels — `/mentoradmin`, the portal).

Endpoints at a glance:

| Endpoint | Purpose |
|---|---|
| `GET /analytics/api/session` | Identity + the pages the user may view + `canAuthor`. |
| `GET /analytics/api/pages` / `…/pages/{key}` | List / render a system page. |
| `POST /analytics/api/pages/{key}/refresh` | Recompute a page now (refresh-all). |
| `GET /analytics/api/portal` | The portal-home dashboard (self-gating). |
| `GET /analytics/api/record/{entity}/{id}` | Record-scoped analytics (parent read as the user = the ACL gate). |
| `GET/POST/PUT/DELETE /analytics/api/admin/metrics` · `…/pages` | Authoring (admin-gated). |
| `GET /analytics/api/admin/entities` · `…/fields` · `POST …/preview` | Builder helpers. |

---

## 8. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| **Analytics tile/app missing** | `ANALYTICS_ENABLED` not set on web, or `SESSION_SECRET` missing. |
| **403 "not authorized to use Analytics"** | User isn't on the analytics view team and isn't an admin. Add them to `Analytics Admin Team` (or widen `ANALYTICS_VIEW_ALLOWED_TEAMS`). |
| **Manage button missing** | User isn't on the admin team, **or** no `DATABASE_URL` (authoring needs the database). |
| **All system panels say "data source isn't configured"** | The deploy is in dry-run / has no `ESPO_API_KEY`. System metrics need a live CRM client. |
| **Operational panels say "submission store isn't configured"** | No `DATABASE_URL` on this deploy. |
| **`admin/*` returns 503** | Authoring endpoints need the database (`DATABASE_URL`). |
| **Mentor Analytics tab says "no analytics set up"** | No mentor-scoped page exists yet — build one (§5 step 6). |
| **Portal home shows no dashboard** | Either the viewer lacks access, or no system page is flagged **portal_dashboard**. |
| **A single panel shows an error message** | That metric couldn't compute (CRM hiccup / missing grant) — by design it degrades to a message and never breaks the page. |
| **Migration didn't run** | Confirm the overlay's PRE_DEPLOY `migrate` job is present and `DATABASE_URL` is set for it; or run `alembic upgrade head` manually (§4). |

---

*Deployment mechanics common to all apps (overlays, `doctl`, the migrate job,
custom domains, rollback) live in `DEPLOYMENT.md`.*
