# info@cbmentors.org rollout plan — shared identity for outbound + inbound email

**Status: PLAN (Doug's rulings captured 2026-07-21; build/activation not started)**

The info@cbmentors.org Workspace mailbox is now live (real licensed user, so
the existing domain-wide delegation covers it — no new Google scopes). This
plan routes **all appropriate** outbound and inbound email through it.

## Doug's rulings (2026-07-21)

1. **Outbound scope: everything except mentor↔client.** All staff-tool email
   — /ops submission replies AND the quick-compose surfaces on Client
   Administration + Mentor Administration — sends as info@. The session
   tools' composes (record compose + their grid quick-compose) stay as the
   mentor's own cbmEmail: relationship mail comes from a person.
2. **No auto-acknowledgment emails.** The public forms stay silent on
   submit; info@ is for replies and inbound. (Revisit later if wanted —
   nothing in this plan precludes it.)
3. **Worker alert emails keep admin@cbmentors.org** as sender — internal
   plumbing stays off the customer-facing identity.
4. **The Marketing Admin Team monitors the /ops queue** (and the info@
   Gmail inbox itself — see the consequences note in Phase 2).

## Current state (what's already built)

- **v0.110.0 shared-mailbox model (deployed, dormant):** with `OPS_MAILBOX`
  set, /ops sends and reads conversations as info@ ("CBM Info", no personal
  signature), every send's Gmail thread is anchored to its submission
  (migration 0013 — already applied on both envs), and the **worker polls
  the info@ inbox** (`OPS_INBOUND_SECONDS`, default 300s), capturing each
  NEW inbound thread as a `held_review` `info-email` submission for
  Approve/Discard triage (Approve = redrive through the info-request
  orchestrator; Discard = spam, zero CRM residue). Outbound-initiated
  threads and bounces are skipped by capture; replies to anchored
  form-conversation threads never double-capture.
- **Quick-compose (assignments/mentoradmin)** registers `register_quicksend`
  WITHOUT a `shared_mailbox` resolver today → sends as the signed-in
  staffer. The resolver hook already exists (ops uses it) — Phase 2 is a
  small wiring change, not new machinery.

## Phase 1 — activate the /ops shared mailbox (config only, no code)

1. **CRM (both instances):** add an **"Email"** option to
   `CIntakeSubmission.form` — until it exists the audit log for approved
   email submissions WARNs (best-effort, non-blocking).
2. **crm-test first:** set `OPS_MAILBOX=info@cbmentors.org` on **web AND
   worker** of the crm-test overlay (`.do/app.prod.yaml`), apply via doctl.
   Run the verification pass (below). NOTE: both envs polling the same
   physical inbox double-captures new threads into both queues — harmless
   short-term (separate DBs/CRMs; capture never mutates the mailbox), but
   **remove `OPS_MAILBOX` from crm-test after verification** so prod is the
   sole steady-state consumer.
3. **Prod:** same two env vars on `.do/app.prod-crm.yaml`, apply.
4. **Verification (the v0.110.0 §first-live-pass):** send a real email to
   info@ → held row appears in /ops → Approve → Contact +
   CInformationRequest created → reply from the detail (goes out as
   info@/"CBM Info") → the thread is visible to a SECOND admin → a
   submitter reply to that thread shows in the conversation and does NOT
   create a second queue row.

## Phase 2 — staff quick-compose sends as info@ (small build)

- **Build:** pass a `shared_mailbox` resolver (the ops `_ops_shared_mailbox`
  pattern — reuse `OPS_MAILBOX`/`OPS_MAILBOX_NAME`, no new setting) to
  `register_quicksend` in `assignments/router.py` and
  `mentoradmin/router.py`. Session-tool routers are deliberately untouched
  (ruling 1). `GET /mailbox` then reports "CBM Info" so the compose dialog
  shows the right identity; shared sends carry no personal signature (by
  design); the CRM Email write-back still records the acting user.
- **Consequences to accept:**
  - Replies to staff notices (e.g. MentorAssignmentNotice) land in the
    **info@ Gmail inbox**, not the sender's mailbox — and NOT in the /ops
    queue (outbound-initiated threads are skipped by inbound capture).
    The Marketing Admin Team watches the inbox for these (ruling 4).
  - The personal-mailbox Gmail sync will no longer see these sends (info@
    is not a synced manager mailbox), so they won't appear in session-tool
    Communications tabs. Acceptable: these surfaces are record-less
    notices, not client correspondence.
- **Verification:** an Assign in Client Administration → compose shows
  "CBM Info" → send → copy in info@ Sent; recipient sees From: CBM Info
  <info@cbmentors.org>.

## Phase 3 — retire espo@ CRM-direct sends (CRM/Workspace side, Doug)

EspoCRM's own outbound (mentor-provisioning `sendAccessInfo` welcome emails,
CRM notifications) still uses the espo@ return address — Doug wants this
ended (standing item since v0.110.0). Point EspoCRM's system outbound SMTP
at **info@** (Google Workspace SMTP relay or an app password on the info@
account), on both instances. App untouched.

## Phase 4 — runbook + follow-ups

- **Queue ownership:** Marketing Admin Team works the /ops Open filter
  daily (triage inbound captures, answer submission replies) and watches
  the info@ Gmail inbox for staff-notice replies (Phase 2 consequence).
- **Known gap — bounce visibility (optional build):** a bounced /ops reply
  is invisible in the app (mailer-daemon is triaged as junk and the
  conversation view searches only the submitter's address — the
  2026-07-21 allen.ingram incident). Follow-up: search the sending mailbox
  for delivery-status messages referencing the sent thread and surface a
  red "bounced" marker in the conversation + reply-state column.
- **Interaction with `COMMS_INTERNAL_DOMAINS` (v0.127.0):** info@ is at
  cbmentors.org, so the mentor-mailbox sweep never scope-matches it —
  correct: /ops owns the info@ channel; a client email that Cc's info@
  still ingests normally on the mentor side (external participant
  present).
- **Out of scope by ruling:** auto-acks (ruling 2), alert sender change
  (ruling 3), mentor↔client identity change (ruling 1).

## Order of operations

1. CRM "Email" enum option (both CRMs) — Doug, 5 min.
2. Phase 1 on crm-test → verify → remove from crm-test.
3. Phase 1 on prod → steady state.
4. Phase 2 build + harness verification → deploy → live check.
5. Phase 3 whenever convenient (independent).
6. Bounce-visibility follow-up — separate session, on request.
