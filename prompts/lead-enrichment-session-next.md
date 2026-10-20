# Kickoff prompt — lead and client enrichment, next session

Last Updated: 10-20-26 18:12 · Revision 0.6

Operating mode: DETAIL (this repository's project default).

Continue the lead and client enrichment arc in `prds/lead-enrichment/`.
Read `README.md`, then `design.md`. The design was approved by Doug on
10-20-26, section by section. Rulings E1 to E17 in § 1 are binding and
append only; record any new answer as E18 onward.

Phase 1 is built in full as v0.269.0 (committed, dark). crm-test carries
the nine fit fields and two throwaway test leads (removed by the nightly
reset). The live pass is the step page
https://claude.ai/artifact/9kfsFpHL13WEQxT4yo8Wmh (sections A to F). When
Doug sends "pushed", check crm-test's /healthz reads 0.269.0; when he sends
"web checks on", create the crm-test lead Great Lakes Brewing Company
(2516 Market Ave, 44113, Unqualified, Lead Source List) under the org key;
after F8, read that lead's website and fit fields back.

Then, one question per turn: build phase 2 (design § 8, the AI research pass
measured on known clients), and § 9 question 6 (which Business Status survey
questions get real CRM fields; elicit them from Doug first).

Still owed by Doug, not by the session: the segment list (§ 9 question 2)
and the privacy-policy review (E7), which must read the AI model
provider's terms.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.6 | 10-20-26 18:12 | Claude (Claude Code) | Grid columns built; the live-pass step page and what Claude does at each report-back. |
| 0.5 | 10-20-26 17:57 | Claude (Claude Code) | Phase 1 built as v0.269.0; next is the grid columns, then the live pass. |
| 0.4 | 10-20-26 17:47 | Claude (Claude Code) | Counties answered (E17). |
| 0.3 | 10-20-26 17:38 | Claude (Claude Code) | The JSON check is done; next is the phase 1 plan review and the crm-test apply. |
| 0.2 | 10-20-26 17:27 | Claude (Claude Code) | Design approved; next steps are the JSON field check and the phase 1 build plan. |
| 0.1 | 10-20-26 15:42 | Claude (Claude Code) | Created at the end of the 10-20-26 design session. |
