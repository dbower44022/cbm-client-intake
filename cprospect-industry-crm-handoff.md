# CRM handoff — a lead carries an industry (ruling 66)

Last Updated: 10-20-26 18:03 · Revision 1.0 — change log at the end.

**What changes:** one choice field on the lead (`CProspect`). Doug's ruling
66 (10-20-26): a lead carries an industry, so a campaign list can select
"Qualified leads in manufacturing" (build plan § 7c.3). The Ohio state
filing carries no industry, so the field fills from an import whose file
has an industry column, from the reviewer in the Review queue, and from the
lead's own window. It is optional and never a gate on Qualify.

**Applied by the plan file, never by hand:**
`scripts/plans/cprospect-industry.json`, plan fingerprint `82ec87c36dce`.

| Entity | Stored field name | Type | Label | Options |
|---|---|---|---|---|
| `CProspect` | `industry` | enum | *Industry* | The Company's Industry Sector list (`Account.cIndustrySector`), 20 values plus empty, copied from crm-test 10-20-26 |

`CProspect` is a custom entity, so the field is stored exactly as typed.
**The options must stay identical to the Company's list**: a lead's industry
is copied to its Company on conversion (null-fill only), and a value the
Company's list lacks would be dropped there. If production's or Boston's
Company list differs from crm-test's, the dry run there will not show it —
compare `entityDefs.Account.fields.cIndustrySector.options` on that CRM
with the plan's list first, and correct the plan if they differ.

## Roles — nothing to change

A new field carries no field-level rule, so it follows the entity grants
already in place: the **Marketing Admin Role** reads and edits `CProspect`
(the Review queue and the lead's window write as the user), and the
**CustomAppAPIRole** reads it (the list engine runs under the org-wide key).
The field is **not Read-only** (ruling 40: a Read-only field drops every API
write).

## Order

1. **crm-test** — `scripts/prospect_crm_test.sh industry` (dry run first:
   `scripts/apply_plan.sh test scripts/plans/cprospect-industry.json`, one
   change, done 10-20-26). Needed before campaign lists' L1 live pass.
2. **The sandbox baseline** — a new column on an existing table survives the
   nightly reset as empty values; the seeded leads need an industry for a
   demo, so the outreach seeder gains one and the baseline is recaptured
   (`SANDBOX-RESET.md`).
3. **Production** at the Sunday 17:00 UTC slot (deferred with the rest of the
   arc until campaign testing ends), from inside the web container, with the
   three environment lines at the top of `scripts/apply_crm_plan.py`, then
   `scripts/plans/cprospect-industry.json --apply --production --expect 82ec87c36dce`.
4. **Boston** with its release:
   `scripts/apply_plan.sh boston scripts/plans/cprospect-industry.json 82ec87c36dce`.

The application feature-detects the field: until a CRM has it, the Review
queue shows no Industry picker, the import ignores an industry column, and
the list editor does not offer Industry for leads.

## Proof it landed

- The applier reads the field back (it prints `verified`).
- As the org key: `GET CProspect?select=id,industry&maxSize=1` → 200.
- As **Mark Marketing** (a real non-admin): Campaign Management → Review →
  pick an industry on a lead and qualify it; the lead's window shows it.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 10-20-26 18:03 | Claude (Claude Code) | Written for ruling 66; the plan dry-run on crm-test, one change, fingerprint `82ec87c36dce`. |
