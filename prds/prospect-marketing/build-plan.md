# Prospect Marketing — build plan v0.2 (2026-10-14)

Last Updated: 10-15-26 00:02 · Revision 0.4 — change log at the end.

**Where this document lives.** `prds/prospect-marketing/` is the whole arc;
start at its `README.md`. The binding decisions are in `rulings.md` beside
this file; the discussion that produced them is under `history/`.

**Status: a plan, not a build.** Nothing here is built, no CRM is changed, no
vendor account exists. This document turns the rulings of
`rulings.md` (rulings 1–8 of 2026-08-11 and 9–27 of
2026-10-13/14, all settled and none reopened here) into the record model, the
screens, the phases, the CRM handoffs and the verification scripts the build
needs. It is a sibling of that document rather than a section of it because
it is longer than the document it serves. Where this plan had to choose, the
choice is stated as a draft with its cost; the choices that pass the two-part
test are in § 9 as numbered questions, and the plan is written on the
recommended answer to each so that a "yes" costs Doug nothing.

**v0.3 (10-14-26 22:41): questions 1, 3, 8 and 9 are answered** — rulings
28–31 in `rulings.md`. Three as recommended; question 8 against it: **an
engagement supports multiple referring partners** (ruling 30), so the
engagement gains a many-to-many link `referringPartners` beside the single
`referringPartner` of v0.255.0 (§ 1.5, § 5). Eight questions stay open;
none changes the CRM's shape.

**Revised to v0.2 on 10-14-26 against the Campaign Management
requirements** — `rulings.md`, *Requirements — the Campaign Management
application*, CM-1 to CM-11 (gathered in
`history/prospect-marketing-plan.md`, section *Requirements — Campaign
Management application (10-14-26)*), which Doug
stated after v0.1 was written. **Those requirements are Doug's and are not
reopened here.** Sections revised: 0, 1.3–1.5, 1.10, 3 (two new kinds, a
new links section, the screens, the word), 4, 5, 6, 7, 8 and 9. Where the
plan had to choose *how* to meet a requirement the choice is a draft with
its cost; the five that pass the two-part test are questions 8–12 in § 9,
and the plan is written on the recommended answer to each.

**Written in the house vocabulary.** Entity, field and link names are the
names EspoCRM will store, computed by its three prefix rules (§ 1.10). A
**rung** is a position on the funnel ladder; a **side exit** is a reason a
record left the ladder; a **touch** is one attempt by the chapter to reach a
business or person; a **door** is any place a record can enter the system (an
import, a public form, the webinar page); **promotion** is the creation of a
Company or Contact from a prospect record (ruling 21); **conversion** is a
relationship beginning through a standard intake form (ruling 22).

---

## 0. What this plan decides, in one screen

- **Three custom entities** — `CProspect` (the quarantine record), `COutreachCampaign` (the campaign, labelled **Campaign** on every screen) and `COutreachTouch` (one row per attempt, which is also campaign membership) — rather than EspoCRM's own Lead and Campaign entities. The finding and the cost are in § 1.1; it is question 1.
- **A campaign names its partners and its events** (CM-2, CM-6): two many-to-many links. The forms relate the campaign's partners to what they create, by each door's own rule (CM-4, § 5) — **an engagement carries every one of them** through a new many-to-many `referringPartners` (ruling 30); a partner's record page gains a Campaigns tab (CM-5).
- **Five kinds** (CM-3): postcard, email, SMS and call select an audience and run the shared engine; social media selects nobody and is its links alone (§ 3.6).
- **A link is a record of the application's own with a short resolvable address** (CM-7, CM-8): named, any number per campaign, pointing at one of the five forms, the programme page or one event; destination correctable after publishing; retire-but-still-open; the QR code generated here (§ 3.7). Where the link lives is question 9.
- **The rung continues after promotion as a field on the Contact and on the Company** (`cFunnelStage`), not through the link to the prospect record, because a webinar registrant has no prospect record to read through (§ 1.8).
- **One word for one thing** (CM-11). A *campaign* is ours; the tool is **Campaign Management**, its own portal tile (CM-10). A *notice* is a Constant Contact send, as the mailing-list plan already calls it (§ 3.9).
- **The landing page is a sixth form kind** (`forms/prospect_response/`), so it inherits durable capture, holds and Submission Admin visibility; a scan is logged on the page load, before any form (§ 4).
- **The standard forms carry three hidden values**, `prospect`, `campaign` and the link's token, exactly as the partner link carries one id, and honour them at delivery with the same validate-or-drop rule (§ 5). The campaign page shows the application's own numbers; conversion is an Analytics dashboard scoped to the campaign (CM-9, § 6).
- **Five phases, each dark behind a flag or feature detection**; Phase 1 mails one real card and records one real scan, and needs two CRM handoffs applied first (§ 7).
- **Twelve questions for Doug** (§ 9); the four that shaped the CRM (1, 3, 8, 9) are answered as rulings 28–31, so Phase 1's handoff can be written. Three gate the first real card: the vendor, what the outside filter delivers, and the card itself.

---

## 1. The record model, in Entity Manager vocabulary

### 1.1 Why custom entities rather than EspoCRM's own Lead and Campaign — question 1

EspoCRM ships a marketing module: a `Lead` entity (person-shaped, with
`createdAccount` and `createdContact` links set by its Convert action), a
`Campaign` entity (types Email, Mail, Web and others, with target lists, a
log of sent / opened / clicked / bounced, and tracking addresses), and a
`campaign` link on every Contact and Account meaning "the campaign that
originated this record". Ruling 27's Contact and Company stamp exists there
already, and Lead's convert links are ruling 21's promotion links.

**Verified on crm-test 2026-10-14, read-only as the org-wide API key:** the
`campaign` field and link exist on Contact and Account; the `Marketing`
group of the CRM's own tab list is empty (every native marketing tab has been
removed); the key gets **HTTP 403 on `Lead` and on `Campaign`** and the
metadata it is served carries no `scopes.Lead` or `scopes.Campaign`. So the
native module is present, hidden from staff, and invisible to the credential
the application runs on.

**Recommendation: build custom entities.** Reasons, in order of weight:

1. **Shape.** Ruling 21's record is a business *or* a person *or* both. Lead
   requires a last name and is a person with an optional account name; a
   filing with no human would carry a placeholder. Whether the required flag
   on a core field can be cleared through the Field Manager and survive an
   upgrade is *unverified*.
2. **Every other arc built custom** — `CInformationRequest`, `CEvent`,
   `CGrant`, `CEventPresenter` — and the chapter-network standard, the
   applier and the conformance check all know how to build and verify a
   custom entity. A core-entity modification (clearing a required flag,
   re-adding tabs, granting a hidden scope) is a shape the standard has not
   carried yet.
3. **The word.** A native Campaign tab would put a third "campaign" in front
   of staff beside ours and Constant Contact's.

**Cost of the recommendation, honestly named:** three entities and sixteen
links to build and keep in the standard, and the native `campaign` link on
Contact and Account stays unused forever (it points at the native entity and
cannot be re-pointed). **Cost of the alternative:** the role grants, the tab
list and a core-field change on every chapter's CRM, plus the two
unverified points above.

**The plan below assumes custom entities.** If Doug chooses the native
module, § 1.2–1.5 are rewritten; §§ 2–8 stand.

### 1.2 `CProspect` — the quarantine record

Create Entity: Name **`Prospect`** (typed without the `C`), label *Prospect*,
plural *Prospects*, Type **BasePlus** (teams and assigned users are what let
a team-read role see it), Stream **on** (the action log posts its notes to
the stream), navigation tab **on** (staff work the list).

One record per business or person the chapter cannot yet uniquely identify
(ruling 21). Both halves optional, at least one present. Everything the
import row held stays on the record; promotion copies, never moves.

| Field | Type | Notes |
|---|---|---|
| `name` | varchar, required | The business name when known, else the person's name. Required by EspoCRM; the application sets it |
| `businessName` | varchar | The business half |
| `firstName`, `lastName` | varchar | The person half, when the row named one |
| `mailingAddress` | address | Street, city, state, postal code, country. The address a card goes to. *The `address` type is untested in the applier — four varchars are the fallback (handoff note)* |
| `addressStatus` | enum: `Usable` · `Dead` | Ruling 15. `Dead` is written by the vendor callback; a new address from any import row resets it to `Usable` |
| `addressDeadAt` | datetime | When the callback marked it |
| `website` | url | Promotes the business (ruling 21) |
| `email` | varchar | Promotes the person (ruling 21). Kept here as the raw row value even after promotion |
| `phone` | varchar | Makes the record selectable by a call campaign (ruling 20) |
| `funnelStage` | enum: `Unverified` · `Qualified` · `Lead` · `Warm Lead` · `Opportunity` | The rung. Candidate and Client are never stored (read from the engagement). Advance-only; the application writes it, never staff |
| `entryStage` | enum, same options | Written once at import, never again |
| `stageChangedAt` | datetime | Feeds the Stale rule |
| `entryDoor` | enum: `State filing` · `List` · `Partner file` | Which import created it. Deliberately **not** called source (ruling 26) |
| `externalReference` | varchar | The filing or registry number the row carried. Generic name: every state has filings |
| `importBatch` | varchar | File name and date, for the batch view and for undo by batch |
| `importRow` | text | The raw row as JSON — the audit trail |
| `qualifiedBy` | varchar | The outside filter's name and version (ruling 11), or the reviewing staff member's name (ruling 18) |
| `qualifiedAt` | datetime | |
| `sideExit` | enum: `` · `Already known` · `Unqualified` · `Do Not Contact` · `Declined` · `Stale` | Empty means on the ladder. *Undeliverable is not a side exit* — ruling 15 makes it an address state, so it lives in `addressStatus` |
| `sideExitAt` | datetime | |
| `sideExitNote` | text | The reviewer's reason |
| `description` | text | Staff notes |

Links stored on `CProspect` (§ 1.5 has the full table): `promotedCompany`,
`promotedContact`, `alreadyKnownCompany`.

### 1.3 `COutreachCampaign` — the campaign

Create Entity: Name **`OutreachCampaign`**, label **Campaign**, plural
**Campaigns**, Type **BasePlus**, Stream **on**, tab **on**. The stored name
keeps a distinguishing word because EspoCRM's own hidden entity is
`Campaign`; the label, the tab and every screen say *Campaign* (CM-11).
BasePlus gives it `assignedUser` — the **owner**, defaulting to the creator
— and `teams`, so no owner field is added.

**What a marketing user fills in** (the working position recorded with
CM-1 to CM-11, plus CM-2 and CM-6): name, kind (and platform for social
media), status, start and end date, owner, notes, partners, events. The
selection rule is set on the Overview for the kinds that select; the
sign-off and run stamps below are written by the application, never typed.
No budget or cost field — a postcard run's cost comes from the run (ruling
13).

| Field | Type | Notes |
|---|---|---|
| `name` | varchar, required | "State New Business Filing — Postcard, 2026-11" is a name, not a source value (ruling 26) |
| `campaignKind` | enum: `Postcard` · `Email` · `SMS` · `Call` · `Social media` | CM-3. The first four select an audience and run the engine (§ 3.1–3.5); social media is its links alone (§ 3.6) |
| `platform` | enum: `` · `Meta` · `YouTube` · `LinkedIn` · `Instagram` · `X` · `Other` | Social media only; one kind with a platform rather than a kind per platform — question 10 |
| `campaignStatus` | enum: `Draft` · `Awaiting sign-off` · `Signed off` · `Running` · `Complete` · `Cancelled` | The application moves it; `Cancelled` instead of delete |
| `selectionRule` | text | The rule as the screen saved it, JSON the application owns (§ 3.1). Never hand-edited |
| `selectionSummary` | text | The same rule in words, for the record and the sign-off |
| `pieceCount` | int | What was signed off (ruling 13). Live counts are computed from touches, never stored |
| `estimatedCost` | currency | What was signed off. **Always written with `estimatedCostCurrency`** or the save 400s |
| `signedOffByName` | varchar | Who signed; the action log holds the actor too |
| `signedOffAt` | datetime | |
| `startDate`, `endDate` | date | The campaign's window; selection runs inside it |
| `vendorTemplateId` | varchar | The mail vendor's template for the card (Postcard) |
| `postcardSize` | enum: `4x6` · `6x9` · `6x11` | Constrains the template; question 5 |
| `runStartedAt`, `runCompletedAt` | datetime | The execution run |
| `description` | wysiwyg | The notes box: the brief, the offer, the creative notes — the shared editor |

Links stored on it: `partnerProfiles` (many-to-many, the partners the
campaign names — CM-2) and `events` (many-to-many, the events it advertises
— CM-6; one or more, the working position), plus the reverse links from
touches, Contacts, Companies and the five relationship records (§ 1.5).
The campaign's **links** in the CM-7 sense are not CRM links at all; they
are the application's own records (§ 3.7, question 9).

### 1.4 `COutreachTouch` — one attempt, and campaign membership

Create Entity: Name **`OutreachTouch`**, label *Touch*, plural *Touches*,
Type **BasePlus**, Stream **off** (machine rows), tab **off** (reached from
the campaign and from the prospect).

One row per intended attempt. A row is created at selection with
`touchStatus=Planned`, which is what "Active Prospect — membership in a
running campaign" (ruling 10) means in storage: a record is an active
prospect while it has a `Planned` or `Sent` touch in a `Running` campaign.
The lifecycle of the attempt and what came back are two fields, because a
card can be delivered and never scanned, or scanned before the vendor
reports delivery.

| Field | Type | Notes |
|---|---|---|
| `name` | varchar | Set by the application: campaign name — target name |
| `channel` | enum: `Postcard` · `Email` · `SMS` · `Call` | Copied from the campaign so a touch reads alone. Social media has no touches: nobody is selected |
| `touchStatus` | enum: `Planned` · `Sent` · `Delivered` · `Returned` · `Done` · `Cancelled` | Postcard: Planned → Sent → Delivered or Returned. Call: Planned → Done. Email: Planned → Sent. A refused sign-off cancels every Planned row |
| `outcome` | enum: `` · `Scanned` · `Clicked` · `No answer` · `Interested` · `Declined` | What came back. Ruling 20's three call outcomes are the last three |
| `stageAtTouch` | enum, the rung options | Stamped when the row leaves `Planned`, so the campaign's reports stay honest after the record moves |
| `plannedAt`, `sentAt`, `deliveredAt`, `returnedAt`, `doneAt` | datetime | |
| `scanToken` | varchar(16), indexed | The QR code's token. Generated from `secrets`, no ambiguous glyphs, never the record id (§ 4) |
| `firstScannedAt` | datetime | Ruling 16's evidence |
| `scanCount` | int | |
| `vendorPieceId`, `vendorStatus` | varchar | The mail vendor's per-piece id and last reported state |
| `mailedAddress` | text | The address **as mailed**, a snapshot, so a Returned touch names which address died even after the record's address changes |
| `calledPhone` | varchar | The number dialled, a snapshot |
| `callNotes` | text | The caller's note (ruling 20) |

Links stored on it: `outreachCampaign` (required), and exactly one of
`prospect`, `contact`, `company` — a prospect record before promotion, a
Contact or Company after it or for a dormant-client campaign (ruling 25).

### 1.5 Every link, with the side it is stored on

Plan-file form (`link` is stored on `entity`, `linkForeign` on
`entityForeign`; the applier computes the stored names). Reverse-link names
on Contact and Account gain the `c` prefix because those entities are not
custom; names on the custom entities stay as typed.

| Stored on | Link (as stored) | Type | Foreign entity | Foreign link (as stored) | Why |
|---|---|---|---|---|---|
| `CProspect` | `promotedCompany` | many-to-one | `Account` | `cProspectRecords` | Ruling 21: the promoted record links back; many-to-one so a Company shows its history |
| `CProspect` | `promotedContact` | many-to-one | `Contact` | `cProspectRecords` | Same |
| `CProspect` | `alreadyKnownCompany` | many-to-one | `Account` | `cAlreadyKnownProspects` | Ruling 12: the match the import found, for the review |
| `COutreachTouch` | `outreachCampaign` | many-to-one | `COutreachCampaign` | `touches` | |
| `COutreachTouch` | `prospect` | many-to-one | `CProspect` | `touches` | Ruling 21: every touch while a prospect |
| `COutreachTouch` | `contact` | many-to-one | `Contact` | `cOutreachTouches` | Touches after promotion, and ruling 25 |
| `COutreachTouch` | `company` | many-to-one | `Account` | `cOutreachTouches` | Same |
| `COutreachCampaign` | `partnerProfiles` | many-to-many | `CPartnerProfile` | `sponsoredCampaigns` | CM-2: the partners a campaign names. The reverse feeds the partner's Campaigns tab (CM-5) |
| `COutreachCampaign` | `events` | many-to-many | `CEvent` | `outreachCampaigns` | CM-6: the events a campaign advertises; one or more (working position) |
| `CEngagement` | `referringPartners` | many-to-many | `CPartnerProfile` | `referredEngagements` | **Ruling 30**: every partner that referred this client — the partner link's partner and every partner the campaign names. Beside the single `referringPartner` (v0.255.0), whose reverse `engagements` stays the Referred Clients tab's first read (§ 5) |
| `Contact` | `cOutreachCampaign` | many-to-one | `COutreachCampaign` | `contacts` | Ruling 27: only when the submission created the Contact |
| `Account` | `cOutreachCampaign` | many-to-one | `COutreachCampaign` | `companies` | Ruling 27: same for the Company |
| `CEngagement` | `outreachCampaign` | many-to-one | `COutreachCampaign` | `engagements` | Ruling 27: every time |
| `CInformationRequest` | `outreachCampaign` | many-to-one | `COutreachCampaign` | `informationRequests` | Ruling 27 |
| `CEventRegistration` | `outreachCampaign` | many-to-one | `COutreachCampaign` | `eventRegistrations` | Ruling 27. **Replaces** the mailing plan's planned `CEventRegistration.noticeCampaignId` (Phase D, unbuilt): a notice's Register link is a campaign link (§ 3.7). `CEvent.noticeCampaignId`, which notice announced the event, stays that plan's |
| `CPartnerProfile` | `outreachCampaign` | many-to-one | `COutreachCampaign` | `attributedPartnerProfiles` | Ruling 27. **Ruling 32**: not `partnerProfiles`, which this entity already uses for the CM-2 many-to-many above — EspoCRM refuses a second link under a name the entity has |
| `CSponsorProfile` | `outreachCampaign` | many-to-one | `COutreachCampaign` | `sponsorProfiles` | Ruling 27 |

Seventeen links, fourteen many-to-one and three many-to-many, none `hasOne` —
the cardinality that has twice silently moved a record off its owner is not
used anywhere here. All three many-to-many links are **relationships** in
EspoCRM's sense: read through `list_related`, written with relate and
unrelate, never through a `*Ids` attribute on the record write.

### 1.6 Fields on Contact and Account

Custom fields on these two native entities are typed unprefixed and stored
with the `c` prefix.

| Entity | Typed | Stored | Type | Why |
|---|---|---|---|---|
| Contact | `smsOptIn` | `cSmsOptIn` | bool, default false | Ruling 9. Beside `cMarketingOptIn`; written true-only by every door that captures the marketing opt-in, exactly as that field is (event registration's EV-12 rule). EspoCRM's native `phoneNumberIsOptedOut` stays the per-number opt-out, the sibling of the email one |
| Contact | `funnelStage` | `cFunnelStage` | enum, the five stored rungs | § 1.8 |
| Contact | `entryStage` | `cEntryStage` | enum, same | Written once at creation |
| Account | `funnelStage` | `cFunnelStage` | enum, same | § 1.8 |
| Account | `entryStage` | `cEntryStage` | enum, same | |
| Account | — | `cCompanyType` | **enum option added: `Prospect`** | Ruling 21: a Company typed Prospect. The option exists on `cContactType` already (read 2026-10-14); it does not on `cCompanyType` (`Client / Sponsor / Partner / Other`) |

**Field-level access.** The Marketing Admin Role, the intake API role and
every role that edits Contact must be able to read and write the new
fields; a role with a `fieldData` restriction on Contact or Account will
silently strip the write (HTTP 200, nothing stored). The handoff lists the
roles to check.

### 1.7 The campaign id on the relationship records — ruling 27 in storage

The five many-to-one links in § 1.5 (engagement, information request,
event registration, partner profile, funder profile). Written at delivery by
the orchestrator that creates the record, from the `campaign` id the form
carried, after a validate-or-drop read of `COutreachCampaign` (the
`_valid_referring_partner` pattern in `forms/client_intake/orchestrator.py`:
an unknown or stale id drops the attribution, never the submission). The
Contact and Company links are written by the same orchestrator **only when
its own find-or-create returned `created`** — `find_create_or_fill` already
reports `created` / `updated` / `matched`, so the rule costs one condition.

### 1.8 Where the rung continues after promotion — decided: a field on both

Two options were open. **Read it through the link** from the promoted record
back to the prospect record, or **store it again** on the Contact and the
Company.

**Decided: `cFunnelStage` and `cEntryStage` on Contact and on Account.**
The deciding fact is in the walk table: a webinar registrant and an
information requester create **a Contact typed Prospect with no prospect
record at all** (sources 3 and 4, "as today"). There is no link to read
through, so the rung must live on the Contact. Once it lives there for those
records it must live there for all, or every funnel read branches twice.

**Rules that keep two stored copies honest:**

- **Advance-only, evidence-only.** The application writes a rung when it
  observes evidence (a scan, a call outcome, a registration, an information
  request); it never lowers one and staff never set one. The prospect record's
  copy stops changing at promotion; the promoted record's starts at the
  prospect's value.
- **A Contact linked to a Company typed Prospect is counted under the
  Company.** The funnel is company-centric (Doug's diagram); the person's
  copy is for the person's own screens. The funnel read (§ 6) applies this
  so nothing is counted twice.
- **Candidate and Client are never stored.** The enum holds the five rungs
  above the engagement; the reporting read overrides the stored value with
  the engagement-derived rung when an engagement exists.

**Cost:** two fields on each of two native entities in the chapter standard,
and a reporting rule instead of a plain count. The alternative's cost was a
rung with nowhere to live for two of the seven sources.

### 1.9 The Prospect relabel — the one sanctioned type rewrite

Today no door ever rewrites `cContactType` or `cCompanyType`:
`merge_company_type` appends, `_CONTACT_FILL_KEYS` excludes the type, and
event registration's D-09 says a Client who attends a webinar is never
relabelled Prospect. Ruling 21 adds exactly one rewrite in the other
direction: **when a relationship type is appended, `Prospect` is removed.**

Implemented once, in `core/crm_upsert.py`: `merge_company_type` gains the
rule, and a sibling `merge_contact_type` is added for the Contact (the
contact's type is still never null-filled or merged for any other reason —
ruling 21 names the relabel as the one exception). Every door that appends
`Client`, `Partner`, `Sponsor` or `Mentor` goes through these two functions,
so the relabel needs no per-door code. `Presenter`, `Member`, `Donor` and
`Administrator` are not relationship types for this rule and leave
`Prospect` in place.

### 1.10 The prefix check — typed name to stored name

| Typed | Where | Stored | Rule |
|---|---|---|---|
| `Prospect` | Create Entity | `CProspect` | Entity names always gain `C` |
| `OutreachCampaign` | Create Entity | `COutreachCampaign` | Same |
| `OutreachTouch` | Create Entity | `COutreachTouch` | Same |
| `funnelStage` | field on `CProspect` | `funnelStage` | Field on a custom entity: as typed |
| `funnelStage` | field on `Contact` | `cFunnelStage` | Field on a native entity: `c` added |
| `outreachCampaign` | link on `CEngagement` | `outreachCampaign` | Link on a custom entity: as typed |
| `outreachCampaign` | link on `Contact` | `cOutreachCampaign` | Link on a native entity: `c` added |
| `prospectRecords` | reverse link on `Account` | `cProspectRecords` | Same |
| `touches` | reverse link on `CProspect` | `touches` | As typed |
| `partnerProfiles` | link on `COutreachCampaign` | `partnerProfiles` | As typed |
| `sponsoredCampaigns` | reverse link on `CPartnerProfile` | `sponsoredCampaigns` | Custom entity: as typed |
| `outreachCampaigns` | reverse link on `CEvent` | `outreachCampaigns` | Custom entity: as typed |
| `referringPartners` | link on `CEngagement` | `referringPartners` | Custom entity: as typed (beside the existing `referringPartner`) |
| `referredEngagements` | reverse link on `CPartnerProfile` | `referredEngagements` | Custom entity: as typed (`engagements` is already the single link's reverse) |
| `attributedPartnerProfiles` | reverse link on `COutreachCampaign` | `attributedPartnerProfiles` | Custom entity: as typed (ruling 32 — `partnerProfiles` is the CM-2 many-to-many) |

Verified after the build by `GET /Metadata` → `entityDefs.<Entity>`, never
by the Entity Manager list view (the label hides the prefix). Nothing in any
name is chapter-specific.

---

## 2. The import doors

Both imports share one engine (`outreach/imports.py`): parse → normalise →
already-known check → create prospect records → promote what the row allows
→ report. Both are **plan, then apply**: the upload shows what would be
created, matched and skipped, with the counts, and nothing is written until
the reviewer applies that exact plan (the Operations-job pattern). Every
import is action-logged with the batch name.

### 2.1 The state-filing import — enters Qualified (ruling 11)

- **Accepts** a CSV. Columns, as a starting contract from
  `research/registry-enrichment/enrichment-sample-201.csv` plus what the
  filter adds: `business_name` (required), `mailing_street`, `mailing_city`,
  `mailing_state`, `mailing_zip` (required as a set), `external_reference`,
  `website`, `email`, `phone`, `contact_first_name`, `contact_last_name`,
  `qualified_by` (the filter's name and version, else the batch default).
  Unknown columns ride into `importRow`; a missing required column fails the
  plan with the column named.
- **From where:** an upload on the Prospects screen, in Phase 1. A watched
  Drive folder or an endpoint the filter posts to are both possible later;
  which one is question 2, not decided here.
- **Each row** becomes a `CProspect` with `funnelStage=Qualified`,
  `entryStage=Qualified`, `entryDoor=State filing`, `qualifiedBy` and
  `qualifiedAt` set from the batch (ruling 11: no second fit check).
- **Promotion at import** (ruling 21, walk row 2 applies to filings too): a
  row with a `website` creates or matches a Company typed Prospect by
  `website_key`, then by name; a row with an `email` finds or creates a
  Contact typed Prospect by email (null-fill on a match, type untouched).
  The prospect record links to both. In practice almost no filing carries
  either, which is the point of the postcard.
- **Within-batch and across-batch duplicates:** a row whose
  `externalReference` already exists is skipped and reported; without a
  reference, same business name plus same postal code is the key.

### 2.2 The already-known check at import — ruling 12

Runs for every row of both imports, conservatively, close to exact:

1. **Company by name and address.** An Account whose `name` matches
   case-insensitively (EspoCRM's own collation, as every door matches today)
   **and** whose billing postal code equals the row's. Name alone is not a
   match — ruling 12 errs toward mailing a card to an existing client over
   dropping a real prospect.
2. **Company by website key**, when the row has one.
3. **Contact by email**, when the row has one.

A match leaves by the **Already known** side exit: the prospect record is
still created (it is the record that the row arrived and was recognised),
with `sideExit=Already known`, `alreadyKnownCompany` set, and no touch is
ever planned for it. The reviewer can reverse the exit on the record ("Not
the same company") — the one staff-set rung move, back to the entry rung.

### 2.3 The list import — enters Unverified (ruling 18)

Same file contract, plus `list_source` (free text naming the vendor or
partner, stored in `importBatch`). Rows enter at `funnelStage=Unverified`,
`entryStage=Unverified`, `entryDoor=List`; `qualifiedBy` is empty until the
**review screen** (§ 3.8) moves a record to Qualified with the reviewer's
name and time, or out by `Unqualified` with a note. A row carrying an email
or website promotes at import exactly as § 2.1 — identity is separate from
fit.

### 2.4 The partner-file import — deferred (ruling 23)

Not built. A partner-supplied file goes through § 2.3 with `list_source`
naming the partner; `entryDoor=Partner file` is reserved in the enum so the
specialised import, when it is built, needs no CRM change.

---

## 3. Campaigns

### 3.1 The shared engine

One package, `campaigns/`, in the house shape: `service.py` (the CRM logic
and the field whitelists), `router.py` (endpoints, the team gate, the
`_crm_failure` mapping, every mutating action through `record_action`),
`frontend/` (vanilla JavaScript, no build). Gated by `CAMPAIGNS_ENABLED`
(off) and `CAMPAIGNS_ALLOWED_TEAMS` (default Marketing Admin Team — CM-1,
the same team as Submission Admin and Event Administration, matching ruling
13's sign-off team). Mounted at `/campaigns`; portal tile **Campaign
Management** (CM-10, CM-11). The prospect screens (import, review, calls)
live under the same tile as secondary grids — question 12.

The four kinds that select an audience — postcard, email, SMS, call — run
the same five steps; only step 4 differs. Social media runs none of them
(§ 3.6): it is created, given links, and run by posting them.

1. **Create.** A marketing user names the campaign, picks the kind, sets
   the window, names the **partners** (a picker over the partner profiles
   the user may read — the Marketing Admin Role reads them since
   2026-10-07) and the **events** it advertises (a picker over events),
   writes the notes (the shared rich-text editor), and sets the selection
   rule from the screen's choices. The screen offers only the choices the
   kind allows (§ 3.2–3.5); the rule is saved as JSON the application owns
   plus its sentence in `selectionSummary`. Partners and events are written
   through relate / unrelate (two relationships), action-logged. The
   campaign's **links** are made on its Links tab (§ 3.7); a postcard
   campaign gets its one link on creation.
2. **Select.** "Build the list" evaluates the rule against the CRM, under
   the org-wide key (an aggregate over records the Marketing Admin Role may
   not read one by one — the directory-availability precedent), and creates
   one `Planned` touch per selected record with `stageAtTouch` empty. The
   count and, for a postcard, the estimated cost are written to the campaign
   and shown. Re-running replaces the Planned set; nothing already Sent is
   touched.
3. **Sign off** (ruling 13). A second button, *Sign off and run*, shows the
   piece count and the estimated cost once more and requires a typed
   confirmation. It stamps `signedOffByName`, `signedOffAt`, `pieceCount`,
   `estimatedCost`, moves the status to `Signed off`, and is action-logged.
   The ruling names the postcard run; the plan applies the same gate to
   every kind because a call list is work handed to people and an email list
   is a push to the mailing service — the cost of the gate is one click.
4. **Execute** — the kind's engine (below).
5. **Record.** Every state change on a touch is a dated write on the row;
   the campaign screen computes selected / sent / delivered / returned /
   scanned / responded / converted live from the touches and the linked
   relationship records. No count is stored except the two signed-off ones.

The selection rule's choices, common to every kind: rung set (from the five
stored rungs), side exit empty, not already touched by this campaign, and
the window. Kind-specific terms are below. "Reach" is never stored (the
withdrawn proposal): a rule names the fields directly.

### 3.2 The postcard kind — rulings 2, 3, 13, 14, 15, 16

**Selection rule:** `CProspect` records with `funnelStage=Qualified` (or
Lead, for a chapter that wants to re-reach a scanner — offered, default
off), `addressStatus=Usable`, no side exit, **and no Sent postcard touch
from any campaign** — ruling 14, one card per company, ever, until a
second-card campaign is designed. A prospect record holding an email with no
opt-in is selected like any other (ruling 19). A promoted Company typed
Prospect with a usable address and no card is selectable too, so a list row
that arrived with a website is not excluded by its own promotion.

**Execution, on the worker** (sends never run in a web request): for each
Planned touch, generate the `scanToken`, render the QR address
`{APP_BASE_URL}/p/{scanToken}`, call the vendor with the touch id as the
idempotency key, and only on the vendor's accept write `touchStatus=Sent`,
`sentAt`, `vendorPieceId`, `mailedAddress`, `stageAtTouch`. A worker that
dies mid-run resumes from the first Planned row; the idempotency key is what
stops a double mailing. Batches of 100; the run's progress is on the
campaign screen.

**Vendor:** `core/postal.py` — one interface (`create_postcard`,
`verify_address`, `parse_event`), a `DryRunPostalClient` that is the default
and produces the full artefact set (rendered piece previews, zero postage),
and one real adapter. Ruling 2 left Lob and PostGrid as a wash on price; the
plan drafts **Lob** because its test key exercises the whole pipeline,
including the callback, without printing — question 4. Settings:
`POSTAL_PROVIDER` (`dryrun` / `lob` / `postgrid`), `POSTAL_API_KEY`
(secret), `POSTAL_WEBHOOK_SECRET` (secret), `POSTAL_TEST_MODE` (default
true: a real key in test mode still mails nothing).

**Undeliverable returns** (ruling 15): the vendor posts delivery events to
`POST /api/campaigns/postal/events` on the web process, signature-verified,
otherwise unauthenticated. A returned-to-sender event sets the touch to
`Returned` with `returnedAt`, and the prospect record's `addressStatus` to
`Dead` with `addressDeadAt`. The rung is untouched; the record is selectable
again the moment an import row brings a new address (the import resets
`addressStatus` when the address changes). Delivered events set `Delivered`.
The campaign screen counts Returned separately from the silent.

**The QR code** encodes the campaign's one link plus the card's own token
(CM-7): `{APP_BASE_URL}/c/{linkToken}/{scanToken}`. The resolve route
(§ 3.7) counts the visit on the link and opens the landing page
`/p/{scanToken}`; the scan token resolves server-side to the touch, the
prospect record and the campaign, so the card carries neither id in the
clear. **The image is generated by the application** (CM-8), as a PNG at
`GET /c/{linkToken}/{scanToken}/qr.png` for the vendor's template to fetch,
or inlined as a data address in the merge variables — whichever the chosen
vendor's template supports; the dry-run client writes both. The same
generator serves every link's QR on the Links tab.

### 3.3 The email kind — ruling 19, and the mailing-list plan

No cold email, ever. An email campaign selects **Contacts** only
(`cMarketingOptIn` true, address not opted out or invalid — the exact
audience rule of `core/mailing_sync.audience`), typed Prospect with a stored
rung in the chosen set, or — the dormant-client rule of ruling 25 — typed
Client whose latest engagement closed more than N days ago (N on the rule;
default 365). A prospect record is never selected by an email campaign; an
email without consent is simply absent from the rule.

**Execution:** the application does not send. It pushes the selected
Contacts as a **named Constant Contact list** (one list per email
campaign, named after it) through the same push `core/mailing_sync.py`
makes nightly for the standing list, and shows the campaign's links
(§ 3.7) for staff to paste into the notice they design and send there
(mailing-list ruling 6). **A notice's Register link is therefore a campaign
link**, and the registration attribution the mailing plan's Phase D meant
to carry as `noticeCampaignId` on the registration is this (§ 1.5). The touch moves to `Sent` when the mailing-list
plan's Phase D reads the notice's send report, or by a *Mark as sent* button
on the campaign until Phase D exists. **Cost:** the push today manages one
list under `MAILING_LIST_NAME`; generalising it to several named lists is
work in this arc, and the standing list's remove rule (list minus audience)
must not touch campaign lists.

### 3.4 The call kind — ruling 20

**Selection rule:** a phone held — on a `CProspect` (`phone` set) or on a
Contact typed Prospect (`phoneNumber` set, `phoneNumberIsOptedOut` false,
`doNotCall` false) — rung in the chosen set, no side exit, not `Declined`
anywhere. Ruling 9's text consent is irrelevant to a voice call and is not a
term.

**Execution: people.** The campaign becomes a **call list**: every Planned
touch is a row on the call screen (§ 3.8), filtered to the caller's own
rows when the campaign assigns callers, else the whole list. A caller opens
a row, sees the name, the number and the brief, dials, and records one of
three outcomes: **No answer** (the touch is Done, a touch only, and *Call
again* plans a fresh row), **Interested** (Done, and the record moves to
Lead — advance-only), **Declined** (Done, and the record leaves by
`Declined`). `callNotes` is free text; `calledPhone` snapshots the number.
This is the one hand-recorded touch in the whole process, and an unrecorded
call reads as never contacted — the screen says so above the list.

Who calls is question 6. The plan drafts: members of the campaign's teams
(the BasePlus `teams` field), default the Marketing Admin Team; adding the
Mentor Team to a campaign's teams opens its call screen to mentors without a
second gate.

### 3.5 The SMS kind — CM-3 and ruling 9

**Selection rule:** a **Contact** holding a phone number with `cSmsOptIn`
true and `phoneNumberIsOptedOut` false, typed Prospect with a stored rung in
the chosen set, or the dormant-client term of ruling 25. A prospect record
is never selected: consent lives on the Contact (ruling 9), and a prospect
record with a phone and no consent is the call kind's (§ 3.4). The text
consent is the whole gate — ruling 9 was written for exactly this.

**Execution: deferred to a vendor ruling** (question 11). No text-sending
path exists in the application, and the plan does not invent one. In this
arc the SMS kind runs as the email kind does before the mailing plan's
Phase D: the campaign builds and signs off its list, shows its links, and
offers an **export of the list** and *Mark as sent*; the touch moves to
`Sent` by that button. The short address (§ 3.7) matters most here — a text
has 160 characters and a link of forty is a third of it. **Cost:** a kind
that selects and reports but does not send, until a vendor is ruled; the
alternative is to leave SMS out of the enum, which CM-3 does not allow.

### 3.6 The social media kind — CM-3

A broadcast. **No selection rule, no touches, no sign-off**: nothing is
spent through the application and nobody is chosen from the CRM (the
working position recorded with the requirements). The campaign is created
with its platform, its partners and its events, moves to `Running` and
`Complete` by the user's hand, and consists of its **links** (§ 3.7) — one
per post or placement, each named for where it goes ("Facebook post 10-20",
"YouTube description, October webinar"). Its whole footprint is visits and
submissions per link and whatever those submissions become; the Responses
tab and the Analytics tab read exactly as for any other kind. **Draft:** one
kind with a `platform` field rather than a kind per platform, because the
kinds differ in *how they run* and every social platform runs the same way
— question 10.

### 3.7 Links — the short resolvable address (CM-7, CM-8)

**What a link is.** A record of the application's own, owned by one
campaign: a name, a destination, a token, a state, who made it and when,
and its counts. Any number per campaign; each counted on its own. The
destinations are closed: one of the five public intake forms
(`client-intake`, `info-request`, `volunteer`, `partner`, `sponsor`), the
public programme page (`/webinars/`), one event's own page
(`/webinars/{slug}`, chosen by event id so a slug change cannot strand it),
or — created by the application for a postcard campaign only, exactly one
— the landing page. Nothing about a partner rides in a link (CM-4).

**Where it lives — decided as a draft, question 9: the application's
database.** Two tables by Alembic migration: `campaign_link` (id, campaign
CRM id, token, name, destination kind, destination target, state
`active` / `retired`, created by / at, retired by / at) and
`campaign_link_visit` (link id, visited at, a salted hash of the address,
late flag, user-agent class). Reasons: the resolve route runs on every
public click and must answer without a CRM call; visit counts are
write-heavy rows the CRM should never carry; correcting a destination is
then an application write, not a CRM write under a public identity. The
CRM holds the campaign; the relationship records hold the campaign id
(ruling 27); the link is one level finer and stays in the application.
**Cost:** links are invisible inside EspoCRM, and on the training sandbox
they vanish with the nightly application-database reset until the seeder
recreates the demo campaign's links (`SANDBOX-RESET.md`). The alternative
is a fourth custom entity, `CCampaignLink`, visible in the CRM and in the
Analytics builder, with visits still counted in the application.

**The address.** `{APP_BASE_URL}/c/{token}`; the token is eight characters
from `secrets` with the ambiguous glyphs removed (0/O, 1/l/I), so a printed
card or a text message carries about forty characters. `GET /c/{token}`
records the visit, then answers a 302 to the destination with
`?campaign=<campaign id>&link=<token>` appended (for the landing page,
`/p/{scanToken}` with the link token held on the response). Rate-limited
per address like the intake endpoints; a token that resolves to nothing is
a 404 in the same words whatever the reason. **A visit is the resolve**; the
form's name-only banner lookup no longer counts as an open.

**After publishing.** The destination can be **corrected** (the printed or
posted address never changes), action-logged with the old and new
destination. A link can be **retired**: it still resolves and still
redirects — a visitor holding a card never meets a dead page — and the
visit and any submission through it are flagged **late**; the Links tab
shows late counts apart. Who may correct or retire: the campaign's team,
the same gate as the page (draft).

**The programme-page carry-through** (CM-7). `/webinars/?campaign=&link=`
is rendered as today; the page's own script reads the two parameters and
appends them to every event address it renders, the event page's
registration form and the calendar modal carry them as hidden fields, and
the registration arrives with both. Nothing is stored server-side and
nothing about a person is in the address bar — a campaign id and an opaque
token. **Cost:** a visitor who types an event's address afresh, or follows
a link from elsewhere on the site, has left the campaign behind; that is
the honest limit of a query-string carry, and the alternative (a cookie on
the public page) was not chosen because the public pages set none today.

**What the forms do with it.** Every public form and the registration form
carry `campaign_id` and `campaign_link` as hidden fields into the captured
payload (§ 5). Submissions per link, by form, are counted from the durable
submission store on the Links tab; the CRM record gets only the campaign.

**The banner.** A form opened through a link shows *"You arrived through
<campaign name>"* from a public name-only lookup,
`GET /api/campaigns/public/{id}`, which answers the name or a 404 and
nothing else — the partner lookup's shape and the harvester rule.

**The QR code.** `GET /api/campaigns/{id}/links/{linkId}/qr.png` renders any
link's code for the Links tab (download, paste into a post); the public
`GET /c/{linkToken}/{scanToken}/qr.png` serves the vendor's template for
cards (§ 3.2). One generator, a small pure-Python encoder, no external
service — the same code whoever prints the next batch (CM-8).

### 3.8 The screens

The tile **Campaign Management** opens at `/campaigns` on the **Campaigns
grid** (CM-10): every campaign with status, kind, owner, partners, window,
links, visits and submissions, sortable and searchable, *New campaign*,
right-click menus. A campaign opens as a **record page in its own stable
browser tab** (the single-tab guard the session tools use), with four tabs:

- **Overview** — the fields of § 1.3, the partners and the events (CM-10),
  the notes, and for the kinds that select: the rule builder, *Build the
  list*, *Sign off and run*, the run's progress.
- **Links** (CM-7, CM-8) — the campaign's links: *New link* (name,
  destination), each row with its short address and a Copy button, its QR
  code, *Correct destination*, *Retire*, and its counts: visits, late
  visits, submissions by form. A postcard campaign shows its one link and
  the note that each card's code is that link plus the card's token.
- **Responses** (CM-9) — the latest responses with a way through to each
  record (the engagement in Client Administration, the information request
  in Submission Admin, the registration in Event Administration), the
  totals, and for a postcard campaign the block: pieces, delivered,
  returned, scanned; the touch grid for every kind that selects.
- **Analytics** (CM-9) — the campaign-scoped dashboard of § 6: conversion
  down the funnel and whatever the Analytics administrators add.

Under the same tile, as secondary grids (question 12):

- **Prospects** — every `CProspect`, filter chips by rung, side exit, entry
  door and batch; *Import…* (state filing or list; plan, then apply);
  row actions *Qualify* / *Unqualified* (the ruling-18 review, with the note
  required), *Do Not Contact*, *Not the same company* (reverses Already
  known), *Open the Company* / *Open the Contact* when promoted. A detail
  popup shows the record, its touches and its promotion links.
- **Calls** — the call screen of § 3.4, across every Running call
  campaign the user may see.
- **Review** — the Unverified queue of § 2.3, which is the Prospects grid
  pre-filtered; kept as its own grid so the review has a home.

**The partner's Campaigns tab** (CM-5) is on the Partner Management record
page, after the Events tab, gated per domain by a new
`DomainConfig.sponsored_campaigns_link` set only on the partner domain
(`sponsoredCampaigns`, the reverse of § 1.5) — the Events-tab precedent in
every part: the tab and its endpoint registered together, the user's own
read of the partner record gating it, the campaigns and their counts read
under the org-wide key (the Partner Manager Role holds no campaign access
and the numbers are aggregates). Rows: campaign, kind, status, window,
links, visits, submissions; a row opens the campaign for a user the tile
admits, else it is plain text.

Every date and time on these screens is the shared `CBMDateTime` control;
the brief is the shared `CBMRichText` editor; the page loads `busy.js`
first, carries `<meta name="cbm-org">` and uses the `{{org}}` and
`{{abbr}}` tokens; no page width cap.

### 3.9 The word — campaign is ours, notice is Constant Contact's

Three things could be called a campaign: ours, EspoCRM's native entity
(hidden, § 1.1), and a Constant Contact send. **Decided by Doug (CM-11):**
in this application a **campaign** is the `COutreachCampaign` record and
the word on screen means that and nothing else; *outreach* appears in no
user-facing string and survives only in stored names, where it keeps ours
apart from the native entity. A Constant
Contact send is a **notice**, the word the mailing-list plan already uses
for it (§ 4.2 there: "one notice about the event"; the field
`noticeCampaignId`). One correction follows for that plan's unbuilt Phase
D: its staff action reads *Link a campaign* and must read **Link a notice**
when built. Recorded here so the two arcs do not ship two meanings.

---

## 4. The postcard landing page — `/p/{token}`

A public route on the web process, gated by `CAMPAIGNS_LANDING_PUBLIC`
(default false; off, the route 404s). Package `campaigns/landing.py` plus
`campaigns/landing_frontend/`; the page is a route, not a static file, for
the same reasons the event pages are: the body is filled server-side and an
unknown, cancelled or dead token must 404 in the same words as a missing
one.

**On load (the scan — ruling 16).** The token resolves to a `Sent` or
`Delivered` touch. The application writes `firstScannedAt` (first time
only), increments `scanCount`, sets `outcome=Scanned`, and moves the
prospect record (or the promoted Company) to **Lead**, advance-only. That
write is best-effort and never blocks the page. A token on a `Planned`
touch (a preview) renders the page and writes nothing. Rate-limited per
address like the intake endpoints (`intake_rate_limit`).

**What it shows (ruling 16).** The business name and the mailing address
**as mailed** (`mailedAddress`, the snapshot — exactly what the holder is
looking at), both editable, with the shared address paste-parser attached.
**Nothing else the chapter may hold is echoed**: no email, no phone, no
person's name, whatever the prospect record carries. The 2026-08-17
harvester rule, kept.

**What it asks for.** The person's first and last name, email, phone, and
two ticks worded for what each permits: *"You may email me about {{org}}
services and events"* (`cMarketingOptIn`) and *"You may text me"*
(`cSmsOptIn`). Both unticked by default; consent is written true-only. No
terms-of-use consent — the page is not an application; the standard forms
collect that when a relationship begins.

**Three actions, all always clickable, validated on click:**

- **Request information** → saves the response, then opens
  `/info-request/?prospect=<id>&campaign=<id>&link=<token>` — the
  campaign's one link, so the submission counts on it (§ 3.7).
- **Request a mentor** → saves the response, then opens
  `/client-intake/?prospect=<id>&campaign=<id>&link=<token>`.
- **Just update my details** → saves the response and thanks them. Without
  this, a person who wants nothing today but gives consent is lost — and
  consent capture is ruling 19's whole point.

**The response is a sixth form kind**, `forms/prospect_response/`
(`FormSpec` slug `prospect-response`, no frontend directory, the landing page
is its door), so it rides durable capture, idempotency by submission token,
the near-duplicate hold scoped by `scan_token`, and Submission Admin. Its
orchestrator, at delivery:

1. Writes the corrections to the prospect record (`businessName`,
   `mailingAddress`; `addressStatus` back to `Usable` when the address
   changed — the person has just told us where they are).
2. **Email given → the person is promoted** (ruling 21): `find_create_or_fill`
   on Contact by email; a new Contact is typed `Prospect`, carries
   `cFunnelStage` and `cEntryStage` copied from the prospect record, the
   consent ticks, and `cOutreachCampaign` (ruling 27: this submission
   created it); an existing Contact is null-filled, keeps its type, and
   gets `cSmsOptIn` written true-only. `promotedContact` is set if empty.
3. **Website given → the business is promoted** (ruling 21): match by
   `website_key`, then by name; a conflicting stored website on a same-named
   company raises `CompanyConflict`, and the row goes to `held_company` for
   Submission Admin exactly as the three company-creating forms do — the
   anonymous visitor is never told. A new Company is typed `Prospect` with
   the stage fields and `cOutreachCampaign`; a matched one is null-filled
   and `merge_company_type` appends `Prospect` only if it holds no type at
   all (a known Client is not re-typed Prospect). `promotedCompany` is set
   if empty.
4. **Neither given → nothing is promoted.** The corrections and the scan
   are the whole result; the prospect record stays the only record. Ruling
   21: a Company per response, not per card — and not even per response
   without a domain.
5. Never a relationship record. Rulings 4 and 5 keep the landing page below
   the standard forms; the engagement or the information request is theirs.

**Carrying the typed details into the standard form without echoing them.**
The server lookup the standard forms call, `GET /api/campaigns/prospect/{id}`,
returns **only the business name and the mailing address** — ruling 16
applies to the prefill as it does to the page, since the id is in a URL.
The name, email and phone the person just typed travel **in the browser
only**: the landing page writes them to `sessionStorage` under a key the
form reads once and clears. The server never serves a person's details back
to a public page. Ruling 5's "minimise data entry" is met; the harvester
rule is unbroken.

---

## 5. Conversion — what the standard forms do with a prospect id and a campaign id

The partner link (v0.255.0) is the precedent in every part: a hidden field,
the captured payload, a validate-or-drop read, a delivery-time write, and a
notes line saying the link did it. Each public form gains three optional
schema fields, `prospect_id`, `campaign_id` (32 characters at most,
`Optional[str]`) and `campaign_link` (the token, 16 at most), three hidden
inputs filled from `?prospect=`, `?campaign=` and `?link=` — which the
resolve route of § 3.7 appends — and a courtesy banner from the name-only
lookups. Nothing here is load-bearing: a missing, stale or forged value
leaves the form exactly as it is today. The link token is captured for the
per-link counts and never written to the CRM.

**At delivery, every orchestrator that receives the ids:**

1. `_valid_campaign(client, campaign_id)` and
   `_valid_prospect(client, prospect_id)` — a `select="id,name"` read each;
   failure drops the id, never the submission.
2. **The Contact is found or created as today**, by email. If the landing
   page already promoted the person, this is a match and a null-fill.
3. **The Company is created as today** (ruling 22) — **except** that when
   the prospect record's `promotedCompany` is set, that Company is used by
   id before any name match, so the business the landing page promoted is
   not matched a second time into a same-named stranger.
4. **The prospect record is linked**: `promotedContact` / `promotedCompany`
   are set if empty; its stage stops changing.
5. **Nothing is copied.** Consents live on the Contact already; the
   corrections live on the prospect record and the promoted Company.
6. **The campaign id is written** (ruling 27): on the relationship record
   every time; on the Contact and on the Company only when this
   orchestrator's find-or-create returned `created`.
6a. **The campaign's partners are related** (CM-4, ruling 30). The
   orchestrator reads the campaign's `partnerProfiles` (under the intake
   API client, which needs `CPartnerProfile` read — it creates partner
   profiles today, so it has it; the handoff re-checks) and applies the
   door's own rule, in the per-door table below. The engagement is the only
   relationship record with partner links, and it has two: the single
   `referringPartner` of v0.255.0 and the many-to-many `referringPartners`
   (§ 1.5). **The rule:** `referringPartners` holds **every** referring
   partner — the partner link's partner when one arrived, and every partner
   the campaign names — written by relate, under the intake API client
   (relate checks both sides, so the client needs `CPartnerProfile` edit —
   it holds it, as the partner form's creator; the handoff re-checks). The
   single `referringPartner` is written **only** by a partner's own intake
   link, as today — it is the specific claim and the popup band's first
   name — and never by a campaign. The Referred Clients tab and every
   count that reads a referring partner read the **union** of the two
   links, deduplicated. A notes line names the partners the campaign set:
   *"Referring partners set from the campaign <name>: <names>."*
7. **The relabel** (§ 1.9): `merge_contact_type` and `merge_company_type`
   append the door's type and remove `Prospect`.
8. A notes line on the relationship record: *"Arrived through the campaign
   <name>."* — the only record that the link did it, since an application
   write and a hand edit are indistinguishable in the CRM history.

**Per door:**

| Door | Relationship record | Rung evidence written | Type appended | Campaign partners (CM-4) |
|---|---|---|---|---|
| client-intake | `CEngagement.outreachCampaign` | none stored — Candidate is read from the engagement | Client (Contact and Company) | every partner the campaign names into `referringPartners` (ruling 30); `referringPartnerId` untouched; a notes line *"Referring partners set from the campaign <name>: <names>."* |
| info-request | `CInformationRequest.outreachCampaign` | `cFunnelStage=Warm Lead` on the Contact, and on the Company it created, advance-only (ruling 17) | none — Prospect stays until a relationship | no partner field exists; through the campaign |
| event registration (`/webinars/{slug}?campaign=&link=`) | `CEventRegistration.outreachCampaign` | `cFunnelStage=Warm Lead` on the Contact, advance-only; `Opportunity` when attendance is later recorded (§ 6) | none (D-09 stands) | through the campaign (CM-6). The event's own `partnerProfiles` are the event's and are not rewritten by a campaign |
| partner | `CPartnerProfile.outreachCampaign` | — | Partner | through the campaign |
| sponsor | `CSponsorProfile.outreachCampaign` | — | Sponsor | through the campaign |
| volunteer | `—` (CM-7 allows a link to it; ruling 27 names no relationship record for it, so the campaign is counted from the submission store only) | — | — | — |

**The dormant-client campaign (ruling 25)** is a selection rule in § 3.3
and § 3.4, never a rung: a former client who responds submits the intake
form as today, which creates a new engagement on the existing client
profile; the engagement carries the campaign id, and that is the whole
attribution.

**The referring partner and the campaign coexist** on an engagement: the
campaign link, the single partner link and the many-partner link, each
with its own notes line. A partner's intake link carries no campaign; a
campaign link carries no partner (CM-4) — the partners come from the
campaign at delivery, by the rule in step 6a. When both arrive (a partner
pastes a campaign link into their own outreach), the partner link's
partner is written to `referringPartner` **and** to `referringPartners`,
the campaign is written, and the campaign's partners are added to
`referringPartners` too — the client is credited to everyone who referred
them (ruling 30). **What reads the union:** the Client Administration
popup's *Referred by* band (every name, the single link's first), the
partner's Referred Clients tab (`engagements` plus `referredEngagements`,
deduplicated by engagement), and the Analytics engagement metrics that
filter on a referring partner.

**Where the type question for the information request stands.** Today
that door creates its Company typed `Client` with `cClientStatus=Prospect`
("nearest fit", from before a Prospect type existed on Companies). Ruling
21's vocabulary wants a Company typed `Prospect`. The plan recommends the
door create it typed `Prospect` once the option exists, with
`cClientStatus` untouched, so the relabel at conversion reads the same for
every door — question 7, because it changes a live door's behaviour.

---

## 6. Reporting

**Four reads, one rule.** Every number comes from `campaigns/reporting.py`,
so every screen agrees (the active-client-count discipline). CM-9 splits
them by who changes them: the first read below is the campaign page's own
and fixed; the funnel and conversion are Analytics.

0. **The campaign page's numbers** (CM-9) — from the application's own
   data, never cached: per link, visits, late visits and submissions by
   form (`campaign_link_visit` and the durable submission store, keyed on
   the captured `campaign_id` and `campaign_link`); the campaign totals;
   the latest responses with their record ids from the submission result;
   for a postcard campaign the touch counts (pieces, delivered, returned,
   scanned).

1. **The funnel** — a count per rung over the **union** of three sets:
   `CProspect` records with no side exit and no `promotedCompany` or
   `promotedContact`; Companies typed Prospect; Contacts typed Prospect
   whose `account` is **not** a Company typed Prospect (§ 1.8's rule
   against double counting). Candidate and Client are counted from
   engagements by the existing rules (an engagement with no completed
   session; one with). The bands are grouped above the rungs.
2. **Touches by campaign** — per `COutreachCampaign`: planned, sent,
   delivered, returned, scanned, responded (a `prospect-response` or
   relationship record carrying the campaign), converted (a relationship
   record carrying it), with `stageAtTouch` breakdowns so a campaign's
   results are read against the rung its targets were on that day.
3. **Entry rung per door** — `entryStage` × `entryDoor` on `CProspect`,
   plus `cEntryStage` on Contacts created by the information request and
   event registration doors, so a door entering half-way down is never read
   as converting better.

**Which are Analytics metrics and which need a screen:**

- **Touches by campaign** and **entry rung per door** are single-entity
  counts with filters and a breakdown — exactly what the Analytics builder
  makes self-serve (entity + filters + aggregation, `breakdown` shape). They
  ship as built-in metrics on a new Analytics page *Campaigns*, and
  admins can derive more without a deploy. The campaign page shows its own
  row of the same numbers from the shared module.
- **The funnel** is a union across three entities with a dedupe rule and
  an engagement-derived override; the builder cannot express it, so it is a
  **built-in computed metric** (`analytics/computed.py`, the operational
  metrics' home), shape `rows`, under the org-wide key. It renders on the
  same Analytics page and as the campaign tab's header strip.
- **The campaign's Analytics tab** (CM-9) is a **new dashboard scope**,
  `COutreachCampaign` — the eighth record view to host one, under the
  one-dashboard-per-record-type rule — with a starter dashboard: Candidates
  and Clients from the engagements carrying the campaign (the existing
  engagement-derived rules), registered and attended from the registrations
  carrying it, information requests, partner and funder profiles, each a
  record-scoped metric filtered on the `outreachCampaign` link, **run live
  as the user and never cached** (the Analytics rule for record scope).
  Cross-campaign comparison is a page the Analytics administrators author
  from the same metrics. **Cost:** a new scope in `analytics/registry.py`
  and the record-page host, plus the Analytics Admin Team building anything
  beyond the starter before the tab says more than it ships with.

**Opportunity** is written when attendance is recorded on a
`CEventRegistration` whose Contact is typed Prospect, whatever the
attendance source — Phase 6a's Zoom pull (off everywhere) or a manual
check-in. No new attendance work is in this arc; the write hangs off the
existing attendance update.

**Stale.** A worker sweep, nightly, moves a prospect record with no stage
change for `PROSPECT_STALE_DAYS` (default 180) and no Planned touch to
`sideExit=Stale`. Records are never deleted; Stale is the re-entry point if
a second-card campaign is ever designed. The period is a setting at
`/setup`.

---

## 7. Phases

Each phase ships dark, is enabled on crm-test's overlay or at `/setup`,
reviewed live as a real non-admin in the relevant team, then enabled on
production. Rollback is the flag. The CRM change for a phase goes through
`prds/chapter-network/crm-update-runbook.md`: handoff written, crm-test
first, rebuild, shape verified in `GET /Metadata`, grants verified as the
org-wide key **and** as a real non-admin, soak, production at the Sunday
17:00 UTC slot, Boston with its release. **Both handoffs add tables**, so the
training sandbox's nightly reset will truncate them until a re-baseline
(`SANDBOX-RESET.md` § *Re-baseline*); the phase-1 script says when.

### Phase 1 — one real card, one real scan

**CRM handoffs first (both additive):**

- `contact-sms-opt-in-crm-handoff.md` + `scripts/plans/contact-sms-opt-in.json` — `Contact.cSmsOptIn`; the field-level check on every role that edits Contact.
- `coutreach-entities-crm-handoff.md` + `scripts/plans/coutreach-entities.json` — the three entities, their fields (kinds per CM-3, `platform`), all seventeen links of § 1.5 including the three many-to-many (partners — CM-2; events — CM-6; `CEngagement.referringPartners` — ruling 30; the five relationship-record links are additive and cheap now, and Phase 2 then needs no CRM change), the four stage fields, the `Prospect` option on `cCompanyType`, and `scripts/migrate_outreach_roles.py` for the grants: the intake API role (`CProspect` create/read/edit, `COutreachTouch` create/read/edit, `COutreachCampaign` read **and its `partnerProfiles` relationship read**, `CEngagement` edit with `CPartnerProfile` edit for the `referringPartners` relate — both held today, re-checked — and the new Contact/Account fields), the Marketing Admin Role (all three: create/read/edit at `all`, **Assignment Permission `all`** — a role that creates a record the application leaves unassigned needs it, the presenters finding — plus `CEvent` read for the events picker, which it holds). The links of CM-7 need no CRM change (§ 3.7, question 9).

**Flags:** `CAMPAIGNS_ENABLED`, `CAMPAIGNS_ALLOWED_TEAMS`, `CAMPAIGNS_LANDING_PUBLIC`, `POSTAL_PROVIDER` (`dryrun`), `POSTAL_API_KEY`, `POSTAL_WEBHOOK_SECRET`, `POSTAL_TEST_MODE`. The resolve route `/c/` is on whenever `CAMPAIGNS_ENABLED` is — a published link must keep working.

**Build:** the `campaigns/` package — the Campaign Management tile, the Campaigns grid, the record page with Overview, Links and Responses (the Analytics tab is Phase 4), partners and events on the Overview, the Prospects grid; the link tables, the resolve route, correct and retire, the QR generator, the visit count (§ 3.7); the social media kind (links only — it needs nothing else and gives the Links tab a real user from day one); the state-filing import (upload, plan, apply) with the already-known check; the postcard kind end to end — selection, sign-off, the worker run, `core/postal.py` with the dry-run client and the chosen vendor's adapter, the callback, the one link and the per-card code; the landing page and `forms/prospect_response/`; the partner's Campaigns tab (CM-5 — a config line, an endpoint and a grid on the existing record page); the SMS tick on the five intake forms and the event registration form (true-only, beside the marketing opt-in, wording naming texts); the three hidden values on every public form and the registration form, **captured and ignored** at delivery (Phase 2 honours them) — captured, because the per-link counts come from the store. Migrations: `campaign_link`, `campaign_link_visit`, and the import ledger (batch, row hash, result) so a re-upload of the same file is a no-op.

**Live verification, on crm-test, as Mark Marketing (Marketing Admin Team), then once more as the org-wide key where stated:**

1. `GET /api/v1/CProspect?maxSize=1`, `COutreachCampaign`, `COutreachTouch` as the org key → HTTP 200 (a 403 is a missed grant).
2. Sign in as Mark Marketing; the portal shows **Campaign Management**; open it; the Campaigns grid is empty. Open Prospects. Import a five-row CSV: one row naming an existing sandbox client company and its postal code, one with a website, one with an email, two with address only. The plan shows: 1 Already known, 1 Company typed Prospect to create, 1 Contact typed Prospect to create, 5 prospect records; apply; the Prospects grid shows five rows at Qualified, one flagged Already known with the company linked.
3. Re-upload the same file: the plan shows nothing to do.
4. New campaign, kind Postcard, name a sandbox partner on it, rule Qualified + usable address; the Links tab shows its one link; *Build the list* → 4 Planned touches (the Already known row absent); *Sign off and run* shows 4 pieces and the dry-run cost; confirm. The worker log shows 4 pieces accepted by the dry-run client; the touches read Sent with a `scanToken` each; the preview artefacts show the QR, and decoding one gives `/c/<link>/<scan>`.
4a. New campaign, kind Social media, platform Meta, two links: one to the client-intake form, one to the programme page. Signed out, open each short address: the first lands on the form with the banner naming the campaign; the second lands on the programme page and every event address on it carries `campaign` and `link`. Back on the Links tab both read 1 visit. *Correct destination* on the first to the info-request form: the same short address now opens that form. *Retire* the second: it still opens the programme page; its next visit counts as late.
4b. As `partner.manager`, open the partner named in step 4: the Campaigns tab lists both the postcard campaign and nothing else (the social one named no partner); the row shows its link count and visits.
5. *Build the list* again on a second postcard campaign → 0 (ruling 14).
6. Signed out, open the card's address `/c/<link>/<scan>` from touch 1: it resolves to `/p/<scan>`, the postcard link reads one more visit, and the page shows that row's business name and mailed address, nothing else; the touch now reads Scanned with `firstScannedAt`; the prospect record reads Lead. Reload: `scanCount` 2, `firstScannedAt` unchanged.
7. On that page enter a name, an email the sandbox does not hold, both ticks, press *Just update my details*: a `prospect-response` row delivers; a Contact typed Prospect exists with `cMarketingOptIn`, `cSmsOptIn`, `cFunnelStage=Lead`, `cEntryStage=Qualified`, `cOutreachCampaign` set; the prospect record's `promotedContact` points at it.
8. On touch 2's page enter a website whose host matches an existing sandbox company under a **different** name: a new Company typed Prospect is created (name match is by name; a different name is a different company). On touch 3's page enter the name and website of an existing company whose stored website differs: the row holds as `held_company` in Submission Admin, and *Same company* delivers it against the existing record with `Prospect` **not** appended.
9. Post a dry-run *returned* event to the callback for touch 4: the touch reads Returned, the record's `addressStatus` reads Dead, the rung is unchanged; the campaign's counts show 1 returned.
10. Press *Request a mentor* on touch 1's page: the client-intake form opens with the business name and address prefilled, the banner names the campaign, the typed name and email are filled from the browser; submit; the engagement is created **as today, with no campaign and no partner on it** (Phase 2 owed), and the Links tab shows 1 submission (client-intake) on the postcard link — the count comes from the store, not the CRM.
11. Open the client-intake form with the campaign id altered: no banner, the form works.
12. As `sally.sponsor` (no team seat): `/campaigns` answers 403 naming the Marketing Admin Team; `/c/<link>` still resolves for her signed-out browser — the resolve route is public.
13. Tick the SMS box on the public client-intake form and submit: the Contact reads `cSmsOptIn` true; submit once more unticked for the same email: still true.
14. Then, on a morning after a reset with no release test running: seed and re-baseline the sandbox so the three tables survive the night.

**Not before the first real card:** question 2 (the filter's file), question 4 (the vendor account — Doug opens it), question 5 (the card itself). The first real run is 25–50 pieces, signed off by Doug, with `POSTAL_TEST_MODE=false` set at `/setup` for that run only.

### Phase 2 — the doors honour the ids

**CRM change:** none (the links shipped with Phase 1's handoff).
**Flag:** none — dark by nature (no id, no change) and feature-detected per link from metadata, so a CRM without the links drops the attribution with a logged note.

**Build:** § 5 in the five orchestrators (client intake, info request, event registration, partner, sponsor), including step 6a's partner rule (CM-4, ruling 30) and the union reads on the popup band and the Referred Clients tab; `merge_contact_type` and the relabel rule in `core/crm_upsert.py`; the campaign banner on the forms and the event page; the programme-page carry-through and the hidden values on the event page's registration form and the calendar modal (§ 3.7); the information request's Company typed Prospect (question 7); the notes lines; the Responses tab's record links and the campaign page's *responded* and *converted* counts.

**Live verification, as Mark Marketing for the reads and signed out for the forms, on crm-test:**

1. A card's *Request a mentor* through to delivery, the postcard campaign naming one partner: the engagement carries the campaign and that partner in `referringPartners` (the single `referringPartner` stays empty), and both notes lines; the partner's Referred Clients tab lists it; the popup's *Referred by* band names it; the Contact and Company created by it carry `cOutreachCampaign`; the prospect record's promotion links are set; the Contact's type reads `Client` with no `Prospect`; the Company's type reads `Client` with no `Prospect`.
1a. The same through a campaign naming **two** partners: the engagement carries the campaign and **both** partners in `referringPartners` (ruling 30); it appears on the campaign's Responses tab, on both partners' Referred Clients tabs and on both partners' Campaigns tabs; the band names both.
1b. The partner's own intake link with a campaign's `?campaign=&link=` appended (a partner reposting a campaign link): `referringPartner` is the link's partner, `referringPartners` holds that partner **and** the campaign's partners, the campaign is written; the Referred Clients tab of each lists the engagement once.
2. The same person again through `/info-request/?campaign=<a second campaign>`: the information request carries the second campaign; the Contact keeps the first (ruling 27).
3. From the social campaign's programme-page link (step 4a of Phase 1): open it signed out, pick an event from the page, register as a Contact typed Prospect from Phase 1: the registration carries the campaign, the Links tab shows 1 submission (event registration) on that link, the Contact's `cFunnelStage` reads Warm Lead and its type is unchanged (D-09). Register for the same event from a freshly typed address: no campaign — the carry-through's honest limit.
4. A Company typed Prospect submits the partner form: `cCompanyType` reads `Partner` with no `Prospect`; the partner profile carries the campaign.
5. An altered campaign id on each form: the record is created, no campaign, a warning in the web log.
6. The Client Administration popup opens the engagement from step 1 and shows the notes line; Submission Admin shows the `prospect-response` rows with their references.

### Phase 3 — lists, review, calls

**CRM change:** none.
**Flags:** `CAMPAIGNS_CALLS` (the Calls grid and the call kind), inside `CAMPAIGNS_ENABLED`.

**Build:** the list import with `list_source`; the Review tab with *Qualify* and *Unqualified* (note required, reviewer stamped); *Do Not Contact* and *Not the same company*; the call kind: rule, call list, the recording screen with the three outcomes and *Call again*; `Declined`; the nightly Stale sweep with `PROSPECT_STALE_DAYS`; the touches-by-campaign and entry-rung metrics on the new Analytics page.

**Live verification, as Mark Marketing, and as a second non-admin on a team the campaign names for the calls:**

1. Import a list of four rows (one with a phone): four records at Unverified in the Review tab; *Qualify* two with notes; *Unqualified* one; the fourth stays.
2. New campaign, kind Call, rule Qualified + phone held: *Build the list* → the rows with a phone (the Unverified one absent); sign off.
3. As the second user on the campaign's team: the Calls tab lists the rows; record *No answer* on one (Done; *Call again* plans a fresh row), *Interested* on another (the record reads Lead), *Declined* on the third (side exit Declined, absent from every later build).
4. As a user on no team the campaign names: the Calls tab is empty with a message naming the team.
5. Set `PROSPECT_STALE_DAYS=0` at `/setup`, run the sweep from Operations as a dry run then apply: untouched Qualified records read Stale; Lead records with a scan today do not. Reset the setting.
6. The Analytics page shows touches by campaign and entry rung per door matching the grids.

### Phase 4 — email and SMS campaigns, the funnel, the campaign dashboard

**CRM change:** none.
**Flags:** `CAMPAIGNS_EMAIL` (the email kind), inside `CAMPAIGNS_ENABLED` and the mailing-list connection; `CAMPAIGNS_SMS` (the SMS kind: rule, list, export, *Mark as sent* — no sending, question 11).

**Build:** the email kind: rule (opted-in Contacts; the dormant-client term), the per-campaign named list push through `core/mailing_sync.py` generalised to several lists, *Mark as sent*, and the Phase D read when that exists; the SMS kind (§ 3.5) to the same shape, with the list export; the funnel computed metric and the Analytics page *Campaigns*; **the `COutreachCampaign` dashboard scope and its starter dashboard on the record page's Analytics tab** (CM-9, § 6); `Opportunity` on attendance.

**Live verification, as Mark Marketing, on crm-test with its own Constant Contact account (the mailing-list plan's ruling A):**

1. New campaign, kind Email, rule Prospect + opted in: the list shows only Contacts with `cMarketingOptIn` true and a usable address; a Contact holding an email without the tick is absent (ruling 19).
2. Sign off: a Constant Contact list named after the campaign appears with exactly those addresses; the standing list is unchanged.
3. The dormant-client rule with N=0 lists the sandbox's closed-engagement clients with the tick; N=3650 lists none.
4. The funnel on the Analytics page: counts per rung add up to the union of the three grids with the dedupe rule, checked against the CRM's own list counts by hand once.
5. Record attendance on a registration whose Contact is typed Prospect: the Contact reads Opportunity.
6. New campaign, kind SMS, rule Prospect + phone + text consent: the list holds only Contacts with `cSmsOptIn` true (the Phase 1 step-7 Contact is in it; a Contact with a phone and no tick is not); sign off; the export downloads those numbers; *Mark as sent* moves the touches to Sent.
7. The postcard campaign's Analytics tab shows the starter dashboard: one Candidate (Phase 2 step 1), registered and attended counts matching Event Administration, every panel rendered as Mark Marketing without a 403.

### Phase 5 — deferred, named so they are not forgotten

Not planned, no dates: the partner-file import (ruling 23); **sending** texts through a vendor (the SMS kind, its rule, its list and its export ship in Phase 4; the vendor is question 11); a second-card campaign (ruling 14 waits for a measured response rate; the Stale exit is its entry point); a watched Drive folder or a posting endpoint for the outside filter (question 2); a funder Campaigns tab (one `DomainConfig` line if ever asked for — CM-5 named partners); Phase D of the mailing-list plan feeding email touches.

---

## 8. The open list — each item answered or put to Doug

From `history/prospect-marketing-plan.md`, *Open after this session*:

| Item | Status | Where |
|---|---|---|
| Rung 1's name | **Ruled (29, 10-14-26): `Unverified`** | Question 3 |
| Where the rung continues after promotion | **Answered:** a field on Contact and Account, because two sources never have a prospect record | § 1.8 |
| The call campaign's recording screen | **Answered:** the Calls tab, three outcomes, *Call again*, the warning that an unrecorded call reads as never contacted | § 3.4 |
| Retention | **Answered as a draft:** Stale after `PROSPECT_STALE_DAYS` (180), never deleted, a `/setup` setting | § 6 |
| Attendance evidence for Opportunity | **Answered:** written off the existing attendance update whatever its source; no new attendance work | § 6 |
| The campaign entity's shape | **Answered, and since defined by Doug (CM-1 to CM-11):** § 1.3, § 1.5, § 3.7, § 3.8; the card's code is the campaign's link plus the card's token; which forms honour the id is § 5's table; the partner link and the campaign link coexist as two links, with the campaign's partners related by step 6a | §§ 1, 3, 5 |
| The Prospect-to-type relabel | **Answered:** one rule in the two merge functions; every door inherits it | § 1.9, § 5 |
| Chapter-network vocabulary | **Answered:** every name checked in § 1.10; `externalReference` and `State filing` replace the state-specific words | § 1.10 |
| What the outside filter delivers, and how | **Put to Doug** | Question 2 |
| The postcard offer and creative | **Put to Doug** — outside this repository; the template's size and QR placement constrain `postcardSize` and the vendor template | Question 5 |
| Which address is mailed | **Put to Doug with question 2** — the import takes one mailing address per row; if the filter delivers both, the plan mails the business's own address, not a registered agent's | Question 2 |

Two items this plan added: the entity choice (question 1) and the vendor
(question 4); who makes the calls (question 6) and the information
request's company type (question 7).

**The requirements section's own open list** (*Still open after this
session*, 10-14-26), each answered here or put to Doug:

| Item | Status | Where |
|---|---|---|
| Several partners on one engagement (CM-4) | **Ruled (30, 10-14-26): multiple referring partners** — a many-to-many `referringPartners` beside the single link; the recommendation was declined | § 1.5, § 5 step 6a, question 8 |
| Social media: one kind with a platform, or a kind per platform | **Put to Doug** — written on: one kind, a `platform` field | § 3.6, question 10 |
| SMS has no sending path | **Put to Doug** — written on: the kind ships with its rule, list and export; sending waits for a vendor | § 3.5, question 11 |
| One event or many per campaign | **Answered as a draft:** many (a many-to-many), from Doug's plural and the programme-page link | § 1.5 |
| The status vocabulary | **Answered as a draft:** the six states of § 1.3, which the application moves; Doug's four-word strawman maps onto them | § 1.3 |
| Who may correct or retire a link | **Answered as a draft:** the campaign's team, action-logged with old and new | § 3.7 |
| The programme-page carry-through | **Answered:** query-string carry by the page's own script, with its honest limit named | § 3.7 |
| Where the prospect screens live | **Put to Doug** — written on: under the Campaign Management tile as secondary grids | § 3.8, question 12 |
| A per-campaign Analytics dashboard | **Answered:** a new dashboard scope, starter dashboard, Phase 4 | § 6 |
| Where links live (new in this revision) | **Ruled (31, 10-14-26): the application's database** | § 3.7, question 9 |

---

## 9. Questions for Doug

Each is written on the recommended answer. **Questions 1, 3, 8 and 9 were
answered on 10-14-26 (rulings 28–31)** and are kept here with their
answers; question 8 went against the recommendation and §§ 0, 1.5, 1.10,
5, 7 and 8 were revised to match. Questions 8–12 were added in v0.2, from
the Campaign Management requirements.

1. **Custom entities, or EspoCRM's own Lead and Campaign?** **Answered:
   custom (ruling 28).** Recommended: custom (§ 1.1). Cost: three entities and sixteen links in the standard,
   and the native `campaign` link stays unused. The alternative's cost: core
   grants, tabs and a required-flag change on every chapter's CRM, two of
   them unverified.
2. **What does the outside filter deliver — the columns, where it lands,
   how often — and which address when a row carries two?** The plan takes a
   CSV upload on the Prospects screen with the § 2.1 columns and mails the
   business's own address. Nothing is built for the delivery path until this
   is answered; the upload works for any answer.
3. **Rung 1's stored name: `Unverified` (recommended) or `Unqualified`?**
   **Answered: `Unverified` (ruling 29).** `Unqualified` is a terminal reject in every surveyed CRM and is also the
   fit-failure side exit here, so one word would mean two things.
4. **Which mail vendor: Lob (recommended) or PostGrid?** Price is a wash
   (ruling 2); Lob's test key runs the whole pipeline, callback included,
   without printing. Doug opens the account; the plan never does.
5. **The card.** Who designs it, which size (`4x6` / `6x9` / `6x11`), and the
   offer text. The template holds the QR code and the business name and
   address merge fields; everything else is creative.
6. **Who makes the calls?** Recommended: members of the teams named on the
   campaign, default the Marketing Admin Team; naming the Mentor Team opens
   the list to mentors. Cost: a mentor who calls needs read and edit on
   `COutreachTouch` and read on `CProspect` in the Mentor Role.
7. **Should the information request door create its company typed
   `Prospect`** (recommended) instead of today's `Client` with
   `cClientStatus=Prospect`? It makes the relabel at conversion read the
   same for every door. Cost: a live door's behaviour changes, and existing
   records keep the old shape unless a one-time script relabels them.
8. **A campaign with several partners, on an engagement.** **Answered
   against the recommendation: multiple referring partners (ruling 30)** —
   the alternative below is what is built (§ 1.5 `referringPartners`,
   § 5 step 6a). The engagement
   holds one referring partner today. Recommended: write it only when the
   campaign names exactly one partner (and no partner link named one);
   otherwise the engagement carries the campaign alone and the partners are
   one hop away. Cost: a client who came through a two-partner campaign is
   absent from both partners' Referred Clients tabs and present on their
   Campaigns tabs instead. The alternative is a second, many-partner link
   on the engagement (one more CRM link; the Referred Clients tab reads
   two links and every count that reads `referringPartner` reads both).
9. **Where campaign links live.** **Answered: the application's database
   (ruling 31).** Recommended: the application's own
   database (§ 3.7) — the resolve route never calls the CRM, visits are
   write-heavy rows, a destination correction is not a CRM write. Cost:
   links are invisible inside EspoCRM and vanish nightly on the sandbox
   until seeded. The alternative is a fourth custom entity,
   `CCampaignLink`, visible in the CRM and to the Analytics builder, with
   visits still counted in the application; it changes the Phase 1 handoff.
10. **Social media: one kind with a platform field** (recommended — every
    platform runs the same way, so the kinds stay about *how a campaign
    runs*) **or one kind per platform** (Meta, YouTube, … each its own enum
    value). Cost of the recommendation: a second field to fill in; of the
    alternative: the kind list grows with every platform and a filter by
    "social" becomes a list of values.
11. **SMS sending.** Recommended: ship the kind with its selection rule, its
    signed-off list and an export, and no sending, until you name a vendor.
    Cost: a kind that does not send; staff send from the vendor's own tool
    with the exported list and press *Mark as sent*. The alternative is to
    rule a vendor now (Twilio is the usual one), which adds a client, a
    secret, a sender number and the opt-out handling the law requires.
12. **The prospect screens' home.** Recommended: Prospects, Review and Calls
    as secondary grids under the *Campaign Management* tile — one tile for
    the whole marketing workspace, the same team either way. Cost: a tile
    named for campaigns also holds the import; the alternative is a second
    tile, *Prospects*, on a portal that already shows a staff user twelve.

---

## 10. Conventions every new screen in this arc follows

Stated once so the build cannot drop them: `busy.js` loaded first on every
page; `<meta name="cbm-org">` and the `{{org}}` / `{{abbr}}` tokens, never
the organisation's name or acronym in served text; every date and time
through `CBMDateTime` (never a `datetime-local`); every rich-text field
through `CBMRichText`; the address paste-parser on the landing page's
address block and the landing page added to `ADDRESS_PAGES`; no page width
cap, density by packing; every action button always visible and clickable,
validating on click with a message naming the missing input or grant; every
mutating staff action through `record_action` at the router; every CRM-facing
feature feature-detected from metadata so it stays dark until the field
exists; best-effort side effects (the scan write, the stamp, the notes
line, the relabel) report through the response and never fail a save; list
reads paged at 200; a 403 and a 404 from the CRM kept apart in every
best-effort mirror.

---

## Revision control

| Field | Value |
|---|---|
| Document | Prospect Marketing — build plan |
| Version | v0.4 — a plan, nothing built; questions 1, 3, 8 and 9 answered (rulings 28–31), multiple referring partners on an engagement; the handoff's one open name ruled (32); eight questions open, none shaping the CRM |
| Last Updated | 10-15-26 00:02 |
| Prepared by | Claude (Claude Code), for D. Bower |
| Session | 2026-10-14 planning session (v0.1) and the same evening's revision session (v0.2), both from `history/prompts/prospect-marketing-build-plan-prompt-v0.1.md`; moved into this directory the same night (v0.2.1) |
| Related | `rulings.md` (rulings 1–27 and the Campaign Management requirements CM-1 to CM-11), `history/prospect-marketing-plan.md` (the discussion record), `prds/mailing-list-and-event-sponsorship-plan.md` (the notice vocabulary, the push), `prds/chapter-network/crm-update-runbook.md`, `forms/client_intake/orchestrator.py` (the partner-link precedent), `core/crm_upsert.py`, `core/mailing_sync.py` |

### Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.4 | 10-15-26 00:02 | Claude (Claude Code) | Ruling 32: § 1.5's reverse of `CPartnerProfile.outreachCampaign` is `attributedPartnerProfiles` (the row had named `partnerProfiles` twice; found by the handoff session's dry run, drafted there, chosen by Doug); § 1.10 gains the row. The plan files were already written on this name, so the fingerprints stand. |
| 0.3 | 10-14-26 22:43 | Claude (Claude Code) | Doug's answers to questions 1, 3, 8 and 9 recorded (rulings 28–31). Question 8 against the recommendation: `CEngagement.referringPartners` many-to-many to `CPartnerProfile` (reverse `referredEngagements`) added — seventeen links; step 6a rewritten (the many link holds every referring partner, the single link stays the partner link's own, readers take the union); the per-door table, the coexist paragraph, Phase 1's handoff and grants, Phase 2's build and verification, § 8 and § 9 updated. |
| 0.2.1 | 10-14-26 22:27 | Claude (Claude Code) | Moved from `prds/prospect-marketing-build-plan.md` into `prds/prospect-marketing/` (Doug's consolidation ruling, 10-14-26); references to the process plan now point at `rulings.md` and `history/`. No section revised. |
| 0.2 | 10-14-26 22:09 | Claude (Claude Code) | Revised against the Campaign Management requirements (CM-1 to CM-11): the campaign is labelled Campaign and names partners and events (two many-to-many links, sixteen in all); five kinds with the SMS kind (§ 3.5) and the social media kind (§ 3.6) added; a new § 3.7 for links as short resolvable addresses in the application's database, with correct, retire, the programme-page carry-through and the QR generator; the screens rebuilt around the Campaign Management tile, the campaign record page (Overview / Links / Responses / Analytics) and the partner's Campaigns tab; the forms carry the link token and relate the campaign's partners by door (step 6a); reporting gains the campaign page's own numbers and a campaign dashboard scope; the phases, their flags (`CAMPAIGNS_*`, `PROSPECT_STALE_DAYS`) and verification scripts updated; the requirements' open list answered in § 8; questions 8–12 added. The superseded-in-part pointer replaced by this revision note. |
| 0.1.1 | 10-14-26 21:55 | Claude (Claude Code) | Pointer added at the top: superseded in part by *Requirements — Campaign Management application (10-14-26)* in the plan (CM-1 to CM-11); the sections v0.2 must revise are named there. No section revised. Duplicated date in Last Updated fixed. |
| 0.1 | 10-14-26 17:34 | Claude (Claude Code) | First version: the record model in Entity Manager vocabulary (three custom entities, fifteen links, the stage fields, the relabel), the two import doors, the three campaign kinds on one engine, the landing page as a sixth form kind, conversion per door, reporting, five phases with handoffs and verification scripts, the open list, seven questions. Finding recorded: the native marketing module is hidden on crm-test and the org key 403s on Lead and Campaign. |
