# Kickoff prompt — write the prospect marketing CRM handoffs

**Written 10-14-26 17:34; gated 10-14-26 21:55. For a fresh Claude Code session rooted in
`cbm-client-intake`.** A handoff-writing session: it produces the two CRM
handoff documents, their plan files and the role script that Phase 1 of the
build plan needs. It builds no application code, changes no CRM and opens no
vendor account. Applying the plan files to crm-test is Doug's step, from the
runbook, after the handoffs are reviewed.

Operating mode: ARCHITECTURE.

---

## Before anything: two answers this session needs from Doug

**Gate added 10-14-26 21:55: do not run this session until build plan v0.2
exists.** The Campaign Management requirements (plan section *Requirements —
Campaign Management application (10-14-26)*, CM-1 to CM-11) change the
campaign entity's kinds, add partner and event links and a link record, so
a handoff written from v0.1 would build the wrong entity.

Read `prds/prospect-marketing-build-plan.md` § 9 first. Two of its questions
change what the handoff says, so ask for them in the first reply and write
nothing until they are answered:

- **Question 1** — custom entities (the plan's recommendation) or EspoCRM's
  own Lead and Campaign. The handoff below assumes custom; the other answer
  is a different session.
- **Question 3** — rung 1's stored enum value, `Unverified` (recommended) or
  `Unqualified`.

Questions 2, 4, 5, 6 and 7 do not change the CRM shape and can stay open
(question 6 may add a Mentor Role grant later; note it as owed).

## The prompt

Use the `espo-crm-changes` skill from the first step. Read, in order:

1. This repo's `CLAUDE.md`, the Gotchas on EspoCRM behaviour and the
   Conventions on feature detection.
2. `prds/prospect-marketing-build-plan.md` § 1 in full — every entity,
   field and link is specified there with its stored name — and § 7 Phase 1
   for the grants and the two file names.
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
   them (rung 1 per question 3), all fifteen links of § 1.5 in plan-file form
   (`link` on `entity`, `linkForeign` on `entityForeign`, never the dialog's
   inverted boxes), the four stage fields on Contact and Account, and the
   `Prospect` option added to `Account.cCompanyType`. Decide and state how
   the `mailingAddress` field is built: test whether the applier accepts the
   `address` type on crm-test with a dry run; if it does not, four varchars
   named in the handoff. Every `currency` field names its companion.
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

### At the end of the session

State the two fingerprints, the files written, what Doug applies and in
which order (crm-test, verify, soak, production at the Sunday slot, Boston
with its release), and name the next kickoff: the Phase 1 build session.

---

## Revision control

| Field | Value |
|---|---|
| Document | Kickoff prompt — prospect marketing CRM handoffs |
| Version | v0.1.1 |
| Last Updated | 10-14-26 21:55 |
| Prepared by | Claude (Claude Code), for D. Bower |

### Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| v0.1.1 | 10-14-26 21:55 | Claude (Claude Code) | Gate added: waits for build plan v0.2 (the Campaign Management requirements). Duplicated date fixed. |
| v0.1 | 10-14-26 17:34 | Claude (Claude Code) | Written at the close of the 2026-10-14 planning session (build plan v0.1). |
