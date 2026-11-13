# Kickoff prompt — Integrations tab, phase 6: the diagnosis agent and fix plans

Last Updated: 11-13-26 11:04 · Revision 0.1 (draft) — see change log at the end.

**Draft.** Doug approves this prompt before the phase 6 session starts.
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
  decisions recorded in its change log are settled; do not re-open them.**
  This phase builds § 6 (6.1 to 6.4 and 6.6) and the `integration_fix_plan`
  table of § 7: rulings I7, I9, I10 and the fix-plan half of I12. The setup
  assistant (§ 6.5, ruling I11) is phase 7.
- `OPEN-ITEMS.md` item 82.
- `setup/CLAUDE.md`, and `CHANGELOG.md` entries 0.321.0 to 0.326.0.
- **The `claude-api` skill, before any Claude API code** (the orchestrator
  requires it): the Python SDK's Tool Runner, `claude-opus-5-5` with adaptive
  thinking, effort `high`, streaming, the server-side refusal fallback, and
  the server-side web search and web fetch tools with `allowed_domains`.
- What phases 1 to 5 built, and reuse it:
  - `integrations/testing.py` (`secret_values`, `scrub`) — the diagnosis
    agent sees a secret only as set or not set and when it last changed;
  - `integrations/store.py` (the stored runs the agent reads), and
    `integrations/checklist.py` (the checklist and its ticks);
  - the checked save path: `core/settings_store.py`, `setup/verify.py`, the
    10-minute confirm-or-undo of `LOCKOUT_KEYS`, and the History tab —
    every setting change a fix plan makes goes through it as the approving
    administrator, noted "applied from a fix plan";
  - the Operations tab's dry-run → apply-that-exact-plan fingerprint
    (`setup/jobs.py`), which a fix plan's approval copies;
  - the existing Claude API code: `comms/summarize.py` and
    `enrichment/research.py` (server-side web tools, cost accounting).

## Scope of this phase

1. **The "Integration agent model" setting** on the Anthropic sub-tab,
   default `claude-opus-5-5` (plan § 2), separate from the summary model.
2. **The read-only tools** of plan § 6.2, each returning only scrubbed data.
3. **The allowed documentation sites** per integration (ruling I9; plan
   § 6.2's proposed lists), on `Integration` in `integrations/registry.py`.
4. **The diagnosis**: "Diagnose with Claude" on a sub-tab whose last test
   failed; one at a time per integration; the agent ends with
   `submit_fix_plan` (plan § 6.3's strict schema); token use and cost stored.
5. **The fix plan**: the `integration_fix_plan` table (Alembic migration, the
   shared engine, a `kind` column ready for phase 7's setup plans),
   fingerprinting, Approve and apply (ruling I7), carried out by the
   application step by step (ruling I10): setting changes straight through,
   pausing at manual steps until ticked, stopping on the first failed step,
   then the re-test. A setting change the plan names that is a secret or on
   the denylist is refused when the plan is written, not when it runs.
6. **§ 6.6, recent errors**: settle it (the plan proposes an
   `integration_event` table both processes write, kept 14 days).
7. **Tests**, with a fake Anthropic client: no secret in anything sent to the
   Claude API; a refused setting change; a changed plan refused at apply; a
   failed step stopping the plan; the re-test.

## Stopping point 1 — the design, before any code

Put to Doug:

- the exact read-only tools and what each returns, with one example of each
  from crm-test's real data, scrubbed;
- the allowed sites per integration, checked against where each vendor's
  documentation actually lives today;
- the system prompt, in full;
- § 6.6's answer;
- **the cost of one diagnosis**, estimated from the token budget, and a
  monthly cap if Doug wants one;
- whether a real diagnosis may be run on crm-test at stopping point 2. It
  spends real money on the chapter's Anthropic key.

Then stop.

## Stopping point 2 — the phase built

Build items 1 to 7. Show the page with the stubbed preview (as phases 2 to 4
did) with a fix plan proposed, approved and applied. Run one real diagnosis
only if Doug said yes at stopping point 1, and report its fix plan and cost.

Close the phase as the orchestrator's **Closing a phase** section requires,
and write the phase 7 prompt as a draft. Then stop for Doug's review.

## Things phases 2 to 5 learned

- **Another session may be working in the same checkout.** On 11-13-26 the
  Business Evaluation session had uncommitted work in shared files, with its
  own version and migration number. Before choosing a version or a
  migration number, read `git status` and every uncommitted migration's
  `down_revision`, and check `uv run alembic heads` shows one head. Run the
  full suite in a scratch worktree holding only this phase's files; build
  each shared file's staged copy from `HEAD` plus this phase's own edits.
  The version is in **both** `pyproject.toml` and `uv.lock`.
- **The switch-off payload test** (`tests/test_integrations_tab.py`) compares
  every group of the Settings tab with a captured fixture, not only
  Features. A new setting that only matters with the tab on goes in
  `setup/service.TAB_ONLY_KEYS`, which hides it while the switch is off; the
  integration agent model is tagged to Anthropic, so it moves to that
  sub-tab with the switch on and must not show with it off.
- **The auto-mode classifier refused reading the deployments' live specs**
  (`doctl apps spec get`), even key names only. Ask Doug when a fact depends
  on them.
- `.env` values reach a `TestClient` settings payload; check a preview's
  `data.js` holds no secret value before serving it.

## Out of scope

The setup assistant and coded actions (phase 7), documentation and the live
review on crm-test (phase 8).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-13-26 11:04 | Claude (Claude Code) | Draft written at the close of phase 5 (v0.326.0), from the orchestrator's rules and what phases 1 to 5 built. |
