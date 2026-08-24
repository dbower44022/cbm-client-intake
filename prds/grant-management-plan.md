# Grant Management — plan v0.1 (2026-08-23) — **STRAWMAN, not approved**

Doug asked for two things: a review of what existing grant-management
applications actually do, and a plan to add grant management to the CRM and to
Funder Management (`/sponsorsessions`). This document is **a strawman for
review** — the rulings section at the end is the part that has to happen before
any of it is built. **Ruling #1 is settled (Doug, 2026-08-23): the grant is the
hub — a funder awards a grant, and the grant is tied to contributions AND to
deliverables.** The rest is still open.

The ask, in Doug's words: *a funder may make a contribution of type Grant that
has one or more deliverables tied to it; deliverables come in different kinds
(numeric — "10 seminars", "25 hours of mentoring to their clients" — and
rating-based — "average approval rating for seminars or mentoring sessions");
once in a time period the deliverables must be reported to the funder, in order
to continue receiving grants.*

---

## 1. What grant-management applications do

Two markets share the name and only one of them is ours. **Grantmaker** systems
(Fluxx, Foundant GLM, Blackbaud Grantmaking, Submittable) run an application
portal, review panels and payment approvals — CBM is not giving grants away.
**Grantee / grant-seeker** systems (AmpliFund, GrantVantage, Instrumentl,
GrantHub, Euna Grants) manage the money CBM *receives* and the obligations that
come attached. That second category is the one to mine, and inside it the
sub-area that matches Doug's ask exactly is **post-award performance and
reporting**.

### The function inventory

**A. Pre-award / pipeline** — opportunity discovery and funder research, an
eligibility screen, LOI and application tracking, a deadline calendar, a
proposal/boilerplate library, budget building, internal review and approval,
submission tracking. *Mostly not CBM's problem today; the one piece that is, is
the renewal deadline — "in order to continue receiving grants" makes the next
application date part of the same record.*

**B. Award setup** — the award record itself: amount, period of performance,
restrictions and designation, a payment or drawdown schedule, funder contacts,
the executed agreement document, automated extraction of the requirements buried
in the award letter, and **renewal lineage** (this grant is last year's grant,
renewed).

**C. Performance / deliverables** — the heart of it. A **performance plan**
hangs off the award: a list of goals, each with a **type**, a target, a
responsible individual, attachments, and progress recorded per reporting period.
AmpliFund's six goal types are the de-facto vocabulary and map almost one-to-one
onto what Doug described:

| Goal type | Captures | CBM example |
|---|---|---|
| **Numeric** | units completed against a discrete target | 10 seminars; 25 mentoring hours |
| **Percent achieved** | total achieved ÷ total possible | 80% of clients completing the programme |
| **Percent changed** | movement from a baseline | revenue growth across the cohort |
| **Milestone** | a yes/no — done or not | curriculum delivered by 30 June |
| **Narrative** | a question the responsible person answers in prose | "describe the impact on participants" |
| **Reimbursement** | spend claimed against the award | *(not CBM — no expense data in the CRM)* |

The outcomes-measurement literature adds the vocabulary underneath a numeric
goal: an **indicator** with a **baseline**, a **target** and periodic **actual**
values, optionally disaggregated. Ratings ("average approval rating") are a
percent-achieved or average-of-scale indicator whose actuals come from a survey
instrument.

**D. Financial** — budget by category, expenses coded to the grant, burn-rate and
spend-down forecasting, drawdowns and invoices, match and in-kind tracking,
restricted-fund balances. *Out of scope for CBM: the CRM holds no expense data,
and the money side CBM does hold is already the Contributions ledger.*

**E. Compliance & documents** — a document library per grant, requirement
checklists, an audit trail of who changed what, subrecipient monitoring.

**F. Reporting to funders** — a **report schedule** per award (interim / annual /
final, each with a due date), report templates combining narrative with the
numbers, **period-locked data** (once a reporting period is closed, achievements
can no longer be added or edited — AmpliFund is explicit about this), a
submission status, attachments, delivery to the funder and a retained copy, and
overdue alerts. The federal cadence convention — interim within 30 days of period
end, final within 90–120 days — is worth knowing even though CBM's funders are
private.

**G. Communication & relationship** — correspondence attached to the grant,
acknowledgment/thank-you tracking, stewardship touchpoints.

**H. Dashboards & alerts** — portfolio view (awarded / pending / received),
deliverable status across every grant, upcoming deadlines, overdue reports,
reminders, role-based access, exports.

### What of that CBM actually needs

**B, C, F, H** — award, deliverables, periodic reporting, and a "what's due"
view. **A** contributes exactly one field (the renewal deadline). **D** is out.
**E** and **G** CBM already has, generically: the Documents tab (Drive) and the
Communications tab both already hang off the funder record, and `core/action_log`
already records every mutating staff action.

The differentiator CBM has and none of these products do: **the deliverables are
measurable from data the system already holds.** Seminars are `CEvent` rows,
mentoring hours are `CSession` rows, clients served are engagements. In
AmpliFund somebody types "7" into a box each quarter. Here, the number can be
computed and the box becomes an override. That should be the design centre.

---

## 2. What CBM already has (verified in the repo, 2026-08-23)

- **`CContribution`** — the funder money ledger, built and live, with
  `contributionType` including **Grant**, a status lifecycle
  (Applied / Pledged / Committed / Received / Unsuccessful / Cancelled), amount,
  five dates, and — telling — an inert **`nextGrantDeadline`** field that nothing
  in the codebase reads. Plan and rulings: `prds/funder-contributions-plan.md`;
  summary math: `sessions/service.py` (`contribution_summary`).
- **The Contributions tab pattern** — `DomainConfig.contributions_link` gates
  *both* the tab and the route registration, `CONTRIBUTION_FIELDS` is one spec
  serving as form layout and write whitelist, enum options come live from CRM
  metadata. A Grants tab is the same shape, one config field along.
- **`CEvent ↔ CSponsorProfile` many-to-many (`sponsorProfiles`) already exists**
  in the CRM — and **is not exposed anywhere in the app** (`EVENT_FIELDS` in
  `events/config.py` has no entry for it). Seminar-to-funder attribution is one
  editor field away.
- **`CEventRegistration.attendanceStatus`** (Registered / Waitlisted / Cancelled /
  Attended / No-Show) with a Zoom-fed attendance pull — attendee counts are
  already real data.
- **`CSession`** with `dateStart`/`dateEnd` and a `Completed` status — mentoring
  hours are computable today.
- **The analytics builder** (`analytics/builder.py`) — a stored *entity + filters
  + aggregation* definition (`count` / `sum` / `avg` / `group_by` / `bucket` /
  `list`) with relative-date filters, a live-preview authoring UI, and
  record-scoped metrics that run as the signed-in user. **This is a deliverable
  measurement engine that already exists.**
- **Compose, templates, Drive documents, action log, worker alerting, portal
  attention badges** — every piece of "produce a report and send it to the
  funder, then remember you did" is already built for other purposes.

### The three real gaps

1. **No rating data exists anywhere.** No `CSession` satisfaction field, no
   `CEventRegistration` rating, no survey capture — the `EventSurvey` follow-up
   template sends people somewhere else and nothing comes back. **Doug's ruling
   2026-08-23: CBM will build the whole rating engine into this system**, so this
   gap closes — but as its own arc (`prds/rating-engine-plan.md`), not as two
   fields bolted onto the grant build. Rating deliverables are Manual until it
   lands, and become automatic with no change to the grant model.
2. **No funder → client attribution.** Partners have a `engagements` link
   (the Referred Clients tab); **funders have nothing equivalent**. "25 hours of
   mentoring to *their* clients" has no answer in the data model yet.
3. **`CEvent.sponsorProfiles` is unexposed**, so even the attribution that does
   exist can't be entered from the app.

---

## 3. Proposed model — the strawman

### Three new CRM entities

**`CGrant`** — the award, and the thing reports are about.

> `name` (req) · `sponsorProfile` (belongsTo CSponsorProfile, reverse
> **`grants`**) · `status` (Applied / Awarded / Active / Reporting / Closed /
> Declined / Cancelled) · `awardAmount` (currency + `awardAmountCurrency`) ·
> `periodStart` · `periodEnd` · `programArea` · `grantManager` (belongsTo
> CMentorProfile) · `reportingFrequency` (Monthly / Quarterly / Semi-annual /
> Annual / Final only / Ad hoc) · `firstReportDue` · `nextReportDue`
> (app-maintained) · `renewalDeadline` · `renewalOf` (belongsTo CGrant, reverse
> `renewals`) · `notes` (wysiwyg) · `description` · `assignedUser` · `teams`

**`CGrantDeliverable`** — one promise, with a type and a target.

> `name` (req, "10 seminars") · `grant` (belongsTo, reverse **`deliverables`**) ·
> `deliverableType` (Numeric / Rate / Percentage / Milestone / Narrative) ·
> `targetValue` (float) · `unit` ("seminars", "hours", "clients") ·
> `ratingScaleMax` (float, Rate only) · `measurementSource` (Automatic / Manual /
> Survey) · `measureKey` (varchar — the built-in measure or `analytics:<key>`) ·
> `measurementNotes` · `frequency` (inherits the grant) · `dueBy` (Milestone) ·
> `deliverableStatus` (On track / At risk / Behind / Met / Not met — derived,
> stored so the CRM grid can show it) · `sortOrder`

**`CGrantReport`** — one reporting period, and the artifact sent to the funder.

> `name` (req) · `grant` (belongsTo, reverse **`reports`**) · `periodStart` ·
> `periodEnd` · `dueDate` · `reportStatus` (Due / Draft / Submitted / Accepted) ·
> `submittedDate` · `narrative` (wysiwyg) · **`results`** (text — the frozen
> per-deliverable numbers, JSON) · `gmailThreadId` · `documentUrl` · `notes`

**The period's actual numbers live in `results` as a JSON snapshot** (ruled,
Doug 2026-08-23) rather than as a fourth entity of one row per deliverable per
period. They are meaningless outside the report they were sent in, and a trend is
still reconstructable by reading a grant's reports in order. Consequences to
honour when building it: the JSON carries a **`version`** key and each entry
records the deliverable id, its name and unit **as they read at submission** (a
later rename must not rewrite history), the computed value, any override and its
reason, and who submitted it — a snapshot that only stores ids is worthless once
a deliverable is edited. A submitted report **renders from the snapshot, never
recomputes**. If CRM-native trend reporting is ever wanted, the fourth entity can
be added later and back-filled by replaying the stored snapshots.

Plus **one link on the existing ledger**: `CContribution.grant` (belongsTo CGrant,
reverse **`payments`**) — so a grant paid in four tranches is one award with four
ledger rows, and the existing Contributions math is untouched.

**Why an entity rather than fields on `CContribution`** (ruled, Doug
2026-08-23). Making the grant the hub keeps the ledger a ledger — money in — and
gives the obligation its own record. Hanging deliverables off a
`contributionType=Grant` row breaks on two things that are certain to happen: a
grant paid in tranches has no single row to *be* the grant, and a renewal has
nothing to descend from.

**Deliverables and contributions are SIBLINGS under the grant, not a chain**
(Doug's follow-up question, 2026-08-23). They are two different axes: a
contribution answers *when the money arrives*, a deliverable answers *what CBM
owes in return* — measured over a period and asserted in a report. Chaining them
fails in both directions: a deliverable running the full grant year ("25
mentoring hours") would have to attach to one arbitrary payment, and a grant paid
in four equal quarterly tranches has no deliverable to hang each payment off.
Keeping them siblings is also what lets grant payments stay ordinary ledger rows,
so the existing Contributions tiles and totals keep working untouched.

*The one case where the two axes really do meet* is a performance-based grant
where the next tranche is released only once the funder accepts a report — and
note the direction: the gate is **report acceptance**, not raw deliverable
attainment, because the report is where attainment is asserted. If that shows up,
the answer is one nullable link on the payment,
`CContribution.contingentOn` → `CGrantReport` ("this payment is contingent on
that report"), a condition on the money rather than a parent for the deliverable.
**Deliberately not built until a real grant needs it.**

### Measurement — the part worth building

A deliverable declares *how it is measured*, not just what its target is.

- **Manual** — a number typed per period with a note. Always available; the only
  option for rating deliverables in v1; the escape hatch for everything not yet
  instrumented. Nothing is ever blocked on the automation existing.
- **Automatic, built-in** — a small registry in `grants/measures.py`, each entry
  a key, a label, a unit and an async `compute(client, grant, period)`:
  - `events.held` — `CEvent` linked to this funder via `sponsorProfiles`,
    status Held, `dateStart` in period → *"10 seminars"*
  - `events.attendees` — `CEventRegistration` at `Attended` for those events
  - `sessions.hours` — Σ (`dateEnd` − `dateStart`) over Completed `CSession`
    rows for the grant's attributed engagements → *"25 hours of mentoring"*
  - `sessions.count`, `clients.served` — distinct attributed engagements
  - `rating.sessions.avg`, `rating.events.avg` — **declared, and automatic once
    the rating engine lands** (ruled, Doug 2026-08-23: CBM captures ratings
    in-house — see `prds/rating-engine-plan.md`, a separate arc). Until then a
    deliverable pointing at one degrades to Manual with an explanatory line
    rather than showing a wrong zero.
- **Automatic, authored** — `analytics:<metricKey>`, delegating to a builder
  metric. That is what makes this extensible without a deploy: staff author a new
  measure in the analytics builder with its live preview, and a deliverable
  points at it. The grant period becomes the metric's custom `TimeRange`.
  *Reuse candidate — to be proven against a live CRM in its phase, not assumed.*

Every automatic number is **an input to the report, never the last word**: the
report builder shows the computed value, lets the manager override it, and
records the override with a reason. Funder reporting is a statement CBM signs.

### Attribution — settled: it lives on the grant (Doug, 2026-08-23)

"Their clients" is defined **per grant**, not per funder: `CGrant` carries a
many-to-many to `CEngagement` (**`fundedEngagements`**, reverse `fundingGrants`),
so a client is attributed to *this year's* grant and next year's renewal starts
clean. The alternative of hanging it on `CSponsorProfile` would have made every
client a funder ever sponsored count forever, and programme-level counting (no
link, every session in the period counts) would credit two funders with the same
hours in the same year.

The cost is upkeep, so the maintenance surface has to be good: a **Funded
Clients** panel on the grant popup that picks from the engagements the signed-in
user can read, plus — since the renewal case is the common one — carrying the
previous grant's list forward as the default when a grant is created via
`renewalOf`. This is the link `sessions.hours`, `sessions.count` and
`clients.served` measure over; without it those three measures have nothing to
count and degrade to Manual.

*Still open (recommended, not ruled):* letting an individual deliverable opt out
of the link with a `measurementScope` of "all programme activity", for a funder
who genuinely funds the programme rather than named clients.

### Where it lives in the app

1. **A Grants tab on the funder record** — `DomainConfig.grants_link`, sponsor
   domain only, the exact `contributions_link` precedent (one config field gates
   both the tab and the route registration). Grid: grant · status · amount ·
   period · next report due · a deliverable progress bar. Tiles above it: active
   grants, awarded this year, reports due, deliverables at risk.
2. **A grant detail popup** — the v0.210.0 engagement-popup treatment (90% of the
   window, resizable, pinned Save/Cancel around a scrolling body, one field spec
   as layout *and* whitelist). Panels: Award · **Deliverables** (inline rows with
   target, live actual, progress) · Payments (the linked ledger rows) ·
   **Reports** · Notes.
3. **The report builder** — opens a period, computes every deliverable, shows
   computed-vs-override side by side, takes the narrative in CBMRichText, and
   then **hands off to the existing compose surface** addressed to the funder's
   primary contact with a `GrantReport` EmailTemplate. On send: freeze `results`,
   stamp `submittedDate` and status Submitted, file a copy to the record's
   Documents (Drive), advance `lastContacted` via `touch_last_contact`, and
   `record_action` it. **Frozen means frozen** — a submitted report never
   recomputes.
4. **An obligations view** — reports due and overdue across every grant the user
   can read, on the Funder Management grid page, plus the portal attention badge.
5. **Worker reminders** — N days before a report due date, and on overdue, through
   the existing alert plumbing to the grant manager.

### House rules this build has to honour

No page width caps (density by packing). Buttons never disabled and never hidden
— validate on click and name what is missing. `CBMDateTime` for every date,
never a raw `datetime-local`. `CBMRichText` for every wysiwyg. `busy.js` first on
any new page, and `{{org}}` + the `cbm-org` meta tag instead of the organisation's
name. Every mutating action through `core/action_log`. Feature-detect each new CRM
field so the feature stays dark until the CRM has it. A currency write must
backfill its `*Currency` companion (this bit the ledger once). List pages are
capped at 200 — an oversized `maxSize` is a 403 that reads as an empty list.
Ship behind **`GRANTS_ENABLED`, checked per request** (the `record_quick_add`
pattern), not at router-mount time, so it is toggleable at `/setup` rather than
denylisted as boot-read.

---

## 4. Phasing

| Phase | What | Depends on |
|---|---|---|
| **0** | Expose `CEvent.sponsorProfiles` in the events editor | — |
| **1** | CRM build: three entities, four links, role grants on crm-test then prod | Ruling #1 |
| **2** | Grants tab + grant popup + deliverables, **manual measurement only** | Phase 1 |
| **3** | Built-in automatic measures + progress and status derivation, incl. the Funded Clients panel | Phase 2 |
| **4** | Report builder → compose hand-off → freeze → file to Drive → action log | Phase 2 |
| **5** | Due/overdue queue, worker reminders, renewal lineage (retiring the inert `nextGrantDeadline`) | Phase 4 |
| **6** | The rating engine (its own arc — `prds/rating-engine-plan.md`); turns rating deliverables automatic | that plan |
| **7** | `analytics:` measure delegation; a Grant dashboard on the funder record scope | Phase 3 |

Phase 2 is genuinely useful on its own: it replaces whatever spreadsheet is
holding this today, and every later phase removes typing from it.

## 5. Rulings needed before anything is built

1. ~~**Grant as its own entity**, with `CContribution` rows linked to it as
   payments?~~ **RULED (Doug, 2026-08-23): yes — the grant is the hub, tied to
   contributions and to deliverables, which are siblings rather than a chain.
   No deliverable→contribution link; the performance-tranche case is deferred to
   an optional `CContribution.contingentOn` → `CGrantReport`.**
2. ~~**Attribution** — how does a client belong to a grant?~~ **RULED (Doug,
   2026-08-23): the link lives on the GRANT** —
   `CGrant.fundedEngagements` ↔ `CEngagement`. Still open: whether a single
   deliverable may opt into programme-wide counting instead.
3. ~~**Frozen report results as JSON, or a fourth entity?**~~ **RULED (Doug,
   2026-08-23): the JSON snapshot on `CGrantReport` — three entities.**
4. ~~**Ratings** — captured in-house or typed in from an outside tool?~~
   **RULED (Doug, 2026-08-23): in-house — CBM is building the entire rating
   engine into this system.** Scoped as its own arc; the grant build treats it as
   a dependency and ships rating deliverables as Manual until it exists.
5. **The report artifact** — an email to the funder with the numbers in the body
   (recommended, reuses compose and thread-anchoring), or a generated PDF?
6. **Can one grant come from two funders?** (Recommend no — one funder, many
   grants.)
7. **Budget and expense tracking against a grant** — in or out? (Recommend out;
   the CRM holds no expense data.)
8. **Who may see and edit grants** — the Sponsor Management Team as it stands, or
   a narrower group? Grant obligations are a different sensitivity from the
   funder record.

## 6. CRM prerequisites (Doug)

- Build `CGrant`, `CGrantDeliverable`, `CGrantReport` and the four links, in the
  Entity Manager, per the naming trap in CLAUDE.md — **the Create Link dialog
  inverts the two Name boxes**, and this has been got wrong four times.
- Add `CContribution.grant`, and `CGrant.fundedEngagements` ↔ `CEngagement`.
- Role grants for the Sponsor Management Team on all three entities: create /
  read / edit, **no delete** (the contributions precedent — cancellation is a
  status).
- crm-test first, then prod, with an enum-option parity check between them.

## 7. Out of scope (candidates, not commitments)

Grant *seeking* (prospect discovery, application drafting, proposal library),
expense and budget tracking, subrecipient monitoring, a funder-facing portal
where the funder reads the report themselves, and multi-currency.

---

## Sources for §1

- [Instrumentl — Best Grant Management Software for Nonprofits](https://www.instrumentl.com/blog/best-grant-management-software)
- [GrantVantage — Grant Administration](https://www.grantvantage.com/solutions/grant-administration/)
- [AmpliFund — Features](https://www.amplifund.com/features/) and the AmpliFund
  recipient guides documenting the six goal types
  ([Colorado Judicial](https://www.coloradojudicial.gov/sites/default/files/2025-11/Grants%20Management%20Recipient%20Guide.pdf))
- [Submittable — Understanding Goal Types in a Goals & Milestones Section](https://next.support.submittable.com/hc/en-us/articles/38701453864599-Understanding-Goal-Types-in-a-Goals-Milestones-Section)
- [Microsoft Learn — Unify program and impact data (indicators, baseline/target/actual)](https://learn.microsoft.com/en-us/industry/nonprofit/outcome-management)
- [Sage — Post-award grant management for nonprofits](https://www.sage.com/en-us/blog/post-award-grant-management-for-nonprofit/)
- [OpenGrants — Grant reporting requirements, deadlines, clawbacks](https://opengrants.io/grant-reporting-requirements-deadlines-clawbacks/)
