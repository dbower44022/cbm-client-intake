# Kickoff prompt — lead and client enrichment, next session

Last Updated: 10-20-26 17:57 · Revision 0.5

Operating mode: DETAIL (this repository's project default).

Continue the lead and client enrichment arc in `prds/lead-enrichment/`.
Read `README.md`, then `design.md`. The design was approved by Doug on
10-20-26, section by section. Rulings E1 to E17 in § 1 are binding and
append only; record any new answer as E18 onward.

Phase 1 is built as v0.269.0 (committed, dark) except the grid columns.
crm-test carries the nine fit fields. Work in this order, one question per turn:

1. Confirm with Doug that no other session holds the prospect marketing arc
   (it allows one at a time), then add the Leads grid's Fit score, Service
   area and County columns, the score and gate filters and the export
   columns (`campaigns/leads.py` and its frontend), and the Review grid's
   *Out of area* filter. Build plan § 2, last two bullets.
2. Write the live-pass step page for crm-test: set `CHAPTER_COUNTIES` to
   `OH:Cuyahoga|OH:Lake` at `/setup`, switch `ENRICHMENT_FREE_PASS` on, the
   Operations job dry run then apply, a real non-admin Marketing Admin Team
   member on the Leads grid, then `ENRICHMENT_WEB_CHECKS` on.
3. Then build phase 2 (design § 8): the AI research pass measured on known
   clients.
4. § 9 question 6: which Business Status survey questions get real CRM
   fields. Elicit the questions from Doug first, never draft them for him.

Still owed by Doug, not by the session: the segment list (§ 9 question 2)
and the privacy-policy review (E7), which must read the AI model
provider's terms.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.5 | 10-20-26 17:57 | Claude (Claude Code) | Phase 1 built as v0.269.0; next is the grid columns, then the live pass. |
| 0.4 | 10-20-26 17:47 | Claude (Claude Code) | Counties answered (E17). |
| 0.3 | 10-20-26 17:38 | Claude (Claude Code) | The JSON check is done; next is the phase 1 plan review and the crm-test apply. |
| 0.2 | 10-20-26 17:27 | Claude (Claude Code) | Design approved; next steps are the JSON field check and the phase 1 build plan. |
| 0.1 | 10-20-26 15:42 | Claude (Claude Code) | Created at the end of the 10-20-26 design session. |
