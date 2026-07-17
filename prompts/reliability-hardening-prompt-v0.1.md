# Claude Code kickoff prompt — Reliability & Observability Hardening

**Version:** v0.1 (2026-07-17)
**Source of truth:** `reliability-review-2026-07-17.md` (repo root) — the full review with
file:line references, failure scenarios, and severity for every finding. This prompt tells
you WHAT to build and in what order; the review tells you WHERE and WHY. Read it first,
in full. Item labels below (P0-1, P1-5, …) refer to that document's numbering.

---

## Role and mission

You are a senior reliability engineer working in the `cbm-client-intake` repo. A
2026-07-17 reliability review found the architecture sound but identified a consistent
defect pattern: **error handling with holes at the seams** — transport exceptions that
bypass `except EspoError` nets, silent `except: pass` blocks, cursors/leases that advance
past failures, and monitoring that runs inside the one process it cannot watch. Your
mission is to close every finding in the review, in the phase order below.

**Work one phase per session unless a phase is trivially small.** Each phase ends with:
all tests green (`uv run pytest -q`), a CHANGELOG entry, a version bump, a commit
(Conventional Commits). **Never push — Doug reviews and pushes** (repo convention).
Update CLAUDE.md's Current status when a phase completes. Where a fix changes behavior a
staff user can see, verify it in the stubbed-browser harness
([[sessions-frontend-stub-harness]]) before calling it done.

**Rules that bound every phase:**
- Do NOT change product behavior beyond the finding being fixed. These are hardening
  changes; a fix that alters a documented contract (e.g. best-effort never blocks a save)
  is wrong even if it "improves" reliability.
- Best-effort contracts stay best-effort, but their failures must become VISIBLE (a log
  line, a `{ok:false}` result, or a metric) — that is the theme of the whole effort.
- Every new failure path gets a test. Prefer extending the existing test files
  (`tests/test_worker.py`, `tests/test_store.py`, etc.) over new frameworks.
- App-side vs CRM-side: nothing in this effort requires CRM builds. If you conclude
  something does, stop and write it up as a handoff instead of building around it.

---

## Phase 1 — Stop the bleeding (P0-1..4 + the worker traceback fix)

Small, surgical, highest value. All five in one session.

1. **P0-1 poison payload.** `worker.py`: move `model_validate` inside the classify-and-
   route try; a `ValidationError` is permanent → `mark_failed` → `needs_attention`. Add a
   top-level `try/except` around `run_once()` in `main()` so NO exception (including store
   errors, review P2 "worker post-orchestrator") can kill the loop — log with
   `exc_info=True`, sleep the poll interval, continue.
2. **Worker tracebacks.** In `process_one`'s non-transient branch, log with
   `log.exception` and store a traceback tail (last ~1000 chars) in `last_error` so a
   `needs_attention` row caused by a code bug is diagnosable from `/ops`.
3. **P0-2 rollback double-delivery.** Gate the worker's claim loop on
   `settings.async_delivery` — flag off ⇒ the worker idles exactly like it does with no
   DATABASE_URL (log the mode banner, don't exit). Test: sync-mode capture + a running
   worker never double-claims.
4. **P0-3 transport errors.** In `core/espo.py`, catch `httpx.HTTPError` in the request
   funnel and raise `EspoError` (subclass or flag, e.g. `EspoTransportError(EspoError)`,
   message includes the operation + URL host, never the API key). Update
   `worker._classify` to keep treating transport as TRANSIENT (it currently keys on
   httpx types — keep both paths passing). Grep every `except EspoError` consumer and
   confirm the new behavior is right there (it repairs `_crm_failure` mapping,
   `refresh_membership` fail-open, assignments' per-target accumulation for free — the
   review lists the exact sites).
5. **P0-4 details PUT allowlist.** `sessions/router.py` details PUT: reject `entity` not
   in `cfg.details_entities` + `Contact` (mirror the peek allowlist). 404, not 403, to
   avoid confirming entity names. Test: `CMentorProfile` PUT through
   `/mentorsessions/api/details/...` is rejected for a non-admin.

**DoD:** tests green incl. new ones for each item; a hand-run of the worker against local
Postgres (docker-compose) survives a deliberately-poisoned payload row, marks it
`needs_attention` with a traceback, and keeps delivering the rest of the batch.

## Phase 2 — See the failures (worker liveness + logging/telemetry pass)

1. **P1-6 worker liveness.** Worker stamps a heartbeat each loop iteration (one-row
   `worker_heartbeat` table or a row in `app_config` — pick the simplest; Alembic
   migration if a new table). `/healthz` gains `worker`: `{lastHeartbeatAgeSeconds}`,
   plus `backlog` and `oldestPendingAgeSeconds` from `store.metrics()` — cheap reads,
   keep `/healthz` fast and NEVER failing because of them (best-effort block). Metrics:
   count `processing` rows with expired leases as stranded (surface in `metrics()` +
   `/ops/api/metrics` + the alert check).
2. **Logging config.** One shared helper (e.g. `core/logging_setup.py`) used by BOTH
   `core/app.py` and `worker.py`: format with `%(name)s` + seconds precision, level from
   a new `LOG_LEVEL` setting (default INFO). Kill the two divergent `basicConfig`s.
3. **Correlation.** One INFO line on async accept (`slug`, token, reference id); worker
   lines include slug + token alongside the row UUID (claim, delivered, retry,
   needs_attention).
4. **Actor logging.** `_crm_failure` in every staff router logs the acting `userName`;
   one INFO line on staff write successes (user, entity/id, changed keys — NOT values);
   portal login success/failure logged with username; `/ops` redrive/discard log the
   actor; the provisioning flow (`provision_mentor_user_steps`) logs each step
   server-side at INFO (never the temp password).
5. **Silent-pass inventory.** Add one WARNING each to the eight `except: pass` sites
   listed in the review's logging section (the assignments co-mentor read at
   `assignments/service.py:503` is P1-10 — its warning must name the consequence:
   "co-mentor list unreadable; assignedUsers write may drop co-mentors").
6. **PII (Doug decision D2 below, default yes):** drop the full-payload WARNING in
   `core/submission_log.py` to metadata-only (form, token, reference, error) when a
   durable store is active; keep the full dump only in the storeless (dev) mode.

**DoD:** a local end-to-end run shows one submission traceable by token from accept line
→ worker lines → delivered line; `/healthz` shows worker heartbeat + backlog; log lines
carry module names + seconds in both processes.

## Phase 3 — Staff-tool write chains (P1-9..12 + P2 staff items)

1. **P1-11 redrive guard + audit.** `store.redrive` requires status in
   `{needs_attention, retry, held_honeypot}` (keep held redrive — it's the honeypot
   false-positive recovery). Add `acted_by` (nullable varchar) to `submission` via
   Alembic; `/ops` redrive/discard record the signed-in username.
2. **P1-9 finish re-homing.** `assign_engagement`: when the stale-guard trips but the
   stored mentor EQUALS the requested mentor, proceed as a repair run — re-execute the
   re-homing loop (idempotent writes) and post the stream note, instead of 400. Response
   marks it `{"repaired": true}`.
3. **P1-12 membership TTL.** Staff gates call `refresh_membership` when the session's
   membership is older than `MEMBERSHIP_REFRESH_SECONDS` (new setting, default 900);
   store a `refreshed_at` stamp in the session. `/ops` gains one CRM-backed check per
   request (its gate refresh suffices) so a dead token can't keep using it.
4. **P2 own-profile resolution.** `assigned_user_id`/`resolve_manager_profile`: match
   membership with `in` over ALL `assignedUsersIds`, not `[0]`. Check every caller
   (assignments, sessions, mentorprofile) for the same `[0]` assumption.
5. **P2 calendar id-before-invite.** `sessions/gcal.py`: create the event with
   `sendUpdates=none`, write `googleCalendarEventId` to the CRM, THEN patch with
   `sendUpdates=all` — a failed write-back now cancels the uninvited event
   (best-effort) instead of leaving a double-invite bomb. Keep the whole hook
   best-effort.
6. **P2 session-create attendee failure.** A relate failure after the session create
   returns success-with-warning naming the session id (the `create_contact` pattern),
   never "Could not create session".
7. **P2 provisioning duplicate-User.** Write `cbmEmail` onto the profile BEFORE creating
   the User (or in the same admin-client sequence), so a failed link write can't defeat
   the reuse guard on the next save. Cache the provisioning admin token across calls
   within a process (module-level, re-login on 401) to stop per-call password logins.
8. **P2 status-check sweep.** Compute `mentor_engagement_metrics` ONCE per sweep and
   pass it in (drop the per-mentor full-table scan).
9. **P2 exclude_conversation.** Wrap the store write in try/except → readable 502; do
   the unlink as the signed-in user (falling back to API key only if that's the
   documented design — check with Doug, D5); on unlink failure do NOT record the
   override (or record it and surface "hidden in app, still linked in CRM" — pick one,
   document it).

**DoD:** tests for each; harness pass on the assign-repair flow and the session-create
warning; 3 (membership TTL) verified with a short TTL against local sessions.

## Phase 4 — Gmail sync loss prevention (P1-5)

The review's comms section (F1–F14) has the full detail. Order matters:

1. **Never advance past a failure.** Track per-message ingest failures in `_ingest_ids`;
   if any failed, do NOT save the new cursor past them — simplest correct form: save the
   OLD cursor (the pass re-reads and dedup makes the replay cheap), count
   `failed` separately from `skipped` in the totals, and alert (webhook) when
   `failed > 0` persists across passes. Guard against a permanently-poisoned message
   wedging the cursor forever: after N consecutive passes failing on the SAME message id,
   record it to a dead-letter list in `email_sync_state` (JSON column, Alembic) and move
   on — dead-lettered ids are visible in logs + `/ops` metrics. (This converts the
   robert.cohen class from silent loss to alerting + a bounded skip list.)
2. **`last_synced_at` only on success.** Error-path `save_sync_state` must not bump it
   (add a `touch_synced_at=False` param or a separate last-success column) — it is the
   expired-cursor backfill window source.
3. **History pagination.** Do not save a cursor past unfetched pages: if
   `_MAX_HISTORY_PAGES` truncates with `nextPageToken` still set, save the last
   *processed* page's cursor position (or the old cursor) and let the next pass continue.
4. **Gmail 429/5xx backoff.** Give `core/gmail.py` the DriveClient treatment: bounded
   exponential backoff on 429/5xx honoring `Retry-After`, shared `httpx.AsyncClient` per
   sync pass (connection reuse). Raise the SEND timeout to fit 20 MB bodies (own timeout,
   e.g. 120s) — reduces the double-send window (full send idempotency is out of scope;
   note it).
5. **Shell-before-message ordering.** Create the CCommunication first (or tolerate
   shells): easiest robust fix — when conversation creation succeeded but the message
   create fails, delete nothing (API user can't), but make `find_conversation_for_thread`
   ALSO match empty shells by `threadId` stored on the conversation so a retry reuses the
   shell instead of duplicating. Verify against the schema in `cconversation-entity.md`.
6. **Write-through include-override.** Persist the include override for unknown
   recipients BEFORE attempting write-through ingest (the send already succeeded — the
   override is what guarantees the thread ingests later), and surface a
   write-through failure to the user as a notice, not silence.

**DoD:** unit tests simulating: one failing message (cursor holds, alert fires,
dead-letter after N), expired cursor after an outage (window from last SUCCESS), 21-page
history (no skip). `GMAIL_RESYNC` still works. Do NOT run against live Gmail in this
phase; note the live re-verify items for Doug.

## Phase 5 — Drive + intake-pipeline residuals

1. **Drive create safety (P1-13).** Pre-generate ids (`files.generateIds`) for uploads so
   a lost response is recoverable (retry with the same id cannot duplicate) and rollback
   always knows the id; never blind-retry non-idempotent POSTs without a pre-set id
   (folders: re-run find-or-create instead). Row-first option: insert the `app_document`
   row as `pending` before the Drive upload, flip `active` after — reconcile sweeps
   `pending` older than 1h. Pick ONE strategy, document it in the module docstring.
2. **Folder-cache invalidation.** On a 404 whose target is the cached folder id, clear
   the cache and re-run `_ensure_path` once.
3. **Grants: non-user permissions (review docs-F9).** `apply_folder_grants` treats
   non-inherited `group`/`domain`/`anyone` permissions as unjustified → revoke + alert.
   Reconcile per-folder ERRORS alert when persistent (not just removals).
4. **Content proxy streaming.** Stream downloads (`httpx.stream` → `StreamingResponse`)
   or enforce a size cap read from Drive metadata before fetching. Docs list endpoint
   gains the same per-record ACL read as upload/content/refresh (review docs-D6).
5. **Intake residuals:** catch `store.capture` failure at accept → log payload at ERROR
   (storeless-style) + controlled 503 "please retry" (P2); `json.JSONDecodeError` → 422;
   sync-with-store path uses `ResumableClient` (P1-8); add `Sponsor` to
   `core/schema_contract.py` `cContactType`; info-request description-append gets a
   progress marker so a retry can't double-append (extend the progress contract to a
   named-step guard, review pipeline-M1).

**DoD:** documents tests green (75+); store tests against live local Postgres for the
migration(s); rollback/orphan paths unit-tested with a fake Drive that lies (5xx after
commit, timeout on response).

## Phase 6 — Infra/ops (code where possible, handoffs where not)

Code items: startup mode banner in `create_app` (environment, dryRun, store, async,
staff stack, feature flags — mirror the worker's) + hard-fail on `espo_dry_run=False`
with empty `ESPO_API_KEY` and on `async_delivery=True` with no store; Content-Length
reject middleware on `/api/*/intake` (default 2 MB, volunteer/photo/doc routes keep
their own caps); simple per-IP token bucket on the intake POSTs (in-memory is fine —
single instance); `Literal["user","service"]` for `gdrive_identity`; worker SIGTERM
handler (finish current item, stop claiming); pin Dockerfile base images; remove or
head-stamp the `create_all()` Alembic bypass; `metrics()` gains a windowed latency
(last N completions).

**Doug/ops handoffs (write them into DEPLOYMENT.md, do not attempt yourself):**
DB backup decision + restore runbook (P1-7 — tier upgrade vs scheduled `pg_dump`);
overlay-recovery paragraph (which secret VALUES are unrecoverable); DO alert/uptime
check pointed at the new `/healthz` worker fields; `instance_count: 1` note for the
worker.

## Decisions to confirm with Doug (recommended defaults in parentheses)

- **D1** `/healthz` on DB-down: keep 503 (web tier cycles with Postgres) or 200-degraded
  with the failure in the body? (Recommend: keep 503 for the DB itself — capture
  genuinely can't work — but never 503 for heartbeat/backlog reads.)
- **D2** Drop full-payload PII logging when the durable store is active? (Recommend yes.)
- **D3** Rate-limit thresholds + body cap sizes. (Recommend 2 MB / 30 req per IP per
   10 min on intake POSTs.)
- **D4** Backup approach for `cbm-db`/`cbm-db-prod`. (Recommend tier upgrade.)
- **D5** `exclude_conversation`: should the unlink run as the user instead of the API
  key? (Recommend yes — matches "all staff writes run as the user".)
- **D6** Gmail dead-letter N (consecutive passes before skipping a poison message).
  (Recommend 5.)

## Live-verification checklist (after deploys, with Doug)

Poisoned-row drill on crm-test (worker survives, `/ops` shows traceback); kill the
worker → `/healthz` heartbeat age grows → DO alert fires; one full Gmail pass with a
deliberately over-length subject → alert + dead-letter, no silent loss; assign-repair
flow on a hand-half-assigned engagement; a mentor attempting the details-PUT bypass
gets 404; portal login lines visible in run logs.
