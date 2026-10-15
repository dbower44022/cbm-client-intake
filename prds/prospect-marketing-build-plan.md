# Prospect Marketing — build plan v0.1.1 (2026-10-14)

Last Updated: 10-14-26 21:55 · Revision 0.1.1 — change log at the end.

**Status: a plan, not a build.** Nothing here is built, no CRM is changed, no
vendor account exists. This document turns the rulings of
`prds/prospect-marketing-plan.md` (rulings 1–8 of 2026-08-11 and 9–27 of
2026-10-13/14, all settled and none reopened here) into the record model, the
screens, the phases, the CRM handoffs and the verification scripts the build
needs. It is a sibling of that document rather than a section of it because
it is longer than the document it serves. Where this plan had to choose, the
choice is stated as a draft with its cost; the choices that pass the two-part
test are in § 9 as numbered questions, and the plan is written on the
recommended answer to each so that a "yes" costs Doug nothing.

**⚠️ Superseded in part, 10-14-26 evening.** The Campaign Management
application was defined after this plan was written:
`prds/prospect-marketing-plan.md`, section *Requirements — Campaign
Management application (10-14-26)*, requirements CM-1 to CM-11. Where this
plan differs — the campaign kinds (SMS and social media), partners and
events on a campaign, named links with short resolvable addresses, the
campaign page's tabs and numbers, the tile *Campaign Management* and the
word *campaign* — the requirements win. That section ends with a
section-by-section list of what v0.2 of this plan must change (§§ 1.3, 1.5,
3.1, 3.5, 3.6, 4, 5, 6, 9). Nothing below has been revised yet.

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

- **Three custom entities** — `CProspect` (the quarantine record), `COutreachCampaign` (the campaign) and `COutreachTouch` (one row per attempt, which is also campaign membership) — rather than EspoCRM's own Lead and Campaign entities. The finding and the cost are in § 1.1; it is question 1.
- **The rung continues after promotion as a field on the Contact and on the Company** (`cFunnelStage`), not through the link to the prospect record, because a webinar registrant has no prospect record to read through (§ 1.8).
- **One word for one thing.** An *outreach campaign* is ours. A *notice* is a Constant Contact send, as the mailing-list plan already calls it (§ 3.6).
- **The landing page is a sixth form kind** (`forms/prospect_response/`), so it inherits durable capture, holds and Submission Admin visibility; a scan is logged on the page load, before any form (§ 4).
- **The standard forms carry two hidden ids**, `prospect` and `campaign`, exactly as the partner link carries one, and honour them at delivery with the same validate-or-drop rule (§ 5).
- **Five phases, each dark behind a flag or feature detection**; Phase 1 mails one real card and records one real scan, and needs two CRM handoffs applied first (§ 7).
- **Seven questions for Doug** (§ 9). Three gate Phase 1: the entity choice, the vendor, and what the outside filter delivers.

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

**Cost of the recommendation, honestly named:** three entities and fifteen
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

Create Entity: Name **`OutreachCampaign`**, label *Outreach Campaign*, plural
*Outreach Campaigns*, Type **BasePlus**, Stream **on**, tab **on**.

| Field | Type | Notes |
|---|---|---|
| `name` | varchar, required | "State New Business Filing — Postcard, 2026-11" is a name, not a source value (ruling 26) |
| `campaignKind` | enum: `Postcard` · `Email` · `Call` | Which engine runs it (§ 3). `Text` is reserved, not offered, until a text campaign is ruled |
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
| `description` | wysiwyg | The brief, the offer, the creative notes — the shared editor |

Links stored on it: `event` (optional, a card or notice that promotes one
webinar), and the reverse links from touches, Contacts, Companies and the
five relationship records (§ 1.5).

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
| `channel` | enum: `Postcard` · `Email` · `Call` | Copied from the campaign so a touch reads alone |
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
| `COutreachCampaign` | `event` | many-to-one | `CEvent` | `outreachCampaigns` | Optional |
| `Contact` | `cOutreachCampaign` | many-to-one | `COutreachCampaign` | `contacts` | Ruling 27: only when the submission created the Contact |
| `Account` | `cOutreachCampaign` | many-to-one | `COutreachCampaign` | `companies` | Ruling 27: same for the Company |
| `CEngagement` | `outreachCampaign` | many-to-one | `COutreachCampaign` | `engagements` | Ruling 27: every time |
| `CInformationRequest` | `outreachCampaign` | many-to-one | `COutreachCampaign` | `informationRequests` | Ruling 27 |
| `CEventRegistration` | `outreachCampaign` | many-to-one | `COutreachCampaign` | `eventRegistrations` | Ruling 27. Distinct from the existing `noticeCampaignId` varchar, which is the Constant Contact notice |
| `CPartnerProfile` | `outreachCampaign` | many-to-one | `COutreachCampaign` | `partnerProfiles` | Ruling 27 |
| `CSponsorProfile` | `outreachCampaign` | many-to-one | `COutreachCampaign` | `sponsorProfiles` | Ruling 27 |

Fifteen links, all many-to-one, none `hasOne` — the cardinality that has
twice silently moved a record off its owner is not used anywhere here.

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
**review screen** (§ 3.5) moves a record to Qualified with the reviewer's
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

One package, `outreach/`, in the house shape: `service.py` (the CRM logic
and the field whitelists), `router.py` (endpoints, the team gate, the
`_crm_failure` mapping, every mutating action through `record_action`),
`frontend/` (vanilla JavaScript, no build). Gated by `OUTREACH_ENABLED`
(off) and `OUTREACH_ALLOWED_TEAMS` (default Marketing Admin Team, the same
team as Submission Admin, matching ruling 13's sign-off team). Mounted at
`/outreach`; portal tile *Prospect Marketing*.

Every campaign kind runs the same five steps; only step 4 differs.

1. **Create.** A marketing user names the campaign, picks the kind, sets
   the window, writes the brief (the shared rich-text editor), and sets the
   selection rule from the screen's choices. The screen offers only the
   choices the kind allows (§ 3.2–3.4); the rule is saved as JSON the
   application owns plus its sentence in `selectionSummary`.
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
`POST /api/outreach/postal/events` on the web process, signature-verified,
otherwise unauthenticated. A returned-to-sender event sets the touch to
`Returned` with `returnedAt`, and the prospect record's `addressStatus` to
`Dead` with `addressDeadAt`. The rung is untouched; the record is selectable
again the moment an import row brings a new address (the import resets
`addressStatus` when the address changes). Delivered events set `Delivered`.
The campaign screen counts Returned separately from the silent.

**The QR code** carries the touch's `scanToken` only. The token resolves
server-side to the touch, the prospect record and the campaign, so the card
carries neither id in the clear. Rendered by the application as a PNG at
`GET /p/{token}/qr.png` for the vendor's template to fetch, or inlined as a
data address in the merge variables — whichever the chosen vendor's template
supports; the dry-run client writes both.

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
(§ 3.5) for staff to paste into the notice they design and send there
(mailing-list ruling 6). The touch moves to `Sent` when the mailing-list
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
touch is a row on the call screen (§ 3.5), filtered to the caller's own
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

### 3.5 The screens

All under `/outreach`, one page with four tabs, each a grid in the house
shape (full width, sortable, searchable, right-click menus, every button
always clickable and explaining itself on a missing input or grant):

- **Prospects** — every `CProspect`, filter chips by rung, side exit, entry
  door and batch; *Import…* (state filing or list; plan, then apply);
  row actions *Qualify* / *Unqualified* (the ruling-18 review, with the note
  required), *Do Not Contact*, *Not the same company* (reverses Already
  known), *Open the Company* / *Open the Contact* when promoted. A detail
  popup shows the record, its touches and its promotion links.
- **Campaigns** — every `COutreachCampaign`; *New campaign*; the campaign
  page with the brief, the rule builder, *Build the list*, *Sign off and
  run*, the live counts, the touch grid, and the **links card**: the
  addresses this campaign owns, each with a Copy button, derived from
  `APP_BASE_URL` and never stored —
  `/client-intake/?campaign=<id>`, `/info-request/?campaign=<id>`,
  `/webinars/<slug>?campaign=<id>` when an event is linked, and for a
  postcard the note that its link rides in each card's QR code.
- **Calls** — the call screen of § 3.4, across every Running call
  campaign the user may see.
- **Review** — the Unverified queue of § 2.3, which is the Prospects grid
  pre-filtered; kept as its own tab so the review has a home.

Every date and time on these screens is the shared `CBMDateTime` control;
the brief is the shared `CBMRichText` editor; the page loads `busy.js`
first, carries `<meta name="cbm-org">` and uses the `{{org}}` and
`{{abbr}}` tokens; no page width cap.

### 3.6 The word — campaign is ours, notice is Constant Contact's

Three things could be called a campaign: ours, EspoCRM's native entity
(hidden, § 1.1), and a Constant Contact send. **Decided:** in this
application an **outreach campaign** is the `COutreachCampaign` record and
the word *campaign* on screen means that and nothing else. A Constant
Contact send is a **notice**, the word the mailing-list plan already uses
for it (§ 4.2 there: "one notice about the event"; the field
`noticeCampaignId`). One correction follows for that plan's unbuilt Phase
D: its staff action reads *Link a campaign* and must read **Link a notice**
when built. Recorded here so the two arcs do not ship two meanings.

---

## 4. The postcard landing page — `/p/{token}`

A public route on the web process, gated by `OUTREACH_LANDING_PUBLIC`
(default false; off, the route 404s). Package `outreach/landing.py` plus
`outreach/landing_frontend/`; the page is a route, not a static file, for
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
  `/info-request/?prospect=<id>&campaign=<id>`.
- **Request a mentor** → saves the response, then opens
  `/client-intake/?prospect=<id>&campaign=<id>`.
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
The server lookup the standard forms call, `GET /api/outreach/prospect/{id}`,
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
notes line saying the link did it. Each public form gains two optional
schema fields, `prospect_id` and `campaign_id` (32 characters at most,
`Optional[str]`), two hidden inputs filled from `?prospect=` and
`?campaign=`, and a courtesy banner from the name-only lookups. Nothing
here is load-bearing: a missing, stale or forged id leaves the form exactly
as it is today.

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
7. **The relabel** (§ 1.9): `merge_contact_type` and `merge_company_type`
   append the door's type and remove `Prospect`.
8. A notes line on the relationship record: *"Arrived through the campaign
   <name>."* — the only record that the link did it, since an application
   write and a hand edit are indistinguishable in the CRM history.

**Per door:**

| Door | Relationship record | Rung evidence written | Type appended |
|---|---|---|---|
| client-intake | `CEngagement.outreachCampaign` | none stored — Candidate is read from the engagement | Client (Contact and Company) |
| info-request | `CInformationRequest.outreachCampaign` | `cFunnelStage=Warm Lead` on the Contact, and on the Company it created, advance-only (ruling 17) | none — Prospect stays until a relationship |
| event registration (`/webinars/{slug}?campaign=`) | `CEventRegistration.outreachCampaign` | `cFunnelStage=Warm Lead` on the Contact, advance-only; `Opportunity` when attendance is later recorded (§ 6) | none (D-09 stands) |
| partner | `CPartnerProfile.outreachCampaign` | — | Partner |
| sponsor | `CSponsorProfile.outreachCampaign` | — | Sponsor |
| volunteer | — (no campaign reaches it; ruling 26 names the intake forms) | — | — |

**The dormant-client campaign (ruling 25)** is a selection rule in § 3.3
and § 3.4, never a rung: a former client who responds submits the intake
form as today, which creates a new engagement on the existing client
profile; the engagement carries the campaign id, and that is the whole
attribution.

**The referring partner and the campaign coexist** on an engagement: two
different links, two different notes lines. A partner's intake link carries
no campaign; a campaign link carries no partner. If a chapter ever gives a
partner a campaign link, both are written.

**Where the type question for the information request stands.** Today
that door creates its Company typed `Client` with `cClientStatus=Prospect`
("nearest fit", from before a Prospect type existed on Companies). Ruling
21's vocabulary wants a Company typed `Prospect`. The plan recommends the
door create it typed `Prospect` once the option exists, with
`cClientStatus` untouched, so the relabel at conversion reads the same for
every door — question 7, because it changes a live door's behaviour.

---

## 6. Reporting

**Three reads, one rule.** Every funnel number comes from
`outreach/reporting.py`, so every screen agrees (the active-client-count
discipline).

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
  ship as built-in metrics on a new Analytics page *Prospect Marketing*, and
  admins can derive more without a deploy. The campaign page shows its own
  row of the same numbers from the shared module.
- **The funnel** is a union across three entities with a dedupe rule and
  an engagement-derived override; the builder cannot express it, so it is a
  **built-in computed metric** (`analytics/computed.py`, the operational
  metrics' home), shape `rows`, under the org-wide key. It renders on the
  same Analytics page and as the campaign tab's header strip.
- **Per-campaign dashboards** would need a new dashboard scope (one per
  record type is the rule). Not in this arc; the campaign page's own counts
  serve.

**Opportunity** is written when attendance is recorded on a
`CEventRegistration` whose Contact is typed Prospect, whatever the
attendance source — Phase 6a's Zoom pull (off everywhere) or a manual
check-in. No new attendance work is in this arc; the write hangs off the
existing attendance update.

**Stale.** A worker sweep, nightly, moves a prospect record with no stage
change for `OUTREACH_STALE_DAYS` (default 180) and no Planned touch to
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
- `coutreach-entities-crm-handoff.md` + `scripts/plans/coutreach-entities.json` — the three entities, their fields, all fifteen links of § 1.5 (the five relationship-record links are additive and cheap now, and Phase 2 then needs no CRM change), the four stage fields, the `Prospect` option on `cCompanyType`, and `scripts/migrate_outreach_roles.py` for the grants: the intake API role (`CProspect` create/read/edit, `COutreachTouch` create/read/edit, `COutreachCampaign` read, and the new Contact/Account fields), the Marketing Admin Role (all three: create/read/edit at `all`, **Assignment Permission `all`** — a role that creates a record the application leaves unassigned needs it, the presenters finding).

**Flags:** `OUTREACH_ENABLED`, `OUTREACH_ALLOWED_TEAMS`, `OUTREACH_LANDING_PUBLIC`, `POSTAL_PROVIDER` (`dryrun`), `POSTAL_API_KEY`, `POSTAL_WEBHOOK_SECRET`, `POSTAL_TEST_MODE`.

**Build:** the `outreach/` package with the Prospects and Campaigns tabs; the state-filing import (upload, plan, apply) with the already-known check; the postcard kind end to end — selection, sign-off, the worker run, `core/postal.py` with the dry-run client and the chosen vendor's adapter, the callback; the landing page and `forms/prospect_response/`; the SMS tick on the five intake forms and the event registration form (true-only, beside the marketing opt-in, wording naming texts); the two hidden ids on the client-intake and info-request forms, **carried and ignored** at delivery (Phase 2 honours them); the funnel read's first version for the campaign page's counts. Migration: one Postgres table for the import ledger (batch, row hash, result) so a re-upload of the same file is a no-op.

**Live verification, on crm-test, as Mark Marketing (Marketing Admin Team), then once more as the org-wide key where stated:**

1. `GET /api/v1/CProspect?maxSize=1`, `COutreachCampaign`, `COutreachTouch` as the org key → HTTP 200 (a 403 is a missed grant).
2. Sign in as Mark Marketing; the portal shows *Prospect Marketing*; open it. Import a five-row CSV: one row naming an existing sandbox client company and its postal code, one with a website, one with an email, two with address only. The plan shows: 1 Already known, 1 Company typed Prospect to create, 1 Contact typed Prospect to create, 5 prospect records; apply; the Prospects grid shows five rows at Qualified, one flagged Already known with the company linked.
3. Re-upload the same file: the plan shows nothing to do.
4. New campaign, kind Postcard, rule Qualified + usable address; *Build the list* → 4 Planned touches (the Already known row absent); *Sign off and run* shows 4 pieces and the dry-run cost; confirm. The worker log shows 4 pieces accepted by the dry-run client; the touches read Sent with a `scanToken` each; the preview artefacts show the QR.
5. *Build the list* again on a second postcard campaign → 0 (ruling 14).
6. Signed out, open `/p/<token>` from touch 1: the page shows that row's business name and mailed address, nothing else; the touch now reads Scanned with `firstScannedAt`; the prospect record reads Lead. Reload: `scanCount` 2, `firstScannedAt` unchanged.
7. On that page enter a name, an email the sandbox does not hold, both ticks, press *Just update my details*: a `prospect-response` row delivers; a Contact typed Prospect exists with `cMarketingOptIn`, `cSmsOptIn`, `cFunnelStage=Lead`, `cEntryStage=Qualified`, `cOutreachCampaign` set; the prospect record's `promotedContact` points at it.
8. On touch 2's page enter a website whose host matches an existing sandbox company under a **different** name: a new Company typed Prospect is created (name match is by name; a different name is a different company). On touch 3's page enter the name and website of an existing company whose stored website differs: the row holds as `held_company` in Submission Admin, and *Same company* delivers it against the existing record with `Prospect` **not** appended.
9. Post a dry-run *returned* event to the callback for touch 4: the touch reads Returned, the record's `addressStatus` reads Dead, the rung is unchanged; the campaign's counts show 1 returned.
10. Press *Request a mentor* on touch 1's page: the client-intake form opens with the business name and address prefilled, the banner names the campaign, the typed name and email are filled from the browser; submit; the engagement is created **as today, with no campaign on it** (Phase 2 owed).
11. Open the client-intake form with the campaign id altered: no banner, the form works.
12. As `sally.sponsor` (no team seat): `/outreach` answers 403 naming the Marketing Admin Team.
13. Tick the SMS box on the public client-intake form and submit: the Contact reads `cSmsOptIn` true; submit once more unticked for the same email: still true.
14. Then, on a morning after a reset with no release test running: seed and re-baseline the sandbox so the three tables survive the night.

**Not before the first real card:** question 2 (the filter's file), question 4 (the vendor account — Doug opens it), question 5 (the card itself). The first real run is 25–50 pieces, signed off by Doug, with `POSTAL_TEST_MODE=false` set at `/setup` for that run only.

### Phase 2 — the doors honour the ids

**CRM change:** none (the links shipped with Phase 1's handoff).
**Flag:** none — dark by nature (no id, no change) and feature-detected per link from metadata, so a CRM without the links drops the attribution with a logged note.

**Build:** § 5 in the five orchestrators (client intake, info request, event registration, partner, sponsor); `merge_contact_type` and the relabel rule in `core/crm_upsert.py`; the campaign banner on the forms and the event page; the hidden ids on the partner and sponsor forms and the event page's registration form; the information request's Company typed Prospect (question 7); the notes lines; the campaign page's *responded* and *converted* counts.

**Live verification, as Mark Marketing for the reads and signed out for the forms, on crm-test:**

1. A card's *Request a mentor* through to delivery: the engagement carries the campaign and the notes line; the Contact and Company created by it carry `cOutreachCampaign`; the prospect record's promotion links are set; the Contact's type reads `Client` with no `Prospect`; the Company's type reads `Client` with no `Prospect`.
2. The same person again through `/info-request/?campaign=<a second campaign>`: the information request carries the second campaign; the Contact keeps the first (ruling 27).
3. A Contact typed Prospect from Phase 1 registers through `/webinars/<slug>?campaign=<id>`: the registration carries the campaign, the Contact's `cFunnelStage` reads Warm Lead and its type is unchanged (D-09).
4. A Company typed Prospect submits the partner form: `cCompanyType` reads `Partner` with no `Prospect`; the partner profile carries the campaign.
5. An altered campaign id on each form: the record is created, no campaign, a warning in the web log.
6. The Client Administration popup opens the engagement from step 1 and shows the notes line; Submission Admin shows the `prospect-response` rows with their references.

### Phase 3 — lists, review, calls

**CRM change:** none.
**Flags:** `OUTREACH_CALLS` (the Calls tab and the call kind), inside `OUTREACH_ENABLED`.

**Build:** the list import with `list_source`; the Review tab with *Qualify* and *Unqualified* (note required, reviewer stamped); *Do Not Contact* and *Not the same company*; the call kind: rule, call list, the recording screen with the three outcomes and *Call again*; `Declined`; the nightly Stale sweep with `OUTREACH_STALE_DAYS`; the touches-by-campaign and entry-rung metrics on the new Analytics page.

**Live verification, as Mark Marketing, and as a second non-admin on a team the campaign names for the calls:**

1. Import a list of four rows (one with a phone): four records at Unverified in the Review tab; *Qualify* two with notes; *Unqualified* one; the fourth stays.
2. New campaign, kind Call, rule Qualified + phone held: *Build the list* → the rows with a phone (the Unverified one absent); sign off.
3. As the second user on the campaign's team: the Calls tab lists the rows; record *No answer* on one (Done; *Call again* plans a fresh row), *Interested* on another (the record reads Lead), *Declined* on the third (side exit Declined, absent from every later build).
4. As a user on no team the campaign names: the Calls tab is empty with a message naming the team.
5. Set `OUTREACH_STALE_DAYS=0` at `/setup`, run the sweep from Operations as a dry run then apply: untouched Qualified records read Stale; Lead records with a scan today do not. Reset the setting.
6. The Analytics page shows touches by campaign and entry rung per door matching the grids.

### Phase 4 — email campaigns and the funnel

**CRM change:** none.
**Flags:** `OUTREACH_EMAIL` (the email kind), inside `OUTREACH_ENABLED` and the mailing-list connection.

**Build:** the email kind: rule (opted-in Contacts; the dormant-client term), the per-campaign named list push through `core/mailing_sync.py` generalised to several lists, the links card, *Mark as sent*, and the Phase D read when that exists; the funnel computed metric and the campaign tab's header strip; `Opportunity` on attendance.

**Live verification, as Mark Marketing, on crm-test with its own Constant Contact account (the mailing-list plan's ruling A):**

1. New campaign, kind Email, rule Prospect + opted in: the list shows only Contacts with `cMarketingOptIn` true and a usable address; a Contact holding an email without the tick is absent (ruling 19).
2. Sign off: a Constant Contact list named after the campaign appears with exactly those addresses; the standing list is unchanged.
3. The dormant-client rule with N=0 lists the sandbox's closed-engagement clients with the tick; N=3650 lists none.
4. The funnel on the Analytics page: counts per rung add up to the union of the three grids with the dedupe rule, checked against the CRM's own list counts by hand once.
5. Record attendance on a registration whose Contact is typed Prospect: the Contact reads Opportunity.

### Phase 5 — deferred, named so they are not forgotten

Not planned, no dates: the partner-file import (ruling 23); text campaigns (`cSmsOptIn` exists from Phase 1; the kind, a vendor and a ruling do not); a second-card campaign (ruling 14 waits for a measured response rate; the Stale exit is its entry point); a watched Drive folder or a posting endpoint for the outside filter (question 2); a dashboard scope per campaign; Phase D of the mailing-list plan feeding email touches.

---

## 8. The open list — each item answered or put to Doug

From `prds/prospect-marketing-plan.md`, *Open after this session*:

| Item | Status | Where |
|---|---|---|
| Rung 1's name | **Put to Doug** — the plan stores `Unverified` and recommends it; the enum value is a one-word change before the handoff is applied | Question 3 |
| Where the rung continues after promotion | **Answered:** a field on Contact and Account, because two sources never have a prospect record | § 1.8 |
| The call campaign's recording screen | **Answered:** the Calls tab, three outcomes, *Call again*, the warning that an unrecorded call reads as never contacted | § 3.4 |
| Retention | **Answered as a draft:** Stale after `OUTREACH_STALE_DAYS` (180), never deleted, a `/setup` setting | § 6 |
| Attendance evidence for Opportunity | **Answered:** written off the existing attendance update whatever its source; no new attendance work | § 6 |
| The campaign entity's shape | **Answered:** § 1.3, § 1.5, § 3.5; the QR carries a token that resolves to both ids; which forms honour the id is § 5's table; the partner link and the campaign link coexist as two links | §§ 1, 3, 5 |
| The Prospect-to-type relabel | **Answered:** one rule in the two merge functions; every door inherits it | § 1.9, § 5 |
| Chapter-network vocabulary | **Answered:** every name checked in § 1.10; `externalReference` and `State filing` replace the state-specific words | § 1.10 |
| What the outside filter delivers, and how | **Put to Doug** | Question 2 |
| The postcard offer and creative | **Put to Doug** — outside this repository; the template's size and QR placement constrain `postcardSize` and the vendor template | Question 5 |
| Which address is mailed | **Put to Doug with question 2** — the import takes one mailing address per row; if the filter delivers both, the plan mails the business's own address, not a registered agent's | Question 2 |

Two items this plan added: the entity choice (question 1) and the vendor
(question 4); who makes the calls (question 6) and the information
request's company type (question 7).

---

## 9. Questions for Doug

Each is written on the recommended answer; a "yes" to all seven changes
nothing above.

1. **Custom entities, or EspoCRM's own Lead and Campaign?** Recommended:
   custom (§ 1.1). Cost: three entities and fifteen links in the standard,
   and the native `campaign` link stays unused. The alternative's cost: core
   grants, tabs and a required-flag change on every chapter's CRM, two of
   them unverified.
2. **What does the outside filter deliver — the columns, where it lands,
   how often — and which address when a row carries two?** The plan takes a
   CSV upload on the Prospects screen with the § 2.1 columns and mails the
   business's own address. Nothing is built for the delivery path until this
   is answered; the upload works for any answer.
3. **Rung 1's stored name: `Unverified` (recommended) or `Unqualified`?**
   `Unqualified` is a terminal reject in every surveyed CRM and is also the
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
| Version | v0.1.1 — a plan, nothing built; seven questions open; **superseded in part by the Campaign Management requirements, v0.2 owed** |
| Last Updated | 10-14-26 21:55 |
| Prepared by | Claude (Claude Code), for D. Bower |
| Session | 2026-10-14 planning session, from `prompts/prospect-marketing-build-plan-prompt-v0.1.md` |
| Related | `prds/prospect-marketing-plan.md` (the rulings), `prds/mailing-list-and-event-sponsorship-plan.md` (the notice vocabulary, the push), `prds/chapter-network/crm-update-runbook.md`, `forms/client_intake/orchestrator.py` (the partner-link precedent), `core/crm_upsert.py`, `core/mailing_sync.py` |

### Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1.1 | 10-14-26 21:55 | Claude (Claude Code) | Pointer added at the top: superseded in part by *Requirements — Campaign Management application (10-14-26)* in the plan (CM-1 to CM-11); the sections v0.2 must revise are named there. No section revised. Duplicated date in Last Updated fixed. |
| 0.1 | 10-14-26 17:34 | Claude (Claude Code) | First version: the record model in Entity Manager vocabulary (three custom entities, fifteen links, the stage fields, the relabel), the two import doors, the three campaign kinds on one engine, the landing page as a sixth form kind, conversion per door, reporting, five phases with handoffs and verification scripts, the open list, seven questions. Finding recorded: the native marketing module is hidden on crm-test and the org key 403s on Lead and Campaign. |
