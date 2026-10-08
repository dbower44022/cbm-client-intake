# Mailing List and Event Sponsorship — plan v0.1 (2026-10-07)

Last Updated: 10-07-26 23:45 · Revision 0.5 — change log at the end.

**Status: Phases A and B done on crm-test; Phase C designed (§ 11), one decision open (§ 11.11), nothing of it built.** This is the plan document for the
arc, in the style of the other arcs in `prds/`: it records Doug's rulings, the
model that follows from them, the phases, and what is deliberately deferred.
It is an implementation-level document, so it names the mailing service
(Constant Contact) and the CRM entities directly. A Level 1 or Level 2
requirements document for this arc, if one is written, must not.

The problem, in Doug's words (2026-10-07): *"Some employees want to use
Constant Contact for sending out event notices, so they have begun adding
contacts into Constant Contact directly. Now some contacts are in the CRM,
others in Constant Contact, and the data does not sync. Event registration is
happening in Constant Contact too, so there is data about events and
registration in two places."*

---

## 1. What this changes, in one paragraph

The CRM becomes the only place a person or an event is entered. The
application pushes the mailing audience from the CRM to Constant Contact and
pulls back only unsubscribes and bounces. Every event notice links to the
event's own page on this application, where registration already writes to
the CRM, so Constant Contact's event and registration features are never used.
Each notice, once sent, is linked to its event so the send counts come back
onto the event record. Partners gain the same many-to-many link to events that
funders already have, and both the Partner Management and Funder Management
records gain an Events tab with registered, attended and became-a-client
counts per event. An in-application email designer, which would let the
content of a notice be generated from the event record, is recorded here as
future work and is not part of this arc.

---

## 2. Doug's rulings (2026-10-07)

1. **The CRM is the master.** Constant Contact is a mirror the application
   refreshes. It holds nothing the CRM did not give it.
2. **Data flows one way, CRM to Constant Contact.** The only flow back is
   unsubscribe and bounce status, because the mailing service is the legal
   authority on opt-out.
3. **Staff stop entering people in Constant Contact.** A person who should
   receive notices is entered as a Contact in the CRM, with the marketing
   opt-in ticked, and the push does the rest.
4. **The existing Constant Contact list is migrated once** into Contact, type
   `Prospect`, matched on email and null-filled like any repeat submitter,
   **with no provenance marker**. Doug: there are too few of them to care
   about Constant Contact as a source, and in steady state it is never one.
5. **Constant Contact only sends the notice.** The link in every notice leads
   to the event's own public page (`/webinars/{slug}`), where registration
   writes a `CEventRegistration`. Constant Contact's event and registration
   features are never used. Registrations already collected there are
   migrated once as `registrationSource = Import`, or let go if few.
6. **Staff keep Constant Contact's drag-and-drop designer.** Doug: *"our team
   can't give up the editor; they are not willing to trade convenience for
   losing creative content for each event."* The application therefore does
   not create the campaign. Staff design and send in Constant Contact, and
   the application links the sent campaign to the event afterwards.
7. **Partner and Funder records show their events with analytics.** One row
   per linked event, with registered, attended and became-a-client counts.
8. **"Requested a mentor" is not a separate count.** Every request ends in an
   assignment, so the existing attendee-to-client conversion rule is the
   measure. Columns are registered, attended, became a client.
9. **Partner sponsorship is one many-to-many link, and the host link goes.**
   Many partners are associated with one event as a matter of course.
   `CEvent.partnerProfiles` ↔ `CPartnerProfile.sponsoredEvents`, the mirror
   of the existing funder link (`sponsorProfiles` ↔ `sponsoredEvents`, read
   from crm-test 2026-10-07); `CEvent.partnerHost` /
   `CPartnerProfile.hostedEvents` is removed. No "host" distinction until a
   real report asks for it.
10. **The in-application designer is deferred.** Recorded in § 8 for future
    action. The event, partner and contact changes come first.

---

## 3. Findings that shaped the plan (verified 2026-10-07)

- **The CRM already carries the sponsorship links.** `CEvent.sponsorProfiles`
  (many-to-many → `CSponsorProfile`) and `CEvent.partnerHost` (many-to-one →
  `CPartnerProfile`, reverse `hostedEvents`) were built in the original events
  handoff and exist on crm-test and production. **The application reads
  neither** — no reference in `events/`, so both are set only in the CRM's own
  screens today. Changing the partner link costs the application nothing.
- **The conversion rule exists and is the one to reuse.**
  `events/reporting.conversion_report` counts a contact as converted when a
  `CEngagement` for them was *created after* their first attended event. The
  engagement Events tab (`engagement_rollup`) and the programme reports share
  the module. The per-partner counts belong in the same module so every
  screen agrees (the same discipline as the active-client count).
- **Marketing consent already lives on Contact.** `cMarketingOptIn` is
  written by the client intake form (`marketing_consent`) and by event
  registration (`consent`). Mentors, partners and funders have no explicit
  opt-in field, so the first push carries only Contacts with the flag true.
- **Constant Contact's current API creates only custom-code campaigns**
  (`format_type` 5), and the vendor's own support states the custom-code
  editor and the drag-and-drop editor are incompatible with no conversion
  between them. So a campaign the application creates can never be opened in
  the designer staff use — the finding behind ruling 6. The API does list
  every campaign whatever its format, attaches contact lists to one, and
  reports unique sends, opens, clicks, bounces and opt-outs per campaign
  (`/reports/summary_reports/email_campaign_summaries`). Sources in § 10.
- **The API is OAuth2 with a refresh token**, not an API key. Connecting the
  account is a one-time browser authorisation by a Constant Contact user;
  the refresh token is a secret the application stores encrypted at `/setup`.
- **The event page is already the registration door.** `/webinars/{slug}`
  carries description, graphic, date and its own registration form, and the
  payload's `url` is this application's address for the event. A notice is
  one more door to the same page; "view information" and "register" are the
  same link.

---

## 4. The model

### 4.1 People

| Where | What | Rule |
|---|---|---|
| CRM `Contact` | the person, email, `cMarketingOptIn`, native email opt-out | master |
| Constant Contact contact + list membership | a copy | refreshed by the push; never edited by hand |
| Constant Contact unsubscribe / bounce | the person's opt-out | pulled back onto the Contact's email address opt-out |

**Audience rule.** A Contact is pushed when it has a primary email address,
`cMarketingOptIn` is true, and the email address is not opted out or marked
invalid in the CRM. Which Constant Contact *list* it joins is a mapping from
a CRM attribute (§ 7, open question 1). A Contact that stops qualifying is
removed from the list, never deleted from Constant Contact.

**Flow back.** An unsubscribe in Constant Contact sets the CRM email address's
opt-out flag; a hard bounce marks it invalid. Nothing else comes back. Both
are advance-only in the opt-out direction: the push never re-subscribes an
address the person opted out of.

**Migration.** One script, dry-run by default, idempotent through a ledger:
export Constant Contact contacts, `find_create_or_fill` on email, type
`Prospect`, opt-in true, no provenance (ruling 4).

### 4.2 Events and notices

| Where | What | Rule |
|---|---|---|
| CRM `CEvent` | the event, its page, its partners and funders | master |
| Constant Contact campaign | one notice about the event, designed and sent by staff | linked afterwards |
| CRM `CEvent.noticeCampaignId` (new, app-managed) | which campaign announced this event | stamped by "Link a campaign" |
| Application cache | the campaign's sent / opened / clicked / bounced counts | read from the API, cached; never the master |

**Link a campaign.** Event Administration offers "Link a campaign" on an
event: the application lists the account's campaigns (newest first, name,
status, sent date), staff pick the one they sent, the application stamps the
campaign id, attaches the event's audience list if the campaign is still a
draft, and from then on shows the counts on the event's Overview. Several
notices per event are possible; the field is a list if the CRM build allows,
else the latest wins and earlier ones ride in the application cache.

**Registration attribution.** The Register link staff paste into a notice is
copied from Event Administration and may carry the campaign id as a query
parameter; the registration form records it on the `CEventRegistration`
(new field, § 6), so a notice's registrations can be counted. Cheap, and the
report partners actually ask for. Not a gate on anything else.

### 4.3 Partners and funders

One many-to-many link each — `partnerProfiles` (new) and `sponsorProfiles`
(existing) — both set from Event Administration through link pickers. The
Events tab on a partner or funder record lists every event linked to it:

| Column | Source |
|---|---|
| Event, date | `CEvent` |
| Registered | count of `CEventRegistration` for the event |
| Attended | registrations with `attendanceStatus` in the attended set |
| Became a client | attended contacts with a `CEngagement` created after the event's start — the existing rule, scoped to one event |

Totals across the partner's events head the tab, and the same totals are
available as Analytics panels on the Partner and Funder dashboards. An
exportable or printable version is a later step (§ 9).

---

## 5. Phases

**Phase A — CRM change (Doug, crm-test first).** `CEvent.partnerProfiles` ↔
`CPartnerProfile.sponsoredEvents`, many-to-many, labels *Partners* /
*Sponsored Events*, relation table `cPartnerProfileEvent`; remove
`partnerHost`. Handoff: `cevent-partner-sponsorship-crm-handoff.md`; plan file
`scripts/plans/cevent-partner-sponsorship.json`; applier
`scripts/migrate_event_sponsorship_schema.py` (`--carry-host` copies any
existing host into the new link first). `CEvent.noticeCampaignId` varchar. `CEventRegistration.
noticeCampaignId` varchar. Written as a handoff through the CRM-changes
procedure, applied with the migration-script pattern, verified by reading
the links back from `GET /Metadata` on the side intended. crm-test, then
production at a Sunday 17:00 UTC slot, then Boston with the release that
carries the code.

**Phase B — Event Administration and the Events tab (code, ships with no
flag; dark until the CRM has the link). BUILT 2026-10-07 as v0.239.0 —
verified by tests only; live pass `OPEN-ITEMS.md` #39. Analytics panels
not built (see § 9).** Partner and funder link pickers in
the editor (relationships, so `list_related` / `relate` / `unrelate`, never a
`*Ids` write). `DomainConfig` gains a `sponsored_events_link` that gates both
the tab and its endpoint, the `contributions_link` precedent. Counts computed
in `events/reporting.py` by one function, paged at 200, best-effort per row
("—", never 0, on a failed read). Analytics panels follow.

**Phase C — the audience push (worker, `MAILING_SYNC`, off by default).
DESIGNED 2026-10-07 — § 11; setup runbook `MAILING-SETUP.md`; one decision
open (§ 11.11).** Constant Contact client in `core/`, OAuth2 refresh-token
flow, credentials and the connection at `/setup`. Nightly push of qualifying
Contacts, matched on email; hourly pull of unsubscribes (and bounces, once
their representation is verified) onto the CRM email address flags. Alerts
through the existing monitoring. The migration script ships with this phase
and runs once, by hand, dry-run first.

**Phase D — Link a campaign (web, `MAILING_SYNC` too).** Campaign listing,
the stamp, list attachment for drafts, counts on the Overview, the
attribution query parameter on the public registration form. Every link
action goes through `record_action`.

**Phase E — deferred:** the in-application designer (§ 8).

Each phase is reviewable on crm-test by a real non-admin Marketing Admin or
Partner Management user before the flag is set on production.

---

## 6. CRM prerequisites

| Entity | Change | Phase |
|---|---|---|
| `CEvent` ↔ `CPartnerProfile` | add many-to-many `partnerProfiles` / `sponsoredEvents`; remove `partnerHost` / `hostedEvents` | A |
| Marketing Admin Role (both CRMs, Boston) | `read: all` on `CPartnerProfile` and `CSponsorProfile`, so the Phase B pickers list — the role held none (handoff § 7); the link write escalates on a foreign-record denial | A — **ruled and applied on crm-test 2026-10-07**; production and Boston owed |
| `CEvent` | `noticeCampaignId` varchar (app-managed, read-only in layouts) | A |
| `CEventRegistration` | `noticeCampaignId` varchar | A |
| `Contact` | none — `cMarketingOptIn` and the native email opt-out suffice | — |

Removing `partnerHost` is metadata-only; the column and any values stay.
Production's event records carry no partner host today, so nothing is lost
either way.

---

## 7. Open questions, with the recommended answer

1. **Which CRM attribute decides the Constant Contact list?** Recommended:
   one list, "Event notices", for every qualifying Contact; add per-topic
   lists only when staff segment by topic. Cost of the simple answer: none
   today; a second mapping later is a settings change, not a rebuild.
2. **Who authorises the connection?** A Constant Contact user owned by the
   organisation, not a person's own login, so a departure does not revoke the
   token. Cost: one shared credential to safeguard, stored only at `/setup`.
3. **Consent for mentors, partners and funders.** They have no opt-in field.
   Recommended: they are not pushed until the CRM standard rules on an
   opt-in for them; staff who want a mentor on the list tick `cMarketingOptIn`
   on the Contact. Cost: a manual tick per person until then.
4. **Per-event "became a client": attended or registered?** Recommended:
   attended, matching the programme rule exactly. Cost: a registrant who
   missed the event and later became a client is not credited to it.

---

## 8. Deferred — the in-application email designer (future action)

**Doug, 2026-10-07:** *"Let's put this in the PRD for future action. It is
more important to move ahead with the event, partner and contact management
changes."*

The idea: a drag-and-drop email designer inside Event Administration. A
"Design notice" button opens it with the event's title, date, summary,
graphic and Register button already placed as blocks; staff design around
them; the application stores the layout with the event and pushes the
finished HTML to Constant Contact as a custom-code draft, so staff go there
only to pick the list and send. The event facts are never typed; the creative
work survives.

What was established:

- The open-source GrapesJS editor's newsletter preset is the candidate: email-
  safe blocks, inlined styles, BSD-3 licence, plain browser JavaScript with no
  build step, vendored like Jodit. Maintenance activity and rendering in
  Outlook are **unverified**.
- Images are already solved: recipients' mail clients need a public address,
  and this application serves event graphics publicly.
- The cost is a feature arc about the size of the Events editor: the designer
  page, a store of saved layouts, per-event drafts, the push. The risk is
  acceptance — staff who know Constant Contact's designer will compare.
- **The agreed first step, when the time comes, is a one-page prototype**
  (the preset with a sample event's blocks pre-placed, no storage, no push)
  put in front of the people who design notices. A day of work that answers
  the only question that matters. If they accept it, the arc is planned
  around it; if not, ruling 6 stands and nothing is lost.
- Commercial embeddable designers exist and are more polished, but are
  monthly-fee services with their own hosting model; not proposed until the
  free option has been seen and rejected.

---

## 9. Later candidates (not commitments)

Suggested on 2026-10-07 as ways to make the partner and event process more
valuable, each built on something already in place:

- **Analytics panels for a partner's or funder's events** on their record
  dashboards, rolling the Events tab totals up — deferred from Phase B.
- **A promotion link per partner.** The partner's link carries its identifier;
  the registration records it; the Events tab can say "your promotion brought
  this many". One field on the registration (the same mechanism as the
  campaign attribution in § 4.2).
- **A periodic impact statement.** The Events tab's numbers for a quarter or
  year, plus clients created and sessions delivered to them, as a page a
  partner or funder can be sent; for funders, fed into grant deliverables of
  the kind "events delivered" / "people reached" (`grant-management-plan.md`).
- **Switch on reminders** (`EVENTS_REMINDERS`, built and off everywhere). The
  cheapest lever on attendance, the number partners judge an event by.
- **The mentor call-to-action and the survey as the measured step.** Both
  templates exist; with registration recognition the attended-to-client path
  becomes one the application can see end to end, and the survey gives each
  partner event a satisfaction score.
- **A partner-scoped public programme page** — the existing page filtered to
  one partner's events, for the partner to link from its own site.

---

## 10. Sources for § 3

- Constant Contact developer documentation: *Email Campaign Overview*
  (`developer.constantcontact.com/api_guide/email_campaigns_overview.html`),
  *Create an Email Campaign* (`…/email_campaign_create.html`), *Email
  Campaign Quick Start Guide* (`…/email_campaigns_get_started.html`), *Email
  reporting overview* (`…/email_reporting_overview.html`).
- Constant Contact community, staff answer: *Switching modes of editing email
  campaign* (`community.constantcontact.com/t5/Get-Help/Switching-modes-of-editing-email-campaign/td-p/398863`).
- GrapesJS newsletter preset (`github.com/GrapesJS/preset-newsletter`).
- For § 11 (read 2026-10-07): *OAuth2 Overview* (`…/api_guide/auth_overview.html`
  — flows, endpoints, token lifetimes, the private-application rule,
  multiple redirect URIs), *Authorization Code Flow*
  (`…/api_guide/server_flow.html` — parameters, Basic-auth token exchange,
  the 300-second code), *Quick Start* (`…/api_guide/getting_started.html`
  — the New Application dialog, Rotating Refresh, the once-shown secret),
  *Scopes* (`…/api_guide/scopes.html`), *Contacts overview*
  (`…/api_guide/contacts_overview.html` — bulk import limits), *Syncing
  contacts* (`…/api_guide/contacts_sync.html` — `updated_after`,
  `status=unsubscribed`, read lists before importing), *Rate limits*
  (`…/api_guide/rate_limits.html`).

---

## 11. Phase C design — the audience push (2026-10-07)

Everything here follows from rulings 1 to 4 and from three vendor facts read
on 2026-10-07 (sources added to § 10). Confidence is stated per item: a fact
read from the vendor's documentation is marked *read*; a behaviour not found
in the pages read is marked *unverified* and listed in § 11.10, to be proved
against a test account before the code that depends on it is written.

### 11.1 Accounts and applications

- **A new developer application is private to the Constant Contact user who
  created it** (*read*). Only that user can authorise it; opening it to all
  users means telephoning the vendor's support and an approval process. So
  the application is created while signed in as the Constant Contact user
  that will connect the deployment — the organisation-owned login of open
  question 2 — and that same user authorises it. The My Applications page
  lives inside the Constant Contact product itself
  (`app.constantcontact.com/pages/dma/portal`), so the sign-in is the
  ordinary Constant Contact sign-in (*read*).
- **One Constant Contact account, one developer application, one
  deployment.** Production connects to the organisation's real account.
  crm-test connects through its own application to the account § 11.11
  settles. The dev deployment never connects: it has no CRM to push from.
  Boston registers its own application in its own account; the chapter
  deployment guide gains a step when Phase C ships.
- **Refresh-token method: Rotating Refresh**, the vendor's recommendation
  (*read*). The cost is that every refresh yields a new refresh token that
  must be stored before anything else happens, and two processes refreshing
  at once would race. § 11.3 serialises the refresh in the database, so the
  choice costs nothing at run time. Whether reusing a superseded token
  revokes the whole grant is *unverified*; the design assumes it does and
  never reuses one.

### 11.2 The redirect address

The address Constant Contact sends the authorisation back to must match,
character for character, an address registered on the application (*read*:
a mismatch is a 400; several absolute addresses may be registered per
application). This application builds it as

```
{APP_BASE_URL}/api/setup/mailing/callback
```

from the `APP_BASE_URL` setting — **never from the request's Host header**,
because production answers on both its custom domain and its
`ondigitalocean.app` address and only one of them is registered. The
Settings panel shows the computed address with a copy button, so the value
registered is the value used. Fixed addresses per deployment:

| Deployment | Redirect address |
|---|---|
| production | `https://apps.clevelandbusinessmentors.org/api/setup/mailing/callback` |
| crm-test | `https://cbm-client-intake-svxs3.ondigitalocean.app/api/setup/mailing/callback` |
| Boston | `https://apps.bbmentors.org/api/setup/mailing/callback` |

A developer's `http://localhost:8000/api/setup/mailing/callback` may be
added to the **crm-test** application only, never production's. (Community
answers say plain `http` is accepted for localhost; *unverified*.)

### 11.3 Connecting, and keeping the connection

- **Start** — `GET /api/setup/mailing/connect`, EspoCRM administrators only
  (the `/setup` gate). Builds the authorise URL with the client ID, the
  redirect address above, `response_type=code`, the scopes
  `contact_data campaign_data account_read offline_access`, and a `state`
  signed with `SESSION_SECRET` carrying the administrator's user id and a
  timestamp. `campaign_data` is requested now, though Phase C never uses it,
  so Phase D does not force a second authorisation; `account_read` lets the
  panel show which account is connected.
- **Callback** — `GET /api/setup/mailing/callback?code&state`, same gate.
  Verifies `state` (signature, age under ten minutes, same administrator),
  exchanges the code at the token endpoint with HTTP Basic
  `client_id:client_secret` (*read*), reads `/account/summary` for the
  account's organisation name, stores the connection, records the action
  (`record_action`, "Mailing service connected"), and redirects to `/setup/`.
  An authorisation code lives 300 seconds (*read*), so the exchange happens
  in the callback, never deferred.
- **Where the connection lives** — a new table `mailing_connection`, one
  row: access token and refresh token (both encrypted with
  `APP_ENCRYPTION_KEY` through `core/crypto`; **refused without a cipher**,
  the same rule the settings store applies to secrets), access-token expiry,
  granted scopes, account label, connected-by, connected-at,
  last-refresh-at, last-error. Added to `core/sandbox_reset.KEEP_TABLES`,
  because a connection crm-test loses every night is no connection. Not an
  `app_setting` row: it is not something an administrator edits, and the
  history table would gain a "(secret set)" row per refresh.
- **One refresher at a time** — any process needing a token runs
  `SELECT … FOR UPDATE` on the row, re-reads the expiry under the lock,
  refreshes only if the access token is within five minutes of expiry,
  writes the new pair before releasing the lock. The vendor rate-limits the
  token endpoint and says to refresh only near expiry (*read*). The access
  token lives 24 hours (*read*: 1440 minutes), so a healthy deployment
  refreshes about once a day.
- **When refresh fails** — a 400/401 from the token endpoint marks the row
  `needs_reauthorisation`, stops the push and pull until a human
  reconnects, and raises **one** alert through the existing monitoring
  ("Mailing service needs re-authorisation"), not one per cycle. This is
  the single failure a human must fix; every other failure retries. A
  refresh token unused for 180 days expires (*read*), which a daily push
  never lets happen.
- **Disconnect** — the panel's Disconnect deletes the row and records the
  action. The vendor-side revocation endpoint is *unverified* and not
  relied on.

### 11.4 Settings

| Key | Kind | Component | Default | Notes |
|---|---|---|---|---|
| `MAILING_SYNC` | bool | worker | off | The switch. Per-request, so `/setup` flips it. |
| `MAILING_CLIENT_ID` | text | both | empty | The application's API key. |
| `MAILING_CLIENT_SECRET` | secret | both | empty | Shown once by the vendor; stored encrypted; never read back. Not a `VERIFIED_KEYS` member — nothing can probe it without a user authorising, so the Connect step is its verification. |
| `MAILING_LIST_NAME` | text | worker | `Event notices` | Open question 1's answer. Find-or-create by name on the first push. |
| `MAILING_PUSH_SECONDS` | int | worker | 86400 | 0 disables the push and leaves the pull. |
| `MAILING_PULL_SECONDS` | int | worker | 3600 | 0 disables the pull. |
| `MAILING_BASE_URL` | text | both | `https://api.cc.email/v3` | Override only for a vendor change. |

Readiness gains a `mailing` feature: flag `mailing_sync`, component
`worker`, requires the client ID and secret, plus a connection-state line
(connected as / not connected / needs re-authorisation) that no other
feature has, because the credential here is a grant rather than a key.
Setting labels say *Mailing service*, never the vendor's name, so the page
reads the same on every chapter; the help text may name the vendor.

### 11.5 The push (nightly, worker)

1. **Audience** — every CRM Contact with a primary email address,
   `cMarketingOptIn` true, `emailAddressIsOptedOut` false and
   `emailAddressIsInvalid` false, read under the org-wide API key, paged at
   200. The three bools are the whole rule (§ 4.1); mentors, partners and
   funders join only when someone ticks the box (open question 3).
2. **The list** — `GET /contact_lists`, matched on `MAILING_LIST_NAME`;
   created when absent. Its id is cached on the connection row.
3. **What the list holds now** — `GET /contacts?lists={id}&include=…`,
   paged, to a set keyed on lower-cased email. The vendor's own sync guide
   says to read list membership before importing, so a recent unsubscribe is
   not re-added (*read*).
4. **Add** — the audience minus the list, sent as
   `POST /activities/contacts_json_import` with `list_ids=[id]` and, per
   contact, `email`, `first_name`, `last_name` (*read*: up to 40,000 per
   call, asynchronous, polled at `GET /activities/{id}`). Existing contacts
   are updated only in the properties sent (*read*). The push never sends a
   contact whose vendor-side `permission_to_send` is `unsubscribed` or
   `temp_hold` (ruling 2: opt-out flows one way).
5. **Remove** — the list minus the audience, sent as
   `POST /activities/remove_list_memberships` by contact id. Removed from
   the list, never deleted from the account (§ 4.1).
6. **Pacing** — one bulk call each way per night, membership reads paged;
   well inside 10,000 calls a day and 4 a second (*read*). Any 429 waits
   and retries once, then the pass is reported as partial.
7. **Plan then apply** — the same function is a `/setup` Operations job
   (dry-run → apply that exact plan, refusing if the plan moved), which is
   how the first run is read before it writes. The nightly timer calls it
   with apply.

### 11.6 The pull (hourly, worker)

- `GET /contacts?status=unsubscribed&updated_after={cursor}` (*read*, the
  vendor's sync guide). For each, the CRM Contact matched on email gets
  `emailAddressIsOptedOut=true` on that address (through `emailAddressData`,
  the write `comms/service.py` already makes). Advance-only: the pull never
  clears a CRM opt-out and the push never re-adds an address the CRM holds
  as opted out. The cursor is persisted on the connection row and moves only
  after a pass completes.
- **Bounces — unverified.** The vendor pages read today do not say how an
  undeliverable address appears on a contact. Candidates: `permission_to_send
  = temp_hold` (community answers describe it as a sticky hold), the
  per-campaign bounce report under `/reports/email_reports`, or a contact
  `status`. Until proved on a test account the pull applies unsubscribes
  only; a hard bounce, once identifiable, sets `emailAddressIsInvalid=true`.
- A contact the vendor reports that the CRM does not hold is logged and
  skipped, never created (ruling 1).

### 11.7 The one-time migration

`scripts/import_mailing_contacts.py`: reads every active vendor contact,
`find_create_or_fill` on email as `Contact` type `Prospect` with
`cMarketingOptIn=true`, no provenance marker (ruling 4). Dry-run by default,
idempotent through a ledger, run once by hand against production **before**
the first production push — otherwise § 11.5 step 5 removes from the list
every person staff entered directly, which is the number the runbook tells
the operator to stop on.

### 11.8 Monitoring and history

Alerts through `core/monitoring`: re-authorisation needed (once), a push
pass that failed or was partial, a pull cursor that has not advanced in a
day. Connect, disconnect and every applied push go through `record_action`.
The push's per-pass counts are kept on the connection row and shown on the
readiness line, so "is it running?" is answered without a log.

### 11.9 Build order

1. `core/mailing.py` — the client: token store with the locked refresh,
   `_request` with one re-auth on 401, contacts, lists, activities. Alembic
   migration 0030 for `mailing_connection`; `KEEP_TABLES`.
2. Settings and the readiness feature; the `/setup` panel rows (client ID,
   secret, redirect address read-only, connection line with Connect /
   Disconnect); the connect and callback routes.
3. The push as a function, exposed as the Operations job, then on the worker
   timer. The pull. Tests with a fake vendor client that enforces the 4-a-
   second and page-size limits the way the EspoCRM fake enforces 200.
4. The migration script.
5. Review on crm-test as a real non-admin reading the results in the CRM,
   then production.

### 11.10 Verification owed before the dependent code is written

- How a bounced address appears on a vendor contact (§ 11.6).
- Whether reusing a superseded rotating refresh token revokes the grant
  (§ 11.1); the design never reuses one either way.
- The exact label of the redirect-address box on the application's edit
  screen, and that it accepts an address with a path (the documentation
  says "absolute URIs"; the quick-start page never mentions the box).
- The maximum page size of `GET /contacts` (the design assumes 500; the
  code reads whatever the documentation states).
- How long the trial account a developer sign-up creates lives, if § 11.11
  chooses it.

### 11.11 Open decision — which account crm-test connects to

crm-test holds training data: invented people with invented addresses, reset
nightly. A push from it is a push of those people.

- **A. A separate Constant Contact account for crm-test** (the trial account
  a developer sign-up creates, or a second paid account). What it does well:
  nothing crm-test does can reach a real person or the real list; the
  review happens end to end, writes included. Cost: one more sign-in to
  hold, and a trial account may expire and need re-creating (§ 11.10).
  **Recommended** — the sandbox already refuses to touch production systems
  by rule, and this keeps that rule.
- **B. The real account, with crm-test confined to a list named
  `Event notices — TEST`.** What it does well: no second account. Cost:
  invented people enter the real account's contact base; one accidental send
  to that list mails invented addresses, and the bounces count against the
  organisation's sender reputation; a real person's unsubscribe pulled back
  by crm-test lands on a sandbox record and is reset that night.
- **C. crm-test never connects; the first review is production's dry-run
  plan.** What it does well: nothing to set up twice. Cost: the write path
  is first exercised on production, which breaks the crm-test-first gate
  every other feature observed.

### 11.12 Follow-on detail, settled

The panel wording is *Mailing service*; the setting prefix is `MAILING_`;
the route prefix is `/api/setup/mailing/`; the table is
`mailing_connection`; the client module is `core/mailing.py`. The scopes
requested are the four in § 11.3. The list name default is *Event notices*.

---

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.5 | 10-07-26 23:45 | Claude (Claude Code) | Phase C designed: § 11 (accounts and the private-application rule, the fixed redirect address per deployment, the connection store with locked rotating refresh, settings, the push and pull, the migration, build order, verification owed, the crm-test account decision). Runbook `MAILING-SETUP.md`. Sources for § 11 added to § 10. |
| 0.4 | 10-07-26 04:10 | Claude (Claude Code) | Phase B built (v0.239.0): pickers, the sponsors endpoint, the Events tab, the rollup. Analytics panels deferred to § 9. |
| 0.3 | 10-07-26 03:45 | Claude (Claude Code) | Phase A applied to crm-test (all but the hand removal); the role grant ruled read-all and applied there. |
| 0.2 | 10-07-26 03:40 | Claude (Claude Code) | Phase A handoff written: far-side link name is `sponsoredEvents` (mirrors the funder link as read from crm-test), relation table named; Marketing Admin Role gap added to the prerequisites. |
| 0.1 | 10-07-26 03:30 | Claude (Claude Code) | First version from the 2026-10-07 conversation: ten rulings, the model, five phases, CRM prerequisites, four open questions with recommendations, the deferred designer, later candidates. |
