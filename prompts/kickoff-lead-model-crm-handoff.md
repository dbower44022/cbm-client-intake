# Kickoff — the lead model's CRM handoff (build plan § 7a.5 step 1)

Revision 1.0 · Last Updated: 10-19-26 01:22 · Prepared by Claude (Claude Code) for D. Bower

| Rev | Date (MM-DD-YY HH:MM) | Change |
|---|---|---|
| 1.0 | 10-19-26 01:22 | First version, written when build plan § 9 questions 13–16 were answered (rulings 45–48). |

Operating mode: DETAIL.

## What this session does

Writes the CRM handoff for the lead model, applies it to crm-test, and writes
the one-time script that moves stored values. This is step 1 of build plan
§ 7a.5. **No application code changes in this session.** Step 2, the code, is
the next session.

## Read first, in this order

1. The repository's root `CLAUDE.md`.
2. `prds/prospect-marketing/README.md`, especially *Rules for working in this
   directory*. One session at a time: check `git log -3 --
   prds/prospect-marketing` before starting.
3. `prds/prospect-marketing/rulings.md`, rulings 41–48. They are binding.
   Ruling 45 says the stored values change, not only the labels.
4. `prds/prospect-marketing/build-plan.md` § 7a in full. Its drafts in § 7a.2
   are drafts. Put any you depend on to Doug before building on them, one
   question at a time.
5. `coutreach-entities-crm-handoff.md`, the Phase 1 handoff this one amends.
6. `prds/chapter-network/crm-update-runbook.md`, including § 7's traps.
7. The `espo-crm-changes` skill. Load it before writing any part of the
   handoff.

## What the handoff covers

- `CProspect`: the label becomes *Outreach Lead*. A lead status field holds
  Unqualified · Qualified · Disqualified · Converted. `entryDoor` is labelled
  *Lead Source*, and the five public forms are added as its values (ruling 48).
  Side exits become Duplicate · Do Not Contact · Declined · Stale. Whether the
  existing `funnelStage` field is reused as the status or a new field is
  added is a decision for Doug. Read the live metadata before proposing.
- `cFunnelStage` / `cEntryStage` on Contact and Account: Prospect · Engaged ·
  Opportunity.
- A one-time move script for the stored values, dry run by default, using the
  map in § 7a.5 step 1. Count each CRM's records first (ruling 45).
- The Read-only rule (ruling 40): no field the application writes is built
  Read-only.

## Order

1. Read live metadata on crm-test for the three entities. Never trust the
   handoff's state table.
2. Draft the handoff and put its open decisions to Doug.
3. Apply it on crm-test through the API or the applier. Verify it as the
   org-wide API key and as a real non-admin.
4. Run the move script dry on crm-test, then for real after Doug's go.
5. Record the state in the README and the build plan. Commit, and stop for
   Doug to review and push.

Production waits for the code release (§ 7a.5 step 4), at a Sunday 17:00 UTC
slot. Boston gets it with its release.
