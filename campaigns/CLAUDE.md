# campaigns/ — Marketing Management (was Campaign Management)

Last Updated: 10-27-26 21:10 · Revision 1.17

Detail for Campaign Management (`/campaigns`, prospect marketing Phases 1 to 4 and the lead model): links, postcards, the landing page, imports, the Leads and Review grids, calls, texts, email, attribution and reporting.

Claude Code loads this file only when a session reads or edits files in this
folder. The rules other packages depend on stay in the root `CLAUDE.md`, which
also points here. Moved word for word from the root file on 10-20-26, when it
outgrew Claude Code's size limit; edit it here from now on.

## Marketing Management — `/campaigns`

**Renamed from Campaign Management in v0.278.0** (Doug, 10-22-26). The
bullets below keep the old name where they record history. The page opens
on the Leads tab; the tab order is Leads, Lists, Campaigns, Review, Calls,
Imports. The `/campaigns` address, the package and the `CAMPAIGNS_*`
settings keep their names — they are identifiers.

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
  `CAMPAIGNS_ALLOWED_TEAMS` — the Calls tab (`/campaigns/#calls`; the old
  `calls.html` redirects there) and `/campaigns/api/calls*` admit any
  signed-in user and the campaign decides.
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
  standing list or its stored id; *Mark as sent* completes it — **the
  switch-off path since M7**: with `CAMPAIGN_LIST_SYNC` on, an email
  campaign must choose a list, its build writes no touch (the send report
  of M9 writes them), sign-off requires the list's copy and syncs it
  (`router._sign_off_to_copy` → `lists_router.run_sync_now`), and *Pick the
  email* stores the vendor's id on `COutreachCampaign.vendorEmailId`
  (feature-detected, written under the API key) and moves it to Running;
  `run_email_cycle` pushes nothing. **The
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
- **Campaign lists** (v0.270.0, build plan § 7c, rulings 58–68; reshaped
  by **M6, v0.289.0**, § 7e.8, rulings 90–94 and 98; dark behind
  **`CAMPAIGN_LISTS`**, read per request). `campaigns/audience.py` is the
  engine, `audience_store.py` the four tables (migrations 0032 and 0037,
  mixed into `CampaignStore`, reset nightly), `lists_router.py` the API,
  the Lists tab (`/campaigns/#lists?list=<id>`; `lists.js`) the screen.
  **A dynamic list is a search and nothing else**: its recipe is
  `{"include": [group], "exclude": [group]}` — a group is `match` (one type,
  all its conditions), `list` (everyone on another list) or `import` (the
  records a file names) — and its members are the union of the Includes
  minus the union of the Leave outs; **Leave out always wins, groups have no
  order**. A Leave out match group tests only the included records of its
  type, in id batches; an Include match refuses above `STEP_CAP` (20,000).
  A run stores its members with `group_index` (the first Include group that
  matched — *Brought in by*) and the Include groups it used, so a changed
  Leave out keeps the labels. **Never add a hand edit to a dynamic list**:
  a person kept off goes onto a static exclusion list through
  `POST /lists/{id}/exclude`, which adds a Leave out list group when needed.
  **A static list is hand rows and nothing else**: empty recipe, never run,
  `mark` / `add-people` / `unmark` only; `run` refuses it, and `mark` /
  `unmark` refuse a dynamic list, in words. **The kind never changes**
  (`save_list` raises, the router answers 400); *Copy* makes a static list.
  The per-channel counts (`audience.channel_counts`, `GET /lists/{id}/counts`)
  are `resolve_targets` per kind over the stored members, never stored.
  A list another list names cannot be deleted. **Group fields come only
  from the curated list** (`CAMPAIGN_LIST_FIELDS`, defaults in
  `audience.DEFAULT_FIELDS`, checked at /setup by `setup/verify._probe_campaign_list_fields`) — never offer
  a field outside it: the member grid shows only the name and the fields
  the recipe used, which is the Marketing Admin Role's read boundary
  (ruling 63). A contacts Include group must name `cContactType` (ruling 60).
  **Members are records; recipients resolve at build time per channel**
  (`audience.resolve_targets`, the same target shapes each kind's
  `select_targets` produces) and every send-time check applies there. A
  campaign naming a list builds from it (`audience_for_build`, passed as
  `audience=` to each kind's `build_list`); one naming none builds exactly
  as before. **A Mentor, Member or Administrator contact is emailed at
  their `cbmEmail` only** — `audience.address_for_email`, used by the push
  for every email campaign. **A list's copy in Constant Contact** (v0.290.0,
  M7, § 7e.9, ruling 95; behind **`CAMPAIGN_LIST_SYNC`**; migration 0038's
  `cc_*` columns): `campaigns/list_sync.py` is the per-list sync over
  `core/mailing_sync`'s parameterised `build_plan` / `apply_plan`. The copy
  holds `resolve_targets(..., KIND_EMAIL, ...)` of the list's current members,
  is found by its stored id and then by name (**never create a copy without
  looking by name first** — the reset empties the id, the vendor keeps the
  list), follows a rename, and is never deleted by the application. One
  worker pass (`run_pass`) reads the unsubscribes and the custom field once
  and runs the standing list, then every active ticked list; *Sync now* is
  the only sync a web request runs, for one list, bounded at
  `SYNC_NOW_SECONDS`. **Every push writes the lead code** as the
  `cf:cbm_lead_code` column (`give_codes`, minted under the org-wide key, at
  most `MINT_PER_PASS`), and re-imports the people already on a copy so a
  replaced code reaches the vendor. The vendor shapes M7 added are inferred
  until the live send; the build plan's § 7e.12 Draft 8 records which were
  confirmed. **L2 (v0.271.0)**: clients (an *engagement*),
  partners and funders; **dotted field names follow links**
  (`audience.resolve_path` — belongsTo walks `<link>Id`, hasOne walks
  backwards through the foreign key, so `CClientProfile.linkedCompany`
  resolves via `Account.cClientProfileId`); link fields filter by id with
  names as options; `olderDays`; list groups (cycle refused at Save by
  `audience.reaches`, at run by `_seen`, depth `LIST_DEPTH`) and file
  groups (ids, emails for leads and contacts, never creates). A client /
  partner / funder reaches its primary contact, or every contact (`ORG_SHAPE` names the links) when the campaign ticks
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
- **One page, six tabs** (v0.279.0, build plan § 7e.2 — step M1 of the
  redesign, rulings 89, 112, 114). `index.html` holds every tab; `lists.js`
  and `calls.js` load after `app.js` and reach the page ONLY through
  `window.CBMMarketing` (`api`, `notice`, `ask`/`openModal`, `session()`,
  `register(name, {onShow, onLeave})`, `showSection`). **Their ids are
  prefixed `ls_` / `cl_`; the modal, notice, user corner and off panel exist
  once, owned by `app.js`** — a new tab script follows the same shape and
  never declares a bare id (`tests/test_campaigns_one_page.py` checks for
  duplicates). `showSection` is async: a tab's `onLeave` may refuse the
  switch (Lists asks about unsaved changes through the page's dialog, never
  `confirm()`), and `onShow(params)` gets the hash's parameters. **A
  signed-in user outside the team gets `callerOnly: true` from `/session`**
  and the page shows the Calls tab alone; nothing else is unlocked — every
  other endpoint keeps `_require_user`, and `calls.may_call` still decides
  per campaign. The portal's *Campaign calls* tile (`portal/router.
  _campaign_calls_tile`) uses `calls.may_call_any` under the org-wide key.
  **No served campaigns file may cite a ruling number** (ruling 112) — the
  guard test fails on `ruling \d` and `CM-\d`; write the hint in plain words
  and leave the number in the documents.
- **The qualification ladder and the Leads tab** (v0.284.0, build plan
  §§ 7e.3 and 7e.4 — step M2 of the redesign, rulings 104–106, 108, 113,
  117; dark behind **`LEAD_LADDER`**, read per request; needs
  `marketing-redesign-crm-handoff.md` on the CRM, feature-detected by
  `ladder.available`). **The rule is one module, `campaigns/ladder.py`**:
  `facts` → `placed` → `next_level`; the level never moves backwards, and
  after *Set level* only a NEW fact moves it forward — the facts snapshot is
  `lead_level_manual` (reset nightly; no snapshot ⇒ never moved). **Call
  `ladder.after_write(lead_id, client=…)` after any application write to a
  lead** (best-effort, org-wide key, silent while off); the import computes
  the level into the create instead (no per-row CRM call — the volume rule).
  The worker's sweep covers leads modified since its watermark (memory; a
  start looks back a day); the Operations job backfills every lead. **The
  level is empty at any status but Qualified** — placement clears it. A level
  edited in the CRM's own screens carries no `levelSetAt`, so the sweep may
  lift it, never lower it. The Leads grid's columns are drawn by `app.js`
  (`LADDER_COLUMNS` / `CLASSIC_COLUMNS`) from the `ladder` flag on every
  `/prospects` answer; the counts are `GET /prospects/counts`, one `total`
  each. *Assign to* (bulk, and on the lead's page) takes the campaign owner's
  team-member list (`service.owner_options`) and `leads.assign_payload`
  refuses a Converted, Disqualified or stopped lead. The lead's page is
  `/campaigns/lead/{id}` (`LEAD_ID` in `app.js`, lock `lead:<id>`); its
  inline gaps go through `leads.facts_payload` (a whitelist — `FACT_FIELDS`)
  and are written as the user; *Convert* runs `convert_lead` under the API
  client from the lead's own email or website. *Email* and *Log a call* are
  shown and say they arrive with personal outreach (M5). ***New code***
  (§ 7d.1, ruling 126) sits on the lead's page and on the directory's
  Contact record page (`directory/router.py`, contacts kind only,
  `leadCodeAdmin` on its session): `leadcode.replace_for_lead` /
  `replace_for_contact` under the org-wide key, both records kept equal,
  the action log given `code_tail` (the last four) and never the code.
- **Review is the research queue, in two modes** (v0.285.0, build plan
  § 7e.6 — step M3, rulings 110, 121; rides `LEAD_LADDER`, no switch of its
  own). *Judge* is the Unqualified queue as before; *Find contacts* lists
  Qualified leads at Identified, and its row writes `firstName`, `lastName`,
  `phone`, `email` through `leads.contacts_payload` (the lead page's
  normalisation) as the user, then `ladder.after_write` — the row leaves
  the queue only when the lead reaches Contactable or Referred. The mode
  rides the address (`#review?mode=contacts`, `LeadQuery.from_params(…,
  mode=)`); a CRM without the ladder refuses the contacts mode in words,
  never answering the judge queue instead. **Every contacts decision also
  sends `seenLevel`**, and `leads.changed_since` names who moved the level.
  The row's *AI research* button fills the boxes from
  `GET /prospects/{id}/suggestions` (`enrichment.runs.suggestions`, org-wide
  key) and Enter closes those findings Accepted through
  `enrichment.runs.close_findings` — values are never rewritten from a
  finding at that point; with no findings it starts a one-lead run.
  **Ruling 121 lives in `enrichment.runs.decide`:** a Person accepted on a
  lead fills the lead's own empty person fields and creates no Contact
  (ruling 43 stands). The Review thead is drawn by `app.js`
  (`REVIEW_COLUMNS`) from the mode, like the Leads grid's.
- **The import tool** (v0.286.0, build plan § 7e.7 — step M4, rulings
  79–88, 111, 123, 127; dark behind **`IMPORT_TEMPLATES`**, read per
  request; migration 0035; `openpyxl`). `campaigns/import_templates.py`
  holds the template table, the mapping and its four fixes, recognition
  and the required check; `campaigns/imports.py` the file reader
  (`read_file`: CSV and `.xlsx`, a `SheetChoice` for several sheets), the
  queued plan (`queue_plan` → the worker's `run_plan_cycle` →
  `plan_batch_now`; dry-run plans inline), the fourth outcome `fills`, the
  level per row and `undo_import`. **The preview never runs in a web
  request** (ruling 123): the batch row carries `plan_status`, the page
  polls `GET /prospects/import/{batchId}`. **The apply writes what the
  preview showed**: the plan's `ladder` flag decides the level, not the
  switch at apply time. *Enters at* Qualified still needs a website or an
  email (ruling 42's floor). **Undo deletes under the org-wide key**
  (ruling 127; the API role's `delete` on `CProspect` is in
  `migrate_outreach_roles.py`), only leads nobody touched
  (`touched_reasons` — a change within `UNDO_WINDOW` of the write is the
  import's own, but a fill by a LATER import is a touch by the ledger,
  `store.filled_by_later_batch`, whatever the clock says), forgets every
  ledger row naming a deleted lead, lists the rest; fills stay. A known
  hash whose lead the CRM no longer has is a new row again (`stale` on the
  plan entry; the apply drops its rows first). **One request writes a batch
  at a time** (v0.287.0, migration 0036): the apply and Undo claim the
  batch's write lease (`store.claim_write`, one statement) and release it
  when the request ends; a second press answers 409 naming who holds it; a
  lease older than five minutes is taken over.
  With the switch off, `plan_import` is the CSV path exactly as before
  and a known row is skipped, not filled. The tab is `imports.js`
  (ids `im_`), handed the Imports tab by `app.js`'s `loadImports` /
  `openImport` when the session says `importTemplatesOn`; it never
  registers an `onShow`. The demo template is restored nightly with the
  demo links (`sandbox_demo.restore_demo_template`).
- **Personal outreach from the lead's page** (v0.288.0, build plan
  § 7e.5 — step M5, rulings 107–109, 115, 118–120, 122, 128; dark behind
  **`LEAD_OUTREACH`**, read per request; needs the redesign handoff's
  Assigned to, Replied and the conversation link, the Gmail integration
  and `CHAPTER_POSTAL_ADDRESS`). The rules are `campaigns/outreach.py`, the
  endpoints `campaigns/outreach_router.py` (registered on `api_router` by
  the tail import in `router.py`). **The composer is the shared
  `frontend/shared/compose.js`** (ruling 128), opened with a host object;
  on a lead it runs with a fixed recipient and no Cc/Bcc, Documents or
  reply. **The sender's mailbox is one rule**, `comms.crm.user_mailbox`
  (ruling 120: the mentor profile's address, else the user's own on
  `MENTOR_EMAIL_DOMAIN`), read by `comms.service.sender_mailbox` for the
  compose and the send and by the sync's scope build. **The server holds
  the guardrails** (`outreach.why_not_email` / `why_not_call`,
  `check_recipients`): Contactable or Referred, no side exit, an email,
  assigned to the sender, the lead's own address as the only recipient; the
  page asks the same questions first and says why in words. **Every
  personal email ends with the opt-out sentence and the postal address**
  (`outreach.append_footer`; an empty setting refuses, naming it). **A
  personal call's three words are stored as the campaign calls' words**
  (`cfg.PERSONAL_OUTCOME_STORED`: Not interested → Declined, No reply yet →
  No answer — the touch's outcome enum has only those; read 10-25-26) and
  its consequences are **`calls.apply_outcome`, shared with
  `record_outcome`** — never a second Interested or Declined branch. A
  personal touch has no campaign and carries the sender and the Marketing
  Admin Team (`outreach.team_ids`). The sync: `comms.crm.PARENT_LINKS`
  has `CProspect: prospects`, `_add_assigned_leads` builds the lead
  source (a marketer-only mailbox gets its own scope), an inbound message
  from the lead's exact address sets `replied` (`sync._mark_leads_replied`)
  and `conversion.mark_converted` clears it. The Leads tab's **Mine** chip
  is the Assigned-to filter preset to `me` (`leads.counts(…, me=)`).
- **Lists only, the strip and the grid** (v0.291.0, build plan § 7e.9
  second half, M8; rulings 99–102; dark behind **`CAMPAIGN_LISTS_ONLY`**,
  read per request, needs `CAMPAIGN_LISTS`; migration 0039).
  `ready_made.lists_only(settings)` is the one test. **The five ready-made
  lists are `campaigns/ready_made.LISTS`, fixed ids, `system` true**;
  migration 0039 holds a frozen copy a test keeps equal. `ensure(store)`
  re-creates a missing one and never touches one that exists (the worker
  every five minutes, the reset hook, `GET /lists`) — **never edit a
  ready-made list's row in place to change it; change `LISTS` and write a
  migration**. Delete, rename, change, retire and Exclude refuse a system
  list (`lists_router._not_system`); Copy makes an ordinary static list.
  *Dormant clients* is the one **`builtin` group** (`audience.builtin_keys`):
  only a ready-made list may carry one, and `_validated` refuses it from the
  API. With the switch on, `build_list` refuses a `rule` payload and a
  campaign with no list; `ready_made.adopt` gives a rule-built Draft or
  Awaiting sign-off campaign its kind's list (`FOR_KIND`). The strip is
  `campaigns/strip.py` (no CRM change), on the record payload as `strip`;
  the page moves the run cards into the *Audience and content* tab
  (`placeCards`) and hides the rule boxes. The grid reads partners, funders
  and events per row, eight at a time (`router._grid_relations`) — the CRM
  has no list-read field for them. Recipients is M9, Promote this event M10.
- **The send report and Recipients** (v0.292.0, build plan § 7e.9, M9;
  ruling 96; dark behind **`CAMPAIGN_SEND_REPORT`**, read per pass and per
  request, needs `CAMPAIGN_LISTS` and `CAMPAIGN_LIST_SYNC`).
  `campaigns/send_report.py`: for each Running email campaign with a picked
  `vendorEmailId`, the worker (every `CAMPAIGN_SEND_REPORT_SECONDS`, a day)
  reads the primary activity's four tracking reports and writes **one
  `COutreachTouch` per recipient, keyed by Contact, updated in place** — never
  a second. Delivered unless bounced (Returned, the code in `vendorStatus`);
  `clickCount` / `firstClickedAt`; `openCount` / `firstOpenedAt`
  feature-detected (`coutreach-touch-opens-crm-handoff.md`); an empty outcome
  becomes Clicked, a human one is never overwritten. **Matching** is the
  campaign's list resolved for email first (members at their chapter
  address), then `Contact.emailAddress`, then `CMentorProfile.cbmEmail`; an
  unmatched address is counted and named, never created. After 30 days from
  the pick the campaign completes. *Read the report now* (`POST
  …/campaigns/{id}/report`) writes at most `WEB_WRITE_CAP` touches. **Never
  build a store inside `run_report_cycle`** — the worker passes its own.
  The vendor's tracking shapes are inferred until the live pass. **The
  Recipients tab** (lists only): `GET …/recipients` (paged, `q`, `status`)
  and `…/recipients.csv`, read under the org-wide key after the user's read
  of the campaign; it replaces the Touches table under Responses. A call
  sign-off now stores `pieceCount`.
- **The Lists tab redesigned** (v0.293.0, build plan § 7e.14, M11;
  rulings 129–132; dark behind **`CAMPAIGN_LIST_SCREENS`**, read per
  request, needs `CAMPAIGN_LISTS`; migration 0040). `listview.js` (ids
  `lv_`) draws the list view, Preview and Edit; `lists.js` keeps the old
  screens and **hands the tab over in its `M.register` while the session
  says `listScreensOn`** — the one place the two meet. View is a page of its
  own, `list-members.html`, served at `/campaigns/lists/{id}/members` by
  `core/app.py` and opened in the browser tab `cbm-list-<id>` (ruling 130,
  the one exception to one page). **Counts are stored**: `audience_list.counts`
  / `counted_at` and `audience_list_member.reach` (letters e, t, p; NULL =
  not counted since written), written only by `campaigns/list_counts.
  refresh_one` — *Refresh* (`POST /lists/{id}/refresh`) and the worker pass
  (`run_pass`, every `CAMPAIGN_LIST_COUNT_SECONDS`, first ten minutes after
  start; the worker passes its own store). `audience.count_list` is three
  `resolve_targets` runs; `resolve_targets` now returns `reachedMembers`,
  the member keys a channel reaches (a duplicate counts as reached). The old
  *Run now* does not update the stored counts. The preview route returns
  `diff` (who comes on and drops off against the last run, 50 names a side);
  the members route takes `channel`, `group` and `detail` (the View columns,
  read as the user by `audience.describe_details`); the name search takes
  `listId` and marks `onList`.
- Owed: nothing on production's CRM (both slots done 10-18-26; every
  campaign switch off there — turning one on is Doug's call at `/setup`);
  Boston with its release; a seeder and sandbox re-baseline; the Twilio
  account and A2P 10DLC before any real text; questions 2, 4, 5 before the
  first real card (`OPEN-ITEMS.md` #51).

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.17 | 10-27-26 21:10 | Claude (Claude Code) | The Lists tab redesigned (v0.293.0, § 7e.14, M11): the hand-over in `lists.js`, View's page, the stored counts and their pass, the route additions. |
| 1.16 | 10-27-26 18:50 | Claude (Claude Code) | The send report and the Recipients tab (v0.292.0, § 7e.9, M9). |
| 1.15 | 10-27-26 14:10 | Claude (Claude Code) | Lists only, the strip and the grid (v0.291.0, § 7e.9 second half, M8): the ready-made lists, the built-in group, adoption, the strip, the grid's per-row reads. |
| 1.14 | 10-26-26 12:05 | Claude (Claude Code) | A list's copy in Constant Contact and the email campaign that sends to it (v0.290.0, § 7e.9, M7): the copy's identity, the one pass, the lead code column, the switch-off path kept. |
| 1.13 | 10-26-26 02:45 | Claude (Claude Code) | Campaign lists rewritten to Include and Leave out (v0.289.0, § 7e.8, M6): the groups, static lists as hand rows, Exclude, the fixed kind, Copy, the per-channel counts. |
| 1.12 | 10-26-26 00:10 | Claude (Claude Code) | Personal outreach from the lead's page (v0.288.0, § 7e.5, M5): the shared composer, the one mailbox rule, the guardrails, the footer, the stored outcome words, `apply_outcome`, the sync's lead source, the Mine chip. |
| 1.11 | 10-25-26 22:48 | Claude (Claude Code) | The import batch write lease (v0.287.0). |
| 1.10 | 10-25-26 20:50 | Claude (Claude Code) | The import tool live-passed (v0.286.3): the later-fill touch, stale ledger rows, the apply lock owed. |
| 1.9 | 10-25-26 19:30 | Claude (Claude Code) | The import tool (v0.286.0, § 7e.7, M4): templates, Excel, the worker preview, fills, the level per row, Undo under the org-wide key, the Imports tab script. |
| 1.8 | 10-25-26 12:36 | Claude (Claude Code) | Review as the research queue (v0.285.0, § 7e.6, M3): the two modes, `seenLevel`, suggestions and `close_findings`, ruling 121 in `decide`. |
| 1.7 | 10-25-26 11:15 | Claude (Claude Code) | The qualification ladder and the Leads tab (v0.284.0, § 7e.3–7e.4, M2): `ladder.py`, `after_write`, the sweep, the counts, Assign to, the lead's page. |
| 1.6 | 10-23-26 01:33 | Claude (Claude Code) | One page, six tabs (v0.279.0, § 7e.2 M1): the shared object, the id prefixes, `callerOnly`, the ruling-number guard; the two old page addresses now redirects. |
| 1.5 | 10-22-26 21:18 | Claude (Claude Code) | Renamed Marketing Management; Leads first (v0.278.0). |
| 1.4 | 10-22-26 13:00 | Claude (Claude Code) | The lead code bullet (v0.276.0, § 7d D1). |
| 1.3 | 10-22-26 12:25 | Claude (Claude Code) | The campaign owner bullet (ruling 76, v0.275.0). |
| 1.2 | 10-21-26 16:01 | Claude (Claude Code) | Campaign lists L2 (v0.271.0). |
| 1.1 | 10-20-26 18:20 | Claude (Claude Code) | Campaign lists L1 (v0.270.0) bullet added. |
| 1.0 | 10-20-26 17:30 | Claude (Claude Code) | Created from the root `CLAUDE.md` section, word for word (Doug's approval 10-20-26). |
