# Prospect Marketing — plan v0.1 (2026-08-11)

**STRAWMAN — not an approved plan.** Sections marked *Doug's rulings* record
decisions already made in the 2026-08-11 session. Everything marked **PROPOSAL**
is my recommendation awaiting your call, not a settled decision.

Scope: manage prospects from **all lead sources**, including those with no email
or phone, and reach the latter by **postcard** carrying a per-prospect QR code
that leads to a personalized landing page and then into the existing intake
forms.

Status: **NOT BUILT.** No code, no CRM entity, no vendor account.

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

## Revision control

| Field | Value |
|---|---|
| Document | Prospect Marketing — plan |
| Version | v0.1 — **strawman, not approved** |
| Last Updated | 2026-08-11 |
| Prepared by | Claude, for D. Bower |
| Session | 2026-08-11 requirements elicitation |
| Related | `research/registry-enrichment/enrichment-findings.md`, `cinformation-request-entity.md`, `prds/intake-receipt-redesign-plan.md` |
