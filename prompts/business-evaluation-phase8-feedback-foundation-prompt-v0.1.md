# Kickoff prompt — Business Evaluation, phase 8: feedback surveys, the foundation

Last Updated: 11-20-26 01:10 · Revision 0.2 — see change log at the end.

**Approved by Doug 11-20-26.** Written by the session that closed phase 7
(11-20-26), from plan revision 0.18 and what phases 6 and 7 actually built.
Start a fresh Claude Code session rooted in
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
build did throughout phases 6 and 7, and took v0.350.1 between two phase 7
commits). Before choosing a version number, read `git log`, the working
tree's `pyproject.toml` and `uv.lock`, and take the next free one; never
take numbers from this prompt. Commit only this phase's lines, staged and
committed in one step, then audit with `git show --stat`. Do not push; Doug
pushes. **One session on this build at a time**: if a second session's
runbook or commit on the Business Evaluation appears, stop and tell Doug.

Read, in full, before any code:

- `prompts/business-evaluation-build-orchestrator-v0.1.md`: the rules every
  phase session follows. They bind this session.
- `prds/business-evaluation-plan.md`: § 3b use 3, § 5 *Added 11-16-26*
  (the `CSurveyResponse` entity and the application tables), and rulings
  **BE29, BE31, BE32 and BE33**, which this phase builds. BE30 (the
  automatic moments) is phase 9.
- `surveys/CLAUDE.md`, especially *Adding a survey purpose*: feedback is the
  second survey purpose, in a package of its own (`feedback/`), and
  `surveys/` must not import it (a test checks).
- `evaluation/CLAUDE.md`: how Business Evaluation registers as a purpose,
  makes links, writes the CRM on submit and retries.
- The `espo-crm-changes` skill, before writing the CRM plan.
- `sessions/CLAUDE.md`: the on-demand send and the mentor's view live in
  Client Management.
- `OPEN-ITEMS.md` #83.

## What phases 6 and 7 left that this phase builds on

- **The survey engine** serves two kinds of link already (a mentor's and an
  intake link), with per-link page words (`page_for`) and an offer of more
  surveys. Question types today: the choice types, `long_text`, `scale`
  (1 to 5) and `yes_no`, in `surveys/definitions.py`.
- **Sending from the shared mailbox** (`evaluation/intake.py`, `_send_shared`)
  and **from the mentor's own mailbox through the composer**
  (`evaluation/sending.py`, Send Evaluation) both exist; reuse one, do not
  write a third.
- **The CRM plan pattern**: `crm-plans/*.json`, `scripts/apply_crm_plan.py`
  with a fingerprint, a role script, a handoff file; on the Association with
  `scripts/evaluation_bma.sh`.
- **Tests run on the Business Mentors Association's system**, not crm-test.

## Scope of this phase

Build, dark behind a new switch (default off) beside the others:

1. **The `feedback` survey purpose** (BE29) in `feedback/`, registered as
   `surveys/CLAUDE.md` describes, with its own definitions folder.
2. **The 0-to-10 question type** in the survey engine, with its page
   control, its check, and its readable text. Built in `surveys/`, usable by
   any purpose.
3. **The survey drafts** as versioned files: mentoring feedback, event
   feedback and evaluation feedback. Each has the recommendation score and a
   few yes/no and short text questions. Every question carries a `# For:`
   comment, as Business Evaluation's do.
4. **The Survey Response CRM plan** (BE31, plan § 5): `CSurveyResponse` and
   its role grants. A mentor reads the responses about their own
   engagements; staff read all. Event feedback is staff only. Applied to the
   Association's CRM, with a handoff file for production and Boston.
5. **Submit writes a Survey Response record** with the score, readable
   answers, JSON, the moment, and links to the engagement, its mentor at the
   time, or the event, and the contact. It is stamped with the engagement's
   `assignedUsers`, and the nightly reconciliation includes it.
6. **The on-demand send** (BE30's on-demand half): a mentor sends the
   mentoring feedback survey on one of their own engagements, and staff send
   any of them.
7. **The mentor's view** of the responses about their own work, on the
   engagement in Client Management.
8. **The low score** (BE32): a score of 6 or below sets `needsFollowUp` and
   alerts staff at once. Mentoring feedback goes to the Mentor
   Administration Team, event feedback to the Marketing Admin Team. Staff
   mark the follow-up done, with a note.
9. **The quiet period** (BE33): a setting, default 30 days (0 turns it off),
   counted per email address across every kind of feedback survey. It skips
   only automatic sends, and logs each skip. The table it needs is settled
   at stopping point (a). This phase builds the check; phase 9's sweep
   calls it.
10. **Tests**: the switch off (every page as before; the routes answer 404);
    the 0-to-10 type's checks; a low score sets the flag and alerts once;
    the quiet period skips an automatic send and never an on-demand one; a
    mentor never reads another mentor's responses; `surveys/` imports
    nothing from `feedback/`.
11. **`OPEN-ITEMS.md` #83** updated.

**Stopping point (a).** Before building, show Doug, one decision at a time,
each with a recommendation:

- the CRM plan: the entity, fields, links and role grants;
- the three survey drafts, question by question;
- where the on-demand send and the mentor's view sit, and who sends;
- how the low-score alert reaches staff (email to the team's members, the
  Needs you list on the new home page, or both), and where staff mark the
  follow-up done;
- the quiet period's table.

After Doug's go-ahead, build steps 1 to 11.

**Stopping point (b)**: Doug's check on the Business Mentors Association's
system. The CRM plan is applied there; the switch is on at its `/setup`.
The check sends a mentoring feedback survey on demand as Joe Mentor, has the
client answer it with a low score, and has a staff member (Kitty Cat or a
Mentor Administration Team member) see the alert and mark the follow-up
done. Close the phase only after Doug's review.

## Not in this phase

The automatic moments and their sweep, and the Analytics panels: phase 9.
The partner offering: phase 10. A staff survey builder: later (BE29).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-20-26 00:59 | Claude (Claude Code) | Drafted at the close of phase 7, from plan revision 0.18. |
| 0.2 | 11-20-26 01:10 | Claude (Claude Code) | Approved by Doug. |
