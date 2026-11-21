# Kickoff prompt — the training application, phase 1: the course page

Last Updated: 11-21-26 11:54 · Revision 0.2 — see change log at the end.

**Draft for Doug's approval.** Once approved, start a fresh Claude Code
session rooted in `~/Dropbox/Projects/cbm-client-intake`, tell it to read
this file, and tell it to follow everything below the line.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This session builds
phase 1 of `prds/training-app-plan.md`. Its one stopping point is **stop 1**,
at the end; between the start and stop 1, work proceeds without asking,
except for a decision that passes the two-part test.

The first reply states the operating mode and the `CLAUDE.md` files loaded.
Open every reply with the local time from `date`.

**Other sessions work in this checkout.** Commit only this session's files,
staged and committed in one step, then audit with `git show --stat`. Do not
push; Doug pushes.

## Read first

- `prds/training-app-plan.md` in full: the rulings TR1 to TR12, the
  decisions in § 4, the design § 5, the data model § 6, phase 1 in § 7.
- `training/CLAUDE.md`, `training/evaluation-staff-course/evaluation-demo.md`
  and `scripts/build_runbook.py`.
- The root `CLAUDE.md`: the conventions (`busy.js` then `textsize.js` first,
  the shared grid, `{{org}}` and `{{abbr}}`, buttons never disabled, no bare
  `vh`), the System Settings section, "build a store once per process" and
  the Alembic id limit of 32 characters.
- `setup/CLAUDE.md`, and the memory on the setup fixture: every new setting
  needs its row in `tests/fixtures/setup_payload_before_integrations.json`.
- One existing small package for its shape: `news/` (router, service, team
  gate, frontend).

## What phase 1 builds

1. The `courses/` package: discovery of `training/*/course.yaml` at start-up,
   the revision read from the Markdown, the significant-revision rule (N of
   N.M), hidden courses.
2. `courses/render.py`: the parser moved out of `scripts/build_runbook.py`,
   which then imports it and produces the same page as before (check by
   rebuilding the evaluation demo's page and comparing). Tokens
   `{{training_url}}` and `{{signin:<role>}}`; the script prints the role
   name in place of a sign-in.
3. The migration `0053_training_courses` and its store, borrowing the shared
   engine (`core/store.shared_engine`): the four tables of plan § 6.
4. The pages: `/courses/` (the member's list, `?app=<route>` ordering) and
   `/courses/{course}` (plan § 5.2): tick boxes saving as ticked, checkpoint
   boxes saving as typed, the progress count, collapse-and-scroll after a
   tick, **Complete course** naming what is missing, the done state.
   Gated: signed in, and able to open at least one of the course's
   applications.
5. The switch `TRAINING_COURSES` and the settings `TRAINING_SYSTEM_URL`,
   `TRAINING_SIGNINS` (secret) and `TRAINING_HIDDEN_COURSES`, each on the
   System Settings page with its fixture row.
6. The evaluation demo: its `course.yaml` (applications `assignments`,
   `mentorsessions`, `mentoradmin`), the training system's address as
   `{{training_url}}`, the three sign-ins as `{{signin:…}}`, and each
   checkpoint worded as something to type. Its revision stays 0.x (a draft,
   decision 9).
7. Tests for each of the above, the full suite passing, a changelog entry and
   a version bump.

Not in phase 1: the Training button, the reminder and dismissal (phase 2);
Needs you and the report (phase 3); the mentor onboarding tick (phase 4);
the help agent (phase 5). Leave room for phase 5: each step on the course
page will gain an **I need help** button, so give a step a stable element
and key the agent can be pointed at.

## Stop 1

Commit, then hand Doug a step-by-step page (the `instruction-discipline`
skill) for the check on the Business Mentors Association's system after he
pushes: switch on `TRAINING_COURSES`, fill in the training address and the
three sign-ins, then, signed in as Kitty Cat, start the evaluation course,
stop halfway, resume on another computer or private window, and complete it.
Wait for his result before closing the phase.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.2 | 11-21-26 11:54 | Claude (Claude Code) | Plan revision 0.3: TR11 and TR12 (the help agent, phase 5) named as out of scope, with room left for its button. |
| 0.1 | 11-21-26 11:47 | Claude (Claude Code) | Drafted at the close of the planning session, from plan revision 0.2. |
