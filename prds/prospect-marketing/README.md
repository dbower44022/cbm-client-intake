# Prospect marketing and Campaign Management

Last Updated: 10-17-26 02:20 · Revision 1.8 — change log at the end.

**Read this first if you are working on prospects or campaigns.** This
directory is the whole arc: the rulings, the build plan, and the record of
how they were reached. It is deliberately separate from the application's
other feature arcs, which each live in one plan document under `prds/`;
this one outgrew a single file on 10-14-26, when three sessions in one day
left three documents that disagreed. The repository's `CLAUDE.md` is the
anchor for *the application*; this file is the anchor for *this arc*.

## What the arc is

A chapter receives a filtered list of new businesses every month (an outside
process does the filtering), mails each one a postcard carrying a QR code,
and reads the scan, the landing page and the standard intake forms as the
business climbs a funnel from prospect to client. Around that sit the
Campaign Management application (marketing users create campaigns of five
kinds and the links that carry a campaign into the public forms), two import
doors, a call screen, an SMS consent tick, and the reporting that reads the
funnel. **Nothing of it is built. No CRM is changed. No vendor account
exists.**

## The documents, and what each one binds

| File | What it is | How it changes |
|---|---|---|
| `rulings.md` | **The binding record.** Rulings 1–27 and requirements CM-1 to CM-11, verbatim, with the ladder and the walk tables | Append only. A new decision is ruling 28 onward, dated |
| `build-plan.md` | **The one plan**, v0.2: the record model in Entity Manager vocabulary, the doors, the campaign engine, the landing page, conversion, reporting, five phases with their CRM handoffs and verification scripts, and § 9, the open questions | Revised in place with a change-log row. Never forked, never a second plan document |
| `history/prospect-marketing-plan.md` | The process plan, v0.6: the 2026-08-11 elicitation, the September funnel discussions, the 2026-10-13/14 walk and the 10-14-26 definition session, with every proposal, working position and strawman labelled | Frozen on 10-14-26. Read it for *why*; cite `rulings.md` for *what* |
| `history/prompts/` | The five kickoff prompts that produced the above, each marked done | Frozen |
| `history/prospect-marketing-funnel-2026-09-02.png` | Doug's funnel diagram, which the ladder table transcribes | Frozen |
| `prompts/prospect-marketing-phase-3-build-prompt-v0.1.md` (repository root) | **The live kickoff**: the Phase 3 build session (lists, review, calls), gated on Doug's Phase 2 live pass | Lives with the other kickoff prompts until it is spent, then moves here |

Where things live, by the house conventions: the two CRM handoffs at the
repository root (`contact-sms-opt-in-crm-handoff.md`,
`coutreach-entities-crm-handoff.md` — **written 10-14-26, nothing applied**),
their plan files under `scripts/plans/` (`contact-sms-opt-in.json`,
`coutreach-entities.json`), the role script `scripts/migrate_outreach_roles.py`,
and the code: the `campaigns/` package, `core/postal.py`, `core/qr.py`,
`forms/prospect_response/` and `frontend/shared/campaign-link.js` (**Phase 1
built 10-15-26, v0.258.0, dark behind `CAMPAIGNS_ENABLED`**).

## State, as of 10-17-26 02:20

- **Settled:** the process end to end (rulings 1–27), the Campaign
  Management application (CM-1 to CM-11), and the build's own rulings 28–34
  (custom entities; `Unverified`; multiple referring partners; links in the
  application database; `attributedPartnerProfiles`; the import's Company and
  Contact writes under the intake API client; **the information request
  door's company typed Prospect**, 10-17-26). None of it is reopened by any
  session.
- **Built:** Phase 1 (10-15-26, v0.258.0) — the Campaign Management tile,
  grid and record page (Overview / Links / Responses), links as short
  resolvable addresses with QR codes, the Prospects grid and the state-filing
  import, the postcard kind end to end with the dry-run vendor, the landing
  page and the `prospect-response` form kind, the partner's Campaigns tab,
  the SMS tick and the three hidden fields on every public door. Dark behind
  `CAMPAIGNS_ENABLED`. **Phase 2 (10-17-26, v0.259.0)** — the five doors
  honour the campaign id and the prospect id (`campaigns/attribution.py`),
  the engagement's `referringPartners` and the three union readers, the
  relabel at conversion (`merge_contact_type`), ruling 34 with its relabel
  script, the programme page's carry-through, the Responses tab's
  *Responded* / *Converted* and record links. Dark by nature: no id, no
  change. Verified by tests only.
- **Written:** the two CRM handoffs, their plan files and the role script
  (10-14-26 23:15, step 2 below); build plan v0.3 — v0.2 (10-14-26 22:09) revised against
  CM-1 to CM-11, then v0.3 (22:43) for Doug's answers to the four
  shape-changing questions (rulings 28–31): custom entities, `Unverified`,
  **multiple referring partners on an engagement** (against the
  recommendation — a many-to-many `referringPartners`, seventeen links in
  all), links in the application database. Eight questions stay open; none
  changes the CRM.
- **Owed, in this order:**
  1. ~~Doug answers the four questions that change the CRM's shape~~ —
     **done 10-14-26 22:41**, rulings 28–31.
  2. ~~The CRM handoff session~~ — **done 10-14-26 23:15**: the two
     handoffs, two plan files and the role script are written; crm-test dry
     runs clean (`contact-sms-opt-in` fingerprint `0bc7219ab932`, one
     change; `coutreach-entities` fingerprint `6b29c8928dcf`, 78 changes).
     Nothing applied. The one name the plan could not store as written
     (build plan § 1.5 named `COutreachCampaign.partnerProfiles` twice) is
     **ruled 10-15-26 — ruling 32, `attributedPartnerProfiles`**, build
     plan v0.4; the fingerprints stand. The handoff also
     decides `address` for the mailing address, names the wysiwyg
     conversion and the tab-list hand step, and observes that the Marketing
     Admin Role holds no Account grant (a Phase 1 build decision).
  3. ~~Doug applies on crm-test~~ — **done 10-15-26 01:06–01:19** (both
     plans, the notes conversion and the role script by Doug through
     `scripts/prospect_crm_test.sh`; the tab list and the detail/list
     layouts by Claude through the admin API; the shape, the org-key
     reads, the sync dry run and the conformance diff all passed; the
     address type was accepted). **The non-admin pass matched 10-15-26 01:49** (Doug as Mark
     Marketing and Sally Sponsor, step page
     https://claude.ai/artifact/ShmRGZgDWWfspETWuU86hQ). crm-test is
     complete and soaking to the Sunday slot.
  4. ~~The Phase 1 build session~~ — **done 10-15-26** (v0.258.0) and
     **live-passed on crm-test 10-15/17-26** (Doug, from the step page in
     `OPEN-ITEMS.md` #51; five fixes on the way, v0.258.1–.5, the API
     role's **edit** on the campaign among them).
  4a. ~~The Phase 2 build session~~ — **done 10-17-26** (v0.259.0; the
     spent prompt is in `history/prompts/`). **Next: Doug's Phase 2 live
     pass on crm-test** (the six steps of build plan § 7 Phase 2, the step
     page https://claude.ai/artifact/JLZyupBD4i6scAogws6sWD) and the relabel
     script's dry run;
     then production's CRM change at the Sunday slot (step 6); then the
     Phase 3 build session from
     `prompts/prospect-marketing-phase-3-build-prompt-v0.1.md`.
  5. **Before the first real card:** questions 2 (what the outside filter
     delivers), 4 (the mail vendor — Doug opens the account) and 5 (the card
     itself).
  6. **Production at the Sunday 17:00 UTC slot, Boston with its release**,
     and a seeder plus a sandbox re-baseline, because both handoffs add
     tables the nightly reset truncates.
- **Open and not blocking:** questions 6, 10, 11 and 12.

## Rules for working in this directory

- **One session writes here at a time.** On 10-14-26 three sessions worked
  the arc in one afternoon and evening; the build plan was revised in one
  while another was gated on the revision and a third rewrote the pointers.
  Parallel sessions share one git index. Before starting a session on this
  arc, check `git log -3 -- prds/prospect-marketing` and the memory note
  `prospect-marketing-rulings`, and close the other session first.
- **`rulings.md` holds Doug's words and nothing else.** A proposal, a
  working position or a strawman goes in the build plan, labelled, or in
  the session's own record under `history/`. A question answered in
  conversation is written to `rulings.md` in the same session, dated.
- **The build plan is the only plan.** A new requirement revises it (a new
  version, a change-log row, the sections named). It is never answered with
  a second plan document or a parallel section elsewhere.
- **The house rules apply to every screen in the arc** — build plan § 10
  lists them, and `CLAUDE.md` *Conventions* is their source.
- **Terminology.** A **rung** is a position on the funnel ladder; a **side
  exit** is a reason a record left it; a **touch** is one attempt to reach a
  business or person; a **door** is any place a record enters; **promotion**
  is the creation of a Company or Contact from a prospect record (ruling
  21); **conversion** is a relationship beginning through a standard intake
  form (ruling 22); a **campaign** is ours and a **notice** is a Constant
  Contact send (CM-11).

## Related

`prds/mailing-list-and-event-sponsorship-plan.md` (the notice vocabulary,
the Constant Contact push, the unbuilt Phase D whose button reads *Link a
notice*); `prds/chapter-network/crm-update-runbook.md` (how every CRM
change in the arc is applied); `forms/client_intake/orchestrator.py` (the
partner-link precedent for the campaign id); `core/crm_upsert.py` (the
null-fill rule, the website key, the one sanctioned relabel);
`research/registry-enrichment/enrichment-findings.md` (the filing data the
import contract starts from).

---

## Revision control

| Field | Value |
|---|---|
| Document | Prospect marketing — directory README |
| Version | 1.8 |
| Last Updated | 10-17-26 02:20 |
| Prepared by | Claude (Claude Code), for D. Bower |

### Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.8 | 10-17-26 02:20 | Claude (Claude Code) | State: Phase 2 built (v0.259.0), ruling 34; Doug's Phase 2 live pass is next, then the Sunday slot, then Phase 3; the live kickoff is the Phase 3 prompt. |
| 1.7 | 10-17-26 01:45 | Claude (Claude Code) | State: Phase 1 live-passed on crm-test; Phase 2 and the production slot are next. |
| 1.6 | 10-15-26 03:05 | Claude (Claude Code) | State: Phase 1 built (v0.258.0); the live pass is next; the live kickoff is Phase 2. |
| 1.5 | 10-15-26 01:50 | Claude (Claude Code) | State: the non-admin pass matched; crm-test complete and soaking; the Phase 1 build session is next. |
| 1.4 | 10-15-26 01:20 | Claude (Claude Code) | State: both handoffs applied on crm-test and verified as the org-wide key; the non-admin pass is the next step. |
| 1.3 | 10-15-26 00:02 | Claude (Claude Code) | State: item (a) ruled (ruling 32); the next step is the crm-test apply. |
| 1.2 | 10-14-26 23:15 | Claude (Claude Code) | State: the CRM handoff session done — two handoffs, two plan files, the role script, crm-test fingerprints; the `partnerProfiles` name collision put to Doug; the live kickoff is now the Phase 1 build prompt and the spent one is in `history/prompts/`. |
| 1.1 | 10-14-26 22:44 | Claude (Claude Code) | State: the four shape-changing questions answered (rulings 28–31, build plan v0.3); the next session is the CRM handoff. |
| 1.0 | 10-14-26 22:26 | Claude (Claude Code) | Created. Doug's ruling the same evening: consolidate the arc's three sessions' output into one directory on the chapter-network pattern. The process plan, the build plan, the funnel diagram and the three spent kickoff prompts moved here; `rulings.md` extracted; the live kickoff stays in `prompts/`. |
