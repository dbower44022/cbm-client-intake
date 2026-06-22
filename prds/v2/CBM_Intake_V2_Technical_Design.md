# CBM Intake Platform — Version 2 Technical Design

Engineering companion to `CBM_Intake_V2_Requirements.md`. This document maps the
six reliability requirements to a concrete architecture, data model, and a
phased, reversible migration from the current synchronous app. Audience:
engineers. (For the business framing, read the requirements doc.)

---

## 1. Scope

Deliver Requirements 1–6 by changing the intake platform from a synchronous,
single-pass, single-instance design into a **durable-capture + asynchronous-
delivery** design:

- Capture every submission to a database we control **before** any CRM call.
- Return success to the visitor immediately; do CRM work in a background worker.
- Make CRM delivery automatic, retried, idempotent, and resumable.
- Add status visibility, alerting, and a CRM schema-drift check.

No new forms or fields, no CRM structural changes, no hosting move.

---

## 2. Where V1 stands (and why it is fragile)

Today (`core/app.py`):

```
POST /api/{slug}/intake
  → validate (Pydantic)               # fast, local
  → honeypot check
  → in-memory idempotency dict         # lost on every redeploy
  → spec.orchestrator(sub, client)     # 4+ sequential EspoCRM calls, synchronous
  → log_submission (CIntakeSubmission) # best-effort, ephemeral on failure
  → return ids
```

Fragility, mapped to the requirements:

| V1 property | Consequence | Fixed by |
|---|---|---|
| No copy kept before CRM work | Submission lost if CRM down / orchestrator throws early | Req 1 |
| Visitor waits on synchronous CRM calls | CRM slow/down → visitor sees 502 | Req 2 |
| One attempt, no retry | Transient failure becomes permanent | Req 3 |
| Idempotency in memory; chain not resumable | Duplicates on redeploy; orphans on partial failure | Req 4 |
| Logs only, ephemeral | No one knows about failures | Req 5 |
| Form enum values hand-aligned to CRM | Silent 400s on CRM rename | Req 6 |

The orchestrators themselves are mostly sound and are **reused unchanged** in V2
except for resumability (§5.4): Account and Contact already use find-or-create
(`_find_or_create_account`, `_find_or_create_contact`), so they are safe to
re-run; the profile/engagement creates are not yet.

---

## 3. Target architecture

```
                 ┌─────────────────────────── DigitalOcean App Platform ──────────────────────────┐
                 │                                                                                  │
  visitor ──▶ web service ──┐                                          ┌── worker service           │
  (form)      (FastAPI)     │   INSERT submission (status=pending)     │   (poll loop)              │
                 │          ▼                                          │      ▲                      │
                 │   ┌──────────────┐   claim FOR UPDATE SKIP LOCKED   │      │                      │
                 │   │  Postgres    │◀─────────────────────────────────┘      │ run orchestrator     │
   thank-you ◀───┘   │  (managed)   │   update status/progress/result         ▼ (resumable)          │
   (immediate)       │  submissions │─────────────────────────────────▶ EspoCRM REST (with retry)    │
                 │   └──────────────┘                                                                 │
                 │        ▲  ▲                                                                         │
                 │        │  └── periodic tasks in worker: backlog/alert check, schema-drift check    │
                 │  status + re-drive (admin UI, EspoCRM-team auth — reuse /assignments pattern)      │
                 └──────────────────────────────────────────────────────────────────────────────────┘
```

One new managed dependency: **DigitalOcean Managed Postgres**. It is the durable
store, the work queue (via `FOR UPDATE SKIP LOCKED`), the idempotency ledger, and
the source for the status view — one system instead of adding a separate queue
and cache. Volume is low (tens of submissions/day), so Postgres-as-queue is more
than sufficient and avoids operating Redis/RabbitMQ.

---

## 4. Data model

Single primary table, `submission` (Postgres, JSONB for the payload):

| Column | Type | Notes |
|---|---|---|
| `id` | uuid (pk) | The reference number returned to the visitor. |
| `form_slug` | text | `client-intake` / `volunteer` / `info-request` / `partner` / `sponsor`. |
| `submission_token` | text | Client idempotency token. **Unique with `form_slug`.** |
| `payload` | jsonb | The full validated submission (honeypot field cleared). |
| `status` | text | `pending`, `processing`, `completed`, `retry`, `needs_attention`, `held_honeypot`. |
| `attempt_count` | int | Delivery attempts so far. |
| `next_attempt_at` | timestamptz | When the worker may next claim it (backoff). |
| `last_error` | text | Most recent failure (trimmed). |
| `progress` | jsonb | CRM ids created so far, for resumable delivery (§5.4). |
| `result` | jsonb | Final ids (`contactId`, `engagementId`, …) on completion. |
| `received_at` | timestamptz | Capture time = the official "it happened" timestamp. |
| `processed_at` | timestamptz | Completion time. |
| `updated_at` | timestamptz | Touch on every state change. |

`UNIQUE (form_slug, submission_token)` is the durable idempotency key. Optional
`submission_event` table (append-only: submission_id, at, from_status,
to_status, note) for an auditable history; nice-to-have, not required for v1.

Status lifecycle:

```
pending ─▶ processing ─▶ completed
   ▲           │
   └─ retry ◀──┤ (transient failure: backoff, attempt_count++)
               └─▶ needs_attention  (permanent failure, or max attempts)
held_honeypot  (set at capture; never auto-processed; shown in review queue)
```

---

## 5. Component design

### 5.1 Accept endpoint — Requirements 1, 2, 4 (idempotency)

`POST /api/{slug}/intake` becomes capture-only:

1. Validate with the existing Pydantic submission model (unchanged).
2. Honeypot: if `company_url` is set, capture with `status=held_honeypot` and
   return the normal generic acknowledgement (no bot signal).
3. `INSERT … ON CONFLICT (form_slug, submission_token) DO NOTHING RETURNING id`.
   On conflict, look up and return the existing row's id (idempotent replay).
4. Return `{ "status": "received", "reference": <id> }` immediately.

No EspoCRM call in the request path. This is the whole of Req 1 (durable before
CRM) and Req 2 (visitor independent of CRM). The endpoint's only dependency is
Postgres; if Postgres is unreachable it fails closed (returns an error and the
visitor can retry) — Postgres is far more available than the multi-call CRM path
and has no partial-failure surface.

The visitor no longer receives CRM ids (they don't exist yet). The forms already
show a generic thank-you, so the frontend change is limited to surfacing the
reference number.

### 5.2 Durable store — Requirements 1, 4

Managed Postgres, accessed with SQLAlchemy (async) + Alembic migrations. A thin
`core/store.py` module owns all submission SQL: `capture()`, `claim_batch()`,
`mark_completed()`, `mark_retry()`, `mark_needs_attention()`, `save_progress()`,
`get()`, `list_for_status_view()`. No ORM models leak outside this module.

### 5.3 Worker — Requirement 3

A second App Platform component (type `worker`, same image, command
`python -m worker`) runs a continuous loop:

1. `claim_batch`: `SELECT … FOR UPDATE SKIP LOCKED WHERE status IN ('pending','retry')
   AND next_attempt_at <= now() LIMIT N`, set claimed rows to `processing`.
   `SKIP LOCKED` makes it safe to run more than one worker.
2. For each, run the form's **resumable** orchestrator (§5.4) against the real
   `EspoClient`.
3. Outcomes:
   - Success → `completed`, store `result`, set `processed_at`.
   - Transient failure (timeout, connection error, HTTP 5xx, 429) → `retry`,
     `attempt_count++`, `next_attempt_at = now + backoff(attempt_count)`
     (e.g. 1m, 5m, 30m, 2h, 6h, capped; jittered). After `MAX_ATTEMPTS` →
     `needs_attention`.
   - Permanent failure (HTTP 4xx such as an enum-mismatch 400) → `needs_attention`
     immediately; retrying will not help, and Req 6 will have warned us.
4. Idle when nothing is due; wake on a short poll interval (a few seconds).
   Optional Postgres `LISTEN/NOTIFY` from the accept endpoint for prompt pickup.

`EspoClient` gains transient-retry-with-backoff (tenacity) for blips *within* an
attempt; the worker handles retries *across* attempts. The two layers compose.

### 5.4 Resumable orchestrators — Requirement 4 (no orphans)

The orchestrators create a chain (e.g. Account → Contact → CClientProfile →
CEngagement). To guarantee "one submission → one complete set, no orphans" across
retries, each step must be skippable if already done.

- Account, Contact: already find-or-create — safe to re-run as-is.
- Profile / Engagement / etc.: today plain `create` — a retry after a mid-chain
  failure would create a second one.

Change: each orchestrator accepts the row's `progress` dict and a
`save_progress(progress)` callback. Before each create it checks `progress` for
that step's id and **skips** it if present; after each successful create it
records the id and calls `save_progress` (which the worker persists to the
`submission.progress` column). A retry therefore resumes exactly where it stopped
and connects to the already-created records instead of duplicating them. This is
a small, mechanical change to each `forms/*/orchestrator.py`, fully covered by the
existing `CapturingClient` unit tests plus new resume tests.

### 5.5 Status view and re-drive — Requirement 3

A small authenticated admin surface, reusing the **EspoCRM team-based auth**
already built for `/assignments` (`assignments/auth.py`): gate to the staff team.

- `GET /ops/submissions` — list with status, age, attempts, last error; filter by
  status/form/date.
- `POST /ops/submissions/{id}/redrive` — set `status=pending`,
  `next_attempt_at=now()` so the worker picks it up again. No re-keying; it
  re-runs from saved `progress`.
- Held-honeypot rows are reviewable and promotable here (replacing the
  CIntakeSubmission "review queue" role for held items).

### 5.6 Observability and alerting — Requirement 5

- Metrics from `submission`: counts by status, oldest `pending`/`retry` age
  (backlog), median capture→complete latency. Exposed on the status view and as
  a small JSON endpoint for external monitoring.
- A periodic task in the worker (internal timer; no dependency on a cron feature)
  evaluates thresholds — e.g. "> N in `needs_attention`", "oldest pending older
  than M minutes" — and sends an alert (transactional email via SMTP/API, or a
  Slack webhook). Alerts state whether the cause looks like our side or the CRM
  (4xx vs 5xx/timeout pattern), so staff know who acts.

### 5.7 Schema-drift check — Requirement 6

The forms send a fixed set of enum values (industry, focus areas, languages,
status, etc.). Today those live in each `forms/*/frontend/options.js` and the
orchestrators. V2 introduces a single declared map of `{ entity.field → expected
options }` the app already relies on. A periodic worker task fetches live
`Metadata` (`entityDefs.<Entity>.fields.<field>.options`) from EspoCRM and diffs
it against the declared set; any expected value missing from the live enum raises
an alert naming the form, entity, field, and value — **before** a visitor's
submission fails on it. (We already confirmed the API user can read this
metadata.)

---

## 6. Requirements traceability

| Req | Delivered by |
|---|---|
| 1 Save every submission immediately | §5.1 accept (capture-first), §5.2 store |
| 2 Forms work when CRM is down | §5.1 (no CRM in request path), §5.3 worker |
| 3 Reliable automatic delivery | §5.3 worker (retry/backoff), §5.5 status + re-drive |
| 4 No duplicates / no orphans | §4 unique key, §5.3 `SKIP LOCKED`, §5.4 resumable orchestrators |
| 5 Early warning | §5.6 metrics + threshold alerts |
| 6 Protection from CRM changes | §5.7 schema-drift check |

---

## 7. Technology choices

- **DigitalOcean Managed Postgres** — durable store, queue, idempotency, status.
  One managed dependency; right-sized for the volume.
- **SQLAlchemy (async) + Alembic** — DB access and versioned migrations.
- **tenacity** — within-attempt transient retry in `EspoClient`.
- **App Platform `worker` component** — same image, `python -m worker`; periodic
  tasks run on internal timers inside it.
- Existing stack unchanged otherwise: FastAPI, httpx, Pydantic, the orchestrators,
  the EspoCRM team-auth from `/assignments`.

Local/dev: run Postgres via docker-compose for parity (avoid SQLite, whose
`SKIP LOCKED`/JSONB semantics differ). `DryRunEspoClient` still serves local CRM-
free runs; the worker can run against dry-run for end-to-end local testing.

---

## 8. Deployment changes

`.do/app.yaml` / `.do/app.prod.yaml`:

- Attach a **managed Postgres** database; it injects `DATABASE_URL`.
- Add a **`worker`** component (same Dockerfile image, `run_command: python -m
  worker`, `instance_count: 1`).
- The `web` service may now safely run `instance_count: 2` (idempotency and the
  queue are shared in Postgres) for zero-downtime deploys — optional.
- New env: `DATABASE_URL` (from the managed DB), `ALERT_EMAIL`/`ALERT_WEBHOOK`,
  `MAX_ATTEMPTS`, backoff/threshold tunables. Secrets stay encrypted as today.
- Run Alembic migrations as a **pre-deploy job** so schema changes apply before
  new code serves.

---

## 9. Migration plan (phased, reversible)

Each phase is independently shippable, and the async cutover is behind a flag so
it can fall back to synchronous.

- **Phase 0 — Durable capture, still synchronous.** Provision Postgres; add the
  `submission` table + `capture()` with the unique key. Capture every submission
  to Postgres, then process synchronously exactly as today. Delivers Req 1 and
  the durable half of Req 4 (no in-memory idempotency) with no visitor-facing
  change and minimal risk.
- **Phase 1 — Asynchronous delivery.** Behind `ASYNC_DELIVERY` flag: accept
  returns immediately after capture; add the worker component; move processing to
  the worker; make orchestrators resumable (§5.4). Delivers Req 2, 3, and the
  resumable half of Req 4. Flag off = Phase 0 behavior, so rollback is instant.
- **Phase 2 — Status + re-drive UI.** §5.5. Completes operability for Req 3.
- **Phase 3 — Alerting + schema-drift.** §5.6 and §5.7. Delivers Req 5 and 6.

Relationship to the existing `CIntakeSubmission` CRM record: in V2 the Postgres
row is the durability/audit mechanism. The worker may still write
`CIntakeSubmission` for in-CRM analytics, but it is no longer the safety net and
its best-effort failure no longer risks data loss.

---

## 10. Risks and open questions

- **Resumability completeness.** Every create step in every orchestrator must be
  guarded by `progress`. Audit all five forms; add resume tests so a half-run
  always converges to one complete set.
- **Cost.** Managed Postgres is a new recurring cost (smallest tier is adequate).
  Confirm acceptable.
- **Alert transport.** Decide email (SMTP/transactional API) vs Slack webhook and
  who receives alerts.
- **Held-honeypot review.** Confirm staff review held submissions in the new
  status UI rather than in the CRM.
- **Backpressure.** Volume is low, but cap `claim_batch` size and worker
  concurrency so a backlog can't stampede the CRM.
- **PII at rest.** Submissions in Postgres contain personal data; rely on managed-
  DB encryption at rest + restricted access, and set a retention policy for
  completed rows.

---

## 11. Testing strategy

- **Unit:** `core/store.py` against a test Postgres; resumable orchestrators with
  the existing `CapturingClient` plus partial-failure/resume cases.
- **Worker:** transient failure → retry/backoff; permanent failure →
  needs_attention; `SKIP LOCKED` exclusivity under two workers.
- **Idempotency:** duplicate token, and retry-after-restart, both yield one set.
- **End-to-end (dry-run):** submit → capture → worker → completed, with the CRM
  forced offline to prove Req 2.
- **Schema-drift:** seed an expected value absent from a stubbed metadata response
  → alert fires naming the field.
- Keep the existing 78 tests green throughout; Phase 0/1 must not change V1
  behavior when the async flag is off.
```
