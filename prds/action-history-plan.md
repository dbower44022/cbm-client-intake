# Reliable Action History Across the CBM Apps — Plan

**Status:** Draft for Doug's review · 2026-07-20
**Author:** Claude (grounded in a live read of the production CRM's stream/audit config)

---

## 1. The problem in one sentence

Staff make consequential changes through the apps — assigning a mentor, approving
a mentor, editing a company, sending an email, uploading a document — and when we
later ask *"who changed this, when, and how?"*, the record's history often can't
answer, so we can't reconstruct what happened (the duplicate-session and
mentor-swap investigations both dead-ended here).

This plan fixes that: **every meaningful action taken through an app leaves one
clear, attributable line in the CRM that a non-technical staffer can read.**

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
manual CRM edits. Together they give a complete, readable trail.

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

**Rule:** every mutating action a user takes through an app posts **one
structured Stream note** to the primary record, and the CRM has the key
**value-change fields marked Audited**.

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

- A single shared helper (extend the existing `core/stream.post_stream_note`)
  that enforces the format and **always** prepends `[App]` and appends `by
  <Actor>`. Every write path calls it. One place to get the wording and the
  actor-stamping right.
- The routers already know the app and the signed-in user, so the actor and
  channel are free.
- Keep it **best-effort but never silent** (see §6).

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
2. **But never lose it either.** On a failed note, write a **structured
   application-log line** (`action`, `actor`, `record`, `summary`) at WARNING so
   the event is still recoverable from run logs. For the highest-value actions
   (approval/provisioning, assignment) consider also recording to the durable
   Postgres store we already run, so a CRM outage can't erase the trail.
3. **Prove the note posts.** Confirm each gate role can create Notes on the
   entities it touches (spot-check: default ACL currently allows it, but the
   provisioning admin path and any team-scoped role should be verified live once).

---

## 7. CRM-side prerequisites (Phase 0 — cheap, and it helps immediately)

These are configuration changes in EspoCRM, no app code, and they pay off the
moment they're made — including for **manual** UI edits, not just app actions:

1. **Mark these fields "Audited"** (Entity Manager → field → Audited): CEngagement
   `mentorProfile`, `assignedUsers`, `engagementAssignedDate`, `closeReason`;
   CMentorProfile `mentorStatus`, `acceptingNewClients`, `cbmEmail`,
   `recordStatus`; CPartnerProfile `partnershipStatus`, `partnerManager`,
   `partnershipType`; CSponsorProfile `cBMSponsorManager`; CSession `sessionType`;
   Contact/Account `assignedUsers`. (Status/date fields already audited stay.)
2. **Enable Stream on `CContribution`** so the funder ledger has any history.
3. **Confirm Note-create** for the staff gate roles and the provisioning admin
   account on the entities they act on (default allows it; verify once live).

Doing only Phase 0 already closes Gap A — the "mentor changed, no trace" class —
for both app and hand edits.

---

## 8. Phased rollout

- **Phase 0 — CRM config (days, no deploy):** mark fields Audited, enable stream on
  CContribution, verify Note grants. *Immediate partial win; low risk; reversible.*
- **Phase 1 — the shared helper + wiring (the bulk of the app work):** extend
  `core/stream` into a standard action-note helper (format + app tag + actor +
  fail-loud logging); wire it into every Tier-1 then Tier-2 write path; add the
  activation/provisioning/details/contact/contribution/document/email notes. Ship
  per app, verified against crm-test as we go.
- **Phase 2 — optional, only if reporting needs it:** a dedicated **`CActionLog`**
  entity (the `CIntakeSubmission` pattern) so we can answer cross-record questions
  the per-record stream can't — *"everything Jane did last week"*, *"every
  assignment in July"* — with a small admin view. Recommended **only if** the
  stream notes prove insufficient for reporting; the stream covers "what happened
  to this record," a log entity covers "what did this person/app do across
  records."

---

## 9. Decisions I need from you

1. **Stream notes now, log-entity later?** My recommendation: yes — Phase 0 + 1
   (audited fields + posted action-notes) solves the stated problem; treat the
   `CActionLog` reporting entity (Phase 2) as a fast-follow only if you want
   cross-record reporting. Or we build the log entity up front if reporting is a
   primary goal.
2. **How much to log?** My recommendation: **key actions + audited value fields**,
   not every keystroke. We log an *action* (and its before→after), and let audited
   fields carry incidental field edits. If you'd rather every Details-tab field
   edit produce its own note, we can — it's just noisier.
3. **Green-light Phase 0 now?** It's cheap CRM config, reversible, and helps
   immediately even before any app work — I'd suggest doing it regardless.

---

*Appendix data (live from production, 2026-07-20): all core entities have Stream
enabled except CContribution; audited-field flags as tabled in §3; gate roles
carry the default (permissive) Note ACL.*
