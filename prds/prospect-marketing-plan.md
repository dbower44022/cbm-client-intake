# Prospect Marketing — plan v0.6.1 draft (2026-10-14)

**STRAWMAN — not an approved plan.** Sections marked *Doug's rulings* record
decisions already made in the 2026-08-11 session. Everything marked **PROPOSAL**
is my recommendation awaiting your call, not a settled decision. The
**Discussion in progress** sections at the end record the 2026-09-01 and
2026-09-02 sessions on funnel stages — ideas only, explicitly **not
decisions**, pending further discussion of the process. **The 2026-09-02
section supersedes the two stage drafts in the 2026-09-01 section**: Doug
tabled his own funnel diagram, and that is now the ladder under discussion.
**The 2026-10-13/14 section at the end records the source-by-source walk
against that ladder and nineteen new rulings (9–27)**; where it conflicts
with the proposals above — the `CProspect`-as-funnel storage section, the
`source` ruling, the reach idea — the rulings win and the earlier text is
kept only as the record of what was proposed.

Scope: manage prospects from **all lead sources**, including those with no email
or phone, and reach the latter by **postcard** carrying a per-prospect QR code
that leads to a personalized landing page and then into the existing intake
forms.

Status: **NOT BUILT.** No code, no CRM entity, no vendor account. The
process is ruled end to end (section of 2026-10-13/14) and **the build plan
is written: `prds/prospect-marketing-build-plan.md` (v0.1, 2026-10-14)** —
the record model, the doors, the campaign engine, the landing page,
conversion, reporting, five phases with their CRM handoffs and verification
scripts, and seven questions for Doug. **The Campaign Management application
is defined** (section *Requirements — Campaign Management application
(10-14-26)*, CM-1 to CM-11, the same evening) and **the build plan is
revised against it (v0.2, 10-14-26 evening)**. This document stays the
record of the rulings and the requirements; the build plan is where the
build is described.

---

## Why postcards are the primary channel, not a fallback

This is the finding that justifies the whole arc, and it is measured rather than
assumed. From `research/registry-enrichment/enrichment-findings.md` (v1.0,
2026-07-30, 201 of 201 records scored):

| Measure | Pool-weighted |
|---|---|
| Strong-match rate (found verified online contact info) | **2.03%** |
| Actionable **and** in the Cuyahoga/Lake service area | **~1.1%** |
| False-positive rate (plausible candidate that failed verification) | **96.94%** |

So for registry-sourced prospects, roughly **99 in 100 cannot be reached by
email or phone at all**, and of the candidates that *look* findable, 19 in 20 are
the wrong business. Enrichment is not a viable acquisition channel here. Mail is.

The corollary matters for the design: **"no email, no phone" is the normal state
of a prospect record**, not an exception to handle. Any model that treats email
as the identity key fails on the majority of the pool.

---

## Doug's rulings (2026-08-11)

1. **An external process filters the raw pool.** Only the top **100–500 per
   month**, already judged high quality, enter this process. The app does not
   score or qualify prospects — it receives a filtered list.
2. **Vendor is Lob or PostGrid**; pricing between them is a wash.
3. **Each postcard carries a customized QR code identifying the prospect.**
   Scanning opens a personalized page so the recipient corrects rather than
   types.
4. **The landing page is a custom intake form** that displays what CBM already
   holds and asks the recipient to correct/update their business and contact
   information.
5. **It then offers two buttons — Info Request and Request a Mentor** — which
   send the recipient to the *standard* intake form, **passing the prospect id**
   so the form can retrieve everything already known and minimize data entry.
6. **From there the workflow is identical to today.** The only difference is the
   tracked source: **`"State New Business Filing-Postcard"`** instead of
   `"CBM Website"`.
7. **Single source of truth is a hard requirement.** Doug is hesitant to store
   prospects in a separate app-side store, because other lead sources will
   arrive and should not fragment.
8. **Contact/Company pollution is given equal weight** to ruling 7 — it is a real
   cost, not an objection to be argued away.

---

## The storage decision — a CRM entity, not an app store, not Contact

Rulings 7 and 8 pull in opposite directions only if the choice is framed as
"app-side store vs Contact." It isn't. A **dedicated EspoCRM entity `CProspect`**
satisfies both: it lives in the CRM (single source of truth, serves every future
lead source), while Contact and Company stay clean until a real human responds.

**This is the established pattern in this codebase, twice over.**
`CInformationRequest` is explicitly *"a dedicated, self-contained record of the
request… ON TOP OF the Contact"*, and `CIntakeSubmission` is a dedicated receipt
entity. Neither overloads Contact. Prospects are the same shape of problem.

Four mechanical reasons **not** to create Contact/Account at mail time:

1. **No dedup key.** `core/crm_upsert.find_create_or_fill` matches Contacts on
   **email**. Prospects have none. The natural key — the Ohio SOS document
   number — has no home on Contact.
2. **Contact is a person; a filing is a business.** The enrichment data shows
   `associates` is frequently a law firm, a formation service, or (doc
   202616605274) literally an email address in the `agent_name` field. There is
   often no reliable human to name.
3. **Double-record risk at conversion.** A prospect responds with an email CBM
   never held → the existing find-or-create-by-email path builds a **second**
   Contact, leaving the cold record and the real one coexisting and unlinked.
   This is the `CClientProfile` duplicate failure in a new costume (v0.185.0).
4. **Campaign state has nowhere to live.** QR token, mail-piece id, delivery
   status, scan timestamp, response state and suppression flags do not belong on
   Contact, and all of them need a home.

`CProspect` also carries a `source` field, which is what actually delivers "all
sources": registry filings, purchased lists, event scans, partner referrals and
walk-ups land in **one** entity, one worklist, one set of suppression rules, and
convert through one path.

**Cost, stated honestly:** this is a CRM-team build and joins the prerequisites
in `OPEN-ITEMS.md`. Per the repo's feature-detect convention the app ships dark
and activates when the entity exists, so it does not gate the code.

---

## ⚠️ Ruling needed — `source` currently means two different things

Ruling 6 asks for source `"State New Business Filing-Postcard"` instead of
`"CBM Website"`. That is an **arrival channel**. But in the code today:

- `forms/info_request/orchestrator.py` sets
  `payload["source"] = source or sub.how_did_you_hear` — so on the website form
  `source` carries **the user's answer to "how did you hear about CBM?"**
- `cinformation-request-entity.md` documents the field as *"How they heard about
  CBM (`how_did_you_hear`)"* — the user-answer meaning.
- `core/receipts.py` sets the receipt's `source` from `how_did_you_hear` too.
- But `forms/info_email/orchestrator.py` already sets `SOURCE = "Email"` — the
  **channel** meaning.

So the conflation predates this work, and the two meanings are already mixed in
live data. They are orthogonal: a postcard recipient can still answer "how did
you hear about CBM" with "a friend."

**PROPOSAL:** `source` becomes strictly the **arrival channel**
(`CBM Website` / `Email` / `State New Business Filing-Postcard` / …), and
`how_did_you_hear` stays its own separate field and stops being written into
`source`. Cheap now, expensive later once postcard data is mixed in.

**This changes existing website-form behaviour**, so it needs your explicit call.
The alternative — a new `channel` field alongside `source` — leaves historic data
untouched but adds a field and leaves `info_email` inconsistent.

---

## The flow

```
external filter → CSV (100–500/mo)
        ↓
  import review  ──→ suppression check ──→ CProspect (source, token, status=Queued)
        ↓
  drop approval → Lob/PostGrid → postcard, QR = /p/<token>
        ↓
  scan (logged on its own, whether or not they submit)
        ↓
  /p/<token> — personalized page: known business + address shown, editable;
               asks for the email/phone CBM lacks
        ↓
  [Request Information]        [Request a Mentor]
        ↓                              ↓
  /info-request/?prospect=<token>   /client-intake/?prospect=<token>
        ↓                              ↓
        └──── standard form, prefilled from the prospect ────┘
                            ↓
        existing orchestrators, unchanged, with
        source = "State New Business Filing-Postcard"
                            ↓
        Contact + Account + CInformationRequest / CClientProfile + CEngagement,
        linked back to the CProspect → status = Converted
```

**A scan that never submits is still signal.** It proves the piece was delivered
and the recipient was interested enough to scan. Logged independently of submit,
and it is the only per-piece delivery evidence short of vendor tracking.

---

## Components to build

### 1. `CProspect` — CRM entity (CRM-team handoff)

Written up separately as `cprospect-entity.md` in Entity Manager vocabulary if
this plan is approved. Sketch:

| Field | Type | Notes |
|---|---|---|
| `name` | varchar (req) | Business name |
| `docNumber` | varchar | Ohio SOS document number — the stable natural key |
| `source` | enum | `State New Business Filing` / `Purchased List` / `Event` / `Partner Referral` / `Other` — the prospect's **origin** |
| `prospectStatus` | enum | `Imported` / `Suppressed` / `Queued` / `Mailed` / `Scanned` / `Responded` / `Converted` / `Undeliverable` / `Declined` |
| `token` | varchar | QR token — unguessable, indexed |
| `mailingStreet/City/State/Zip` | varchar | The mailing address actually used |
| `contactName` | varchar | Owner/associate name where known |
| `email`, `phone` | varchar | Empty at import; filled by the landing page |
| `formationDate` | date | |
| `mailingBatch` | varchar | e.g. `2026-09 Cuyahoga` — see the campaign note below |
| `mailedDate` | datetime | |
| `mailPieceId`, `mailProvider` | varchar | Vendor's per-piece id, for tracking |
| `deliveryStatus` | enum | From vendor callbacks |
| `scannedAt` | datetime | First scan |
| `scanCount` | int | |
| `respondedAt` | datetime | |
| `suppressed` | bool | |
| `suppressionReason` | enum | |
| `description` | text | Raw import row as JSON — the audit trail |
| `convertedContact` | link → Contact | Set at conversion |
| `convertedCompany` | link → Account | Set at conversion |

**PROPOSAL — no `CCampaign` entity in v1.** A `mailingBatch` varchar is enough to
group a drop and report on it. A full campaign entity is a second CRM build for
value v1 doesn't need. Revisit if you want per-campaign creative/cost tracking.

### 2. `/p/<token>` — the personalized landing page (public)

New public surface — the first one since the intake forms. Vanilla HTML/JS, no
build step, `busy.js` first per convention.

- Shows business name, mailing address and formation date, all **editable**.
- Asks for the contact name, email and phone CBM lacks — the actual point.
- Two buttons: **Request Information** / **Request a Mentor**.
- On click: save corrections to the `CProspect`, then redirect to the standard
  form with `?prospect=<token>`.
- Per convention: **both buttons always enabled and visible**, validating on
  click ([[buttons-never-disabled-validate-on-click]]).

**Token security.** Opaque and unguessable — ≥10 chars from `secrets`, ~50 bits,
excluding ambiguous glyphs since it may be typed from the card. Rate-limit `/p/`
and the prefill endpoint. The page exposes only the business name and mailing
address already printed on the card the holder is looking at, so exposure is
bounded — but tokens must not be enumerable, or the whole prospect list becomes
harvestable.

### 3. Prefill on the standard forms

**Neither form supports prefill today** — there is no query-param or token
hydration in `forms/client_intake/frontend/app.js` or
`forms/info_request/frontend/app.js`. Net-new:

- `GET /api/prospect/{token}` → the known fields (public, token-gated,
  rate-limited).
- Both forms hydrate from it when `?prospect=` is present.
- The token rides through submit so the orchestrator can stamp the source and
  link the conversion back to the `CProspect`.

### 4. Source plumbing

- **info-request:** already threaded — `orchestrator.run(..., source=...)`
  exists. Pass the value.
- **client-intake:** no `source` concept at all. Needs adding.
- **`core/receipts.py`:** `_receipt_fields` derives `source` from
  `how_did_you_hear`; an explicit source must win. Depends on the ruling above.

### 5. Mail provider

`core/mail_provider.py` — thin interface, `LobClient` first, PostGrid adapter
behind the same shape.

**Recommendation: Lob**, on non-price grounds since cost is a wash. Its `test_`
sandbox lets the entire pipeline be built and exercised without printing
anything, which matters more than usual here because every bug costs postage.
Both support per-piece QR through HTML templates with merge variables, address
verification and NCOALink.

**QR rendering:** Lob fetches template assets server-side, so a public
`GET /p/<token>/qr.png` endpoint is the simplest path; embedding a data URI per
piece is the alternative if we would rather not expose a second public route.

**Flags:** `PROSPECTS_ENABLED`, `MAIL_PROVIDER`, `LOB_API_KEY`. Sends run on the
**worker**; landing pages on **web**. Mirroring `espo_dry_run`, the provider
**defaults to dry-run** — postage is never spent by accident, and a drop in
dry-run produces the full artifact set for review without mailing.

### 6. `/prospects` — staff surface

**PROPOSAL:** its own package + portal tile gated to Marketing Admin Team
(matching `/ops`), following the house `service.py` + `router.py` + vanilla-JS
shape. Import review, suppression, batch build, drop approval, response
tracking. Every mutating action through `core/action_log.py` per convention.

---

## PROPOSALS awaiting your call

1. **Suppression rules** — exclude a prospect when: already a client or contact
   (address/name match), mailed within the last **6 months**, returned
   undeliverable, or explicitly do-not-mail. An undeliverable return kills *the
   address*, not the prospect — it stays available if a better address arrives.
2. **Approval gate** — a drop requires explicit human sign-off before it spends
   money, showing piece count and estimated cost. Marketing Admin Team.
3. **Cadence** — **one card per prospect in v1**, no follow-up sequence. Add
   sequences once there is a measured response rate to justify them.
4. **Import schema** — the columns from `enrichment-sample-201.csv` (`doc_number`,
   `business_name`, `agent_*`, `filing_*`, `associates`, `effective_date`) as
   the starting contract, plus whatever the filter adds. Needs agreeing with
   whoever runs the external filter.
5. **Which address gets mailed** — the filing address and the agent address
   differ, and the agent is often a commercial service. **Proposal: mail the
   filing address**, since the agent address reaches a registered-agent mail
   drop, not the business. The external filter may already resolve this.

---

## Open questions

- **What does the external filter deliver, in what format, on what cadence?**
  A CSV drop into Drive, an API, a manual upload?
- **What does the postcard actually offer?** Ruling: "free services." The
  landing page copy and the card creative both depend on the specific offer.
- **Who designs the card?** Creative is outside this repo, but its dimensions and
  the QR placement constrain the template.
- **Does an undeliverable return feed back automatically?** It does with Lob or
  PostGrid; it does not with a VistaPrint CSV upload. This is a real argument for
  an API vendor beyond convenience.

---

## Verification (planned)

- Unit: token generation and uniqueness, suppression rules, import dedup on
  `docNumber`, source stamping through both orchestrators, receipt source
  precedence.
- Stub-harness UI loop for the landing page and prefill
  ([[sessions-frontend-stub-harness]]).
- Provider in dry-run: a full drop end to end, artifacts reviewed, zero postage.
- Live on crm-test as a **real non-admin** Marketing Admin Team member (admins
  bypass ACL), then one small real drop — 25–50 pieces — before a full month.

---

## Out of scope (future candidates)

- Prospect scoring or qualification — the external filter owns this (ruling 1).
- Follow-up sequences and multi-touch campaigns.
- A `CCampaign` entity with creative and cost tracking.
- Email/SMS channels for prospects who do have contact details.
- Attribution reporting beyond per-batch response rate (an Analytics page later).

---

## Discussion in progress — funnel stages (2026-09-01, no decisions yet)

The 2026-09-01 session widened the scope from "postcards to registry filings"
to **a marketing process that takes prospects from every source and moves them
through one funnel**. What follows is the state of that discussion. Nothing in
this section is decided; Doug wants further, more detailed discussion of the
process before settling the stage list, and expects the process may need more
status buckets than any draft below.

### Working positions stated by Doug during the session

Recorded because he said them, not as rulings — he may revise them.

- **Every source uses the same stages**, even though sources enter at different
  stages (a state filing enters at the top; a webinar registrant enters part-way
  down).
- **The funnel ends at the form submission.** "Client" is read from the linked
  engagement for reporting, never tracked a second time on the prospect record.
- **The first stage draft (Identified / Reached / Engaged / Requesting) was
  not granular enough.**
- **Qualification is not one thing.** A real, in-area business with no email,
  phone or business type is *not* as qualified as one with all three, and the
  difference drives which campaign a prospect belongs to.
- **Campaign membership must be reportable.** Segmenting analytics on "has
  email / has phone / …" field-by-field is unworkable; the grouping needs a
  first-class label.

### Ideas on the table

**1. Two axes, not one.** Every model surveyed separates *how far along the
prospect is* (lifecycle stage) from *what we know and can do* (working status /
reach). Mixing them makes a prospect who merely gained an email look as if they
moved a stage. Proposed shape:

- **Stage** — moves forward only, on evidence the system can observe (a mail
  piece accepted, a QR scan, a registration, a form submission). Staff never
  set it by hand. The **entry stage** is stored separately from the current
  stage so per-source conversion reporting stays honest (a source entering
  half-way down will always "convert better" unless the entry rung is visible).
- **Reach level** — a small named set computed from the fields present,
  recomputed whenever the record changes. First cut: *Address only* → *Email*
  → *Phone* → *Known* (named owner + business type). This is the label
  campaigns target and analytics segments on.
- **Campaigns select on stage + reach level**, and each *touch* stamps both as
  they were that day, so a prospect mailed at *Address only* and later emailed
  at *Email* counts once in each segment even though the record has since
  changed. An enrichment hit that adds an email changes the label, and the
  prospect is picked up by the matching campaign on its next run — nobody moves
  them by hand.

**2. Candidate stage ladders.** Two drafts were discussed; neither is adopted.

*Draft A (eight rungs, plain English):* Identified → Qualified → Contacted →
Delivered → Aware → Interested → Conversing → Requesting.

*Draft B (names borrowed from the surveyed models, "Delivered" dropped
because no model treats delivery as a stage — it is a fact about the touch):*

| # | Stage | Meaning | Borrowed from |
|---|---|---|---|
| 1 | Identified | We know the business exists | Nonprofit "Identification"; Marketo "Anonymous" |
| 2 | Qualified | It fits and is worth the effort | Nonprofit "Qualification"; MQL |
| 3 | Contacted | We have made a touch | Salesforce / Zoho "Contacted" |
| 4 | Engaged | They responded in some way | Marketo "Engaged"; HubSpot "Subscriber" |
| 5 | Interested | They took a step toward us | AIDA "Interest"; HubSpot "Lead" |
| 6 | Nurturing | Two-way exchange under way | Salesforce "Nurturing"; nonprofit "Cultivation" |
| 7 | Applied | Form submitted — funnel complete | The Sales-Accepted handoff |
| 8 | Client | Read from the engagement | Neoserra "Client"; HubSpot "Customer" |

Side exits (not rungs; the reason matters more than the rung left from):
**Unqualified**, **Do Not Contact**, **Undeliverable** (kills the address, not
the prospect), **Declined** (they said no — distinct from silence), **Stale**
(no movement for a set period; the re-entry point for re-marketing), **Lost**,
**Junk**.

**3. Qualified = fit, and only fit.** Real operating business (not a
formation-service mail drop), in the service area, not already a client or
contact, not do-not-contact. Ruling 1 above says an outside process applies
this for filings; for the other sources it would be a quick staff review or a
simple automatic check (ZIP in area), with the record showing who or what
cleared it and when. Whether "qualified" should carry more than fit is exactly
what Doug's reach-level point challenges — open.

**4. One prospect record with a business half and a person half**, each
optional, at least one required. A filing enters with only the business half;
a webinar registrant with only the person half; later touches fill the other.
The alternative (separate business-prospect and person-prospect records, linked
when both are known) doubles every report and workflow. **Not yet answered** —
Doug redirected to the stage discussion before ruling.

### Survey of stage models (for reference)

| Model | Stages, in order |
|---|---|
| HubSpot lifecycle | Subscriber → Lead → MQL → SQL → Opportunity → Customer → Evangelist |
| Marketo / Forrester demand waterfall | Anonymous → Known → Engaged → MQL → Sales Accepted → Sales Qualified → Opportunity → Closed Won |
| Salesforce lead status | Open (not contacted) → Working → Contacted → Nurturing → Qualified / Unqualified → Converted |
| Zoho lead status | Not Contacted → Attempted to Contact → Contacted → Contact in Future → Pre-Qualified → Qualified; plus Junk, Lost |
| Nonprofit donor cycle | Identification → Qualification → Cultivation → Solicitation → Stewardship |
| SBDC software (Neoserra) | Pre-client → Client (pre-client activity kept off official reports) |
| AIDA | Attention → Interest → Desire → Action |

Two patterns hold across all of them: (a) a marketing half and a sales half
with a named handoff in the middle — for CBM the handoff is the form
submission, where intake and Client Administration already take over; (b) the
sales tools track *how the contact attempt is going* (not contacted / attempted
/ contacted / nurturing) as a status separate from lifecycle stage, and the
commonest complaint in the practitioner articles is mixing the two.

### Open for the next session (as of 2026-09-01 — see the 2026-09-02 section below for what changed)

- Walk the process end to end, source by source, and see whether it needs more
  status buckets than Draft B — Doug's expectation is that it might.
- Naming family: business-CRM (Lead / Qualified / Nurturing), nonprofit
  (Identification / Cultivation / Solicitation), or plain English.
- Whether reach level is the right second axis, and its levels.
- The one-record-two-halves question (idea 4).
- Then return to the earlier open items: the `source` field ruling, `CProspect`
  storage, and the tension between the `/p/<token>` page and the 2026-08-17
  events ruling that a public page may echo nothing we know about a person.
- Chapter-network note: "Ohio SOS document number" and "State New Business
  Filing" are chapter-specific vocabulary now that the product is
  de-Clevelanded; a `CProspect` build would go through
  `prds/chapter-network/crm-update-runbook.md`, not a one-off handoff.

---

## Discussion in progress — Doug's funnel diagram (2026-09-02, no decisions yet)

The 2026-09-02 session was set up to walk the process source by source
against Draft B. One question in, Doug tabled his own funnel diagram, which
**replaces Draft A and Draft B as the ladder under discussion**. The image is
kept in the repo as `prompts/prospect-marketing-funnel-2026-09-02.png`. The
session recorded the diagram and the first review point, then stopped at the
first open question; the source-by-source walk has not yet been done against
this ladder.

### The ladder as Doug drew it (Doug's, 2026-09-02 — a proposal, not a ruling)

Eight rungs in three colour bands, each band naming who owns the work there.
Definitions transcribed from the diagram.

| # | Band | Rung | Doug's definition |
|---|---|---|---|
| 1 | Prospect Marketing | **Unqualified Prospect** | Companies that have a company name, address and other basic information, but no email address or phone number. They also have NOT been verified to be a running company in an industry segment where CBM offers mentoring (could be a real-estate LLC). |
| 2 | Prospect Marketing | **Qualified Prospect** | Companies where CBM has enriched the company information adequately to know they are a functioning company, has an email or phone number, and knows they are the type of company that might want mentoring. |
| 3 | Prospect Marketing | **Active Prospect** | Companies that have been selected for an active outreach campaign. |
| 4 | Lead Marketing | **Lead** | A prospect who has explored at least one Service (Mentoring, Webinar, Seminar) but NOT registered. |
| 5 | Lead Marketing | **Warm Lead** | A prospect that has registered for at least one Service. |
| 6 | Lead Marketing | **Opportunity** | A company that has consumed a Service, but not Mentoring. |
| 7 | Lead Marketing | **Candidate** | A company that has expressed interest in Mentoring, but not attended a session. |
| 8 | Client Management | **Client** | A company with at least one active mentoring session. |

Two things the diagram settles that the earlier drafts left open, read as
Doug's intent rather than as rulings: the funnel is **company-centric** (every
rung is defined on a company), and the three bands make the ownership handoffs
explicit — Prospect Marketing → Lead Marketing at the first sign of the
company's own action, Lead Marketing → Client Management at the first active
mentoring session. The "funnel ends at the form submission" working position of
2026-09-01 is refined by this: **Candidate** and **Client** sit below the
submission and are read from the engagement (Candidate ≈ an engagement that
exists but has no completed session; Client ≈ an engagement with one), which is
consistent with that position rather than contradicting it.

### First review point (Claude's, 2026-09-02 — recommendation, not adopted)

**The postcard has no home on this ladder as drawn.** *Qualified* bundles three
tests: verified as a running company in a segment CBM serves, an email or
phone in hand, and the right type of company. *Active Prospect* sits below it,
so a campaign selects from the Qualified. But the enrichment study
(`research/registry-enrichment/enrichment-findings.md`) is the reason the
postcard exists: ~99 in 100 filings carry no email or phone and web enrichment
cannot find one. Under the ladder as drawn a filing can never reach Qualified
before it is mailed, so the postcard campaign has nothing to select from. The
postcard is not an outreach *to* the qualified; it is the instrument that
qualifies them, by getting the owner to hand over the email or phone CBM could
not find.

The concrete collapse: two companies share *Unqualified* today — a Houston
formation-service shell that will never want a mentor, and a real Westlake
landscaper CBM simply cannot reach yet. The first is a reject; the second is
exactly who the postcard is for. Different handling, same label.

**Recommendation:** split what Qualified bundles.

- **Qualified = verified fit only** — a running company, in the service area,
  in a segment CBM mentors, not already a client or contact.
- **Reach becomes a separate label** on the record (working name *reach*:
  none / email / phone / both, recomputed whenever the record changes), which
  any campaign can select on. This is the 2026-09-01 "second axis" idea, now
  grounded in the diagram rather than in the surveyed models.
- **Active Prospect becomes campaign membership, not a rung** a company climbs
  to. The postcard campaign selects *Qualified + no reach*; an email campaign
  selects *Qualified + email*; both companies are "Active" while their campaign
  runs, and the same company can be mailed this month and emailed next month
  without moving a rung. Each touch stamps the rung and the reach as they were
  that day, so campaign reporting stays honest after the record changes.

This keeps all eight of Doug's names and all three bands; it changes what two
of the top three rungs mean.

**The question put to Doug, unanswered when the session paused:** does the
split hold, or should email-or-phone stay inside Qualified with the postcard
campaign selecting directly from the Unqualified rung instead?

### Noted for the walk, not yet raised (Claude's)

Held back so the discussion stays one question at a time; each is a candidate
missing or ambiguous bucket to test when the source-by-source walk resumes.

- **Where an inbound info@ email or an Information Request lands.** It is not a
  registration (Warm Lead) and not necessarily interest in mentoring
  (Candidate); *Lead* ("explored but not registered") is the nearest rung but
  its evidence is passive. An inquiry is a person writing to us — possibly its
  own bucket.
- **Evidence for *Lead*.** "Explored a service" is observable for a postcard (a
  QR scan) and an email (a link click) but not for an anonymous website visit.
  Each source needs a stated observable, or the rung is unreachable from it.
- **Jumps.** A postcard recipient who presses *Request a Mentor* goes from
  Unqualified/Qualified straight to Candidate, skipping four rungs. The ladder
  reads as strictly sequential (Candidate below Opportunity implies a service
  consumed first); the process needs to say jumps are normal and the *entry*
  rung is recorded per source.
- **Company-centric vs. person-centric sources.** A webinar registrant is a
  person, business often unknown; a filing is a business, person often
  unknown. Today a webinar registration creates a **Contact** (Prospect) by
  email plus a `CEventRegistration` (verified in `events/service.py`,
  2026-09-02), i.e. it never touches a prospect record at all. The
  one-record-two-halves question from 2026-09-01 is still open and this
  ladder makes it sharper.
- **Naming smell.** In every surveyed CRM *Unqualified* is a terminal reject,
  not the top of the funnel. If rung 1 keeps its meaning it may want a name
  like *Unverified*; if the split above is adopted, the reject becomes a side
  exit and the name is free.
- **Side exits are absent from the diagram** (already known / suppressed /
  undeliverable / do-not-contact / declined / stale). The 2026-09-01 list
  still stands as the candidate set.
- **Former or dormant clients** re-entering the funnel — the diagram ends at
  Client with no return path.
- **Chapter-network vocabulary** — none of the eight rung names is
  Cleveland-specific, which is a point in the ladder's favour.

### Open for the next session (as of 2026-09-02 — closed by the 2026-10-13/14 section below)

- Doug's answer to the Qualified/reach question above.
- Then the source-by-source walk against *this* ladder: filings, purchased
  lists, webinar registrants and attendees, inbound info@, partner referrals,
  mentor/client referrals and walk-ups, dormant clients — entry rung, rungs
  passed, touches, evidence per move, side exits.
- The items held back above, raised as the walk reaches them.
- Still queued behind those: the `source` ruling, `CProspect` storage, and the
  `/p/<token>` page versus the 2026-08-17 harvester ruling.

## Rulings — the source-by-source walk (2026-10-13/14)

The session the 2026-09-02 kickoff prompt called for. It resumed at the
unanswered Qualified question, walked all seven sources end to end against
Doug's funnel diagram, and settled the storage model, the consent fields and
the source field on the way. **Everything under "Doug's rulings" below was
stated by Doug as a decision and is dated.** Items under "Claude's" are mine
and are not decisions. The 2026-09-02 section's *Open for the next session*
list is closed by this section.

### Doug's rulings (2026-10-13 and 2026-10-14)

Numbered from 9 to follow the eight rulings of 2026-08-11. Where a ruling
changes an earlier one, the earlier one is named.

9. **SMS consent is added now, not deferred.** Its own tick beside the
   existing marketing opt-in on the person, because the law treats a text
   differently from an email. Captured wherever the marketing opt-in is
   captured today (the intake forms, event registration) plus the postcard
   landing page, each with wording that names texts. A text campaign selects
   on phone held plus SMS consent given. (10-14-26)
10. **Qualified means verified fit only** — a running company, in the service
    area, in a segment the chapter mentors, not already a client or contact.
    **Active Prospect is membership in a running campaign, not a rung** a
    company climbs to. The eight names and three bands of the 2026-09-02
    diagram stand; the meaning of two of the top three rungs changes.
    (10-14-26)
11. **A state filing enters at Qualified on the outside filter's verdict**
    (ruling 1), with the record showing what cleared it and when. No second
    fit check inside the process. (10-14-26)
12. **The already-known check runs at import**, matched conservatively on
    company name plus address, close to exact. A match is not a prospect: it
    leaves by the **Already known** side exit. The rule errs toward mailing a
    card to an existing client (noticeable, one card) over silently dropping a
    real prospect (never seen). (10-14-26)
13. **A postcard run waits for Marketing Admin Team sign-off** — the run
    assembles its list, shows the piece count and the estimated cost, and
    mails nothing until signed. (10-14-26)
14. **One postcard per company.** Any follow-up sequence waits for a measured
    response rate from the first campaigns. The six-month re-mail suppression
    is moot until a second-card campaign exists. (10-14-26)
15. **An undeliverable return marks the address dead and leaves the company
    Qualified**, selectable again the day a better address arrives from any
    source; fed back automatically from the mail vendor. Reports count these
    separately from the silent ones. (10-14-26)
16. **A scan of the postcard's code alone moves the company to Lead** — the
    company's first own action, the handoff from Prospect Marketing to Lead
    Marketing. Corrections, an added email or phone and the consent ticks on
    the landing page change what the chapter holds and may do, never the rung.
    **The landing page shows only what is printed on the card** (business name
    and mailing address); it never echoes an email, phone or person's name the
    chapter may already hold — the 2026-08-17 harvester ruling, now reconciled.
    (10-14-26)
17. **An information request lands on Warm Lead**, whose wording widens from
    "registered for at least one service" to **"asked the chapter for
    something and gave their details to get it."** Inbound info@ email is the
    same case. The owed reply is Submission Admin's response status, not a
    funnel matter. **Request a Mentor** goes straight to Candidate through the
    intake form; jumps are normal and the entry rung is recorded. (10-14-26)
18. **A purchased or partner-supplied list row enters at Unverified and
    reaches Qualified by a staff review**, with who cleared it and when on the
    record. The already-known check runs at import as for filings. (10-14-26)
19. **A company holding an email with no marketing opt-in goes to the postcard
    campaign**; the email stays unused until consent is given. No cold-email
    sending path; the Constant Contact opted-in-only rule stands. (10-14-26)
20. **A phone number makes a company selectable by a call campaign.** Each
    call is a touch recorded by the caller with one of three outcomes: no
    answer is a touch only; interest moves the company to Lead; a clear no
    leaves by **Declined**. (10-14-26)
21. **Storage model — Doug's design, which replaces the `CProspect`-as-funnel
    proposal above and an earlier same-day ruling for one prospect record with
    a business half and a person half.** A **prospect record is a quarantine**
    for a business or person the chapter cannot yet uniquely identify. It
    carries the rung, the entry rung, who or what qualified it, the side exit
    and every touch made while it is a prospect. **A web domain promotes the
    business to a Company typed Prospect; an email promotes the person to a
    Contact typed Prospect.** The promoted record links back to the prospect
    record, which stays as the history. The Prospect type is replaced by
    Client, Partner, Funder or a later type when a relationship begins — the
    one sanctioned relabel (today no form ever rewrites a type). **"Do we know
    them" is one search** of Companies or Contacts; a prospect record is by
    definition not uniquely identifiable, so the import check is the only
    place it is searched, automatically and conservatively. Under this rule
    almost every filing stays a prospect record through the whole postcard
    campaign, and a Company is created per *response*, not per card — so the
    Company-pollution cost (ruling 8) does not arise. (10-14-26)
22. **A relationship always creates a Company and a Contact, website or not,
    exactly as today.** The domain-or-email identity rule governs only the
    marketing stage. The application therefore never meets a prospect record
    where it expects a Company (about thirty read sites across eight packages,
    plus the CRM's own layouts and the Drive folder scheme, all assume one).
    (10-14-26)
23. **No single-entry partner referral.** A partner who supplies names
    supplies a file, handled by a specialised import; that import is not
    built now. A partner-supplied list enters under ruling 18. (10-14-26)
24. **Mentor, client and walk-up referrals enter only through the existing
    doors** (the website forms, the webinar page); the form's "how did you
    hear" answer records the referral. The conversation itself is never a
    touch. (10-14-26)
25. **A dormant or former client stays a Client and never re-enters the
    funnel.** Re-marketing is a campaign selection rule over existing client
    records (engagement closed longer than a set period, opt-in present); a
    response is a new engagement through the intake form as today. (10-14-26)
26. **Two tracking fields, and ruling 6 is refined.** **Source** stays what it
    is today — what the person says on any form — and is never written by a
    door. **Campaign** is a new entity created by marketing users; each
    campaign owns one or more links; a link opens one of the standard intake
    forms carrying the campaign's id, and the records the form creates carry
    it. The postcard is a campaign whose link rides in the QR code; "State New
    Business Filing-Postcard" is a campaign's name, not a source value.
    Precedent: the partner intake link (v0.255.0) already rides a hidden
    field, the captured payload and a delivery-time write. (10-14-26)
27. **The campaign id lands on the relationship record every time** (the
    engagement, the information request, the event registration, the partner
    or funder profile) **and on the Contact and Company only when that
    submission created them**, so a person who arrives through two campaigns
    over the years keeps both. (10-14-26)

### Proposals of mine withdrawn in the session (Claude's)

- **A stored "reach" field** (address only / email / phone / both). Doug: an
  overly complex set of fields, hard to maintain. Withdrawn: reach is fully
  derived from the fields present, and a campaign's selection rule names it
  directly. The reportable grouping Doug asked for on 2026-09-01 is **the
  campaign itself** (ruling 26), stamped on every touch.
- **A separate three-state permission field per channel.** Withdrawn: the
  marketing opt-in and EspoCRM's per-address opt-outs already exist and are
  already maintained by the forms, event registration and the Constant
  Contact unsubscribe sync; ruling 9 adds the one missing tick.
- **`source` as the arrival channel.** Withdrawn by ruling 26.
- **A prospect record with two halves as the funnel's home**, and
  **person-on-Contact, business-on-prospect**. Both replaced by ruling 21.
- **A pre-form partner referral entry.** Withdrawn by ruling 23.
- **Lost** and **Junk** side exits: not needed once in seven walks. Dropped
  unless Doug objects.

### The ladder as it stands (Doug's names, 2026-09-02; meanings per the rulings)

| # | Band | Rung | Meaning now | Evidence that puts a record here |
|---|---|---|---|---|
| 1 | Prospect Marketing | Unqualified (**working name: Unverified**, Claude's) | Known to exist; fit not yet verified | A list row at import |
| 2 | Prospect Marketing | Qualified | Verified fit only (ruling 10) | The outside filter's verdict (filings); a staff review (lists) |
| — | Prospect Marketing | Active Prospect | Membership in a running campaign, not a rung (ruling 10) | Selected by a campaign run |
| 3 | Lead Marketing | Lead | Explored a service | A QR scan; a call where interest was shown |
| 4 | Lead Marketing | Warm Lead | Asked the chapter for something and gave their details to get it (ruling 17) | A webinar registration; an information request; an inbound info@ email |
| 5 | Lead Marketing | Opportunity | Consumed a service, not mentoring | Attendance recorded |
| 6 | Lead Marketing | Candidate | Asked for mentoring; no session yet | An engagement exists (read from the engagement) |
| 7 | Client Management | Client | Active mentoring | An engagement with a completed session (read from the engagement) |

The rung lives on the prospect record until promotion and on the Company or
Contact typed Prospect after it (ruling 21); Candidate and Client are read
from the engagement, never stored a second time (2026-09-01 working position,
confirmed by the walk).

**Side exits in use:** Already known (ruling 12) · Unqualified-as-reject, the
fit failure, which the split in ruling 10 moved off the ladder · Do Not Contact
· Undeliverable (kills the address, ruling 15) · Declined (ruling 20) · Stale
(the silent majority after a set period; the re-entry point if a second-card
campaign is ever built).

### The walk, source by source

| Source | Enters at | Record created at entry | Campaigns that can select it | Rungs reachable | Side exits seen |
|---|---|---|---|---|---|
| 1. State filings | Qualified (ruling 11) | Prospect record (ruling 21) | Postcard | Lead (scan) → Warm Lead (Info Request) / Candidate (Request a Mentor) → Client | Already known, Undeliverable, Stale |
| 2. Purchased / partner lists | Unverified → Qualified by review (ruling 18) | Prospect record; Company or Contact typed Prospect if a domain or email arrived with the row | Postcard (no opt-in), email (opt-in), call (phone) | As filings, plus Lead by call | Already known, Unqualified, Declined, Stale |
| 3. Webinar registrants / attendees | Warm Lead | Contact typed Prospect, as today; a prospect record for a named business with no domain | Email (if opted in) | Opportunity (attendance) → Candidate → Client | — |
| 4. Inbound info@ / Info Request | Warm Lead (ruling 17) | Contact typed Prospect, as today | Email (if opted in) | Candidate → Client | — |
| 5. Partner referrals | Candidate via the partner link (as today); a supplied file enters as source 2 (ruling 23) | As today | — | — | — |
| 6. Mentor / client / walk-up referrals | Wherever the door they use puts them (ruling 24) | As today | — | — | — |
| 7. Dormant clients | Never re-enters (ruling 25) | None — campaign selection over Client records | Email, call | — | — |

Opportunity is reachable only from the webinar source, which is correct: no
other source consumes a service before mentoring.

### Open after this session (Claude's list)

- **Rung 1's name.** *Unqualified* is a terminal reject in every surveyed CRM;
  with the reject now a side exit the rung means "known, fit not verified".
  Working name *Unverified*; Doug has not ruled.
- **Where the rung continues after promotion** — a field on Company and
  Contact, or read through the link from the prospect record. Design detail
  for the build plan; the walk needs only that it continues.
- **The call campaign's recording screen** (ruling 20) — the first touch a
  human records by hand; unrecorded calls read as "never contacted".
- **Retention.** Prospect records that go Stale accumulate; the period and
  what happens after it are not set.
- **Attendance evidence** for Opportunity needs Phase 6a (Zoom pull, off
  everywhere) or a manual check-in.
- **The campaign entity's shape** — links, the QR code carrying both the
  prospect id and the campaign id, which forms honour the id, how the
  partner link (v0.255.0) and the campaign link coexist.
- **The Prospect-to-type relabel** at conversion is new behaviour for every
  door; today the type is excluded from every null-fill by design.
- **Chapter-network vocabulary**: none of the rung names is Cleveland-specific;
  "State New Business Filing" is now a campaign name, so the smell is gone
  from the schema. A prospect entity and a campaign entity are CRM changes
  under `prds/chapter-network/crm-update-runbook.md`.
- The earlier open questions (what the outside filter delivers and how; the
  postcard offer and creative; which address is mailed) are unchanged.

**Next step (as of the walk):** the build plan is written
(`prds/prospect-marketing-build-plan.md`, 2026-10-14); its § 9 holds the
seven questions that gate the CRM handoff. **Superseded the same evening by
the section below**: the build plan must first be revised to v0.2 against
the Campaign Management requirements — **done, v0.2, the same evening** —
and the CRM handoff then waits for the answers to build plan questions 1, 3,
8 and 9, which change the CRM's shape.

---

## Requirements — Campaign Management application (10-14-26)

The definition session the 2026-10-13/14 walk called for
(`prompts/prospect-marketing-campaign-app-prompt-v0.1.md`), run the same
evening in DETAIL mode, one question per turn. Seven questions were put to
Doug in the prompt's order and every one was answered. **Everything under
"Doug's requirements" was stated by Doug on 10-14-26** and is dated as such;
"working positions" were said in the discussion and may be revised;
"strawmen" are mine and were not adopted. Rulings 1–27 were not reopened.

**Read this before the build plan.** `prds/prospect-marketing-build-plan.md`
v0.1 was written earlier the same day, before these requirements existed.
**Its v0.2 (the same evening) is revised against them**, section by section
per the list at the end of this section; the five choices that revision had
to make are its questions 8–12. The requirements win where anything still
differs.

### Doug's requirements (10-14-26)

Numbered CM-1 onward so they are never confused with rulings 1–27.

- **CM-1. The Marketing Admin Team creates and runs campaigns.** The same
  team that works Submission Admin and Event Administration and signs a
  postcard run under ruling 13. No new team.
- **CM-2. A campaign names one or more associated partners.**
- **CM-3. The campaign kinds are postcard, email, SMS, call and social
  media** (Meta, YouTube and the like). SMS and social media were added by
  Doug to the three kinds the walk produced.
- **CM-4. A form that receives a campaign link looks up the campaign's
  partner or partners and, by that form's own logic, relates them to the
  records it creates.** Nothing about a partner rides in the link; the
  campaign is the source of the partner at delivery.
- **CM-5. Every partner's Overview has a Campaigns tab** listing the
  campaigns that partner sponsors.
- **CM-6. A campaign can be linked to events**, so a campaign that
  advertises events ties every registration made through its link to the
  campaign and to the campaign's partners.
- **CM-7. What a link is** (a strawman Doug adopted as written): a link is
  created inside a campaign by a marketing user, has its own name, and
  points at one destination. The destinations are any of the five public
  intake forms, the public workshops-and-webinars programme page, or one
  event's own page. A campaign has any number of links, each counted on
  its own. A link to the programme page carries the campaign through to
  whichever event registration the visitor makes from it. The postcard
  campaign has exactly one link, pointing at the landing page, and each
  card's code is that link plus the card's own prospect token.
- **CM-8. A campaign link is a short address of its own that the
  application resolves** to the destination and stamps with the campaign
  as it sends the visitor on, never the CRM id in the open. Accepted with
  it, as the behaviours the short address exists for: the destination can
  be corrected after the link is published; a link can be retired, and a
  retired link still opens its destination with the response marked late;
  the QR code is generated by the application from the short address.
- **CM-9. The numbers are split by who changes them.** The campaign's own
  page shows what the application's records know, fixed and the same on
  every chapter: a row per link with visits and submissions by form, the
  campaign totals, the latest responses with a way through to each record,
  and for a postcard campaign the pieces mailed, the undeliverable returns
  and the scans. Conversion down the funnel (Candidate, Client, read from
  the engagement; registered and attended for an event campaign) and any
  comparison between campaigns are Analytics: a dashboard scoped to the
  campaign, plus whatever cross-campaign pages the Analytics administrators
  author.
- **CM-10. Its own portal tile**, gated to the Marketing Admin Team, in the
  house shape: a grid of campaigns with status and kind, and a record page
  per campaign that opens in its own stable browser tab, with Overview,
  Links, Responses and Analytics tabs; the partners and events a campaign
  is tied to are on its Overview.
- **CM-11. The word on the screen is Campaign.** Accepted with it: the tile
  is *Campaign Management*, beside Client, Partner and Funder Management;
  in this application a Constant Contact send is a **notice**, never a
  campaign, so the mailing plan's unbuilt Phase D button *Link a campaign*
  is built as *Link a notice*.

### Working positions (said in discussion, not ruled)

- No mentor, client administrator or partner manager ever creates a
  campaign. A partner's own intake link is their referral mechanism; a
  campaign is a chapter-level marketing act. Doug did not object.
- The create screen asks for six things: name, kind, status, a start and
  end date, an owner (defaulting to the creator) and a notes box. No budget
  or cost field: a postcard run's cost comes from the run under ruling 13,
  an email campaign costs nothing and a call campaign costs time. No
  creative, template or artwork on the record; design stays in the vendor's
  tools (mailing plan ruling 6). Doug added partners and kinds to this
  strawman and struck nothing from it.
- The dormant-client campaign is an email or call campaign with a
  different selection rule (ruling 25), not a sixth kind.
- A social media campaign selects nobody from the CRM. It is a broadcast
  whose footprint here is its links and their responses, so a selection
  rule is a property of some kinds and not others.
- There is no enforced two-person rule on spending: the sign-off of ruling
  13 is recorded by name and time, by the same team that built the
  campaign. The cost was named and accepted.
- "Linked to events" was said in the plural; the working position is one
  or more events per campaign.
- The campaign-to-event link and the mailing plan's `noticeCampaignId`
  (Phase D, unbuilt) cover the same ground and should become one design,
  not two fields that mean nearly the same.
- The engagement holds one referring partner today. A campaign with several
  partners needs the build plan to say what CM-4's "relate the partner"
  means on an engagement: a second, many-partner link, or a rule for the
  single field.

### Strawmen (mine, not adopted)

- Status vocabulary *draft / approved / running / closed*. The build plan's
  six states are its own draft; neither is ruled.
- Social media as one kind with a platform field (Meta, YouTube, …) rather
  than one kind per platform.
- The short address as `<app>/c/<token>`, resolved by a link record that
  holds the destination, with the resolve route rate-limited because a
  short address that resolves to something is a thing people probe.
- A link's "visit" is the resolve; the form's banner lookup is no longer
  the open count.
- The programme-page carry-through as the campaign id held by the page and
  appended to every event link it renders, so the registration form
  receives it.

### The campaign's fields, as named

| Field | Named by | Notes |
|---|---|---|
| Name | strawman, unopposed | |
| Kind | Doug | postcard · email · SMS · call · social media (Meta, YouTube, …) — CM-3 |
| Status | strawman, unopposed | vocabulary open |
| Start and end date | strawman, unopposed | the shared date control |
| Owner | strawman, unopposed | defaults to the creator |
| Notes | strawman, unopposed | the shared rich-text editor |
| Partners (one or more) | Doug | CM-2; drives CM-4 and CM-5 |
| Events (one or more) | Doug | CM-6; plurality a working position |
| Links (any number) | Doug, via CM-7 | each named, one destination, own count |
| Budget / cost | — | deliberately absent; the postcard run computes its cost (ruling 13) |

### The link's shape

| Property | Value |
|---|---|
| Address | a short address of the application's own, resolved server-side (CM-8) |
| Carries | the campaign; for a postcard also the card's prospect token (CM-7); never a partner (CM-4) |
| Destinations | the five intake forms · the programme page (carry-through) · one event's page |
| After publishing | destination correctable; retire-but-still-open, late-marked |
| QR code | generated by the application from the short address |
| Count | per link: visits, submissions by form (CM-9) |

### The screens

- **Portal tile** *Campaign Management*, Marketing Admin Team (CM-10,
  CM-11).
- **Campaign grid**: status, kind; the house grid shape.
- **Campaign record page**, one stable tab per record: Overview (fields,
  partners, events), Links (create, name, copy, correct destination,
  retire, QR), Responses (latest responses through to each record; the
  postcard block), Analytics (the campaign-scoped dashboard).
- **Partner Overview**: a Campaigns tab (CM-5).
- Conventions noted where a screen is named, not re-litigated: no page
  width cap; every button always visible and clickable, explaining itself
  on a missing input or grant; every date through the shared date control;
  every rich-text field through the shared editor; every mutating action
  action-logged.

### Still open after this session

- CM-4 on an engagement when a campaign has several partners (above).
- Social media: one kind with a platform field or one kind per platform,
  and what counts as a response from it.
- SMS: there is no sending path in the application today; ruling 9 settled
  the consent, not the vendor. The build plan reserved the kind; CM-3
  offers it.
- One event or many per campaign.
- The status vocabulary.
- Who may correct or retire a link (presumably the same team).
- The programme-page carry-through mechanism.
- Where the prospect screens of the build plan (Prospects, Calls, Review)
  live now that the tile is *Campaign Management*: inside it, or their own.
- The build plan's § 6 says a per-campaign dashboard scope is "not in this
  arc"; CM-9 requires one.

### What build plan v0.1 must change to meet these requirements

Listed by section so the v0.2 session can work through it.

- **§ 1.3 the campaign entity**: kinds gain SMS and social media (CM-3);
  an owner; the entity's *label* reads Campaign on screen (CM-11) whatever
  its stored name.
- **§ 1.5 links**: a many-to-many between the campaign and partner
  profiles (CM-2, CM-5); the single `event` link becomes one or more
  (CM-6, working position); a link record per campaign link, or an
  application-side table, holding name, destination, token, state (CM-7,
  CM-8).
- **§ 3.1 and § 3.5 the engine and screens**: the tile is *Campaign
  Management* at its own route, not *Prospect Marketing* at `/outreach`
  (CM-10); the campaign page gains the Links and Responses tabs; the links
  card's derived `?campaign=<id>` addresses are replaced by resolvable
  short addresses (CM-8); the selection rule applies to the kinds that
  select (working position).
- **§ 3.6 the word**: *outreach campaign* becomes *campaign* in every
  user-facing string; *notice* stands (CM-11).
- **§ 4 the landing page**: the card's code is the campaign's one link plus
  the prospect token (CM-7), generated by the application (CM-8).
- **§ 5 conversion**: the form receives the campaign from the resolved link,
  looks up the campaign's partners and relates them by its own logic
  (CM-4); the "a campaign link carries no partner" sentence stands, the
  "both are written only if a chapter gives a partner a campaign link"
  sentence does not; event registrations through a campaign link tie to
  the campaign and its partners (CM-6).
- **§ 6 reporting**: the campaign page's fixed numbers and the
  campaign-scoped Analytics dashboard (CM-9); the "not in this arc" line
  goes.
- **§ 9 questions**: the still-open list above joins it.


## Revision control

| Field | Value |
|---|---|
| Document | Prospect Marketing — plan |
| Version | v0.6.1 draft — **process ruled end to end; Campaign Management application defined (CM-1 to CM-11); build plan v0.2 revised against it**; the storage section above is superseded by ruling 21 |
| Last Updated | 10-14-26 22:09 |
| Prepared by | Claude, for D. Bower |
| Session | 2026-08-11 requirements elicitation; 2026-09-01 funnel-stage discussion; 2026-09-02 funnel diagram review (paused at the first question); 2026-10-13/14 source-by-source walk (rulings 9–27); 2026-10-14 Campaign Management definition (CM-1 to CM-11) |
| Related | `research/registry-enrichment/enrichment-findings.md`, `cinformation-request-entity.md`, `prds/intake-receipt-redesign-plan.md`, `prompts/prospect-marketing-funnel-2026-09-02.png`, `prompts/prospect-marketing-process-session-prompt-v0.1.md`, `prompts/prospect-marketing-campaign-app-prompt-v0.1.md`, `prds/prospect-marketing-build-plan.md` |

### Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| v0.6.1 draft | 10-14-26 22:09 | Claude (Claude Code) | Status, the requirements section's pointer and the next step now say the build plan is revised (v0.2) and name the four build-plan questions that gate the CRM handoff. No requirement or ruling changed. |
| v0.6 draft | 10-14-26 21:55 | Claude (Claude Code) | Added *Requirements — Campaign Management application (10-14-26)*: Doug's eleven requirements CM-1 to CM-11 (Marketing Admin Team; partners on a campaign; kinds gain SMS and social media; forms relate the campaign's partners; a partner Campaigns tab; campaign-to-event links; named links of any number with programme-page carry-through; short resolvable addresses with correctable destinations, retire-but-open and QR generated here; the campaign-page / Analytics split; its own tile with a record page; the word Campaign, a Constant Contact send a notice), the working positions, the strawmen, the field, link and screen tables, the open list, and the section-by-section list of what build plan v0.1 must change. Status and next step updated; the duplicated date in Last Updated fixed. No ruling changed. |
| v0.5 draft | 10-14-26 17:34 | Claude (Claude Code) | Status, next step and header now point at the build plan (`prds/prospect-marketing-build-plan.md` v0.1). No ruling changed. |
| v0.4 draft | 10-14-26 17:18 | Claude (Claude Code) | Added the 2026-10-13/14 section: the source-by-source walk, rulings 9–27 (SMS consent; Qualified = fit only and Active Prospect = campaign membership; the quarantine storage model; a relationship always creates a Company; Source unchanged plus a new Campaign entity), the withdrawn proposals, the ladder and the per-source walk tables, the open list. Header, status and revision rows updated; the 2026-09-02 open list marked closed. |
| v0.3 draft | 09-02-26 | Claude | Doug's funnel diagram recorded; first review point; paused at the Qualified question. |
| v0.2 draft | 09-01-26 | Claude | Funnel-stage discussion recorded — ideas only. |
| v0.1 draft | 08-11-26 | Claude | Strawman from the requirements elicitation; rulings 1–8. |
