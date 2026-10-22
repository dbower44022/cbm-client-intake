# CRM handoff — an engagement's close date becomes writable (ruling 70)

Last Updated: 10-21-26 22:48 · Revision 1.0 — change log at the end.

**What changes:** one field parameter. `CEngagement.closeDate` is
**Read-only** on crm-test and production (read 10-21-26), with no formula
setting it, so EspoCRM silently drops every API write to it (a Read-only field
is a global ACL restriction — ruling 40) and **no engagement on either CRM
holds a close date** (production has 7 Completed). Doug's ruling 70
(10-21-26): clear Read-only; the application stamps today's date when an
engagement moves into Completed, Inactive or Abandoned and the field is empty
(v0.273.0), and staff may correct it on the Details tab.

**Applied by the plan file, never by hand:**
`scripts/plans/cengagement-close-date-writable.json`, plan fingerprint
`c80d9070da1d`. The dry run on crm-test shows one change:
`change field CEngagement.closeDate (readOnly: True -> False)`.

## Roles — nothing to change

No role carries a field rule on `closeDate`, so it follows the
`CEngagement` grants: the Mentor Role edits engagements it is assigned to,
the client administration roles edit all. That is who should be able to
correct a close date.

## Order

1. **crm-test** — `scripts/prospect_crm_test.sh closedate` (dry run done
   10-21-26). The application's stamp is inert until then: it reads the
   field's Read-only flag first and does nothing while it is set.
2. **Production** at the Sunday slot, from inside the web container:
   `scripts/plans/cengagement-close-date-writable.json --apply --production --expect c80d9070da1d`.
3. **Boston** with its release:
   `scripts/apply_plan.sh boston scripts/plans/cengagement-close-date-writable.json c80d9070da1d`
   (read Boston's field first; if it is not Read-only there, the applier
   reports nothing to do).

## Proof it landed

- The applier reads the parameter back (it prints `verified`).
- As a real non-admin in Client Management, set an engagement with no close
  date to **Completed** from the Overview status badge: its Details tab then
  shows **Close date** as today.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 10-21-26 22:48 | Claude (Claude Code) | Written for ruling 70; dry-run on crm-test, one change, fingerprint `c80d9070da1d`. |
