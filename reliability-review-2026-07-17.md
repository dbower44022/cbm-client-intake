# Reliability & Observability Review — CBM Client Intake

**Date:** 2026-07-17 · **Tree:** v0.75.1 (main + uncommitted ET/signature work)
**Method:** six parallel deep reviews (submission pipeline, staff tools, Gmail comms, Drive docs, logging/telemetry, infra/config/ops), every finding verified against the actual code. Findings are ranked; file:line references are to this tree.

**Overall verdict:** the architecture is fundamentally sound — durable capture-before-ack, `FOR UPDATE SKIP LOCKED` + lease, resumable delivery, correct retry classification, honeypot hold-not-drop, and consistently *visible* best-effort contracts in the newer staff tools. The dominant risk pattern is the opposite of what usually ails apps this age: not missing error handling, but **error handling with holes at the seams** — transport-level exceptions that bypass the `EspoError` nets, best-effort `except: pass` blocks that hide real breakage, cursors/leases that advance past failures, and a monitoring stack that runs *inside* the one process it cannot watch (the worker). The logging is good where incidents already happened (comms sync, docs uploads) and thin where they haven't yet (worker tracebacks, staff-action audit, portal logins).

---

## P0 — Critical (fix before anything else)

### 1. Poison payload crash-loops the worker — invisible, alert-free, permanent
`worker.py:75` — `spec.submission_model.model_validate(claimed.payload)` runs **before** the `try:` at line 83. A payload the current schema rejects (e.g. a deploy tightened a form schema after capture) raises `ValidationError` → escapes `process_one` → escapes `run_once` → escapes `main()`'s `while True` → the process dies. App Platform restarts it; the row sits in `processing` under a fresh 900s lease; ~15 min later it's reclaimed and the worker crashes again — forever. The row never reaches `needs_attention`, and `store.metrics()` counts only `pending`/`retry` (`core/store.py:427–450`), so a `processing` row is **invisible to every alert**. Batch-mates claimed alongside it are stranded until lease expiry each cycle.
**Fix shape:** move validation inside the try (ValidationError = permanent → `needs_attention`), and add a top-level guard around `run_once` so no single row can kill the loop.

### 2. The documented rollback config double-delivers submissions
`core/app.py:114–119,147,156` + `worker.py:112–119` — in sync-with-store mode the web tier captures the row as `pending` then delivers synchronously, but the worker **never checks `settings.async_delivery`** — it claims any `pending` row, due immediately. The documented rollback ("flip `ASYNC_DELIVERY=false`", worker left deployed) therefore has both the web tier and the worker delivering the same submission concurrently, with no shared progress → duplicate CClientProfile/CEngagement/etc.
**Fix shape:** gate the worker's claim loop on `async_delivery`, or capture sync-path rows in a non-claimable status.

### 3. `EspoClient` never wraps transport errors — every `except EspoError` net has a hole
`core/espo.py` (all methods) — `httpx.ConnectError`/`ReadTimeout` propagate raw; `EspoError` is raised only for HTTP ≥400 responses. Verified consequences:
- **Intake sync path** (`core/app.py:157`): a CRM outage — the exact scenario V2 exists for — 500s the user, writes no `mark_failed`, no OrchestratorError audit record; the row stays `pending`.
- **Assignments** (`assignments/service.py:548–573`): a timeout mid re-homing aborts the remaining contact/profile/account writes and the stream note, surfacing as a raw 500.
- **Every router's `_crm_failure`** is bypassed: no session-expired handling, no readable 400/403 — a blank 500/edge-504 exactly when the CRM is slow (the historically observed symptom).
- **Portal** (`assignments/auth.py:254–263`): `refresh_membership`'s fail-open catches only `EspoError`, so a CRM outage makes `GET /api/portal/session` a raw 500 — the staff front door goes down with the CRM.
Contrast: `worker.py:49–59` classifies `httpx.TransportError` correctly, and `core/gmail.py:128` / `core/gdrive.py:196` wrap properly. The gap is specific to the Espo client. **One change in `core/espo.py` repairs the whole class** (wrap transport errors in an `EspoError` subclass flagged transient).

### 4. Sessions details PUT is missing the entity allowlist — privilege bypass
`sessions/router.py:255–262` + `sessions/details.py:480–488` — `PUT /{slug}/api/details/{entity}/{record_id}` does not restrict `entity` to `cfg.details_entities` (the peek endpoint does, `sessions/service.py:634–639`). It is a generic write proxy bounded only by the caller's CRM ACL — and the Mentor Role deliberately carries `CMentorProfile edit=all` (required for co-mentor relates). Any Mentor Team member can `PUT /mentorsessions/api/details/CMentorProfile/{any-id}` and set `mentorStatus`, dues, compliance flags on anyone's profile — bypassing both the mentorprofile whitelist and the Mentor Administration gate. **One-line fix.**

---

## P1 — High

### 5. Gmail sync: cursor advances past failed messages — silent permanent loss (already bit prod)
- `comms/sync.py:206–219, 270–279` — `_ingest_ids` swallows per-message failures at WARNING; `sync_mailbox` then unconditionally saves the new cursor. A message whose CRM create 400s or whose fetch times out is never retried. This is the exact mechanics of the robert.cohen incident (7–8 messages lost until a manual `GMAIL_RESYNC`). No dead-letter, no retry queue, and the drop isn't counted in `totals["errors"]` — the incident pass logged "0 sync errors".
- `comms/store.py:124–130` + `comms/sync.py:263–267` — error-path `save_sync_state` bumps `last_synced_at`, which is the **backfill window source** after historyId expiry. A two-week mailbox outage (revoked delegation) → cursor expired → backfill window computed as "yesterday−1d" instead of "last success−1d" → the whole outage span silently skipped. `last_synced_at` must only advance on success.
- `comms/sync.py:45,66–86` — `_MAX_HISTORY_PAGES=20` stops paging but saves the **current-tip** historyId, permanently skipping the unfetched pages after a long outage on a busy mailbox.
- `core/gmail.py:109–137` — no 429/backoff/retry on any Gmail call (unlike DriveClient); during large backfills, quota bursts become runs of swallowed per-message failures (multiplying the first bullet).

### 6. Worker liveness is unmonitored; the alerter is the process that dies
`worker.py:170–182` + `core/app.py:309–334` — both alert checks (backlog age, needs_attention) run inside the worker loop; `/healthz` verifies DB only. A crashed, wedged, or accidentally-undeployed worker produces no alert of any kind — backlog grows until a human opens `/ops` or a user complains. The DO worker component has no health check (process-exit restart only; a hung loop is undetected).
**Fix shape:** surface `oldestPendingAgeSeconds` + a worker heartbeat (row stamped each cycle) on `/healthz`, so any external uptime check sees a dead worker; count `processing`-with-expired-lease rows in metrics (also closes finding 1's visibility gap).

### 7. No backup story for the system of record
`.do/app.yaml:41–43` — `cbm-db` is dev-tier (`production: false`, mirrored live per project record); dev-tier App Platform databases don't get automated backups/PITR. Nothing in DEPLOYMENT.md/STAFF-DEPLOYMENT-GUIDE.md mentions backup or restore. `pending`/`retry`/`needs_attention` rows exist **only** in this DB — DB loss during a CRM outage backlog = unrecoverable submission loss with no runbook. Upgrade tier or add a scheduled `pg_dump`, and write the restore section either way. (The design would survive a restore well — redelivery is idempotent via progress — if a backup existed.)

### 8. Sync-with-store delivery records no progress → redrive duplicates records
`core/app.py:156` — the sync path calls the orchestrator with the raw client; `ResumableClient` is worker-only (`worker.py:81`). A partial sync failure marked `needs_attention` has `progress=NULL`; the /ops redrive re-runs the whole chain — `find_one` dedupes Account/Contact, but plain creates (CClientProfile, CEngagement, …) duplicate. Latent while prod runs async; armed by any fallback to sync mode.

### 9. Half-assigned engagement is unrepairable in-app
`assignments/service.py:451–515` — the engagement write (mentor+status+assignedUsers) lands first; if the process dies or a transport error escapes (finding 3) before the re-homing loop, contacts/profile/account keep the old owner and no stream note posts. On retry the v0.72.1 stale guard itself rejects ("already has a mentor") — there is **no in-app path to finish the re-homing**, and nothing tells anyone it's needed. Allow a "finish re-homing" re-run when the requested mentor matches the stored one.

### 10. Silent co-mentor access revocation
`assignments/service.py:503–504` — `except EspoError: pass` (not even a log) on the `additionalMentors` read that feeds the `assignedUsersIds` merge. If that read fails, the write overwrites the collaborator list with just the new mentor — silently revoking every co-mentor's engagement access. This is the defect class Doug already reported once; if it recurs via this path, the logs will contain nothing.

### 11. /ops redrive & discard: no audit, no actor, no status guard
- `ops/router.py:86–104` — redrive and discard (a terminal, data-affecting staff decision) log nothing and store no actor; the `submission` table has no acted-by column. "Who discarded this submission?" is unanswerable by design.
- `core/store.py:381–395` — `redrive` has no status guard (contrast `discard`, which guards `completed`): redriving a `completed` row re-delivers (duplicate Normal audit record + re-run side effects); redriving a `processing` row creates two concurrent deliveries racing `save_progress` → duplicate creates. Require `needs_attention`/`retry`/`held_honeypot`.

### 12. Stale entitlements: cookie teams refreshed only by the portal
`assignments/auth.py:37`; gates in all five staff routers; refresh only at `portal/router.py:149` — a staffer who bookmarks an app directly keeps their cookie entitlements after CRM team removal, until the CRM token dies (which can be never). `/ops` is worst: it makes no CRM calls at all, so even a dead token never surfaces — an ex-staffer could list/redrive submissions on cookie entitlements alone. Add TTL-based `refresh_membership` inside the staff gates and give `/ops` one CRM-backed check.

### 13. Drive upload orphan windows
- `core/gdrive.py:196–197` — network-level failure on the upload POST (or final resumable chunk) after Drive committed = file exists, caller never learned the id, rollback never attempted → orphan; user retry duplicates. Use `files.generateIds` (pre-generated ids) to make creates recoverable and retry-safe.
- `core/gdrive.py:189–203` — `_send` retries 5xx on non-idempotent POSTs (upload, create_folder, /copy, create_permission): a post-commit 500 + retry double-creates.
- `docs/service.py:250–265` — if rollback delete also fails, the orphan's id lives only in a log line; `run_docs_reconciliation` never sweeps folder contents for row-less files. Consider insert-row-first (status `pending`) → flip to `active` after Drive confirms, so reconcile can sweep orphans.

---

## P2 — Medium (grouped)

### Submission pipeline
- **DB outage at accept = raw 500 + lost payload** (`core/app.py:116–119`): `store.capture` failures uncaught; no payload dump at ERROR, no controlled 503. Also `/healthz` 503s on DB-down, so App Platform cycles the web tier — a Postgres blip downs even the static forms (availability inversion; make a conscious call).
- **Worker post-orchestrator DB errors kill the process** (`worker.py:85–108`): the `except` covers only the orchestrator; `mark_completed`/`mark_retry`/`claim_batch` failures crash the loop. Worst case: delivery succeeded, `mark_completed` blips → crash → redelivery (duplicate Normal audit record; M-class side effects re-run).
- **`update`-based side effects aren't resumable** (`core/resumable.py:63–71`; `forms/info_request/orchestrator.py:144–153`): the info-request description **append** re-runs on retry — duplicate blocks in staff-visible data. Progress is also persisted *after* each create (`resumable.py:47–53`): a kill between POST and record = one duplicate record; accepted at-least-once cost, worth documenting.
- **Fixed 900s lease, no renewal** (`core/store.py:249–301`): a CRM brownout can push a serial 10-row batch past the lease; deploy-overlap workers double-claim the tail. Renew between items or claim per-item.
- **Schema-drift contract stale** (`core/schema_contract.py:80`): `Contact.cContactType` expected-list lacks `"Sponsor"`, which the sponsor orchestrator writes — the drift check won't pre-warn on exactly that discriminator.
- **Malformed JSON → 500 not 422** (`core/app.py:82–83`); **no HTTP connection reuse** in EspoClient (new client + TLS handshake per call, ~6+ per delivery).

### Staff tools
- **Write-ambiguity on timeouts, no idempotency keys anywhere**: a timed-out `POST /User` (provisioning) or session create + user retry = duplicate User / duplicate session.
- **Provisioning duplicate-User path still reachable** (`mentoradmin/service.py:642–667`): User created, then link+`cbmEmail` backfill in a separate staff-token PUT; if that PUT fails while `cbmEmail` was blank, the reuse guard can't fire and the next save mints `jane.doe2@…` + second welcome email. Write `cbmEmail` before/with User creation.
- **Calendar double-invite window** (`sessions/gcal.py:211–227`): event created (invitations emailed) *before* the event id is written to the CRM; a failed write-back = orphan event + the next save creates a second event and re-emails everyone. Persist the id first or look up by session on retry.
- **Session create + attendee relate halt-on-failure** (`sessions/service.py:867–870`): relate failure surfaces as "Could not create session" while the session exists → retry duplicates. (Contrast `details.py:447–455`, which names the created id — do the same.)
- **Own-profile resolution matches only the first collaborator** (`sessions/service.py:143–166` via `assigned_user_id` = `assignedUsersIds[0]`): on collaborators-shaped prod, a profile listing someone else first makes the mentor's own profile unresolvable — and can resolve someone *else's* profile as "mine" in `/mentorprofile` (editable via membership). Test membership with `in`.
- **Read-modify-write on `assignedUsersIds`** (assignments + 3 sites in sessions): concurrent co-mentor add vs assign = lost update, silent access loss.
- **The assign stale-guard is advisory** (read-then-write, ~1s race window; no other write path got a guard — notes, mentor saves, details saves are last-write-wins).
- **Status-check sweep is O(mentors × engagements)** (`mentoradmin/service.py:741` → full CEngagement sweep per mentor): will 504 as data grows; compute metrics once.
- **Provision admin logs in fresh every call** (`mentoradmin/router.py:434–462`): a rotated password turns sweeps into repeated failed admin logins → EspoCRM brute-force lockout of the service account.
- **`exclude_conversation`** (`sessions/router.py:451–461` + `comms/service.py:178–196`): team-gated only, performs the unlink with the privileged API key (bypasses user ACL), and records the PG override even when the CRM unlink fails (UI still shows the conversation; nothing retries).
- **Docs list endpoint skips the per-record ACL read** (`sessions/router.py:642–655`) that upload/content/refresh perform — metadata (filenames, uploaders, webViewLinks) enumerable across ACL boundaries.
- **Send-path double-send** (`core/gmail.py` + `comms/quicksend.py:97–101`): 20s timeout on up-to-27MB send POSTs; a timeout after Gmail committed → "try again" → duplicate email. Raise the send timeout; consider a client-side in-flight guard.
- **Write-through failure after send to non-contact recipients** (`comms/service.py:475–501`): the include-override is only persisted when write-through succeeded, so one Espo blip permanently orphans that thread from the CRM (the code comment claims the sync picks it up — false for unknown recipients), and the user sees success.
- **Conversation shell before message row** (`comms/sync.py:169–172`): a failed CCommunication create leaves an empty shell that thread-matching can't find → duplicate conversations on retry (the 5 hand-deleted crm-test shells came from this ordering; unchanged).
- **Folder-cache staleness** (`docs/service.py:163–165`): a console-deleted record folder 404s every subsequent upload forever; no invalidation/re-create path.
- **Grants engine ignores non-`user` permissions** (`docs/grants.py:143–147`): a `group`/`domain`/`anyone` grant added in the console is never revoked by reconcile — violating the access model it exists to enforce. Reconcile *errors* also never alert (only removals do).
- **Content proxy fully buffers** (`sessions/router.py:759–763` + `core/gdrive.py:341–352`): no size guard on `?original=true` — a few concurrent large downloads can OOM basic-xxs. Stream or cap.
- **Convert-on-view temps leak on client disconnect** (`core/gdrive.py:391–395` — `finally` delete is cancelled with the request) and accumulate in record folders now visible to grant-holders (the "nobody sees it" docstring predates the grants model).

### Infra / config
- **No startup mode banner on web; silent degraded modes** (`core/config.py` all-default): empty `DATABASE_URL` ⇒ in-memory capture; `ASYNC_DELIVERY` without store ⇒ silently sync; `SESSION_SECRET` unset ⇒ staff stack silently unmounts; live mode + empty API key ⇒ boots fine, 401s at runtime. Log an effective-mode banner in `create_app` and hard-fail contradictory combos. (The worker has a one-line banner; the web tier has nothing.)
- **`create_all()` bypasses Alembic** (`core/app.py:255–257`, `worker.py:133`): a fresh env booted before its migrate job exists builds current schema with no `alembic_version` → later `upgrade head` wedges every deploy. Drop it or stamp head.
- **No rate limiting or body-size cap on public forms**: honeypot + idempotency only; a token-varying bot writes unbounded rows/CRM records; the DO edge passes ≥60MB bodies and `await request.json()` buffers before validation. Early Content-Length reject + modest per-IP bucket.
- **Floating Docker tags** (`Dockerfile:3,6`): `python:3.12-slim` + `uv:latest` — a rebuild months later gets different toolchain; pin minor/digest.
- **Worker has no SIGTERM handling** (`worker.py:231–232`): every deploy kills mid-delivery; lease+resume recovers, but each push rolls the duplicate-create dice and delays the in-flight row up to 15 min. Also: alert-cooldown state and Gmail cursors assume exactly one worker instance — document/guard `instance_count: 1`.
- **Comms sync runs inline on the delivery loop** (`worker.py:167–203`): a full `GMAIL_RESYNC` backfill blocks submission delivery and the alert checks for its whole duration.
- **Gitignored overlays** are the only local copy of live config, inside Dropbox; recovery via `doctl apps spec get` is proven but the "laptop dies" runbook (and which secret *values* are unrecoverable: ESPO_API_KEY, SESSION_SECRET, SA JSON, APP_ENCRYPTION_KEY) belongs in DEPLOYMENT.md.

---

## Logging / telemetry assessment

**Configuration**
- `core/app.py:42–46` — web format omits `%(name)s` (no module attribution; can't filter httpx noise) and has minute-resolution timestamps, no timezone.
- `worker.py:123` — the worker's separate `basicConfig` (it never imports `core.app`) uses the stdlib default format: **worker log lines have no timestamps at all**. Retry forensics depend entirely on DO console timestamps.
- No `LOG_LEVEL` setting anywhere — DEBUG lines (notably comms triage decisions: *why* a message was skipped, `comms/sync.py:107,129`) are permanently invisible in prod with no lever short of a deploy.
- The `httpx` INFO line per outbound call is currently the *only* record of most CRM traffic — an accidental trace that vanishes if anyone tunes logging.

**Correlation**
- Async accept (the production mode) logs **nothing** — no token, no reference (`core/app.py:147–148`). The trace starts at the worker, which logs only the row UUID (`worker.py:92–109`), never slug/token. Web keys on token, worker on UUID; the join exists only in Postgres.
- No request-ID middleware; concurrent staff users' warnings can't be grouped into per-request narratives; no latency/status telemetry beyond uvicorn access lines.

**Missing incident context**
- `worker.py:85–101` — non-transient failures store/log `str(exc)` only, no traceback. A code bug (`KeyError: 'contactId'`) lands in `needs_attention` as an unusable four-character string; **the single highest-payoff logging fix** is `exc_info=True` + traceback tail in `last_error`. Same pattern in `sessions/gcal.py:82–84` and the worker's timer guards.
- Staff-tool save failures never log the attempted payload (`sessions/details.py:480–489`) — combined with the field-ACL-silently-strips gotcha, "why didn't my edit stick" always requires live repro.
- `_crm_failure` warnings omit the acting user.

**Audit trail**
- Espo `modifiedBy` + v0.74.0 stream notes are the right backbone, but: portal logins (success *and* failure) are entirely unlogged; staff save successes log nothing with a user; the assignment log line lacks the acting staffer; the provisioning SSE flow (mailbox + User creation — the highest-privilege action in the app) yields events to the browser only, zero server-side log; /ops redrive/discard have no actor anywhere (P1 finding 11).

**Silent `except: pass` inventory** (each deserves one WARNING):
`assignments/service.py:503` (co-mentor read — P1 finding 10), `mentoradmin/service.py:409–412` (reconcile_user_links), `mentoradmin/service.py:257–260` (sync_record_status persist), `mentoradmin/router.py:162–165` (admin-login fallback silently downgrades the sweep), `sessions/service.py:1015–1018` (linkedCompany fallback), `comms/crm.py:349–351`, `comms/summarize.py:155–156`, `assignments/auth.py:76–77`.

**Metrics gaps**
- Worker liveness (P1 finding 6); `processing` rows invisible to metrics; Gmail per-message drops invisible ("0 errors" on the loss pass) and mailbox `errors` never alerted; `avgLatencySeconds` is lifetime-cumulative (can't show this week's regression); no web-tier error-rate/latency counters.

**Hygiene**
- Full submission payloads (PII) log at WARNING whenever the CRM audit write fails — i.e. bulk PII into DO logs precisely during CRM outages; with the durable store live, drop to metadata. Contact-email query params appear in httpx INFO URLs. No secrets/tokens logged anywhere (verified); no print() misuse; the two fake-mailbox invalid_grant WARNINGs each pass train readers to ignore WARNING.

---

## What's done well (keep doing these)

- **Capture-before-ack + DB unique idempotency key** (`uq_submission_form_token`, race-correct via `on_conflict_do_nothing` + read-back).
- **`FOR UPDATE SKIP LOCKED` + lease reclaim** — textbook; crashed workers can't strand rows (the gaps above are at the edges, not the core).
- **Resumable delivery** with per-entity progress, verified by tests; retry classification (transport=transient, 5xx/408/429=transient, other 4xx=permanent, unknown=permanent) is exactly right.
- **`EspoError` messages** are consistently self-describing (op+entity/id+status+body) and logged at every router boundary; `forbidden_hint`/`validation_message` turn them into precise user-facing errors.
- **Honeypot hold-not-drop** with recovery path; enum-drift and phone-implausibility degrade to notes, never failed deliveries.
- **Best-effort contracts are visible** in the newer tools: `{ok,error}` results surfaced as UI notices (calendar, provisioning, co-mentor add), `reassignmentErrors` in both response and stream note.
- **comms/sync** is the best-instrumented subsystem (per-message warnings with mailbox+id, `log.exception`, per-pass totals, per-mailbox error state in the DB) and its per-mailbox blast-radius isolation + cursor-after-ingest crash safety are correct.
- **docs/** has the best external-call hygiene (uniform `_send` funnel: timeout, status-aware backoff, rate-limit sniffing), a correctly-ordered rollback with loud `ROLLBACK FAILED` logging, exemplary upload receipt logs (who/what/bytes), a convergent idempotent grants engine, and record-scoped `get_document`.
- **Auth**: complete gate coverage (incl. SSE stream, quicksend registrations), empty team lists fail closed, `SESSION_SECRET` degrades atomically, only tokens (never passwords) in the cookie.
- **Deploy/infra**: additive-only migrations behind a PRE_DEPLOY job sharing the app's engine normalization; `uv sync --frozen`; `.dockerignore`/`.gitignore` secret discipline; the deploy.sh live-app guard; `/healthz` deliberately not coupling to the CRM.

---

## Suggested fix order (effort-weighted)

| # | Item | Findings | Effort |
|---|------|----------|--------|
| 1 | Worker: validation inside try + top-level `run_once` guard + `exc_info` tracebacks in `last_error` | P0-1, logging | Small |
| 2 | Wrap httpx transport errors in `core/espo.py` as transient `EspoError` | P0-3 | Small |
| 3 | Entity allowlist on the details PUT | P0-4 | One line |
| 4 | Gate the worker claim loop on `async_delivery` | P0-2 | Small |
| 5 | `/healthz`: backlog age + worker heartbeat; count expired-lease `processing` rows in metrics | P1-6 | Small |
| 6 | Gmail sync: don't advance cursor past failed ingests; `last_synced_at` only on success; drain `nextPageToken` or hold the cursor; alert on fetched−stored | P1-5 | Medium |
| 7 | Logging pass: shared basicConfig (name+seconds, both processes), `LOG_LEVEL` setting, async-accept INFO line, worker slug+token in lines, actor in `_crm_failure` + staff-write successes, portal login lines, WARNINGs in the silent-pass list, /ops actor logging | telemetry | Medium |
| 8 | Redrive status guard + actor column; assign "finish re-homing" path; log the co-mentor read failure | P1-9/10/11 | Small–Medium |
| 9 | Backup: tier upgrade or scheduled pg_dump + DEPLOYMENT.md restore section | P1-7 | Ops |
| 10 | Startup mode banner + fail-fast contradictory config; body-size cap + per-IP rate limit on `/api/*/intake` | infra | Small |
| 11 | Drive: pre-generated file ids for creates; folder-cache 404 invalidation; row-first upload (sweepable orphans) | P1-13 | Medium |
| 12 | ResumableClient on the sync path; membership TTL refresh in staff gates; calendar id-before-invite; provisioning cbmEmail-before-User | P1-8/12, P2 | Medium |
