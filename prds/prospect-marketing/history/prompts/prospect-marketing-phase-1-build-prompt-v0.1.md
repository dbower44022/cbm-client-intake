# Kickoff prompt — prospect marketing Phase 1: one real card, one real scan

**DONE 10-15-26 03:05.** Spent by the session that ran it: v0.258.0, the
`campaigns/` package, `core/postal.py`, `core/qr.py`,
`forms/prospect_response/`, the hidden fields and SMS tick on every public
door, the partner's Campaigns tab, the worker run, migration 0031, 36 tests;
rulings 32 and 33 recorded on the way. Dark behind `CAMPAIGNS_ENABLED`.
Doug's live pass is owed from the step page in `OPEN-ITEMS.md` #51. Next
kickoff: `prompts/prospect-marketing-phase-2-build-prompt-v0.1.md`.

**Written 10-14-26 23:15. For a fresh Claude Code session rooted in
`cbm-client-intake`.** A build session: it produces the `campaigns/` package,
the `forms/prospect_response/` form, the postcard pipeline with a dry-run
vendor client, the SMS tick on the public forms, and the Phase 1 live
verification script — all dark behind `CAMPAIGNS_ENABLED`. It changes no CRM
and opens no vendor account.

**The arc lives in `prds/prospect-marketing/`** — read its `README.md`
first, then `rulings.md` (binding) and `build-plan.md` (v0.3, the one plan).

Operating mode: DETAIL for the code; the plan's decisions are made, so the
session discusses mechanics one consequential thing at a time, not the
model.

---

## The gate: the CRM change must be on crm-test first

Phase 1 reads and writes `CProspect`, `COutreachCampaign` and
`COutreachTouch`, the four stage fields, `Contact.cSmsOptIn` and the
seventeen links. Before writing code, confirm all of it is on crm-test:

1. `coutreach-entities-crm-handoff.md` § 0 reads *Done* for crm-test, with
   item (a) — the `partnerProfiles` name — ruled by Doug and the ruled name
   in build plan § 1.5 and § 1.10.
2. `contact-sms-opt-in-crm-handoff.md` § 0 reads *Done* for crm-test.
3. `GET /CProspect?maxSize=1`, `COutreachCampaign`, `COutreachTouch` as the
   org-wide key answer 200 (handoff § 5 step 2).

If any of the three is not true, **stop and say so** — the apply is Doug's
step from the handoffs, not this session's. Every CRM read in the code
still feature-detects its field or link from metadata, so production (which
takes the change at a Sunday slot) stays dark with a logged note rather than
500ing.

## The prompt

Read, in order:

1. This repo's `CLAUDE.md` — the Conventions in full (busy.js first, buttons
   never disabled, `CBMDateTime`, `CBMRichText`, the `{{org}}` and
   `{{abbr}}` tokens, action logging at the router, feature detection,
   best-effort side effects) and the Session Management section for the
   house shape of a staff tool.
2. `prds/prospect-marketing/build-plan.md` v0.3: § 1 (the model), § 2.1–2.2
   (the state-filing import and the already-known check), § 3.1, § 3.2, § 3.6
   and § 3.7 (the engine, the postcard kind, the social kind, the links),
   § 3.8 (the screens), § 4 (the landing page), § 7 Phase 1 (the build list,
   the flags and the fourteen-step live verification), § 10 (the house
   rules).
3. `coutreach-entities-crm-handoff.md` § 0 items (b), (g), (h) and (i) —
   the address sub-field names, the decided defaults, the currency
   companion, and the Marketing Admin Role's missing Account grant, which
   this session decides: the import's Company creates run under the intake
   API client (the quick-add precedent, v0.249.1) or the role gains Account
   create and read. Put it to Doug as a consequential decision before
   building the import.
4. The precedents named in build plan § 7 Phase 1 and § 10: the partner
   intake link (`forms/client_intake/orchestrator.py`, v0.255.0) for the
   hidden fields and the validate-or-drop read; `core/crm_upsert.py` for
   the null-fill rule and `website_key`; `sessions/` for the grid, record
   page and `DomainConfig` shape; `events/` for a feature that ships dark
   behind a flag and feature detection.

Build what § 7 Phase 1 lists, in this order, each step green before the
next: the migrations and the link tables; the resolve route and the QR
generator; the Campaign Management tile, grid and record page with Overview,
Links and Responses; the social media kind; the Prospects grid and the
state-filing import with the already-known check; the postcard kind end to
end with `core/postal.py` and its dry-run client; the landing page and
`forms/prospect_response/`; the partner's Campaigns tab (CM-5); the SMS tick
on the six public doors; the hidden values captured and ignored at delivery.
Then write the live verification as a step page for Doug — the fourteen
steps of § 7 Phase 1, as Mark Marketing and signed out, in the house format.

Tests for every piece; the suite green; commit; do not push.

### Guardrails

- The names in the build plan and the handoff are the names.
- Nothing chapter-specific in any string; every page carries the tokens.
- Dark by default: `CAMPAIGNS_ENABLED` off, `POSTAL_PROVIDER=dryrun`,
  `POSTAL_TEST_MODE=true`. **Never a real vendor call** in this session.
- **One session on this arc at a time.** Check
  `git log -3 -- prds/prospect-marketing campaigns` before writing; if
  another session touched either in the last hour, stop and say so.
- Phase 2 (the doors honouring the ids) is not this session; the hidden
  values are captured and ignored.

### At the end of the session

State what is built, what is verified by tests only, and the step page's
address. Update `prds/prospect-marketing/README.md` *State*, `OPEN-ITEMS.md`
#51 and `CHANGELOG.md`; move this prompt to
`prds/prospect-marketing/history/prompts/` marked done; name the next
kickoff (Phase 2, after Doug's live pass).

---

## Revision control

| Field | Value |
|---|---|
| Document | Kickoff prompt — prospect marketing Phase 1 build |
| Version | v0.1.1 |
| Last Updated | 10-15-26 03:05 |
| Prepared by | Claude (Claude Code), for D. Bower |

### Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| v0.1.1 | 10-15-26 03:05 | Claude (Claude Code) | Marked done and moved to `prds/prospect-marketing/history/prompts/`. |
| v0.1 | 10-14-26 23:15 | Claude (Claude Code) | Written at the close of the CRM handoff session; gated on the crm-test apply and the item (a) ruling. |
