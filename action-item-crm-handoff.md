# CRM handoff — Business Evaluation phase 5: `CActionItem`

Last Updated: 11-16-26 01:10 · Revision 0.2 — see change log at the end.

One new record type: one Action Item record per action item a client agreed
to when a Business Evaluation report was released. Linked to the engagement,
to the Business Evaluation it came from, and to its owner, a Contact (the
client's people and the mentors alike). Plus two role grants. Design:
`prds/business-evaluation-plan.md` § 3 step 7, ruling BE20, open question 1
(answered by Doug 11-15-26: a new record type, not the CRM's own Task, whose
owner must be a CRM login and which no role can read today). Build prompt:
`prompts/business-evaluation-phase5-prompt-v0.1.md`.

**Additive.** One entity, 5 fields, 3 links, Multiple Assigned Users and
Collaborators switched on, 2 role grants. Nothing removed, renamed or
narrowed. Safe ahead of the code: the application feature-detects the entity
(`evaluation/release.items_available`) and stays dark behind
`BUSINESS_EVALUATION`. **Needs `business-evaluation-crm-handoff.md` first**:
one link points at `CBusinessEvaluation`.

## 0. Current state

| CRM | State | Evidence |
|---|---|---|
| The Business Mentors Association (the test system) | **Done 11-15-26** by Doug with `./scripts/evaluation_bma.sh apply`: both plans (phase 1's too) created and verified, the four grants read back, rebuild HTTP 200; the org-wide key reads `CActionItem` (HTTP 200). **Non-admin check passed 11-16-26**: Joe Mentor released a report with three action items and marked one Done. Dry run 11-15-26: fingerprint `5bf3e2de43a8` while `CBusinessEvaluation` was missing; `1dd0c354c974` once it exists (the fingerprint covers the work still to do, not the file). | The applier's dry-run output. |
| crm-test | **Not applied.** Doug chose the Association for testing. | — |
| Production | **Not applied.** At a Sunday 17:00 UTC slot with the phase 1 plan, after the Association's check. | — |
| Boston | **Owed** with its release. | — |

Decided here, and said so:

- **No field is Read-only** (ruling 40): the application writes them all.
- **`engagement`, `businessEvaluation` and `owner` are required by the
  application, not the CRM** (the applier creates links after field
  parameters, as in phase 1).
- **`status`** is Open, Done or Dropped, default Open, audited (the stream is
  on). **`priority`** and **`timeHorizon`** carry the report's values and may
  be empty, for an item the mentor added by hand. **`dueDate`** is a date.
- **The owner is a Contact**, so a client's person and a mentor (whose
  profile's `contactRecord` is a Contact) are owners in the same way.
- **Grants:** `CustomAppAPIRole` create, read all, edit all. **Mentor Role**
  create, read own, edit own: a mentor writes the items when releasing and
  marks them Done or Dropped; "own" reaches every item carrying the mentor in
  `assignedUsers`, which the application stamps from the engagement and the
  nightly reconciliation keeps. No delete for either.

## 1. Names

`CActionItem` (typed `ActionItem`; the CRM adds the `C`). Its fields and its
three links are stored as written: `engagement`, `businessEvaluation`,
`owner`. The reverse links on custom entities are stored as typed:
`CEngagement.actionItems`, `CBusinessEvaluation.actionItems`. The reverse on
`Contact` gains a `c`: `Contact.cActionItemsOwned`.

## 2. Apply

From the build computer (Doug's desktop computer, host name
doug-System-Product-Name), in `~/Dropbox/Projects/cbm-client-intake`:

    PYTHONPATH=. uv run python scripts/run_with_admin.py --env <the CRM's env file> \
        scripts/apply_crm_plan.py crm-plans/action-item.json              # dry run
    ... crm-plans/action-item.json --apply --production --expect 1dd0c354c974
    PYTHONPATH=. uv run python scripts/run_with_admin.py --env <the CRM's env file> \
        scripts/migrate_evaluation_roles.py --apply

For the Association, `./scripts/evaluation_bma.sh apply` runs both plans and
the grants. For production, from inside the deployed web container, as the
header of `scripts/apply_crm_plan.py` describes.

## 3. Check

- `GET /Metadata` reads `entityDefs.CActionItem.links` with `engagement`,
  `businessEvaluation` and `owner`, and `entityDefs.CEngagement.links` with
  `actionItems`.
- As a real non-admin mentor (Joe Mentor), on an engagement's Evaluations
  tab: release an approved report with one action item agreed; the item
  shows under Action items; changing its status saves.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-15-26 23:20 | Claude (Claude Code) | Created with phase 5. |
| 0.2 | 11-16-26 01:10 | Claude (Claude Code) | Applied on the Association and checked as a non-admin. |
