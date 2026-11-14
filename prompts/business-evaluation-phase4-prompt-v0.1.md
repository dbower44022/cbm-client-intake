# Kickoff prompt — Business Evaluation, phase 4: review and approval

Last Updated: 11-14-26 17:23 · Revision 0.2 — see change log at the end.

**Approved by Doug 11-14-26.** Written at the close of phase 3 (v0.332.0).
Start a fresh Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake` and tell it to read this file and
follow everything below the line. Phase 3 is pushed and live.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This prompt names
two stopping points. Between them the work proceeds without asking.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires. Open every reply with the local time from
`date`.

**Another session may be working in this checkout at the same time** (one
committed v0.331.0 during phase 3). Before choosing a version number or an
Alembic migration number, read `git log` and `alembic/versions/` and take the
next free one; never take numbers from this prompt. Commit only this phase's
lines, staged and committed in one step, then audit with `git show --stat`.

Read, in full, before any code:

- `prompts/business-evaluation-build-orchestrator-v0.1.md`: the rules every
  phase session follows. They bind this session.
- `prds/business-evaluation-plan.md`: the plan. **Its approved rulings are
  settled; do not re-open them.** This phase builds § 3 steps 5 and 6 and
  rulings BE17 and BE18. Open question 6 (prompts editable in System
  Settings) is not this phase's.
- `evaluation/CLAUDE.md`: what phases 1 to 3 built, and their rules.
- `sessions/CLAUDE.md`: the Evaluations tab, co-mentors (`add_comentor`
  stamps `assignedUsers`), sessions and their scheduling.
- `OPEN-ITEMS.md` #83: what is owed.
- `evaluation/sending.py` (`answers_view`, `retry_analysis`), `evaluation/report.py`
  (the template and its `data-internal` section), the Evaluations tab in
  `sessions/frontend/app.js` (`openEvlAnswers`) and the Evaluations routes in
  `sessions/router.py`.
- `frontend/shared/richtext.js`: the shared `CBMRichText` editor this phase
  must use, and how it handles images.

## Scope of this phase

Build review and approval, dark behind `BUSINESS_EVALUATION`:

1. **The report editor**: reviewers edit `reviewedReport` in the shared
   `CBMRichText` editor, on the Evaluations tab, beside the client's answers.
   `draftReport` is never written after the analysis (BE17); the editor keeps
   the draft visible for comparison. Save sends only a changed report, as the
   user. Check that the editor and the CRM keep the `data-internal` marker on
   Points to check, which phase 5's client version depends on.
2. **Co-mentor editing** (BE18): every co-mentor on the engagement can edit
   the reviewed report. The access is the CRM's own (the record carries the
   engagement's `assignedUsers`); prove it as a real non-admin co-mentor.
   On crm-test, Matt Mentor is a co-mentor on Brightline Bakehouse.
3. **Approve** (BE17): only the engagement's mentor can approve. Approve sets
   Approved, `approvedAt` and `approvedBy`. A co-mentor who presses Approve
   is told why it is refused; the button is never hidden or disabled.
4. **Scheduling the review session** (plan § 3 step 6): from an Approved
   round, the mentor schedules a session through the existing session
   scheduling, and the session is linked to the round's records
   (`reviewSession`).
5. **Every save and the Approve are recorded** through `core/action_log.py`.
6. **Tests**: the editor routes, the draft never written, Approve by the
   mentor and refused for a co-mentor, the review-session link, the switch
   off.
7. **`OPEN-ITEMS.md` #83** updated.

**Stopping point (a).** Before building, put to Doug, with a recommendation
for each:
- what happens to editing after Approve: locked, editable by the mentor only,
  or editable by every reviewer with the approval withdrawn;
- whether a reviewer can see what changed from the draft (side by side, a
  marked-up difference, or the draft alone beside the editor);
- whether images may be put into the report (the email-signature precedent
  refuses them, because the client version is emailed and recipients cannot
  reach the application's image proxy);
- how the review session is chosen: a new session made from the round, or an
  existing scheduled session picked.

After Doug's go-ahead, build steps 1 to 7.

**Stopping point (b)**: on a local run against crm-test, Doug edits a draft
as Joe Mentor, edits it as Matt Mentor (the co-mentor), approves as Joe
Mentor, is refused Approve as Matt Mentor, and schedules the review session.
`scripts/evaluation_sample_reports.py` makes the drafts to work on; crm-test
resets nightly, so make them the same day. Close the phase only after Doug's
check.

## Not in this phase

Release to the client and action items as records (phase 5); the partner
offering (phase 6); the other four areas and prompts editable in System
Settings (phase 7 and later).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-14-26 13:35 | Claude (Claude Code) | Drafted at the close of phase 3, from the orchestrator and what phases 1 to 3 built. |
| 0.2 | 11-14-26 17:23 | Claude (Claude Code) | Approved by Doug. |
