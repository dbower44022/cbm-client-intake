# CRM handoff — event audience and display time (Track F, F2 + F3)

Last Updated: 10-07-26 21:55 · Revision 1.2 — see change log at the end.

**What this adds:** five fields on `CEvent` and one registration-source option,
so an event can be Internal or Public, reach named chapters, be limited to teams,
take portal registrations, and wait for a display time. Design and rulings:
`prds/events/CBM_Events_Audience_and_Display_Design.md`.

**The application is already safe without it.** Every one of these fields is
feature-detected; a CRM that lacks them behaves exactly as before. So this can
be applied to each system in its own time — nothing breaks in between.

---

## 0. Current state — read this first

| System | State | Evidence |
|---|---|---|
| crm-test | **Done 2026-09-29 05:38 UTC** | Applied from this plan by the configuration admin account, with the CRM-changes skill's applier; the applier read every field back. Then verified as the org-wide API key: all six fields detected by the application, every option list correct, a `where` on `audience` answers 200, the existing events read as Public by the carry-over rule, `registrationSource` offers `Portal`. |
| Production | **Done 2026-10-07** | Doug ran `scripts/migrate_event_audience_schema.py --apply` from inside the production web container (the console step page). Read back from inside that container as the org-wide API key at 21:54 UTC-4: `audience` `[Internal, Public]`, `publicReach` three options, `reachChapters` `[cleveland, boston]`, `internalTeams` multiEnum, `takesRegistrations` bool, `eventReleaseDate` datetime (it already existed, as inferred), `registrationSource` ends in `Portal`. Owed: the before/after conformance exit numbers and the editor check (page §§ 2.10, 3). |
| Boston | **Owed** — with the release that carries the code | Built from crm-test's files, so it is expected to have `eventReleaseDate`. |

crm-test's fields survive the nightly reset: they are Entity Manager work, which
lives in files the reset rebuilds from.

## 1. The naming rules

`CEvent` and `CEventRegistration` are custom entities, so **field names are
stored exactly as typed** — `audience`, not `cAudience`. The plan gives every
name unprefixed and the applier computes the stored name. Nothing in this change
touches a non-custom entity.

## 2. The automated path — use this

The change is defined once, in `scripts/plans/cevent-audience-display.json`.
`scripts/migrate_event_audience_schema.py` applies that file's fields and
options: idempotent (anything present is skipped), additive only, then a
rebuild and a read-back of every change from metadata. Every system it runs on
ends with the same schema.

On **production**, run it from inside the deployed **web** container (the only
place the production administrator credential exists), never from a laptop —
see the `do-app-console-scripting` note in `CLAUDE.md`:

```bash
# Inside the container the administrator is the provisioning service account.
export ESPO_ADMIN_BASE="$ESPO_BASE_URL"
export ESPO_ADMIN_USER="$ESPO_PROVISION_USERNAME"
export ESPO_ADMIN_PASS="$ESPO_PROVISION_PASSWORD"

cd /app
PYTHONPATH=/app .venv/bin/python scripts/migrate_event_audience_schema.py           # dry run
PYTHONPATH=/app .venv/bin/python scripts/migrate_event_audience_schema.py --apply   # apply
```

The interpreter is `.venv/bin/python`: the image does not put the virtual
environment on `PATH`, so a bare `python` there is the system interpreter
without the application's packages. A step-by-step version of this section
for the console, with the exact expected output of the dry run and the
read-back as the org-wide key, was written on 10-01-26:
https://claude.ai/artifact/EoSQ9EuKC4oWPFYWvpxQRe (Doug's private page).

The container must be running a build that includes this change (v0.233.0 or
later), or the script and plan are not there.

The dry run should list five fields to create (six if `eventReleaseDate` is
missing) and one option to add. **If it lists anything else, stop.**

**Trap, found on crm-test:** the field manager's update needs the *complete*
field definition. Sending only the new option list is answered with HTTP 500 and
no detail. The script merges onto the definition it read. (The CRM-changes
skill's own applier, which applied this plan to crm-test, had the same fault and
is fixed.)

## 3. What the plan builds

For a reader checking by eye, or building by hand if the applier cannot run.

| Entity | Field | Type | Options (exact values) | Label |
|---|---|---|---|---|
| CEvent | `audience` | Enum | `Internal`, `Public` — no blank option, no default | Audience |
| CEvent | `publicReach` | Enum | `This chapter`, `All chapters`, `Selected chapters` | Reach |
| CEvent | `reachChapters` | Multi-Enum | `cleveland` shown as "Cleveland Business Mentors"; `boston` shown as "Boston Business Mentors" | Chapters |
| CEvent | `internalTeams` | Multi-Enum | the nine standard team names, exactly as the Teams list spells them | Limit To Teams |
| CEvent | `takesRegistrations` | Boolean | default off | Takes Registrations |
| CEvent | `eventReleaseDate` | Date-Time | — (only if missing) | Display From |
| CEventRegistration | `registrationSource` | *(existing enum)* | add `Portal` — do not remove anything | — |

Three details that matter:

- **`audience` has no default, on purpose.** An empty audience is read by the
  carry-over rule: ticked reads as Public, unticked as Internal. That is what lets
  every existing event carry over without a data change. `Internal` is listed
  first so that an event created by hand in the CRM defaults to the safe value.
- **`reachChapters` values are the chapters' short labels**, identical in every
  chapter's CRM, because a future shared list will match on them. Type the
  lower-case value; the full name is the option's label.
- **Adding a chapter later** means adding an option to `reachChapters` on every
  chapter's CRM. Until the chapter network's Phase 1 applier exists, that is a
  re-run of an updated plan on each system.

## 4. Role grants — none needed

Verified 2026-09-29 against the roles standard
(`prds/chapter-network/roles-standard/prod-capture-2026-08-31.json`):

- The application's API role already reads and writes `CEvent` and reads,
  creates and edits `CEventRegistration` at "all".
- No role has a field-level lock on either entity, so the new fields are not
  stripped on save.

Mentor Role holds no access to `CEventRegistration` at all. That is why the
portal's Register action writes under the organisation-wide key, not as the
member — by design, not an omission to fix here.

## 5. Verification — read the data back

As the **org-wide API key**, on the system just changed:

```
GET /api/v1/Metadata?key=entityDefs.CEvent.fields.audience
    -> {"type":"enum","options":["Internal","Public"], ...}
GET /api/v1/Metadata?key=entityDefs.CEvent.fields.reachChapters.options
    -> ["cleveland","boston"]
GET /api/v1/Metadata?key=entityDefs.CEventRegistration.fields.registrationSource.options
    -> [..., "Portal"]
GET /api/v1/CEvent?maxSize=1&where[0][type]=equals&where[0][attribute]=audience&where[0][value]=Public
    -> 200 (a total of 0 is correct on a system where nobody has set one yet)
```

Then, in Event Administration, open any event and edit it: the **Publishing**
panel now shows *Show this event*, *Audience*, *Reach*, *Display from* — and
*Limit to teams* and *Takes registrations* when the audience is Internal. The
panel only shows fields the CRM has, so a missing control means a missing field.

The live review of the feature itself — a limited Internal event seen and not
seen by two real non-admin mentors, a display time arriving, a public
registration refused for an Internal event — is in the design, § 8 step 3. **An
administrator's test proves nothing there**: administrators pass every team
limit.

## 6. Production

At the Sunday 17:00 UTC slot, by a human, from inside the deployed web
container, after crm-test has been reviewed live. Production's events are all
ticked programme events today, so after the change every one of them still reads
as Public and the public page is unchanged. The first visible difference is an
event someone deliberately sets to Internal.

---

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.2 | 10-07-26 21:55 | Claude (Claude Code) | Production applied by Doug 10-07-26 and read back as the org-wide key from inside the container; state table updated. |
| 1.1 | 10-07-26 04:32 | Claude (Claude Code) | Production commands use `.venv/bin/python` (a bare `python` in the container lacks the packages); link to the 10-01-26 console step page. Production still owed — no run recorded. |
| 1.0 | 09-29-26 01:45 | Claude (Claude Code) | First version. Applied to crm-test and verified; production and Boston owed. Records the applier's enum-option fix. |
