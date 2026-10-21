# CRM handoff — a funder carries a status (ruling 67)

Last Updated: 10-21-26 15:51 · Revision 1.0 — change log at the end.

**What changes:** one choice field on the funder record (`CSponsorProfile`).
Doug's ruling 67 (10-20-26, against the recommendation): a funder carries a
status, set by staff in Funder Management, so a campaign list can select
"every funder except the ones who have ended" (build plan § 7c.3).

**Applied by the plan file, never by hand:**
`scripts/plans/csponsor-funder-status.json`, plan fingerprint `84636d15191f`.

| Entity | Stored field name | Type | Label | Options |
|---|---|---|---|---|
| `CSponsorProfile` | `funderStatus` | enum | *Funder status* | empty · Prospective · Active · Lapsed · Ended |

`CSponsorProfile` is a custom entity, so the field is stored exactly as
typed. **Existing funders start empty** — no status is guessed from dates;
a list reads empty as "not set". Partners need nothing: they already carry
`partnershipStatus`.

## Roles — nothing to change

A new field carries no field-level rule, so it follows the entity grants: the
**Sponsor Manager Role** edits it where it edits the funder (its Details
tab), the **Marketing Admin Role** reads it, and the **CustomAppAPIRole**
reads it (the list engine runs under the org-wide key). Not Read-only
(ruling 40).

## Order

1. **crm-test** — `scripts/prospect_crm_test.sh funderstatus` (dry run
   first: `scripts/apply_plan.sh test scripts/plans/csponsor-funder-status.json`,
   one change, done 10-21-26). Before campaign lists' L2 live pass.
2. **The sandbox baseline** — the column survives the nightly reset as empty
   values; a demo needs the outreach seeder to set a few, then a recapture.
3. **Production** at the arc's Sunday slot, from inside the web container:
   `scripts/plans/csponsor-funder-status.json --apply --production --expect 84636d15191f`.
4. **Boston** with its release:
   `scripts/apply_plan.sh boston scripts/plans/csponsor-funder-status.json 84636d15191f`.

The application feature-detects the field: until a CRM has it, Funder
Management shows no Funder status and the list editor does not offer it.

## Proof it landed

- The applier reads the field back (it prints `verified`).
- As the org key: `GET CSponsorProfile?select=id,funderStatus&maxSize=1` → 200.
- As **Sally Sponsor**: Funder Management → Harrowgate Family Trust → Details →
  the Funding panel shows *Funder status*; set it to Active and save.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 10-21-26 15:51 | Claude (Claude Code) | Written for ruling 67; the plan dry-run on crm-test, one change, fingerprint `84636d15191f`. |
