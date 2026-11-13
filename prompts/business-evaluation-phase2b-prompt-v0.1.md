# Kickoff prompt — Business Evaluation, phase 2b: the survey engine

Last Updated: 11-13-26 14:24 · Revision 0.2 — see change log at the end.

Written for ruling BE23 (plan revision 0.5), approved by Doug 11-13-26: the
survey engine moves out of `evaluation/` after phase 2 and before phase 3.
Paste everything below the line into a fresh Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake`, after phase 2 has closed.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This prompt names
two stopping points. Between them the work proceeds without asking.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires. Open every reply with the local time from
`date`.

**Another session may be working in this checkout at the same time.** Before
choosing a version number or an Alembic migration number, read `git log` and
`alembic/versions/` and take the next free one; never take numbers from this
prompt. Commit only this phase's lines, staged and committed in one step, then
audit with `git show --stat`.

**First action.** Ruling BE23 is already in the plan (revision 0.5) and the
orchestrator (revision 0.6), merged and committed by the session that closed
phase 2. Check that the plan's § 4 carries ruling BE23 and its § 8 exists,
and that the orchestrator lists phase 2b, before any other work. If either is
missing, stop and tell Doug.

Read, in full, before any code:

- `prompts/business-evaluation-build-orchestrator-v0.1.md`: the rules every
  phase session follows. They bind this session.
- `prds/business-evaluation-plan.md`: the plan. **Its approved rulings are
  settled; do not re-open them.** This phase builds ruling BE23 and nothing
  else.
- `evaluation/CLAUDE.md`, and every file in `evaluation/`, including
  `frontend/` and `surveys/`.
- What phase 2 added that uses the link store or the survey page: start from
  `git log` for phase 2's commit and its `git show --stat`.
- `alembic/versions/0044_evaluation_links.py`, the `_dark_evaluation`
  middleware in `core/app.py`, `scripts/evaluation_make_link.py`, and every
  `tests/test_evaluation_*.py`.
- `OPEN-ITEMS.md` #83.

## What this phase is

**A refactor. Nothing a client, a mentor or a staff member sees may change.**
Every existing Business Evaluation test passes with no change except its
imports and paths. If a test needs any other change to pass, stop and put it
to Doug.

## Scope of this phase

1. **The survey engine**, a new package `surveys/`, holding no code specific
   to Business Evaluation:
   - The definition format and loader, from `evaluation/surveys.py`.
   - The link store and the saved answers, from `evaluation/store.py`,
     generalized. A link records its survey purpose key, the CRM entity type
     and record id it points at, the purpose's own data as JSON, and a display
     snapshot (for Business Evaluation, the company name) so that opening a
     link never calls the CRM.
   - The submit retry, from `evaluation/service.run_retry_cycle`, calling the
     survey purpose's submit function.
   - The public page and its API, from `evaluation/router.py` and
     `evaluation/frontend/`, at `/survey/{token}`, `/api/survey/…` and
     `/survey-assets/…`.
2. **The purpose registry**, `surveys/registry.py`. A survey purpose declares:
   its key; its feature switch setting; its link expiry setting; the folder
   holding its survey definitions; the surveys a link opens and in what order,
   given the link; the first screen's text and consent wording; the function
   called on submit; and the function called on a survey's first save.
3. **`evaluation/` keeps only what is specific to Business Evaluation**: its
   survey purpose registration, its definitions (they stay in
   `evaluation/surveys/`), the CRM writes on submit, the In Progress hook,
   phase 2's mentor side, and `scripts/evaluation_make_link.py`. Phase 2's
   link creation calls the engine's store.
4. **The old address keeps working.** `/evaluation/{token}` answers with a
   permanent redirect to `/survey/{token}`, so a link already emailed still
   opens. The old API paths are removed.
5. **The migration.** Rename `evaluation_link` to `survey_link` and
   `evaluation_answer` to `survey_answer`. Add the purpose key, entity type,
   record id, purpose data and display snapshot columns, and fill them on every
   existing row: purpose `business-evaluation`, entity `CEngagement`, record id
   from `engagement_id`, the rest from the existing columns. Production already
   has these tables, so the migration must work on tables with rows, and its
   downgrade must restore them.
6. **The switch.** A survey route answers only for a link whose survey
   purpose's switch is on. With `BUSINESS_EVALUATION` off, every survey
   address answers 404, exactly as `/evaluation/…` does today.
7. **Settings keep their names.** `EVALUATION_LINK_DAYS` and
   `EVALUATION_RETRY_SECONDS` stay, as Business Evaluation's own settings,
   named by its purpose registration. Decided, to avoid a settings migration.
8. **Tests.** All existing ones pass as described above. New: a test survey
   purpose, registered only inside the tests, that runs end to end through the
   engine (open, consent, save, submit, retry); a guard that fails if anything
   in `surveys/` imports from `evaluation/`; the migration up and down on a
   table with rows; the old address redirecting.
9. **Documentation.** A new `surveys/CLAUDE.md` saying how to add a survey
   purpose. `evaluation/CLAUDE.md` updated to what remains. One pointer line
   in the root `CLAUDE.md`. `OPEN-ITEMS.md` #83 updated.

**Stopping point (a).** Before moving any code, stop and put to Doug, in a
short note: the purpose registry's interface, the new table layout, and the
migration's steps.

**Stopping point (b).** Before closing the phase, run the application locally
against crm-test with the switch on. Give Doug runbook steps to repeat the
phase 1 live check: an old `/evaluation/…` link opens through the redirect; a
new link opens at `/survey/…`; the Finance survey saves, is closed and
reopened, and submits to its Business Evaluation record. Close the phase only
after Doug's report.

## Closing, in addition to the orchestrator's steps

The next phase's prompt already exists: phase 3's was written at the close of
phase 2. Revise it for the new paths (revision bump, change log line) and put
it to Doug for approval again.

## Not in this phase

A general Survey Response record in the CRM, sending to many people, totals
across responses, surveys staff can edit (plan § 8). Any change of behavior.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-13-26 11:54 | Claude (Cowork) | Created for ruling BE23 (option B: after phase 2, before phase 3). |
| 0.2 | 11-13-26 14:24 | Claude (Claude Code) | Moved into `prompts/`. First action rewritten: BE23 is merged into the plan (0.5) and the orchestrator (0.6) before this session starts, not committed by it. |
