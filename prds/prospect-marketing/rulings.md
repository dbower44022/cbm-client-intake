# Prospect Marketing — rulings

Last Updated: 10-17-26 01:54 · Revision 1.4 — change log at the end.

**This file is the binding record of the arc.** It holds, word for word,
every decision Doug has made about prospect marketing and the Campaign
Management application: rulings 1–8 (2026-08-11), rulings 9–27
(2026-10-13/14) and requirements CM-1 to CM-11 (10-14-26), with the two
tables the rulings refer to. Nothing else is in it — no proposals, no
working positions, no strawmen. Those are in `history/` with the discussion
that produced them, and the build plan (`build-plan.md`) cites them where
it drafts on one.

**How this file changes.** Only by appending: a new ruling takes the next
number (28 onward) with its date; a changed ruling is a new ruling naming
the one it changes, and the old text stays. When Doug answers a question in
the build plan's § 9, the answer is written here as a ruling and the
question is marked answered there. The text of a ruling is never edited
after it is recorded. The copies were extracted from
`history/prospect-marketing-plan.md` v0.6 on 10-14-26, unchanged except
that the first heading was brought to the same level as the others.

---

## Rulings

### Doug's rulings (2026-08-11)

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

### Doug's rulings (10-14-26, on the build plan's § 9 questions)

Answered in one reply at 22:41 on 10-14-26: "your recommendation, except
for #3 [question 8] — we need to support multiple partner referrals to a
single engagement." Each is recorded as the ruling it is; the build plan
marks the question answered.

28. **Custom entities, not EspoCRM's own Lead and Campaign** (build plan
    question 1). `CProspect`, `COutreachCampaign` and `COutreachTouch` are
    built as custom entities; the native marketing module stays hidden and
    the native `campaign` link on Contact and Account stays unused.
    (10-14-26)
29. **Rung 1 is stored as `Unverified`** (question 3). `Unqualified` remains
    the fit-failure side exit only. (10-14-26)
30. **An engagement supports multiple referring partners** (question 8 —
    the recommendation of a single partner was declined). A client who
    arrives through a campaign naming several partners is credited to every
    one of them. The build plan says how the single referring partner of
    v0.255.0 and the many-partner link coexist. (10-14-26)
31. **Campaign links live in the application's own database** (question 9),
    not as a fourth CRM entity; the resolve route never calls the CRM.
    (10-14-26)

### Doug's ruling (10-15-26, on the CRM handoff's one open name)

`coutreach-entities-crm-handoff.md` § 0 item (a) put one name to Doug: build
plan § 1.5 gave `COutreachCampaign.partnerProfiles` to two links. Doug's
reply at 00:01 on 10-15-26: "1" — the drafted name.

32. **The reverse of `CPartnerProfile.outreachCampaign` on the campaign is
    `attributedPartnerProfiles`** (the handoff's drafted name, option 1).
    `partnerProfiles` stays the CM-2 many-to-many to the partners a
    campaign names; the funder-side reverse `sponsorProfiles` is unchanged.
    (10-15-26)

### Doug's ruling (10-15-26, at the start of the Phase 1 build session)

The CRM handoff's item (i) left one decision to the build: whose credential
makes the Company and Contact writes, and the already-known reads, when an
import row carries a website or an email. Put as option A (the intake API
client, the quick-add precedent) against option B (Company create and read
plus Contact edit on the Marketing Admin Role). Doug's reply at 02:15: "a".

33. **The import's already-known reads, Company and Contact creates and
    null-fills run under the intake API client** (option A). The
    marketing user's team seat gates the screen; the action log and the
    batch field record who ran the import; Created By on those records is
    the API user, as on every intake-created record. The prospect records
    themselves are created as the signed-in user. No role change. The
    Marketing Admin Role's Contact edit stays *no* (the presenters ruling
    of 10-08-26). Every later import door inherits this shape. (10-15-26)

### Doug's ruling (10-17-26, at the start of the Phase 2 build session)

Build plan § 9 question 7, put as a consequential decision: option A, the
information request door creates its company typed `Prospect` with
`cClientStatus` untouched, against option B, today's `Client` with
`cClientStatus=Prospect`. Doug's reply at 01:53: "A".

34. **The information request door creates a new company typed `Prospect`**
    (option A), `cClientStatus` untouched, so the relabel at conversion
    (ruling 21, § 1.9) is one rule for every door. A company the CRM already
    knows is left with the types it has — the door appends nothing to it.
    The write feature-detects the `Prospect` option on `cCompanyType` and
    falls back to today's shape until a CRM has it (production until its
    Sunday slot). Companies the door created before are relabelled by a
    one-time, dry-run-first script that Doug runs. (10-17-26)

---

## Requirements — the Campaign Management application

Numbered CM-1 onward so they are never confused with rulings 1–27. Gathered
one question per turn on 10-14-26, in DETAIL mode; everything here was
stated by Doug.

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

---

## The two tables the rulings refer to

Ruling 10 says the eight names and three bands of Doug's 2026-09-02 diagram
stand; this is that ladder with the meanings the rulings gave each rung. The
walk is the record of how each of the seven sources moves through it, as
settled on 2026-10-13/14. Rung 1's stored name is build plan question 3.

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

---

## Revision control

| Field | Value |
|---|---|
| Document | Prospect Marketing — rulings |
| Version | 1.4 |
| Last Updated | 10-17-26 01:54 |
| Prepared by | Claude (Claude Code), for D. Bower |
| Source | `history/prospect-marketing-plan.md` v0.6 (10-14-26 21:55), sections *Doug's rulings (2026-08-11)*, *Doug's rulings (2026-10-13 and 2026-10-14)*, *The ladder as it stands*, *The walk, source by source*, *Doug's requirements (10-14-26)* |

### Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.4 | 10-17-26 01:54 | Claude (Claude Code) | Ruling 34 appended: the information request door creates its company typed `Prospect` (Doug's "A" to build plan § 9 question 7, at the start of the Phase 2 build). |
| 1.3 | 10-15-26 02:16 | Claude (Claude Code) | Ruling 33 appended: the import's Company and Contact writes run under the intake API client (Doug's "a" at the start of the Phase 1 build). |
| 1.2 | 10-15-26 00:02 | Claude (Claude Code) | Ruling 32 appended: the ruling-27 reverse link on the campaign is `attributedPartnerProfiles` (Doug's "1" to the handoff's item (a)). |
| 1.1 | 10-14-26 22:42 | Claude (Claude Code) | Rulings 28–31 appended: Doug's answers to build plan § 9 questions 1, 3, 8 and 9 (custom entities; `Unverified`; multiple referring partners on an engagement; links in the application database). |
| 1.0 | 10-14-26 22:25 | Claude (Claude Code) | Created when the arc was consolidated into `prds/prospect-marketing/` (Doug's ruling, 10-14-26: a directory on the chapter-network pattern). Rulings 1–27, CM-1 to CM-11 and the two tables copied verbatim from the process plan; no ruling changed. |
