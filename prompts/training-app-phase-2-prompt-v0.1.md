# Kickoff prompt — the training application, phase 2: the Training button and the reminder

Last Updated: 11-21-26 15:59 · Revision 1.0 — see change log at the end.

**Approved by Doug as written, 11-21-26.** Start a fresh Claude Code
session rooted in `~/Dropbox/Projects/cbm-client-intake`, tell it to read
this file, and tell it to follow everything below the line.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This session builds
phase 2 of `prds/training-app-plan.md`. Its stopping points are **stop 2a**,
after the button's place in each application is decided, and **stop 2**, at
the end. Between them, work proceeds without asking, except for a decision
that passes the two-part test.

The first reply states the operating mode and the `CLAUDE.md` files loaded.
Open every reply with the local time from `date`.

**Other sessions work in this checkout.** Commit only this session's files,
staged and committed in one step, then audit with `git show --stat`. Do not
push unless Doug asks.

## Read first

- `prds/training-app-plan.md`: TR2, TR3, TR4, decisions 6 to 11, design
  § 5.1, the data model § 6, phase 2 in § 7, and the open question in § 9
  on where the button sits.
- The `courses/` package as phase 1 built it (v0.362.0, v0.362.2): `service.py`
  (who may take a course, status), `store.py` (`training_dismissal` exists
  but nothing writes it yet), `router.py` (the same-person check every save
  carries, and why).
- The headers of the three applications the evaluation course names:
  `assignments/frontend/`, the shared sessions frontend (Client Management),
  `mentoradmin/frontend/`.
- The root `CLAUDE.md` conventions: `busy.js` then `textsize.js` first, then
  the new `training.js`; buttons never disabled or hidden; no bare `vh`.

## What phase 2 builds

1. **Stop 2a first.** Read each application's header and propose where the
   Training button sits in each, with a picture of each header (open
   question § 9). Wait for Doug's choice.
2. `GET /api/courses/mine?app=<route>` gains each course's **due** state
   (plan § 6: can open, not hidden, at 1.0 or later, no completion and no
   dismissal at the current N), and the change log entry of the current
   revision for a course due again.
3. `POST /api/courses/{course}/dismiss`, writing `training_dismissal` at the
   current N, with the same-person check.
4. `frontend/shared/training.js`: the Training button, opening
   `/courses/?app=<route>`, and the reminder bar under the header with
   **Start** or **Continue** and **Don't remind me again**. It never covers
   the application's controls. Loaded by every application a course names;
   with `TRAINING_COURSES` off it draws nothing.
5. Tests, the full suite passing, a changelog entry and a version bump.

A draft course (0.x) is never due, so stop 2 needs a course at 1.0 or later:
a small test course listed in Client Administration, Client Management and
Mentor Administration, hidden in production by `TRAINING_HIDDEN_COURSES`.

## Stop 2

Commit, then hand Doug a step-by-step page (the `instruction-discipline`
skill, built with `scripts/build_runbook.py`) for the check on the
Association: as Kitty Cat, the reminder in Client Administration, dismissed
there and gone from Client Management and Mentor Administration; then the
test course raised to 2.0 and the reminder back with its change log entry.
Keep each course page in a normal window and every exercise sign-in in a
private window (the lesson of stop 1). Wait for his result before closing
the phase.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 11-21-26 15:59 | Doug | Approved as written. |
| 0.1 | 11-21-26 15:58 | Claude (Claude Code) | Drafted at the close of phase 1 (stop 1 passed 11-21-26). |
