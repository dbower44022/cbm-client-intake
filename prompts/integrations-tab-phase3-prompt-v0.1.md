# Kickoff prompt — Integrations tab, phase 3: the integration test, the other six

Last Updated: 11-13-26 01:21 · Revision 0.1 (draft) — see change log at the end.

**Draft.** Doug approves this prompt before the phase 3 session starts.
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
  them.** This phase builds § 3's part 2 (Test Integration) for Fathom,
  Constant Contact, Lob, Twilio, Anthropic and YouTube.
- `OPEN-ITEMS.md` item 82.
- `setup/CLAUDE.md`, and `CHANGELOG.md` entries 0.321.0 and 0.322.0.
- What phase 2 built, and copy its shape exactly:
  - `integrations/testing.py`: `Check`, `Context`, `Skip`, `Blocked`,
    `run_checks`, the scrubbing of secret values, the one-test-at-a-time lock;
  - `integrations/checks/espocrm.py`, `google.py` and `zoom.py`: each has a
    `Deps` dataclass of real clients that tests replace with fakes, a
    `CHECKS` list and `run(settings, deps=None)`;
  - `integrations/registry.py`: `test_module` on `Integration`;
  - `integrations/store.py`, the two endpoints in `setup/router.py`, the test
    block in `setup/frontend/app.js` (`testBlock`, `testedText`);
  - `tests/test_integration_test.py`.
- The clients the checks will use: `core/fathom.py`, `core/mailing.py` and
  `setup/mailing.py` (the Constant Contact connection and its rotating
  refresh token), the Lob and Twilio clients under `campaigns/` (find them by
  `postal_provider` and `sms_provider`), the Anthropic client used by
  `comms/summarize.py` and the enrichment research, and the YouTube client
  used by the events library. Read the `claude-api` skill before writing the
  Anthropic checks.

## Scope of this phase

1. **The checks and integration facts for the six integrations**, starting
   from plan § 3's proposals. Each one is confirmed against the vendor's API
   as it is written. Where a call cannot be confirmed from the vendor's
   reference, say so at stopping point 2 and make the check read unknown,
   never ok, when the answer has an unexpected shape.
2. **Set `test_module`** on each of the six, so their sub-tabs get the Test
   Integration button and their placeholders go.
3. **Tests**: each check's ok, failed and unknown paths with fake clients,
   and no secret in any result.

Rules that bind this phase, as in phase 2: a secret's value never leaves the
server and is never written into a check's detail or a fact; opening the page
never calls an outside service; a check that cannot reach its target says
unknown, never ok; **nothing writes to any outside service**. Two cases need
care:

- **Constant Contact's refresh token rotates**: using it returns a new one,
  which must be stored or the connection is lost. Decide at stopping point 1
  whether the check refreshes the token (through the existing code path,
  which stores the new one) or reads only with the stored access token, and
  say what each costs.
- **Lob and Twilio**: test mode versus live mode, and a check never sends a
  postcard or a text.

## Stopping point 1 — the checks, before any code

For each of the six integrations, put to Doug the list of checks and
integration facts you will build: what each check calls, what ok and failed
mean, and which need a feature switched on. Name any proposal from plan § 3
you dropped or changed, and why. Then stop.

## Stopping point 2 — the phase built

Build items 1 to 3. Then show the page with the stubbed preview (as phase 2
did: a scratchpad copy of the page with a `stub.js` loaded before `busy.js`,
answering `/setup/api/settings` and the test endpoint from a `data.js` built
from real check runs with fake clients) and take a screenshot of each of the
six sub-tabs after a test. Where credentials are held locally, run that
integration's test for real and report the result.

Close the phase as the orchestrator's **Closing a phase** section requires,
and write the phase 4 prompt as a draft. Then stop for Doug's review.

## Things phase 2 learned

- **Another session may be working in the same checkout.** On 11-13-26 a
  Business Evaluation session was editing `core/config.py`,
  `core/settings_registry.py` and `pyproject.toml` while phase 2 was built.
  Run the full suite in a scratch worktree holding only this phase's files,
  and stage only this phase's files (a shared file by hunk, through
  `git apply --cached`).
- **The switch-off payload test** (`tests/test_integrations_tab.py`) compares
  the Settings tab with a captured fixture, so any new setting in the
  Features group fails it until the fixture is re-captured.
- The page's class names collide easily: phase 2's first `su__checks` clashed
  with Feature readiness's. Grep `setup/frontend/styles.css` before naming one.

## Out of scope

The setup checklist (phase 4), the nightly run (phase 5), the diagnosis agent
(phase 6) and the setup assistant (phase 7).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-13-26 01:21 | Claude (Claude Code) | Draft written at the close of phase 2 (v0.322.0), from the orchestrator's rules and what phase 2 built. |
