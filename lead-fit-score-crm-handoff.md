# CRM handoff — lead enrichment build phase 1: the fit score on `CProspect`

Last Updated: 10-20-26 17:54 · Revision 0.2 — see change log at the end.

Nine fields on the lead (`CProspect`), written by the free pass: the fit
score, the service-area gate, the county, the three signals, the reasons, the
time scored and the rule version. Design: `prds/lead-enrichment/design.md`
§ 4 (rulings E2, E12, E13). Build plan:
`prds/lead-enrichment/build-plan-phase-1.md`.

**Additive.** Nine new fields. Nothing is removed, renamed or narrowed. Safe
to apply ahead of the code: the application feature-detects the fields and
writes nothing until they exist and the switch is on.

## 0. Current state

| CRM | State | Evidence |
|---|---|---|
| crm-test | **Done 10-20-26 17:48.** Applied by Claude (`scripts/enrichment_crm_test.sh fitscore`): nine fields created and read back by the applier. § 3 steps 1 and 2 passed the same minute: all nine present, none Read-only; the org-wide key lists `CProspect` with `fitScore,fitGate` (200, total 3,817). The non-admin check rides the build phase's live pass. | The applier's output; a metadata and list read as the org-wide key. |
| Production | **Not applied.** At a Sunday 17:00 UTC slot, after the crm-test pass. | — |
| Boston | **Owed** with the release that carries build phase 1. | — |

Decided here, and said so:

- **No field is Read-only.** The application writes all nine, and a
  Read-only field drops every API write with HTTP 200 (CLAUDE.md Gotchas,
  ruling 40). Staff are told by each field's tooltip not to edit it by hand,
  and the next pass overwrites a hand edit anyway.
- **No role grant changes.** The free pass writes under the org-wide API
  key, and `CustomAppAPIRole` already holds `CProspect` create, read all and
  edit all (`scripts/migrate_outreach_roles.py`, line 73). The Marketing
  Admin Role already reads `CProspect` at all, so the Leads grid can show
  the new columns.
- **No sandbox seeder stage.** crm-test's nightly reset empties columns added
  after the baseline. The worker rescores every lead whose `fitScoredAt` is
  empty, so the scores come back on the first pass after each reset with no
  seeder and no re-baseline. The cost: for up to one sweep interval after
  04:00 UTC, crm-test's Leads grid shows no scores.
- **The JSON field question (design E5, E6) is settled, verified on crm-test
  10-20-26:** `fields.jsonObject` and `fields.jsonArray` are `notCreatable:
  true` and `filter: false`, while `fields.text` is `filter: true` and
  `fullTextSearch: true`. The survey response record's answers field will be
  a `text` field. This handoff does not build it; it is recorded here because
  this is where it was read.

## 1. Names

Every name below is stored exactly as written: `CProspect` is a custom
entity, so its field names gain no prefix. The applier checks this on read
back.

| Field | Type | Label |
|---|---|---|
| `fitScore` | int, 0 to 100 | Fit score |
| `fitGate` | enum: (empty), Passed, Location unknown, Out of area | Service area |
| `fitCounty` | varchar 100 | County |
| `fitOperating` | int, 0 to 100 | Fit: operating business |
| `fitSegment` | int, 0 to 100 | Fit: segment |
| `fitFindability` | int, 0 to 100 | Fit: findability |
| `fitReasons` | text | Fit reasons |
| `fitScoredAt` | datetime | Fit scored |
| `fitRuleVersion` | varchar 20 | Fit rule version |

## 2. Apply on crm-test

Before you start: a terminal on the build computer whose prompt ends in
`cbm-client-intake$`, any time except 04:00 to 05:00 UTC.

1. In that terminal, type the line below and press Enter.

   ```
   cd ~/Dropbox/Projects/cbm-client-intake
   ```

   You should see the prompt return with no message. What it does: puts you
   in the project folder the script needs.

2. In the same terminal, type the line below and press Enter.

   ```
   scripts/enrichment_crm_test.sh fitscore
   ```

   **This changes crm-test's CRM:** it creates the nine fields. To undo it, the
   fields can be removed in the Entity Manager; nothing else depends on them
   yet. You should see nine `created` lines, a rebuild, and nine read-back
   lines each ending `ok`, within about a minute. If not, stop and paste the
   last lines shown. What it does: applies exactly the plan that was dry-run,
   refusing if it changed.

Report back: the last ten lines from step 2.

## 3. Verify

Claude does these from the build computer once step 2 is reported.

1. Read `entityDefs.CProspect.fields` from `GET /Metadata` and confirm all
   nine fields are present under the names in § 1, with no `readOnly`.
2. As the org-wide API key: `GET /CProspect?maxSize=1&select=fitScore,fitGate`
   answers 200.
3. Re-run `scripts/preflight_crm.py` and diff against the run taken before
   the apply; only the nine fields should differ.

The non-admin check belongs to the build phase's live pass, because only
the code puts the columns on the Leads grid: a member of the Marketing Admin
Team opens Campaign Management, the Leads tab, and sorts by Fit score.

## 4. Production and Boston

Production: at a Sunday 17:00 UTC slot, run by Doug from inside the
production web container, with the same plan and fingerprint. Claude
writes the step page for that slot when it is booked. Boston:
`scripts/apply_plan.sh boston scripts/plans/cprospect-fit-score.json
8e57af53eef5` with its release.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.2 | 10-20-26 17:54 | Claude (Claude Code) | crm-test applied and verified (§ 0). |
| 0.1 | 10-20-26 17:38 | Claude (Claude Code) | Created. Plan file `scripts/plans/cprospect-fit-score.json`, dry run on crm-test clean, fingerprint `8e57af53eef5`. JSON field types read as not creatable. |
