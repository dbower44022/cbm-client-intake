# Kickoff prompt — Integrations tab, phase 5: the nightly integration test

Last Updated: 11-13-26 10:30 · Revision 0.1 (draft) — see change log at the end.

**Draft.** Doug approves this prompt before the phase 5 session starts.
Paste everything below the line into a fresh Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake`.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This prompt names
two stopping points. Between them the work proceeds without asking.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires. Open every reply with the local time from
`date`.

Read, in full, before any code:

- `prompts/integrations-tab-build-orchestrator-v0.1.md`: the rules every
  phase session follows. They bind this session.
- `prds/integrations-tab-plan.md`: the plan. **Rulings I1 to I13 and the
  phase 1 mapping decisions (change log 0.5) are settled; do not re-open
  them.** This phase builds § 5 and ruling I8: the nightly integration test
  in the worker and its alert. The diagnosis agent never runs on its own.
- `OPEN-ITEMS.md` item 82.
- `setup/CLAUDE.md`, and `CHANGELOG.md` entries 0.321.0, 0.322.0, 0.323.0 and
  0.325.0.
- What phases 2 to 4 built, and reuse it:
  - `integrations/testing.py` (`run_integration_test`, the one-test-at-a-time
    lock — note it is per process, and the nightly run is in the worker);
  - `integrations/store.py` (`NIGHTLY` already exists; the status line
    already says "nightly" for such a run);
  - `integrations/checks/*.py`, and which settings and credentials each one
    reads;
  - `integrations/registry.py` (`in_use`, `blocking_switches`) and
    `integrations/guard.switches_on`;
  - `integrations/checklist.py`: a nightly pass changes what the
    `test_passed` steps show, with no other change.
- The worker and the alerting it already does: `worker.py`,
  `core/monitoring.py` (`send_alert`, `run_alert_check` and its cool-down),
  and how the worker schedules its other daily jobs (the sandbox reset, the
  assignment-stamp reconciliation) at an hour in the chapter's time zone.

## Scope of this phase

1. **The nightly run** in the worker: once a day at a new setting's hour
   (plan § 5: default 06:00 in the chapter's time zone), for each
   integration that is in use and has at least one feature switched on (EspoCRM
   always). Each run stored with `trigger=nightly` and no person.
2. **The alert**: one through `core/monitoring.send_alert` per failed
   integration, naming the integration and the failed check, with a link to
   its sub-tab (`APP_BASE_URL` + `/setup/#integrations/<key>`). Not repeated
   for an unchanged failure, using `run_alert_check`'s cool-down pattern; a
   recovery is reported once. An "unknown" outcome does not alert on its
   own: decide at stopping point 1 after how many nights it does.
3. **The setting** for the hour (and, if needed, a switch for the run),
   registered through `core/settings_registry.py` and placed by its
   integration tag or group as phase 1's mapping does.
4. **Tests**: which integrations run, the hour and the time zone, the stored
   rows, the alert, its cool-down and its recovery, and nothing ever written
   to an outside service.

## Stopping point 1 — the design, before any code

Put to Doug:

- **Which checks the worker cannot run as the web process does.** The
  provisioning account's credentials are on the web component only
  (`CLAUDE.md`, Deployment), so the EspoCRM provisioning check cannot run
  in the worker as it is. Read each check module and the components' settings,
  list every check affected, and propose what each does at night (skipped
  with a reason, or the run moved to the web process).
- When "unknown" becomes an alert, and the alert's wording.
- The setting's name, default, group and component.

Then stop.

## Stopping point 2 — the phase built

Build items 1 to 4. Run one nightly pass by hand against crm-test from a
laptop where credentials are held locally, as phase 2 did for EspoCRM, and
report what it stored and what it would have sent.

Close the phase as the orchestrator's **Closing a phase** section requires,
and write the phase 6 prompt as a draft. Then stop for Doug's review.

## Things phases 2 to 4 learned

- **Another session may be working in the same checkout.** On 11-13-26 the
  Business Evaluation session had uncommitted work in `core/app.py`,
  `core/config.py`, `core/settings_registry.py`, `core/sandbox_reset.py`,
  `CHANGELOG.md`, `OPEN-ITEMS.md`, `CLAUDE.md`, `pyproject.toml` and
  `uv.lock`, with its own version (0.324.0) and migration (0044), while
  phase 4 was built. Before choosing a version or a migration number, read
  `git status` and every uncommitted migration's `down_revision`, and check
  `uv run alembic heads` shows one head. Run the full suite in a scratch
  worktree holding only this phase's files; build each shared file's staged
  copy from `HEAD` plus this phase's own edits, never by staging the file.
  The version is in **both** `pyproject.toml` and `uv.lock`.
- **The switch-off payload test** (`tests/test_integrations_tab.py`) compares
  the Settings tab with a captured fixture, so any new setting in the
  Features group fails it until the fixture is re-captured.
- `.env` values reach a `TestClient` settings payload (playlist IDs, a Fathom
  key's "set"); check a preview's `data.js` holds no secret value before
  serving it.

## Out of scope

The diagnosis agent (phase 6), the setup assistant (phase 7), and the live
review on crm-test (phase 8).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-13-26 10:30 | Claude (Claude Code) | Draft written at the close of phase 4 (v0.325.0), from the orchestrator's rules and what phases 1 to 4 built. |
