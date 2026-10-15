# Kickoff prompt — write the prospect marketing build plan

> **Done — history.** This kickoff was run and its product is recorded; it was
> moved here on 10-14-26 when the arc was consolidated into
> `prds/prospect-marketing/`. Paths below predate the move; start at the
> directory's `README.md`.

**Written 10-14-26 17:18; revised 10-14-26 21:55. For a fresh Claude Code
session rooted in `cbm-client-intake`.** This is a planning session, not a
build session and not a discussion session. The process is ruled end to end;
the job now is to turn the rulings into a build plan with phases, a CRM
handoff list and a verification script, in the shape the other plan
documents in `prds/` have.

**State as of 10-14-26 22:09: both sessions this prompt describes have run.**
The build plan was written (v0.1, 17:34) and revised against the Campaign
Management requirements (v0.2, the same evening); it stands at
`prds/prospect-marketing-build-plan.md` with twelve questions in its § 9.
**Running this prompt again is not the next step.** The next step is the
CRM handoff session, `prompts/prospect-marketing-crm-handoff-prompt-v0.1.md`,
once questions 1, 3, 8 and 9 are answered. Keep this prompt as the record of
how the plan was produced; if the plan ever needs a v0.3 against new
requirements, run it again with a new *Read first* item naming them.

Operating mode: ARCHITECTURE.

---

## The prompt

The prospect marketing process is designed and ruled. The design is in
**`prds/prospect-marketing-plan.md`**, whose final section, *Rulings — the
source-by-source walk (2026-10-13/14)*, holds rulings 9–27 and the two tables
(the ladder, the per-source walk). Your job is to write **the build plan** for
it as a new section of that document, or as a sibling document if it grows
past a section, and to produce the CRM handoff list it needs. You build
nothing. You change no CRM. You open no vendor account.

### Read first

1. This repo's `CLAUDE.md` in full. Note the Conventions section (the
   `{{org}}` token, `busy.js`, `CBMDateTime`, action logging, feature
   detection) — every new screen must follow them, and the plan must say so.
2. `prds/prospect-marketing-plan.md` — all of it. **Rulings 1–8 (2026-08-11)
   and 9–27 (2026-10-13/14) are settled; do not reopen them.** Everything
   between those two sections is the record of what was proposed on the way
   and is superseded where it conflicts — in particular the
   `CProspect`-as-funnel storage section (replaced by ruling 21), the
   `source` proposal (replaced by ruling 26) and the reach idea (withdrawn).
3. `prds/chapter-network/crm-update-runbook.md` — a prospect entity and a
   campaign entity are CRM changes and go through it, crm-test first, then
   production at the Sunday slot, then Boston with its release.
4. `forms/client_intake/orchestrator.py` and `core/crm_upsert.py` — how a
   submission creates Account, Contact, profile and engagement today, the
   null-fill rule, the website-key comparison (the already-known check of
   ruling 12 and the domain rule of ruling 21 reuse it), and the referring
   partner write (v0.255.0), which is the precedent for the campaign id
   (rulings 26–27).
5. `forms/event_registration/orchestrator.py` — the Contact-typed-Prospect
   path that ruling 21 keeps as is, and the "never relabel" rule that the
   Prospect-to-type relabel at conversion will be the one exception to.
6. `core/mailing_sync.py` — the opted-in-only rule ruling 19 relies on.
7. `prds/mailing-list-and-event-sponsorship-plan.md` § on Constant Contact
   — the campaign entity must not collide with Constant Contact's own
   campaigns in name or meaning; decide and say which word the UI uses.
8. **`prds/prospect-marketing-plan.md`, section *Requirements — Campaign
   Management application (10-14-26)*** — Doug's requirements CM-1 to
   CM-11 for the application marketing users create campaigns and links
   in, gathered one question at a time after the build plan's first
   version. **They are Doug's and are not reopened.** They settle item 7's
   word (Campaign; a Constant Contact send is a notice), the kinds (SMS and
   social media added), partners and events on a campaign, what a link is
   and looks like, the campaign-page / Analytics split, and where the tool
   lives. The section ends with what v0.1 must change, by section.

### What the plan must contain

Work in this order and keep each as its own heading.

1. **The record model, in Entity Manager vocabulary** (see the
   `espo-crm-changes` skill and `crm-specs-use-entity-manager-terms`):
   the prospect record (ruling 21 — quarantine, business and/or person,
   rung, entry rung, qualified-by, side exit, link to the promoted Company
   and Contact), the campaign entity and its links (ruling 26), the touch
   record (campaign, date, channel, outcome, stamped rung), the SMS consent
   tick on Contact (ruling 9), the campaign id on each relationship record
   and on Contact and Company (ruling 27), and the Prospect type's relabel.
   Decide where the rung continues after promotion (a field on Company and
   Contact, or read through the link) and say why. Every entity, field and
   link named exactly as EspoCRM will store it — recall the three prefix
   rules.
2. **The import doors**: the state-filing import (enters Qualified, ruling
   11, already-known check at import, ruling 12), the list import (enters
   Unverified, staff review, ruling 18), the specialised partner-file import
   deferred (ruling 23). What each accepts, in what format, from where —
   the open question on the outside filter's delivery must be put to Doug
   as a question in the plan, not answered for him.
3. **Campaigns**: the entity, the marketing-user screen that creates one
   and its links, the three campaign kinds (postcard, email, call), each
   kind's selection rule written out (rulings 10, 19, 20), the approval gate
   (ruling 13), one card per company (ruling 14), the vendor callback for
   undeliverable returns (ruling 15), and the call-recording screen (ruling
   20 — the one hand-recorded touch). Where the campaign kinds share one
   engine and where they differ.
4. **The postcard landing page** (`/p/<token>` or whatever the plan names
   it): shows only what is printed on the card (ruling 16), collects
   corrections, email, phone and both consents, offers Info Request and
   Request a Mentor carrying both the prospect id and the campaign id into
   the standard forms. The scan alone moves the rung (ruling 16). Which
   Contact and Company get created at which moment (ruling 21 for email and
   domain, ruling 22 for a relationship).
5. **Conversion**: what each standard form does when it receives a prospect
   id and a campaign id — reuse the Contact, create the Company, link the
   prospect record, copy nothing (consents already live on the Contact),
   write the campaign id per ruling 27, and relabel Prospect to the new
   type. The dormant-client campaign (ruling 25) as a selection rule, not a
   rung.
6. **Reporting**: the funnel read as a union of prospect records and
   promoted records; touches by campaign; entry rung per source. Which of
   these are Analytics metrics and which need a screen.
7. **Phases**, each shippable dark behind a flag per the deployment gate in
   `CLAUDE.md`, with the CRM handoff each phase needs listed first, and the
   live-verification script for each as a real non-admin in the relevant
   team. Phase 1 should be the smallest thing that mails one real card and
   records one real scan.
8. **The open list** from the plan's 2026-10-13/14 section, each item either
   answered by this plan with its reasoning, or put to Doug as a numbered
   question at the end.

### How to run the session

- ARCHITECTURE mode: decide routine choices and present them as drafts;
  surface only decisions that pass the two-part test in `CLAUDE.md`, one at
  a time, in prose, with a recommendation and its cost.
- Verify a premise before building on it: read the code, or query crm-test
  read-only, before asserting how something behaves today.
- Executive register throughout; Terminology Precision wins where they
  conflict.
- The plan carries a revision table and a change log (Last Updated in
  MM-DD-YY HH:MM). Commit; do not push.

### Guardrails

- No code, no CRM changes, no vendor accounts.
- Do not reopen rulings 1–27. If a ruling cannot be implemented as stated,
  say exactly why, in a sentence, and put the question to Doug.
- Chapter-network vocabulary: nothing Cleveland-specific in an entity,
  field, link or rung name.
- No page width caps; every button always clickable; every date field the
  shared control; every wysiwyg field the shared editor.

### At the end of the session

State what the plan decided, the numbered questions for Doug, and the CRM
handoff files the build will need (named, not written). If the next step is
the CRM handoff, write its kickoff prompt as
`prompts/prospect-marketing-crm-handoff-prompt-v0.1.md`.

---

## Revision control

| Field | Value |
|---|---|
| Document | Kickoff prompt — prospect marketing build plan |
| Version | v0.3 |
| Last Updated | 10-14-26 22:09 |
| Prepared by | Claude (Claude Code), for D. Bower |

### Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| v0.3 | 10-14-26 22:09 | Claude (Claude Code) | Both sessions done (build plan v0.1 and v0.2); the state note now points at the CRM handoff prompt as the next step. |
| v0.2 | 10-14-26 21:55 | Claude (Claude Code) | The build plan now exists (v0.1.1); the session's job becomes v0.2 against the Campaign Management requirements. *Read first* item 8 added. |
| v0.1 | 10-14-26 17:18 | Claude (Claude Code) | Written at the close of the 2026-10-13/14 discussion session, which ruled the process end to end (plan v0.4 draft, rulings 9–27). |
