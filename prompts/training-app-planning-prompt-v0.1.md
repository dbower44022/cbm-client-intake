# Kickoff prompt — the training application: planning

Last Updated: 11-21-26 11:10 · Revision 0.1 — see change log at the end.

**Written 11-21-26 at Doug's request (his choice A: plan first, build
later).** Start a fresh Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake`, tell it to read this file, and tell
it to follow everything below the line.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This is a planning
session: **no application code is written**. Its products are documents.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires. Open every reply with the local time from
`date`.

**Other sessions work in this checkout.** Commit only this session's files,
staged and committed in one step, then audit with `git show --stat`. Where
another session has uncommitted changes in a file you also edit
(`CLAUDE.md`, `OPEN-ITEMS.md`), commit only your own lines. Do not push;
Doug pushes.

## Why this session exists

On 11-21-26 a staff training demo for the Business Evaluation was written
as Markdown (`training/evaluation-staff-course/evaluation-demo.md`) and
turned into a step-by-step page by `scripts/build_runbook.py`, published as
a Claude page. Doug asked whether that is the right way to reach many users,
and proposed instead a **training application inside our application**:

> "Should we create a training app in our application that contains a
> number of these training runs and we capture which users have completed
> each training including version numbers so we could make an update
> training available to the users when a new release is published?"

The Claude page lives outside our system, knows nobody, records nothing
centrally and needs a session to update. A training application would serve
the courses behind our own sign-in, record completion per person and per
course revision, and flag a changed course as due again. **What exactly it
does is Doug's to say**: this session does not guess it.

## Read first, before the first question

- `training/CLAUDE.md`: what a course is, one folder per course, the
  audiences and their teams, the step-by-step standard, the publish path.
  (Its sandbox section still names crm-test; since 11-14-26 the test and
  training system is the Business Mentors Association's, whose CRM restores
  only on demand. See the root `CLAUDE.md`, Deployment.)
- `training/evaluation-staff-course/evaluation-demo.md` and
  `scripts/build_runbook.py`: the first course in the new shape, and the
  script that renders it. The application would serve the same Markdown.
- `training/training-guide.md` and `training/demo-records.md`: the older
  sandbox training material.
- The root `CLAUDE.md`, the sections on the portal and the home page (team
  gates, Needs you, the shared panel standard), the conventions (`busy.js`,
  the shared grid, `{{org}}`, buttons never disabled, the action log) and
  the System Settings section (feature switches).
- `prds/home-page-plan.md`: Needs you, where "a course is due" might show.

Read these quietly. Do not summarise them back to Doug.

## How the session runs

1. **Elicit first.** Ask Doug what he wants, one question at a time, in
   plain prose, with a worked example from real project content. These are
   the questions known so far; others will come up:
   1. What counts as **completed**: every step ticked, the checkpoints
      confirmed, a short quiz at the end, or a trainer signing off?
   2. Who is **assigned** which course: by team, by hand, or both? Is a
      course required or optional?
   3. What makes a course **due again**: any new course revision, or only
      one marked as a significant change? How does that relate to an
      application release?
   4. Who sees **completion**: the trainee, the trainer, team leads,
      administrators? Does "a course is due" show on the home page's Needs
      you list?
   5. Where the **demo data** comes from: a fresh client per run (as the
      evaluation demo does), or seed records per course on the training
      system?
   6. Which **chapters** get which courses, and whether a chapter can add
      its own.
   7. Whether the training runs on the **live system** with real
      permissions, or only on the training system, and how a trainee
      reaches the training system's logins.
2. **Then propose the design**: the courses as files in the repository (one
   folder each, versioned by their revision line), the application's pages,
   the completion record (application database or CRM, and why), the
   switches, and what reuses existing parts (the home page, the shared grid,
   the action log, `build_runbook.py`).
3. **Decisions go to Doug one at a time**, in the consequential decision
   template of `~/.claude/CLAUDE.md`, each with a recommendation and its
   cost. Record each answer before asking the next.
4. **Write the plan**: `prds/training-app-plan.md`, with revision control,
   terms, the rulings from Doug's answers (numbered TR1 onward), the data
   model, the phases with their stopping points, and open questions. Add an
   open item to `OPEN-ITEMS.md` pointing at it.
5. **Close** with a review list and the first build phase's prompt as a
   draft, revision 0.1, for Doug to approve.

## Not in this session

Any application code. Moving the evaluation demo into the application
(that is a build phase). Publishing anything to the documentation site.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-21-26 11:10 | Claude (Claude Code) | Drafted on Doug's choice A (11-21-26): plan the training application first. |
