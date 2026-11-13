# Kickoff prompt — Integrations tab, phase 4: the setup checklist

Last Updated: 11-13-26 01:44 · Revision 0.1 (draft) — see change log at the end.

**Draft.** Doug approves this prompt before the phase 4 session starts.
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
  them.** This phase builds § 3's part 4 (the setup checklist) and all of
  § 4, plus the `integration_checklist_tick` table of § 7.
- `OPEN-ITEMS.md` item 82.
- `setup/CLAUDE.md`, and `CHANGELOG.md` entries 0.321.0 to 0.323.0.
- The deployment guide's step files and their renderer:
  `prds/chapter-network/deployment-guide/steps/` (its `README.md` first, then
  every `stage-*.yaml`), `scripts/render_deployment_guide.py`, and the
  rendered guide under `prds/chapter-network/deployment-guide/guide/`. Note
  each step's `produces:` key, the natural source for `setting_set` checks.
- What phases 1 to 3 built, and copy their shape:
  - `integrations/registry.py` (the nine integrations, their switches and
    credentials) and `integrations/testing.py`;
  - `integrations/store.py` (the shared engine, `RESET_TABLES`) and
    migration `0043` — the new table follows the same pattern;
  - the two test endpoints in `setup/router.py` and the sub-tab rendering in
    `setup/frontend/app.js`, where the "Setup checklist — comes with
    phase 4" placeholder sits (`placeholders`);
  - `tests/test_integration_test.py` and `tests/test_integration_test_phase3.py`.

## Scope of this phase

1. **The step-file keys**: `integration:` and `check:` on each step that
   belongs to an integration (plan § 4). `scripts/render_deployment_guide.py
   --check` must still pass, and the rendered guide must not change.
2. **The automatic checks**, named in code: `setting_set:<key>`,
   `switch_on:<key>`, `test_passed:<integration>` (reads the last row of
   `integration_test_run`), `crm_field:<Entity>.<field>` (from CRM metadata
   through the existing cached read). Opening the page never calls an outside
   service: a check that would need one reads unknown and says why.
3. **The hand ticks**: the `integration_checklist_tick` table (Alembic
   migration, shared engine, in `RESET_TABLES`), two endpoints, the History
   tab entry through `core/action_log.py`, one deployment-wide set of ticks.
   An automatic step can never be ticked by hand; when its check fails, the
   box stays empty and the reason is shown beside it.
4. **The first step of every checklist**: "Decide whether this chapter uses
   <integration>" (ruling I5), automatic from the "in use" setting.
5. **The missing steps** for Lob, Twilio, Anthropic and YouTube, written into
   the step files to the Step-by-Step Instructions standard. Every location
   named outside-in, every value in its own copyable block.
6. **The page**: the checklist section on each sub-tab, folded when the
   integration is not in use; the placeholder goes.
7. **Tests**: the keys parse, every `check:` names a known check, the
   rendered guide is unchanged, each check's ticked, empty and unknown paths,
   a hand tick refused on an automatic step, the switch-off payload test still
   passing.

## Stopping point 1 — the mapping, before any code

Put to Doug, for each of the nine integrations: the steps its checklist will
show, in order, with the stage file each comes from, which are automatic and
the `check:` each carries, and which are manual. Name the new steps proposed
for Lob, Twilio, Anthropic and YouTube by title, with the stage they go
into. Name any step that belongs to two integrations, and say how it is
shown. Then stop.

## Stopping point 2 — the phase built

Build items 1 to 7. Show the page with the stubbed preview (a scratchpad
copy of the page with `stub.js` and `data.js` loaded before `busy.js`, as
phases 2 and 3 did; `data.js` built from the real settings payload with the
switch on) and take a screenshot of three sub-tabs' checklists: Google
Workspace (the longest), Zoom, and one integration marked not in use.

Close the phase as the orchestrator's **Closing a phase** section requires,
and write the phase 5 prompt as a draft. Then stop for Doug's review.

## Things phases 2 and 3 learned

- **Another session may be working in the same checkout.** On 11-13-26 a
  Business Evaluation session had `core/config.py`,
  `core/settings_registry.py`, `pyproject.toml`, `uv.lock` and the
  switch-off fixture open. Run the full suite in a scratch worktree holding
  only this phase's files, and stage only this phase's files (a shared file
  by hunk, through `git apply --cached`). The version is in **both**
  `pyproject.toml` and `uv.lock`.
- **The switch-off payload test** (`tests/test_integrations_tab.py`) compares
  the Settings tab with a captured fixture, so any new setting in the
  Features group fails it until the fixture is re-captured.
- The page's class names collide easily. Grep `setup/frontend/styles.css`
  before naming one.
- The preview's `data.js` can be generated with `TestClient` from the
  `_app` helper in `tests/test_integration_test.py`; the local `.env`
  values leak into that payload (playlist IDs, for example), so check it
  holds no secret before serving it — `run_checks` scrubs results, not the
  settings payload.
- Phase 3's live run found **one of the five configured YouTube playlists
  missing**. If the YouTube checklist gets a "playlists readable" step, it is
  `test_passed:youtube`, not a new check.

## Out of scope

The nightly run (phase 5), the diagnosis agent (phase 6) and the setup
assistant (phase 7).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-13-26 01:44 | Claude (Claude Code) | Draft written at the close of phase 3 (v0.323.0), from the orchestrator's rules and what phases 1 to 3 built. |
