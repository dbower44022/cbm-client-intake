# Kickoff prompt — Business Evaluation, phase 5: release and action items

Last Updated: 11-15-26 12:20 · Revision 0.1 — see change log at the end.

**Draft, awaiting Doug's approval.** Written at the close of phase 4
(v0.336.0). When approved, start a fresh Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake` and tell it to read this file and
follow everything below the line. Phase 4 must be pushed first.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This prompt names
two stopping points. Between them the work proceeds without asking.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires. Open every reply with the local time from
`date`.

**Another session may be working in this checkout at the same time** (the
Integrations build committed v0.333.0 to v0.335.0 during phase 4). Before
choosing a version number or an Alembic migration number, read `git log`,
the working tree's `pyproject.toml` and `alembic/versions/`, and take the
next free one; never take numbers from this prompt. Commit only this
phase's lines, staged and committed in one step, then audit with
`git show --stat`.

Read, in full, before any code:

- `prompts/business-evaluation-build-orchestrator-v0.1.md`: the rules every
  phase session follows. They bind this session.
- `prds/business-evaluation-plan.md`: the plan. **Its approved rulings are
  settled; do not re-open them.** This phase builds § 3 step 7 and rulings
  BE19 and BE20, and needs **open question 1** answered (which CRM entity
  holds action items).
- `evaluation/CLAUDE.md`: what phases 1 to 4 built, and their rules.
- `sessions/CLAUDE.md`: the Evaluations tab, the session editor, Documents
  and the record's email composer.
- `docs/CLAUDE.md`: filing a document in the engagement's Documents.
- `OPEN-ITEMS.md` #83: what is owed.
- `evaluation/review.py` (approval, the review session), `evaluation/report.py`
  (the template and its `data-internal` section), `evaluation/email.py` (the
  invitation, the pattern for a new email), and the review screen in
  `sessions/frontend/app.js` (`evlReviewScreen`).

## Scope of this phase

Build release and action items, dark behind `BUSINESS_EVALUATION`:

1. **The client version** (BE19): the reviewed report without every
   `data-internal` section. Made on the server from `reviewedReport`, never
   from `draftReport` (BE17). A test proves an internal section never
   reaches it.
2. **Release** (§ 3 step 7): from an Approved record whose review session
   is linked, the mentor releases the client version. It is filed in the
   engagement's Documents and emailed to the client from the mentor's own
   mailbox through the shared composer, which the mentor edits before
   sending. Status becomes **Reviewed with Client**, with `releasedAt`.
   Only the engagement's mentor releases, as only the mentor approves.
3. **Action items as records** (BE20): the action items the client agreed
   to become records on the engagement, each with an owner and a due date,
   in the entity open question 1 settles. A CRM change goes through a plan
   in `crm-plans/`, applied to crm-test by `scripts/apply_crm_plan.py`,
   with a handoff file for production.
4. **Editing after release**: decided at stopping point (a).
5. **Every release and every action item write is recorded** through
   `core/action_log.py`.
6. **Tests**: the client version without internal sections, release by the
   mentor and refused for a co-mentor, refused before approval and before a
   review session, the action items written, the switch off.
7. **`OPEN-ITEMS.md` #83** updated.

**Stopping point (a).** Before building, put to Doug, with a recommendation
for each:
- open question 1: a new action-item entity linked to the engagement, or
  the CRM's own Task entity;
- what the client version looks like as a document: the file type (a PDF,
  or a Google Doc in the engagement's Drive folder) and its heading;
- how the mentor picks the action items the client agreed to, and sets
  each one's owner and due date;
- what happens to editing once a report is Reviewed with Client: locked, or
  a new release;
- the release email's wording.

Show Doug **the client version of a sample report** (plan § 6, phase 5's
stopping point) at this stop.

After Doug's go-ahead, build steps 1 to 7.

**Stopping point (b)**: on a local run against crm-test, Doug, as Joe
Mentor, approves a sample round, links a review session, releases one
area, sees the document on the Documents tab, sends the email (it goes to a
sandbox address; say where it lands), and confirms the action items. He is
refused Release as Matt Mentor. `scripts/evaluation_sample_reports.py` makes
the drafts. **crm-test resets at 04:00 UTC, which is 23:00 local time**:
make the drafts after the reset and finish before the next one. A local run
needs `ESPO_DRY_RUN=false`, `BUSINESS_EVALUATION=true`, a `SESSION_SECRET`,
and, for the sample script, the local database container
`cbm-client-intake-db-1` with `DATABASE_URL` set and migrated. A local run has
no provisioning administrator, so a link the deployed applications escalate
is refused there. Close the phase only after Doug's check.

## Not in this phase

The partner offering (phase 6); the other four areas and prompts editable in
System Settings (phase 7 and later).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-15-26 12:20 | Claude (Claude Code) | Drafted at the close of phase 4, from the orchestrator and what phases 1 to 4 built. |
