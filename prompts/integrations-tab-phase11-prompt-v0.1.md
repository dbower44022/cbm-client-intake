# Kickoff prompt — Integrations tab, phase 11: documentation and the live review

Last Updated: 11-15-26 12:44 · Revision 0.2 (approved) — see change log at the end.

**Approved by Doug 11-15-26.** Paste everything below the line into a fresh
Claude Code session rooted in `~/Dropbox/Projects/cbm-client-intake`.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This prompt names
four stopping points. Between them the work proceeds without asking.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires. Open every reply with the local time from
`date`.

Read, in full, before any work:

- `prompts/integrations-tab-build-orchestrator-v0.1.md`: the rules for every
  phase session, and how a phase is closed.
- `prds/integrations-tab-plan.md`. Rulings I1 to I13 and W1 to W6 are
  settled. § 4, § 6.3, § 6.5 and § 7 each open with a note naming what phase
  10 removed.
- `setup/CLAUDE.md`, `OPEN-ITEMS.md` items 82 and 85, and `CHANGELOG.md`
  0.321.0 to 0.335.0.
- `SYSTEM-SETTINGS-SETUP.md`, which does not yet describe the Integrations
  tab.

## Part 1 — documentation

Write what an administrator and the next engineer need, from what was built.
Do not write it from the plan, which records rulings that were later
replaced.

- **`SYSTEM-SETTINGS-SETUP.md`** gets an Integrations tab section. It
  covers:
  - the switch (`INTEGRATIONS_TAB`) and what changes when it is on;
  - the sub-tabs, the status line, the "in use" settings and their two
    refusals;
  - the Test Integration button and what each result means;
  - the set-up wizard: where it starts, Back, Start again, Fix with the
    wizard, and a failed screen;
  - Ask Claude and its monthly budget;
  - the nightly test, its hour and its alert;
  - switching it off.
- **`setup/CLAUDE.md`** gets the rules a future session must not break, in
  a few lines each:
  - the registry and the `integration=` tags;
  - the guard;
  - a check that cannot read answers unknown, never ok;
  - "skipped" counts as passing a wizard screen;
  - the wizard's step-file keys and `wizard.problems`;
  - Claude is read-only, and a secret's value never reaches it;
  - one budget table;
  - Alembic's 32-character revision limit.
- The root `CLAUDE.md` gets one pointer line under System Settings and
  nothing more. That file has a size budget.
- Check whether `SYSTEM-SETTINGS-SETUP.md` is in `scripts/publish_docs.py`'s
  registry. If it is, publishing is Doug's decision, since that site is
  public.

**Stopping point 1.** Put the documentation to Doug for review. Then stop.

## Part 2 — the live review on the Business Mentors Association's system

The test system is the Association's (`OPEN-ITEMS.md` #85), not crm-test.

- Its application tracks `main`. Check its `/healthz` reports v0.335.0 or
  later before anything else.
- The switch is not on there yet (#85 owed (1)). Switching it on is one of
  Doug's steps.
- Its CRM keeps test records until someone restores it, and a restore
  removes `crm.config` (#84).

Write the review as a **runbook page** (the Step-by-Step Instructions
standard: one done box per step, a "Before you start" block, the
report-back line at each section's end). Doug walks it signed in as an
administrator.

Integrations that have no credentials on the Association are walked only as
far as their first screen that needs a vendor. The page says so for each.

Walk what phase 9 and phase 10 left unproved (#82, 9a, 9d and 10a):

- **the Zoom Meetings test**, which also reads the co-host setting for the
  first time;
- **every integration's wizard**, as far as that integration's credentials
  allow;
- **the Google test's whole-grant line**;
- **both button screens**: Google's shared drive and Twilio's sender number;
- **the Connect screen's return** for Constant Contact;
- **Fix with the wizard** after a failed test;
- **the nightly alert's link**;
- **one real Ask Claude answer**, and what it cost.

**Stopping point 2.** The runbook page is published and its link given to
Doug. Then stop.

**Stopping point 3.** Doug's findings come back. Put each one to him as a
fix or as an open item, one at a time. Fix what he approves, with tests, on
its own version. Then stop.

## Part 3 — closing

Close the phase as the orchestrator requires.

- The State column is updated: the build's eleven phases are done.
- Item 82 is reduced to what is still owed.
- Switching the tab on in production is **not** this phase. Write it as the
  next step for Doug's decision, with what production lacks: credentials,
  the CRM changes in #80 and #84, and the chapter apps' release train.

**Stopping point 4.** Closed. Then stop.

## Things the build has learned

- **Another session works in the same checkout and git index.** Commit with
  an explicit path list (`git commit -- <paths>`, after `git add` of new
  files only), and audit with `git show --stat`. If a file you must change
  holds another session's uncommitted edits, stop and ask before committing
  it (phase 10, `OPEN-ITEMS.md`).
- **Read `git log` and `uv run alembic heads`** before choosing a version or
  a migration number. The Business Evaluation build takes versions too
  (v0.336.0 came between phases).
- **The local Postgres container `cbm-client-intake-db-1`** runs the
  `_pg` migration tests with
  `TEST_DATABASE_URL=postgresql://cbm:cbm@localhost:5432/cbm_intake`.
  `tests/test_settings_store_pg.py` fails there because of older rows
  (#82 10c); every other test passes.
- Doug's review of 11-13-26: one list, never three; never ask to set a value
  the page already shows; one step or question at a time (memory
  `wizard-not-lists`).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.2 | 11-15-26 12:44 | Claude (Claude Code) | Approved by Doug. |
| 0.1 | 11-15-26 12:42 | Claude (Claude Code) | Draft written at the close of phase 10 (v0.335.0). The live review moves from crm-test to the Business Mentors Association's system (#85). |
