# Kickoff prompt — Business Evaluation, phase 2: the mentor side

Last Updated: 11-13-26 11:52 · Revision 0.2 — see change log at the end.

**Draft for Doug's approval.** Written at the close of phase 1 (v0.324.0) from
the build orchestrator's rules and what phase 1 actually built. Paste
everything below the line into a fresh Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake`, after Doug approves it.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This prompt names
two stopping points. Between them the work proceeds without asking.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires. Open every reply with the local time from
`date`.

**Another session may be working in this checkout at the same time** (the
Integrations tab build did, through phase 1). Before choosing a version number
or an Alembic migration number, read `git log` and `alembic/versions/` and take
the next free one; never take numbers from this prompt. Commit only this
phase's lines, staged and committed in one step, then audit with
`git show --stat`.

Read, in full, before any code:

- `prompts/business-evaluation-build-orchestrator-v0.1.md`: the rules every
  phase session follows. They bind this session.
- `prds/business-evaluation-plan.md`: the plan. **Its approved rulings are
  settled; do not re-open them.** This phase builds § 3 step 2 and the
  mentor's view of steps 1 and 3, and rulings BE3, BE5, BE10, BE12 (resend),
  BE14 (Declined, Expired) and BE18.
- `evaluation/CLAUDE.md`: what phase 1 built, and its rules.
- `OPEN-ITEMS.md` #83: what is owed.
- `sessions/CLAUDE.md`, `sessions/config.py` (`DomainConfig`, the `MENTOR`
  domain), `sessions/service.py` and `sessions/router.py`: how a tab is added
  to Client Management, gated by a `DomainConfig` field that controls both the
  tab and its endpoints. Client Management only: never Partner or Funder
  Management.
- The shared composer `frontend/shared/compose.js`, `comms/service.py`
  (`sender_mailbox`) and `comms/crm.user_mailbox`: mentor-to-client mail goes
  from the mentor's own mailbox.
- `core/action_log.py` and `core/history.py`: every mutating staff action is
  recorded, with old and new values (ruling Q5.4).
- `scripts/evaluation_make_link.py` and `evaluation/store.py`: the link-making
  logic this phase moves behind the Send Evaluation button.

## Scope of this phase

Build the mentor side, dark behind the same switch, `BUSINESS_EVALUATION`:

1. **The Mentor Role's grant on `CBusinessEvaluation`**: read and edit at the
   level that reaches records carrying the mentor in `assignedUsers` (the
   level the Mentor Role holds on `CEngagement`; read it from crm-test, do not
   assume it). Extend `scripts/migrate_evaluation_roles.py`, apply it on
   crm-test, read it back, and add it to `business-evaluation-crm-handoff.md`.
2. **The Evaluations tab** on an engagement in Client Management, behind a new
   `DomainConfig` field set on the mentor domain only. One row per Business
   Evaluation record, grouped by round: the area, the status, sent and
   submitted dates. A row opens the client's answers (`answersReadable`, and
   the business profile from the client profile), read-only. The tab is
   feature-detected: a CRM without the entity shows the tab saying it is not
   available, with the reason.
3. **Send Evaluation**, a button on the tab: a dialog to pick the areas, from
   the area surveys that exist (Finance and Marketing in the pilot, ruling
   BE22). It advises two or three per round and warns above three, and still
   sends (BE10; the button is never disabled). Sending creates the records
   (status Sent, the engagement's `assignedUsers`, the next round), makes the
   link, and opens the email (step 4). The logic moves out of
   `scripts/evaluation_make_link.py` into one service both use.
4. **The email**: the shared composer, opened from the mentor's own mailbox,
   to the engagement's primary contact, with the wording filled in and the
   link in it. The mentor can edit it before sending. The link reaches the
   email only through this path.
5. **Resend and Expire**: Resend issues a new link and ends the old one
   (`replaced_at`, ruling BE12) and opens the email again. Expire ends the link
   and sets the round's open records to Expired. **Record a decline**: sets
   Declined on records not yet submitted (BE14). Each is recorded through
   `core/action_log.py` with old and new values.
6. **Tests**: the tab and its gate, the grant feature detection, Send (records,
   link, round number, the warning above three), Resend ending the old link,
   Expire, Declined, the action log entries, the switch off.
7. **`OPEN-ITEMS.md` #83** updated.

**Stopping point (a).** Before building the email (step 4), stop and put to
Doug: the Send dialog's wording, and the email's subject and body, written
out in full. These are what a client receives, so they are Doug's decision.
Also put whether the email wording lives in the CRM as an email template (staff
can edit it without a release) or in this repository (versioned with the
surveys), with a recommendation.

After Doug's go-ahead, build steps 4 to 7.

**Stopping point (b).** Run the application locally against crm-test with the
switch on, sign in as a real non-admin mentor (Joe Mentor; administrators
bypass ACL), and give Doug runbook steps to send an evaluation to a training
client, read the email, open the link, and see the status change on the tab.
Close the phase only after Doug's report.

## Not in this phase

Anything that calls the Claude API (phase 3), the report editor and approval
(phase 4), release to the client and action items (phase 5), the partner
offering (phase 6).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-13-26 10:50 | Claude (Claude Code) | Drafted at the close of phase 1, from the orchestrator and what phase 1 built. |
| 0.2 | 11-13-26 11:52 | Claude (Claude Code) | Added: read `git log` and `alembic/versions/` before choosing a version or migration number, because another session may work in parallel. |
