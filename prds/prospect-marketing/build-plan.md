# Prospect Marketing — build plan v0.2 (2026-10-14)

Last Updated: 10-23-26 01:25 · Revision 0.37 — change log at the end.

**v0.8 (10-18-26 23:16): rulings 41–44 change the record model.** Every
record from an outside source is a **Lead** (Unqualified, Qualified,
Disqualified); a Company or Contact typed Prospect is created only at first
contact; campaigns may select Unqualified leads; "door" is retired. Phases
1–4 were built on the earlier model, so **§§ 1–6 describe what is built,
not what is ruled**, until the rework in **§ 7a** is built. Questions 13–16
in § 9 gate it.

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

**The type question for the information request — ruled (34, 10-17-26).**
Until then that door created its Company typed `Client` with
`cClientStatus=Prospect` ("nearest fit", from before a Prospect type existed
on Companies). The door now creates it typed `Prospect` with `cClientStatus`
untouched, so the relabel at conversion reads the same for every door; a
company the CRM already knows keeps the types it has; the write
feature-detects the `Prospect` option and falls back to the old shape until
a CRM carries it; `scripts/relabel_info_request_companies.py` relabels the
companies created under the old shape, once per CRM.

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

**Built 10-17-26, v0.259.0** (`campaigns/attribution.py` and the five
orchestrators; the union reads; `merge_contact_type`; ruling 34; the
carry-through; the Responses tab's counts and links). Verified by tests only
— the six steps below are Doug's live pass, `OPEN-ITEMS.md` #51.

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

**Built 10-18-26, v0.261.0** (`campaigns/review.py`, `calls.py`,
`stale.py`, `reporting.py`, `frontend/calls.html`; `analytics/campaigns.py`).
Question 6 answered first — **ruling 36**: callers are the members of the
teams named on the campaign, each acting as themself; the Mentor Role gains
`COutreachTouch` read/edit and `CProspect` read through
`scripts/migrate_outreach_roles.py` (so "no CRM change" holds for shape,
not for grants). Ruling 37 (no rung on a record holding a relationship
type) built first as v0.260.2. The Analytics page is named *Campaigns*, as
§ 6 says. Verified by tests and a stub harness only — the six steps below
are Doug's pass, `OPEN-ITEMS.md` #51, step page
https://claude.ai/artifact/D8atEqEdRaRBKh4mmxiPsj.

**CRM change:** none (the Mentor Role's two grants aside — ruling 36).
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

**Built 10-18-26, v0.262.0–v0.264.0.** Question 11 answered first, against the
recommendation — **ruling 38: the application sends the texts** (Twilio behind
a dry-run default, `core/sms.py`, `campaigns/sms.py`; STOP honoured at once;
texting hours; an interrupted send never resent by itself) — and **ruling
39: the wording is `COutreachCampaign.smsMessage` in the CRM** (one field,
`scripts/plans/coutreach-sms-message.json`), so Phase 4 carries a CRM change
after all. The email kind pushes each campaign as its own named list
(`campaigns/email.py`); the funnel is a panel on the *Campaigns* page; the
`COutreachCampaign` dashboard scope's counts run under the org key after the
user's read (the Marketing Admin Role reads no engagement). Tests and a stub
harness only; Doug's pass: https://claude.ai/artifact/96dzUAsNAfkbJCx2eDu91g.

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

Not planned, no dates: the partner-file import (ruling 23); ~~sending texts through a vendor~~ (built in Phase 4, ruling 38 — the real Twilio account, number and A2P 10DLC registration are Doug's); a second-card campaign (ruling 14 waits for a measured response rate; the Stale exit is its entry point); a watched Drive folder or a posting endpoint for the outside filter (question 2); ~~a funder Campaigns tab~~ (built 10-20-26, ruling 57); Phase D of the mailing-list plan feeding email touches.

---

## 7a. Rework to the lead model — rulings 41–44 (v0.8, draft; nothing built)

**Phases 1–4 were built on the earlier model.** Rulings 41–44 (10-18-26)
rename the raw record, change its ladder and move the moment a Company or
Contact is created from "a website or email arrived" to "first contact".
Until this rework is built, §§ 1–6 describe what is built, not what is
ruled. Every campaign switch is off on production and the arc's data there
is test data (inferred from the README's State, not checked record by
record), so the rework can change stored values rather than carry two
vocabularies.

### 7a.1 The model as ruled

- **Lead** — every record entered from an outside source (ruling 41). The
  stored entity stays `CProspect`; its label changes (7a.2).
- **Lead status** (ruling 42): **Unqualified** (every lead starts here; a
  business lead with no website, or a person lead with no email, can never
  leave it), **Qualified** (could become a client, partner or funder; not
  yet contacted and has not responded), **Disqualified** (will never be a
  client, partner or funder). **Converted** is drafted as the fourth value:
  first contact happened and the Company or Contact exists (ruling 43).
- **Prospect** — a Company or Contact typed Prospect, created only at first
  contact (ruling 43). Its stages continue on `cFunnelStage`.
- **Campaigns may select Unqualified leads** for postcards and calls; a
  response bringing a website or email converts the lead straight to a
  Prospect; silence leaves it Unqualified until the Stale sweep (ruling 44).
- **Lead Source** replaces "entry door"; "door" is retired from every
  document and screen (ruling 41). The five public forms are **public
  forms**.

### 7a.2 Drafts this plan chose — each a draft with its cost, not a ruling

Written into the executive overview on 10-18-26 and open to Doug's change:

- **The prospect stages after contact: Prospect · Engaged · Opportunity**,
  then Candidate and Client read from the engagement. *Lead* stops being a
  rung (the record carries the word now) and *Warm Lead* becomes
  **Engaged**, with ruling 17's wording: asked for something and gave their
  details to get it. Cost: two option values change on Contact and Account.
- **Side exits on the lead: Duplicate** (was Already known), **Do Not
  Contact**, **Declined**, **Stale**. Disqualified is a status, not an
  exit. Cost: one value renamed, one moved.
- **A scan alone does not convert.** It is recorded on the lead (as today,
  `firstScannedAt`, `scanCount`) and moves nothing: there is no website or
  email to create a real record from. Cost: ruling 16's "a scan alone moves
  the company to Lead" no longer has a rung to move to.
- **A call marked Interested converts**, and the caller records the email
  or website on the call screen (question 15).
- **The CRM label is "Outreach Lead", the screens say "Lead"** — ruling
  35's rule that a custom entity never takes a built-in name (EspoCRM ships
  a hidden `Lead` entity), as with *Outreach Campaign*.
- **Lead Source is a label on the lead only.** The Contact's existing
  **Source** (what the person says on a form, ruling 26) is untouched; the
  two names sit on different records.

### 7a.3 What changes, component by component

| Component | Built today | After rulings 41–44 |
|---|---|---|
| `CProspect` in the CRM (handoff) | Label *Prospect*; `funnelStage`/`entryStage` Unverified · Qualified · Lead · Warm Lead · Opportunity; `entryDoor`; `sideExit` Already known · Unqualified · Do Not Contact · Declined · Stale | Label *Outreach Lead*; a status Unqualified · Qualified · Disqualified · Converted; `entryDoor` labelled *Lead Source*; exits Duplicate · Do Not Contact · Declined · Stale (question 13 decides labels or stored values) |
| `cFunnelStage` / `cEntryStage` on Contact and Account (handoff) | Unverified · Qualified · Lead · Warm Lead · Opportunity | Prospect · Engaged · Opportunity |
| `campaigns/imports.py` | Filings enter Qualified; a row with a website or email creates a Company or Contact under the API client (ruling 33) | Every row enters Unqualified; no Company or Contact is created; Already known becomes Duplicate |
| `campaigns/review.py` | Qualify / Unqualified on an Unverified record | Qualify only when the lead has a website or email (refused with the reason otherwise); Disqualify with a note |
| `campaigns/landing.py`, `forms/prospect_response/` | A scan moves the record to Lead; a website or email promotes | A scan is recorded, no stage; a response with a website or email converts: Company and/or Contact typed Prospect at stage Prospect, the lead Converted and linked |
| `campaigns/calls.py` | Interested moves to Lead; Declined exits | Interested converts (email or website captured); Declined exits |
| `campaigns/postcard.py` | Selects Qualified records (a promoted record stands for its company, v0.258.5) | Selects Unqualified and Qualified leads; a Converted lead's company keeps standing in |
| `campaigns/attribution.py` | Information request and registration write Warm Lead; a prospect id is promoted by link | They write Engaged; a lead named by the prospect id converts (status Converted, links set) |
| `campaigns/stale.py` | Unverified and Qualified records | Unqualified and Qualified leads |
| `campaigns/email.py`, `campaigns/sms.py` | Select Contacts typed Prospect at a chosen rung | The same, on the new stage names |
| `campaigns/reporting.py`, `analytics/campaigns.py` | The funnel over the five rungs; Responses shows *Converted* = a relationship began | The funnel over lead statuses then prospect stages; *Converted* now means a lead became a Prospect (question 14) |
| Screens, `CLAUDE.md`, this directory's README | "prospect record", "door", "promotion" | "lead", "Lead Source", "public form", "conversion" |

### 7a.4 The words that move

- **door** → **Lead Source** (the field) or **public form** (the five forms).
- **promotion** (ruling 21) → **conversion**: a lead becomes a Prospect.
- **conversion** in its old sense (ruling 22, a relationship beginning) needs
  a new word, because the old and new meanings would sit on the same
  screen — question 14.
- **prospect record** → **lead**; **rung** → **stage** in every document
  meant for staff (the code's `funnelStage` names stay).

### 7a.5 Order, once questions 13–16 are answered

1. **CRM handoff** for `CProspect`, Contact and Account, applied on
   crm-test first by `prds/chapter-network/crm-update-runbook.md`, with a
   one-time, dry-run-first script that moves existing values (Unverified →
   Unqualified, Lead and Warm Lead → Prospect and Engaged, Already known →
   Duplicate, Unqualified-as-exit → Disqualified, promoted → Converted).
   **crm-test done 10-19-26** (`coutreach-lead-model-crm-handoff.md`, rulings
   49 and 50): fields and labels applied and verified; the value move and
   the layouts wait for step 2's release, the removals for Doug (handoff § 6).
2. **Code**, in one release behind the existing switches: import, review,
   landing and response, calls, postcard selection, attribution, stale,
   email and SMS selection, reporting, then the screens' words.
   **Built 10-19-26, v0.265.0, committed, not pushed** — with rulings 51
   (a scan alone changes no status), 52 (a business lead converts to a
   Company and its Contact, even without a website) and 53 (a state filing
   with a website or an email enters Qualified), put to Doug at the start of
   the session. Decided in the build, each following from a ruling: a
   response converts when the response or the lead holds a website or an
   email (a response is first contact); a converted Company is matched by
   website, then by name and postal code (the import's rule); Interested on
   a Contact changes no stage; postcards select Unqualified and Qualified
   leads, Companies typed Prospect only when ticked; an import row matching a
   converted lead's Company or Contact is a Duplicate, a matched Contact named
   in the reason note only; the touch's recorded position gains Unqualified,
   Prospect and Engaged (one more CRM plan, handoff § 3a); the funnel's bands
   are Lead, Prospect, Client. The release's CRM steps on crm-test are
   `touchpos`, `leadlayouts` and `leadmove` in `scripts/prospect_crm_test.sh`.
3. **Live pass** on crm-test: the Phase 1–4 passes' steps that touch a
   stage, re-run on the new names; the Phase 4 pass resumes after it.
   **Passed 10-19-26 23:44** (Doug as Mark Marketing, Joe Mentor and signed
   out; page https://claude.ai/artifact/DPSsyZMYPhvHQRUnL696Rk rev 1.5;
   B–G read back from the CRM by Claude, H's three tables matched every
   expected number). It found three defects, fixed and live as v0.265.1–3
   (the lead's notes, *Who calls* for a marketing user, the call screen's
   own email and Cancel), and ruling 54 (marketing reads every Company).
4. **Production** at the Sunday 17:00 UTC slot; Boston with its release.
   **Deferred by Doug 10-20-26 ("B")** until lead and campaign development is
   finished, so one slot carries every CRM change. Until then production
   writes no stage and no lead behind a public-form record (`OPEN-ITEMS.md`
   #51).

**Cost of the rework:** one CRM handoff on three CRMs, about ten modules
and their tests, and a second live pass over steps already passed. The
alternative — labels only, stored values unchanged — is question 13.

---

## 7b. The Leads and Review grids at volume (10-20-26)

Doug's requirement, with ruling 56: "we need to dramatically improve the
'Leads' and 'Review' grids to handle a large number of records, and provide
better searching and qualifying." His requirements are being gathered one
question at a time (answers 1–5 below); § 7b.1 is the design drawn from them,
approved by Doug as written (10-20-26) and built as v0.267.0 the same night.

**How the two grids work today** (read from the code, 10-20-26):

- Both load every matching lead in one request. The application pages
  through the CRM 200 at a time, one call after another, and **stops
  silently at 2,000** (`campaigns/service._MAX_ROWS`). At the plan's
  100–500 filings a month the Leads grid starts dropping rows within a
  year, and nothing on the screen says so: the count reads "2000 of 2000".
- Search is in the browser, over the rows already loaded, by substring.
  Filters (status, reason, Lead Source) are server-side and reload.
- Review lists every Unqualified lead with no reason, and acts on one lead
  at a time: *Qualify* or *Disqualify* (a reason required) on the row,
  *Do Not Contact* and *Not the same company* in the lead's window. There is no
  bulk action and nothing to help decide (no website check, no
  duplicate hint beyond the import's own).
- To qualify, a lead needs a website or an email (ruling 42), and the
  Review screen cannot add either: its refusal says "Add one to the lead
  in the CRM first". Most leads reach Review precisely because they have
  neither (ruling 53 sends a filing row with one straight to Qualified).

**Doug's answers so far:**

1. **Volume: about 10,000 leads a year** (10-20-26). So the grids are built
   for tens of thousands over time: the CRM searches, sorts and counts, and
   the grid shows a page at a time.
2. **Qualifying: both bulk and a fast single lookup** (option C,
   10-20-26). Bulk *Disqualify* and *Do Not Contact* over ticked rows or a
   filter, one shared reason, for the obvious no's; then one lead at a
   time with a web search for the name and city, the website or email
   typed into the row, and *Qualify* / *Disqualify* moving to the next lead
   from the keyboard. No bulk *Qualify* (each lead needs its own website or
   email, ruling 42).
3. **Leads grid search: one box plus more filters** (option B, 10-20-26).
   The box matches the business name, the person's name, email, phone,
   website, street, city, ZIP and filing number. Filters, combinable:
   status, reason, Lead Source, import batch, ZIP or city, the date the
   lead arrived (from–to), and reached by a campaign (yes / no / this
   campaign). The count shows the total matching; the grid's search and
   filters ride the address so a search can be bookmarked. No saved
   searches.
4. **The Leads grid acts too: bulk actions and an export** (option B,
   10-20-26). Ticked rows, or everything the filter matches: *Disqualify*
   and *Do Not Contact* with one shared reason, the count named before it
   runs, every change in the action history. *Export* downloads the
   matching leads as a CSV file. No editing in the grid (Review is where a
   website or email is typed).
5. **Two reviewers at once: a guard, no claiming** (the recommendation,
   10-20-26). Every decision re-reads the lead and is refused if someone
   else decided it first, naming who; the queue skips decided leads. The
   guide says the filters split the work (by import batch or ZIP).
   Claiming is built only if duplicated lookups prove a problem.

### 7b.1 The design — approved 10-20-26 01:47, built as v0.267.0, live-passed 10-20-26 14:28

**Shared: the CRM does the work.** One server-side list call for both
grids: `GET /campaigns/api/prospects` gains `q`, the new filters, `sort`,
`dir`, `offset` and `limit` (page of 50, at most 200 — the CRM's own
limit), and answers `{prospects, total}`. The search box becomes one `or`
clause of `contains` over `businessName`, `name`, `firstName`, `lastName`,
`email`, `phone`, `website`, `mailingAddressStreet`, `mailingAddressCity`,
`mailingAddressPostalCode`, `externalReference` — no CRM change.
"Reached by a campaign" yes / no is the `touches` link's `isLinked` /
`isNotLinked` (checked live before it is relied on); "this campaign"
reads that campaign's touches and filters by their lead ids. The silent
2,000 cap goes; nothing loads every lead any more. No CRM change and no
switch: the grids are already dark behind `CAMPAIGNS_ENABLED`.

**The Leads grid.** The search box (typing waits half a second, then
asks), a filter bar (status, reason, Lead Source, import batch, ZIP or
city, arrived from–to, reached by a campaign), sortable columns, *n of
total* and Previous / Next pages. The whole state rides the address
(`#prospects?q=…&status=…`), so a search can be bookmarked and the back
button works. A tick column with *select this page* and *select all n
matching*; with any ticked, a bar offers **Disqualify…** and **Do Not
Contact…** (one shared reason; Disqualify requires it, as today).
**Export** downloads the matching leads as CSV (UTF-8, one row per lead,
the grid's columns plus address, website, email, phone, filing number),
streamed by the server page by page.

**Bulk actions — plan, then apply, the house pattern.** *Select all n
matching* sends the filter, not the ids: the server resolves it, refuses
above 2,000 ("narrow the filter"), and returns the count and ids. The
confirmation names the count and the reason ("Disqualify 12 leads?"). The
browser then applies in batches of 50 to `POST
/campaigns/api/prospects/bulk`, showing progress; each lead is re-read
and skipped, never overwritten, if it changed since (a status other than
the one the action expects, or a reason already set — the existing review
rules, ruling 50). One action-history row per batch, naming every lead.
The result says *done*, *skipped (changed meanwhile)* and *failed*.

**The Review queue.** The same server-side list, fixed to Unqualified
with no reason, oldest first, with the same search box and filters (so
two reviewers can split by batch or ZIP). Each row carries:
- **Search the web** — opens a search for the business name and city
  (or the person's name and city) in one reused browser tab;
- a **Website** box and an **Email** box, filled with what the lead holds;
- **Qualify** (saves the typed website or email, then qualifies — one
  request, refused with the ruling-42 message when both are empty),
  **Disqualify…** (reason required) and the lead's window for the rest.
Keyboard: in a row's Website or Email box, Enter is Qualify; after any
decision the row leaves the queue and the cursor lands in the next row's
Website box. The same tick column and bulk bar as the Leads grid. The
guard of answer 5 on every decision.

**Cost, named.** About two to three days: a list endpoint, a bulk
endpoint, an export route, the review action taking a website and email,
the two grids rewritten in the existing page, tests against a fake CRM,
and a live pass on crm-test with the seeded leads. The live check owed is
the `isLinked` filter and the `contains` search speed at real volume —
crm-test holds seventeen leads, so a test import of a few thousand rows
is part of the pass.

## 7c. Campaign audiences — named lists (rulings 58–68; approved 10-20-26)

**Status: approved by Doug as written (10-20-26 18:02). Built and live-passed
on crm-test: L1 10-21-26 15:36, L2 10-21-26 22:30. Production and Boston wait
for the arc's slot.** Rulings 58
to 65 decide who a campaign reaches and how its list is made. This section
turns them into the record model, the screens, the engine and the order of
work. Where this section had to choose, the choice is stated as a draft with
its cost. Three choices passed the two-part test and were § 9 questions 17 to
19; all three are answered (rulings 66, 67 and 68) and the section is
written on those answers.

**How a campaign selects its audience today** (read from the code,
10-20-26). Each kind holds one fixed rule, saved as JSON in
`COutreachCampaign.selectionRule`:

- The postcard kind (`campaigns/postcard.py`) selects leads at chosen
  statuses, or Companies typed Prospect at chosen stages, with a usable
  address, no exit, and no postcard ever sent to the business (ruling 14).
- The email kind (`campaigns/email.py`) selects Contacts typed Prospect at
  chosen stages with the marketing opt-in, plus clients whose last
  engagement closed more than N days ago (ruling 25).
- The call kind (`campaigns/calls.py`) selects leads at chosen statuses and
  Contacts typed Prospect at chosen stages, with a phone number.
- The text-message kind (`campaigns/sms.py`) selects Contacts with the
  text-message consent (ruling 9).

*Build the list* runs the rule under the organisation-wide API key and
writes one Planned `COutreachTouch` per target. No user can narrow the
audience further, and no campaign can reach partners, funders or a chosen
set of contact types.

### 7c.1 The model as ruled

- **Targets** (ruling 58): leads, clients, partners, funders and contacts,
  in any combination on one list.
- **Recipients** (rulings 59 and 60): a client, partner or funder reaches
  its primary contact, or every contact on the record when the campaign
  ticks *Include every contact on the record*. A contact target is its own
  recipient. A person reached twice receives one message. A Mentor, Member
  or Administrator is addressed at their `cbmEmail` only.
- **A list is static or dynamic** (ruling 61) and is **an ordered recipe**
  (ruling 62): *Add matching*, *Keep only matching*, *Remove matching*,
  hand ticks and a file import, each step showing what it added or
  dropped. A static list runs once and is frozen; a dynamic list runs
  again at the start of each send.
- **Step fields** (ruling 63) come from a curated list per target type,
  which administrators edit at `/setup`.
- **Lists are named records** on a *Lists* tab (ruling 64). A campaign
  picks one. A list in use is retired, never deleted. A step may add or
  remove the members of another list. Each campaign records the list and
  version it sent to.
- **A hand edit on a dynamic list is a standing entry** (ruling 65):
  *always include* or *always exclude*, applied after the recipe.
- **Send-time checks always apply** (ruling 62): consent (rulings 9 and
  19), a Do Not Contact or Disqualified exit, a dead address (ruling 15),
  one card per business for a lead (ruling 14), and "not already carded
  by this campaign" for a client, partner or funder (ruling 68).

### 7c.2 What a list member is, per target type

A list holds **records**, not people. The person or address a campaign
reaches is resolved from the record at send time, by channel. Drafts,
each with its cost:

- **A lead** is a `CProspect` record.
- **A client is a `CEngagement` record**, not the client profile or the
  Company. The engagement holds the status and close date that every client
  filter needs. Cost: a business with two engagements can be on a list
  twice; it still receives one card and one message per person, because
  recipients are de-duplicated after resolution.
- **A partner** is a `CPartnerProfile` record; **a funder** a
  `CSponsorProfile` record; **a contact** a `Contact` record.

**Who or what each channel reaches** (a page to consult, so a table):

| Target | Postcard | Email, text message, call |
|---|---|---|
| Lead | The lead's mailing address, when usable | Call: the lead's phone. Email and text: only the Contact it converted to, with consent — a lead is never emailed cold (ruling 19) |
| Client | The engagement's Company billing address, through its client profile | The engagement's primary contact (`primaryEngagementContact`), or every contact on the engagement (`engagementContacts`) when ticked |
| Partner | The partner company's billing address (`partnerCompany`) | The primary partner contact (`primaryPartnercontact`), or every contact on the partner profile (`contacts`) when ticked |
| Funder | The funder company's billing address (`sponsorCompany`) | The funder contact (`sponsorContact`), or every contact on the funder profile (`sponsorContacts`) when ticked |
| Contact | The Contact's Company billing address, else the Contact's own address (draft) | The Contact itself |

A record whose recipient cannot be resolved (no primary contact, no usable
address) is skipped and counted on the sign-off screen with its reason,
never guessed (ruling 59).

**Touches stay as they are.** A touch already carries `prospectId`,
`companyId` or `contactId`; a client, partner or funder target's touch
names the resolved Contact or Company. Which list record it came from is
kept in the application database (§ 7c.5). **No CRM change.**

### 7c.3 The step fields — the default list, verified against crm-test

Read from the crm-test CRM's live metadata on 10-20-26. Option values are
always read live. A field on a linked record (marked *via*) costs a second
CRM query per step that uses it.

**Leads (`CProspect`):** Lead status (`leadStatus`) · Lead Source
(`leadSource`) · Postal code (`mailingAddressPostalCode`) · City
(`mailingAddressCity`) · Import batch (`importBatch`) · Arrived
(`createdAt`) · Qualified on (`qualifiedAt`) · Exit (`sideExit`).
Industry (`industry`, new — ruling 66; absent until its CRM handoff is
applied, so the field is feature-detected and offered only where it
exists).

**Clients (`CEngagement`):** Engagement status (`engagementStatus`) · Close
date (`closeDate`) · Close reason (`closeReason`) · Start date
(`engagementStartDate`) · Mentoring focus areas (`mentoringFocusAreas`) ·
Referring partner (`referringPartner`) · Outreach campaign
(`outreachCampaign`) · *via the client profile:* Industry sector
(`industrySector`), Annual revenue range (`annualRevenueRange`), Number of
employees (`numberOfEmployees`), Home-based (`isHomeBased`) · *via the
Company:* Postal code (`billingAddressPostalCode`) · *computed:* days since
the client's last engagement closed (ruling 25's existing rule, kept
because "all engagements closed" cannot be written as one field condition).

**Partners (`CPartnerProfile`):** Partnership status (`partnershipStatus`)
· Partnership type (`partnershipType`) · Partner manager
(`partnerManager`) · Partnership start date (`partnershipStartDate`) · Last
contacted (`lastContacted`) · *via the Company:* Industry sector
(`cIndustrySector`), Postal code (`billingAddressPostalCode`).

**Funders (`CSponsorProfile`):** Funder manager (`cBMSponsorManager`) · Last
contribution (`lastContribution`) · Total contribution
(`totalContribution`) · Last contacted (`lastContacted`) · *via the
Company:* Sponsorship level (`cSponsorshipLevel`), Sponsorship renewal date
(`cSponsorshipRenewalDate`), Postal code (`billingAddressPostalCode`).
Funder status (new — ruling 67; options drafted Prospective · Active ·
Lapsed · Ended; feature-detected, offered only where it exists; empty
means "not set").

**Contacts (`Contact`):** Contact type (`cContactType`) · Funnel stage
(`cFunnelStage`) · Marketing opt-in (`cMarketingOptIn`) · Text-message
opt-in (`cSmsOptIn`) · How did you hear (`cHowDidYouHear`) · Postal code
(`addressPostalCode`) · Created (`createdAt`). **An *Add matching* step on
contacts must name at least one contact type** (ruling 60: nothing ticked
by default); "No type" is `cContactType` empty.

**The `/setup` setting.** `CAMPAIGN_LIST_FIELDS`, one entry per target type
listing its fields (and the *via* hop for a linked one). Editing it is
validated against live CRM metadata — a field the CRM lacks, or of a type
no operator serves, is refused with the reason — and recorded in the
settings history. Not boot-read: a change applies within the settings
refresh. A field removed from the CRM or the setting stays on any recipe
that used it, flagged, and the step refuses to run until it is edited
(ruling 63).

### 7c.4 The engine

**Running a recipe.** Under the organisation-wide API key, like every
selection today. Each step is one CRM `where` per target type (plus one per
*via* hop), paged at 200. A working set of keys (`lead:<id>`,
`client:<id>`, `partner:<id>`, `funder:<id>`, `contact:<id>`) is carried
through the steps in order:

- *Add matching* — the union.
- *Keep only matching* — the intersection, for the step's target type;
  members of other types pass through untouched (draft: the screen says
  so on the step).
- *Remove matching* — the difference.
- *Add* / *Remove members of list…* — the same three, reading the other
  list's current membership. A list may not reach itself through another
  list; the save refuses a cycle.
- *Import* — a file of CRM ids or email addresses, matched to existing
  records; an unmatched row is reported, **never created** (creating leads
  is the Imports tab's job).
- Standing entries (dynamic) or hand ticks (static) apply last.

Each step records its before-and-after count; the screen shows them beside
the step. **A step whose result exceeds 20,000 records is refused** with
"narrow the step" (draft; the Leads grid's bulk cap is 2,000, and ruling
56's volume is about 10,000 leads a year).

**When a list runs.** A static list runs when staff press *Run* and is
then frozen; *Run again* replaces the frozen membership, keeps hand ticks
made since as standing differences, and asks for confirmation first. A
dynamic list runs at the start of each send: in this application, a
campaign's *Build the list* (postcard, email push, call list, text
campaign each send once). So "dynamic" matters when one list feeds a
sequence of campaigns — the March postcard and the April call read the
same recipe a month apart and see the list as it is that day.

**The campaign's send** (§ 3.1 step 2, changed). *Build the list* reads the
campaign's list (frozen membership, or the recipe run now), resolves each
member to its recipient by channel (§ 7c.2), applies the send-time checks,
de-duplicates recipients, and writes the Planned touches as today. The
sign-off screen shows: members on the list, recipients resolved, and each
skip reason with its count. The kinds' fixed rules become the kinds'
send-time checks, which they already partly are (consent, usable address,
phone held, one card per business).

**Existing campaigns.** A campaign with a `selectionRule` and no list keeps
working exactly as now. With `CAMPAIGN_LISTS` on, a new campaign picks a
list; the kind's rule screen is no longer offered. Draft, chosen because
every existing campaign is crm-test test data or already sent.

**Who sees what.** The Lists tab is behind the campaigns gate
(`CAMPAIGNS_ALLOWED_TEAMS`, the Marketing Admin Team) and
`CAMPAIGN_LISTS`. The member preview shows each record's name, its target
type, and the values of the curated fields the recipe used — nothing else
— so the Marketing Admin Role sees no engagement field beyond the reviewed
list (the boundary ruling 63 was chosen to keep). Every list create, edit,
run, freeze, retire and standing-entry change goes through `record_action`.

### 7c.5 Storage — the application database (migration 0032)

Ruling 64 puts lists in the application database, like campaign links
(ruling 31). Six tables:

- `audience_list` — id, name, notes, kind (static / dynamic), status
  (active / retired), current version, created and changed by and when.
- `audience_list_step` — list id, position, action, target type,
  conditions (JSON), source list id (for a list step), import reference.
- `audience_list_member` — a static list's frozen membership: list id,
  target key, the step that added it, added by and when for a hand tick.
- `audience_list_entry` — a dynamic list's standing entries: list id,
  target key, include / exclude, note, made by and when (ruling 65).
- `audience_list_version` — the recipe as JSON and the member count at each
  saved change, so a campaign's "version it sent to" can be shown later.
- `campaign_audience` — campaign id, list id, list version, the *Include
  every contact* tick, and per member the resolved recipient or the skip
  reason, written at *Build the list*.

**The training sandbox empties these tables every night** (the app's own
Postgres is restored at 05:00 UTC), so lists made on crm-test during a
pass are gone by morning, and demo lists need a seeder stage and a
re-baseline, as the campaign links did (`campaigns/sandbox_demo.py`).

### 7c.6 The screens

- **Campaign Management → Lists tab** (ruling 56's top bar gains *Lists*):
  a grid of lists — name, kind, members, used by N campaigns, last run,
  status — with *+ New list*, search and *Show retired*.
- **A list's page:** the header (name, kind switch static / dynamic, *Run*
  or *Run again*, *Retire*); the **Recipe** panel, one row per step with
  its counts, drag to reorder, *+ Add step*; the **Standing entries**
  panel (dynamic) with who, when and the note, each removable; the
  **Members** grid, paged at 50 from the application database, with the
  tick column for hand edits and the used-fields columns; *Used by* naming
  each campaign and the version it sent to.
- **A step's editor:** action, target type, then conditions — field (from
  the curated list), operator (by field type, ruling 63), value (options
  read live; dates through `CBMDateTime`). *Preview* shows the step's
  count before it is saved.
- **The campaign form:** a *List* picker in place of the rule screen, and
  the *Include every contact on the record* tick (ruling 59), shown when
  the list holds clients, partners or funders.
- **`/setup` → Campaigns:** the `CAMPAIGN_LIST_FIELDS` editor, one panel
  per target type.

Every convention in § 10 applies.

### 7c.7 Order and cost

Two steps, each behind `CAMPAIGN_LISTS` (off; read per request), each with
a live pass on crm-test as a real non-admin Marketing Admin user.

1. **L1 — lists of leads and contacts. Built as v0.270.0 (10-20-26 18:20), not
   pushed; live-passed on crm-test 10-21-26 15:36 (`OPEN-ITEMS.md` #51).** Two simplifications:
   steps reorder with up/down buttons, not drag; the field list is a text
   setting at `/setup`, not a panel per type. The tables, the engine with *Add*,
   *Keep only*, *Remove*, static and dynamic, hand ticks and standing
   entries, the Lists tab and list page, the campaign's *List* picker for
   all four sending kinds, the `/setup` field list for those two types,
   and the sign-off screen's skip counts. About four days.
2. **L2 — clients, partners and funders, and lists of lists. Built as
   v0.271.0 (10-21-26 16:01); live-passed on crm-test 10-21-26 22:30 (`OPEN-ITEMS.md` #51).** The three
   target types with their *via* fields, recipient resolution and *Include
   every contact*, the list-member steps with the cycle check, and the
   import step. About three days.

**Cost, named.** About a week and a half, the largest piece of this arc
since Phase 1. The live pass is harder than usual because the sandbox
empties the lists nightly and crm-test holds few partners, funders and
closed engagements, so the pass needs seeded records first. Two CRM
changes, each its own handoff: the lead's industry field (ruling 66),
applied before L1's live pass, and the funder status (ruling 67), applied
before L2's, with its Details-tab field and grid column part of L2; the Review queue's industry picker and the import's
industry column are part of L1.

## 7d. The lead identifier in every link (rulings 71–73; drafted 10-22-26 for approval)

**Status: APPROVED (10-22-26 01:35) — question 20 answered A (ruling 74), the prefill table in § 7d.4 confirmed as written (ruling 75). The CRM handoff of § 7d.5 is written (10-22-26 01:42, `lead-code-crm-handoff.md`, plan fingerprint `bec909277859`, dry run clean on crm-test). Applied on crm-test 10-22-26 12:45–12:48 and read back. **D1 built 10-22-26 13:00 (v0.276.0, committed, not pushed)**; its live pass on crm-test is owed, then D2.** Rulings 71 to 73
(10-22-26) say that every link delivered to a known person carries that
person's lead identifier after the campaign link, that the identifier
belongs to the person for life, and that each form decides for itself what
to do with the lead it was opened for while every form attributes to it.
This section turns the three rulings into the storage, the vendor step, the
resolver, the per-form prefill table and the order of work. Where it had to
choose, the choice is a draft with its cost. One choice passed the two-part
test and is § 9 question 20.

**How a person is identified in a link today** (read from the code,
10-22-26). A campaign link is `/c/{link}` and names the campaign only.
The postcard alone identifies a person: its card carries
`/c/{link}/{scanToken}`, a twelve-character code minted per **touch** at
send time (`campaigns/tokens.py`), resolved by the landing page to the
touch, the lead and the campaign. The five public forms and the event
registration carry `campaign_id`, `campaign_link` and `prospect_id` as
hidden fields; `prospect_id` is the lead's **CRM id**, handed over by the
landing page, and the forms' prefill after that handoff is the name-only
`GET /api/campaigns/public/prospect/{id}` lookup, which returns the business
name and mailing address and nothing else (ruling 16). An email notice's
links are the campaign links pasted by staff; a text's wording is sent as
typed, so any link in it is the same for every recipient; a call script
shows no link. Nothing identifies the recipient of an email or a text.

### 7d.1 The code

**One code per person, for life (ruling 72).** Twelve characters from the
same alphabet as the scan token (no 0/O, 1/l/I, so a person can read it
back from a card or a text), minted from `secrets` the first time a
campaign needs it or when staff press *New code*. Never a CRM id: a link
carries no record id in the clear, which is the rule the card already
keeps.

**Where it lives — a field on the lead and on the contact (ruling 74).**
`CProspect.leadCode` (varchar 16, indexed) and `Contact.cLeadCode` (varchar
16, indexed), both app-written and never Read-only in the CRM (ruling 40's
rule: a field rule keeps staff off them). A person is one of three things,
and the code follows them:

- **An unpromoted lead** holds the code on the lead record.
- **A lead promoted to a Contact** keeps one code: promotion copies
  `leadCode` to the contact's `cLeadCode` (never mints a second), and the
  two stay equal.
- **A Contact with no lead** (every contact imported or created before the
  lead model, and any contact a campaign reaches without a lead behind it)
  holds the code on the contact alone.

The resolver looks the code up on Contact first, then on the lead. The
alternative is an application table `lead_code` (code, lead id, contact id,
company id), which needs no CRM change but is emptied by the sandbox reset
every night and would make every demo link on crm-test dead by morning
until the seeder re-minted it; the code must survive, so it lives in the
CRM. **Cost:** two fields in one handoff on every CRM, with the two
conformance cells.

**The postcard's scan token becomes the lead code.** The card's address
keeps its shape, `/c/{link}/{code}`, but the second part is the lead's
code, not a per-touch token: at send time the postcard run mints the lead's
code if it has none and writes it to the touch's `scanToken` as well, so
the landing page and the scan counters (`firstScannedAt`, `scanCount`,
ruling 51) work unchanged. One card per business (ruling 14) means one
touch per lead anyway, so nothing is lost. The twelve-character
`new_scan_token` stays as the minting function, renamed.

**New code.** A button on the lead's record in Campaign Management and on
the contact's record page in the directory (`/directory/contacts/record/{id}`),
Marketing Admin Team, action-logged with the old code's last four
characters. Minting a new code invalidates the old one at once: a link
holding it resolves to the campaign only, exactly as an unknown code does,
and the form opens empty. The vendor's custom field is rewritten by the
next push that includes the person; until then a notice sent in between
carries the old code, so the button's confirmation says so.

### 7d.2 Delivering the code, per kind

- **Email.** One custom field in the vendor account, **`cbm_lead_code`**,
  created once by the application through the vendor's custom-fields
  endpoint when the mailing connection is made (and checked on every push;
  the Readiness line says *custom field missing* if an administrator
  deleted it). Both pushes — the nightly standing push in
  `core/mailing_sync.py` and the campaign push in `campaigns/email.py` —
  write it as the `cf:cbm_lead_code` column of the JSON import, minting the
  code for any contact that has none. The campaign's Links tab shows each
  link twice: the plain address, and the address **to paste into a
  notice**, `{APP_BASE_URL}/c/{link}/[[custom.cbm_lead_code]]`, with a Copy
  button, because the merge tag is the vendor's and nobody should type it.
  *Inferred, to verify on the first live run:* the import column key must
  match the custom field's stored `name` (lowercase, underscores), not its
  label — a vendor forum answer, not a documented rule; and the merge tag's
  exact spelling in a link. The vendor does not merge the tag in a preview
  or a test send: the check is a real send to one address.
- **Text.** The campaign's wording gains one placeholder, **`{link}`**, that
  the send replaces per recipient with the campaign's first link followed
  by the recipient's code (minted at send time). `check_message` refuses
  wording with no `{link}` the way it refuses wording with no STOP, so a
  text never goes out with the same address for everyone. Wording that
  carries a pasted campaign address as well is left alone.
- **Call.** The caller's page shows the person's link, campaign link plus
  code, with a Copy button, so a caller can read it out or send it in a
  follow-up email. Minted when the call list is built.
- **Postcard.** As § 7d.1: the card's code is the lead's.
- **Social media.** The campaign link only (ruling 71): there is no
  recipient.

### 7d.3 Resolving the code

`GET /c/{link}/{code}` already exists for cards and today always opens the
landing page. It becomes the one resolver for every kind:

1. Shape-check both parts before any lookup (`looks_like_token`), count the
   visit on the link as today.
2. Look the code up on Contact, then on the lead, under the organisation-wide
   API key. Not found: redirect to the link's destination with the campaign
   and link only — the visitor sees the page they were promised, with no
   lead on it, in the same words whatever the reason.
3. Found: find the person's touch on this campaign (campaign + contact, or
   campaign + lead) and record the click on it: outcome **Clicked** (a new
   `outcome` value beside Scanned), `firstClickedAt` once, `clickCount`
   every time. A scan or a click alone changes no status (ruling 51). No
   touch — the person forwarded the link, or clicked after staff rebuilt the
   list — records nothing on a touch and still carries the lead to the
   form.
4. Redirect (302, `no-store`) to the link's destination with
   `?campaign=<id>&link=<token>&lead=<code>`. The landing page destination
   keeps `/p/{code}` as today. **The code rides, never the lead's CRM id**:
   `prospect_id` in the forms' hidden fields becomes `lead_code` (the schema
   field stays optional and bounded; capture keeps both names for one
   release so a held submission from before the change still delivers).

### 7d.4 What each form does with the lead — ruling 73

**One public lookup, per form.** `GET /api/campaigns/public/lead/{code}?form=<slug>`
replaces the prospect lookup. It answers that form's prefill set and
nothing else, from a **server-side allowlist per form** (`PREFILL_FIELDS`
in `campaigns/config.py`): whatever one form may show, no caller with the
code can read more than the widest form's set, and the allowlist is the
place that widening is reviewed. A code that resolves to nothing is a 404
in the same words as a malformed one. The values come from the contact
when the person has one, else from the lead; the company's from the
promoted company, else the lead's business half.

**The per-form table (approved as written, ruling 75; the registration
row is Doug's example):**

| Form | Prefills | The person sees | At delivery |
|---|---|---|---|
| **Event registration** (event page form and the calendar's sign-up window) | Everything the form asks: first and last name, email, phone, company, the business-stage question | The form filled in, a line *"Not you? Clear the form"*, and the **Register** button — one press | Matches the contact by email as today; writes the campaign and the lead; a new contact is Converted from the lead (ruling 48) |
| **Information request** | Name, email, phone, company | Filled in, same *Not you?* line | As today plus the lead |
| **Request a mentor** (client intake) | Name, email, phone; company name, website and address from the promoted company or the lead | Step 1 and the company step filled in; the rest of the wizard is theirs | As today (§ 5) plus the lead; the promoted company is used by id before any name match |
| **Volunteer application** | Name, email, phone | Filled in | As today plus the lead |
| **Partner application** | Name, email, phone; company name and website | Filled in | As today plus the lead |
| **Funder application** | Name, email, phone; company name and website | Filled in | As today plus the lead |
| **Postcard landing page** | Business name and mailing address only (ruling 16 still governs this page) | As today | As today |

Every form keeps the courtesy banner it has (*"You arrived through
<campaign>"*) and shows the person's first name in it when the lead
resolved. **Nothing prefilled is trusted at delivery**: the submission is
validated exactly as a typed one, the contact is matched by the email
submitted, and the lead code is validated-or-dropped like the campaign id.
A person who clears the form and types someone else's details creates that
someone as today, attributed to the campaign and to the lead that opened
the form — the attribution is to the link's holder, which is what ruling
73 asks.

**Attribution at delivery.** `attribution.resolve` reads `lead_code`,
resolves it to the lead (and contact) under the API key, and the existing
steps run: `record_lead` links the lead to what was created, the campaign
id is written by ruling 27, the touch moves to **Responded** with the
created record linked (postcard's existing path, now for every kind). A
submission with a code and no campaign (a link retired and re-minted, or a
code typed by hand) still attributes to the lead.

### 7d.5 Storage and CRM changes

- **CRM handoff** (one plan file, `scripts/plans/lead-code.json`):
  `CProspect.leadCode` varchar 16; `Contact.cLeadCode` varchar 16;
  `COutreachTouch.outcome` offers `Clicked` (already present, built with
  the entity); `COutreachTouch` gains `firstClickedAt` (datetime) and
  `clickCount` (int). **No index** (written 10-22-26): *index* is not a
  Field Manager parameter for a varchar, the scan token's finding; it is a
  droplet metadata edit, made only if a production click proves slow. The
  two conformance cells are field rules on the Marketing Admin Role (read
  yes, edit no), so every write of either code field goes under the
  org-wide key; ruling 77 keeps them on that role only and both fields off
  every layout. Handoff: `lead-code-crm-handoff.md`. Field ACL: the
  Marketing Admin Role already edits leads and touches; the intake API
  client needs Contact edit for `cLeadCode` (it has Contact edit). Two
  conformance cells.
- **Application database:** none. The vendor custom field's id is read by
  name on each push, not stored.
- **Settings:** none new. The vendor field name is a constant; a chapter
  that must rename it edits the constant (named in § 8).

### 7d.6 Order and cost

Behind no new switch: the resolver and the lookups are inert until a code
exists, and a code exists only when a campaign mints one or staff press
*New code*. Each step has a live pass on crm-test as a real non-admin.

1. **D1 — the code and the resolver.** *Built 10-22-26, v0.276.0.* Four
   choices made in the build, each within the rulings: (a) **ruling 31 is
   kept** — the resolve does not look the code up before redirecting; it
   carries the code on, the click is written after the 302, and the form's
   lookup is what finds an unknown code (the visitor sees the empty form
   step 2 asks for); (b) **there is no touch status "Responded"** — § 7d.4's
   "the touch moves to Responded" names nothing that exists; Responded is
   ruling 46's count of submissions carrying the campaign, unchanged, and
   delivery writes nothing on a touch; (c) the registration row of
   `PREFILL_FIELDS` is what the form asks (name, email, phone, ZIP) — the
   table's company and business-stage question are not on that form; (d)
   the sandbox's demo codes are written nightly by the worker's demo-link
   restore (the card token is the lead's code), so no baseline recapture is
   needed. The forms fill only the company half from the lookup until D2
   brings each form's *Not you?* line. The CRM handoff applied on crm-test;
   minting; the postcard's code becomes the lead's; `/c/{link}/{code}` for
   every kind with the click recorded; the forms' hidden field renamed;
   the per-form lookup with the allowlist; attribution reads the code.
   About two days.
2. **D2 — the forms prefill.** The seven rows of the table, each form's
   own screen; the *Not you?* line; the registration's one-press path on
   the event page and in the calendar window. About two days.
3. **D3 — delivery per kind.** The vendor custom field created and written
   by both pushes; the paste-into-a-notice address on the Links tab; the
   text's `{link}` placeholder; the caller's link; *New code* on the lead
   and the contact. The live pass includes one real send from the trial
   account to Doug's own address, because the vendor merges the tag only
   in a real send. About two days.

**Cost, named.** About a week. One CRM handoff on every CRM before D1's
pass; production's and Boston's apply ride the deferred production slot
(the lead model is not there yet, and the code field joins it). The
vendor half rests on two inferred facts (§ 7d.2) that only the first live
send can confirm. And the standing cost ruling 73 accepted: a forwarded
notice carries the recipient's code, and a form that prefills everything
shows that recipient's details to whoever holds the forward; *New code* is
the remedy after the fact, not a prevention.

## 7e. The Marketing Management redesign (rulings 79–116; drafted 10-23-26 for approval)

Doug opened the redesign on 10-22-26 at 22:13: "We need to dramatically
improve the entire Marketing Management UI." Over the next three hours he
ruled on every tab, one question at a time: imports (79–88), lists,
Constant Contact and event promotion (89–98), campaigns (99–102), leads and
review (103–113), and calls (114–116). This section is the build that
follows from those rulings. **Nothing in it is built.** Where the rulings
left a mechanism open, the plan chooses one and marks it **Draft**, with its
cost, in § 7e.12. A Draft is not a ruling until Doug approves it.

The facts below were read from the code on 10-23-26, after commit
`ea15328` plus the ruling commits.

### 7e.1 What the redesign touches

Nearly every part of the campaigns package changes:

- `campaigns/frontend/`: all three pages become one.
- `campaigns/audience.py` and `lists_router.py`: the list engine.
- `campaigns/email.py` and `core/mailing_sync.py`: the Constant Contact
  push.
- `campaigns/imports.py`: templates, Excel and undo.
- `campaigns/review.py`, `leads.py` and `calls.py`: the ladder and personal
  outreach.
- `comms/`: the email sync recognises leads.
- `enrichment/`: people found by research land on the lead.
- `events/`: Promote this event and the roll-up.

The CRM gains fields on `CProspect` and one link on `CConversation`
(§ 7e.11). The application database gains three tables and changes one
(§ 7e.11). About 150 existing tests pin behaviour that the rulings change;
each step below names its files.

### 7e.2 One page, six tabs — rulings 89, 112, 114 (built as v0.279.0, 10-23-26; live pass owed)

**Today.** `index.html` and `app.js` (one 1,593-line IIFE) hold Leads,
Campaigns, Review and Imports. `lists.html` / `lists.js` (641 lines) and
`calls.html` / `calls.js` (174 lines) are separate pages, opened in named
browser tabs from the top bar. No script sets a `window.*` global, so the
three scripts cannot collide by name. **They collide by DOM id**: index and
lists share eleven ids (`modal*`, `notice`, `offPanel`, `offReason`,
`runNote`, `userCorner`, `whoName`), and calls shares five of them.

**The build.**

- `index.html` gains a Lists panel and a Calls panel, and the top bar
  becomes six section buttons.
- `lists.js` and `calls.js` stay separate files, loaded by `index.html`
  after `app.js`. Each panel's ids are prefixed (`ls_`, `cl_`), so the
  modal, notice and user corner exist once, owned by `app.js`.
- A small shared object, `window.CBMMarketing`, carries what the three
  scripts share: `api`, `notice`, the open modal, the session. Each script
  registers `onShow` / `onLeave` with `showSection`. Lists' `onLeave` is
  the unsaved-changes warning that `beforeunload` gives today.
- `lists.html` and `calls.html` become redirects to `/campaigns/#lists` and
  `/campaigns/#calls`, so old bookmarks and the record page's links keep
  working. Their copies of the top bar go away.

**Callers from other teams (ruling 114).** Today `/session` answers 403 to
anyone outside `CAMPAIGNS_ALLOWED_TEAMS`, and a test asserts it. The build
changes that answer. `/session` returns `callerOnly: true` (plus `callsOn`)
to a signed-in user who is not on the team, and the page then shows only
the Calls tab. **Every other endpoint keeps its team gate unchanged**, so a
caller who forges a tab switch gets the same 403s as today. The calls
endpoints keep their per-campaign check (`calls.may_call`). The portal adds
a **Campaign calls** tile (`portal/router.py`) for a user who may call on
at least one running call campaign and is not on the team. The tile
re-uses `calls.call_list`'s split, read under the API client.

**Ruling 112.** Every hint that cites a ruling is rewritten in plain words.
A guard test fails on `ruling \d` in any served campaigns file.

**Tests that change.** `test_campaigns_phase3.py:346-355` (the 403 becomes
`callerOnly`) and `:565-566` (reads `calls.js` strings). Also
`test_campaigns.py:248-258` (the tile), `test_campaign_attribution.py:577-586`
(record-page strings) and `test_shared_branding.py` (each page still served).

### 7e.3 The qualification ladder — rulings 104–106, 111

**The field.** `CProspect.leadStatus` keeps its four stored values
(Unqualified, Qualified, Disqualified, Converted): every filter in
`calls.py`, `postcard.py`, `stale.py`, `audience.py`, `reporting.py` and
`leads.py` reads them, and they stay true. A new enum field,
**`qualificationLevel`** (*Level*), holds the level inside Qualified:
Identified, Contactable, Referred. It is empty unless `leadStatus` is
Qualified. The grid's *Level* column shows Unqualified or Disqualified from
`leadStatus`, and the level otherwise. The staff see one ladder (ruling 105);
the CRM stores two fields, because the second one is only meaningful inside
the first.

**The rule** (one function, `campaigns/ladder.py`):

- `facts(lead)`: named person (`firstName` or `lastName`), phone, email,
  referrer.
- `placed(facts)`: Referred when there is a referrer and a phone or an
  email; else Contactable when there is a named person and a phone or an
  email; else Identified.
- `next_level(current, manual, facts, facts_at_manual)` applies ruling 106:
  - The level never moves backwards.
  - With no manual setting, it is `max(current, placed(facts))`.
  - With a manual setting, it moves forward only when a fact absent from
    `facts_at_manual` is now present, and only as far as `placed` allows.

**Where it runs.** There is no single place a lead is saved: staff also edit
leads in the CRM's own screens. So placement runs in two places.

- **Inline, after every application write to a lead:** review, enrichment
  `land` and `decide`, the prospect-response orchestrator, call outcomes,
  the import and the lead editor (§ 7e.6).
- **A sweep in the worker** over leads modified since its last pass. This
  catches edits made in the CRM's screens, every
  `LEAD_LEVEL_SWEEP_SECONDS` (default 900).

`facts_at_manual` lives in a new application table, `lead_level_manual`
(lead id, level, facts snapshot, set by, set at). The CRM records only the
level and two fields saying who set it by hand and when. **Draft 1** (§ 7e.12).

**The referrer.** A new link, `CProspect.referredByPartner` → `CPartnerProfile`
(many-to-one), plus a text field `referredByName` for a referrer who is not
a partner. Either one counts as a referrer.

**Imports (ruling 111).** A template's *Enters at* setting (Unqualified or
Qualified) replaces `entry_status`'s fixed rule. A Qualified row is then
placed by `placed()`, with the template's partner as referrer. Ruling 53's
state-filing rule becomes the default template setting for the State filing
source: Qualified when the row has a website or an email.

**Tests that change.** `test_campaigns_phase3.py:54,87,101`,
`test_campaign_leads.py:98,204,217,227`, `test_campaigns.py:604`,
`test_sandbox_demo.py:219`. The sandbox seeder gains levels on its demo
leads.

### 7e.4 The Leads tab and the lead's page — rulings 104, 108, 113

The grid keeps § 7b's server-side paging, search and count.

- **Counts across the top**, one CRM `total` request each, run in
  parallel: Unqualified, Identified, Contactable, Referred, *Replied, not
  yet converted* and Disqualified. Each count is a filter.
- **The filter row** shrinks to search, Assigned to (with *Mine*), Lead
  Source and batch, and place. *More filters* opens the rest.
- **The Reach column** is computed from the row: postcard lights with a
  live address, phone with a phone number, email with an email address.
  Email is dim unless the level is Contactable or Referred, because only
  those levels may be emailed personally (ruling 107).
- **Bulk actions** gain *Assign to…*.
- **The Import button leaves** (ruling 88).

The lead's window becomes a page, `/campaigns/lead/{id}`, served like
`/campaigns/record/{id}`, with the single-tab record guard.

- **Header:** name, level, assignee, *How we can reach them*, and the
  actions Email, Log a call, Set level, Assign and Convert.
- ***What we know*:** Business, Person and Fit, with empty fields shown as
  gaps. Each gap is an inline input written as the user, and every write
  runs placement.
- ***Where it came from*:** Lead Source, batch and referrer.
- ***Activity*:** one timeline built from touches (postcards, calls, texts),
  personal emails and replies (`CConversation`, § 7e.5), level and status
  changes (the action log) and enrichment findings.

**`CProspect.assignedUser`.** The entity is checked for the field and
whether it is customizable before the handoff is written (the
`espo-crm-changes` skill). The picker lists active members of
`CAMPAIGNS_ALLOWED_TEAMS`. Assignment is written as the user, so the
Marketing Admin Role needs Assignment Permission that allows it. The
handoff checks this.

### 7e.5 Personal outreach — rulings 107–109

**Sending (ruling 107).** The record compose already exists:
`POST /records/{id}/messages` in `sessions/router.py` calls
`comms.service.send_message`, which can take a pre-built `RecordRef`. The
lead page builds `RecordRef(entity="CProspect", addresses={lead.email})`
and opens the shared compose. The guardrails are enforced on the server,
not in the screen:

- one recipient;
- the lead is Contactable or Referred, with no `sideExit` and no Do Not
  Contact;
- the body carries the opt-out line, which the server appends when it is
  missing: "If you'd rather not hear from us, reply and say so and we won't
  write again." The wording is a Draft (Draft 6).
- the message is logged.

The sender is the user's own `cbmEmail`. **Today that is read from the
user's `CMentorProfile`, and a marketing staff member may have none.** The
compose refuses with a message naming what is missing (Draft 4).

**Log a call.** Today a call is a `COutreachTouch` on a running call
campaign. Personal outreach has no campaign. **Draft 3**: the touch's
campaign link becomes optional, and the touch carries channel *Personal
call* or *Personal email*. Calls and personal touches then share one record
and one outcome vocabulary (ruling 115). The outcomes are:

- **Interested** runs `conversion.convert_lead`, unchanged, under the API
  client as `calls._convert_on_interest` does.
- **Not interested** sets `sideExit` Declined, with a reason.
- **No reply yet** writes the touch only.

**Replies (ruling 109).** The sync matches mail to records through scopes
built from mentor profiles' linked Contacts (`comms/crm.build_scopes`), and
attaches conversations through `PARENT_LINKS` (CEngagement, CPartnerProfile,
CSponsorProfile). The build:

- adds a `CConversation` ↔ `CProspect` link in the CRM (the handoff) and
  `CProspect` to `PARENT_LINKS`;
- adds a scope source of **assigned leads**: for each lead with an
  `assignedUser` and an email, the scope belongs to that user's mailbox;
- adds `CProspect` to `scopes.WATCHED_ENTITIES`, so a new assignment
  rebuilds the scopes;
- updates every loop over `PARENT_LINKS` (`comms/service.py:643`,
  `comms/attachments.py:143`, `myemail/service.py:147`);
- grants the Marketing Admin Role `CConversation` read on its own records.

A reply sets a new boolean on the lead, `CProspect.replied` (*Replied*),
which conversion clears. The *Replied, not yet converted* count reads it.
**Only assigned leads are matched**: matching every lead's address against
every mailbox would attach a stranger's reply to whichever lead shared the
address (Draft 2).

**Tests.** `test_comms_scopes.py` and `test_comms_sync.py` gain the lead
source. A new `test_campaign_outreach.py` covers the guardrails, the opt-out
line, the refusal without a `cbmEmail`, and the three outcomes.

### 7e.6 Review as the research queue — ruling 110

`LeadQuery.review_queue` gains a mode:

- ***Judge Unqualified leads***: today's queue, unchanged.
- ***Find contacts for Identified leads***: Qualified leads at Identified,
  with no exit, oldest first. Each row has inline contact name, phone and
  email. Enter writes them, runs placement, and moves to the next lead. A
  lead that moved to Contactable leaves the queue.

**The AI research button** fills the row with the latest Proposed findings,
for the reviewer to accept with Enter. `enrichment.runs.decide` today
refuses to accept a *Person* finding on a lead ("ruling 43"). Ruling 43
forbids creating a **Contact** before first contact. It does not forbid
writing a person's name into the lead's own `firstName` / `lastName` /
`email` / `phone`. **Draft 5**: accepting a Person finding fills those lead
fields where they are empty, and creates no Contact.

**Tests.** `test_enrichment_research.py` (decide), `test_campaign_leads.py`
(the queue).

### 7e.7 The import tool — rulings 79–88

**Today.** `campaigns/imports.py` reads CSV only, with fixed column names.
It plans (stored as a batch in the ledger) and applies in parts of 100,
resumable. A repeat row is matched by `row_hash` (the Lead Source plus the
external reference, else the business name and ZIP) and skipped. A row
matching a Company or Contact creates a lead closed as Duplicate.

**The build.**

- **Templates.** A new table, `import_template`: id, name, Lead Source,
  list source, *Qualified by*, *Enters at* (ruling 111), the referrer
  partner id, `mapping` JSONB and `header_signature`, plus the audit
  columns. Mapping entries are column → field, or one of four fixes:
  `split_name`, `join`, `fixed`, `ignore` (ruling 82). Shared by the team
  (ruling 79). Every change is action-logged.
- **Excel.** `openpyxl` (a new dependency) reads `.xlsx`. A workbook with
  several sheets asks for the sheet (ruling 80). `.xls` is refused with
  "save it as .xlsx". The file size limit stays 5 MB and 5,000 rows.
- **Recognition (ruling 81).** Each template is scored by header overlap.
  Likely renames come from a normalised-name similarity and are shown as
  suggestions, never applied silently. The screen lists new, missing and
  renamed columns. A required field (business name, the four address parts)
  left unmapped stops the import. *Save as an update to the template*
  writes a new `header_signature`.
- **Preview = rehearsal (ruling 83).** `plan_import` already checks every
  row against the CRM. It gains:
  - the fourth outcome, *fills an existing lead* (ruling 84), carrying the
    fields it would fill;
  - the level each new row lands at;
  - per-row *exclude*, stored on the planned batch.

  The screen is the counts-as-filters strip plus the walk-through (the
  spreadsheet values beside the lead fields). The plan step already takes
  minutes for large files, so it gets a progress line. Today the modal
  waits on one request; the plan request becomes a background job the page
  polls (Draft 7).
- **Repeat rows fill empty fields (ruling 84).** `known_row` stops meaning
  *skip*. The ledger maps `row_hash` → lead id, and apply writes only the
  lead's empty fields, as the user, then runs placement. A row matching a
  Company or Contact keeps today's Duplicate lead (ruling 85).
- **After writing.** *Show these leads* opens the Leads tab filtered to the
  batch (ruling 86).
- **Undo (ruling 87).** *Undo this import* on the history reads the
  batch's created lead ids from the ledger. A lead is *touched* when it has:
  - any touch;
  - membership of any list or campaign;
  - a status or level change after the batch;
  - a `sideExit`;
  - a conversation.

  An untouched lead is deleted, as the user, with `record_action`. Touched
  leads are listed and left. Fills on existing leads stay. The batch is
  stamped *Undone* with a count.
- **The tab (ruling 88).** Templates and history share the Imports tab, and
  *Import…* is its one entry point.

**Tests.** `test_campaigns_phase3.py` (import), `test_campaigns.py:604`,
plus a new `test_campaign_import_templates.py` covering recognition,
renames, the four fixes, Excel, fills, undo and the touched rule.

### 7e.8 Lists — rulings 90–95, 98

**The model.**

- `audience_list.recipe` becomes `{"include": [group], "exclude": [group]}`.
- A group is one of:
  - `{type, conditions}` (today's step conditions, with the same curated
    fields and operators);
  - `{listId}`;
  - `{values}` (the file import).
- `run_recipe` becomes the union of the includes minus the union of the
  excludes.
- *Keep only*, step order, the per-step counts and the `step` column go.
  The run report gains one count per group.
- **A static list has no recipe** (ruling 91). Its members are hand rows
  only, so `run_list`, `last_run_at` and the "never run" guard
  (`audience.py:723`) no longer apply to it.
- **A dynamic list has no hand edits** (ruling 92). `audience_list_entry`,
  `apply_entries` and the dynamic half of `mark` / `unmark` are removed.
- `kind` cannot change after creation (ruling 93). *Copy current members
  to a new static list* is a new route.

**The data.** Lists exist only on crm-test, as test data, and the sandbox
truncates the tables nightly. Migration 0034 converts what it can: Add
steps become includes, Remove steps become excludes, and a list with *Keep
only* or with step order that matters is marked *needs rebuilding* and
shown so. Standing entries become a static list per dynamic list, named
"<list> — exceptions" and left out by it. No production data exists.

**The screens (ruling 98).**

- The index shows name, kind, members, the Constant Contact tick and last
  used.
- The list page has a top line with per-channel counts. Each count is
  `resolve_targets` run per kind, as the counts only.
- A dynamic list states *who is on it* in sentences, one per group,
  generated from the group. *Edit* opens the builder: Include and Leave out
  panels, each with + group.
- A static list has *Add people*: the same condition panel plus a name or
  email box over the five target types, with tick, select all and Add
  (ruling 94).
- The member grid has search, sort and export. On a dynamic list it adds a
  *Brought in by* column (the group) and **Exclude**, which asks which
  static list to add the person to (ruling 92).
- Creating a dynamic list offers to leave out an exclusion list.

**Tests.** `test_campaign_lists.py` is largely rewritten. These go:

- `test_add_widens_keep_narrows_remove_excludes`
- `test_keep_only_touches_its_own_type`
- `test_hand_ticks_and_standing_entries`
- `test_a_static_list_never_run_cannot_be_sent_to`
- `test_static_list_run_freeze_and_hand_tick_survives_run_again`

The import, lists-of-lists and cycle tests stay, adapted.

### 7e.9 Constant Contact, campaigns and events — rulings 95–97, 99–102

**A kept-current copy per list (ruling 95).** `core/mailing_sync.py` works
for one list, named by `MAILING_LIST_NAME`, with its id and last-push
summary on the singleton `mailing_connection` row.

- `audience()`, `build_plan()` and `apply_plan()` gain a parameter: the
  people to hold, already consent-filtered, and the list name. The
  consent and address rule is shared with `audience.resolve_targets`'s
  email branch, so a member of the chapter is held at `cbmEmail` there as
  everywhere.
- `audience_list` gains `cc_sync` (bool), `cc_list_id`, `cc_last_sync_at`
  and `cc_last_sync` (JSONB summary).
- The worker's push loop runs the standing list and then every
  `cc_sync` list. `vendor_unsubscribed` is fetched once per pass. Alert
  keys are per list (`mailing_list_<id>_failed`).
- *Sync now* is a route that runs one list's pass, records the action, and
  reports the counts.
- A rename renames the Constant Contact list (`PUT /contact_lists/{id}`, a
  new `MailingClient` method). Retiring stops the sync and never deletes
  the copy.

**The email campaign (rulings 95, 96, 100).**

- Sign-off no longer pushes a per-campaign list (`push_campaign` and its
  `Campaign — <name>` list go). Sign-off now requires the campaign's list
  to have `cc_sync` on, runs *Sync now*, and moves the campaign to Signed
  off.
- The strip then reads "Next: send it in Constant Contact to <list>, then
  pick that email here". *Pick the email* lists the account's email
  campaigns sent in the last 30 days to that list, through new
  `MailingClient` methods over the email-campaign endpoints. The
  `campaign_data` scope is already granted, so no reconnection is needed.
- Picking one stores its id on the campaign (new field
  `COutreachCampaign.vendorEmailId`) and moves it to Sent.
- **The send report (ruling 96).** A worker pass reads, for each Sent
  email campaign in its first 30 days, the per-recipient tracking reports
  (sends, bounces, opens, clicks). It writes one `COutreachTouch` per
  recipient, matched to the Contact by address: Sent / Delivered /
  Returned, with opened and clicked, upserted so a re-read never doubles.
- *Mark as sent* goes. The pick is the confirmation.
- The exact endpoint shapes are **inferred from the vendor's V3 reference,
  not yet called**. The first live run is the check (Draft 8).

**Lists only (ruling 99).** The four per-kind rule cards
(`app.js:556-786`) and their `rule` payloads go. Each kind's
`select_targets` becomes the recipe of a **ready-made dynamic list**
created by migration 0034: *All leads for postcards*, *Opted-in prospects
(Engaged and later)*, *Prospects with text consent*, *Leads and prospects
with a phone*, plus *Dormant clients (a year)*. They are marked `system`:
they cannot be deleted and can be copied (Draft 9). Build always reads the
campaign's list. `resolve_targets` keeps every per-channel check, which is
what makes ruling 99's "never an unlawful send" true.

**The campaign page (ruling 100).** The strip maps today's
`campaignStatus` with no CRM change:

- Draft is Draft when the list or content is missing.
- *Ready* is Awaiting sign-off.
- Signed off is Signed off.
- *Sent* is Running for a postcard or text, Running for a call once calls
  begin, and the email pick for an email.
- *Results* is Complete.

`_MANUAL_MOVES` stays for Cancel. The tabs:

- Overview.
- *Audience and content*: the list picker, the per-channel counts and the
  kind's content (text wording, postcard template, the picked email).
- Links: the personal form first, with Copy.
- *Recipients*: touches, paged, searchable and exportable, with delivery
  columns. This replaces the Touches table under Responses.
- Responses.
- *Results*: today's Analytics, renamed.

**The grid (ruling 101).** It gains Event, Funders, Stage (the strip's
word), Reached and Responses. Partners are always filled: the present
60-row cutoff goes, read in one batched related-list pass. The filters move
to the server when the grid passes 200 rows.

**+ New campaign (ruling 102).** A short form (channel, name, owner, and
optionally event, partners and funders) creates the Draft and opens it.

**Promote this event (ruling 97).**

- *Promote this event* on the event's detail view (`events/frontend`)
  opens a form: tick the channels, pick the list, confirm the names. It
  creates one campaign per channel through the same create path, linked to
  the event (`COutreachCampaign.events`).
- The event gains a **Campaigns** tab. It shows one row per linked
  campaign (reached, registered and attended) plus *No campaign*, using the
  existing, unused `reporting.campaign_results`
  (`campaigns/reporting.py:257`). It reads `CEventRegistration.outreachCampaignId`
  and `attendanceStatus`.
- Each number opens the people behind it.

**Tests.** `test_campaigns_email.py` (the push and its list name go),
`test_mailing_sync.py` (parameterised), `test_campaigns_phase4.py`,
`test_events_*` (the tab), and a new `test_campaign_send_report.py`.

### 7e.10 The Calls tab — rulings 115, 116

`calls.js` moves into the page as the Calls panel:

- the brief moves to the top, collapsible;
- the counts are computed from `call_list`;
- rows open a side panel with *What we know* (the lead page's component),
  the personal link and the outcomes;
- *Call again* takes a time through `CBMDateTime`;
- recording an outcome moves to the next row.

`record_outcome` is unchanged, apart from Draft 3's shared outcome code.

### 7e.11 Storage and CRM changes

**Application database (migration 0034):**

- `import_template` (new);
- `lead_level_manual` (new);
- `import_batch` gains `excluded_rows` JSONB, `undone_at`, `undone_by`
  and `undo_result`;
- `audience_list` gains `cc_sync`, `cc_list_id`, `cc_last_sync_at`,
  `cc_last_sync` and `system`;
- `audience_list_entry` is dropped after its conversion;
- the recipe conversion and the ready-made lists are created.

The sandbox recapture adds seeders for templates and the ready-made lists
(`SANDBOX-RESET.md`).

**CRM, one handoff** (`marketing-redesign-crm-handoff.md`, written with the
`espo-crm-changes` skill, verified against `GET /Metadata`):

- `CProspect.qualificationLevel`: enum Identified / Contactable /
  Referred, never Read-only.
- `CProspect.levelSetByHand` (user link) and `levelSetAt` (datetime).
- `CProspect.referredByPartner`: many-to-one to `CPartnerProfile`.
- `CProspect.referredByName`: varchar.
- `CProspect.replied`: bool.
- `CProspect.assignedUser`: enabled, if absent.
- `CConversation` ↔ `CProspect`: many-to-many, matching the existing
  `PARENT_LINKS` shape.
- `COutreachTouch.outreachCampaign` no longer required, and its channel
  gains *Personal call* and *Personal email* (Draft 3).
- `COutreachCampaign.vendorEmailId`: varchar.
- Roles:
  - Marketing Admin Role: `CConversation` read; edit on `CProspect` for the
    new fields; Assignment Permission allowing a lead's assignee.
  - Mentor Role: unchanged.

All of it is feature-detected, so each piece stays dark until its field
exists. Production's apply rides the arc's deferred Sunday slot.

### 7e.12 Drafts for Doug's approval — RULED 10-23-26 03:53 (rulings 117–125)

Doug: "approve as recommended". Drafts 1, 2, 3, 5, 8 and 9 stand as
written (rulings 117, 118, 119, 121, 124, 125). Drafts 4, 6 and 7 stand
as Claude's recommended change, noted under each (rulings 120, 122, 123).

1. **Placement runs inline and in a 15-minute sweep, with the manual
   snapshot in the application database.** Ruled 117, plus: a manual level
   with no snapshot is never moved by the sweep.
   - Cost: a lead edited in the CRM's own screens can take up to 15 minutes
     to change level.
   - Cost: the "who set it by hand" history is split. The CRM has who and
     when; the application has the facts snapshot.
2. **Only assigned leads are matched by the email sync.** A reply to a
   personal email always comes from an assigned lead, because ruling 108
   sends personal outreach only through an assignee.
   - Cost: a lead who writes in unprompted, with no assignee, is not
     captured on the lead. It reaches info@ as today.
3. **A touch without a campaign** carries personal calls and emails.
   - Cost: every report that counts touches per campaign must ignore
     campaign-less touches. The handoff changes a required flag on a live
     entity.
4. **A sender needs a `cbmEmail` on a mentor profile.** Marketing staff
   without one are refused, with the reason named.
   - Cost: some staff need a profile, or a later change reads the address
     from the user record instead.
   - **Ruled otherwise (120):** the mentor profile's address first, else
     the user's own address when it is on the chapter's mail domain. The
     same resolution feeds § 7e.5's sync scopes.
5. **A Person found by research fills the lead's own person fields.**
   - Cost: it narrows how `enrichment` reads ruling 43. Contacts are still
     created only at first contact.
6. **The opt-out line wording** appended to every personal email, as in
   § 7e.5.
   - **Ruled otherwise (122):** the sentence AND the chapter's postal
     address, from a new setting filled in at /setup; the server appends
     both when the message lacks them.
7. **The import plan runs as a background job the page polls.**
   - Cost: a new job table or the existing enrichment-run pattern reused.
     The build reuses the enrichment pattern.
   - **Ruled otherwise (123):** the delivery worker runs the plan; the
     `import_batch` row carries its status (two new columns) and the page
     polls that row. Not the enrichment run table.
8. **The send report's vendor endpoints are inferred, not yet called.**
   - Cost: the first live run may reshape § 7e.9's report step.
9. **The ready-made lists are system lists**, undeletable but copyable,
   with the five names in § 7e.9.

### 7e.13 Order and cost

Each step is dark behind its own switch, read per request, and gets a live
pass on crm-test as a real non-admin Marketing Admin user (plus a Mentor
Team caller for M1 and M10).

1. **M1: one page, six tabs** (§ 7e.2), behind no switch, because the
   tabs are the same features. About two days. **Built as v0.279.0
   (10-23-26 01:33), not pushed; live pass owed.** Three build choices,
   each a routine one under the section as written: the unsaved-list
   warning on a tab switch is the page's own dialog (*Unsaved changes* →
   *Leave them*), never the browser's; the open list rides the hash
   (`#lists?list=<id>`), so the old `lists.html?list=` address still opens
   the list; the *Campaign calls* tile reads the running call campaigns
   under the org-wide key on each portal load (one list read plus one read
   per running call campaign) and shows nothing on a failed read.
2. **M2: the ladder and the Leads tab** (§§ 7e.3, 7e.4), behind
   `LEAD_LADDER`, after the handoff's lead fields on crm-test. About four
   days.
3. **M3: Review as the research queue** (§ 7e.6). About a day and a half.
4. **M4: the import tool** (§ 7e.7), behind `IMPORT_TEMPLATES`. About
   five days.
5. **M5: personal outreach** (§ 7e.5), behind `LEAD_OUTREACH`, after the
   handoff's link and touch changes. About four days.
6. **M6: lists** (§ 7e.8). About four days.
7. **M7: Constant Contact per list and the email campaign** (§ 7e.9
   first half), behind `CAMPAIGN_LIST_SYNC`. About three days, plus the
   live send.
8. **M8: lists only and the campaign page** (§ 7e.9 second half). About
   four days.
9. **M9: the send report and Recipients** (§ 7e.9). About three days.
10. **M10: Promote this event and the roll-up, and the Calls tab**
    (§§ 7e.9, 7e.10). About three days.

**Cost, named.**

- **About seven weeks of build, the largest piece of this arc.** Each step
  can ship and be used on its own, in this order.
- **One CRM handoff** on every CRM, with production on the deferred slot.
- **One new dependency** (`openpyxl`).
- **About 150 existing tests rewritten**, mostly in lists and campaigns.
- **A larger email sync.** Assigned leads join the scopes, and they are
  matched exactly.
- **Two parts rest on facts a live run must confirm:** the vendor's report
  endpoints, and the send-report volume on a real list.
- **The standing cost the rulings accepted:** CBM writes personally to
  people who never opted in (ruling 107).

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
| Social media: one kind with a platform, or a kind per platform | **Ruled (55, 10-20-26): one kind, a `platform` field** | § 3.6, question 10 |
| SMS has no sending path | **Put to Doug** — written on: the kind ships with its rule, list and export; sending waits for a vendor | § 3.5, question 11 |
| One event or many per campaign | **Answered as a draft:** many (a many-to-many), from Doug's plural and the programme-page link | § 1.5 |
| The status vocabulary | **Answered as a draft:** the six states of § 1.3, which the application moves; Doug's four-word strawman maps onto them | § 1.3 |
| Who may correct or retire a link | **Answered as a draft:** the campaign's team, action-logged with old and new | § 3.7 |
| The programme-page carry-through | **Answered:** query-string carry by the page's own script, with its honest limit named | § 3.7 |
| Where the prospect screens live | **Ruled (56, 10-20-26): under the Campaign Management tile** | § 3.8, question 12 |
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
   **Deferred by Doug 10-18-26 23:01, "till later with more information".**
   The analysis put to him, kept so it is not redone: (a) the raw Ohio
   filing does not arrive in the import's shape — it carries a document
   number, the name, the effective date, associates and **two addresses**
   (the filing address and the registered agent's) — so either the filter
   renames its columns or the import accepts the filing's own names as
   aliases (the latter recommended, a small change); (b) where it lands:
   the upload (built), a watched Drive folder, or an endpoint — the upload
   recommended at 100–500 rows a month; (c) monthly, harmless to repeat;
   (d) **which address** is the decision: A filing address always; B filing
   address, else the agent's, skipping commercial agent services; C the
   filter chooses one per row and the import keeps both on the record
   (recommended — the filter already judges fit under ruling 11). The
   research sample's evidence: `research/registry-enrichment/enrichment-findings.md`.
3. **Rung 1's stored name: `Unverified` (recommended) or `Unqualified`?**
   **Answered: `Unverified` (ruling 29).** `Unqualified` is a terminal reject in every surveyed CRM and is also the
   fit-failure side exit here, so one word would mean two things.
4. **Which mail vendor: Lob (recommended) or PostGrid?** Price is a wash
   (ruling 2); Lob's test key runs the whole pipeline, callback included,
   without printing. Doug opens the account; the plan never does.
   **Deferred by Doug 10-18-26 23:02 until more information is available.**
5. **The card.** Who designs it, which size (`4x6` / `6x9` / `6x11`), and the
   offer text. The template holds the QR code and the business name and
   address merge fields; everything else is creative.
   **Deferred by Doug 10-18-26 23:02 until more information is available.**
6. **Who makes the calls?** Recommended: members of the teams named on the
   campaign, default the Marketing Admin Team; naming the Mentor Team opens
   the list to mentors. Cost: a mentor who calls needs read and edit on
   `COutreachTouch` and read on `CProspect` in the Mentor Role. **Answered
   10-18-26: as recommended (ruling 36).**
7. **Should the information request door create its company typed
   `Prospect`** (recommended) instead of today's `Client` with
   `cClientStatus=Prospect`? **Answered 10-17-26: yes (ruling 34).** A
   matched company keeps the types it has; the write feature-detects the
   option and falls back to the old shape until a CRM carries it;
   `scripts/relabel_info_request_companies.py` relabels the companies
   created under the old shape, dry-run first, Doug runs it. It makes the
   relabel at conversion read the same for every door. Cost: a live door's
   behaviour changes, and existing records keep the old shape unless a
   one-time script relabels them.
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
    "social" becomes a list of values. **Answered 10-20-26: A, as built
    (ruling 55).**
11. **SMS sending.** Recommended: ship the kind with its selection rule, its
    signed-off list and an export, and no sending, until you name a vendor.
    Cost: a kind that does not send; staff send from the vendor's own tool
    with the exported list and press *Mark as sent*. The alternative is to
    rule a vendor now (Twilio is the usual one), which adds a client, a
    secret, a sender number and the opt-out handling the law requires. **Answered
    10-18-26: B, send from the application (ruling 38), against the
    recommendation.**
12. **The prospect screens' home.** Recommended: Prospects, Review and Calls
    as secondary grids under the *Campaign Management* tile — one tile for
    the whole marketing workspace, the same team either way. Cost: a tile
    named for campaigns also holds the import; the alternative is a second
    tile, *Prospects*, on a portal that already shows a staff user twelve. **Answered 10-20-26: A, as built
    (ruling 56)**, with a new requirement for the two grids (§ 7b).

Questions 13–16 were added in v0.8 for the rework of § 7a (rulings 41–44).

13. **Change the stored values, or the labels only?** Recommended: change
    the stored option values on `CProspect`, Contact and Account and move
    the existing ones with a dry-run-first script, while the arc's data is
    still test data. Cost: a value migration on three CRMs and every
    module's constants. The alternative relabels the options in the CRM and
    keeps `Unverified`, `Lead` and `Warm Lead` as stored values — cheaper
    now, but the code and the CRM then disagree in every read, which is the
    confusion the rulings set out to remove. **Answered 10-19-26: A, change
    the stored values (ruling 45).**
14. **What does the old "conversion" become?** The Responses tab counts
    *Converted* = a relationship record carries the campaign. Under ruling
    43, *converted* means a lead became a Prospect. Recommended: the tab
    shows **Converted** (leads that became Prospects) and **Became a client,
    partner or funder** (the old meaning), and documents say "a
    relationship begins" for ruling 22. Cost: one more column. The
    alternative keeps *Converted* for the old meaning and calls the lead
    step something else, which breaks with every CRM the research looked
    at. **Answered 10-19-26: A, three counts (ruling 46).**
15. **Must a call marked Interested capture an email or website?**
    Recommended: yes — the outcome asks for one, and without it the call is
    recorded as a response on the lead, which stays a lead (ruling 42: no
    Company without a website, no Contact without an email). Cost: one more
    field for the caller. The alternative converts on the outcome alone and
    creates a Company or Contact with neither, which ruling 44's "a response
    that brings a website or email converts" rules out. **Answered 10-19-26:
    A, an email or website is required (ruling 47).**
16. **Does a public-form submission also create a lead?** A webinar
    registrant or information requester today creates a Contact with no
    prospect record (§ 1.8). Recommended: no — a public-form submission is
    first contact itself, so it creates the Prospect directly and its Lead
    Source is the form; only a lead named by the prospect id is converted.
    Cost: not every Prospect has a lead behind it, so "where did they come
    from" reads the Contact's campaign and Source, not a lead. The
    alternative creates a lead already Converted for every submission — a
    complete history, and a lead record per form submission.
    **Answered 10-19-26: B, a lead behind every new public-form record
    (ruling 48)** — against this question's recommendation, which the
    session withdrew because ruling 41 names every new outside record a lead.
17. **Leads have no industry field — add one?** Ruling 63's default list
    names industry for leads, but `CProspect` holds none (crm-test
    metadata, 10-20-26), so "Qualified leads in manufacturing" cannot be
    written. **A (recommended):** add `industry` to the lead as an enum
    with the Company's own sector options (`Account.cIndustrySector`), filled
    by the imports when a file carries it and editable in Review. **B:**
    filter a lead by the industry of the Company it converted to — useless
    for the unconverted leads that most campaigns target. **C:** no industry
    on leads. Cost of A: a CRM change on three CRMs (crm-test, then
    production at its slot, Boston with its release) and an import mapping;
    and it fills only as fast as the source files carry an industry, which
    question 2 (what the outside filter delivers) has not settled.
    **Answered 10-20-26: A (ruling 66).**
18. **Funders have no status field — is that enough?** Ruling 63's default
    names a status for funders; `CSponsorProfile` has none. **A
    (recommended):** use what exists — manager, last contribution, total
    contribution, last contacted, and the Company's sponsorship level and
    renewal date; "lapsed funders" is "last contribution before a date".
    **B:** add a funder status enum (for example Prospective, Active,
    Lapsed) to the funder record. Cost of A: no field says a funder has
    ended, so a funder who stopped stays selectable until staff exclude
    them. Cost of B: a CRM change on three CRMs and a status nobody yet
    keeps current.
    **Answered 10-20-26: B, against the recommendation (ruling 67).**
19. **Does "one card per business, ever" (ruling 14) apply to clients,
    partners and funders?** It was ruled for prospects, and the postcard
    code checks every card ever sent to the Company. A client who received
    a prospect card in 2026 could never be mailed a re-marketing card.
    **A (recommended):** ruling 14 applies to lead targets only; a client,
    partner or funder card is limited instead by "not carded by this
    campaign". **B:** ruling 14 applies to every target. Cost of A: a
    business can receive a prospect card and later a client card; a
    partner or funder could be carded by every campaign that names them.
    **Answered 10-20-26: A (ruling 68).**

20. **Where the lead code lives.** § 7d.1 drafts two CRM fields,
    `CProspect.leadCode` and `Contact.cLeadCode`, copied at promotion.
    **A (recommended):** the two fields. Cost: a CRM handoff on every CRM,
    and the code is visible to any role that reads the record (a staff
    member can copy a link that opens as that person). **B:** an
    application table mapping code to lead, contact and company. Cost: no
    CRM change, but the sandbox reset empties it nightly so every demo
    link dies by morning, and the code is invisible in the CRM and the
    Analytics builder.
    **Answered 10-22-26: A (ruling 74).**

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
| Version | v0.26 — Phases 1–4 and the lead model built; §§ 7b and 7c built and live-passed on crm-test; § 7d (the lead identifier in every link, rulings 71–75) approved, D1 built; § 7e (the Marketing Management redesign, rulings 79–125) approved, step M1 built as v0.279.0 |
| Last Updated | 10-23-26 03:53 |
| Prepared by | Claude (Claude Code), for D. Bower |
| Session | 2026-10-14 planning session (v0.1) and the same evening's revision session (v0.2), both from `history/prompts/prospect-marketing-build-plan-prompt-v0.1.md`; moved into this directory the same night (v0.2.1) |
| Related | `rulings.md` (rulings 1–27 and the Campaign Management requirements CM-1 to CM-11), `history/prospect-marketing-plan.md` (the discussion record), `prds/mailing-list-and-event-sponsorship-plan.md` (the notice vocabulary, the push), `prds/chapter-network/crm-update-runbook.md`, `forms/client_intake/orchestrator.py` (the partner-link precedent), `core/crm_upsert.py`, `core/mailing_sync.py` |

### Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.39 | 10-23-26 03:53 | Claude (Claude Code) | § 7e.12 ruled (rulings 117–125, Doug "approve as recommended"): six Drafts as written, Drafts 4, 6 and 7 as recommended; each change noted under its Draft. § 7e is approved. |
| 0.38 | 10-23-26 01:33 | Claude (Claude Code) | § 7e.13 step M1 built (v0.279.0): one page, six tabs; the three build choices recorded under the step; § 7e.2 heading marked built. The Drafts in § 7e.12 still await Doug. |
| 0.37 | 10-23-26 01:25 | Claude (Claude Code) | § 7e added: the Marketing Management redesign from rulings 79–116 — one page, the qualification ladder, personal outreach, Review as a research queue, the import tool, lists, Constant Contact per list with the send report, lists-only campaigns, Promote this event, the Calls tab; storage and one CRM handoff; nine Drafts for approval (§ 7e.12); ten steps, about seven weeks (§ 7e.13). Header Version and Last Updated brought up to date. |
| 0.36 | 10-22-26 13:00 | Claude (Claude Code) | § 7d: D1 built (v0.276.0); the four build choices recorded under § 7d.6 step 1. |
| 0.35 | 10-22-26 12:40 | Claude (Claude Code) | § 7d.5: ruling 77 noted (field rules on the Marketing Admin Role only, code fields off every layout). |
| 0.34 | 10-22-26 01:42 | Claude (Claude Code) | § 7d.5's CRM handoff written (`lead-code-crm-handoff.md`, `scripts/plans/lead-code.json`, fingerprint `bec909277859`; two field rules in `scripts/migrate_outreach_roles.py`). Ruling 74's "indexed" not buildable through the API — recorded in § 7d.5; `Clicked` found already present. Header revision corrected from 0.30. |
| 0.33 | 10-22-26 01:35 | Claude (Claude Code) | § 7d approved: the prefill table confirmed as written (ruling 75); status line and table heading updated. |
| 0.32 | 10-22-26 01:34 | Claude (Claude Code) | Question 20 answered A (ruling 74): the code lives in two CRM fields; § 7d.1's storage marked settled. |
| 0.31 | 10-22-26 01:31 | Claude (Claude Code) | § 7d added: the lead identifier in every link (rulings 71–73) — the per-person code on the lead and the contact, delivery per kind (the vendor custom field and merge tag, the text's `{link}`, the caller's link), the one resolver `/c/{link}/{code}` recording the click, the per-form lookup with a server-side allowlist, the per-form prefill table with Doug's registration example, the handoff, three steps. Question 20 added (where the code lives). |
| 0.31 | 10-22-26 12:10 | Claude (Claude Code) | § 7c status line: built and live-passed on crm-test. |
| 0.30 | 10-21-26 22:30 | Claude (Claude Code) | § 7c.7 L2 live-passed on crm-test; § 7c complete on crm-test. |
| 0.29 | 10-21-26 16:01 | Claude (Claude Code) | § 7c.7 L2 built (v0.271.0). |
| 0.28 | 10-21-26 15:36 | Claude (Claude Code) | § 7c.7 L1 live-passed on crm-test. |
| 0.27 | 10-20-26 18:20 | Claude (Claude Code) | § 7c.7 L1 built (v0.270.0). |
| 0.26 | 10-20-26 18:02 | Claude (Claude Code) | § 7c approved by Doug as written. |
| 0.25 | 10-20-26 17:56 | Claude (Claude Code) | § 9 question 19 answered: A, ruling 14 applies to leads only (ruling 68); § 7c.1 and the section's opening updated. § 7c awaits approval. |
| 0.24 | 10-20-26 17:49 | Claude (Claude Code) | § 9 question 18 answered: B, a funder status (ruling 67); § 7c.3 and § 7c.7 updated. |
| 0.23 | 10-20-26 17:47 | Claude (Claude Code) | § 9 question 17 answered: A, a lead carries an industry (ruling 66); § 7c.3 and § 7c.7 updated. |
| 0.22 | 10-20-26 17:37 | Claude (Claude Code) | New § 7c, campaign audiences as named lists (rulings 58–65), a draft for approval: what a list member is per target type, the recipient per channel, the default step-field table verified against crm-test metadata, the engine, six application tables (migration 0032), the screens, two build steps (L1, L2) and their cost. § 9 questions 17 (no industry on leads), 18 (no status on funders) and 19 (ruling 14's scope) added. The revision table's Version and Last Updated brought up to date. |
| 0.21 | 10-20-26 14:36 | Claude (Claude Code) | § 7a.5 step 4 deferred by Doug until development is finished, with its cost named. |
| 0.20 | 10-20-26 14:28 | Claude (Claude Code) | § 7b live-passed on crm-test (v0.267.0–2); the pass's two fixes recorded in `CHANGELOG.md`. |
| 0.19 | 10-20-26 02:00 | Claude (Claude Code) | § 7b.1 approved as written and built (v0.267.0). |
| 0.18 | 10-20-26 01:44 | Claude (Claude Code) | § 7b: Doug's five answers on the Leads and Review grids, and § 7b.1, the design drawn from them, a draft for approval. |
| 0.17 | 10-20-26 01:16 | Claude (Claude Code) | § 9 question 12 answered: A (ruling 56). Doug's new requirement for the Leads and Review grids opens § 7b, being gathered. |
| 0.16 | 10-20-26 01:08 | Claude (Claude Code) | § 9 question 10 answered: A, one social media kind with a Platform field (ruling 55). |
| 0.15 | 10-19-26 23:44 | Claude (Claude Code) | § 7a.5 step 3 passed: the lead model's live pass on crm-test, with v0.265.1–3 and ruling 54. Step 4, production, is next. |
| 0.14 | 10-19-26 11:47 | Claude (Claude Code) | § 7a.5 step 2 built (v0.265.0, not pushed): the code rework, with rulings 51–53 and the decisions that follow from them recorded in the step. |
| 0.13 | 10-19-26 11:03 | Claude (Claude Code) | § 7a.5 step 1 done on crm-test: the lead model's CRM handoff written and its additive half applied (rulings 49, 50); step 2, the code, is next. |
| 0.12 | 10-19-26 01:22 | Claude (Claude Code) | § 9 question 16 answered: B, a lead behind every new public-form record (ruling 48). Questions 13–16 all answered; § 7a.5 step 1, the CRM handoff, is next. |
| 0.11 | 10-19-26 01:21 | Claude (Claude Code) | § 9 question 15 answered: A, an Interested call converts only with an email or website (ruling 47); the question's citation corrected from ruling 42 to ruling 44. |
| 0.10 | 10-19-26 01:20 | Claude (Claude Code) | § 9 question 14 answered: A, three counts on the Responses tab (ruling 46). |
| 0.9 | 10-19-26 01:09 | Claude (Claude Code) | § 9 question 13 answered: A, change the stored values (ruling 45). |
| 0.8 | 10-18-26 23:16 | Claude (Cowork) | Rulings 41–44 (the lead model, from the executive overview session): a revision note at the top; new § 7a — the model as ruled, the drafts chosen (stages Prospect · Engaged · Opportunity, exit Duplicate, a scan does not convert, CRM label *Outreach Lead*), the component-by-component change table, the words that move, the order and its cost; questions 13–16 added to § 9. §§ 1–6 not rewritten: they describe the build until § 7a is built. |
| 0.7 | 10-18-26 02:24 | Claude (Claude Code) | § 7 Phase 4 marked built (v0.262.0–v0.264.0) with rulings 38 and 39; Phase 5's texting item struck. |
| 0.6 | 10-18-26 00:50 | Claude (Claude Code) | § 7 Phase 3 marked built (v0.261.0) with what it holds; question 6 answered (ruling 36) and the Mentor Role's two grants named; ruling 37 recorded as built first. |
| 0.4 | 10-15-26 00:02 | Claude (Claude Code) | Ruling 32: § 1.5's reverse of `CPartnerProfile.outreachCampaign` is `attributedPartnerProfiles` (the row had named `partnerProfiles` twice; found by the handoff session's dry run, drafted there, chosen by Doug); § 1.10 gains the row. The plan files were already written on this name, so the fingerprints stand. |
| 0.3 | 10-14-26 22:43 | Claude (Claude Code) | Doug's answers to questions 1, 3, 8 and 9 recorded (rulings 28–31). Question 8 against the recommendation: `CEngagement.referringPartners` many-to-many to `CPartnerProfile` (reverse `referredEngagements`) added — seventeen links; step 6a rewritten (the many link holds every referring partner, the single link stays the partner link's own, readers take the union); the per-door table, the coexist paragraph, Phase 1's handoff and grants, Phase 2's build and verification, § 8 and § 9 updated. |
| 0.2.1 | 10-14-26 22:27 | Claude (Claude Code) | Moved from `prds/prospect-marketing-build-plan.md` into `prds/prospect-marketing/` (Doug's consolidation ruling, 10-14-26); references to the process plan now point at `rulings.md` and `history/`. No section revised. |
| 0.2 | 10-14-26 22:09 | Claude (Claude Code) | Revised against the Campaign Management requirements (CM-1 to CM-11): the campaign is labelled Campaign and names partners and events (two many-to-many links, sixteen in all); five kinds with the SMS kind (§ 3.5) and the social media kind (§ 3.6) added; a new § 3.7 for links as short resolvable addresses in the application's database, with correct, retire, the programme-page carry-through and the QR generator; the screens rebuilt around the Campaign Management tile, the campaign record page (Overview / Links / Responses / Analytics) and the partner's Campaigns tab; the forms carry the link token and relate the campaign's partners by door (step 6a); reporting gains the campaign page's own numbers and a campaign dashboard scope; the phases, their flags (`CAMPAIGNS_*`, `PROSPECT_STALE_DAYS`) and verification scripts updated; the requirements' open list answered in § 8; questions 8–12 added. The superseded-in-part pointer replaced by this revision note. |
| 0.1.1 | 10-14-26 21:55 | Claude (Claude Code) | Pointer added at the top: superseded in part by *Requirements — Campaign Management application (10-14-26)* in the plan (CM-1 to CM-11); the sections v0.2 must revise are named there. No section revised. Duplicated date in Last Updated fixed. |
| 0.1 | 10-14-26 17:34 | Claude (Claude Code) | First version: the record model in Entity Manager vocabulary (three custom entities, fifteen links, the stage fields, the relabel), the two import doors, the three campaign kinds on one engine, the landing page as a sixth form kind, conversion per door, reporting, five phases with handoffs and verification scripts, the open list, seven questions. Finding recorded: the native marketing module is hidden on crm-test and the org key 403s on Lead and Campaign. |
