# Kickoff prompt — Integrations tab, phase 8: the wizard, piloted on Zoom

Last Updated: 11-14-26 00:11 · Revision 0.2 (draft) — see change log at the end.

**Draft.** Doug approves this prompt before the phase 8 session starts.
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

- `prompts/integrations-tab-build-orchestrator-v0.1.md`: the rules every
  phase session follows.
- `prds/integrations-tab-plan.md`, **§ 10 above all**: rulings W1 to W6
  (Doug, 11-13-26 and 11-14-26) and why they were made. They supersede I4, I7
  and I10 to I12. Do not re-open them.
- `OPEN-ITEMS.md` item 82, `setup/CLAUDE.md`, and `CHANGELOG.md` entries
  0.321.0 to 0.329.0.
- The deployment guide's step files and their README
  (`prds/chapter-network/deployment-guide/steps/`), Zoom's steps above all:
  5.5, 8.4, and the `integration:` and `check.auto:` keys phase 4 added.
- What phases 2 to 7 built that the wizard reuses: `integrations/testing.py`
  and `integrations/checks/zoom.py` (the checks), `integrations/checklist.py`
  (the step-file reading), `integrations/diagnosis.py` (the agent's tools and
  loop, for Ask Claude), `integrations/actions.py` (`zoom.confirm_host`), the
  checked save path in `setup/router.py` (`_checked_save`, `_checked_reset`).
- **The Step-by-Step Instructions standard** and the `instruction-discipline`
  skill: every wizard screen is a step to that standard — where, the one
  action, the value to copy, what you should see, what to do if not.

## Scope of this phase

1. **The step-file keys** for wizard screens: one screen per guide action
   (W3), each with what / why / how, its check where the application can make
   one, and questions with branches. The rendered guide must not change
   (`scripts/render_deployment_guide.py --check`, and the test that renders
   every stage with and without the keys).
2. **Zoom's screens, drafted** in the step files, from step 5.5's actions and
   the first question ("Does this chapter use Zoom?", W1, saving the "in use"
   setting).
3. **The wizard engine**: reads the screens; starts at the first screen whose
   check fails (W5) — every check passing means "set up", and it stops;
   one screen at a time; Back; Done for vendor-console actions; the check run
   before moving on; a setting entered on its screen saved through the checked
   save path; progress kept for the whole deployment (a table, with its
   Alembic migration and the shared engine).
4. **Ask Claude about this** on a failed screen (W6), reusing the agent's
   read-only tools; never automatic; against the monthly budget.
5. **The page**: a Wizard panel on the sub-tab, built **beside** the old
   sections (they go in phase 10), behind `INTEGRATIONS_TAB`.
6. **Tests.**

## Stopping point 1 — the design and Zoom's screens, before the engine

Put to Doug: the new step-file keys with one worked example; every Zoom screen
as drafted, in order, as Doug will see it (what / why / how / check / if not),
with its branches. Then stop.

## Stopping point 2 — the pilot built

Build items 1 to 6. Show the stubbed preview of the wizard on Zoom: the
first question, a vendor-console screen, a screen whose check fails with Ask
Claude, and the finished state. Close the phase as the orchestrator requires,
and write the phase 9 prompt as a draft. Then stop.

## Stopping point 3 — the live pilot

After Doug pushes, a runbook page for walking the Zoom wizard on crm-test.
Fix what it finds. Then stop.

## Things the build has learned

- **Another session works in the same checkout and git index.** Commit with
  an explicit path list (`git commit -- <paths>`, after `git add` of new
  files only), never `git add -A`; audit with `git show --stat`. Read
  `git log` for the current version (in `pyproject.toml` and `uv.lock`) and
  `uv run alembic heads` for the migration head before choosing either.
- The switch-off payload test compares every group of the Settings tab with
  a fixture; a setting that only matters with the tab on goes in
  `setup/service.TAB_ONLY_KEYS`.
- Doug's review of 11-13-26: **one list per question, never three**; a
  finished or discarded item shrinks to one line; never ask someone to set a
  value the page already shows.
- crm-test has the Integrations tab on and its Anthropic key set; it has no
  Zoom account (its Zoom credentials are empty).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.2 | 11-14-26 00:11 | Claude (Claude Code) | Rewritten for the wizard (plan § 10, rulings W1 to W6). Revision 0.1 (documentation and the live review) is superseded; that work is now phase 11. |
| 0.1 | 11-13-26 17:45 | Claude (Claude Code) | Draft: documentation and the live review on crm-test. |
