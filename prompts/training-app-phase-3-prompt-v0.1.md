# Kickoff prompt — the training application, phase 3: Needs you and the training report

Last Updated: 11-21-26 22:33 · Revision 0.1 — see change log at the end.

**Draft for Doug's approval.** Once approved, start a fresh Claude Code
session rooted in `~/Dropbox/Projects/cbm-client-intake`, tell it to read
this file, and tell it to follow everything below the line.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This session builds
phase 3 of `prds/training-app-plan.md`. Its stopping points are **stop 3a**,
after the report's grid and its one open question are settled, and **stop
3**, at the end. Between them, work proceeds without asking, except for a
decision that passes the two-part test.

The first reply states the operating mode and the `CLAUDE.md` files loaded.
Open every reply with the local time from `date`.

**Other sessions work in this checkout.** Commit only this session's files,
staged and committed in one step, then audit with `git show --stat`. Do not
push unless Doug asks.

## Read first

- `prds/training-app-plan.md`: TR5, TR6, decisions 8 and 10, design § 5.3
  and § 5.4, the settings table in § 5.7, phase 3 in § 7, and the open
  question in § 9 on whether the report offers a download of its grid.
- The `courses/` package as phases 1 and 2 built it (v0.362.0 to v0.363.1):
  `service.py` (who may take a course, status, `due`), `store.py`, and
  `router.py` (`GET /api/courses/mine` and its `reminder`; the same-person
  check, and why).
- The home page's Needs you: `portal/needs.py` (its rules), and the
  `GET /api/portal/home/needs` read in `portal/router.py`. The root
  `CLAUDE.md` § *Portal + authentication*, "The new home page".
- Chapter News's read report (`news/`): decision 10 takes its rule for who
  counts — every active regular login in a team that opens one of the
  course's applications, plus administrators in at least one team.
- The shared grid (`frontend/shared/grid.js`, `grid.css`, the root
  `CLAUDE.md` conventions) and `prds/shared-grid-plan.md`.
- The memory note on a new setting: every System Settings entry needs its
  row in `tests/fixtures/setup_payload_before_integrations.json`.

## What phase 3 builds

1. **The Course kind on Needs you** (TR6, § 5.3). `portal/needs.py` gains
   **Course** rows, "Course due: <name>", from the same due rule as the
   reminder (`courses/service.due`), across every application the member
   can open, never re-decided in the portal. A click opens the course page.
   The rows come after the mentoring and staff rows. Dismissing the reminder
   in an application, or completing the course, clears the row. With
   `TRAINING_COURSES` off, or `HOME_V2` off, nothing changes.
2. **Stop 3a.** Propose the report's grid (columns, the course picker, the
   answers view) with a picture, and put § 9's open question, a download of
   the grid, in the consequential-decision form. Wait for Doug's choice.
3. **The training report** (TR5, § 5.4): `/courses/report`, gated by the new
   setting `TRAINING_REPORT_ALLOWED_TEAMS` (default Mentor Administration
   Team; administrators always pass). A course picker, then one shared grid
   of people: name, teams, status (*Completed 1.2 on 11-28-26*, *Due
   again*, *In progress, 12 of 30*, *Dismissed*, *Not started*), and a
   button opening that person's checkpoint answers. Read only. The people
   are worked out by decision 10, never kept by hand; the training sign-ins
   are left out by name (the usernames in `TRAINING_SIGNINS`).
4. A Training report link where the report team will find it, to be
   proposed at stop 3a with the grid.
5. Tests, the full suite passing, a changelog entry and a version bump.

## Stop 3

Commit, then hand Doug a step-by-step page (the `instruction-discipline`
skill, built with `scripts/build_runbook.py`) for the check on the
Association: as Joe Mentor, the "Course due: Training reminder test" row on
the home page's Needs you, opening the course; then the report read as the
Mentor Admin login, showing Kitty Cat as *Dismissed* or *Due again* and Joe
Mentor's status, with a person's checkpoint answers opened. Keep each
course page and the report in a normal window and every training sign-in in
a private window. Wait for his result before closing the phase.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-21-26 22:33 | Claude (Claude Code) | Drafted at the close of phase 2 (stop 2 passed 11-21-26). |
