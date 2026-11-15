# Kickoff prompt — Integrations tab, phase 10: the removal (ruling W4)

Last Updated: 11-15-26 11:47 · Revision 0.2 (approved) — see change log at the end.

**Approved by Doug 11-15-26.** Paste everything below the line into a fresh
Claude Code session rooted in `~/Dropbox/Projects/cbm-client-intake`.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This prompt names
three stopping points. Between them the work proceeds without asking.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires. Open every reply with the local time from
`date`.

Read, in full, before any work:

- `prompts/integrations-tab-build-orchestrator-v0.1.md` (the rules for every
  phase session, and how a phase is closed).
- `prds/integrations-tab-plan.md`, **§ 10**: rulings W1 to W6. **Ruling W4
  is this phase**: the wizard replaces the setup checklist's display with its
  hand ticks, the setup assistant and its setup plans, and the diagnosis's
  fix plans with Approve and apply. Doug approved the removal on 11-13-26
  under the global rule on removing functionality. Do not re-open it.
- `setup/CLAUDE.md`, `OPEN-ITEMS.md` item 82, `CHANGELOG.md` 0.331.0 to
  0.334.0.
- `integrations/wizard.py`, `integrations/checklist.py`,
  `integrations/ticks.py`, `integrations/fixplans.py`,
  `integrations/diagnosis.py`, `integrations/actions.py`, and the wizard,
  checklist, fix-plan and setup-plan parts of `setup/router.py`,
  `setup/service.py` and `setup/frontend/app.js`.

## What is removed

- **The setup checklist's display** on each sub-tab, its hand ticks and their
  endpoint, and the `integration_checklist_tick` table.
- **The setup assistant** (Set up with Claude) and its **setup plans**.
- **The diagnosis's fix plans** with Approve and apply: their endpoints, the
  runner that carries them out (`_carry_out`, `_execute_step`), and the
  `integration_fix_plan` table.
- Their tests, and every mention on the page.

## What stays, underneath (W4)

- The integration tests and their checks: they are the wizard's checks.
- The agent's read-only tools and its loop: they answer Ask Claude on a
  failed screen. Check what `diagnosis.py` still needs once fix plans are
  gone, and keep only that.
- The coded actions (`integrations/actions.py`): the wizard's button screens
  run them.
- The nightly test and its alert.
- **`integrations/checklist.py`'s reading of the step files.** The
  `integration:` and `check.auto:` keys are still read: the readiness counts
  and the "Used by" lists may depend on them. Find every reader before
  removing a function. Remove a key from the step files only if nothing
  reads it, and say so at stopping point 1.
- The monthly budget, which then counts Ask Claude alone. This month's
  diagnosis costs sit in the fix-plan table that the migration drops, so the
  budget would forget them. Say at stopping point 1 how that month is
  handled.

## What is added

- **Fix with the wizard** (W4): a failed integration test, on the sub-tab and
  in the nightly alert's link, offers to open the wizard. The wizard then
  starts at the first failing screen (W5).

## Stopping point 1 — the removal list

Put to Doug the exact list: each function, endpoint, page part, table and
test to be removed; each one kept and why; the migration (number, what it
drops, the downgrade); and what the page shows in place of each removed part.
Then stop.

## Stopping point 2 — built

Remove what Doug approved, with the migration, behind the same switch
(`INTEGRATIONS_TAB`): while it is off, System Settings behaves exactly as
before, and a test proves it. All tests pass. Commit on its own version.
Then stop.

## Stopping point 3 — closed

Close the phase as the orchestrator requires, and write the phase 11 prompt
(documentation, and the live review on the Business Mentors Association's
system, the test system since 11-14-26, `OPEN-ITEMS.md` #85) as a draft.
Then stop.

## Things the build has learned

- **Another session works in the same checkout and git index.** Commit with
  an explicit path list (`git commit -- <paths>`, after `git add` of new
  files only); audit with `git show --stat`. Read `git log` for the version
  (in `pyproject.toml` and `uv.lock`) and `uv run alembic heads` before
  choosing either.
- **The test system is the Business Mentors Association's**, not crm-test,
  since 11-14-26 (`OPEN-ITEMS.md` #85).
- **Phase 9 left these unproved against a vendor** (all built with fakes):
  every wizard screen, the Google `grant` line, the Zoom Meetings test, both
  button screens, and the Connect screen's return. Phase 11's live review
  walks them.
- Doug's review of 11-13-26: one list, never three; never ask to set a value
  the page already shows; one step or question at a time (memory
  `wizard-not-lists`).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.2 | 11-15-26 11:47 | Claude (Claude Code) | Approved by Doug. |
| 0.1 | 11-15-26 11:23 | Claude (Claude Code) | Draft written at the close of phase 9 (v0.334.0). |
