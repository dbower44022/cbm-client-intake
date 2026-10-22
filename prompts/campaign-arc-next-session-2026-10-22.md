# Kickoff — campaign arc, after campaign lists (next session)

Last Updated: 10-22-26 12:12 · Revision 1.0 — change log at the end.

Operating mode: ARCHITECTURE (the global default). Read
`prds/prospect-marketing/README.md` first, then `rulings.md` (rulings 1–70
are binding) and build plan § 7c.

## Where things stand (10-22-26)

- **Campaign lists, build plan § 7c, rulings 58–68 — built and live-passed on
  crm-test.** L1 v0.270.0 (passed 10-21-26 15:36, page
  https://claude.ai/artifact/2jDCeJN96LR2cHvA2Mddro); L2 v0.271.0 (passed
  10-21-26 22:30, page https://claude.ai/artifact/BcETZsL5hFi3h9Bpm3wNUd).
  `CAMPAIGN_LISTS` is ON for crm-test only (a `/setup` override).
- **v0.272.0** — the status badge with a ▾ on the partner and funder Overview
  (Doug's request 10-21-26); live on both deployments, checked on crm-test.
- **v0.273.0, ruling 70** — an engagement's close date is stamped when it
  closes. `CEngagement.closeDate` was Read-only on crm-test AND production
  (every write dropped, no engagement dated). Cleared on crm-test 10-22-26
  00:30 and live-checked as Joe Mentor (page
  https://claude.ai/artifact/HNia1sYdcjHCmce2eRq19J).
- Every version through v0.273.0 is pushed. Two docs-only commits may be
  local — `git log origin/main..main`.

## What is owed

1. **The backfill question (ruling 70).** Production has 7 Completed
   engagements and no close date on any. First check, read-only, whether
   the CRM's history records when each engagement's status changed
   (`engagementStatus` audited? its stream notes "Status changed from … to
   …" posted by `sessions.service.set_status` since v0.272.0 — older ones
   may not exist). Then put the question to Doug: backfill from history,
   leave empty for staff to fill, or both.
2. **The production slot for the arc — deferred by Doug until campaign
   testing is finished** (10-20-26 15:06). Do not schedule it on your own.
   When Doug opens it, the CRM list for production (each from inside the
   web container, `--production --expect <fingerprint>`):
   - the lead model plans and value move (`coutreach-lead-model-crm-handoff.md`);
   - `scripts/plans/coutreach-funders.json` (`4658d1450804`, ruling 57);
   - `scripts/plans/cprospect-industry.json` (`82ec87c36dce`, ruling 66) —
     compare production's `Account.cIndustrySector` options first;
   - `scripts/plans/csponsor-funder-status.json` (`84636d15191f`, ruling 67);
   - `scripts/plans/cengagement-close-date-writable.json` (`c80d9070da1d`, ruling 70);
   - the role scripts: `migrate_outreach_roles.py` (rulings 54, 69).
   Boston takes the same with its release (`scripts/apply_plan.sh boston …`).
3. **Sandbox re-baseline.** Lead `industry`, `funderStatus` and the writable
   close date survive the nightly reset as empty values; demo data for them
   needs the outreach seeder and a recapture (`SANDBOX-RESET.md`).

## Traps learned this arc (also in the CLAUDE.md files)

- Untyped Contacts are stored as `[""]`; `arrayIsEmpty` misses them —
  "No type" ORs in `arrayAnyOf [""]`.
- `CClientProfile.linkedCompany` is hasOne: walk it backwards through
  `Account.cClientProfileId`.
- The org key cannot create `COutreachCampaign` on crm-test; prepare test
  campaigns as the CRM configuration admin (`scripts/run_with_admin.py`).
- A step page names WHERE each expected result appears on screen
  (Doug 10-21-26).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 10-22-26 12:12 | Claude (Claude Code) | Written at the close of the campaign lists session. |
