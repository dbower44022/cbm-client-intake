# Kickoff prompt — Integrations tab, phase 7: the setup assistant and setup plans

Last Updated: 11-13-26 12:12 · Revision 0.1 (draft) — see change log at the end.

**Draft.** Doug approves this prompt before the phase 7 session starts.
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
  This phase builds § 6.5: the setup assistant, its setup plans and the
  coded actions — rulings I11 and I12 (every setup step, automatic or
  manual, waits for the administrator's confirmation), and check-on-confirm
  (plan § 2).
- `OPEN-ITEMS.md` item 82.
- `setup/CLAUDE.md`, and `CHANGELOG.md` entries 0.321.0 to 0.327.0.
- **The `claude-api` skill, before any Claude API code.**
- What phase 6 built, and extend it rather than copy it:
  - `integrations/diagnosis.py`: the snapshot, the read-only tools, the
    loop, `check_plan`, the scrubbing — the setup assistant is the same
    agent asked a different question, with a third step kind;
  - `integrations/fixplans.py`: the table already has `kind`; setup plans
    are `kind = "setup"`;
  - the endpoints and `_carry_out` in `setup/router.py`, and the Diagnosis
    section in `setup/frontend/app.js` (`diagnosisBlock`);
  - `integrations/checklist.py`: a setup plan starts from the open steps of
    the checklist, and a confirmed manual step runs its step's automatic
    check where one exists;
  - the Operations tab's dry-run → apply-that-exact-plan jobs
    (`setup/jobs.py`): every coded action is idempotent and has a dry run.

## Scope of this phase

1. **"Set up with Claude"** on a sub-tab whose setup checklist has open
   steps. Same model, tools, sites, budget and approval as the diagnosis.
2. **`submit_setup_plan`**: setting changes, manual steps and **coded
   actions** — chosen by name from a list in code, with their inputs. The
   agent never writes its own call to an outside service.
3. **The first coded actions** (plan § 6.5's proposals, each confirmed or
   dropped at stopping point 1): create the Google shared drive and its
   folder scheme; apply a feature's CRM fields and relationships (wrapping
   the existing `scripts/migrate_*_schema.py`); look up the Twilio sender
   number; confirm the Zoom host user. Each with a dry run, idempotent, and
   run as the confirming administrator where the CRM is involved.
4. **The one-step-at-a-time runner** (ruling I12): every step waits for the
   administrator's confirmation; a confirmed manual step runs its check, and
   a failed check keeps the step open, names what is missing and offers a
   diagnosis.
5. **Manual steps arrive with the chapter's own values filled in**, for
   example the delegation grant with the exact client ID and scope list.
6. **Tests**, with a fake Anthropic client and fake vendor clients.

## Stopping point 1 — the design, before any code

Put to Doug:

- each proposed coded action: what it calls, its dry run, what makes it
  idempotent, and whether the credentials it needs are ones this
  application may hold (ruling I11: never broad administrator credentials
  for a vendor);
- the steps that stay manual because the vendor has no API or would need
  credentials the application must not hold (plan § 6.5's inferred list),
  each confirmed against the vendor's documentation;
- the setup assistant's system prompt, in full;
- whether a real setup plan may be run on crm-test at stopping point 2,
  and on which Anthropic key.

Then stop.

## Stopping point 2 — the phase built

Build items 1 to 6. Show the page with the stubbed preview, a setup plan
proposed and carried out one step at a time. Run one real setup plan only if
Doug said yes at stopping point 1.

Close the phase as the orchestrator's **Closing a phase** section requires,
and write the phase 8 prompt as a draft. Then stop for Doug's review.

## Things phases 2 to 6 learned

- **Another session may be working in the same checkout.** On 11-13-26 the
  Business Evaluation session had uncommitted work in shared files with its
  own version and migration numbers, twice. Before choosing a version or a
  migration number, read `git log`, `git status` and every uncommitted
  migration's `down_revision`, and check `uv run alembic heads` shows one
  head. Run the full suite in a scratch worktree holding only this phase's
  files; build each shared file's staged copy from `HEAD` plus this phase's
  own edits. The version is in both `pyproject.toml` and `uv.lock`.
- **The switch-off payload test** compares every group of the Settings tab
  with a captured fixture. A new setting that only matters with the tab on
  goes in `setup/service.TAB_ONLY_KEYS`.
- **No Anthropic key is held locally** (11-13-26), so a real Claude call runs
  on crm-test, after a push, with the tab on — or Doug supplies a key.
- **The auto-mode classifier refuses reading the deployments' live specs**;
  ask Doug when a fact depends on them.
- `.env` values reach a `TestClient` settings payload; check a preview's
  `data.js` holds no secret before serving it.

## Out of scope

Documentation and the live review on crm-test (phase 8).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-13-26 12:12 | Claude (Claude Code) | Draft written at the close of phase 6 (v0.327.0), from the orchestrator's rules and what phases 1 to 6 built. |
