# Resume prompt — the Ambassador Program

Last Updated: 11-21-26 23:27 · Revision 1.0 — see change log at the end.

Paste the block below into a new Claude Code session rooted in
`~/Dropbox/Projects/cbm-client-intake`.

```
Operating mode: DETAIL. Resume the Ambassador Program (session of 11-21-26).

Read first, in this order:
1. prds/Ambassador Program/ambassador-program-decisions.md — decisions AM1 to AM10, all approved.
2. prds/Ambassador Program/ambassador-program-prd.md — § 15 records where the build differs.
3. ambassador/CLAUDE.md — the rules kept for the package.
4. OPEN-ITEMS.md item 91 — what is owed, in order.

State on 11-21-26 23:27: v0.360.0 to v0.364.1 are pushed and live on the Business Mentors
Association's system (the test system), which runs v0.364.1 with the program switched on.
Doug's runbook passed; v0.360.1 (analytics dates) and v0.360.2 (review-list writes under the
key) fixed what it found; the referral's applied half passed; the portal signs in through the
shared box (v0.361.0, checked by Doug). CRM build: applied on the Association's CRM and on
crm-test; production, Boston and Lakeside not yet. Production has the code but the switch is
off and its CRM lacks CAmbassadorActivity.

Owed, in order (confirm each with Doug before starting):
1. Doug's demo setup page https://claude.ai/artifact/2d9dcVirER5puhCJTgUwLt — part A (push) is
   done; parts B (the four training sign-ins, adding "Ambassador program team" for
   mark.marketing@bma.test) and C (open /courses/ambassador-demo) are Doug's. Then a test user
   runs the course; it is draft 0.1 until then.
2. Publish ambassador-program-overview.md and ambassador-program.md to the docs site: a new
   book, then entries in scripts/publish_docs.py; each publish needs Doug's OK.
3. Production rollout at a Sunday 17:00 UTC slot: crm-plans/ambassador.json and
   scripts/migrate_ambassador_roles.py from inside production's web container
   (ambassador-activity-crm-handoff.md), then Doug switches it on.
4. crm-test re-baseline sitting: scripts/sandbox/enrich_training_data.py --apply the morning after
   a reset, then Doug's droplet purge-deleted and baseline (SANDBOX-RESET.md).
5. The Association's baseline re-capture (#87) now also holds the Ambassador records.

Claude Code's safety check refuses this session's git pushes: give Doug the two lines to run
with "!" instead.
```

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 11-21-26 23:27 | Claude (Claude Code) | Created at the close of the 11-21-26 session. |
