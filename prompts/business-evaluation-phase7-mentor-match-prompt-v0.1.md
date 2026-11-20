# Kickoff prompt — Business Evaluation, phase 7: the mentor match

Last Updated: 11-19-26 22:40 · Revision 0.2 — see change log at the end.

**Approved by Doug 11-19-26.** Written by the session that closed phase 6
(11-19-26), from plan revision 0.16 and what phase 6 actually built. Start a fresh Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake`, tell it to read this file, and tell
it to follow everything below the line.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This prompt names
two stopping points. Between them the work proceeds without asking.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires. Open every reply with the local time from
`date`.

**Other sessions work in this checkout at the same time** (the home page
build did throughout phase 6). Before choosing a version number, read
`git log`, the working tree's `pyproject.toml` and `uv.lock`, and take the
next free one; never take numbers from this prompt. Commit only this phase's
lines, staged and committed in one step, then audit with `git show --stat`.
Do not push; Doug pushes. **One session on this build at a time**: if a
second session's runbook or commit on the Business Evaluation appears, stop
and tell Doug (it happened in phase 6).

Read, in full, before any code:

- `prompts/business-evaluation-build-orchestrator-v0.1.md`: the rules every
  phase session follows. They bind this session.
- `prds/business-evaluation-plan.md`: § 3b use 2 and ruling **BE28**, which
  this phase builds, and BE17 (no report outside reviewers).
- `evaluation/CLAUDE.md`, "What phase 6 built", and `surveys/CLAUDE.md`.
- `assignments/CLAUDE.md`: Client Administration, the mentor roster and its
  capacity rules (client counts are app-computed from `CEngagement`, never
  the CRM's own fields).
- `evaluation/analysis.py`: the one Claude API pattern this build uses
  (`client.beta.messages.parse`, `scrub`, cost logging). Load the
  `claude-api` skill before writing any Claude API code.
- `OPEN-ITEMS.md` #83.

## What phase 6 left that this phase builds on

- The engagement popup in Client Administration has a **Business profile**
  tab (`evaluation/intake.business_profile_view`): the profile as data
  (`profile_sections`, `surveys.answers.answer_sections`) and the areas
  picked, area and status only, the areas read under the org-wide key after
  the staff member's own read of the engagement. Doug ruled (11-16-26) that
  answers must stand out from questions; the tab's look is v0.340.1.
- The mentor roster with app-computed capacity is
  `assignments.service.list_all_mentors` (Max Clients minus Active Clients;
  `industryExperience`, `areaOfExpertise`, `mentoringFocusAreas`,
  `industrySector` on `CMentorProfile`).

## Scope of this phase

Build, dark behind a new switch (default off) beside `INTAKE_SURVEY`:

1. **The AI analysis button (BE28)** on an engagement waiting for a mentor
   in Client Administration. Where it sits (on the Business profile tab is
   the natural place) is settled at stopping point (a).
2. **What is sent to the Claude API**: the business profile answers, the
   areas picked, the intake's mentoring focus areas and needs, and for each
   eligible mentor (Active, accepting new clients, with a login, the same
   rule as the Assign list) the profile fields named at stopping point (a),
   their active clients and maximum. **No contact details** (no names of the
   client's people, no email addresses, phone numbers or street addresses;
   `analysis.scrub` on every free-text value). Mentors are named, since the
   result names them.
3. **The matching prompt as a versioned file** (BE9), with structured output:
   the client's needs, the kind of mentor that would suit, and a few named
   mentors, each with a reason. **Advice only**: no button in the result
   assigns.
4. **The result panel**, read-only, with when it was run and by whom. Whether
   a result is kept (application database) or made fresh each time is
   settled at stopping point (a).
5. **Recorded in the action log** (`core/action_log.py`): who ran it, on
   which engagement, the cost.
6. **Tests**: the switch off (no button, the route answers 404); no contact
   details in the request sent (a test reads it); an ineligible mentor never
   sent; a mentor at capacity marked as such; a refused or failed call shown
   as a message, never a 500; the result never offers an Assign action.
7. **`OPEN-ITEMS.md` #83** updated.

**Stopping point (a).** Before building, show Doug: the mentor profile fields
sent; the prompt's text; the result panel and where the button sits; whether
a result is kept. One decision at a time, with a recommendation.

After Doug's go-ahead, build steps 1 to 7.

**Stopping point (b)**: sample matches from made-up clients against the
Association's mentors, reviewed by Doug, then his check on the Business
Mentors Association's system as Kitty Cat (a real non-admin). The Association
has few mentors; settle at stopping point (a) whether that is enough to judge
the prompt. Close the phase only after Doug's review.

## Not in this phase

Mentors' past engagements as input (BE28 leaves them for later); feedback
surveys (phases 8 and 9); the partner offering (phase 10).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-19-26 22:35 | Claude (Claude Code) | Drafted at the close of phase 6, from plan revision 0.16. |
| 0.2 | 11-19-26 22:40 | Claude (Claude Code) | Approved by Doug. |
