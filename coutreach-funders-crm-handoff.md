# CRM handoff — a campaign names its funders (ruling 57)

Last Updated: 10-20-26 14:43 · Revision 1.0 — change log at the end.

**What changes:** one many-to-many relationship between an outreach campaign
and a funder profile. Doug's ruling 57 (10-20-26): a campaign names its funders
the way it names its partners (CM-2), and every funder record gets a Campaigns
tab (CM-5's twin). Funders get no credit on the records a campaign brings in.

**Applied by the plan file, never by hand:**
`scripts/plans/coutreach-funders.json`, plan fingerprint `4658d1450804`.

| Side | Entity | Stored link name | Points at |
|---|---|---|---|
| Campaign | `COutreachCampaign` | `funderProfiles` (label *Funders*) | `CSponsorProfile` |
| Funder | `CSponsorProfile` | `sponsoredCampaigns` (label *Sponsored Campaigns*) | `COutreachCampaign` |

Relation (middle table) `cOutreachCampaignSponsorProfile`. Both entities are
custom, so neither name gains a prefix. `COutreachCampaign.sponsorProfiles` is
**not** this link: it is the ruling-27 reverse of `CSponsorProfile.outreachCampaign`
(the campaign a funder *arrived through*) and stays as it is.

## Roles — nothing to change

Read on crm-test 10-20-26 as administrator:

- **Marketing Admin Role** reads `CSponsorProfile` at *all* (the picker) and
  cannot edit it. Relating a funder needs edit on both sides, so the
  application retries only a `noAccessToForeignRecord` refusal as the admin
  account — the same path the partner picker uses.
- **CustomAppAPIRole** reads and edits both entities: the funder's Campaigns
  tab reads the campaigns under the org-wide key after the user's own read of
  the funder record gates it (the partner-tab and Events-tab precedent), so the
  **Sponsor Manager Role needs no campaign grant**.

## Order

1. **crm-test** — `scripts/prospect_crm_test.sh funders` (dry run first:
   `scripts/apply_plan.sh test scripts/plans/coutreach-funders.json`, one
   change). Then `uv run python scripts/sandbox/seed_outreach_data.py --apply`
   relates Harrowgate Family Trust to *September 2026 filings — Postcard*.
2. **The sandbox baseline** — the relation is a new table, so the nightly
   reset truncates it until the next recapture (`SANDBOX-RESET.md`). Until
   then, re-run the seeder the morning of any demo.
3. **Production** at the Sunday 17:00 UTC slot, with the lead-model release,
   from inside the web container, with the three environment lines at the
   top of `scripts/apply_crm_plan.py`, then
   `scripts/plans/coutreach-funders.json --apply --production --expect 4658d1450804`.
4. **Boston** with its release: `scripts/apply_plan.sh boston scripts/plans/coutreach-funders.json 4658d1450804`.

The application feature-detects the link: until a CRM has it, the campaign form
shows no Funders picker and the funder's Campaigns tab explains that the CRM
does not link campaigns to this record type yet.

## Proof it landed

- The applier reads the link back on both sides (it prints `verified`).
- As the org key: `GET CSponsorProfile/<id>/sponsoredCampaigns?maxSize=1` → 200.
- As **Mark Marketing** (a real non-admin): Campaign Management → a campaign →
  Edit shows a **Funders** picker; ticking one and saving shows it on the
  campaign's Overview under *Funders*.
- As **Sally Sponsor**: Funder Management → Harrowgate Family Trust →
  **Campaigns** tab lists *September 2026 filings — Postcard*.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 10-20-26 14:43 | Claude (Claude Code) | Written for ruling 57; the plan dry-run on crm-test, one change, fingerprint `4658d1450804`. |
