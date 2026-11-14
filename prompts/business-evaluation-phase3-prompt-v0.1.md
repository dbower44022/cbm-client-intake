# Kickoff prompt — Business Evaluation, phase 3: the analysis

Last Updated: 11-13-26 23:36 · Revision 0.3 — see change log at the end.

**Approved by Doug 11-13-26.** Written at the close of phase 2 (v0.328.0)
and revised at the close of phase 2b (v0.330.0), which moved the survey page,
the links, the saved answers and the submit retry into the survey engine,
`surveys/` (ruling BE23). Paste everything below the line into a fresh Claude
Code session rooted in `~/Dropbox/Projects/cbm-client-intake`, after phase 2b
is pushed.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This prompt names
two stopping points. Between them the work proceeds without asking.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires. Open every reply with the local time from
`date`.

**Another session may be working in this checkout at the same time.** Before
choosing a version number or an Alembic migration number, read `git log` and
`alembic/versions/` and take the next free one; never take numbers from this
prompt. Commit only this phase's lines, staged and committed in one step, then
audit with `git show --stat`.

Read, in full, before any code:

- `prompts/business-evaluation-build-orchestrator-v0.1.md`: the rules every
  phase session follows. They bind this session.
- `prds/business-evaluation-plan.md`: the plan. **Its approved rulings are
  settled; do not re-open them.** This phase builds § 3 step 4 and rulings
  BE6, BE9 (the prompt and rubric versions), BE15, BE16 and BE17.
- `evaluation/CLAUDE.md`: what phases 1, 2 and 2b built, and their rules.
- `surveys/CLAUDE.md`: the survey engine. **The engine holds no Business
  Evaluation code** (ruling BE23), and a test fails if `surveys/` imports
  from `evaluation/`. The analysis is Business Evaluation's: it lives in
  `evaluation/`, never in `surveys/`.
- `OPEN-ITEMS.md` #83: what is owed.
- The `claude-api` skill: load it before writing any Claude API code.
- `comms/summarize.py`: the structured-output pattern
  (`client.messages.parse`) this phase follows, and how it reads its key and
  logs its cost.
- `evaluation/service.py` (`deliver`, the CRM write the engine calls on
  submit, which sets **Submitted**), `evaluation/purpose.py` (the
  registration), `surveys/answers.py` (`answers_json`, `readable_html`),
  `evaluation/sending.py` (the tab's rows and the answers view) and
  `worker.py` (the survey engine's retry pass, one per survey purpose):
  where the analysis job joins. The analysis job is Business Evaluation's
  own worker pass beside the engine's, not part of the engine's retry.
- `sessions/CLAUDE.md`, the Evaluations tab entry: where the draft report and
  Retry show.

## Scope of this phase

Build the analysis, dark behind the same switch, `BUSINESS_EVALUATION`, plus
any sub-switch the session judges the Claude API needs (announce it):

1. **The analysis prompts and scoring rubrics** for Finance and Marketing
   (BE9, BE22), versioned files beside the surveys, each with its version
   stored on the record (`promptVersion`, `rubricVersion`). A rubric names its
   dimensions, each scored 1 to 5 with a description of each level.
2. **The report format** (BE16): summary; a score per rubric dimension with
   the reason; strengths; gaps; recommended action items (title, reason,
   priority, time horizon); information the client did not give; the points
   the analysis is unsure of. One schema for the structured output and one
   template that renders it as the `draftReport` HTML. `reviewedReport` starts
   as a copy of `draftReport` (plan § 5).
3. **The worker job**: picks up each Submitted record, sends the business
   profile, the area answers and the analysis prompt to the Claude API, one
   call per area, writes `draftReport`, `reviewedReport`, `scores`,
   `analyzedAt` and the versions, and sets **Draft Ready**. **No contact
   details reach the Claude API**: no email addresses, phone numbers or street
   addresses; the company name and the business profile are allowed. A test
   proves it.
4. **Failure and Retry** (BE15): a failed call sets **Analysis Failed** and
   writes `analysisError`; a **Retry** button on the Evaluations tab, recorded
   through `core/action_log.py`, puts the record back in the queue. Buttons
   are never disabled.
5. **The mentor is notified** when a draft is ready. How is stopping point
   (a)'s question.
6. **Cost logging**: tokens and cost per call, as `comms/summarize.py` logs
   them.
7. **The draft on the Evaluations tab**, read-only, in the dialog that already
   shows the answers. Editing and approval are phase 4. **The draft report
   never reaches the client** (BE17): no code path emails, files or shows it
   to anyone but reviewers.
8. **Tests**: the schema, the template, the worker's pick-up and status
   changes, the contact-detail scrub, failure and Retry, the switch off.
9. **`OPEN-ITEMS.md` #83** updated.

**Stopping point (a).** Before building the worker (step 3), stop and put to
Doug: the Finance and Marketing analysis prompts and rubrics, and the report
template, written out in full; and how the mentor is notified that a draft is
ready (an email from the application, a CRM notification, or the tab alone),
with a recommendation. The prompts decide what every client's report says, so
they are Doug's decision.

After Doug's go-ahead, build steps 3 to 9.

**Stopping point (b)** (plan § 6): sample reports written by the worker from
made-up answers for both areas, on a local run against crm-test, shown to Doug
on the Evaluations tab as Joe Mentor. Close the phase only after Doug's review
of those reports.

## Not in this phase

The report editor, co-mentor editing and Approve (phase 4); release to the
client and action items as records (phase 5); the partner offering (phase 6);
the other four areas (phase 7); reading the client's website or competitors
(open question 3).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-13-26 13:58 | Claude (Claude Code) | Drafted at the close of phase 2, from the orchestrator and what phases 1 and 2 built. |
| 0.2 | 11-13-26 22:58 | Claude (Claude Code) | Revised at the close of phase 2b: the order note replaced; `surveys/CLAUDE.md` added to the reading; the files where the analysis joins renamed to the engine's (`surveys/answers.py`, `evaluation/purpose.py`, the engine's retry pass); the analysis stays in `evaluation/`. |
| 0.3 | 11-13-26 23:36 | Claude (Claude Code) | Approved by Doug. |
