# Kickoff prompt — lead and client enrichment, next session

Last Updated: 10-26-26 11:56 · Revision 1.0

Operating mode: DETAIL (this repository's project default).

Continue the lead and client enrichment arc in `prds/lead-enrichment/`.
Read `README.md`, then `design.md`. The design was approved by Doug on
10-20-26, section by section. Rulings E1 to E17 in § 1 are binding and
append only; record any new answer as E18 onward.

State at 10-26-26 11:56, read before anything else:

- Phase 1, the fit score: v0.269.0 / v0.270.1, live-passed on crm-test
  10-21-26, dark in production.
- Phase 2, the AI research pass: v0.274.0, pushed, dark behind
  `ENRICHMENT_AI`; crm-test carries `CEnrichmentFinding` and its grants.
  The real model ran on crm-test on 10-22-26 and led to v0.277.1 (a finding
  never proposes a value the record already holds). How much of the staff
  test page https://claude.ai/artifact/JePeP4H6XSGY4PnXsUVKgV was completed
  is NOT recorded — ask Doug first.
- Other sessions have since built on `enrichment/` (the Marketing
  Management redesign: AI research on every Review row, `close_findings`,
  ruling 121). Read `git log -- enrichment/` and the root `CLAUDE.md`
  before editing; one session on that arc at a time.
- crm-test's nightly reset empties `CEnrichmentFinding` (a table newer than
  the sandbox baseline) and removes the test leads and the test client.
  Re-create them for a pass (`enrichment-finding-crm-handoff.md`; the
  engagement needs `mentoringNeedsDescription`).

Work in this order, one question per turn:

1. Ask Doug how far the staff test got; finish and record the rest
   (`OPEN-ITEMS.md` #58).
2. Production's two CRM changes at a Sunday slot (`lead-fit-score-crm-handoff.md`
   § 4, `enrichment-finding-crm-handoff.md` § 4) — write the step page when
   Doug books it.
3. The list button, when the lists feature's session agrees.
4. § 9 question 6: which Business Status survey questions get real CRM
   fields. Elicit them from Doug first.

Still owed by Doug, not by the session: the segment list (§ 9 question 2)
and the privacy-policy review (E7), which must read the AI model
provider's terms.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 10-26-26 11:56 | Claude (Claude Code) | End-of-session state: what ran, what other sessions changed, what is owed. |
| 0.9 | 10-22-26 11:19 | Claude (Claude Code) | Phase 2 built; the staff-test page and its test data. |
| 0.8 | 10-21-26 13:54 | Claude (Claude Code) | Phase 1 live-passed; next is phase 2. |
| 0.7 | 10-21-26 09:56 | Claude (Claude Code) | Second live-pass attempt: what Claude does at each report-back. |
| 0.6 | 10-20-26 18:12 | Claude (Claude Code) | Grid columns built; the live-pass step page and what Claude does at each report-back. |
| 0.5 | 10-20-26 17:57 | Claude (Claude Code) | Phase 1 built as v0.269.0; next is the grid columns, then the live pass. |
| 0.4 | 10-20-26 17:47 | Claude (Claude Code) | Counties answered (E17). |
| 0.3 | 10-20-26 17:38 | Claude (Claude Code) | The JSON check is done; next is the phase 1 plan review and the crm-test apply. |
| 0.2 | 10-20-26 17:27 | Claude (Claude Code) | Design approved; next steps are the JSON field check and the phase 1 build plan. |
| 0.1 | 10-20-26 15:42 | Claude (Claude Code) | Created at the end of the 10-20-26 design session. |
