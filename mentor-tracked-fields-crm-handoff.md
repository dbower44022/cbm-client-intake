# CRM handoff — tracked fields on mentor, partner and funder profiles

Last Updated: 11-05-26 11:04 · Revision 1.0 — see change log at the end.

Nine fields become tracked fields (EspoCRM's **Audited** checkbox), so each
change leaves a dated, signed note on the record whoever makes it, in the
application or in the CRM's own screens. From the mentor login integrity
plan (`prds/mentor-login-integrity-plan.md`, § 4.6; Doug's ruling Q5.2,
11-04-26). The History tab (plan step 5) shows these notes.

| Entity | Field (stored name) | Shown as |
|---|---|---|
| `CMentorProfile` | `cbmEmail` | CBM email |
| `CMentorProfile` | `mentorStatus` | Status |
| `CMentorProfile` | `mentorType` | Type |
| `CMentorProfile` | `acceptingNewClients` | Accepting new clients |
| `CMentorProfile` | `maximumClientCapacity` | Maximum client capacity |
| `CMentorProfile` | `mentorStatusNotes` | Status notes (to be renamed Mentor Assignment Preferences, staff notes plan) |
| `CMentorProfile` | `departureDate` | Departure date |
| `CPartnerProfile` | `partnershipStatus` | Partnership status |
| `CSponsorProfile` | `funderStatus` | Funder status |

## 0. Current state — read this first

| CRM | State | Evidence |
|---|---|---|
| crm-test | **Owed.** `CMentorProfile` tracks no fields; `CPartnerProfile` and `CSponsorProfile` track none. | `GET /Metadata` as the configuration administrator, 11-04-26. |
| Production | **Owed; not read.** Plan check C3 reads it first, so only missing fields are added. | — |
| Boston | **Owed.** EspoCRM 10.0.10. | — |

**Verified:** these five entities keep a stream (`scopes.<Entity>.stream`
is true on crm-test), and EspoCRM's audit clean-up skips entities with a
stream, so tracked changes are kept indefinitely (source,
`Classes/Cleanup/Audit.php`, crm-test, 11-04-26). **Not verified:** the
names `partnershipStatus` and `funderStatus` were taken from this
application's code (`sessions/`), not from CRM metadata; confirm both in
`GET /Metadata` before applying.

**A side effect, accepted by ruling:** a mentor can read the notes on their
own mentor profile, so a mentor sees tracked changes to these seven fields
on their profile.

## 1. The naming rules

All three entities are custom (`C…`), so field names are stored exactly as
shown above. Read them from `entityDefs.<Entity>.fields` in `GET /Metadata`,
never from a label.

## 2. Automated path (preferred)

Altering a field is `PUT Admin/fieldManager/{Entity}/{field}` with the
field's full definition plus `"audited": true` (capability map: "answers",
not yet exercised on a real CRM). The build adds an `audited` change type to
`scripts/apply_crm_plan.py`, or a small `scripts/set_audited_fields.py`
that reads each definition, sets `audited`, writes it back, rebuilds, and
reads every field back. Dry run first, crm-test first.

**Trap.** A `PUT` that sends only `{"audited": true}` may replace the field
definition with that one key. Send the whole definition read from
`GET Admin/fieldManager/{Entity}/{field}` with `audited` changed.

## 3. Hand path

In the CRM, as an Administrator-type login: Administration → Entity Manager
→ the entity (Mentor, Partner or Funder profile, by its label) → Fields →
the field → tick **Audited** → Save. Repeat for each field. Then
Administration → Rebuild.

## 4. Check

1. `GET /Metadata` → `entityDefs.<Entity>.fields.<field>.audited` is `true`
   for all nine.
2. In Mentor Administration, as a real non-administrator on the Mentor
   Administration Team, change a test mentor's Accepting new clients. Open
   the mentor profile in the CRM: the record's stream shows the change, with
   the old and new value and that person's name.
3. On crm-test, the nightly reset rebuilds from files, so the tracked
   setting survives it (the setting is metadata, not data). Confirm the
   morning after.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 11-05-26 11:04 | Claude (Claude Code) | First issue, from the mentor login integrity design session. |
