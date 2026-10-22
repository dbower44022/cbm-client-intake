# CRM handoff — lead enrichment phase 2: `CEnrichmentFinding`

Last Updated: 10-22-26 11:17 · Revision 0.1 — see change log at the end.

One new record type: one record per value an enrichment tier proposes, linked
to the lead (`CProspect`) or to a client's Company (`Account`). Plus three
role grants. Design: `prds/lead-enrichment/design.md` § 6; build plan:
`prds/lead-enrichment/build-plan-phase-2.md` § 2 (rulings E10, E12, E14,
E19).

**Additive.** One entity, 16 fields, 2 links, 3 role grants. Nothing removed,
renamed or narrowed. Safe ahead of the code: the application feature-detects
the entity and its two links, failing closed.

## 0. Current state

| CRM | State | Evidence |
|---|---|---|
| crm-test | **Done 10-22-26** by Claude: `scripts/enrichment_crm_test.sh findings` (fingerprint `7d96e327dbd4`) created and read back the entity, 16 fields and both links; `scripts/enrichment_crm_test.sh roles` set and read back the three grants and rebuilt (HTTP 200). The org-wide key lists `CEnrichmentFinding` (200, total 0). The non-admin check rides the live pass. | The applier's and the role script's output. |
| Production | **Not applied.** At a Sunday 17:00 UTC slot, after crm-test's pass. | — |
| Boston | **Owed** with its release. | — |

Decided here, and said so:

- **No field is Read-only** — the application writes every one (ruling 40).
- **The entity is type Base**, no stream: a finding is a small fact with its
  own decided-by and decided-at, not a conversation.
- **`name` is required by the Base type,** so the application names each
  finding (`website: https://…`, `Person: Jane Doe`, `Summary`).
- **Grants:** `CustomAppAPIRole` create, read all, edit all (the worker writes
  findings; Accept and Reject are written under it after the application's
  team gate). Marketing Admin Role and Client Assignment Role read all, edit
  all, so the findings can be read in the CRM itself. The Mentor Role gets
  nothing (E19).
- **No sandbox seeder stage.** Findings are made by runs; a reset that
  removes them leaves nothing broken.

## 1. Names

`CEnrichmentFinding` (typed `EnrichmentFinding`; the CRM adds the `C`). Its
fields are stored exactly as written (a custom entity's fields gain no
prefix). The link to `Account` is stored on Account as
`cEnrichmentFindings` (a non-custom entity's side gains a `c`); the applier
computes and verifies both.

## 2. Apply on crm-test (done 10-22-26)

From the build computer, in `~/Dropbox/Projects/cbm-client-intake`:

```
scripts/enrichment_crm_test.sh findings
```

```
scripts/enrichment_crm_test.sh roles
```

## 3. Verify

1. `GET /Metadata` → `entityDefs.CEnrichmentFinding`: the 16 fields, none
   Read-only, links `prospect` and `company`; `entityDefs.Account.links`
   carries `cEnrichmentFindings`, `entityDefs.CProspect.links` carries
   `enrichmentFindings`.
2. As the org-wide key: `GET /CEnrichmentFinding?maxSize=1` answers 200.
3. A real non-admin pass (the live-pass step page): a Marketing Admin Team
   member sees a lead's findings; a Client Administration Team member accepts
   one on a client.

## 4. Production and Boston

Production at a Sunday slot, from inside the production web container: the
applier with this plan and fingerprint, then
`scripts/migrate_enrichment_roles.py --apply` under the admin login. Claude
writes the step page when the slot is booked. Boston:
`scripts/apply_plan.sh boston scripts/plans/cenrichment-finding.json
7d96e327dbd4`, then the role script against Boston.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 10-22-26 11:17 | Claude (Claude Code) | Created. Applied and verified on crm-test the same day. |
