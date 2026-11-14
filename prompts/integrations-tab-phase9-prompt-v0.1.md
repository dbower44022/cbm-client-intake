# Kickoff prompt — Integrations tab, phase 9: the other eight integrations' wizard screens

Last Updated: 11-14-26 01:40 · Revision 0.1 (draft) — see change log at the end.

**Draft.** Doug approves this prompt before the phase 9 session starts.
Paste everything below the line into a fresh Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake`.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This prompt names
three stopping points. Between them the work proceeds without asking.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires. Open every reply with the local time from
`date`.

Read, in full, before any work:

- `prompts/integrations-tab-build-orchestrator-v0.1.md`.
- `prds/integrations-tab-plan.md`, **§ 10**: rulings W1 to W6. Do not
  re-open them.
- `OPEN-ITEMS.md` item 82, `setup/CLAUDE.md`, `CHANGELOG.md` 0.331.0.
- **Zoom's 14 screens** in `prds/chapter-network/deployment-guide/steps/stage-05.yaml`
  (step 5.5's `wizard:` key) and `steps/README.md`'s `wizard` row: the
  pattern to follow. And `integrations/wizard.py`.
- Each integration's guide steps (`integration:` keys from phase 4) and its
  checks in `integrations/checks/`.
- Whatever the live Zoom pilot on crm-test (phase 8, stopping point 3) found.

## Scope of this phase

Screens for EspoCRM, Google Workspace, Fathom, Constant Contact, Lob, Twilio,
Anthropic and YouTube, in the same shape as Zoom's: the "Does this chapter
use …?" question first (none for EspoCRM, always in use), one screen per
action, a check on every screen the application can check, branches where a
chapter may already have the account. Where a phase 7 coded action exists
(the Google shared drive, the Twilio sender number), its screen runs it.
Any new check kind the screens need (for example, a Google directory user
exists) is added to `integrations/wizard.py` with its tests.

## Stopping point 1 — Google Workspace's screens

Google is the largest: put its screens to Doug first, in order, as he will
see them. Then stop.

## Stopping point 2 — the other seven

Put the other seven integrations' screens to Doug. Then stop.

## Stopping point 3 — built

Build the approved screens, with tests that each integration's screens load
and name only real checks and settings, and that the rendered guide is
unchanged. Close the phase as the orchestrator requires, and write the
phase 10 prompt (the removal, ruling W4) as a draft. Then stop.

## Things the build has learned

- **Another session works in the same checkout and git index.** Commit with
  an explicit path list (`git commit -- <paths>`, after `git add` of new
  files only); audit with `git show --stat`. Read `git log` for the version
  (in `pyproject.toml` and `uv.lock`) and `uv run alembic heads` before
  choosing either.
- Doug's review of 11-13-26: one list, never three; never ask to set a value
  the page already shows; one step or question at a time
  (memory `wizard-not-lists`).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-14-26 01:40 | Claude (Claude Code) | Draft written at the close of phase 8 (v0.331.0). |
