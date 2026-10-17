# Kickoff prompt — prospect marketing Phase 2: the doors honour the ids

**Written 10-15-26; revised 10-17-26 01:49 for a fresh Claude Code session
rooted in `cbm-client-intake`.** A build session: the five orchestrators
honour the campaign id, the link token and the prospect id that Phase 1
captures; the engagement gains its referring partners from the campaign
(ruling 30, CM-4); the relabel at conversion (ruling 21, § 1.9); the
programme-page carry-through; the Responses tab's record links. No CRM
change (the links shipped with Phase 1's handoff). Dark by nature: no id,
no change.

**The arc lives in `prds/prospect-marketing/`** — read its `README.md`
first, then `rulings.md` (binding, 1–33) and `build-plan.md` (v0.4).

Operating mode: DETAIL for the code.

---

## The gate is open

Phase 1 (v0.258.0–v0.258.5) is live on crm-test and production, dark behind
`CAMPAIGNS_ENABLED`, and **Doug's Phase 1 live pass on crm-test ran on
10-15/17-26 and is recorded as complete** in `OPEN-ITEMS.md` #51, with the
five fixes it found. The live build is v0.258.6 or later. Nothing to wait
for.

## The first thing in the session: question 7

Build plan § 9 question 7 is unanswered and this phase touches the door it
concerns. **Put it to Doug before writing any code**, as a consequential
decision (the eight-part template), then stop and wait. The analysis, already
checked against `forms/info_request/orchestrator.py` on 10-17-26:

- Today the information request door creates a new Company typed **Client**
  with `cClientStatus=Prospect` (a nearest fit from before a Prospect type
  existed on Companies), and a matched company gains the Client type.
- **Option A (recommended):** create it typed **Prospect**, `cClientStatus`
  untouched — the shape the landing page and the import produce — so the
  relabel at conversion (append the relationship type, remove Prospect) is
  one rule for every door. Cost: a live door changes what it writes; the
  companies it created before keep the old shape unless a one-time,
  dry-run-first script relabels them (write it; Doug runs it); staff
  filtering Companies by the Client type stop seeing information-request
  companies there until they become clients.
- **Option B:** keep Client. Cost: a special case in the relabel rule, and
  ruling 21's vocabulary holds for two doors out of three.

Record the answer as ruling 34 in `rulings.md`, dated, before building.

## The prompt

Read, in order:

1. This repo's `CLAUDE.md` — the Conventions and the **Campaign Management**
   section (the standing rules Phase 1 set, including who acts under which
   credential).
2. `prds/prospect-marketing/build-plan.md` § 5 (conversion, every door and
   step 6a, the per-door table), § 1.7, § 1.9, § 3.7 (the programme-page
   carry-through), § 7 Phase 2 (the build list and the six-step live
   verification).
3. `forms/client_intake/orchestrator.py` (the partner-link precedent:
   `_valid_referring_partner`, the notes line), `core/crm_upsert.py`
   (`merge_company_type` — the relabel rule goes beside it as
   `merge_contact_type`), `campaigns/config.py` (the payload keys
   `campaign_id` / `campaign_link` / `prospect_id`), `campaigns/public.py`
   (what a link's redirect carries), `forms/prospect_response/orchestrator.py`
   (how Phase 1 promotes and links a prospect record — reuse its shape),
   `core/forms.py` (`BaseSubmission` holds the three fields).
4. The readers of the referring partner that must take the union of the
   single `referringPartner` and the many `referringPartners`:
   `assignments/` (the popup's *Referred by* band, v0.256.0),
   `sessions/` (the partner's Referred Clients tab,
   `DomainConfig.referred_clients_link="engagements"`), and `analytics/`
   (any engagement metric filtering on a referring partner — grep
   `referringPartner`).

Build what § 7 Phase 2 lists, each piece green before the next:

1. **The five orchestrators** (client intake, info request, event
   registration, partner, sponsor): `_valid_campaign` and `_valid_prospect`
   (validate-or-drop reads; failure drops the id, never the submission);
   `outreachCampaign` written on the relationship record every time and on
   the Contact and Company **only when that orchestrator's find-or-create
   returned `created`** (ruling 27); the prospect record's `promotedCompany`
   used by id before any name match, and its promotion links set if empty;
   the rung evidence per door (info request and registration: `cFunnelStage`
   Warm Lead on the Contact, advance-only); the notes line *"Arrived through
   the campaign <name>."*
2. **Step 6a on the engagement** (CM-4, ruling 30): `referringPartners`
   holds every referring partner — the partner link's partner when one
   arrived, plus every partner the campaign names — written by relate under
   the intake API client; the single `referringPartner` stays the partner
   link's own; a notes line *"Referring partners set from the campaign
   <name>: <names>."* Then the three readers take the **union**,
   deduplicated by engagement.
3. **`merge_contact_type` and the relabel at conversion** in
   `core/crm_upsert.py`: appending Client, Partner, Sponsor or Mentor removes
   Prospect; Presenter, Member, Donor and Administrator leave it. Every door
   that appends a type goes through the two functions. Plus question 7's
   answer in the information request door.
4. **The programme page's carry-through**: `/webinars/?campaign=&link=`
   appends both to every event address it renders, the event page's form
   and the calendar modal already carry them (Phase 1). Honest limit: a
   visitor who types an event's address afresh has left the campaign.
5. **The Responses tab**: record links through to the engagement (Client
   Administration), the information request (Submission Admin), the
   registration (Event Administration); *responded* / *converted* counts.
6. **Submission Admin's form filter** (`ops/frontend/app.js` `FORMS`) gains
   `prospect-response` and `event-registration` — a follow-up the Phase 1
   pass noted.

Tests for every piece; the suite green; commit; do not push. Then write
Doug's live verification as a step page — the six steps of § 7 Phase 2 —
**naming the application or window AND the tab in every step** (Doug,
10-17-26: a bare tab or grid name is unusable with several applications, the
CRM and a private window open; the memory note `steps-name-the-app-and-the-tab`).

### Guardrails

- The names in the build plan are the names.
- An unknown or stale campaign id drops the attribution, never the
  submission. A stale prospect id likewise.
- Nothing here needs a CRM change; if something seems to, stop and say so.
- The applier's `--apply`, the role script's `--apply` and any mutating SSH
  are refused to Claude by the session classifier — Doug runs those with the
  `!` prefix; `scripts/prospect_crm_test.sh` is the one-word wrapper.
- **One session on this arc at a time.** Check
  `git log -3 -- prds/prospect-marketing campaigns forms` before writing;
  if another session touched them in the last hour, stop and say so.

### At the end of the session

State what is built, what is verified by tests only, and the step page's
address. Update `prds/prospect-marketing/README.md` *State*, `OPEN-ITEMS.md`
#51 and `CHANGELOG.md`; move this prompt to
`prds/prospect-marketing/history/prompts/` marked done; name the next
kickoff (Phase 3 — lists, review, calls). Remind Doug of what Phase 1 still
owes outside this arc's code: production's CRM change at a Sunday 17:00 UTC
slot (both plans, the receipt option, the role script with its seventh
grant, the notes conversion, the tab list, the three entities' layouts —
`coutreach-entities-crm-handoff.md` § 7), Boston with its release, and the
sandbox seeder plus re-baseline.

---

## Revision control

| Field | Value |
|---|---|
| Document | Kickoff prompt — prospect marketing Phase 2 build |
| Version | v0.2 |
| Last Updated | 10-17-26 01:49 |
| Prepared by | Claude (Claude Code), for D. Bower |

### Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| v0.2 | 10-17-26 01:49 | Claude (Claude Code) | Gate open (the Phase 1 live pass ran 10-15/17-26); question 7 made the session's first step, with the analysis checked against the door's code; the readers of the referring-partner union named; the step-page rule (name the app and the tab) and the classifier note added; the Submission Admin form-filter follow-up folded in. |
| v0.1 | 10-15-26 03:05 | Claude (Claude Code) | Written at the close of the Phase 1 build session; gated on Doug's Phase 1 live pass. |
