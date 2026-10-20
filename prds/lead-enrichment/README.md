# Lead and client enrichment

Last Updated: 10-20-26 17:38 · Revision 1.1

This directory holds the design of the enrichment system: finding out what
kind of business a lead or a client is, its website, its email, and its key
contacts, and ranking leads by how likely they are to be a fit for the
chapter's services.

Start with `design.md`. It records Doug's rulings from the 10-20-26 session
(E1 to E16) and the design built on them, approved section by section the
same day. Two questions remain open in its § 9.

Then `build-plan-phase-1.md` (draft): the free pass and the fit score, with
its CRM handoff `lead-fit-score-crm-handoff.md` at the repository root.

## Related directories

- `prds/prospect-marketing/` owns the lead record (`CProspect`), the lead
  model (rulings 41 to 54) and the Leads and Review grids (ruling 56). This
  design adds a fit score and enrichment to the lead. It does not change the
  lead model. Where the two disagree, the prospect marketing rulings win
  until a ruling here says otherwise.
- `research/registry-enrichment/enrichment-findings.md` is the 201-record
  research pass that shapes the verification rule (design § 3).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.1 | 10-20-26 17:38 | Claude (Claude Code) | Points to the phase 1 build plan and its handoff. |
| 1.0 | 10-20-26 17:27 | Claude (Claude Code) | Design approved; ruling count E16. |
| 0.8 | 10-20-26 17:25 | Claude (Claude Code) | Ruling count updated to E15. |
| 0.7 | 10-20-26 15:54 | Claude (Claude Code) | Ruling count updated to E14. |
| 0.6 | 10-20-26 15:50 | Claude (Claude Code) | Ruling count updated to E13. |
| 0.5 | 10-20-26 15:49 | Claude (Claude Code) | Ruling count updated to E12. |
| 0.4 | 10-20-26 15:41 | Claude (Claude Code) | Ruling count updated to E11. |
| 0.3 | 10-20-26 15:40 | Claude (Claude Code) | Ruling count updated to E10. |
| 0.2 | 10-20-26 15:38 | Claude (Claude Code) | Ruling count updated to E9. |
| 0.1 | 10-20-26 15:12 | Claude (Claude Code) | Created with the strawman design. |
