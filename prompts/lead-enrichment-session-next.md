# Kickoff prompt — lead and client enrichment, next session

Last Updated: 10-20-26 17:38 · Revision 0.3

Operating mode: DETAIL (this repository's project default).

Continue the lead and client enrichment arc in `prds/lead-enrichment/`.
Read `README.md`, then `design.md`. The design was approved by Doug on
10-20-26, section by section. Rulings E1 to E16 in § 1 are binding and
append only; record any new answer as E17 onward.

Work in this order, one question per turn:

1. Get Doug's review of `prds/lead-enrichment/build-plan-phase-1.md` (draft)
   and the chapter's counties for `CHAPTER_COUNTIES`.
2. Doug applies the CRM change on crm-test:
   `scripts/enrichment_crm_test.sh fitscore` (`lead-fit-score-crm-handoff.md`
   § 2, fingerprint `8e57af53eef5`); Claude verifies (§ 3).
3. Build phase 1 as the plan says, dark, with tests; then the live pass.
4. § 9 question 6: which Business Status survey questions get real CRM
   fields. Elicit the questions from Doug first, never draft them for him.

Still owed by Doug, not by the session: the segment list (§ 9 question 2)
and the privacy-policy review (E7), which must read the AI model
provider's terms.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.3 | 10-20-26 17:38 | Claude (Claude Code) | The JSON check is done; next is the phase 1 plan review and the crm-test apply. |
| 0.2 | 10-20-26 17:27 | Claude (Claude Code) | Design approved; next steps are the JSON field check and the phase 1 build plan. |
| 0.1 | 10-20-26 15:42 | Claude (Claude Code) | Created at the end of the 10-20-26 design session. |
