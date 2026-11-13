# Kickoff prompt — Integrations tab, phase 2: the integration test, three integrations

Last Updated: 11-13-26 00:38 · Revision 0.1 (draft) — see change log at the end.

**Draft.** Doug approves this prompt before the phase 2 session starts.
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
  them.** This phase builds § 3's part 2 (Test Integration) for EspoCRM,
  Google Workspace and Zoom, and the `integration_test_run` table of § 7.
- `OPEN-ITEMS.md` item 82.
- `setup/CLAUDE.md`, and `CHANGELOG.md` entry 0.321.0 for what phase 1 built.
- What phase 1 built: `integrations/registry.py`, `integrations/guard.py`,
  `core/settings_registry.py` (`INTEGRATION_TAGS`), `setup/service.py`
  (`_integrations`, the `status` block, `tested` is `None` today),
  `setup/readiness.py` (`_add_integrations`), `setup/frontend/app.js`
  (`renderIntegrations`, `statusLine`, `placeholders`) and
  `tests/test_integrations_tab.py`.
- The clients the checks will use: `core/espo.py`, `core/admin_client.py`,
  `core/schema_contract.py`, `core/gmail.py`, `core/gdrive.py`,
  `core/gcalendar.py`, `core/google_directory.py`, `core/zoom.py`, and
  `setup/verify.py` (its probes already distinguish "failed" from "could not
  reach — unknown").
- `core/store.py` (`shared_engine`) and the newest Alembic migration under
  `alembic/versions/`, for how a table is added.

## Scope of this phase

1. **The integration test framework.** A check is a named function that
   returns ok, failed or unknown with one line of detail, and never raises.
   An integration test runs that integration's checks in order and collects
   the integration facts. Add the test to `Integration` in the registry.
2. **The table `integration_test_run`** (plan § 7), with an Alembic migration
   and a store that borrows `core/store.shared_engine`. Only manual runs in
   this phase; the `nightly` value exists for phase 5.
3. **The checks and integration facts for EspoCRM, Google Workspace and
   Zoom**, starting from plan § 3's proposals. Each one is confirmed against
   the vendor's API as it is written. Google's checks cover only the features
   switched on, plus the credentials. The EspoCRM version read is an open
   point (plan § 9): find the call on crm-test before relying on it.
4. **The Test Integration button** on those three sub-tabs, the result as one
   line per check, and the integration facts. The status line's "Not tested
   yet" becomes the last result and its time. The other six sub-tabs keep
   their phase 1 placeholder, now saying phase 3.
5. **An API endpoint** for running a test and one for reading the last run,
   admin-only like the rest of `/setup/api`, each run recorded with
   `core/action_log.py`.

Rules that bind this phase: a secret's value never leaves the server and is
never written into a check's detail or a fact; opening the page never calls an
outside service; a check that cannot reach its target says unknown, never ok;
nothing writes to any outside service.

## Stopping point 1 — the checks, before any code

For each of the three integrations, put to Doug the list of checks and
integration facts you will build: what each check calls, what ok and failed
mean, and which need a feature switched on. Name any proposal from plan § 3
you dropped or changed, and why. Then stop.

## Stopping point 2 — the phase built

Build items 1 to 5. Tests: each check's ok, failed and unknown paths with fake
clients; no secret in any stored run; the endpoint is admin-only; the status
line reads the last run; the switch-off payload test still passes.

Then show the page with the stubbed preview (as phase 1 did) or a real
sign-in, and take a screenshot of each of the three sub-tabs after a test.
If a crm-test sign-in is available, run the three tests there and report the
results.

Close the phase as the orchestrator's **Closing a phase** section requires,
and write the phase 3 prompt as a draft. Then stop for Doug's review.

## Out of scope

The other six integrations' tests (phase 3), the setup checklist, the nightly
run, the diagnosis agent and the setup assistant.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-13-26 00:38 | Claude (Claude Code) | Draft written at the close of phase 1 (v0.321.0), from the orchestrator's rules and what phase 1 built. |
