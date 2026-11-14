# Build orchestrator — Business Evaluation

Last Updated: 11-13-26 22:58 · Revision 0.7 — see change log at the end.

This file runs the whole build of the Business Evaluation offering. It names the
phases, the prompt for each one, the rules that every phase session follows, and
the stopping points where the work pauses for Doug. The design is
`prds/business-evaluation-plan.md`; this file never restates or changes it.

All rulings in the plan were approved by Doug on 11-13-26.

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
| 1 | The foundation: the CRM plan on crm-test, the survey definition format, the business profile, Finance and Marketing survey drafts, the link store, the public survey page | `prompts/business-evaluation-phase1-prompt-v0.1.md` | Built v0.324.0, live-checked by Doug 11-13-26 |
| 2 | The mentor side: the Evaluations tab, Send Evaluation, the email, status, resend and expire | `prompts/business-evaluation-phase2-prompt-v0.1.md` | Built v0.328.0, checked by Doug as Joe Mentor 11-13-26 |
| 2b | The survey engine (ruling BE23): the engine pieces moved from `evaluation/` into `surveys/`, with Business Evaluation as the first survey purpose | `prompts/business-evaluation-phase2b-prompt-v0.1.md` | Built v0.330.0, live-checked by Doug on a local run against crm-test 11-13-26 |
| 3 | The analysis: the worker job, the analysis prompts and rubrics, the report template, Retry | `prompts/business-evaluation-phase3-prompt-v0.1.md` | Draft prompt written 11-13-26, revised for the survey engine at the close of phase 2b (revision 0.2); awaits Doug's approval. |
| 4 | Review and approval, and scheduling the review session | written at the end of phase 3 | — |
| 5 | Release of the client version, and action items as records | written at the end of phase 4 | — |
| 6 | The partner and funder offering, and the anonymized roll-up | written at the end of phase 5 | — |
| 7 | The pilot review, then the other four evaluation areas as content | written at the end of phase 6 | — |
| 8 | Documentation, training material, the live review on crm-test, the production handoff | written at the end of phase 7 | — |

The session closing each phase updates the **State** column.

## Rules for every phase session

**Reading, before any code.**

- `prds/business-evaluation-plan.md` in full. **Its approved rulings are
  settled.** A session does not re-open them. A session that finds a ruling
  cannot be built as written stops and puts that to Doug.
- The root `CLAUDE.md`, plus `sessions/CLAUDE.md` for any phase that touches
  Client Management and `docs/CLAUDE.md` for any phase that files documents.
  Any other folder's `CLAUDE.md` named by the phase prompt.
- The `OPEN-ITEMS.md` item that phase 1 creates, for what is owed.

**Operating mode.** DETAIL, this repository's default. The phase prompt names
its stopping points. Between two stopping points the work proceeds without
asking. Follow-on detail is announced as "decided unless you object" and does
not stop the work, except a choice that changes what a client, a mentor or a
partner sees or receives, which goes to Doug as a decision.

**Building.**

- **Everything is built dark** behind `BUSINESS_EVALUATION`, default off. While
  the switch is off, every existing page behaves exactly as before, and a test
  proves it.
- **A CRM-facing feature detects its entity and fields from metadata** and stays
  inert until they exist. CRM changes go through a plan in `crm-plans/`, applied
  to crm-test by `scripts/apply_crm_plan.py`, with a handoff file for
  production. No phase changes production's CRM.
- **The client's public pages follow the public forms' rules**: honeypot,
  submission-token idempotency, `{{org}}` and `{{abbr}}` tokens, the shared
  wizard styles, no CRM id in any link. A link opens nothing once it has expired
  or been replaced.
- **The survey engine (`surveys/`) holds no code specific to Business
  Evaluation** (ruling BE23). Everything specific lives in `evaluation/`, which
  registers itself as a survey purpose. A test fails if `surveys/` imports
  from `evaluation/`.
- **The draft report never reaches the client** (ruling BE17). No code path
  emails, files or shows `draftReport` to anyone but reviewers.
- **Answers sent to the Claude API carry no contact details**: no email
  addresses, phone numbers or street addresses. The company name and the
  business profile are allowed.
- **Business Evaluation records carry the engagement's `assignedUsers`**, and
  the nightly assignment reconciliation includes the new entity.
- The repository's conventions hold: `busy.js` loaded first on the page, action
  buttons never disabled or hidden, the shared grid for any grid, the shared
  `CBMRichText` editor for any rich text, the shared `CBMDateTime` control for
  any date, mentor-to-client mail from the mentor's own mailbox, every mutating
  staff action recorded through `core/action_log.py`, best-effort side effects
  that never fail the user's save.
- A new database table comes with an Alembic migration. A new store borrows the
  shared engine (`core/store.shared_engine`).
- Any Claude API code follows the `claude-api` skill: load it before writing
  that code. Structured output through `client.messages.parse`, as
  `comms/summarize.py` does.

**Closing a phase.**

1. All tests pass: `uv run pytest -q`. State the count.
2. The version is bumped in `pyproject.toml` (a minor version for a phase that
   adds a capability). `CHANGELOG.md` gets the entry.
3. The Business Evaluation item in `OPEN-ITEMS.md` is updated: what is built,
   what is owed.
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
| 0.1 | 11-13-26 00:42 | Claude (Cowork) | Created from plan revision 0.1: eight phases, the rules for every phase session, the closing steps. |
| 0.2 | 11-13-26 00:57 | Claude (Cowork) | Plan approved (revision 0.2): phase 1 state changed to not started. |
| 0.3 | 11-13-26 10:45 | Claude (Claude Code) | Phase 1 built (v0.324.0); phase 2 draft prompt written. |
| 0.4 | 11-13-26 11:50 | Claude (Claude Code) | Phase 2 prompt approved by Doug. |
| 0.5 | 11-13-26 13:55 | Claude (Claude Code) | Phase 2 built (v0.328.0); phase 3 draft prompt written. |
| 0.6 | 11-13-26 14:22 | Claude (Cowork) | Ruling BE23: phase 2b added after phase 2, before phase 3; phase 3's prompt revised at the close of phase 2b; new rule that the survey engine holds no Business Evaluation code. Merged by Claude (Claude Code) 11-13-26 14:24. |
| 0.7 | 11-13-26 22:58 | Claude (Claude Code) | Phase 2b built (v0.330.0); phase 3's prompt revised for the survey engine. |
