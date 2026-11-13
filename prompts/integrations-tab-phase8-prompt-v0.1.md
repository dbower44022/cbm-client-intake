# Kickoff prompt — Integrations tab, phase 8: documentation and the live review

Last Updated: 11-13-26 17:45 · Revision 0.1 (draft) — see change log at the end.

**Draft.** Doug approves this prompt before the phase 8 session starts.
Paste everything below the line into a fresh Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake`.

---

## Kickoff

**Operating mode: DETAIL** (this repository's default). This prompt names
three stopping points. Between them the work proceeds without asking.

The first reply states the operating mode and the `CLAUDE.md` files loaded,
as the global rule requires. Open every reply with the local time from
`date`.

Read, in full, before any work:

- `prompts/integrations-tab-build-orchestrator-v0.1.md` and
  `prds/integrations-tab-plan.md`. **Rulings I1 to I13 and the decisions in
  the plan's change log are settled.** This phase is plan § 8, step 8.
- `OPEN-ITEMS.md` item 82: everything owed.
- `setup/CLAUDE.md`, `SYSTEM-SETTINGS-SETUP.md`, and `CHANGELOG.md` entries
  0.321.0 to 0.329.0.
- The `instruction-discipline` skill: the live review is run by Doug from a
  runbook page.

## Scope of this phase

1. **Documentation.**
   - `SYSTEM-SETTINGS-SETUP.md`: a section for the Integrations tab — the
     sub-tabs, the status line, Test Integration and the nightly run, the
     setup checklist and hand ticks, Diagnose with Claude, Set up with
     Claude, the monthly budget, the switch, and rollback (switch it off).
   - `setup/CLAUDE.md`: the rules a future session needs — the registry, the
     checks' contract (ok / failed / unknown, never raise, scrubbed), the
     step-file keys, `TAB_ONLY_KEYS`, the agent's snapshot and its no-secret
     rule, the checked save path used by plans, the coded-action contract.
     Keep the root `CLAUDE.md` under its 80,000-character limit: point to
     `setup/CLAUDE.md` rather than add to it.
   - The staff guide on the docs site, if `SYSTEM-SETTINGS-SETUP.md` has a
     published twin (`scripts/publish_docs.py`); a publish needs Doug's OK.
2. **The live review on crm-test**, as an administrator, from a runbook
   page: every sub-tab's test; the checklist and a hand tick on the History
   tab; one diagnosis and one setup plan run end to end, including one coded
   action; the morning's nightly run in the worker log; the switch off and
   on again. Record what passed, what failed and what it cost.
3. **The production decision**: what turning the tab on in production
   needs — the Anthropic key, the budget, who receives the nightly alert.

## Stopping point 1 — the documentation drafted

Show Doug the new and changed documents. Then stop.

## Stopping point 2 — the live review

Publish the runbook page, wait for Doug's results, fix what the review finds
(each fix its own commit), and report. Then stop.

## Stopping point 3 — before production

Put the production decision to Doug. Do not switch anything on in
production. Close the build as the orchestrator's **Closing a phase**
section requires; there is no next phase prompt.

## Things phases 2 to 7 learned

- **Another session may be working in the same checkout.** On 11-13-26 the
  Business Evaluation session had staged renames in the shared git index.
  Commit with an explicit path list (`git commit -- <paths>`), never
  `git add -A` or a bare `git commit`, and audit with `git show --stat`.
  Read `git log` for the current version first; it is in `pyproject.toml`
  and `uv.lock`.
- The first real diagnosis (crm-test, 11-13-26) cost $0.26 and took under a
  minute. The Integrations tab is on in crm-test's System Settings, and
  crm-test's Anthropic key is set there.
- The auto-mode classifier refuses reading the deployments' live specs; ask
  Doug when a fact depends on them.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 11-13-26 17:45 | Claude (Claude Code) | Draft written at the close of phase 7 (v0.329.0), from the orchestrator's rules and what phases 1 to 7 built. |
