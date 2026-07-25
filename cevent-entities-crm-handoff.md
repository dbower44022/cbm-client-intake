# CEvent + CEventRegistration — schema review and change list

**Both entities already exist on crm-test.** This document is no longer a
from-scratch build spec: it is a **review of the as-built schema against the
Events & Webinars requirements**, plus the precise set of changes needed.

Live schema read from crm-test **2026-07-25** via the metadata API.
PRD: `prds/events/CBM_Events_PRD.md` · Plan:
`prds/events/CBM_Events_Implementation_Plan.md`.

> ## ✅ APPLIED TO CRM-TEST — 2026-07-25
>
> Everything in §2, §3 and §4 below is **done on crm-test**, applied via
> `scripts/migrate_event_schema.py --apply` as `admin@cbmentors.org`:
> 16 new fields · 3 enum-option additions · 1 blank option removed ·
> 4 `readOnly` flags cleared · 1 relabel · the `partnerHost` link · rebuild.
> Re-running the script is a clean no-op (idempotent).
>
> **Verified end-to-end:** a `CEventRegistration` created **as the intake API
> user** stored **all 17 fields** — including the four previously-readOnly ones —
> and the probe record was deleted afterwards as admin (`CEventRegistration`
> is back to 0 records, no residue). `scripts/probe_events_schema.py` reports
> *"No blocking schema problems found."*
>
> **NOT applied:** **production** (untouched; see §7). §5 (the `topic`
> vocabulary) needs no change at all — the existing list is the chosen one.
>
> Two API contract facts learned, now encoded in the migration script:
> `Admin/fieldManager` **PUT requires the complete field definition** (a partial
> body 500s with an empty error), and `EntityManager/action/createLink` wants
> **Create-Relationship-dialog vocabulary** (`manyToOne`), not metadata terms
> (`belongsTo` → HTTP 400).

Written in **Entity Manager vocabulary** — "LEFT" means the entity whose
Relationships tab you are on.

---

## 0. Headline findings

1. **The entities exist and are well designed.** `CEvent` (scope type **Event**,
   so it appears in the EspoCRM calendar) and `CEventRegistration` (BasePlus)
   are already linked to each other and to Contact, with a field set that is
   unmistakably designed for a public workshop programme — `eventSyllabus`,
   `eventFee`, `eventGraphic`, `sponsorGraphic`, `venueCapacity`,
   `registrationUrl`, `recordingUrl`, `topic`, `presenters`, `sponsorProfiles`,
   `resources`. **Most of the PRD's data model is already built.**
2. **`CEventRegistration` has 0 records** — free to reshape without migration.
3. **⚠️ `CEvent` has 92 records, and none of them are workshops.** They are
   internal calendar entries — *"Operations/Team Meeting"*, *"Tech Team
   Recurring Meetings"* — and **mirrors of mentoring sessions** created by a
   CRM-side automation (`createdBy = System`, description *"Scheduled from CBM
   Client Management"*). Our app has never written a `CEvent`. **Decided §1:
   workshops share `CEvent`, gated by `publishToWebsite`.**
4. **⚠️ Several fields are `readOnly` and/or `required` in a combination that
   will break API writes** — including two that are *required AND readOnly*.
   See §4. This would have failed the first live registration.
5. **Topic vocabulary settled with no change needed** — the curated 10-value
   public-facing `topic` list already on `CEvent` is the one being used. §5.
6. **Prod parity is unverified** (no prod credentials locally). See §7.

---

## 1. ✅ DECIDED — `CEvent` is the home for public workshops

**Doug's ruling, 2026-07-25: "use existing event".** Public workshops live in
the existing `CEvent` entity (**Option A** below), gated by the new
`publishToWebsite` flag. No new entity is created.

Consequences to hold onto:
- **`publishToWebsite` is the only thing standing between an internal team
  meeting and the public website.** It defaults to `false`, so the 92 existing
  rows and every future calendar entry are excluded by construction. Any query
  serving the website MUST filter on it — this is a load-bearing rule, not a
  convenience.
- The events grid in `/events` will show internal calendar rows alongside
  workshops, so it needs a default filter (published, or by `eventType`).
- Worth finding out what CRM automation creates the session mirrors: it stamps
  every row with the default `eventType = "Online Webinar"`, which will skew any
  event-type reporting until corrected.

### The options as evaluated

`CEvent` is currently functioning as the **organisation's calendar entity** —
team meetings and session mirrors. Putting the public workshop programme in the
same entity means one grid, one calendar, and one ACL scope covering both.

| Option | What it means | Assessment |
|---|---|---|
| **A. Reuse `CEvent`, gated by a new `publishToWebsite` flag** | Workshops are `CEvent` rows with `publishToWebsite = true`. The 92 internal rows have it `false` (the default) and can never reach the website. | **Recommended.** `CEventRegistration` is already wired to `CEvent`; the field set was clearly built for this; workshops get the CRM calendar for free. Risk is a staffer wrongly ticking the box — contained, and visible. |
| **B. New entity for the public programme** (e.g. `CWorkshop`) | Clean semantic separation; internal calendar untouched. | Costs rebuilding the registration link and abandons a purpose-built field set. Also splits "all events" reporting across two entities — the opposite of the brief. |
| **C. Reuse `CEvent` and stop the session-mirroring automation** | As A, plus retiring whatever writes those 92 rows. | Only if the mirrors have no purpose — worth knowing what created them either way. |


---

## 2. `CEvent` — change list

### 2.1 Add these fields

| Field (api-name) | Type | Why |
|---|---|---|
| `publishToWebsite` | bool, **default false** | **The single most important addition.** Gates everything public: the website shows only `publishToWebsite = true` + future + not cancelled. Keeps the 92 internal rows (and every future team meeting) off `clevelandbusinessmentors.org`. (EV-03) |
| `slug` | varchar (100) | URL segment for the shareable per-event page, e.g. `grant-writing-basics`. App-generated and unique. (EV-06, D-02) |
| `zoomWebinarId` | varchar (50) | The Zoom webinar id (e.g. `89002896927`) — the key the whole Zoom integration turns on: push registrants, pull the attendance report. (EV-21, EV-30) |
| `registrationCloses` | datetime | When registration shuts. Empty ⇒ the app treats it as `dateStart`. (EV-14) |

### 2.2 Change these fields

| Field | Now | Change to | Why |
|---|---|---|---|
| `status` | enum `Planned`, `Held`, `Not Held` | **add `Cancelled`** | A cancelled event must be distinguishable from one that simply didn't happen — it triggers Zoom cancellation and notifies registrants. (EV-22) |
| `registrationUrl` | url, **readOnly** | **clear readOnly** | The app writes the Zoom registration URL here. A readOnly field is stripped on save. (§4) |
| `eventType` | enum with a **blank `""` option** | remove the blank option | Cosmetic but real: blank enum options produce empty values the options-sync tooling has to strip. |
| `venueCapacity` | int, label "Venue Capacity" | **relabel "Capacity"** | It is the seat cap for online events too (EV-15). No type change, no data change. |

### 2.3 Reuse as-is — no change (the PRD's fields already exist under other names)

| PRD concept | Existing field | Note |
|---|---|---|
| Short blurb on the calendar card | `description` (text) | The one-or-two-line summary the website shows under the title. |
| Full description for the event page | `eventOverview` (wysiwyg) | |
| Extra programme detail | `eventSyllabus` (wysiwyg) | Bonus — a natural extra block on the per-event page. |
| Delivery mode (drives Zoom) | `format` (enum `In-Person` / `Virtual` / `Hybrid`, required) | **This is the field the Zoom logic keys on**: Virtual/Hybrid ⇒ provision a webinar; In-Person ⇒ no Zoom, check-in only. |
| Programme kind | `eventType` (`Online Webinar` / `In Person Event` / `Online Course`) | Kept as the editorial category, distinct from `format`. |
| Start / end / length | `dateStart`, `dateEnd`, `duration`, `isAllDay` | Native Event-scope fields; already correct. |
| Location | `location` (text) | Single free-text field — the PRD's separate name/address split is dropped in favour of what exists. |
| Event image | `eventGraphic` (file), `sponsorGraphic` (file) | |
| Recording link | `recordingUrl` (url) | Already exactly right (D-07). |
| Generic join link | `virtualMeetingUrl` (url) | The public join URL (not the per-registrant one). |
| Presenters | `presenters` (many-to-many → Contact, foreign `cPresenterEvents`) | Covers guests, staff, **and mentors** — a mentor's `CMentorProfile` is reached through their Contact, so no extra link is needed. |
| Sponsors | `sponsorProfiles` (many-to-many → CSponsorProfile) | Bonus capability the PRD didn't ask for; keep. |
| Registrations | `registrations` (one-to-many → CEventRegistration) | Already correct. |

**Not needed after all:** `youtubeVideoId` and `thumbnailUrl` — both are derived
from `recordingUrl` at read time. `zoomHostEmail` — there is one host
(`zweb@cbmentors.org`), held in app settings. `mentorPresenters` — resolved
through `presenters` → Contact → mentor profile.

### 2.4 One link to add

| Link name (LEFT = CEvent) | Type | Related | Foreign link (on RIGHT) | Why |
|---|---|---|---|---|
| `partnerHost` | **Many-to-One** (CEvent is the Many) | `CPartnerProfile` | `hostedEvents` | D-10 requires partner organisations as hosts/presenters. Sponsors have a link; partners don't. FK `partnerHostId`. |

### 2.5 Questions on existing fields

- **`eventReleaseDate`** (datetime) — what was this for? If it means "publish
  on the website from this date", it may replace part of `publishToWebsite`.
- **`documents`** (varchar) — a varchar named "documents" looks like a
  leftover; confirm before we build around it.
- **`reminders`** (jsonArray) — EspoCRM's native reminder mechanism. We are
  sending our own branded reminders (D-13), so this should stay **unused** to
  avoid registrants getting two of everything.
- **`parent`** (linkParent) and **`contacts`** (many-to-many → Contact) — not
  needed by this project; harmless. `contacts` could hold invitees, but
  registrations are the record of who's coming.

---

## 3. `CEventRegistration` — change list

Zero records, so all of this is free.

### 3.1 Add these fields

| Field (api-name) | Type | Why |
|---|---|---|
| `email` | varchar | **Required by the integration.** It is the dedupe key (one registration per email per event, EV-13), the match key against the Zoom participant report (EV-30), and the only place to put an address for an attendee with no Contact yet. Must be **plain varchar** — a custom email-type field on a custom entity binds to the primary address and silently stores nothing (the `CIntakeSubmission.submitterEmail` lesson). |
| `firstName` | varchar | Submitted-name snapshot; also the walk-in / unmatched-participant case where no Contact exists yet. |
| `lastName` | varchar | As above. |
| `joinTime` | datetime | First join (Zoom report, or check-in time in person). (D-12) |
| `leaveTime` | datetime | Last leave. (D-12) |
| `minutesAttended` | int | Total minutes in session. (D-12) |
| `attendanceSource` | enum: `Zoom Report`, `Check-in`, `Manual` | Records how attendance was determined, so a **manual correction is never overwritten** by a later automatic pull. (EV-34) |
| `zoomRegistrantId` | varchar (100) | Zoom's id for this registrant — needed to cancel them. |
| `zoomJoinUrl` | url | The **per-registrant** join link Zoom returns. Our reminder emails carry it. (EV-61) |
| `marketingOptIn` | bool | Consent snapshot as given at registration. (D-19) |
| `followUpsSent` | multiEnum: `Recording`, `No Show`, `Mentor CTA`, `Survey` | Send-once ledger for the four follow-ups. (EV-62) Reminders keep using the existing `remindersSent`. |
| `unmatchedParticipant` | bool | Set when a Zoom attendee matched no registration and this row was created for them — flags it for staff review instead of dropping them. (EV-32) |

**Not needed:** `zipCode` and `phone` — zip goes to `Contact.addressPostalCode`
and phone to `Contact.phoneNumber`, where they're actually useful.

### 3.2 Change these fields

| Field | Now | Change to | Why |
|---|---|---|---|
| `attendanceStatus` | enum `Registered`, `Attended`, `No-Show`, `Cancelled` (required, default `Registered`) | **add `Waitlisted`** | Capacity + waitlist is a requirement (EV-15). **Keep it as one field** — this matches the ruling already made for the Submission Admin request status: one field where each state is a value, not parallel status fields. |
| `registrationSource` | enum `Online`, `Walk-In` (required, **readOnly**) | **add `Staff` and `Import`; clear readOnly** | Staff register people by phone (EV-18) and the YouTube/historic import needs a value. readOnly blocks the API from setting it at all. |
| `registrationDate` | datetime, **required AND readOnly** | **clear readOnly** (or give it a "now" default) | ⚠️ Required + readOnly is the dangerous combination — see §4. |
| `cancellationDate` | datetime, **readOnly** | **clear readOnly** | The app sets it when a registrant cancels via their self-service link (EV-16). |

### 3.3 Reuse as-is

`name` · `event` (→ CEvent, foreign `registrations`) · `contact` (→ Contact,
foreign `cEventRegistrations` — **this reverse link is exactly what gives a
person's attendance history**, EV-71) · `remindersSent` (multiEnum `7-day`,
`1-day`, `1-hour` — reuse for reminder scheduling, EV-61) ·
`confirmationSentAt` · `postEventFollowUpSentAt` · `cancellationReason` ·
`specialRequests` (useful for in-person accessibility/dietary needs) ·
`lastCommunicationBouncedAt` (bounce tracking, free) · `description`.

---

## 4. ⚠️ The readOnly / required trap

EspoCRM strips `readOnly` fields on save — **including API saves**. Two fields
are currently **required *and* readOnly**:

- `CEventRegistration.registrationDate`
- `CEventRegistration.registrationSource`

A required field the API is not allowed to set is a field that can make every
create fail validation (or silently store nothing, which is worse — the
`CIntakeSubmission.submitterEmail` failure mode). Also affected:
`CEventRegistration.cancellationDate` and `CEvent.registrationUrl`.

**Resolve before any live write:** clear `readOnly` on all four (a "read-only in
the UI" intent is better expressed with field-level role permissions), or give
`registrationDate` a dynamic default of now. A create probe against crm-test
will confirm.

---

## 5. ✅ DECIDED — keep the existing 10-value `topic` list

**Doug's ruling, 2026-07-25: "use the existing 10-value topic list".** This
**supersedes D-18** (which had chosen the 31-value `CMentorProfile.areaOfExpertise`
skills list — a ruling made before we knew a purpose-built list already existed).

`CEvent.topic` stays exactly as built:

> single enum · *Business Fundamentals · Marketing & Sales · Finance &
> Accounting · Legal & Compliance · Operations · Technology & Digital ·
> Leadership & People · Industry-Specific · Networking · Other*

**No CRM change required** — this was the last open item in the change list, and
it turns out to need nothing. The list is browse-sized, audience-worded, and
designed for this page, which is what a public filter needs; 31 mentor skills
would have made an unusable facet.

Consequences for the build:
- The recorded-library search (EV-04) filters on this 10-value list, and the
  public API returns `topic` as a single value, not an array.
- Event topics and mentor expertise are now **separate vocabularies**. A future
  "mentors who cover what you watched" feature would need a mapping table
  between the two — noted, not built, and not a reason to revisit this.
- If an event ever genuinely needs two topics, widening `topic` to a multiEnum
  is a one-line change to `scripts/migrate_event_schema.py` (the options stay
  the same). Deliberately not done now.

*(All 92 existing records have `topic = null`, so there was no data at stake
either way.)*

---

## 6. Permissions

### 6.1 Intake API user — ✅ ALREADY GRANTED, no action needed

Verified live 2026-07-25 by reading the API user's own ACL table. The
`customapps` user (type `api`) already has, on **both** entities:

| Entity | create | read | edit | delete | stream |
|---|---|---|---|---|---|
| `CEvent` | yes | **all** | all | **no** | all |
| `CEventRegistration` | yes | **all** | all | **no** | all |

This is exactly what the integration needs — including `edit` on
`CEventRegistration`, which is genuinely required (unlike the other intake
entities): a repeat registration updates the existing row rather than
duplicating it, and attendance is written back onto it. `delete: no` matches the
house convention. **Nothing to do here.**

> **The API user cannot change the schema.** Also verified 2026-07-25:
> `Admin/fieldManager/…` and `EntityManager/…` both return **403** for this key.
> Schema changes in EspoCRM are **admin-only** — no role grants them (the same
> constraint as User creation, recorded in CLAUDE.md). Every change in §2–§5 must
> be applied either in the Entity Manager UI or through the API **as an
> Admin-type user** (the `ESPO_PROVISION_*` service account pattern).

### 6.2 Marketing Admin Team role (the event administrators, D-15)

| Entity | create | read | edit | delete |
|---|---|---|---|---|
| `CEvent` | yes | all | yes | **no** |
| `CEventRegistration` | yes | all | yes | **no** |

No delete: events are cancelled, registrations are cancelled — nothing is
destroyed (the `CContribution` convention). Also confirm this role reads
`Contact`, `CMentorProfile`, `CPartnerProfile`, and `CSponsorProfile` so
presenter/sponsor pickers and registrant links resolve.

### 6.3 Mentor Team role (read-only rollup, EV-72)

**read** on `CEvent` and `CEventRegistration` (scope `all` is simplest — the app
only ever shows a mentor the registrations belonging to their own engagement's
contacts).

---

## 7. Prod parity — NOT DONE, and now the main drift risk

Production was deliberately **left untouched** — crm-test only, this session.
crm-test and prod now **differ by exactly this change list**, so prod must
receive the identical migration before any prod deployment:

```bash
PYTHONPATH=. \
ADMIN_BASE=https://crm.clevelandbusinessmentors.org \
ADMIN_USER=admin@cbmentors.org ADMIN_PASS=... \
uv run python scripts/migrate_event_schema.py            # dry run first
uv run python scripts/migrate_event_schema.py --apply
PYTHONPATH=. ESPO_BASE_URL=https://crm.clevelandbusinessmentors.org ESPO_API_KEY=... \
uv run python scripts/probe_events_schema.py             # then diff vs crm-test
```

Because the script is idempotent and declarative, this reproduces crm-test
exactly rather than repeating it by hand — which is how the last two drifts
(`CCommunication` field lengths, `Account.cAccountType`) happened.

Before running it, confirm on production:

1. Do `CEvent` and `CEventRegistration` exist at all?
2. Do their fields, enum options, and links match crm-test **exactly** —
   especially `format`, `status`, `eventType`, `topic`, `attendanceStatus`,
   `registrationSource`, and the `registrations` / `contact` links?
3. Same `readOnly` flags (§4)?
4. How many `CEvent` records, and of what kind?

Prod schema drift from crm-test has bitten this project before (the
`CCommunication` field-length drift; the `Account.cAccountType` divergence), so
this is a real check, not a formality. Run it with the same probe used here,
pointed at prod.

---

## 8. Verification (after the changes)

1. Create a `CEvent` in the EspoCRM UI: future `dateStart`, `format = Virtual`,
   `publishToWebsite = true`.
2. As the **intake API user**, create a `CEventRegistration` against it with
   `email`, `firstName`, `lastName`, `registrationSource = Online` — confirm it
   saves and that **every field actually stored** (re-read it; a 200 with a
   missing value is the readOnly failure mode).
3. Update that registration's `attendanceStatus` to `Attended` with
   `joinTime`/`leaveTime`/`minutesAttended` — confirm the API can write them.
4. Confirm the reverse links resolve: the event lists its registrations, and the
   Contact lists `cEventRegistrations`.
5. Confirm a Marketing Admin Team user can create/edit both and **cannot**
   delete either; confirm a Mentor Team user can read but not edit.
6. Confirm the 92 existing internal `CEvent` rows all have
   `publishToWebsite = false`.

---

## 9. Standing gotchas that apply here

- **No before-save name formulas** on either entity — the app sets `name`
  explicitly, and an unconditional formula would overwrite it (the `CSession`
  lesson).
- **Datetimes are UTC over the API.** The app converts to/from
  America/New_York; the CRM UI's default timezone should agree.
- **Custom email-type fields don't store** on custom entities — hence plain
  varchar for `email`.
- **Enum drift is tolerated by the app**: a value that falls out of an enum's
  options is dropped rather than failing the whole save. That means a renamed
  option won't break registrations, but it will silently stop storing that
  value — tell us when options change.
- Build order: fields → relationships → permissions → **then** verify with §8.
