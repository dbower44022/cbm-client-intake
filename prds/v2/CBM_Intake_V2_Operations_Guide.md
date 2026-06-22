# CBM Intake V2 — Operations & Technical Guide

The practical runbook for turning on V2 (durable capture + asynchronous
delivery) and running it day to day. Companion to the requirements
(`CBM_Intake_V2_Requirements.md`) and design (`CBM_Intake_V2_Technical_Design.md`).

---

## 1. What is deployed today

V2 (Phases 0–3) is merged and **running dormant** in production. The code is
present and tested, but inert: the app behaves exactly as V1 until a database is
attached and the flags are set. Two switches turn it on:

| Switch | Off (today) | On |
|---|---|---|
| `DATABASE_URL` | no store — V1 in-memory behavior | every submission captured to Postgres before any CRM work |
| `ASYNC_DELIVERY` | the web app processes synchronously | the web app returns immediately; the **worker** delivers to the CRM |

`GET /healthz` reports `"durableStore": true` once `DATABASE_URL` is set.

**Production facts** (from `CLAUDE.md`):
- App ID: `509b4370-b9ca-42c7-b251-04d6820fe88e`
- URL: `https://cbm-client-intake-svxs3.ondigitalocean.app`
- `doctl` is installed and authenticated (`admin@cbmentors.org`).
- Live config lives in the **gitignored** `.do/app.prod.yaml` overlay, applied with
  `doctl apps update <app-id> --spec .do/app.prod.yaml --wait`. Activation is done
  by editing that overlay and re-applying.

---

## 2. Architecture (technical reference)

```
visitor → web service ──capture──▶ Postgres ◀──claim/deliver── worker service ──▶ EspoCRM
            │ (FastAPI)              (managed)                    (python -m worker)
            └─ thank-you (immediate)   ▲                          └─ periodic: alert + schema-drift checks
                                        └─ /ops console (staff): status, re-drive, metrics
```

**Components**
- **web** — the existing service. Serves the forms, captures submissions, and (in
  async mode) returns immediately. Also serves `/ops` and `/assignments`.
- **worker** — `python -m worker`. Claims due submissions (`FOR UPDATE SKIP
  LOCKED`), delivers them via the orchestrators with retry/backoff, and runs the
  alert + schema-drift checks on a timer.
- **Postgres** — durable store, work queue, idempotency ledger, and the source for
  the `/ops` console and metrics.

**Submission lifecycle** (`status` column)
```
pending ─▶ processing ─▶ completed
   ▲           │
   └─ retry ◀──┤ (transient failure: backoff 1m→5m→30m→2h→6h, attempt_count++)
               └─▶ needs_attention  (permanent 4xx, or attempts exhausted)
held_honeypot  (spam-guard hit; never auto-delivered; reviewable in /ops)
```

**Key files**: `core/store.py` (store + queue), `worker.py` (delivery loop),
`core/resumable.py` (no-duplicate retries), `core/monitoring.py` +
`core/schema_contract.py` (Phase 3), `ops/` (console), `alembic/` (schema).

**Environment variables**

| Var | Where | Purpose |
|---|---|---|
| `DATABASE_URL` | web + worker + migrate job | turns on the durable store |
| `ASYNC_DELIVERY` | web + worker | `true` = asynchronous delivery |
| `ESPO_DRY_RUN`, `ESPO_BASE_URL`, `ESPO_API_KEY` | web + worker | CRM connection (worker writes too) |
| `SESSION_SECRET`, `ASSIGN_ALLOWED_TEAMS` | web | already set — gate `/ops` + `/assignments` |
| `ALERT_WEBHOOK_URL` | worker | Slack-style alert webhook (optional; logs if unset) |
| `MAX_DELIVERY_ATTEMPTS`, `ALERT_*`, `WORKER_*`, `SCHEMA_CHECK_SECONDS` | worker | tunables (sensible defaults) |

---

## 3. Activation runbook

We activate in two stages so each is verified before the next. Everything is a
change to `.do/app.prod.yaml` applied with one `doctl` command, and every step is
reversible.

### Prerequisites
- `doctl` authenticated (it is). Confirm: `doctl account get`.
- The current `.do/app.prod.yaml` overlay (has the `ESPO_*` + `SESSION_*` envs).
- The `.do/app.yaml` comment block has a ready-to-copy spec for the database, the
  migrate job, and the worker.

### Stage A — durable capture (Phase 0), still synchronous

Lowest risk: the visitor experience is unchanged; we just start keeping a
permanent copy of every submission and enforce idempotency in the database.

1. **Add a database** to `.do/app.prod.yaml`:
   ```yaml
   databases:
     - name: cbm-db
       engine: PG
       version: "16"
       production: false   # single-node dev DB; ample for this volume
   ```
2. **Add a pre-deploy migration job** (creates the `submission` table before new
   code serves):
   ```yaml
   jobs:
     - name: migrate
       kind: PRE_DEPLOY
       dockerfile_path: Dockerfile
       github: { repo: dbower44022/cbm-client-intake, branch: main }
       run_command: .venv/bin/alembic upgrade head
       envs:
         - { key: DATABASE_URL, scope: RUN_TIME, value: "${cbm-db.DATABASE_URL}" }
   ```
3. **Give the web service the database** (add to its `envs`):
   ```yaml
       - { key: DATABASE_URL, scope: RUN_TIME, value: "${cbm-db.DATABASE_URL}" }
   ```
   (Do **not** set `ASYNC_DELIVERY` yet.)
4. **Apply**: `doctl apps update 509b4370-b9ca-42c7-b251-04d6820fe88e --spec .do/app.prod.yaml --wait`
5. **Verify Stage A**:
   - `curl -s <url>/healthz` → `"durableStore": true`.
   - Submit a real test on a form (or the info-request form). It should succeed as
     normal.
   - Sign in to `<url>/ops` (staff in the `Client Administration Team`) → the
     submission appears with status **completed**.

### Stage B — asynchronous delivery (Phase 1 + worker + monitoring)

Now the visitor gets an instant thank-you and the worker does the CRM work.

1. **Add the worker** to `.do/app.prod.yaml`:
   ```yaml
   workers:
     - name: delivery-worker
       dockerfile_path: Dockerfile
       github: { repo: dbower44022/cbm-client-intake, branch: main, deploy_on_push: true }
       instance_size_slug: basic-xxs
       instance_count: 1
       run_command: .venv/bin/python -m worker
       envs:
         - { key: DATABASE_URL, scope: RUN_TIME, value: "${cbm-db.DATABASE_URL}" }
         - { key: ASYNC_DELIVERY, scope: RUN_TIME, value: "true" }
         - { key: ESPO_DRY_RUN, scope: RUN_TIME, value: "false" }
         - { key: ESPO_BASE_URL, scope: RUN_TIME, value: "https://crm-test.clevelandbusinessmentors.org" }
         - { key: ESPO_API_KEY, scope: RUN_TIME, type: SECRET, value: "<the intake api key>" }
         # optional: - { key: ALERT_WEBHOOK_URL, scope: RUN_TIME, type: SECRET, value: "https://hooks.slack.com/..." }
   ```
2. **Turn on async on the web service** (add to its `envs`):
   ```yaml
       - { key: ASYNC_DELIVERY, scope: RUN_TIME, value: "true" }
   ```
3. **Apply** the spec again (same `doctl apps update … --wait`).
4. **Verify Stage B**:
   - Submit a test. The form should return its thank-you immediately.
   - `/ops` shows the submission go **pending → processing → completed** within a
     few seconds; the worker logs show `delivered <id>`.
   - Worker logs: `doctl apps logs 509b4370-… --type run -f` (the `delivery-worker`
     component) → look for `worker started` then `delivered …`.

> Optional CRM-down drill: temporarily point the worker's `ESPO_BASE_URL` at a bad
> host. Submissions still capture and the form still succeeds; rows sit in
> `retry`/`needs_attention`; fix the URL and re-drive — they complete. (Do this in
> a quiet window.)

---

## 4. Day-to-day operations

### The ops console (`<url>/ops`)
- Sign in with an EspoCRM account in the `Client Administration Team`.
- **Summary line + chips**: backlog, needs-attention, oldest-pending age, average
  delivery time, and counts by status.
- **Table**: every submission with status, submitter, age, attempts, last error.
  Click the reference to see the full payload, what was created so far
  (`progress`), and the error.
- **Re-drive**: on `held_honeypot` / `needs_attention` / `retry` rows. It re-queues
  the submission; the worker re-runs it **from saved progress**, so nothing is
  duplicated and no data is re-typed.

### What the statuses mean / what to do
- **completed** — delivered to the CRM. Nothing to do.
- **pending / processing** — in flight. If `pending` is piling up, the worker may
  be down or the CRM slow (see alerts).
- **retry** — a transient failure (CRM 5xx/timeout); it will retry itself on the
  backoff schedule. No action unless it persists.
- **needs_attention** — a permanent failure (e.g. a value the CRM rejected) or
  retries exhausted. Open it, read the error, fix the cause (often a form-option/
  CRM mismatch — see schema-drift below), then **Re-drive**.
- **held_honeypot** — caught by the spam guard. If it's a real person, **Re-drive**
  to process it.

### Alerts (from the worker)
- **"N submission(s) need attention"** — open `/ops`, fix + re-drive.
- **"Delivery backlog: oldest pending is X minutes old"** — usually the CRM is
  slow/down; submissions are safe and will drain automatically when it recovers.
  Check the worker is running and the CRM is reachable.
- **"CRM schema drift: Entity.field no longer offers value(s) …"** — the CRM team
  renamed/removed an option the forms send. Reconcile: update the form's options
  (and `core/schema_contract.py`) to match the CRM, or ask the CRM team to restore
  it. This warning arrives **before** submissions start failing on it.

Alerts post to `ALERT_WEBHOOK_URL` if set, otherwise appear in the worker logs at
WARNING.

### Logs
- Web: `doctl apps logs 509b4370-… --type run -f` (the `web` component).
- Worker: same command, `delivery-worker` component — shows deliveries, retries,
  and the periodic checks.

---

## 5. Rollback / disable (instant, reversible)

Edit `.do/app.prod.yaml` and re-apply:
- **Back to synchronous (Phase 0)**: set `ASYNC_DELIVERY=false` on the web service
  (the worker can stay; it just finds nothing to claim). The web app processes
  inline again; submissions still captured.
- **Back to V1 entirely**: remove `DATABASE_URL` from the web service. No store,
  in-memory idempotency, exactly as before V2. (Captured rows remain in the DB.)
- The durable store means **no submission is lost** during any rollback.

---

## 6. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `/healthz` `durableStore:false` after Stage A | `DATABASE_URL` not on the web service, or the migrate job failed — check the deployment's job logs. |
| `/ops` data shows 503 | Web service has no `DATABASE_URL` (store not configured). |
| Submissions stuck in `pending`, none `processing` | Worker not running — check the `delivery-worker` component is deployed and its logs show `worker started`. |
| Everything in `retry`/`needs_attention` | CRM unreachable or rejecting — check `ESPO_BASE_URL`/`ESPO_API_KEY` on the **worker**, and `ESPO_DRY_RUN=false`. |
| Migration job fails | Confirm `DATABASE_URL` is bound (`${cbm-db.DATABASE_URL}`) and the DB component name matches. |
| Duplicate records feared after a retry | They won't: Account/Contact are find-or-create and other creates are skipped via saved `progress`. |

---

## 7. Go-live checklist

- [ ] `doctl account get` works.
- [ ] Stage A applied; `/healthz` → `durableStore:true`.
- [ ] Test submission visible in `/ops` as `completed`.
- [ ] Stage B applied; worker logs show `worker started`.
- [ ] Test submission goes `pending → completed` via the worker; form returned
      instantly.
- [ ] `/ops` re-drive works on a test `needs_attention` row.
- [ ] (Optional) `ALERT_WEBHOOK_URL` set and a test alert received.
- [ ] Schema-drift check has run once with no false alerts (worker logs).
- [ ] Rollback path confirmed understood (flip `ASYNC_DELIVERY`, or drop
      `DATABASE_URL`).
