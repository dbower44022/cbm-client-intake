# Kickoff prompt — Business Evaluation: planning wider uses, before phase 6

Last Updated: 11-16-26 01:55 · Revision 0.1 — see change log at the end.

**Written 11-16-26 at Doug's request**, after phase 5 closed (v0.338.0) and
before phase 6 starts. Start a fresh Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake`, tell it to read this file, and tell it
to follow everything below the line.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This is a planning
session: **no application code is written**. Its products are documents.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires. Open every reply with the local time from
`date`.

**Another session may be working in this checkout.** Commit only this
session's files, staged and committed in one step, then audit with
`git show --stat`. Do not push; Doug pushes.

## Why this session exists

Doug wants to **expand the uses of the Business Evaluation** before phase 6
(the partner and funder offering) is built. Phase 6's prompt is approved but
not started, so phase 6 waits for this plan. What "expand the uses" means is
**Doug's to say**: this session does not guess it.

## Read first, before the first question

- `prds/business-evaluation-plan.md`: the plan. Rulings BE1 to BE23 are
  approved. **This session may propose amendments or new rulings (BE24
  onward), each one marked proposed until Doug approves it.** It never edits
  an approved ruling silently.
- `prompts/business-evaluation-build-orchestrator-v0.1.md`: the phases, their
  state, and the rules every phase session follows.
- `prompts/business-evaluation-phase6-prompt-v0.1.md`: the approved phase 6
  prompt, which this plan may change.
- `evaluation/CLAUDE.md` and `surveys/CLAUDE.md`: what phases 1 to 5 built.
  The survey engine (ruling BE23) already serves any survey purpose. Plan § 8
  names later purposes, such as customer satisfaction.
- `OPEN-ITEMS.md` #83: what is owed.

Read these quietly. Do not summarise them back to Doug.

## How the session runs

1. **Elicit first.** Ask Doug what uses he has in mind: one question at a
   time, in plain prose, never a list of options he did not ask for. Keep
   asking until each new use is clear: who starts it, who answers, what
   happens to the answers, who sees the results. A worked example from real
   project content helps him answer.
2. **Then map each use onto what exists.** For each one, say plainly what is
   already built that it reuses (the survey engine, the analysis, review and
   approval, release, action items), what is new, and which approved rulings
   it touches.
3. **Decisions go to Doug one at a time**, in the consequential decision
   template from `~/.claude/CLAUDE.md`, and only where the two-part test
   holds. Routine choices are decided and announced.
4. **Write the plan only after Doug has answered.** A draft shown earlier is
   marked as a strawman and is never committed as settled.

## Products, once Doug has approved the content

- **`prds/business-evaluation-plan.md`**: a new revision with the new uses,
  the proposed rulings as Doug approved them, any change to § 5's data model,
  and the build phases re-cut where needed. Change log line.
- **The orchestrator**: the phase table changed to match. Phase 6's state
  reads "on hold for the expansion plan" until Doug says otherwise.
- **Phase 6's prompt**: revised only if the plan changes phase 6, as a new
  revision for Doug's approval.
- **`OPEN-ITEMS.md` #83**: one line naming the plan revision and what waits on it.
- **The next prompt**: a draft kickoff prompt for whichever phase comes next
  under the new plan, revision 0.1, for Doug's approval.

## Stopping points

- **(a)** After eliciting: a short statement of each use as understood, for
  Doug to correct before any mapping.
- **(b)** The decisions, one at a time.
- **(c)** The revised plan and orchestrator, for review before they are committed.

## Not in this session

Code, CRM changes, live tests, and the production CRM change at the Sunday
slot. That change is a separate item in #83.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-16-26 01:55 | Claude (Claude Code) | Written at Doug's request after phase 5 closed. |
