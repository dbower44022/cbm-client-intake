# Prospect Marketing — rulings

Last Updated: 10-20-26 17:47 · Revision 1.32 — change log at the end.

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

### Doug's ruling (10-17-26, on the Phase 2 live pass)

Step B8 found two fields labelled *Campaign* on Contact and Company: the
native `campaign` link to EspoCRM's own `Campaign` entity, and ours. Doug:
"It is terrible design practice to have two fields with the same name. We
either need to rename ours, or remove the existing, but we cannot leave two
fields with the same name." Removal is impossible (a system link), and a
custom field never takes a built-in field's name. Doug's reply at 22:48:
"rename ours".

35. **In the CRM our entity and its links are labelled "Outreach Campaign"**
    — the entity, its plural, and the link and field on the eight records
    that carry it. The application's own screens keep the word "Campaign"
    (CM-11); the application has no native field to collide with. Labels
    only — no stored name changes. Every CRM, by
    `scripts/relabel_outreach_campaign.py`. (10-17-26)

### Doug's ruling (10-18-26, at the start of the Phase 3 build session)

Build plan § 9 question 6, put as a consequential decision: option A, the
campaign's teams decide and each caller acts as themself; option B, the
same teams but the application reads and writes under the org-wide API key;
option C, a fixed Marketing Admin Team gate. Doug's reply at 00:12: "a".

36. **Callers are the members of the teams named on the campaign, and each
    caller acts as themself** (option A). The campaign's `teams` field is
    read live on every request; its default is the Marketing Admin Team;
    naming the Mentor Team opens the call screen to mentors with no second
    gate; an administrator always passes. When the campaign names callers,
    each caller sees only their own rows, else the whole list (§ 3.4). The
    call list reads and the outcome writes run as the signed-in user, so the
    CRM records the caller. The Mentor Role gains `COutreachTouch` read and
    edit and `CProspect` read on every CRM, merge-only, by
    `scripts/migrate_outreach_roles.py` — Doug runs its `--apply`.
    (10-18-26)

### Doug's ruling (10-18-26, on the Phase 2 live pass's rung finding)

The pass found the information request door writing `cFunnelStage = Warm
Lead` on Pia Phase, a Contact already typed Client. Put as a consequential
decision: option A, skip the rung on a record already holding a
relationship type; option B, leave it and filter in reports. Doug's reply at
00:13: "a".

37. **A door's rung evidence never lands on a record that already holds a
    relationship type** (option A). The information request and registration
    doors leave `cFunnelStage` untouched on a matched Contact whose
    `cContactType` holds Client, Partner, Sponsor or Mentor, and on a
    promoted Company whose `cCompanyType` holds Client, Partner or Sponsor.
    A record typed only Prospect, or untyped, still advances. The ladder is
    for prospects; a client's rung is read from the engagement (§ 1.8). A
    rung already written that way is left alone. (10-18-26)

### Doug's ruling (10-18-26, at the start of the Phase 4 build session)

Build plan § 9 question 11, put as a consequential decision: option A, the
SMS kind builds, signs off and exports its list and staff send from their
own tool; option B, the application sends through a texting service. Doug's
reply at 01:53: "b" — against the recommendation.

38. **The application sends a text-message campaign itself** (option B),
    through a texting service, at sign-off, as the postcard run hands its
    pieces to the mail vendor. The selection stays ruling 9's: a Contact with
    `cSmsOptIn` true, a phone, not opted out. Sending makes the chapter the
    sender in law, so an opt-out reply (STOP) is honoured at once and written
    back to the Contact, and the vendor account, its sender number and the
    carrier registration a United States sender needs are prerequisites
    before the first real text. (10-18-26)

### Doug's ruling (10-18-26, on where the text's wording lives)

Ruling 38 needs a place for the message itself; the campaign carried none.
Put as a consequential decision: option A, a new text field on the campaign
in the CRM; option B, the application's own database beside the links
(ruling 31). Doug's reply at 01:58: "a".

39. **A text-message campaign's wording is a field on the campaign in the
    CRM** (option A): `COutreachCampaign.smsMessage`, plain text, written on
    the campaign's form in Campaign Management and frozen at sign-off. It is
    campaign content, and the CRM is the system of record; it travels to
    every CRM as one field (`scripts/plans/coutreach-sms-message.json`).
    Decided with it, unless Doug says otherwise: Twilio as the texting
    service behind a dry-run client that is the default; a STOP reply sets
    the Contact's `cSmsOptIn` false; sends only between 9:00 and 20:00
    chapter time; an interrupted send is flagged for review, never resent
    by itself. (10-18-26)

### Doug's ruling (10-18-26, on the Phase 4 pass's finding)

The pass (step B2) found the campaign card's ticks snapping back after
*Build the list*: the eight campaign fields the application writes had been
built Read-only, which EspoCRM enforces as a restriction on every writer, so
none had ever stored. Put as a consequential decision: option A, clear
Read-only and keep staff off by field-level rule; option B, clear it only;
option C, store them in the application's database. Doug's reply at 11:05:
"a".

40. **The fields the application writes on a campaign are not Read-only in
    the CRM; staff are kept off them by field-level rule** (option A). The
    eight — the rule and its summary, the signed-off count and cost, who
    signed off and when, the run's start and finish — are written by the
    application under the org-wide API key; the Marketing Admin Role reads
    them and cannot edit them. Never build a field the application writes as
    Read-only. (10-18-26)

### Doug's rulings (10-18-26, evening — the lead model)

Made in a Cowork session writing an executive overview of the arc for
the chapter's leadership. Doug found the arc's names unfamiliar ("prospect
record", "door") and asked for the names other CRMs and common practice
use. The research (EspoCRM's own Lead, Microsoft Dynamics 365, Salesforce,
HubSpot's lifecycle stages; sources in the overview) found the raw record
is called a **Lead** almost everywhere, is **qualified** or
**disqualified**, and is **converted** into a company and a contact; and
that common usage puts the lead *before* the prospect, the reverse of this
arc. Doug then ruled in four replies. Rulings 41 and 42 are his words; 43
and 44 were put as consequential decisions.

41. **Every record entered from an outside source is a Lead, and "door"
    is retired.** Doug: "I think we should use Unqualified Lead to define
    raw information brought in from outside regardless of the 'Lead
    Source'. I think we need to get rid of the term Door too." And in the
    next reply: "Any new record entered into the system from an outside
    source is named a 'Lead'." This renames the prospect record of ruling
    21 (the stored entity `CProspect` is unchanged by this ruling). Where a
    lead came from is its **Lead Source**. (10-18-26)
42. **A lead is Unqualified, Qualified or Disqualified; contact makes it a
    Prospect.** Doug, word for word: "If we do not have a concrete
    understanding if the lead is a real company or person that may
    eventually be interested in our services it has a status of
    'Unqualified' and it needs further information to become qualified. A
    company without an website or a contact without a email can never be
    'Qualified'. A lead that has an email or website is still not
    qualified if we do not understand if they may some day be a client. If
    we know that they will NEVER be a client/partner/funder then they
    become a disqualified lead. If we find out they may be a
    client/partner/funder but we have not contacted them, or they have not
    responded to a marketing outreach, they become a qualified lead. Once
    we have some contact, they can become a prospect." This changes
    rulings 10 and 11 (a state filing no longer enters Qualified on the
    outside filter's verdict: without a website or email it is
    Unqualified), 18 (a list row enters Unqualified, not Unverified) and 29
    (rung 1 is Unqualified; the fit-failure side exit is Disqualified).
    (10-18-26)
43. **A Company or Contact is created only at first contact.** Put as a
    consequential decision: option 1, the lead holds everything until
    first contact, when the Company and/or Contact is created typed
    Prospect and the lead is marked converted; option 2, the Company
    and/or Contact is created when the lead is qualified and retyped
    Prospect at first contact. Doug's reply: "1". This changes ruling 21's
    promotion rule (a web domain or an email no longer creates a Company or
    Contact by itself) and ruling 33 (the import creates no Company or
    Contact). (10-18-26)
44. **A campaign may select Unqualified leads.** Put as a consequential
    decision: option 1, postcards and calls may select Unqualified leads,
    a response that brings a website or email converts the lead straight to
    a Prospect, and a lead that never responds stays Unqualified until the
    Stale sweep; option 2, only Qualified leads are selectable; option 3,
    the outside filter's screening counts as qualification. Doug's reply:
    "1". Ruling 42's rule that a lead without a website or email is never
    Qualified stands whole. (10-18-26)

### Doug's ruling (10-19-26, on build plan § 9 question 13)

Put as a consequential decision in a Claude Code session: option A, change
the stored option values on `CProspect`, Contact and Account and move the
existing records with a dry-run-first script; option B, relabel the options
in the CRM and keep `Unverified`, `Lead`, `Warm Lead` and `Already known` as
stored values. Doug's reply at 01:09: "a".

45. **The rework changes the stored values, not only the labels**
    (option A). The CRM, the code, the screens and the documents carry one
    word per stage. Existing records are moved by a one-time script that
    reports before it writes, applied on crm-test first, then production
    at a Sunday slot, then Boston with its release; each CRM's records are
    counted before the script runs. (10-19-26)

### Doug's ruling (10-19-26, on build plan § 9 question 14)

Put as a consequential decision in the same session: option A, the
Responses tab shows Responded, Converted (leads that became Prospects) and
Became a client, partner or funder, and documents call ruling 22's event "a
relationship begins"; option B, Converted keeps its old meaning and the
lead-to-Prospect step takes another word. Doug's reply at 01:20: "a".

46. **"Converted" means a lead became a Prospect; a campaign's win is
    "became a client, partner or funder"** (option A). The Responses tab
    and the campaign dashboard show three counts: Responded, Converted and
    Became a client, partner or funder. The third is computed as Converted
    is today (a relationship record carries the campaign). Documents call
    ruling 22's event "a relationship begins"; ruling 22 stands as
    recorded. (10-19-26)

### Doug's ruling (10-19-26, on build plan § 9 question 15)

Put as a consequential decision in the same session: option A, a call
marked Interested converts the lead only when the caller records an email
or a website; option B, Interested converts on its own and creates a
phone-only Company or Contact. Doug's reply at 01:21: "a".

47. **A call marked Interested converts the lead only with an email or a
    website** (option A). Choosing Interested asks the caller for an email
    and a website; either one converts the lead (Company and/or Contact
    typed Prospect, the lead Converted). With neither, Interested is
    recorded on the call, the lead stays a lead and the screen says why,
    and *Call again* is offered as for No answer. A typed email is matched
    as on the public forms, so a known email reuses its Contact. This
    applies ruling 44's "a response that brings a website or email
    converts the lead". (10-19-26)

### Doug's ruling (10-19-26, on build plan § 9 question 16)

Put as a consequential decision in the same session, with the
recommendation changed from the build plan's because ruling 41 reads "Any
new record entered into the system from an outside source is named a
'Lead'": option A, a public-form arrival creates the Prospect directly and
no lead; option B, every public form that creates a new Company or Contact
also creates a lead, marked Converted at once, its Lead Source the form.
Doug's reply at 01:22: "b".

48. **Every new record from a public form has a lead behind it**
    (option B). A public form that creates a new Company or Contact also
    creates a lead, Converted at once, with the form as its Lead Source, so
    Lead Source answers "where did they come from" for every record. A
    repeat submitter whose record already exists gets no new lead. The
    lead is written retry-safe with the rest of the delivery and never
    loses the submission. A client, partner or funder form converts its
    lead straight to the relationship. Drafted, not ruled: the staff
    screens that create records are not an outside source and create no
    lead. (10-19-26)

### Doug's ruling (10-19-26, at the start of the lead-model CRM handoff session)

Put as a consequential decision: option A, a lead's status lives in the
existing `CProspect.funnelStage` field with new options and the label
"Lead status"; option B, a new field `leadStatus` holds it and
`funnelStage` / `entryStage` on the lead stop being used, their removal
proposed in the handoff for Doug to approve. crm-test held no `CProspect`
records when this was put. Doug's reply at 10:44: "b".

49. **A lead's status is a new field, `leadStatus`** (option B): an enum of
    Unqualified · Qualified · Disqualified · Converted, default Unqualified,
    with a `leadStatusChangedAt` stamp, not Read-only (ruling 40). The
    lead's `funnelStage` and `entryStage` stop being used; their removal is
    proposed in the handoff, never done without Doug's approval. (10-19-26)

### Doug's ruling (10-19-26, on build plan § 7a.2's drafts)

Put as a consequential decision in the same session: option A, approve the
four drafts the CRM handoff builds on as written; option B, change one or
more. Doug's reply at 10:49: "a".

50. **The four § 7a.2 drafts are approved as written** (option A):
    a Company's or Contact's stages after first contact are **Prospect ·
    Engaged · Opportunity** (Engaged replaces Warm Lead, ruling 17's
    meaning); the reasons a lead stops being worked are **Duplicate · Do
    Not Contact · Declined · Stale** (Duplicate replaces Already known;
    Disqualified is a status, not a reason); the lead entity's CRM label is
    **Outreach Lead** and the screens say **Lead**; **Lead Source** is a
    field on the lead only, and the Contact's Source (ruling 26) is
    untouched. The draft "a scan alone does not convert" is left for the
    code session. (10-19-26)

### Doug's ruling (10-19-26, at the start of the lead-model code session)

Put as a consequential decision: option A, a postcard scan is recorded on
the touch and the lead (`firstScannedAt`, `scanCount`, outcome Scanned)
and changes no status; option B, a scan makes an Unqualified lead
Qualified. Doug's reply at 11:10: "a".

51. **A scan alone changes no status** (option A). The scan is recorded
    on the touch and the lead and moves nothing: the lead stays
    Unqualified or Qualified, and a converted lead's Company stays at
    Prospect. This changes ruling 16's "a scan of the postcard's code alone
    moves the company to Lead"; its rule that the landing page shows only
    what is printed on the card stands. (10-19-26)

### Doug's ruling (10-19-26, on converting a business lead with an email only)

Put as a consequential decision in the same session: option A, conversion
creates the Company from a business lead (its name and mailing address,
matched by name and postal code, a given website checked as the public
forms check it) plus the Contact for the email, linked to it; option B,
an email creates only a Contact and the Company waits for a website.
Doug's reply at 11:13: "a".

52. **A business lead converts to a Company and its Contact** (option A).
    When a business lead converts — a landing-page response, a call marked
    Interested, or a public form carrying the lead's id — the Company is
    created from the lead even without a website, and the Contact for the
    email is linked to it. A person lead with no business name converts to
    a Contact only. This changes ruling 21's rule that only a web domain
    creates a Company. (10-19-26)

### Doug's ruling (10-19-26, on how a state filing enters)

Put as a consequential decision in the same session, because ruling 42's
note and build plan § 7a.3 read differently: option A, a state-filing row
carrying a website or an email enters Qualified on the outside filter's
verdict (ruling 11), and every other row enters Unqualified; option B,
every row enters Unqualified. Doug's reply at 11:20: "a".

53. **A state filing with a website or an email enters Qualified**
    (option A), with the outside filter recorded as Qualified by and the
    time as Qualified at (ruling 11). A filing row with neither, and every
    list or partner-file row, enters Unqualified (rulings 18, 42). The
    import creates no Company or Contact (ruling 43). (10-19-26)

### Doug's ruling (10-19-26, on the lead model's live pass)

Doug reported that Mark Marketing had no Companies in the crm-test CRM. The
Marketing Admin Role holds no Company grant, and production's 08-31 role
standard has none either. Put as a consequential decision: option A, grant
the role read-only access to all Companies; option B, leave it. Doug's reply
at 12:23: "a".

54. **The Marketing Admin Team reads every Company, read only** (option A).
    The Marketing Admin Role gains Account read *all*, with create, edit,
    delete and stream left at no; the application keeps making and editing
    Companies under its own account (ruling 33). Applied through
    `scripts/migrate_outreach_roles.py` on crm-test first, then production
    at a Sunday slot and Boston with its release; the role standard is
    updated to match. (10-19-26)
55. **Social media is one campaign kind with a Platform field** (option A,
    build plan § 9 question 10). Kind says how a campaign runs; the platform
    (Meta, YouTube, LinkedIn, Instagram, X, Other) is its own field, shown
    only for a Social media campaign. A new platform is one new option on
    that field. Confirms what Phase 1 built; nothing changes. (10-20-26)
56. **The lead screens stay inside the Campaign Management tile** (option A,
    build plan § 9 question 12): Campaigns, Leads, Review, Calls and Imports
    on one page's top bar, one tile, one team. Doug added in the same
    answer: "we need to dramatically improve the 'Leads' and 'Review' grids
    to handle a large number of records, and provide better searching and
    qualifying" — a requirement being gathered, build plan § 7b. (10-20-26)
57. **A campaign names its funders, like its partners** (option A). A
    many-to-many link from the campaign to the funder profile, a *Funders*
    picker beside *Partners* on the campaign form, and a Campaigns tab on
    every funder record with the partner tab's counts (CM-5's twin, under
    Doug's rule that Partner and Funder Management never differ). Funders
    get no credit on the records a campaign brings in — CM-4 stays
    partner-only. A CRM link on every CRM: crm-test first, production at
    the Sunday slot, Boston with its release. (10-20-26)

### Doug's ruling (10-20-26, on who a campaign may target)

Doug asked whether comparable products send a campaign to their whole
database or to a defined list. Research (HubSpot, Salesforce, EspoCRM,
Mailchimp) found every one targets a defined audience — a static list, a
saved filter, or both. Doug's reply at 15:00: "The first decision is that
campaigns may be targeted as leads, clients, partners, funders, contacts or
any combination of all them."

58. **A campaign may target leads, clients, partners, funders, contacts, or
    any combination of them.** A campaign's audience is no longer leads
    alone. Extends ruling 25 (re-marketing over client records) to every
    record type named; how the audience is narrowed within each type, and
    how it is fixed at sign-off, are decisions still to come. (10-20-26)

### Doug's ruling (10-20-26, on which people on a record a campaign reaches)

Put as a consequential decision: when a campaign targets a client, partner
or funder, option A, the primary contact only; option B, every contact on
the record; option C, the primary contact by default, with a per-campaign
switch for every contact. Doug's reply at 15:08: "c".

59. **A campaign reaches the record's primary contact, unless staff tick
    "Include every contact on the record"** (option C). The switch is per
    campaign, and the audience count before sign-off reflects it. Approved
    with it, as presented: consent still applies person by person (ruling
    19 for email, ruling 9 for texts); a postcard goes to the
    organisation's mailing address and is outside this ruling; one address
    reaches one person, the first contact holding it; "primary" is the link
    the record already holds (the engagement's primary contact, the
    partner's or funder's "Make primary" contact); a record with no primary
    contact is skipped and counted on the sign-off screen, never guessed.
    (10-20-26)

### Doug's ruling (10-20-26, on what "contacts" means as a campaign target)

Put as a consequential decision, with the crm-test CRM's Contact type list
read live (Client, Mentor, Partner, Administrator, Presenter, Donor,
Member, Prospect, Sponsor, or none): option A, every Contact in the CRM;
option B, a contact-type picker; option C, every Contact belonging to none
of the other four targets. Doug's reply at 15:13: "b".

60. **A campaign targeting contacts names the contact types it reaches**
    (option B). Staff tick types from the CRM's live type list, plus "No
    type" for an untyped Contact; nothing is ticked by default. Approved
    with it, as presented: a Contact chosen as itself is its own recipient
    (ruling 59's primary-contact rule does not apply); a person reached
    through two targets receives one message; a ticked Mentor, Member or
    Administrator is addressed at their `cbmEmail` only, or skipped
    without one; consent still applies person by person (rulings 9 and
    19). (10-20-26)

### Doug's rulings (10-20-26, on static and dynamic lists)

Doug set the order: "The first question we need to ask is if the list is
dynamic or static. I think that we want to support both." Research found
two ways products build a static list: filters frozen once at creation
(HubSpot's snapshot list) and accumulating search results with "Add to"
(Salesforce campaign members, EspoCRM target lists). Doug added that
accumulating means several queries ("All records in the area code" then
"add all records with industry type = ..."); each Add widens the list, so
narrowing needs a "Keep only matching" step. Doug's reply at 15:28 to both
questions: "yes to both".

61. **A campaign's audience may be a static list or a dynamic list.** Both
    are supported. (10-20-26)
62. **A list is an ordered recipe of steps:** Add matching (widens), Keep
    only matching (narrows), Remove matching (excludes), records ticked in
    or out by hand, and a file import. Each step shows how many records it
    added or dropped. A **static** list runs the recipe once, is frozen,
    and is then edited by hand; a **dynamic** list runs the same recipe
    again before every send. One editor serves both, and the kind is one
    setting. Presented with it at 15:18 and not contested: membership of
    a list never overrides the checks made at send time — consent
    (rulings 9 and 19), a Do Not Contact or Disqualified exit, a dead
    address (ruling 15), one card per business (ruling 14) — and the
    sign-off count shows who was skipped and why. Still to be ruled: how
    hand edits survive a dynamic list's next run, which conditions a step
    may use, and whether a list belongs to one campaign or is reusable.
    (10-20-26)

### Doug's ruling (10-20-26, on which conditions a list step may use)

Put as a consequential decision: option A, a curated field list per record
type fixed in code; option B, any field through a general builder; option
C, a curated field list per type that administrators edit at `/setup`.
Doug's reply at 15:32: "c".

63. **A list step's fields come from a curated list per record type that
    administrators edit at `/setup`** (option C). Staff see only the
    reviewed fields, with plain labels and option values read live from
    the CRM; an administrator adds or removes a field without a deploy,
    validated against live CRM metadata and recorded in the settings
    history. Approved with it, as presented: a step may hold several
    conditions, all of which must match (either-or is two Add steps);
    operators follow the field's type (is one of / is not one of; contains
    / starts with; before / after / within the last N days; at least / at
    most; is empty / is not empty); the shipped default list is
    leads — status, source, industry, postal code; clients — engagement
    status, close date, industry; partners and funders — status, manager;
    contacts — type — with the full table brought to Doug in
    `build-plan.md` for approval; a field that leaves the CRM drops out
    of the list and is flagged on the recipe, never silently ignored.
    (10-20-26)

### Doug's ruling (10-20-26, on whether a list belongs to one campaign)

Put as a consequential decision: option A, a list lives inside its
campaign and is reused only by copying; option B, named lists on their own
screen that several campaigns use. Doug's reply at 15:47: "b".

64. **Lists are named records on their own *Lists* tab in Campaign
    Management, and a campaign picks the list it sends to** (option B). An
    edit to a list reaches every campaign using it at that campaign's next
    send. Approved with it, as presented: a change never reaches a send
    already under way (a static list stays as frozen; a dynamic list runs
    its recipe again only at the start of each send; ruling 13's typed
    piece count still guards a postcard); a list in use is retired, never
    deleted, and stays readable on the campaigns that used it; a recipe
    step may add or remove the members of another list, which is how a
    standing exclusion list works; each campaign records the list and
    version it sent to; the recipe, frozen membership and history live in
    the application database, like campaign links (ruling 31), and touches
    stay in the CRM — no CRM change; lists are edited by the Marketing
    Admin Team, the campaigns gate. (10-20-26)

### Doug's ruling (10-20-26, on hand edits to a dynamic list)

Put as a consequential decision: option A, hand edits become standing
"always include" / "always exclude" entries applied after the recipe on
every run; option B, a dynamic list takes no hand edits; option C, hand
edits last until the next run. Doug's reply at 15:49: "a".

65. **A hand edit on a dynamic list becomes a standing entry** (option A):
    "always include" or "always exclude", applied after the recipe on
    every run, shown in its own panel on the list with who made it and
    when, and removable. The send-time checks still apply to an "always
    include". Approved with it, as presented: on a static list a hand tick
    simply changes the frozen membership; a standing entry whose record no
    longer exists in the CRM is flagged, never silently dropped; each
    entry carries who, when and an optional note; a standing entry is not
    a Do Not Contact exit — a person no campaign may contact still takes
    the lead's Do Not Contact action. (10-20-26)

### Doug's ruling (10-20-26, on build plan § 9 question 17)

Put as a consequential decision: the lead record holds no industry, and the
Ohio filing carries none. Option A, add an industry field to the lead,
filled by imports, in the Review queue and in the lead's window; option B,
filter by the converted Company's industry only; option C, no industry on
leads. Doug's reply at 17:47: "a".

66. **A lead carries an industry** (option A). `CProspect.industry`,
    labelled *Industry*, a choice field whose options are kept identical
    to the Company's sector list (`Account.cIndustrySector`). Filled by an
    import whose file has an industry column, by the reviewer in the
    Review queue beside the Website and Email boxes, and in the lead's
    window. Optional, never a gate on Qualify. On conversion it carries to
    the Company by null-fill only. Its own CRM handoff and plan file;
    crm-test first, production at its slot, Boston with its release. It
    joins the lead's step fields (ruling 63). (10-20-26)

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
| Version | 1.32 |
| Last Updated | 10-20-26 17:47 |
| Prepared by | Claude (Claude Code), for D. Bower |
| Source | `history/prospect-marketing-plan.md` v0.6 (10-14-26 21:55), sections *Doug's rulings (2026-08-11)*, *Doug's rulings (2026-10-13 and 2026-10-14)*, *The ladder as it stands*, *The walk, source by source*, *Doug's requirements (10-14-26)* |

### Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.32 | 10-20-26 17:47 | Claude (Claude Code) | Ruling 66 appended: a lead carries an industry (Doug's "a" to build plan § 9 question 17). |
| 1.31 | 10-20-26 15:50 | Claude (Claude Code) | Ruling 65 appended: a hand edit on a dynamic list becomes a standing include/exclude entry (Doug's "a"). Campaign-audience rulings 58–65 complete. |
| 1.30 | 10-20-26 15:48 | Claude (Claude Code) | Ruling 64 appended: named reusable lists on a Lists tab; a campaign picks its list (Doug's "b"). |
| 1.29 | 10-20-26 15:33 | Claude (Claude Code) | Ruling 63 appended: list-step fields come from a per-type curated list editable at `/setup` (Doug's "c"). |
| 1.28 | 10-20-26 15:29 | Claude (Claude Code) | Rulings 61 and 62 appended: static and dynamic lists both supported; a list is an ordered recipe of steps (Doug's "yes to both"). |
| 1.27 | 10-20-26 15:13 | Claude (Claude Code) | Ruling 60 appended: a campaign targeting contacts names the contact types it reaches (Doug's "b"). |
| 1.26 | 10-20-26 15:08 | Claude (Claude Code) | Ruling 59 appended: a campaign reaches the primary contact unless staff tick "Include every contact on the record" (Doug's "c"). |
| 1.25 | 10-20-26 15:02 | Claude (Claude Code) | Ruling 58 appended: a campaign may target leads, clients, partners, funders, contacts, or any combination (Doug's first decision on campaign audiences). Revision table's Version and Last Updated brought up to date (they read 1.21). |
| 1.24 | 10-20-26 14:36 | Claude (Claude Code) | Ruling 57 appended: a campaign names its funders, like its partners (Doug's "a"). |
| 1.23 | 10-20-26 01:16 | Claude (Claude Code) | Ruling 56 appended: the lead screens stay inside the Campaign Management tile (Doug's "a" to build plan § 9 question 12), with his new requirement for the Leads and Review grids quoted. |
| 1.22 | 10-20-26 01:08 | Claude (Claude Code) | Ruling 55 appended: social media is one campaign kind with a Platform field (Doug's "a" to build plan § 9 question 10). |
| 1.21 | 10-19-26 12:23 | Claude (Claude Code) | Ruling 54 appended: the Marketing Admin Team reads every Company, read only (Doug's "a"). |
| 1.20 | 10-19-26 11:20 | Claude (Claude Code) | Ruling 53 appended: a state filing with a website or an email enters Qualified (Doug's "a"). |
| 1.19 | 10-19-26 11:13 | Claude (Claude Code) | Ruling 52 appended: a business lead converts to a Company and its Contact, even without a website (Doug's "a"). |
| 1.18 | 10-19-26 11:10 | Claude (Claude Code) | Ruling 51 appended: a scan alone changes no status (Doug's "a" to build plan § 7a.2's last draft, at the start of the lead-model code session). |
| 1.17 | 10-19-26 10:49 | Claude (Claude Code) | Ruling 50 appended: build plan § 7a.2's four CRM-facing drafts approved as written (Doug's "a"). |
| 1.16 | 10-19-26 10:44 | Claude (Claude Code) | Ruling 49 appended: a lead's status is a new field `leadStatus` (Doug's "b", lead-model CRM handoff session). |
| 1.15 | 10-19-26 01:22 | Claude (Claude Code) | Ruling 48 appended: every new record from a public form has a lead behind it, Converted at once (Doug's "b" to build plan § 9 question 16, the session's revised recommendation). |
| 1.14 | 10-19-26 01:21 | Claude (Claude Code) | Ruling 47 appended: a call marked Interested converts the lead only with an email or a website (Doug's "a" to build plan § 9 question 15). |
| 1.13 | 10-19-26 01:20 | Claude (Claude Code) | Ruling 46 appended: "converted" means a lead became a Prospect; the win is "became a client, partner or funder" (Doug's "a" to build plan § 9 question 14). |
| 1.12 | 10-19-26 01:09 | Claude (Claude Code) | Ruling 45 appended: the lead-model rework changes the stored values, not only the labels (Doug's "a" to build plan § 9 question 13). |
| 1.11 | 10-18-26 23:16 | Claude (Cowork) | Rulings 41–44 appended: the lead model — Lead for every record from outside, "door" retired (41); Unqualified / Qualified / Disqualified, Prospect at contact (42); Company or Contact created only at first contact (43, Doug's "1"); campaigns may select Unqualified leads (44, Doug's "1"). The ladder table and the walk above are left as recorded; build plan v0.8 § 7a carries the new ladder. |
| 1.10 | 10-18-26 11:20 | Claude (Claude Code) | Ruling 40 appended: app-written campaign fields are not Read-only; a field rule keeps staff off them (Doug's "a", Phase 4 pass finding). |
| 1.9 | 10-18-26 02:00 | Claude (Claude Code) | Ruling 39 appended: the text's wording is a campaign field in the CRM (Doug's "a"), with the follow-on details decided. |
| 1.8 | 10-18-26 01:55 | Claude (Claude Code) | Ruling 38 appended: the application sends text-message campaigns itself (Doug's "b" to build plan § 9 question 11, against the recommendation). |
| 1.7 | 10-18-26 00:16 | Claude (Claude Code) | Ruling 37 appended: no rung evidence on a record already holding a relationship type (Doug's "a", Phase 2 live pass finding). |
| 1.6 | 10-18-26 00:14 | Claude (Claude Code) | Ruling 36 appended: callers are the campaign's teams, acting as themselves; the Mentor Role gains COutreachTouch read/edit and CProspect read (Doug's "a" to build plan § 9 question 6, at the start of the Phase 3 build). |
| 1.5 | 10-17-26 22:50 | Claude (Claude Code) | Ruling 35 appended: "Outreach Campaign" as the CRM label (Doug's "rename ours", Phase 2 live pass B8). |
| 1.4 | 10-17-26 01:54 | Claude (Claude Code) | Ruling 34 appended: the information request door creates its company typed `Prospect` (Doug's "A" to build plan § 9 question 7, at the start of the Phase 2 build). |
| 1.3 | 10-15-26 02:16 | Claude (Claude Code) | Ruling 33 appended: the import's Company and Contact writes run under the intake API client (Doug's "a" at the start of the Phase 1 build). |
| 1.2 | 10-15-26 00:02 | Claude (Claude Code) | Ruling 32 appended: the ruling-27 reverse link on the campaign is `attributedPartnerProfiles` (Doug's "1" to the handoff's item (a)). |
| 1.1 | 10-14-26 22:42 | Claude (Claude Code) | Rulings 28–31 appended: Doug's answers to build plan § 9 questions 1, 3, 8 and 9 (custom entities; `Unverified`; multiple referring partners on an engagement; links in the application database). |
| 1.0 | 10-14-26 22:25 | Claude (Claude Code) | Created when the arc was consolidated into `prds/prospect-marketing/` (Doug's ruling, 10-14-26: a directory on the chapter-network pattern). Rulings 1–27, CM-1 to CM-11 and the two tables copied verbatim from the process plan; no ruling changed. |
