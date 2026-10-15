# Kickoff prompt — prospect marketing Phase 2: the doors honour the ids

**Written 10-15-26. For a fresh Claude Code session rooted in
`cbm-client-intake`.** A build session: the five orchestrators honour the
campaign id, the link token and the prospect id that Phase 1 captures; the
engagement gains its referring partners from the campaign (ruling 30, CM-4);
the relabel at conversion (ruling 21, § 1.9); the programme-page
carry-through; the Responses tab's record links. No CRM change (the links
shipped with Phase 1's handoff). Dark by nature: no id, no change.

**The arc lives in `prds/prospect-marketing/`** — read its `README.md`
first, then `rulings.md` (binding, 1–33) and `build-plan.md` (v0.4).

Operating mode: DETAIL for the code.

---

## The gate: Phase 1's live pass has matched

Do not start until `OPEN-ITEMS.md` #51 records Doug's Phase 1 live pass on
crm-test as matched (step page linked there) and v0.258.0 or later is live.
If it does not, **stop and say so**.

## The prompt

Read, in order:

1. This repo's `CLAUDE.md` — the Conventions and the Campaign Management
   section.
2. `prds/prospect-marketing/build-plan.md` § 5 (conversion, every door and
   step 6a), § 1.7, § 1.9, § 3.7 (the carry-through), § 7 Phase 2 (the build
   list and the six-step live verification).
3. `forms/client_intake/orchestrator.py` (the partner-link precedent and the
   `_valid_referring_partner` validate-or-drop read), `core/crm_upsert.py`
   (`merge_company_type` — the relabel rule goes beside it as
   `merge_contact_type`), `campaigns/config.py` (the payload keys),
   `campaigns/public.py` (what a link's redirect carries).

Build what § 7 Phase 2 lists: the five orchestrators (client intake, info
request, event registration, partner, sponsor) writing `outreachCampaign` on
the relationship record every time and on the Contact and Company only when
that submission created them (ruling 27), after a validate-or-drop read of
the campaign; step 6a — the engagement's `referringPartners` from the
campaign's partners plus the partner link's partner, the single
`referringPartner` written only by a partner's own link, the popup band and
the Referred Clients tab reading the union; `merge_contact_type` and the
relabel at conversion; the programme page's carry-through of `campaign` and
`link` to every event address it renders; the information request's Company
typed Prospect (question 7 — put it to Doug first); the notes lines; the
Responses tab's record links and *responded* / *converted* counts.

Tests for every piece; the suite green; commit; do not push. Then write
Doug's live verification as a step page — the six steps of § 7 Phase 2.

### Guardrails

- The names in the build plan are the names.
- An unknown or stale campaign id drops the attribution, never the
  submission.
- **One session on this arc at a time.** Check
  `git log -3 -- prds/prospect-marketing campaigns forms` before writing.

### At the end of the session

Update `prds/prospect-marketing/README.md` *State*, `OPEN-ITEMS.md` #51 and
`CHANGELOG.md`; move this prompt to `prds/prospect-marketing/history/prompts/`
marked done; name the next kickoff (Phase 3).

---

## Revision control

| Field | Value |
|---|---|
| Document | Kickoff prompt — prospect marketing Phase 2 build |
| Version | v0.1 |
| Last Updated | 10-15-26 03:05 |
| Prepared by | Claude (Claude Code), for D. Bower |

### Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| v0.1 | 10-15-26 03:05 | Claude (Claude Code) | Written at the close of the Phase 1 build session; gated on Doug's Phase 1 live pass. |
