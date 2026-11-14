# Kickoff prompt — event hosting methods (Zoom Meetings, Zoom Webinars, other platforms)

Last Updated: 11-14-26 14:08 · Revision 0.1 (draft) — see change log at the end.

**Draft.** Doug approves this prompt before the session starts. Paste
everything below the line into a fresh Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake`.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). The plan names
stopping points; between them the work proceeds without asking. The first
reply states the operating mode and the `CLAUDE.md` files loaded, as the
global rule requires. Open every reply with the local time from `date`.

**One Events session at a time.** Check with Doug that no other session is
working in `events/` before you start.

Read, in full, before any work:

- **`prds/events/event-hosting-plan.md`** — the plan. **Rulings EH1 to EH10
  are settled**; do not re-open them. § 6 lists the open points to settle
  with Doug as you reach them. § 7 is the build order with its stopping points.
- `events/CLAUDE.md`, above all the confirmation (rulings D3-1 and D3-2), the
  outside host (D3-3, D3-4) and attendance; `OPEN-ITEMS.md` #80 (the
  `hostedBy` field, crm-test only).
- `core/zoom.py` (its integration contract at the top), `events/zoom_sync.py`,
  `events/attendance.py`, `events/confirm.py`, `events/visibility.py`,
  `events/config.py`, and `scripts/probe_zoom.py`.
- The memory note on the two Zoom worlds (mentoring sessions never use the
  chapter's Zoom account; ruling EH10).
- For the CRM change: the `espo-crm-changes` skill and
  `prds/chapter-network/crm-update-runbook.md`.

## Your part of the build

Plan § 7, **steps 1, 3, 4, 5 and 6**. **Step 2 — splitting the Zoom
integration on System Settings into Zoom Webinars and Zoom Meetings, with
their settings — is built by the Integrations tab build, in another session,
not here.** Steps 1 and 3 can run before it; **step 4 waits until step 2 is
committed** (read `git log` and `OPEN-ITEMS.md` #82 for it). If step 4 needs a
setting step 2 has not provided, stop and tell Doug rather than adding it
here.

1. **Probe Zoom Meetings.** Extend `scripts/probe_zoom.py` for meetings:
   read-only first, then — only with Doug's yes and on the chapter account he
   names — one test meeting with registration, one registrant, the
   registrant's join link, a past meeting's participant report, and the test
   meeting deleted. Doug runs anything that writes. **Stop**: report what Zoom
   actually does against plan § 3, and put § 6's points 4 and 5 to Doug.
3. **The CRM change** for the hosting method on `CEvent` (plan § 5): a handoff
   in Entity Manager vocabulary and a plan file for `scripts/apply_crm_plan.py`,
   applied to crm-test only, read back. **Stop.**
4. **Zoom Meetings in Events** and **Other platform's** registrations and
   confirmation, with § 6's points 1 to 3 settled first. **Stop.**
5. **The event form**: the method choice, the defaults per audience, the
   explanation line, the not-set-up reason, the capacity refusal, the overlap
   warning, and the platform named at publish. **Stop.**
6. **The live check on crm-test**, from a runbook page (the
   `instruction-discipline` skill), then production and the chapters at the
   Sunday slot. **Stop.**

Everything new is built dark, behind its own switch.

## Rules this session follows

- **Another session works in the same checkout and git index** (the
  Integrations tab build, and others). Commit with an explicit path list
  (`git commit -- <paths>`, after `git add` of new files only), never
  `git add -A` or a bare `git commit`; audit with `git show --stat`. Read
  `git log` for the current version (in `pyproject.toml` and `uv.lock`) and
  `uv run alembic heads` before choosing a version or a migration number.
- Run the full suite in a scratch worktree holding only this session's files.
- Commit; Doug reviews and pushes.
- Each stop ends with the review list and **What next**, as the Reply Format
  standard requires; every instruction to Doug follows the Step-by-Step
  Instructions standard.
- Doug's preference for any guided flow: one step or question at a time,
  never stacked lists (memory `wizard-not-lists`).

## Closing

At the end of each step: `CHANGELOG.md`, `OPEN-ITEMS.md` (a new item for
this build, linked to #80 and #82), the plan's change log, and `events/CLAUDE.md`
where a rule changes.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-14-26 14:08 | Claude (Claude Code) | Draft, written with the plan `prds/events/event-hosting-plan.md` revision 0.1. |
