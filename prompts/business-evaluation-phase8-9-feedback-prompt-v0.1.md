# Kickoff prompt — Business Evaluation, phases 8 and 9: feedback surveys

Last Updated: 11-20-26 01:27 · Revision 0.2 — see change log at the end.

**Approved by Doug 11-20-26.** Doug's choice B, 11-20-26: phases 8 and 9
run as **one session**. Every decision for both phases is put to him first,
then both are built without stopping, then one combined check is made on the
Association's system. This prompt replaces the approved phase 8 prompt
(`prompts/business-evaluation-phase8-feedback-foundation-prompt-v0.1.md`,
revision 0.2, now superseded). Written from plan revision 0.18 and what
phases 6 and 7 actually built. Start a fresh Claude Code
session rooted in `~/Dropbox/Projects/cbm-client-intake`, tell it to read
this file, and tell it to follow everything below the line.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This prompt names
two stopping points. Between them the work proceeds without asking.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires. Open every reply with the local time from
`date`.

**Other sessions work in this checkout at the same time** (the home page
build did throughout phases 6 and 7, and committed a file this session had
edited but not yet staged). Before choosing a version number, read
`git log`, the working tree's `pyproject.toml` and `uv.lock`, and take the
next free one; never take numbers from this prompt. **Stage only this
work's lines**: where another session has uncommitted changes in a file you
also edited (`CLAUDE.md`, `OPEN-ITEMS.md`, `CHANGELOG.md`), commit only your
own hunks and leave theirs in the working tree. Commit in one step, then
audit with `git show --stat` and `git show`. Do not push; Doug pushes.
**One session on this build at a time**: if a second session's runbook or
commit on the Business Evaluation appears, stop and tell Doug.

Read, in full, before any code:

- `prompts/business-evaluation-build-orchestrator-v0.1.md`: the rules every
  phase session follows. They bind this session, with the one exception
  above (two phases, one session).
- `prds/business-evaluation-plan.md`: § 3b use 3, § 5 *Added 11-16-26*
  (the `CSurveyResponse` entity and the application tables), and rulings
  **BE29 to BE33**, which this session builds.
- `surveys/CLAUDE.md`, especially *Adding a survey purpose*: feedback is the
  second survey purpose, in a package of its own (`feedback/`), and
  `surveys/` must not import it (a test checks).
- `evaluation/CLAUDE.md`: how Business Evaluation registers as a purpose,
  makes links, writes the CRM on submit and retries; phase 5's release (one
  of the automatic moments).
- `sessions/CLAUDE.md`: the on-demand send and the mentor's view live in
  Client Management; a Completed session is one of the moments.
- `events/CLAUDE.md`: registrations and attendance, for the event moment.
- `analytics-guide.md` and `prds/analytics-app-plan.md`: the metric library,
  built-in pages and panels, for the starter panels.
- The `espo-crm-changes` skill, before writing the CRM plan.
- `OPEN-ITEMS.md` #83.

## What phases 6 and 7 left that this work builds on

- **The survey engine** serves two kinds of link already (a mentor's and an
  intake link), with per-link page words (`page_for`) and an offer of more
  surveys. Question types today: the choice types, `long_text`, `scale`
  (1 to 5) and `yes_no`, in `surveys/definitions.py`.
- **Sending from the shared mailbox** (`evaluation/intake.py`, `_send_shared`)
  and **from the mentor's own mailbox through the composer**
  (`evaluation/sending.py`, Send Evaluation) both exist; reuse them, do not
  write a third.
- **A worker step that runs after an event and never fails its caller**:
  `evaluation/intake.on_delivered` is the pattern for a best-effort send.
- **The CRM plan pattern**: `crm-plans/*.json`, `scripts/apply_crm_plan.py`
  with a fingerprint, a role script, a handoff file; on the Association with
  `scripts/evaluation_bma.sh`. Commands that change the Association's CRM
  are Doug's to run; give him the steps.
- **Tests run on the Business Mentors Association's system**, not crm-test.

## Scope

Build, dark: a new switch for feedback surveys (default off) beside the
others, and one switch per automatic moment (BE30), each default off.

**Phase 8, the foundation (BE29, BE31 to BE33):**

1. **The `feedback` survey purpose** in `feedback/`, registered as
   `surveys/CLAUDE.md` describes, with its own definitions folder.
2. **The 0-to-10 question type** in the survey engine, with its page
   control, its check and its readable text. Built in `surveys/`, usable by
   any purpose.
3. **The survey drafts** as versioned files: mentoring feedback, event
   feedback and evaluation feedback. Each has the recommendation score and a
   few yes/no and short text questions. Every question carries a `# For:`
   comment, as Business Evaluation's do.
4. **The Survey Response CRM plan** (BE31, plan § 5): `CSurveyResponse` and
   its role grants. A mentor reads the responses about their own
   engagements; staff read all. Event feedback is staff only. A handoff file
   for production and Boston.
5. **Submit writes a Survey Response record** with the score, readable
   answers, JSON, the moment, and links to the engagement, its mentor at the
   time, or the event, and the contact. It is stamped with the engagement's
   `assignedUsers`, and the nightly reconciliation includes it.
6. **The on-demand send**: a mentor sends the mentoring feedback survey on
   one of their own engagements, and staff send any of them.
7. **The mentor's view** of the responses about their own work, on the
   engagement in Client Management.
8. **The low score** (BE32): a score of 6 or below sets `needsFollowUp` and
   alerts staff at once. Mentoring feedback goes to the Mentor
   Administration Team, event feedback to the Marketing Admin Team. Staff
   mark the follow-up done, with a note.
9. **The quiet period** (BE33): a setting, default 30 days (0 turns it off),
   counted per email address across every kind of feedback survey. It skips
   only automatic sends, and logs each skip. The engagement-closing survey
   always goes.

**Phase 9, the moments and Analytics (BE30):**

10. **The worker sweep** that finds the four automatic moments, so a change
    made in the CRM directly is caught too:
    - an engagement closes;
    - its third session is logged as Completed;
    - an event or webinar ends (to registrants marked Attended);
    - a Business Evaluation report is released.

    Each moment has its own switch. The sweep never sends twice for one
    moment (the table is settled at stopping point (a)), calls the quiet
    period, and never fails the worker.
11. **Starter Analytics panels**: the recommendation score by mentor, by
    event and over time, built from Survey Response records, with their
    visibility set so a mentor never sees another mentor's figures.

**For both:**

12. **Tests**: the switches off (every page as before; the routes answer
    404; the sweep sends nothing); the 0-to-10 type's checks; a low score
    sets the flag and alerts once; the quiet period skips an automatic send
    and never an on-demand or closing one; each moment sends once and only
    once, and not at all with its switch off; a mentor never reads another
    mentor's responses or figures; `surveys/` imports nothing from
    `feedback/`.
13. **Closing**: version, `CHANGELOG.md`, `OPEN-ITEMS.md` #83, the plan's
    change log, the orchestrator's State column for phases 8 and 9, and
    phase 10's prompt left on hold (it is rewritten when Doug lifts the
    hold).

## Stopping point (a): every decision, before any code

Put each decision to Doug **one at a time**, each with a recommendation and
its cost, in this order. Record each answer before asking the next.

1. The CRM plan: the entity, fields, links and role grants.
2. The three survey drafts, question by question.
3. Where the on-demand send and the mentor's view sit, and who sends.
4. How the low-score alert reaches staff (email to the team's members, the
   Needs you list on the new home page, or both), and where staff mark the
   follow-up done.
5. The quiet period and the sweep's sent-moments record: tables in the
   `feedback` package, or the survey engine's link store.
6. Each automatic moment's exact trigger: which status means "closes", what
   counts as the third session, when an event has "ended", and how far back
   the sweep looks the first time it is switched on (so switching it on does
   not survey every client ever closed).
7. Who each automatic survey is sent to, and from which mailbox.
8. The starter Analytics panels: which metrics, on which pages, visible to
   whom.

After the last answer, state in a few lines everything decided and build
steps 1 to 13 **without stopping**. A finding during the build that changes
what a client, mentor or staff member sees goes to Doug at once; everything
else is decided and noted for the closing review.

## Stopping point (b): one combined check

When both phases are built and every test passes, write one runbook page
for Doug's check on the Business Mentors Association's system, following
the Step-by-Step Instructions standard. It covers: applying the CRM plan
(Doug runs the commands), the switches at `/setup`, an on-demand mentoring
survey sent as Joe Mentor and answered with a low score, a staff member (a
real non-admin) seeing the alert and marking the follow-up done, each
automatic moment triggered once on a test record, the quiet period skipping
a second automatic send, and the starter panels in Analytics. Close both
phases only after Doug's review.

## Not in this work

The partner offering: phase 10, on hold. A staff survey builder: later
(BE29).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-20-26 01:16 | Claude (Claude Code) | Drafted on Doug's choice B (11-20-26): phases 8 and 9 in one session, all decisions first, one combined check. Replaces the phase 8 prompt, revision 0.2. |
| 0.2 | 11-20-26 01:27 | Claude (Claude Code) | Approved by Doug. |
