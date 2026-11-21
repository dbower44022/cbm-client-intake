# Ambassador Activity — CRM handoff

Last Updated: 11-21-26 03:01 · Revision 0.1

What the Ambassador Program needs in each CRM
(`prds/Ambassador Program/ambassador-program-prd.md` § 7). Everything is
applied through the API, from the plan and the roles script; nothing here is
done by hand in Entity Manager. Order: the Business Mentors Association's CRM
first (the test system), then crm-test, then production at the Sunday 17:00
UTC slot from inside the deployed web container, then Boston and Lakeside.
Until a CRM has the record type, the application keeps the program dark there
by itself, even with the switch on.

## Before you start

- The Association's baseline re-capture (`OPEN-ITEMS.md` #87) is done first.
- An Admin-type login for the CRM, in `.env` or the container's
  `ESPO_PROVISION_*` settings.

## 1. The structure — `crm-plans/ambassador.json`

Creates:

1. **Ambassador Activity** (`CAmbassadorActivity`), with Multiple Assigned
   Users and Collaborators on, and the 25 fields the plan lists. No field is
   Read-only: the application writes every one (ruling 40).
2. Its three links: **Ambassador** (to the mentor profile), **Contact** and
   **Company**.
3. **Referred by** on Contact (stored `cReferredBy`), CEngagement,
   CPartnerProfile and CSponsorProfile, each pointing at the mentor profile.
4. Two option values: `CSession.sessionType` **Ambassador Contact** and
   `CProspect.leadSource` **Ambassador referral**.

Dry run, read it, then apply with the fingerprint it prints:

```
PYTHONPATH=. uv run python scripts/apply_crm_plan.py crm-plans/ambassador.json
```

```
PYTHONPATH=. uv run python scripts/apply_crm_plan.py crm-plans/ambassador.json --apply --expect <fingerprint>
```

The script reads every link back and confirms which side it is stored on.

## 2. The roles — `scripts/migrate_ambassador_roles.py`

- **CustomAppAPIRole**: Ambassador Activity create, read all, edit all;
  CSession create, read all, edit all.
- **Mentor Role**: Ambassador Activity read own, edit own. Field rules: the
  mentor edits only the date, the activity and the note, and cannot read
  what the delivery found (`routedTo`, `matchStatus`, `corrections`, the
  review fields).
- **Marketing Admin Role**: Ambassador Activity read all, edit all.

```
PYTHONPATH=. uv run python scripts/run_with_admin.py scripts/migrate_ambassador_roles.py
```

```
PYTHONPATH=. uv run python scripts/run_with_admin.py scripts/migrate_ambassador_roles.py --apply
```

## 3. Check

1. `GET /Metadata`: `entityDefs.CAmbassadorActivity.fields` lists the 25
   fields; `entityDefs.Contact.links.cReferredBy` exists.
2. As a real non-admin mentor, log an activity on `/ambassador/`: it appears
   in My activity, and the CRM shows it to that mentor and to no other.
3. As a Marketing Admin Team member, open `/ambassador/review/`.

## 4. The sandbox

`CAmbassadorActivity` is a new table: crm-test's nightly restore truncates it
until the baseline is re-captured with it present (see `SANDBOX-RESET.md`).
The application's own `ambassador_report` table is reset with the sandbox's
other training data.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-21-26 03:01 | Claude (Claude Code) | Created with the Ambassador Program build (v0.360.0). |
