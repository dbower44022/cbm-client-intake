# Kickoff prompt — Business Evaluation, phase 6: the intake survey

Last Updated: 11-16-26 11:59 · Revision 0.1 — see change log at the end.

**Draft, awaiting Doug's approval.** Written by the planning session on wider
uses (11-16-26), from plan revision 0.14. Start a fresh Claude Code session
rooted in `~/Dropbox/Projects/cbm-client-intake`, tell it to read this file,
and tell it to follow everything below the line.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This prompt names
two stopping points. Between them the work proceeds without asking.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires. Open every reply with the local time from
`date`.

**Another session may be working in this checkout at the same time.** Before
choosing a version number or an Alembic migration number, read `git log`,
the working tree's `pyproject.toml` and `alembic/versions/`, and take the
next free one; never take numbers from this prompt. Commit only this
phase's lines, staged and committed in one step, then audit with
`git show --stat`. Do not push; Doug pushes.

Read, in full, before any code:

- `prompts/business-evaluation-build-orchestrator-v0.1.md`: the rules every
  phase session follows. They bind this session.
- `prds/business-evaluation-plan.md`: the plan, § 3b and rulings **BE24 to
  BE27**, which this phase builds.
- `evaluation/CLAUDE.md` and `surveys/CLAUDE.md`: what phases 1 to 5 built.
- `assignments/CLAUDE.md`: Client Administration, and Assign's re-homing.
- The root `CLAUDE.md`, "The five public intake forms", and
  `forms/client_intake/orchestrator.py` (`submit_intake`).
- `OPEN-ITEMS.md` #83.

## Scope of this phase

Build, dark behind a new switch (default off) beside `BUSINESS_EVALUATION`:

1. **The intake survey (BE24).** Once a client intake is delivered, make an
   evaluation link for the new engagement that opens the business profile
   survey only, and email it from `OPS_MAILBOX`. Best-effort: a failure is
   logged and never fails the intake, and a re-driven delivery never sends a
   second link. Today `sending.send` refuses a send with no area
   (`choose_areas`); this phase needs a profile-only link, without weakening
   the mentor's Send dialog.
2. **"Do you have time to provide more details?" and the area picker
   (BE25)**, on the survey page after the business profile. A yes lists the
   areas that have a survey, with the two-or-three advice; ticking areas
   creates one Business Evaluation record each, round 1, under the
   org-wide key, and adds them to the same link. A no ends the survey. The
   page belongs to the evaluation purpose; the survey engine gains only a
   general hook, never Business Evaluation code (BE23).
3. **Client Administration (BE26)**: on an engagement waiting for a mentor,
   the business profile answers and the areas picked, readable by the
   Client Administration Team. Never a draft report.
4. **Assign moves the evaluation records (BE26)**: their `assignedUsers`
   re-homed with the rest of the engagement.
5. **Analyze before assignment (BE27)**: a System Settings switch, default
   off. Off: the analysis pass skips a Submitted record whose engagement has
   no mentor, and assigning a mentor lets it run. On or off, the draft-ready
   email goes to the mentor once one is assigned.
6. **Every staff action recorded** through `core/action_log.py`, if this
   phase adds any.
7. **Tests**: the switch off (intake unchanged, no email); the link made once
   per engagement; a failed send never fails the intake; yes and no on the
   picker; the records created; Client Administration never sees the draft;
   the analysis held while unassigned when the setting is off; Assign
   re-homing the records.
8. **`OPEN-ITEMS.md` #83** updated.

**Stopping point (a).** Before building, show Doug: the intake survey
email's wording; the "more details?" screen and the area picker; the Client
Administration panel; any grant the Client Administration Team needs to read
the business profile answers (a CRM change goes through a plan in
`crm-plans/` with a handoff file). One decision at a time, with a
recommendation.

After Doug's go-ahead, build steps 1 to 8.

**Stopping point (b)**: Doug runs a runbook on **the Business Mentors
Association's system**. He submits a client intake, receives the email at
an address he owns (the Association's sandbox address domain may block
delivery; settle how before writing the runbook), answers the business
profile, says yes, picks an area, and submits. As a Client Administration
user he sees the answers and the pick, then assigns a mentor; as that mentor
he sees the records on the Evaluations tab. Close the phase only after
Doug's check.

## Not in this phase

The mentor match (phase 7), feedback surveys (phases 8 and 9), the partner
offering and co-branding (phase 10).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-16-26 11:59 | Claude (Claude Code) | Drafted by the planning session on wider uses, from plan revision 0.14. |
