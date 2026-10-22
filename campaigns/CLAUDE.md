# campaigns/ — Campaign Management

Last Updated: 10-22-26 13:00 · Revision 1.4

Detail for Campaign Management (`/campaigns`, prospect marketing Phases 1 to 4 and the lead model): links, postcards, the landing page, imports, the Leads and Review grids, calls, texts, email, attribution and reporting.

Claude Code loads this file only when a session reads or edits files in this
folder. The rules other packages depend on stay in the root `CLAUDE.md`, which
also points here. Moved word for word from the root file on 10-20-26, when it
outgrew Claude Code's size limit; edit it here from now on.

## Campaign Management — `/campaigns`

Marketing Admin Team (`CAMPAIGNS_ALLOWED_TEAMS`), behind **`CAMPAIGNS_ENABLED`**
(off; read **per request**, so a `/setup` flip needs no restart — the routers
mount with the staff stack and answer 404 while off). Prospect marketing
Phase 1 (v0.258.0, 10-15-26); the arc is `prds/prospect-marketing/` (its
`README.md` first; `rulings.md` 1–33 binding; `build-plan.md` v0.4). Package
`campaigns/` in the house shape. **Needs the Phase 1 CRM change**
(`coutreach-entities-crm-handoff.md`, `contact-sms-opt-in-crm-handoff.md`):
every read feature-detects `CProspect` / `COutreachCampaign` / `COutreachTouch`
and the campaign's links, and a CRM without them answers *not available* with
the reason.

- **Who acts:** campaign reads and writes run as the signed-in user (the
  Marketing Admin Role creates/reads/edits the three entities). Aggregates and
  machine writes — the postcard selection and its Planned touches, the import's
  already-known reads and its Company/Contact creates (**ruling 33**), the
  counts on the partner's Campaigns tab — run under the **org-wide API key**.
  Relating a campaign to a partner needs edit on the partner, which that role
  lacks by ruling, so `service._link_or_escalate` retries only a
  `noAccessToForeignRecord` denial as the admin account.
- **The owner is the campaign's Assigned User** (ruling 76, v0.275.0): set
  to the creator at create, changed only through
  `PUT …/campaigns/{id}/owner`, which accepts an active member of the
  `CAMPAIGNS_ALLOWED_TEAMS` teams (`service.owner_options`, org-wide key) and
  writes as the user. `assignedUserId` stays off `CAMPAIGN_FIELDS`, so the
  general save can never move it.
- **Links live in the application database** (ruling 31; `campaigns/store.py`,
  migration 0031: `campaign_link`, `campaign_link_visit`, the import ledger).
  `GET /c/{token}` **never calls the CRM**: it counts the visit and 302s to the
  destination with `?campaign=&link=`. A token that resolves to nothing is a 404
  in the same words whatever the reason; a **retired link still opens** and its
  visit is flagged late; an event link's slug is cached and refreshed whenever
  staff open the Links tab. A postcard's per-card code is `/c/{link}/{scan}`,
  its QR PNG `…/qr.png` (`core/qr.py`, `segno`).
- **The postcard kind** (`campaigns/postcard.py`): *Build the list* selects
  under rulings 10, 14 (one card per business, ever — any Sent/Delivered/
  Returned postcard touch from any campaign excludes the target) and 15 (a dead
  address is skipped), reconciles this campaign's Planned touches (kept /
  created / Cancelled) and moves Draft → Awaiting sign-off. *Sign off and run*
  needs the **typed piece count** (ruling 13), stamps the campaign and sets
  **Signed off, which is the worker's queue** (`run_campaign_cycle`, every
  `CAMPAIGNS_RUN_SECONDS`): each Planned touch becomes a vendor piece with the
  **touch id as the idempotency key**, then Sent with `scanToken`,
  `mailedAddress` (the snapshot) and `stageAtTouch`; Complete when none is left.
  The vendor is `core/postal.py` — `DryRunPostalClient` by default (nothing
  printed, `dryrun-<touch id>`), `LobPostalClient` written from the published
  API and **never run**. Delivery events arrive signed at
  `POST /api/campaigns/postal/events` (404 until `POSTAL_WEBHOOK_SECRET` is
  set); a returned piece marks the **address** dead and leaves the rung
  (ruling 15). In dry run a staff *Simulate* button posts the same event.
- **The landing page `/p/{token}`** (`campaigns/landing.py`, behind
  `CAMPAIGNS_LANDING_PUBLIC`): the scan writes `firstScannedAt` once,
  `scanCount`, outcome Scanned and moves the record to **Lead, advance-only**
  (ruling 16); a Planned touch is a preview and writes nothing. The page shows
  **only what the card printed** — the business name and the address as mailed
  — never an email, phone or person's name the chapter holds. Its response is
  the sixth form kind, `forms/prospect_response/` (delivery-only, scoped
  duplicate hold by `scan_token`, `company_keys` for the `held_company` hold):
  email promotes the person, website the business (ruling 21), consent
  **true-only**, never a relationship record. A mentor or information request
  then opens the standard form with `?prospect=&campaign=&link=`; the typed
  details travel in `sessionStorage` only, and `GET /api/campaigns/prospect/{id}`
  serves the printed facts alone.
- **Every public form carries `campaign_id`, `campaign_link`, `prospect_id`**
  (declared on `core/forms.BaseSubmission` — an undeclared key is dropped by
  capture) and the **SMS tick** `sms_consent` → `Contact.cSmsOptIn`, true-only
  (ruling 9). **Honoured at delivery since Phase 2 (v0.259.0)** — the next
  bullet. The shared
  `frontend/shared/campaign-link.js` fills the hidden fields, shows the banner
  from the name-only lookup `GET /api/campaigns/public/{id}` and prefills the
  printed facts. The GET rate limit covers `/c/` and `/api/campaigns/public/`.
- **The import** (`campaigns/imports.py`): plan, then apply; the file is read
  in the browser and posted as text (no multipart); the already-known check is
  Company by name **and** postal code, Company by website key, Contact by email
  (ruling 12) — a match still creates the prospect record, with the *Already
  known* side exit; a re-upload of the same file is a no-op through the ledger.
- **Funders on a campaign** (v0.268.0, ruling 57): `cfg.LINK_FUNDERS`
  (`funderProfiles` ↔ `CSponsorProfile.sponsoredCampaigns`), a picker
  beside Partners, and Funder Management's Campaigns tab
  (`DomainConfig.sponsored_campaigns_link` on both domains now).
  Feature-detected (`service.funders_available`). **Not**
  `COutreachCampaign.sponsorProfiles` — that is ruling 27's attribution
  reverse. Funders get no CM-4 credit.
- **The import at volume** (v0.267.2): the already-known check reads the
  whole file in batches (`imports.KnownIndex`, ~30 reads for 800 rows), and
  the page applies 100 rows per request until `remaining` is 0 — never put
  a per-row CRM call back into the plan, and never one request for a whole
  apply (61.6 s and a timed-out page, 10-20-26).
- **The Leads and Review grids at volume** (v0.267.0, build plan § 7b,
  Doug's five answers 10-20-26): `campaigns/leads.py` — the CRM searches,
  sorts and counts a page at a time (never load every lead; the old list
  stopped silently at 2,000); bulk Disqualify / Do Not Contact over ticked
  rows or all matching (cap 2,000, batches of 50, each lead re-read and
  skipped if changed since seen); a CSV export; Review as a queue whose row
  takes the website or email and qualifies in one step. **Every decision
  carries what the reviewer saw (`seenStatus` / `seenExit`) and a change
  since answers 409 naming who** — keep that on any new review action.
- **The partner's Campaigns tab** (CM-5): `DomainConfig.sponsored_campaigns_link`
  on the partner domain only, the Events-tab shape exactly.
- **Phase 2 — the public forms honour the ids** (v0.259.0, 10-17-26; build plan
  § 5). One module, `campaigns/attribution.py`, serves the five
  orchestrators (client intake, information request, event registration,
  partner, sponsor): a **validate-or-drop** read of the campaign and of the
  prospect record (unknown, stale, cancelled, forged, or a CRM without the
  link ⇒ the attribution is dropped with a logged note, never the
  submission — every write feature-detects its link or field, so
  production until its Sunday slot behaves exactly as before); the campaign
  on the **relationship record every time** (`outreachCampaignId`) and on
  the Contact and Company (`cOutreachCampaignId`) **only when that
  orchestrator created them** (ruling 27 — on a registration, the create
  only, so a repeat sign-up keeps the first); a prospect record's
  **promoted company used by id before any name match**, its promotion
  links set if empty; the rung as evidence, advance-only (information
  request and registration ⇒ Warm Lead on the Contact, the entry stage
  written once on a new record; a client has no stored rung — Candidate is
  read from the engagement); the notes line *"Arrived through the campaign
  <name>."*. **Step 6a (ruling 30):** the engagement's `referringPartners`
  holds EVERY referring partner — the partner link's partner plus every
  partner the campaign names — related after the create; the single
  `referringPartner` is the partner link's own and is never written by a
  campaign; the three readers (the popup's *Referred by* band, the
  Referred Clients tab via `engagements` + `referredEngagements`, the
  Partner Analytics metrics) take the **union**, deduplicated by
  engagement. **The relabel at conversion is one rule** (§ 1.9):
  `core/crm_upsert.merged_types` — appending Client, Partner, Sponsor or
  Mentor removes `Prospect`, nothing else is ever removed; both
  `merge_company_type` and the new `merge_contact_type` apply it, and
  `merge_contact_type` is the ONE reason a public form touches a matched
  contact's type (the information request and registration forms never do).
  **Ruling 34:** the information request form creates its company typed `Prospect`,
  `cClientStatus` untouched, a matched company left alone (it used to gain
  Client), feature-detected with the old shape as the fallback;
  `scripts/relabel_info_request_companies.py` (dry-run default) relabels
  the old-shape companies once per CRM — Doug runs it. **The carry-through:**
  the programme page appends `?campaign=&link=` to every event address it
  renders (`CBMEvents.config.eventUrlQuery`); a freshly typed address has
  left the campaign. **The Responses tab** leads with *Responded* /
  *Converted* (`campaigns/router.summarize_responses`) and links through:
  `/assignments/?engagement=<id>` opens the popup, `/events/?event=<id>`
  the event (both new deep links), partner / funder record pages,
  Submission Admin for an information request.
- **Ruling 37 (v0.260.2):** the information request and registration
  forms never write a stage on a record that already holds a relationship
  type — `attribution.holds_relationship`, checked inside `advance_rung`, so
  every caller must SELECT the type field (`cContactType` / `cCompanyType`).
- **Phase 3 — lists, review, calls** (v0.261.0, 10-18-26; dark behind
  **`CAMPAIGNS_CALLS`**, read per request). The **Review** tab
  (`campaigns/review.py`): *Qualify* / *Unqualified* (note required) on an
  Unverified record, *Do Not Contact*, *Not the same company* (clears
  *Already known* and `alreadyKnownCompany`, the link under the API
  client); **no side exit is ever written over another**. **The call kind**
  (`campaigns/calls.py`): a promoted prospect record IS its Contact; *Sign
  off* starts the list at once (no worker) and the last recorded row
  completes it. **Who calls is ruling 36**: the members of the teams named
  on the campaign (its own `teams`, set by the form's *Who calls* picker;
  none ⇒ the Marketing Admin Team), gated per campaign in `calls`, NOT by
  `CAMPAIGNS_ALLOWED_TEAMS` — the Calls page `/campaigns/calls.html` and
  `/campaigns/api/calls*` admit any signed-in user and the campaign decides.
  **The touch is written as the caller; the rung, the `Declined` exit, the
  *Call again* row and the completion under the API client** (the Mentor
  Role reads `CProspect`, never edits it). **Every call record carries its
  campaign's teams** (v0.261.1): the Mentor Role's Assignment Permission is
  *team*, and EspoCRM refuses such a role ANY save of a record with neither
  a team nor an assigned user (`isPermittedTeamsEmpty`) — so the API client
  stamps the teams before the caller writes. The Mentor Role's grants
  (`COutreachTouch` read/edit, `CProspect` read) are in
  `migrate_outreach_roles.py`. **The Stale sweep** (`campaigns/stale.py`):
  Unverified/Qualified, no side exit, no Planned touch, no activity within
  `PROSPECT_STALE_DAYS`; worker every `PROSPECT_STALE_SWEEP_SECONDS`, and
  `/setup` → Operations *Prospect Stale sweep* (its plan text carries no
  clock, so the fingerprint holds). **Every number is
  `campaigns/reporting.py`** (`summarize_responses` moved there; the
  router re-exports it): the record page, the Responses tab and the new
  Analytics page *Campaigns* (`analytics/campaigns.py`, live, org key).
- **Phase 4** (v0.262.0–v0.264.0, 10-18-26). **Texts (rulings 38, 39,
  `CAMPAIGNS_SMS`):** the application sends — `core/sms.py`, Twilio behind
  `DryRunSmsClient` (the default, `SMS_PROVIDER`); the wording is the CRM
  field `COutreachCampaign.smsMessage`, feature-detected
  (`cfg.CAMPAIGN_OPTIONAL_FIELDS`, dropped from the form and the write
  when absent) and NOT in `CAMPAIGN_SELECT` (a CRM without it would refuse
  the select — read it by a whole get). Selection is ruling 9 (a Contact
  with `cSmsOptIn`). Sign-off refuses wording without STOP. **A touch is
  marked `vendorStatus=sending` before every send and a touch left so is
  never resent by itself** (Twilio has no idempotency key). Sends only
  inside `SMS_SEND_HOURS`. Signed callbacks `/api/campaigns/sms/inbound`
  (STOP → `cSmsOptIn` false) and `/status`, 404 until Twilio is
  configured; the body is parsed by hand (no python-multipart).
  **Email (`CAMPAIGNS_EMAIL`):** `campaigns/email.py` pushes each campaign
  as its OWN list `Campaign — <name>` and never reads or writes the
  standing list or its stored id; *Mark as sent* completes it. **The
  funnel** (`reporting.funnel`, Candidate/Client from the engagement
  status) and **the campaign dashboard scope** `COutreachCampaign`
  (`analytics/campaigns.py`, counts under the org key after the user's read
  — the Marketing Admin Role reads no engagement). **Opportunity on
  attendance** (`attribution.opportunity_on_attendance`) from the manual
  mark, the check-in and the Zoom pull, org key, best-effort.
- **The lead model (v0.265.0, rulings 41–53; build plan § 7a)** supersedes
  the rung words in the Phase 1–4 bullets above. A lead (`CProspect`, CRM
  label *Outreach Lead*) carries `leadStatus` Unqualified · Qualified ·
  Disqualified · Converted and `leadSource`; a Company or Contact is made
  only at first contact and carries `cFunnelStage` Prospect · Engaged ·
  Opportunity. One conversion rule, `campaigns/conversion.py`: an email or
  a website converts; a business lead becomes a Company (matched by website,
  then name and postal code) and the Contact for the email (ruling 52); a
  scan changes nothing (51). A filing row with a website or email enters
  Qualified (53). Every new public-form record gets a lead Converted at
  once (48, `attribution.record_lead`, retry-safe through
  `ResumableClient.created_ids`). **Stage writes need the NEW options**
  (`rung_available`): a CRM still on the old ladder gets none rather than a
  400. Every campaign read requires `CProspect.leadStatus`. Three counts:
  Responded, Converted, Became a client, partner or funder (46).
- **Campaign lists** (v0.270.0, build plan § 7c, rulings 58–68; dark
  behind **`CAMPAIGN_LISTS`**, read per request). `campaigns/audience.py`
  is the engine, `audience_store.py` the five tables (migration 0032,
  mixed into `CampaignStore`, reset nightly), `lists_router.py` the API,
  `frontend/lists.html` the page. A list is an ordered recipe — *add*
  widens, *keep* narrows **only its own type**, *remove* excludes; keep and
  remove test only the current members in id batches, add refuses above
  `STEP_CAP` (20,000). Static = frozen membership plus hand rows that
  survive *Run again*; dynamic = re-run at every build plus standing
  entries (ruling 65). **Step fields come only from the curated list**
  (`CAMPAIGN_LIST_FIELDS`, defaults in `audience.DEFAULT_FIELDS`, checked
  at /setup by `setup/verify._probe_campaign_list_fields`) — never offer
  a field outside it: the member grid shows only the name and the fields
  the recipe used, which is the Marketing Admin Role's read boundary
  (ruling 63). A contacts *Add* must name `cContactType` (ruling 60).
  **Members are records; recipients resolve at build time per channel**
  (`audience.resolve_targets`, the same target shapes each kind's
  `select_targets` produces) and every send-time check applies there. A
  campaign naming a list builds from it (`audience_for_build`, passed as
  `audience=` to each kind's `build_list`); one naming none builds exactly
  as before. **A Mentor, Member or Administrator contact is emailed at
  their `cbmEmail` only** — `audience.address_for_email`, used by the push
  for every email campaign. **L2 (v0.271.0)**: clients (an *engagement*),
  partners and funders; **dotted field names follow links**
  (`audience.resolve_path` — belongsTo walks `<link>Id`, hasOne walks
  backwards through the foreign key, so `CClientProfile.linkedCompany`
  resolves via `Account.cClientProfileId`); link fields filter by id with
  names as options; `olderDays`; `addList` / `removeList` steps (cycle
  refused at Save by `audience.reaches`, at run by `_seen`, depth
  `LIST_DEPTH`) and `import` (ids, emails for leads and contacts, never
  creates). A client / partner / funder reaches its primary contact, or
  every contact (`ORG_SHAPE` names the links) when the campaign ticks
  *Include every contact* (ruling 59); its card goes to its company
  (ruling 68, no ruling-14 check).
- **The lead code** (v0.276.0, build plan § 7d D1, rulings 71–75 and 77;
  `campaigns/leadcode.py`). One twelve-character code per person, for life:
  `CProspect.leadCode`, copied to `Contact.cLeadCode` at conversion
  (`mark_converted` → `sync_on_conversion`), never a second. **Write it only
  under an API key** — the Marketing Admin Role holds a read-only field rule
  on both, so a marketer's own write is dropped with HTTP 200. Feature-
  detected (`leadcode.available`); never put either field in a static
  select. `/c/{link}/{code}` carries it on as `&lead=` (landing: `/p/{code}`)
  and **still never waits on the CRM** — the click is a `BackgroundTasks`
  write after the 302. The postcard prints the person's code as its
  `scanToken`, so one token may sit on several touches: resolve a card with
  `landing.resolve_touch(client, token, campaign_id)`, never `find_one`.
  The public lookup `/api/campaigns/public/lead/{code}?form=` answers
  `cfg.PREFILL_FIELDS[form]` and nothing more — **that table is ruling 75;
  widening a row is a new ruling**. The sandbox's demo cards get their card
  token as their lead code every night (`sandbox_demo.restore_demo_codes`).
- Owed: nothing on production's CRM (both slots done 10-18-26; every
  campaign switch off there — turning one on is Doug's call at `/setup`);
  Boston with its release; a seeder and sandbox re-baseline; the Twilio
  account and A2P 10DLC before any real text; questions 2, 4, 5 before the
  first real card (`OPEN-ITEMS.md` #51).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.4 | 10-22-26 13:00 | Claude (Claude Code) | The lead code bullet (v0.276.0, § 7d D1). |
| 1.3 | 10-22-26 12:25 | Claude (Claude Code) | The campaign owner bullet (ruling 76, v0.275.0). |
| 1.2 | 10-21-26 16:01 | Claude (Claude Code) | Campaign lists L2 (v0.271.0). |
| 1.1 | 10-20-26 18:20 | Claude (Claude Code) | Campaign lists L1 (v0.270.0) bullet added. |
| 1.0 | 10-20-26 17:30 | Claude (Claude Code) | Created from the root `CLAUDE.md` section, word for word (Doug's approval 10-20-26). |
