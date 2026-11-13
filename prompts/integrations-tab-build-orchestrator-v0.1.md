# Build orchestrator — the Integrations tab of System Settings

Last Updated: 11-12-26 23:59 · Revision 0.1 — see change log at the end.

This file runs the whole build of the Integrations tab. It names the phases,
the prompt for each one, the rules that every phase session follows, and the
stopping points where the work pauses for Doug. The design is
`prds/integrations-tab-plan.md`; this file never restates or changes it.

## How the build runs

- **One phase per Claude Code session**, rooted in
  `~/Dropbox/Projects/cbm-client-intake`. Each session is started with that
  phase's prompt, pasted in full.
- **Each phase prompt is written after the phase before it has been reviewed**,
  so it starts from what was actually built. The session that closes a phase
  writes the next phase's prompt as a draft. Doug approves the draft before the
  next session starts.
- **One session on this build at a time.** Parallel sessions share one git index
  ([[parallel-sessions-share-one-git-index]]).
- **Doug moves the pointer.** No session starts the next phase on its own.

## The phases

| Phase | What it builds | Prompt | State |
|---|---|---|---|
| 1 | The framework: the integration registry, the sub-tab shell, the status line, the "in use" settings and their guard, the `INTEGRATIONS_TAB` switch, and moving the settings | `prompts/integrations-tab-phase1-prompt-v0.1.md` | Prompt written 11-12-26; not started |
| 2 | The integration test for EspoCRM, Google Workspace and Zoom | written at the end of phase 1 | — |
| 3 | The integration test for Fathom, Constant Contact, Lob, Twilio, Anthropic and YouTube | written at the end of phase 2 | — |
| 4 | The setup checklist: the step-file keys, the automatic checks, the hand ticks, the missing steps | written at the end of phase 3 | — |
| 5 | The nightly integration test and its alert | written at the end of phase 4 | — |
| 6 | The diagnosis agent and fix plans | written at the end of phase 5 | — |
| 7 | The setup assistant and setup plans | written at the end of phase 6 | — |
| 8 | Documentation, and the live review on crm-test | written at the end of phase 7 | — |

The session closing each phase updates the **State** column.

## Rules for every phase session

**Reading, before any code.**

- `prds/integrations-tab-plan.md` in full. **Its rulings, I1 to I13, are
  settled.** A session does not re-open them. A session that finds a ruling
  cannot be built as written stops and puts that to Doug.
- The root `CLAUDE.md` and `setup/CLAUDE.md`. Any other folder's `CLAUDE.md`
  named by the phase prompt.
- `OPEN-ITEMS.md` item 82, which phase 1 creates, for what is owed.

**Operating mode.** DETAIL, this repository's default. The phase prompt names
its stopping points. Between two stopping points the work proceeds without
asking. Follow-on detail is announced as "decided unless you object" and does
not stop the work, except a choice that changes what a user sees or receives,
which goes to Doug as a decision.

**Building.**

- **Everything is built dark** behind `INTEGRATIONS_TAB`, default off. While
  the switch is off, System Settings behaves exactly as before, and a test
  proves it.
- **Every change to a setting goes through the existing checked save path**
  (`core/settings_store.py`, `setup/verify.py`), including the changes a fix
  plan or a setup plan makes. No phase writes `app_setting` any other way.
- **A secret's value never leaves the server and never reaches the Claude
  API.** Only "set or not set" and the time it last changed.
- **The application carries out a plan; the agent only writes it** (ruling
  I10). No phase gives the diagnosis agent or the setup assistant a tool that
  changes anything.
- The repository's conventions hold: `busy.js` loaded first on the page, no
  page-width cap, action buttons never disabled or hidden, the `{{org}}` and
  `{{abbr}}` tokens, the shared grid for any grid, a CRM-facing feature that
  detects its field from metadata, best-effort side effects that never fail the
  user's save.
- A new database table comes with an Alembic migration. A new store borrows the
  shared engine (`core/store.shared_engine`).
- Any Claude API code follows the `claude-api` skill: load it before writing
  that code.

**Closing a phase.**

1. All tests pass: `uv run pytest -q`. State the count.
2. The version is bumped in `pyproject.toml` (a minor version for a phase that
   adds a capability). `CHANGELOG.md` gets the entry.
3. `OPEN-ITEMS.md` item 82 is updated: what is built, what is owed.
4. The plan's change log gets one line naming the phase and the version.
5. The **State** column above is updated.
6. Commit, Conventional Commits style, staged and committed in one step, then
   audited with `git show --stat`. **Do not push.** Doug reviews and pushes.
7. The next phase's prompt is written as a draft, revision 0.1, from this
   file's rules and what the phase actually built.
8. The reply is a review list, then **What next**, as the Reply Format standard
   requires.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-12-26 23:59 | Claude (Claude Code) | Created from plan revision 0.3: eight phases, the rules for every phase session, the closing steps. |
