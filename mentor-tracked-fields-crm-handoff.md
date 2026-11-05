# CRM handoff — tracked fields on mentor, partner and funder profiles

Last Updated: 11-05-26 13:20 · Revision 1.1 — see change log at the end.

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
| Production | **Owed.** None of the nine tracked; all nine exist under these names. | Plan check C3, `scripts/check_login_integrity_prod.sh`, 11-05-26. |
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
field's full definition plus `"audited": true`. The plan is
`scripts/plans/mentor-tracked-fields.json`, applied by
`scripts/apply_crm_plan.py` (its `fieldParams` change type): it reads each
whole definition, refuses to send anything but `audited` changed, rebuilds,
and fails if any other key moved on read-back. Dry run first, crm-test
first:

```
PYTHONPATH=. uv run python scripts/run_with_admin.py scripts/apply_crm_plan.py scripts/plans/mentor-tracked-fields.json
```

Then the same command with `--apply --expect <fingerprint>` (the dry run
prints it; e85b46a1a6e0 on crm-test, 11-05-26). Boston adds
`--env ~/.config/cbm-boston/boston.env` after `run_with_admin.py` and
`--production`; production runs from inside the web container (the
applier's header). If `mentorStatusNotes` has been renamed by the staff
notes work, the applier refuses that field: update the plan first.

**Check after the crm-test apply:** the option labels of `mentorStatus`
and `mentorType` still read as before (the PUT carries no
`translatedOptions`; whether EspoCRM keeps the translations is not
verified, and the read-back cannot see it).

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
| 1.1 | 11-05-26 13:20 | Claude (Claude Code) | Automated path built (step 0): the plan file and the applier command. Production check C3: none tracked, all nine exist. Label check added. |
| 1.0 | 11-05-26 11:04 | Claude (Claude Code) | First issue, from the mentor login integrity design session. |
