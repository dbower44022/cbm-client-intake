# Action History & Reporting (CActionLog) — PRD

**Status:** Live (Phase 1) · 2026-07-21
**Related:** `prds/action-history-plan.md` (design + diagnosis), `core/action_log.py`
(implementation)

---

## 1. Summary

Every meaningful action a staff member takes through the CBM apps now leaves a
durable, attributable record in EspoCRM — **on the record it touched** (a stream
note) **and** in a **queryable reporting log** (`CActionLog`). This turns "who
changed this, when, and how?" from a code-forensics exercise into a filter-and-read.

## 2. Problem & motivation

Staff make consequential changes through the apps — assigning a mentor, recording
a session, approving a mentor — and the CRM's history often couldn't answer what
happened, because:

- the fields that change most (`mentorProfile`, `mentorStatus`,
  `partnershipStatus`, all assignment fields) were **not audited**, so they
  changed with no trace;
- app writes run **as the signed-in user**, so they were indistinguishable from
  manual CRM edits; and
- the meaningful actions are **multi-record** (an assignment touches ~6 records),
  which no single field-change note captures.

Two real investigations (a duplicate-session incident and a mentor-swap) dead-ended
on exactly this. This feature removes that blind spot.

## 3. Goals / non-goals

**Goals**
- One clear, human-readable history line on the affected record for every
  mutating staff action, naming the app, the action, the before→after, and the actor.
- A cross-record, filterable, exportable **reporting log** so questions like
  "everything Jane did this week" or "every assignment in July" are a saved search.
- Ship safely and incrementally, without blocking or slowing any user operation.

**Non-goals**
- Auditing *every* field edit keystroke (incidental field changes are covered by
  EspoCRM's native Audited-field history, configured CRM-side).
- Replacing EspoCRM's stream; this augments it.
- A bespoke in-app reporting UI in Phase 1 (the CRM's native list view serves it).

## 4. Users & use cases

- **CBM administrators / support:** "This engagement changed — who did it and
  when?"; "Show me everything this staffer did"; "Every mentor approval this month."
- **Managers:** per-record history at a glance (an "Action Log" panel on each
  engagement, mentor, company, etc.).
- **Engineers:** reconstruct an incident from a queryable log instead of guessing
  from CRM field state.

## 5. How it works

Each mutating action performs **two writes**, from one shared helper
(`core/action_log.record_action` / `log_action`):

1. **Stream note** — posted on the primary record **as the acting user**, so the
   record's own history reads naturally, in the format:
   `[App] <what changed, before → after> · <downstream records touched> · by <Actor>`
2. **`CActionLog` row** — one per action, written **via the shared API key** (not
   the user's token) so the reporting log never depends on each staff role's
   permissions; the actor is stored explicitly so attribution stays exact.

Example (a real live row):
> **Mentor assigned: Douglas Bower. Status → Pending Acceptance. Re-homed 1/1
> contact(s), client profile, company.** — App: Client Administration · Action:
> Mentor Assigned · by Douglas Bower · Record: Engagement "Tester Tommy — Intake
> 2026-07-21" · Outcome: Success

## 6. Data model — the `CActionLog` entity

| Field | Type | Meaning |
|-------|------|---------|
| `name` | Varchar | the one-line summary (also the stream-note text) |
| `app` | Varchar | which app the action came through (Client Administration, Client/Partner/Funder Management, Mentor Administration, …) |
| `category` | Varchar | coarse grouping for reports (Assignment, Session, Status Change, Provisioning, …) |
| `actionType` | Varchar | the specific verb (Mentor Assigned, Session Recorded, Login Provisioned, …) |
| `actorName` | Varchar | who performed it |
| `summary` | Text | full human-readable description |
| `details` | Text (JSON) | structured before→after + downstream records touched |
| `outcome` | Enum | Success / Partial / Failed |
| `record` | Belongs-to-Parent | the affected record — any of Account, Contact, Engagement, Mentor Profile, Client Profile, Partner Profile, Sponsor Profile, Session — giving click-through + a per-record "Action Log" panel |
| `createdAt` | Date-Time | when (native) |

**Design decisions (rationale in the plan doc):**
- **`actionType`, `app`, `category` are free-text Varchar**, not enums — the app
  sends a growing vocabulary of action names, and an enum would *reject* (and
  silently drop) any value it didn't list. Free-text guarantees coverage forever.
- **The record link is named `record`, not `parent`** — `parent` is reserved on
  the entity (it carries EspoCRM's built-in activity parent/child links).
- **Attribution is the `actorName` text field**, not a User link (a User link's
  auto `actorName` would collide); it is filterable and reliable.

## 7. Functional requirements

- **FR-1** Every wired mutating action writes exactly one `CActionLog` row and one
  stream note on the affected record.
- **FR-2** Each row records app, action, category, actor, a human summary, a
  structured `details` diff, the affected record (linked), and an outcome.
- **FR-3** The actor is the signed-in staff member, recorded even though the log
  row is written under the shared API identity.
- **FR-4** Status/lifecycle changes record before→after (e.g. "Status →
  Pending Acceptance", "Assigned → Active").
- **FR-5** Multi-record actions name the downstream records touched (contacts,
  client profile, company, sessions) in the summary and details.
- **FR-6** Reporting is available in the CRM immediately: filter/sort the Action
  Log list by app, action, category, actor, date, or record, and export to CSV;
  each record shows its own Action Log panel.

## 8. Action catalog

**Live (Phase 1):**
- Client Administration — Mentor Assigned, Mentor Reassigned, Assignment Repaired
- Session tools (Client/Partner/Funder Management) — Engagement Accepted, Session
  Recorded, Engagement Activated, Co-mentor Added, Co-mentor Removed

**Planned (wire into the same log, no further CRM setup):** mentor **provisioning**
(login + mailbox creation — the highest-value action still unlogged) and
mentoradmin edits; session **Details** edits, contact link/unlink, contributions;
My Mentor Profile self-edits; directory edits; document upload/archive/access
grants; email sends. Full endpoint list: plan §5.1.

## 9. Non-functional requirements

- **NFR-1 Never breaks the operation.** Both writes are best-effort; a failure
  never rolls back or blocks the user action.
- **NFR-2 Never silent.** A failed write logs a structured WARNING (app, actor,
  record, action) so the event is recoverable from run logs.
- **NFR-3 Feature-gated.** The `CActionLog` write is skipped (the stream note
  still posts) until the CRM entity exists, and activates automatically once it
  does — so the app can ship ahead of the CRM build.
- **NFR-4 Reliable attribution.** Writing under the API key removes per-role grant
  gaps as a failure mode; the API user needs only `CActionLog` create + read.
- **NFR-5 Low overhead.** One extra create per action; the entity-existence probe
  is cached.

## 10. Reporting

- **In the CRM (Phase 1, no app code):** the native `CActionLog` list view — sort
  by Created At to watch live; filter by actor / app / action / category / date /
  record; CSV export; per-record "Action Log" panel for drill-down.
- **In-app (future, optional):** a staff "Activity" view over the same entity, if
  staff shouldn't open the CRM directly.

## 11. Rollout & status

- **App:** `core/action_log.py` + router wiring shipped; deployed to prod and
  crm-test (v0.124.0+).
- **CRM:** `CActionLog` entity built on **both** production and crm-test (fields,
  the `record` link over all 8 record types, and the API user's create+read grant).
- **Verified live:** a real mentor assignment on crm-test produced a complete row
  (actor, action, before→after, re-homing counts, linked engagement with resolved
  name, outcome). Production is configured identically and awaits its first
  live action.
- **Complements Phase 0 (CRM config, Doug-owned):** marking the key change-fields
  Audited so native value-change history covers manual edits too.

## 12. Out of scope / future

- Wiring the remaining action catalog (§8) — incremental, no new CRM work.
- An in-app Activity dashboard (§10).
- Retention / rollup of the log if volume ever warrants.
- A per-user `actor` link (deferred — `actorName` text covers attribution today).

## 13. Appendix — CRM build reference

Entity `CActionLog` (create it by passing name `ActionLog`; EspoCRM prefixes `C`).
Fields per §6. The `record` link is a **Children-to-Parent** link (parent types =
the 8 above; foreign link name `cActionLog`). The intake API user's role(s) need
`CActionLog` **create + read** (read is required — EspoCRM reads the row back
after create). Admin-API endpoints used to build it: fields via
`POST/DELETE /api/v1/Admin/fieldManager/{Entity}[/{field}]`; links via
`POST /api/v1/EntityManager/action/createLink`; role grant via
`PUT /api/v1/Role/{id}` merging `data.CActionLog`; then
`POST /api/v1/Admin/action/rebuild`.
