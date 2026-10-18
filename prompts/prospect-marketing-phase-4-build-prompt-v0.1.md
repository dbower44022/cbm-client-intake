# Kickoff prompt — prospect marketing Phase 4: email and SMS campaigns, the funnel, the campaign dashboard

**Written 10-18-26 00:55 at the close of the Phase 3 build session, for a
fresh Claude Code session rooted in `cbm-client-intake`.** A build session:
the email kind, the SMS kind, the funnel metric on the *Campaigns* Analytics
page, the `COutreachCampaign` dashboard scope with its starter dashboard, and
`Opportunity` on attendance. Two flags inside `CAMPAIGNS_ENABLED`:
`CAMPAIGNS_EMAIL` and `CAMPAIGNS_SMS`. No CRM change in shape.

**The arc lives in `prds/prospect-marketing/`** — read its `README.md`
first, then `rulings.md` (binding, 1–37) and `build-plan.md` (v0.6).

Operating mode: DETAIL for the code.

---

## The gate

Phase 4 waits on two things. Check both before writing code, and stop and
say so if either is not met:

1. **Doug's Phase 3 live pass** (`OPEN-ITEMS.md` #51, step page
   https://claude.ai/artifact/D8atEqEdRaRBKh4mmxiPsj) reported complete, or
   Doug opens the gate explicitly, as he did for Phase 3.
2. **The email kind needs the mailing-list connection live on crm-test** —
   the Constant Contact Phase C build (v0.243.0/v0.244.0) and Doug's
   `MAILING-SETUP.md` §§ 2–4 live run. If that run is still owed, build the
   SMS kind, the funnel, the dashboard scope and `Opportunity` first, and
   put the email kind's order to Doug.

## The first thing in the session: question 11

Build plan § 9 question 11 (SMS sending) is unanswered and this phase builds
the screen it concerns. **Put it to Doug before writing any code**, as a
consequential decision (the eight-part template), then stop and wait. The
plan's recommendation: ship the kind with its selection rule, its list
export and *Mark as sent* — no sending provider. Record the answer as ruling
38 in `rulings.md`, dated, before building.

Questions 10 and 12 are open too; put them only if the build reaches them.

## The prompt

Read, in order:

1. This repo's `CLAUDE.md` — Conventions and the **Campaign Management**
   section, including the Phase 3 bullet (who acts under which credential,
   ruling 36's per-campaign gate, `campaigns/reporting.py` as the one home
   of every number).
2. `prds/prospect-marketing/build-plan.md` § 3.3 (the email kind), § 3.5
   (the SMS kind), § 6 (the funnel, the dashboard scope, Opportunity), § 7
   Phase 4 (the build list and the seven-step live verification).
3. `campaigns/calls.py` (the newest selecting kind: selection, build,
   sign-off, a list people work), `campaigns/postcard.py`,
   `campaigns/reporting.py`, `analytics/campaigns.py` (the *Campaigns* page
   the funnel joins), `analytics/records.py` (how a record scope and its
   starter dashboard are declared), `core/mailing_sync.py` (the push the
   email kind generalises to several lists),
   `prds/mailing-list-and-event-sponsorship-plan.md` § 11.

Build what § 7 Phase 4 lists, each piece green before the next. Tests for
every piece; the suite green; commit; do not push. Then write Doug's live
verification as a runbook page following the Step-by-Step Instructions
standard (one action per done box, the application and the tab named in
every step, every value pre-filled from a CRM read, click-to-copy entries,
a report-back line per section).

### Guardrails

- The names in the build plan are the names; the Analytics page is
  *Campaigns* (it exists since v0.261.0 — the funnel is a panel on it).
- A side exit is never written over another side exit.
- Every count comes from `campaigns/reporting.py`.
- Ruling 19: an email held without the opt-in tick is never emailed.
- Ruling 9: a text goes only to `cSmsOptIn` true.
- Nothing here needs a CRM shape change; a role grant goes through
  `scripts/migrate_outreach_roles.py` (merge-only) and the handoff's § 4
  table, and Doug runs its `--apply`.
- **One session on this arc at a time.** Check
  `git log -3 -- prds/prospect-marketing campaigns forms analytics` before
  writing; if another session touched them in the last hour, stop and say
  so. Parallel sessions share one git index: stage your own files by name.

### At the end of the session

State what is built and what is verified by tests only, and the runbook
page's address. Update `prds/prospect-marketing/README.md` *State*,
`OPEN-ITEMS.md` #51 and `CHANGELOG.md`; move this prompt to
`prds/prospect-marketing/history/prompts/` marked done; name the next
kickoff (Phase 5's deferred items, or the first real card). Remind Doug of
what the arc owes outside its code: production's CRM change at a Sunday
17:00 UTC slot (now including the Mentor Role's two grants of ruling 36),
Boston with its release, the sandbox seeder plus re-baseline, and questions
2, 4 and 5 before the first real card.

---

## Revision control

| Field | Value |
|---|---|
| Document | Kickoff prompt — prospect marketing Phase 4 build |
| Version | v0.1 |
| Last Updated | 10-18-26 00:55 |
| Prepared by | Claude (Claude Code), for D. Bower |

### Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| v0.1 | 10-18-26 00:55 | Claude (Claude Code) | Written at the close of the Phase 3 build session; gated on Doug's Phase 3 pass and the mailing-list connection on crm-test; question 11 made the session's first step. |
