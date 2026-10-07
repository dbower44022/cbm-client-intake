# Mailing List and Event Sponsorship — plan v0.1 (2026-10-07)

Last Updated: 10-07-26 03:30 · Revision 0.1 — change log at the end.

**Status: rulings settled, nothing built.** This is the plan document for the
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
   `CEvent.partnerProfiles` ↔ `CPartnerProfile.events`, the mirror of the
   existing funder link; `CEvent.partnerHost` / `CPartnerProfile.hostedEvents`
   is removed. No "host" distinction until a real report asks for it.
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
`CPartnerProfile.events`, many-to-many, labels *Partners* / *Events*; remove
`partnerHost`. `CEvent.noticeCampaignId` varchar. `CEventRegistration.
noticeCampaignId` varchar. Written as a handoff through the CRM-changes
procedure, applied with the migration-script pattern, verified by reading
the links back from `GET /Metadata` on the side intended. crm-test, then
production at a Sunday 17:00 UTC slot, then Boston with the release that
carries the code.

**Phase B — Event Administration and the Events tab (code, ships with no
flag; dark until the CRM has the link).** Partner and funder link pickers in
the editor (relationships, so `list_related` / `relate` / `unrelate`, never a
`*Ids` write). `DomainConfig` gains a `sponsored_events_link` that gates both
the tab and its endpoint, the `contributions_link` precedent. Counts computed
in `events/reporting.py` by one function, paged at 200, best-effort per row
("—", never 0, on a failed read). Analytics panels follow.

**Phase C — the audience push (worker, `MAILING_SYNC`, off by default).**
Constant Contact client in `core/`, OAuth2 refresh-token flow, secrets at
`/setup`. Nightly push of qualifying Contacts, matched on email; hourly pull
of unsubscribes and bounces onto the CRM email address flags. Alerts through
the existing monitoring. The migration script ships with this phase and runs
once, by hand, dry-run first.

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
| `CEvent` ↔ `CPartnerProfile` | add many-to-many `partnerProfiles` / `events`; remove `partnerHost` / `hostedEvents` | A |
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

---

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 10-07-26 03:30 | Claude (Claude Code) | First version from the 2026-10-07 conversation: ten rulings, the model, five phases, CRM prerequisites, four open questions with recommendations, the deferred designer, later candidates. |
