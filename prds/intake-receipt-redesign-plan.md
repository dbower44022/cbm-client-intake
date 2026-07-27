# Intake Receipt Redesign — the CRM as the single source of truth for every arrival

*Approved by Doug 2026-07-27 (this document records the design elicited and
ruled in that conversation). Status: **APPROVED, NOT BUILT.** Companion CRM
build handoff: `cintake-submission-redesign.md` (repo root). Supersedes the
`reason`/`status` model in `cintake-submission-entity.md`.*

---

## 1. The requirement (Doug's ruling, verbatim intent)

**The CRM is THE single source of truth. It must be auditable to determine all
business transactions.** Consequences:

1. **Every arrival is written to the CRM** as an intake receipt
   (`CIntakeSubmission`) — including every email received at info@, *before*
   any human decision. Junk volume is acceptable; the CRM's database can hold
   millions of rows.
2. **Every disposition is recorded in the CRM** — who decided, when, and why.
   A discarded critical email must be answerable from the CRM alone.
3. **Fix the data structure now instead of bandaiding it** — the confusing
   `reason` + `status` pair is replaced outright, not papered over.

## 2. The new data structure

One receipt record per arrival, updated as its state changes. The old
`reason` and `status` fields are **deleted** after migration.

### 2.1 Intake Status (enum — the ONE status field)

| Value | Meaning |
|---|---|
| `Received` | Arrived and being processed (covers waiting + delivery + automatic retries). |
| `Completed` | The intake information was proper and the proper CRM records were written. |
| `Held-Spam` | The spam trap was triggered; no business records created. |
| `Held-Email` | An inbound info@ email awaiting human review; no business records created. |
| `Error` | Writing the CRM records failed; a human must act. |
| `Discarded` | A person decided no business records should be created (junk / no action). |

Lifecycle:

```
web form:   Received ──► Completed
                └──────► Error ──► (Re-drive) ──► Completed
                                └► (Discard)  ──► Discarded
spam trap:  Held-Spam ─► (Re-drive) ──► Completed
                      └► (Discard)  ──► Discarded
info@ email: Held-Email ─► (Approve) ──► Received ──► Completed / Error
                        └► (Discard) ──► Discarded
```

`Discarded` and `Completed` are terminal. Only humans produce `Discarded`;
only the app produces every other value.

### 2.2 Intake Message (text)

Plain-language explanation, set by the app per status (Doug's wording):

| Status | Intake Message |
|---|---|
| `Received` | *(blank)* |
| `Completed` | *(blank — the created-record links carry the outcome)* |
| `Held-Spam` | `The <form type> spam trap was triggered` |
| `Held-Email` | `All emails need review` |
| `Error` | A **long, specific** description: which record-creation step failed, the CRM's rejection verbatim, what was and wasn't created, and possible fixes (e.g. "the phone number 12312… was rejected by the CRM — correct it in the payload and Re-drive"). |

The message is not overwritten on disposition (the disposition fields carry
that part of the story).

### 2.3 Payload (text) + Email link (url)

- **Web forms:** `payload` holds the complete form input as submitted (JSON;
  the hidden spam field cleared; oversized values like base64 resumes noted as
  omitted — they are preserved in the app store).
- **Emails:** `payload` holds the email **content itself** — From, To, Subject,
  Date, body text — because a Gmail link is only usable by someone with
  mailbox access and a mailbox message can be deleted by a human. The
  source-of-truth copy lives in the CRM. `emailLink` (separate url field)
  additionally deep-links the original in the shared info@ mailbox for
  convenience.

The native `description` field is no longer written (historical records keep
theirs).

### 2.4 Disposition fields (the business decision, in the CRM)

Written whenever a human dispositions a held/errored receipt (Approve,
Discard, or Re-drive):

| Field | Type | Content |
|---|---|---|
| `dispositionedBy` | varchar | The acting staff user (display name + username). |
| `dispositionedAt` | datetime | When. |
| `dispositionReason` | varchar | **Required for Discard** (the app enforces it — the UI will not discard without a reason). Optional note for Approve/Re-drive. |

### 2.5 Unchanged fields

`name`, `form` (incl. the `Email` value), `submitterEmail`, `source`, and the
`contact` link all stay as they are. On `Completed`, `contact` still links the
Contact the submission produced or matched.

## 3. Write model (this is a real change, not just fields)

Today the receipt is **create-only, once, after the outcome, best-effort**.
The new model:

1. **Create at arrival.** Web form → receipt created at capture time with
   `Received` (or `Held-Spam` when the trap fired). info@ email → receipt
   created at capture time with `Held-Email` — *before* any human decision.
   The CRM now sees 100% of arrivals.
2. **Update on every state change.** Delivery outcome (`Completed` / `Error`),
   Approve, Re-drive, Discard — each updates the same receipt (status,
   message, disposition fields, contact link).
3. **The app tracks the receipt.** New column on the app's `submission` table:
   `crm_receipt_id` (Alembic migration) so updates target the right CRM record
   and reconciliation can compare the two systems row-by-row.
4. **CRM role change required:** the intake API user needs **edit** on
   `CIntakeSubmission` (today create/read suffices). See the handoff doc.

## 4. Guaranteed truth: the reconciliation sweep (Doug-approved shape)

The 8-try background worker keeps its job (delivering the *business records*).
The receipt writes get their own guarantee:

- **Opportunistic first:** every receipt create/update is attempted at the
  moment it happens (as today, but now including arrival-time and
  disposition-time writes).
- **The sweep:** a timer inside the existing background worker (default
  hourly; `RECEIPT_RECONCILE_SECONDS`) compares every app-store submission row
  against the CRM: receipt missing → create it; status / disposition / message
  stale → update it. Idempotent — running it twice changes nothing the second
  time.
- **Manual trigger:** a "Sync receipts to CRM" action in Submission Admin runs
  the same sweep on demand (the user-introduced retry Doug asked for).
- **Monitoring:** the sweep's drift count (receipts missing or stale) joins
  the existing admin alerting — the same channel that already emails
  admin@cbmentors.org about failed deliveries, backlog, and a dead worker.
  Persistent drift = the system admin hears about it without watching logs.
  Every individual failed write still lands in the error log.

Net guarantee: whatever fails and whenever, once the CRM is reachable the
sweep converges it — every arrival has a receipt, every receipt shows the
true status and disposition.

## 5. One vocabulary everywhere

Submission Admin stops showing machine statuses. Its Status column, detail
header, filters, and the portal-badge tooltips use exactly the receipt
vocabulary: **Received / Completed / Held-Spam / Held-Email / Error /
Discarded** (internal machine states map: pending·processing·retry →
Received; needs_attention → Error; held_honeypot → Held-Spam; held_review →
Held-Email; completed → Completed; discarded → Discarded). The internal words
never appear on a screen again. The Open/Closed work-queue flag and the
info-request Request status (New / In Progress / Responded / Closed) are
unchanged and remain what they are: "is it still on the to-do list" and "the
conversation state" — both distinct from intake processing.

## 6. Behavior changes beyond the schema

1. **Discard requires a reason** (UI: reason picker like the existing Close
   popover) and stamps the disposition fields — in the app store AND the CRM
   receipt.
2. **Held emails are in the CRM immediately** at capture (`Held-Email`), not
   only after Approve. Approve moves the SAME receipt through
   `Received → Completed`; Discard moves it to `Discarded`. Nothing about the
   Approve/Discard workflow location changes — Submission Admin remains the
   triage surface.
3. **Spam receipts** change shape only (message wording + payload field);
   they were already written at arrival.

## 7. Migration (both environments: crm-test, then prod)

1. **CRM build first** (additive — see the handoff doc): new fields + enum,
   edit grant. Safe before the app deploys: EspoCRM ignores writes to fields
   that don't exist, and the sweep back-fills anything missed during the
   window.
2. **App deploy**: new write model + `crm_receipt_id` column (Alembic) +
   sweep + UI vocabulary.
3. **One-off migration script** (per env, dry-run first):
   - For every existing `CIntakeSubmission`: set `intakeStatus` from `reason`
     (`Normal`→`Completed`, `Honeypot`→`Held-Spam`,
     `OrchestratorError`→`Error`), set `intakeMessage` per §2.2, copy the old
     `description`'s JSON block into `payload`.
   - **Back-link**: extract the `submission_token` from each receipt's stored
     JSON, match it to the app-store row, and store `crm_receipt_id` — so the
     sweep never creates a duplicate receipt for a pre-redesign submission.
     App rows whose token matches no receipt (the old best-effort write
     failed back then) get their receipt created by the first sweep.
   - App-store rows already `discarded`/held get their receipts updated to
     the matching terminal status (dispositionedBy = the stored `acted_by`
     where present, reason = "migrated — predates disposition reasons").
4. **Delete `reason` and `status`** in the CRM (Entity Manager) once the
   migration is verified — the bandaid fields do not linger.

## 8. Build phases

| Phase | Contents |
|---|---|
| **A — schema + write model** | CRM fields built (handoff doc); app: `crm_receipt_id` migration, receipt create-at-arrival + update-on-change, Error message composer, email payload/link, Discard-with-reason UI + disposition stamping. |
| **B — the guarantee** | Reconciliation sweep (timer + manual trigger + drift alerting); migration script; run migration on crm-test, verify, then prod; delete old fields. |
| **C — vocabulary** | Submission Admin + portal badge tooltips display the receipt vocabulary only; staff docs updated (`submission-admin.md`, `intake-processing-overview.md`, the flow diagram's tab 0 collapses to one column). |

Each phase ships tested + harness-verified per repo convention; live checks
per phase are listed in the handoff doc §Verification.

## 9. Explicitly out of scope

- The info-request **Request status** lifecycle (unchanged).
- The delivery worker's retry policy (unchanged: 8 tries, backoff).
- The planned CRM-side alert workflow (`cintake-submission-entity.md`
  "Alerting") — if ever built, it should key on `intakeStatus` ∈
  {Held-Spam, Held-Email, Error}; noted in the handoff.
- Bulk purge/archival policy for junk receipts (Doug: volume is acceptable;
  revisit only if it ever isn't).
