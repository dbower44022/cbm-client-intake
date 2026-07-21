# Reliable Action History Across the CBM Apps — Plan

**Status:** Draft for Doug's review · 2026-07-20 · rev 2 (reporting entity moved
into Phase 1 per Doug; audited-field config owned by Doug)
**Author:** Claude (grounded in a live read of the production CRM's stream/audit config)

---

## 1. The problem in one sentence

Staff make consequential changes through the apps — assigning a mentor, approving
a mentor, editing a company, sending an email, uploading a document — and when we
later ask *"who changed this, when, and how?"*, the record's history often can't
answer, so we can't reconstruct what happened (the duplicate-session and
mentor-swap investigations both dead-ended here).

This plan fixes that on two levels: **every meaningful action leaves one clear,
attributable line on the record** (so the history reads right in context), **and
every action is also written to a queryable reporting log** (so "who did what,
when, across which records" is a filter-and-read, not an investigation). The
second half is the priority — the recent problems need to be diagnosed faster,
and cross-record reporting is what does that.

---

## 2. "Stream" vs "History" — what they actually are (and which to use)

You asked which is which and which is best. Short answer: **in EspoCRM they are
the same underlying thing, and we should use it deliberately in two modes.**

EspoCRM has **one** record-history mechanism: the **Stream**. It is a feed of
small "Note" records attached to each record (the panel you see on an
engagement, a mentor, a company). "History" is not a separate audit database —
the word gets used loosely for two things:

- the **Stream** feed itself (the change/activity history of a record), and
- an **Activities → History** panel that lists related *meetings, calls, and
  emails* — that's a different feature and not what we mean here.

So when we say "log it in history," we mean **write the right entries into the
Stream.** There are two kinds of Stream entry, and each is right for a different
job:

| Kind | How it's created | What it captures | Good for |
|------|------------------|------------------|----------|
| **Automatic field-change note** (type `Update`) | EspoCRM writes it by itself **only when a field flagged "Audited" changes** | "engagementStatus: *was* Pending Acceptance → *became* Assigned", attributed to the user | Simple, single-field value changes (status, key links) |
| **Posted note** (type `Post`) | The app (or a person) writes free text to the record's stream | Whatever we say — including the **action**, the **app** it came through, the **actor**, and **all the downstream records touched** | Multi-step actions no single field captures; naming who/what did it |

**Recommendation: use both, on purpose.**

- **Audited fields** give us native, zero-code, queryable value-change history —
  and, importantly, they also cover edits made **directly in the EspoCRM UI**, not
  just through our apps. We should turn this on for the fields that matter.
- **Posted notes** are the app's job. They are the only way to record an
  *action* (an assignment touches ~6 records; a field note on one of them doesn't
  tell the story) and the only way to stamp **"the app did this, on behalf of
  Jane, via Client Administration"** — which a bare field-change note never says.

Neither alone is enough. Audited fields miss actions and miss the app/actor
context; posted notes miss the convenience of native field diffs and don't cover
manual CRM edits. Together they give a complete, readable **on-record** trail.

**But the stream answers only "what happened *to this record*."** It can't answer
"what did Jane do last week?" or "every mentor assignment in July, across all
engagements" — the *cross-record* questions our recent investigations actually
needed. For those we add a third leg: a **custom reporting entity** the app
writes one row to per action (§4.2). That's the change from the first draft — it
is now part of Phase 1, not a later option — because faster investigations are
the point.

---

## 3. Why today's history doesn't help — the diagnosis (with live evidence)

I read the production CRM's configuration directly. Four concrete gaps:

### Gap A — the fields that change most are **not audited**, so they change silently

Live audit-flag check on production (✓ = EspoCRM auto-logs a change, ✗ = silent):

| Entity | Field | Audited? |
|--------|-------|----------|
| CEngagement | engagementStatus | ✓ |
| CEngagement | **mentorProfile** (the assigned mentor) | ✗ |
| CEngagement | assignedUser / assignedUsers | ✗ |
| CEngagement | engagementAssignedDate, closeReason | ✗ |
| CMentorProfile | **mentorStatus** | ✗ |
| CMentorProfile | acceptingNewClients, cbmEmail, recordStatus, assignedUser | ✗ |
| CPartnerProfile | **partnershipStatus**, partnerManager, partnershipType | ✗ |
| CSponsorProfile | cBMSponsorManager, description (sponsor notes) | ✗ |
| CSession | status, dateStart | ✓ |
| CSession | sessionType, assignedUsers | ✗ |
| Contact | cContactType | ✓ |
| Contact / Account | assignedUser / assignedUsers | ✗ |

This is the root of *"the mentor changed but the history doesn't show it"*: a
mentor swap changes `mentorProfile`, which is **not audited** — so it leaves no
trace at all. Same for approving/suspending a mentor (`mentorStatus`), moving a
partnership stage (`partnershipStatus`), and every re-homing of assigned users.

### Gap B — app writes look identical to hand edits

The apps act **as the signed-in user**, so even an audited change says only
"Jane changed the status" — never whether Jane did it in the CRM UI or the app
did it on Jane's behalf. This already cost us a real forensic investigation
(a mentor swap that looked like, but wasn't, an app assignment).

### Gap C — the meaningful actions are multi-record, and mostly unlogged

The high-value actions each touch **several** records at once, and only two
surfaces record anything today:

- **Logged today (posted notes):** Client Administration's *assign*, *reassign*,
  *repair*, and the session tools' *accept engagement* and *add/remove co-mentor*.
  Public intake forms also log every submission to a `CIntakeSubmission` record.
- **NOT logged today (write CRM data, leave no note):** Mentor Administration
  edits **and mentor approval / login provisioning** (creating a user account
  leaves no trace on the profile); My Mentor Profile self-edits; the session
  tools' **Details-tab edits**, contact add/remove, notes edits, and **Funder
  contributions**; **document** uploads / archives / Drive access grants;
  **email** sends and conversation curation; Workspace **Directory** inline edits.

### Gap D — coverage is silent when it fails, and one entity has stream off

Posted notes today are "best-effort": if the write fails they log a warning and
move on — good (they must never break the operation) but it means a gap can pass
unnoticed. And **CContribution has Stream disabled entirely**, so the funder
ledger has no history at all.

---

## 4. The target model — one convention, everywhere

**Rule:** every mutating action a user takes through an app performs **two
writes** — a structured **Stream note** on the primary record (on-record history)
**and** a **`CActionLog` row** (cross-record reporting, §4.2) — and the CRM has
the key **value-change fields marked Audited**. One shared helper does both from
one call, so a write path can't do one and forget the other.

### The standard note format

```
[<App>] <action> — <what changed, before → after> · <downstream touched> · by <Actor>
```

Examples (readable by any staffer, and greppable by us):

- `[Client Administration] Mentor assigned: Jane Smith (was: unassigned). Status Submitted → Pending Acceptance. Re-homed: 3 contacts, client profile, company. · by Bob Staff`
- `[Mentor Administration] Mentor approved: status Candidate → Active. Login created (jane.smith@cbmentors.org), added to Mentor Team. · by Bob Staff`
- `[My Mentor Profile] Profile updated: headline, areas of expertise, photo. · by Jane Smith`
- `[Client Management] Session recorded (Completed, 2026-07-17). Engagement activated: Assigned → Active. · by Jane Smith`
- `[Funder Management] Contribution added: $5,000 received 2026-07-01. · by Bob Staff`
- `[Communications] Email sent to james@acme.com — "Re: next steps". · by Jane Smith`

Every note names **the app**, **the action**, **the before→after where it
applies**, **the other records touched**, and **the actor** — the five things
missing today.

### Where the note lands

On the **primary record** of the action (the engagement, the mentor profile, the
partner/sponsor, the company/contact). For actions that fan out across many
records, one note on the primary record that *names* the others is enough — we
don't need a copy on each (it would clutter every record's stream). For
document/email actions we also keep the native artifacts (the Email record in the
contact's history, the document metadata row).

### How it's built

- A single shared helper — `record_action(...)` (extends the existing
  `core/stream.post_stream_note`) — takes the app, actor, action type, primary
  record, before→after, and downstream list **once**, then does both writes: the
  formatted Stream note **and** the `CActionLog` row. Every write path calls this
  one function, so the wording, the `[App]`/actor stamping, and the reporting row
  are all guaranteed together.
- The routers already know the app and the signed-in user, so the actor and
  channel are free.
- Keep it **best-effort but never silent** (see §6).

### 4.2 The reporting entity — `CActionLog` (now a Phase-1 deliverable)

A custom EspoCRM entity, **one row per action** (the proven `CIntakeSubmission`
pattern). This is what makes investigations fast: because it's a native entity,
**EspoCRM's own list view gives filterable, sortable, exportable reporting for
free** — filter by *who*, *which app*, *which action*, *date range*, or *which
record* and read the answer, with **no app UI to build**. It turns
"reconstruct what happened" from a code-forensics exercise (which is where the
duplicate-session and mentor-swap questions ended up) into a saved search.

Proposed fields:

| Field | Type | Purpose |
|-------|------|---------|
| `name` | varchar (auto) | the one-line summary — same text as the stream note |
| `actionType` | enum | Mentor Assigned / Reassigned / Approved, Login Provisioned, Session Recorded, Engagement Activated, Profile Edited, Contact Linked/Unlinked, Email Sent, Document Uploaded, Access Granted, Contribution Recorded, Field Edited, … |
| `app` | enum | Client Administration / Mentor Administration / Client-Partner-Funder Management / My Mentor Profile / Directories / Submission Admin / Communications / Intake |
| `actor` | link → User | who did it (click-through, filter "everything Jane did") |
| `actorName` | varchar | stored explicitly so attribution survives even when the row is written under the API key (see below) |
| `parent` | belongs-to-parent | the primary record acted on (Account / Contact / CEngagement / CMentorProfile / CPartnerProfile / CSponsorProfile / CSession) — click-through + "all actions on this engagement" |
| `summary` | text | the full human-readable line |
| `details` | text (JSON) | before→after field diffs + the downstream records touched |
| `outcome` | enum | Success / Partial / Failed |
| *(native)* `createdAt` | datetime | when |

**Who writes it, and why that matters for reliability.** The `CActionLog` row is
written via the **shared create-only API key** (the same one the intake forms
use), **not** the per-user token — so the reporting log never depends on each
staff role having a grant, and can't be silently dropped by a role gap. Because
`actor`/`actorName` are stored explicitly, attribution stays exact regardless.
(The *Stream note* still posts as the signed-in user, so on-record history reads
naturally as authored by them.) Best-effort but logged: a failed `CActionLog`
create still emits the structured app-log line (§6).

**Reporting, two ways:**
- **Immediately, in the CRM (zero app code):** a saved-search list view by actor
  / app / action / date, plus CSV export — available the moment rows start
  flowing.
- **Optionally later:** a small in-app "Activity" view (in Submission Admin, or a
  new page) over the same entity, if staff shouldn't go into the CRM directly.

**CRM prerequisite (Doug / CRM side):** create the `CActionLog` entity + the
fields above + the `parent` link's target list + the intake API user's **create**
grant + a **read** grant for whoever should browse the reports.

---

## 5. Scope — the action catalog (what each app must start logging)

Priority is by how often the action matters in a "what happened?" question.

**Tier 1 — highest value (assignment, status, and identity changes):**

- **Mentor Administration:** mentor field edits (esp. `mentorStatus`, capacity,
  compliance); **approval → login/mailbox provisioning** (currently invisible);
  the "Update Mentor Status" sweep.
- **Client Administration:** already logs assign/reassign/repair — bring the
  **engagement-notes** edit and any status change under the same helper.
- **Session tools:** session create/edit already changes audited fields; add an
  explicit note for **engagement activation** and for **Details-tab edits** to the
  company / client profile / engagement / contacts; contact **add/remove**.
- **Partner/Funder management:** **partnershipStatus** and sponsor-manager
  changes; contributions (needs stream enabled first — §7).

**Tier 2 — important, lower frequency:**

- **My Mentor Profile:** self-edits, photo, signature (a mentor changing their own
  public data).
- **Workspace Directories:** inline Contact/Company/Partner edits.
- **Documents:** upload, archive/restore, and **Drive access grants** (who was
  given access to what).
- **Communications / email:** a note on the record when an email is **sent** from
  the app (the native Email write-back already lands in the contact's history; a
  short stream line makes it visible on the engagement too).

**Already covered (the models to copy):** intake forms → `CIntakeSubmission`;
Client Administration assign/reassign; session accept + co-mentor.

### 5.1 Endpoint checklist (every staff-initiated write, from a full code inventory)

✅ = already posts a note · ➕ = add a note · 🔹 = value covered once fields are
Audited (§7), a note optional.

**assignments/** — ✅ assign, ✅ reassign (both post notes today) · ➕ `PUT
/engagements/{id}/notes` (description edit).

**sessions/** (largest gap) — ✅ accept, ✅ add/remove co-mentor · ➕ `PUT
/details/{entity}/{id}` (arbitrary field edits, incl. status, on engagement /
client profile / partner / sponsor / company / contact) · ➕ contact
link / unlink / create-and-link (`POST`/`DELETE …/contacts`, may create an
Account) · ➕ `POST …/sessions` + `PUT /sessions/{id}` (**session create/edit,
which also creates/updates a live Google Calendar event** — the note should say
so) · ➕ engagement **activation** (Assigned → Active on first completed
session) · ➕ `POST`/`PUT …/contributions` (funder ledger, incl. soft-delete →
Cancelled) · ➕ `POST …/messages` (email send) · ➕ include/exclude conversation.

**mentoradmin/** (no notes today) — ➕ `PUT /mentors/{id}` (profile edits incl.
`mentorStatus`, + linked-Contact mirror) · ➕ **`POST /mentors/{id}/provision`**
and the inline-provision path (**creates a Google mailbox + an EspoCRM login
User + team + `cbmEmail`** — the single most consequential unlogged action) · ➕
`POST /mentors/status-check` (recordStatus + user-link reconciliation).

**mentorprofile/** (no notes today) — ➕ `PUT /profile`, `PUT /signature`,
`POST`/`DELETE /photo` (mentor self-edits of their own public record).

**directory/** — ➕ `PUT /records/{id}` (inline Contact / Company / Partner edit).

**documents (sessions + mentoradmin)** — ➕ upload, archive/restore, and Drive
**access grants** (records both the `documentsFolderUrl` CRM write and who was
granted/revoked access — today all silent).

**comms/email (all `POST /sendmail` across apps)** — ➕ a stream line on the
record when mail is **sent** (the native `Email` write-back already lands in the
contact's history; the note makes it visible on the engagement/partner/sponsor).

**Already audited elsewhere (leave as-is):** public intake + ops redrive →
`CIntakeSubmission`. **No CRM write (out of scope):** myemail, portal
login/logout, ops resolve/notes/discard (app-DB with `acted_by`), Google setup.

---

## 6. Reliability — best-effort, but never silent

History that silently fails to record is worse than none (it looks complete).
So:

1. **Never break the operation.** A note failure must never roll back the save
   (unchanged from today).
2. **But never lose it either.** If *either* write fails, emit a **structured
   application-log line** (`action`, `actor`, `record`, `summary`) at WARNING so
   the event is recoverable from run logs. Writing the `CActionLog` row under the
   API key (not the per-user role) already removes the most likely failure — a
   role missing a grant. For the highest-value actions (approval/provisioning,
   assignment) we can additionally mirror to the durable Postgres store we already
   run, so even a full CRM outage can't erase the reporting trail.
3. **Prove both writes land.** Confirm the gate roles can create Notes on the
   entities they touch (default ACL allows it; verify the provisioning-admin path
   once), and confirm the API user has `CActionLog` **create**.

---

## 7. CRM-side prerequisites (Phase 0 — CRM config, owned by Doug)

Configuration changes in EspoCRM, no app code, that pay off the moment they're
made — including for **manual** UI edits, not just app actions:

1. **Mark the key fields "Audited"** across all entities (Entity Manager → field →
   Audited). *Doug is handling this.* The concrete gap list from the live audit is
   a good starting checklist: CEngagement `mentorProfile`, `assignedUsers`,
   `engagementAssignedDate`, `closeReason`; CMentorProfile `mentorStatus`,
   `acceptingNewClients`, `cbmEmail`, `recordStatus`; CPartnerProfile
   `partnershipStatus`, `partnerManager`, `partnershipType`; CSponsorProfile
   `cBMSponsorManager`; CSession `sessionType`; Contact/Account `assignedUsers`
   (status/date fields already audited stay).
2. **Enable Stream on `CContribution`** so the funder ledger has any history.
3. **Create the `CActionLog` entity** (fields + `parent` target list per §4.2) and
   grant the intake API user **create** + the reporting audience **read**.
4. **Confirm Note-create** for the staff gate roles and the provisioning admin
   account on the entities they act on (default allows it; verify once live).

Items 1–2 alone already close Gap A — the "mentor changed, no trace" class — for
both app and hand edits; item 3 unlocks the Phase-1 reporting.

---

## 8. Phased rollout

- **Phase 0 — CRM config (owned by Doug; no deploy):** mark the key fields Audited
  across all entities, enable Stream on `CContribution`, **create the `CActionLog`
  entity + grants** (§4.2/§7), verify Note-create. *Immediate partial win on its
  own; low risk; reversible.*
- **Phase 1 — the shared helper + wiring + reporting (the app work):**
  1. Build `record_action(...)` — the one shared helper that does **both** writes
     (formatted Stream note **and** the `CActionLog` row), with app tag, actor
     stamp, and fail-loud logging (§4.1/§4.2/§6).
  2. Wire it into every mutating endpoint on the §5.1 checklist — Tier 1
     (assignment, status, identity, provisioning, activation) first, Tier 2 next.
  3. **Reporting comes free** the moment rows flow: the CRM's native `CActionLog`
     list view (filter by actor / app / action / date / record, + CSV export).
  Ship per app, verified against crm-test as we go.
- **Phase 2 — optional polish:** a small in-app "Activity" view over `CActionLog`
  (so staff needn't open the CRM), and retention/rollup if volume ever warrants.
  Not required for the reporting goal — the CRM list view already delivers it.

---

## 9. Decisions & division of labor

**Settled (your direction, 2026-07-20):**
- **Full reporting via the `CActionLog` custom entity is in Phase 1**, not a later
  option — the app dual-writes a stream note *and* a log row per action, and the
  CRM's native list view gives filterable/exportable reporting immediately.
- **You are updating the Audited-field settings** for the key fields across all
  entities (Phase 0, item 1).

**Still worth your call:**
1. **`CActionLog` fields — confirm the shape in §4.2** before I wire to it (the
   `actionType`/`app` enum value lists especially, since they drive the report
   filters). I can propose the final enum lists with the code.
2. **How much to log?** Recommendation: **key actions + audited value fields**, not
   every keystroke — log an *action* (with before→after), let audited fields carry
   incidental edits. Say the word if you want every Details-tab field edit as its
   own row (more complete, noisier).
3. **Who reads the reports?** If only admins go into the CRM list view, Phase 1 is
   done at that; if front-line staff need it, we add the small in-app Activity view
   (Phase 2).

**Next step:** once you've set the Audited fields and created the `CActionLog`
entity (I can hand you an exact field/grant spec to build from), I start Phase 1
with the shared helper and the Tier-1 endpoints.

---

*Appendix data (live from production, 2026-07-20): all core entities have Stream
enabled except CContribution; audited-field flags as tabled in §3; gate roles
carry the default (permissive) Note ACL.*
