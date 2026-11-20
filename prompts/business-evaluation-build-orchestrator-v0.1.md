# Build orchestrator — Business Evaluation

Last Updated: 11-20-26 03:40 · Revision 0.27 — see change log at the end.

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
- **The exception, phases 8 and 9** (Doug's choice B, 11-20-26): one session builds both. Every decision for both phases comes first, at one stopping point; both are built without stopping; one combined check closes both. Phase 9's prompt is therefore not written after phase 8's review.

## The phases

| Phase | What it builds | Prompt | State |
|---|---|---|---|
| 1 | The foundation: the CRM plan on crm-test, the survey definition format, the business profile, Finance and Marketing survey drafts, the link store, the public survey page | `prompts/business-evaluation-phase1-prompt-v0.1.md` | Built v0.324.0, live-checked by Doug 11-13-26 |
| 2 | The mentor side: the Evaluations tab, Send Evaluation, the email, status, resend and expire | `prompts/business-evaluation-phase2-prompt-v0.1.md` | Built v0.328.0, checked by Doug as Joe Mentor 11-13-26 |
| 2b | The survey engine (ruling BE23): the engine pieces moved from `evaluation/` into `surveys/`, with Business Evaluation as the first survey purpose | `prompts/business-evaluation-phase2b-prompt-v0.1.md` | Built v0.330.0, live-checked by Doug on a local run against crm-test 11-13-26 |
| 3 | The analysis: the worker job, the analysis prompts and rubrics, the report template, Retry | `prompts/business-evaluation-phase3-prompt-v0.1.md` | Built v0.332.0; sample reports reviewed by Doug 11-14-26 |
| 4 | Review and approval, and scheduling the review session | `prompts/business-evaluation-phase4-prompt-v0.1.md` | Built v0.336.0; checked by Doug on a local run against crm-test 11-15-26 |
| 5 | Release of the client version, and action items as records | `prompts/business-evaluation-phase5-prompt-v0.1.md` | Built v0.338.0; checked by Doug on the Business Mentors Association's system 11-16-26 |
| 6 | The intake survey: sent when a client intake is delivered, "more details?" and the area picker, the answers in Client Administration, Assign moving the records (BE24 to BE27) | `prompts/business-evaluation-phase6-intake-survey-prompt-v0.1.md` | Built v0.339.0; checked by Doug on the Association 11-19-26 (tab look fixed v0.340.1) |
| 7 | The mentor match: the AI analysis button in Client Administration (BE28) | `prompts/business-evaluation-phase7-mentor-match-prompt-v0.1.md` | Built v0.350.0; samples reviewed and checked by Doug on the Association 11-20-26 |
| 8 | Feedback surveys, the foundation: the `feedback` purpose, the 0-to-10 question, the Survey Response record, on-demand send, the mentor's view, low-score alerts, the quiet period (BE29, BE31 to BE33) | `prompts/business-evaluation-phase8-9-feedback-prompt-v0.1.md`, with phase 9 (Doug's choice B, 11-20-26); the phase 8 prompt, revision 0.2, is superseded | Built v0.354.0 with phase 9 (decisions taken 11-20-26); the combined check on the Association owed |
| 9 | Feedback moments and Analytics: the four automatic moments, starter panels (BE30) | the same prompt as phase 8 (one session) | Built v0.354.0 with phase 8; the combined check owed |
| 10 | The partner and funder offering, co-branding, the anonymized roll-up (BE21, BE34 to BE36); formerly phase 6 | `prompts/business-evaluation-phase6-prompt-v0.1.md` (revision 0.2, approved 11-16-26) is superseded: rewritten at the end of phase 9 | **On hold** for the expansion plan (plan revision 0.14) |
| 11 | The pilot review, then the other four evaluation areas as content; formerly phase 7 | written at the end of phase 10 | — |
| 12 | Documentation, training material, the live review, the production handoff; formerly phase 8 | written at the end of phase 11 | — |

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
- **Each new use has its own switch, default off** (rulings BE24,
  BE28, BE29, BE30), beside `BUSINESS_EVALUATION`. Off, every page behaves
  as before, and a test proves it.
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
| 0.8 | 11-13-26 23:36 | Claude (Claude Code) | Phase 3 prompt approved by Doug. |
| 0.9 | 11-14-26 13:35 | Claude (Claude Code) | Phase 3 built (v0.332.0); phase 4 draft prompt written. |
| 0.10 | 11-14-26 17:23 | Claude (Claude Code) | Phase 4 prompt approved by Doug. |
| 0.11 | 11-15-26 12:20 | Claude (Claude Code) | Phase 4 built (v0.336.0); phase 5 draft prompt written. |
| 0.12 | 11-15-26 12:45 | Claude (Claude Code) | Phase 5 prompt approved by Doug. |
| 0.13 | 11-15-26 23:20 | Claude (Claude Code) | Phase 5 built (v0.338.0); its check owed. |
| 0.14 | 11-16-26 01:10 | Claude (Claude Code) | Phase 5 checked on the Association; phase 6 draft prompt written. |
| 0.15 | 11-16-26 01:22 | Claude (Claude Code) | Phase 6 prompt approved by Doug. |
| 0.16 | 11-16-26 02:05 | Claude (Claude Code) | Phase 6 on hold: Doug wants a planning session on wider uses of the evaluation first. |
| 0.17 | 11-16-26 11:59 | Claude (Claude Code) | The phases re-cut to plan revision 0.13: new phases 6 to 9 (the intake survey, the mentor match, feedback surveys, feedback moments); the partner offering moved to phase 10 and on hold, its approved prompt superseded; the pilot and documentation phases renumbered 11 and 12. One rule added: each new use has its own switch. |
| 0.18 | 11-16-26 12:08 | Claude (Claude Code) | Phase 6 (the intake survey) prompt approved by Doug. |
| 0.19 | 11-16-26 13:30 | Claude (Claude Code) | Phase 6 built (v0.339.0); its check owed. |
| 0.20 | 11-19-26 22:30 | Claude (Claude Code) | Phase 6 checked on the Association; phase 7 draft prompt written. |
| 0.21 | 11-19-26 22:40 | Claude (Claude Code) | Phase 7 (the mentor match) prompt approved by Doug. |
| 0.22 | 11-19-26 23:36 | Claude (Claude Code) | Phase 7 built (v0.350.0); its check owed. |
| 0.23 | 11-20-26 00:59 | Claude (Claude Code) | Phase 7 checked on the Association; phase 8 draft prompt written. |
| 0.24 | 11-20-26 01:10 | Claude (Claude Code) | Phase 8 (feedback surveys, the foundation) prompt approved by Doug. |
| 0.25 | 11-20-26 01:16 | Claude (Claude Code) | Doug's choice B: phases 8 and 9 in one session, all decisions first, one combined check; the combined prompt drafted, the phase 8 prompt superseded. |
| 0.26 | 11-20-26 01:27 | Claude (Claude Code) | The combined phase 8 and 9 prompt approved by Doug. |
| 0.27 | 11-20-26 03:40 | Claude (Claude Code) | Phases 8 and 9 built (v0.354.0); the combined check owed. Phase 10 stays on hold; its prompt is rewritten when Doug lifts the hold. |
