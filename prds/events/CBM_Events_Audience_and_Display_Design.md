# CBM Events — Audience and Display Time: Design (Track F, F2 + F3)

Last Updated: 09-28-26 00:30 · Revision 0.1 — see change log at the end.

**Status: DRAFT for Doug's review. Nothing here is built, and nothing here is a
ruling unless it cites one.** The requirements are Doug's rulings recorded in
`CBM_Events_Finalization_Plan.md` revision 4.2, sections F2 (requirements 1–5)
and F3 (requirements 1–9); they are cited below as *F2-n* and *F3-n*. Everything
else is Claude's design and is marked where it is a choice. Four decisions in
§ 9 are Doug's to make before the build starts.

---

## 1. What this changes, in one paragraph

Every event gains an **audience** (Internal or Public), a **reach** for Public
events, an optional **team limit** and **Takes registrations** checkbox for
Internal events, and a **display time**. One function — the **visibility
rule** — decides whether a given event may be shown, and every public page, the
public registration form and the portal calendar call it. With the new CRM
fields empty, the visibility rule gives exactly today's answer, so the change
can ship before the CRM fields exist and stays inert until they do.

## 2. Findings that shaped the design

All verified 09-28-26 unless marked.

1. **A display-time field already exists on crm-test and has never been used.**
   `CEvent.eventReleaseDate` is a datetime (30-minute step), empty on every row.
   The 2026-07-25 schema handoff (`cevent-entities-crm-handoff.md` § 2.5) asked
   what it was for — "if it means publish on the website from this date, it may
   replace part of `publishToWebsite`" — and no answer was ever recorded.
   Production is **inferred, not checked**, to have it too: the 09-14-26 schema
   diff reported only two differences, neither of them this field. → Decision
   D1.
2. **`CEvent` has EspoCRM's own `teams` field** (it is an Event-type entity), but
   EspoCRM fills that field automatically with the creating user's default team
   (EspoCRM's documented behaviour — **not tested on these systems**). A team
   limit stored there would silently narrow any event created in the CRM by a
   user who has a default team, and it would start controlling CRM access the
   day any role reads events at "team" level. → The design uses a separate
   field (§ 3).
3. **Every role that reads `CEvent` reads it at "all"** (the roles standard,
   `roles-standard/prod-capture-2026-08-31.json`): Mentor Role, Marketing Admin
   Role, Content and Event Admin, the intake role and the API role. So any
   mentor can already open every event, including one limited to a team, inside
   the CRM itself. **A team limit in this application is therefore a display
   filter, not confidentiality.** → Decision D4.
4. **The public registration form checks only the checkbox**
   (`forms/event_registration/orchestrator.py`, `check_open`, line 96). It does
   not use `_public_where`, so it must be moved onto the visibility rule, or an
   Internal event would take public sign-ups (F3's recorded finding).
5. **crm-test holds five events today, all ticked**, all created by the API
   user. The 94 internal rows the documentation describes are not in the
   current nightly snapshot. The planned check — that meetings synced from
   Google arrive unticked — **cannot be made on crm-test as it stands**. It is
   also moot: the checkbox is a CRM `bool` with `notNull`, whose value is false
   unless something sets it, and under F3-4 an unticked event is shown nowhere.
6. **The editor cannot render a multiple-choice field.** `events/frontend/app.js`
   handles `enum`, `bool`, `wysiwyg`, `text`, `duration`, `datetime`, `int` and
   `url`. The reach's chapter list and the team limit both need a multi-enum
   control. F1 (topic takes several values) needs the same control, so it is
   built once.
7. **The CRM standard is, today, the custom CRM files copied from Cleveland's
   test system** (deployment guide step 9.6). A new chapter gets whatever
   crm-test holds on its build day. There is **no mechanism yet** for pushing a
   changed option list to a chapter that is already built — that is the
   chapter-network Phase 1 applier, not started. → Cost named in § 3.3.

## 3. CRM fields

All on `CEvent`, a custom entity, so the names are stored exactly as typed.
Every field is feature-detected from metadata, per the standing convention: a
field the CRM does not have drops out of the editor and the write whitelist
together, and the visibility rule treats it as empty.

| Field | Type | Meaning | Rule |
|---|---|---|---|
| `publishToWebsite` (exists) | bool | Relabelled **Show this event** (F3-4). The CRM field keeps its name. | Unchanged: nothing is shown unless it is ticked. |
| `audience` | enum: `Internal`, `Public` | Where a shown event appears (F3-1). | Empty is read by the carry-over rule, § 3.1. |
| `publicReach` | enum: `This chapter`, `All chapters`, `Selected chapters` | The reach of a Public event (F3-1). | Ignored unless `audience` is Public. |
| `reachChapters` | multiEnum of chapter keys (§ 3.3) | The named chapters when the reach is Selected chapters. | The creating chapter is always added on save (F3-6). |
| `internalTeams` | multiEnum of the standard team names | Limits an Internal event to members of those teams (F3-5). Empty means every signed-in member. | Ignored unless `audience` is Internal. |
| `takesRegistrations` | bool, default false | Turns on the portal Register button for an Internal event (F3-7). | Public events always take registrations, as today. |
| `eventReleaseDate` (exists on crm-test) **or** a new `displayFrom` | datetime | The display time (F2). Empty means as soon as ticked. | Decision D1. |

`CEventRegistration.registrationSource` gains one option, **`Portal`**, for a
registration a member makes from the portal (F3-7). Inventing a value the CRM
does not hold makes the whole create fail, so the option is a CRM prerequisite
of the portal registration and the application checks for it before offering
the button.

### 3.1 Existing events need no data change — the carry-over rule

F3-4 ruled that ticked events carry over as Public with this chapter's reach,
and unticked events as Internal. The visibility rule reads an **empty**
`audience` exactly that way: empty and ticked means Public, reach this chapter;
empty and unticked means Internal. Adding a field to EspoCRM leaves existing
rows empty, so every event already carries over correctly the moment the field
exists, with no back-fill script and no window during the deployment in which
an event reads wrongly. The editor shows the effective value, so staff never
see a blank. *Claude's choice.* Cost: "empty means something" is a rule a future
reader has to learn; it is stated in the visibility rule's docstring and tested.

### 3.2 The team limit uses team names, not EspoCRM's `teams` field

For the reason in finding 2. The options are the teams of the roles standard
(Analytics Admin, Client Administration, Data Integrity, Marketing Admin,
Mentor Administration, Mentor, Partner Management, Sponsor Management, System
Administration), matched against the signed-in user's team names — which the
portal already holds in the session and uses for every other gate.
*Claude's choice.* Cost: a team a chapter adds for itself cannot be chosen until
it is in the standard, and a renamed team orphans the stored name; the editor
keeps an orphaned value visible rather than dropping it (the stored-value
convention of the other editors).

### 3.3 The chapter list, and this chapter's own key

The stored value is the chapter's **short label** — the lower-case name the
deployment guide already builds into everything for a chapter (`boston`,
`cleveland`) — with the chapter's full name as the option's display label. The
short label is stable when a chapter renames itself, which is what the future
shared list needs to match on (F3-3). Initial options: `cleveland` and
`boston`. Lakeside is a rehearsal instance, not a member chapter, and is not
listed.

The application needs to know which chapter it is, to add itself to the reach
(F3-6). A new setting, **`CHAPTER_KEY`** (default `cleveland`, editable at
`/setup` under Presentation beside the organisation name), holds it. The
feature-readiness panel warns when `CHAPTER_KEY` is not one of the CRM's
`reachChapters` options. *Claude's choice.*

**Cost, stated plainly:** until the Phase 1 applier exists, adding a chapter to
the list reaches chapters already built only by a hand edit in Entity Manager
on each one, or a re-run of a schema script. That is acceptable while the reach
has no visible effect (F3-2), and it must be solved before the sharing is.

## 4. The visibility rule

One module-level function in `events/service.py`, beside `_public_where`, and
two ways of applying it:

- **As a CRM filter**, for list reads: `_public_where` gains `audience` is
  Public (or empty — the carry-over rule), and the display time is empty or
  before now. The reach needs **no** filter on this chapter's own pages: F3-6
  puts the creating chapter in every reach, and every event in this CRM was
  created by this chapter, so the reach cannot exclude anything here yet. The
  function says so in its docstring, so the future sharing work knows where the
  reach check goes.
- **As a pure check on one record**, `is_shown(event, surface, user, now)`, for
  the registration form, the per-event page and the portal. The surface is
  `public` or `portal`.

| Surface | Ticked | Not cancelled | Display time passed | Audience | Team limit |
|---|---|---|---|---|---|
| Public calendar, recorded library, event page, public registration form | required | required | required (F2-1) | Public, or empty and ticked | — |
| Portal calendar | required | required | required (F2-1, F3-9) | Internal **or** Public (F3-8) | Internal only: empty, or the user is in one of the teams, or the user is an administrator |

The display time is compared on the application's clock at the moment of the
read. Cached public reads can therefore show an event up to about two minutes
late (Claude's decision recorded in F2).

**Guard test.** A test fails if any file under `events/`, `portal/` or
`forms/event_registration/` reads `publishToWebsite` for a visibility decision
outside the visibility rule — the same kind of guard as the stylesheet
contract. The Zoom module's own read is the one exception it allows, because
F2-4 deliberately keys Zoom on the checkbox alone.

## 5. The public side

- `list_upcoming`, `published_recordings` and `get_by_slug` change only through
  `_public_where`. An Internal event's page 404s exactly as an unpublished one
  does today, so its existence is not confirmed to anyone guessing the address.
- The registration orchestrator's `check_open` calls `is_shown(..., "public")`
  instead of reading the checkbox, and so refuses an Internal event and an event
  before its display time with the same message as a missing one: "That event
  could not be found." Registration opens at the display time with no separate
  opening time (F2-3).
- `PUBLIC_SELECT` gains the new fields so both checks can see them. The public
  payload does **not** expose them; the reach and team limit are staff data.

## 6. The portal side — what F3 supplies to F5

F3 builds the selection and the actions; **F5 builds the surface** (the list on
the portal's home page, the details view, the filter control). Split this way,
F3 is testable end to end through its interfaces before F5 exists.

- **`portal_calendar(user, now)`** in `events/service.py`: upcoming events
  (starting from two hours ago, the public calendar's slack) that pass
  `is_shown(..., "portal")`, soonest first, each marked Internal or Public.
  It reads **under the organisation-wide API key**, as the directory
  availability and the analytics system metrics do, because a Standard User
  role reads `CEvent` at "own" and would see an empty calendar; the team limit
  is then applied by the application. Served at `GET /api/portal/events`.
- **The member's filter**, saved per user (F3-8). A new application table,
  `user_preference` (CRM user id, preference key, a JSON value, updated at),
  added by Alembic migration 0028, with `GET`/`PUT /api/portal/preferences/{key}`.
  It is general on purpose — the next per-user setting needs no new migration —
  but it holds only the calendar filter until something else asks. The filter's
  choices themselves are F5's to design.
- **Portal registration** (F3-7): `POST /api/portal/events/{id}/register`, as the
  signed-in member, refused unless the event is Internal, shown to this user,
  `takesRegistrations` is ticked, and registration is open. It creates a
  `CEventRegistration` with source `Portal`, subject to the same capacity and
  waitlist rules as the public form and the same one-registration-per-person
  rule. Recorded in the action history.
  - **Which contact the registration belongs to** (*Claude's choice*): the
    member's own Contact, found through their mentor profile's linked Contact
    first and then by their CRM user's email address on a Contact. If neither
    finds one, the registration is recorded with the member's name and email and
    **no** Contact — `CEventRegistration` was designed to hold an attendee with
    no Contact yet — rather than creating a second Contact for a person the CRM
    already knows. Cost: a staff member with no Contact appears in the
    registrant list by email only.
  - A member registering for a **Public** event from the portal goes to that
    event's public page, as assumed during F3; the Register action here is for
    Internal events only.
- **Internal events in the recorded library** are out of scope. An Internal
  event with a recording is not public and does not appear there. Whether the
  portal should offer internal recordings is for F5 or later.

## 7. Event Administration

- **Publishing panel**, in this order: Show this event · Audience · Reach (when
  Public) · Chapters (when the reach is Selected chapters) · Limit to teams
  (when Internal) · Takes registrations (when Internal) · Display from ·
  URL slug · Recording URL. The conditional fields hide and reappear with the
  audience; they are inputs, not action buttons, so the never-hide-a-button
  convention is not engaged.
- **The reach carries a standing note**: "Other chapters do not show this event
  yet. The reach is recorded now so the shared list can use it later." (F3-2).
- **Warnings at save, never blocking** (F2-2, F2-5): a display time on an
  unticked event; a display time after the start of an event that has not
  happened yet. A limited Internal event also carries the note from finding 3,
  if Doug's decision D4 keeps the limit as a display filter.
- **The grid's "Live" column becomes a state**: Hidden · Appears *date* ·
  Public · Internal · Internal, limited. The default "published" filter becomes
  "shown or scheduled". This is the "Appears" state recorded in F2.
- The editor gains the **multi-enum control** (finding 6), built once for F2/F3
  and reused by F1.
- The creating chapter is added to `reachChapters` server-side on every save,
  not only in the browser, so a direct API call cannot leave it out (F3-6).

## 8. Rollout

1. **Code first, dark by construction.** With none of the new CRM fields present,
   the visibility rule returns today's answers, the editor shows today's
   controls (relabelled checkbox aside) and the portal endpoints return nothing.
   No feature flag is added, because the CRM fields are the switch — the
   feature-detect convention. *Cost:* the relabel of the checkbox ships with the
   code, before anything else changes, and the rollback is a revert, not a
   toggle.
2. **CRM change on crm-test**, through a new handoff document and an extension
   of `scripts/migrate_event_schema.py` (idempotent, dry-run by default),
   written under the CRM-changes procedure. Verified as the API key **and** as a
   real non-admin Marketing Admin Team member, since administrators pass every
   gate.
3. **Live review on crm-test**: an Internal event, a limited Internal event seen
   and not seen by two real non-admin mentors, a Public event with a future
   display time appearing on time, and a refused public registration for an
   Internal event. Remember the nightly reset: records made in the day are gone
   by morning.
4. **Production** at a Sunday slot, then Boston when it takes the release.

Tests owed with the code: the carry-over rule for every combination of empty
and set; the display time at, before and after now; the team limit for member,
non-member and administrator; the registration form refusing Internal and
not-yet-shown events; the guard test in § 4; the portal registration's contact
resolution and its refusal paths; a test fake that enforces the 200-row list
limit.

## 9. Decisions for Doug

**D1 — Use the existing `eventReleaseDate` field as the display time, or build
a new one?** Reusing it saves a CRM build on crm-test and, if the inference in
finding 2 holds, on production; the label is changed to "Display from". Its cost
is that nobody recorded what it was made for, and if someone in the CRM team
had a different use in mind, the two meanings collide. A new `displayFrom`
field costs one CRM build per system and leaves the old field unexplained.
**Recommendation: reuse it**, after asking the CRM team the 07-25 question once
more; if nobody claims it, it is the field the handoff already guessed it was.

**D2 — Do Internal events that are online get a Zoom webinar?** Today the Zoom
module creates a webinar for any ticked online event (F2-4), on the chapter's
public webinar account. Under F3 an Internal meeting that is ticked and online
would get one too, and portal registrations are not pushed to Zoom. Option A:
Public events only — the webinar account stays the public programme's, and an
Internal event uses a link staff paste in. Option B: every ticked online event,
as the code does now. **Recommendation: A.** Cost: an internal training that
wants a webinar has to be run from Zoom by hand.

**D3 — Are there chapters other than Cleveland and Boston to list now?** The
list is the CRM standard's (F3-3), and I know of no other member chapter.
Lakeside is a rehearsal and is left out. **Recommendation:** Cleveland and
Boston only.

**D4 — Is a team limit a display filter, or must it keep the event
confidential?** Finding 3: every role that reads events reads all of them, so a
mentor can open a limited event in the CRM itself. Option A: a display filter —
the portal hides it from non-members, and the editor says plainly that it is
not private. Option B: confidential — the limited event is also closed in the
CRM, which means changing Mentor Role's event read from "all" to a narrower
level across the roles standard, on every chapter, and checking every screen
that reads events as a mentor. **Recommendation: A**, because nothing in F3
asked for secrecy and B is a roles-standard change with a reach well beyond
this feature. Cost: a genuinely private meeting should not be put on the
calendar at all.

---

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 09-28-26 00:30 | Claude (Claude Code) | First draft, from the F2 and F3 requirements Doug ruled 09-27-26 and 09-28-26 (Finalization Plan revision 4.2). Findings verified against the code, crm-test's metadata and data, and the roles standard. Four decisions for Doug (D1–D4). |
