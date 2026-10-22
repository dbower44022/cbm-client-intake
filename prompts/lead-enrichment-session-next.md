# Kickoff prompt — lead and client enrichment, next session

Last Updated: 10-22-26 11:19 · Revision 0.9

Operating mode: DETAIL (this repository's project default).

Continue the lead and client enrichment arc in `prds/lead-enrichment/`.
Read `README.md`, then `design.md`. The design was approved by Doug on
10-20-26, section by section. Rulings E1 to E17 in § 1 are binding and
append only; record any new answer as E18 onward.

Phase 1 is built (v0.269.0, v0.270.1) and live-passed on crm-test
10-21-26. Phase 2, the AI research pass started by staff, is built as
v0.274.0 (rulings E18, E19; `prds/lead-enrichment/build-plan-phase-2.md`),
dark behind `ENRICHMENT_AI`; crm-test carries `CEnrichmentFinding` and its
grants. The staff test is the step page
https://claude.ai/artifact/JePeP4H6XSGY4PnXsUVKgV (sections A to E). Its test
data on crm-test (removed by the nightly reset; re-create if needed): leads
Great Lakes Brewing Company, Superelectric Pinball Parlor, Banter Beer and
Wine (batch "AI research live pass 10-22-26"), and the client Mitchell's
Homemade Ice Cream (Account, CClientProfile, CEngagement
6ada291ac5727bcbe — ids change on re-creation; the engagement needs
mentoringNeedsDescription). When Doug sends "pushed", check crm-test's
/healthz reads 0.274.0. After each section, read the findings back
(`CEnrichmentFinding`), the run costs (`enrichment_run_item`), and for E13
that the accepted person's Contact has no marketing opt-in.

Then: the list button (when the lists feature is on and its session agrees),
production's two CRM changes at a Sunday slot, and § 9 question 6 (Business
Status survey fields; elicit them from Doug first).

Still owed by Doug, not by the session: the segment list (§ 9 question 2)
and the privacy-policy review (E7), which must read the AI model
provider's terms.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.9 | 10-22-26 11:19 | Claude (Claude Code) | Phase 2 built; the staff-test page and its test data. |
| 0.8 | 10-21-26 13:54 | Claude (Claude Code) | Phase 1 live-passed; next is phase 2. |
| 0.7 | 10-21-26 09:56 | Claude (Claude Code) | Second live-pass attempt: what Claude does at each report-back. |
| 0.6 | 10-20-26 18:12 | Claude (Claude Code) | Grid columns built; the live-pass step page and what Claude does at each report-back. |
| 0.5 | 10-20-26 17:57 | Claude (Claude Code) | Phase 1 built as v0.269.0; next is the grid columns, then the live pass. |
| 0.4 | 10-20-26 17:47 | Claude (Claude Code) | Counties answered (E17). |
| 0.3 | 10-20-26 17:38 | Claude (Claude Code) | The JSON check is done; next is the phase 1 plan review and the crm-test apply. |
| 0.2 | 10-20-26 17:27 | Claude (Claude Code) | Design approved; next steps are the JSON field check and the phase 1 build plan. |
| 0.1 | 10-20-26 15:42 | Claude (Claude Code) | Created at the end of the 10-20-26 design session. |
