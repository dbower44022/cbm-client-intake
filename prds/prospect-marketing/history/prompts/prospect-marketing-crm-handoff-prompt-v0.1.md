# Kickoff prompt — write the prospect marketing CRM handoffs

**DONE 10-14-26 23:15.** Spent by the session that ran it the same evening:
`contact-sms-opt-in-crm-handoff.md` (fingerprint `0bc7219ab932`) and
`coutreach-entities-crm-handoff.md` (78 changes, fingerprint `6b29c8928dcf`)
at the repository root, their plan files under `scripts/plans/`,
`scripts/migrate_outreach_roles.py`, two fingerprint pins in
`tests/test_apply_crm_plan.py`. Nothing applied. One name in build plan § 1.5
could not be stored as written (`COutreachCampaign.partnerProfiles` named
twice) and is put to Doug in that handoff's § 0 item (a). Next kickoff:
`prompts/prospect-marketing-phase-1-build-prompt-v0.1.md`.

**Written 10-14-26 17:34; revised 10-14-26 22:44. For a fresh Claude Code session
rooted in `cbm-client-intake`.** A handoff-writing session: it produces the
two CRM handoff documents, their plan files and the role script that Phase 1
of the build plan needs. It builds no application code, changes no CRM and
opens no vendor account. Applying the plan files to crm-test is Doug's step,
from the runbook, after the handoffs are reviewed.

**The arc lives in `prds/prospect-marketing/`** — read its `README.md`
first, then `rulings.md` (binding) and `build-plan.md` (v0.2, the one
plan). The process plan under `history/` is the discussion record, not a
source for names or shapes.

Operating mode: ARCHITECTURE.

---

## The gate is open: the four shape-changing questions are answered

Build plan § 9 questions 1, 3, 8 and 9 were answered by Doug on 10-14-26
at 22:41 and are **rulings 28–31 in `rulings.md`**: custom entities; rung 1
stored `Unverified`; **multiple referring partners on an engagement** (the
recommendation was declined — `CEngagement.referringPartners`, a
many-to-many to `CPartnerProfile`, reverse `referredEngagements`, build plan
v0.3 § 1.5 and § 5 step 6a); campaign links in the application's database.
Nothing to ask first. Questions 2, 4, 5, 6, 7, 10, 11 and 12 stay open and
do not change the CRM's shape (question 6 may add a Mentor Role grant
later; note it as owed).

## The prompt

Use the `espo-crm-changes` skill from the first step. Read, in order:

1. This repo's `CLAUDE.md`, the Gotchas on EspoCRM behaviour and the
   Conventions on feature detection.
2. `prds/prospect-marketing/build-plan.md` (v0.3) § 1 in full — every entity,
   field and link is specified there with its stored name (§ 1.3 the kinds
   and `platform`, § 1.5 the seventeen links, § 1.10 the prefix check) — and
   § 7 Phase 1 for the grants and the two file names.
3. `prds/chapter-network/crm-update-runbook.md` §§ 3 and 7.
4. `.claude/skills/espo-crm-changes/references/api-contract.md` for the
   plan-file format, and `references/writing-manual-instructions.md` for the
   handoff rulebook.
5. The two fullest existing examples: `cevent-presenters-crm-handoff.md`
   with `scripts/plans/cevent-presenters.json`, and
   `cgrant-entities-crm-handoff.md`. Match their shape.

Produce, at the repository root and under `scripts/plans/`:

1. **`contact-sms-opt-in-crm-handoff.md`** and
   **`scripts/plans/contact-sms-opt-in.json`** — one bool on Contact,
   `smsOptIn` typed unprefixed, stored `cSmsOptIn`, default false, label and
   tooltip naming texts. The handoff's grants section lists every role that
   edits Contact and says how to confirm the field is not stripped by a
   `fieldData` rule (read each role's `fieldData` as admin).
2. **`coutreach-entities-crm-handoff.md`** and
   **`scripts/plans/coutreach-entities.json`** — the three entities
   (`Prospect`, `OutreachCampaign`, `OutreachTouch`, typed without the `C`),
   every field of § 1.2–1.4 with the enum options exactly as the plan lists
   them (rung 1 is `Unverified`, ruling 29), **all seventeen links of § 1.5**
   in plan-file form (`link` on `entity`, `linkForeign` on `entityForeign`,
   never the dialog's inverted boxes) — fourteen many-to-one and the three
   many-to-many (`partnerProfiles` to `CPartnerProfile`, `events` to
   `CEvent`, and `CEngagement.referringPartners` to `CPartnerProfile`,
   ruling 30) — the four stage fields on Contact and Account,
   and the `Prospect` option added to `Account.cCompanyType`. Decide and
   state how the `mailingAddress` field is built: test whether the applier
   accepts the `address` type on crm-test with a dry run; if it does not,
   four varchars named in the handoff. Every `currency` field names its
   companion.
3. **`scripts/migrate_outreach_roles.py`** — the grants of § 7 Phase 1 for
   the intake API role and the Marketing Admin Role (Assignment Permission
   `all` on the latter), dry-run by default, idempotent, admin-type asserted,
   modelled on `scripts/migrate_presenter_roles.py`. Roles are API-writable
   as admin; do not write hand steps for them.
4. In each handoff: a verification section with the exact requests —
   `GET /Metadata` → `entityDefs.<Entity>` for the shape, `GET /<Entity>?maxSize=1`
   as the org-wide key for the grant, and the one real non-admin check — and a
   note that both handoffs add tables the training sandbox truncates nightly
   until a re-baseline.

Run the applier's **dry run only** against crm-test for both plan files and
paste the fingerprints into the handoffs. Do not apply. Commit; do not push.

### Guardrails

- The names in the build plan are the names. Do not rename; if a name
  cannot be stored as written, say why and put it to Doug.
- Nothing chapter-specific in any name, label or option.
- Additive only — nothing is removed or narrowed.
- **One session on this arc at a time.** Check
  `git log -3 -- prds/prospect-marketing` before writing; if another
  session touched the directory in the last hour, stop and say so.

### At the end of the session

State the two fingerprints, the files written, what Doug applies and in
which order (crm-test, verify, soak, production at the Sunday slot, Boston
with its release), and name the next kickoff: the Phase 1 build session.
Update `prds/prospect-marketing/README.md` *State* and `OPEN-ITEMS.md` #51,
and move this prompt to `prds/prospect-marketing/history/prompts/` marked
done.

---

## Revision control

| Field | Value |
|---|---|
| Document | Kickoff prompt — prospect marketing CRM handoffs |
| Version | v0.1.5 |
| Last Updated | 10-14-26 23:15 |
| Prepared by | Claude (Claude Code), for D. Bower |

### Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| v0.1.5 | 10-14-26 23:15 | Claude (Claude Code) | Marked done and moved to `prds/prospect-marketing/history/prompts/`; the outputs and the one open name named at the top. |
| v0.1.4 | 10-14-26 22:44 | Claude (Claude Code) | Gate open: questions 1, 3, 8 and 9 answered (rulings 28–31); the seventeenth link (`CEngagement.referringPartners`) named; rung 1 fixed as `Unverified`. |
| v0.1.3 | 10-14-26 22:28 | Claude (Claude Code) | Paths follow the consolidation into `prds/prospect-marketing/`; the gate section rewritten as one list of the four shape-changing questions (1, 3, 8, 9), each answer recorded as a ruling; "fifteen links" corrected to sixteen with the two many-to-many named; the one-session rule and the end-of-session bookkeeping added. |
| v0.1.2 | 10-14-26 22:09 | Claude (Claude Code) | Gate met (build plan v0.2); questions 8 and 9 added to the answers needed first; the read list points at v0.2's changed sections. |
| v0.1.1 | 10-14-26 21:55 | Claude (Claude Code) | Gate added: waits for build plan v0.2 (the Campaign Management requirements). Duplicated date fixed. |
| v0.1 | 10-14-26 17:34 | Claude (Claude Code) | Written at the close of the 2026-10-14 planning session (build plan v0.1). |
