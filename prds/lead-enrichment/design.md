# Lead and client enrichment — design

Last Updated: 10-22-26 10:50 · Revision 1.3 (approved 10-20-26; § 9 questions 2 and 6 open)

**Status.** Approved by Doug on 10-20-26, section by section. Section 1
records his rulings and is binding (append only). Section 9 lists the two
questions still open: the segment list and the survey fields.

## 0. Terms

- **Enrichment** is adding facts about a business to its record from a
  source outside the record: the type of business, its website, its email,
  and its key contacts.
- **A lead** is a `CProspect` record, as defined by the prospect marketing
  rulings 41 and 42.
- **A client** is a business with a `CClientProfile` and at least one
  `CEngagement`.
- **The free pass** is the enrichment tier that costs nothing per record.
  It reads only what the record already holds and what public sources
  answer without charge.
- **The fit score** is a number from 0 to 100 that the free pass gives a
  lead. It estimates how likely the lead is to be a fit under ruling 10's
  definition.
- **An advanced tier** is any enrichment tier past the free pass. There
  are three: the AI research pass, the paid business-data service, and the
  guided staff research.
- **The AI research pass** is an advanced tier in which an AI model searches
  the web for the business, decides whether each candidate found is the same
  business, and writes a summary with its evidence.
- **Verification** is the check that a found website, email or contact
  belongs to this business and not to a different business with a similar
  name.
- **A finding** is one fact an enrichment tier proposes for one field on one
  record, with its source, its evidence and its confidence.
- **A Client Enrichment Survey** is a fixed questionnaire a mentor sends a
  client. Four are named: Business Status, Financial Status, Marketing
  Status and Technology Status.
- **A survey response record** is the CRM record holding one client's
  answers to one Client Enrichment Survey.

## 1. Rulings (Doug, 10-20-26 — binding, append only)

- **E1. Enrichment escalates in tiers on the same record.** Every lead gets
  the free pass. The free pass gives each lead a fit score, and staff use the
  ranking to choose which leads go on to the advanced tiers, including the AI
  research pass.
- **E2. The fit score estimates ruling 10's fit**: a running company, in the
  service area, in a segment the chapter mentors, and not already a client or
  contact. The segment list does not exist yet. Cleveland Business Mentors
  will write one, and it is a chapter setting, never code.
- **E3. All three advanced tiers are built**: the AI research pass first,
  then the paid business-data service after a trial batch, then the guided
  staff research.
- **E4. A new client is enriched automatically**, so that the Client
  Administration Team has a fuller picture of the business and can assign a
  better-matched mentor. Once assigned and after meeting the client, the
  mentor may enrich further by automated means, or send the client one or
  more Client Enrichment Surveys chosen by the area the client has asked
  for help with.
- **E5. The surveys start fixed** (option 1). A developer builds each
  survey. Important questions get real CRM fields. Every other answer is
  stored as JSON (JavaScript Object Notation) in one searchable field.
- **E6. Survey answers live in the CRM** (option 1), on a survey response
  record linked to the engagement. The application does the search.
- **E7. For a client, the automated passes send business facts only**
  (option 1): the company name, address and website. The owner's name goes
  out only when it already appears in a public state filing. The client's
  email, phone, notes and survey answers never leave the CRM. A
  privacy-policy review is owed by Doug or counsel.
- **E8. Spending is capped by a monthly budget per chapter** (option 1),
  set at `/setup`. Every run shows its estimated cost and the budget left
  before it starts. A run that would exceed the budget is refused, with the
  amount named. The actual cost is recorded in the action log.
- **E9. Cleveland Business Mentors' starting budget is $50 a month**,
  shared by every paid tier, reviewed after two months of actual costs and
  again when build phase 2 measures the cost per run. (§ 9 question 1)
- **E10. A key person found at a client's business becomes a Contact only
  when a person accepts the finding** (option 1, § 9 question 8). The
  Contact is linked to the client's Company and marked as found by
  enrichment. That mark keeps it out of every marketing list, in this
  application and in the mailing list mirror, until the person opts in
  themselves. On a lead, a person found stays a finding (prospect marketing
  ruling 43).
- **E11. The mentor's automated enrichment is a deeper pass on the
  client's own presence** (option 2, § 9 question 5). It starts from the
  website and social media pages already confirmed on the record, reads them
  in full, and writes a summary for the mentor: what the business sells, how
  it presents itself, published prices, how customers reach it and pay, its
  reviews, and the gaps a mentor would notice. It never searches for the
  business afresh. It is charged to the same budget (E9) and checked on a
  sample before mentors rely on it.
- **E12. Verification is strict, with three exclusions** (§ 3 approved as
  written below). A finding is Verified only when two independent facts
  agree. The registered agent's address counts as a fact only when the agent
  is one of the filing's associates. An exact name in a public registry is a
  name match, not a second fact. The owner's other business is not this
  business. Only a Verified finding applies without a person accepting it.
- **E13. Service area is a gate, not a weight** (option 2). A lead whose
  location is confirmed outside the chapter's counties scores 0, goes to no
  advanced tier, and is flagged "out of area" on the Review grid, where staff
  can disqualify it in one step. It is never disqualified automatically. A
  lead whose only address is a registered agent's is "location unknown" and
  is scored on its other signals.
- **E14. On a lead, a Verified website or email is written directly, into an
  empty field only** (option 1, § 6). A finding that differs from a value
  the lead already holds is shown beside it as a difference and never
  replaces it. A written website or email makes a lead eligible for
  Qualified, never Qualified by itself: the status changes only through the
  existing review rules (rulings 42 and 53).
- **E15. A survey answer replaces the value in a field the survey owns**
  (option 1, § 7). The client is the source of both values and the newer is
  the better. The answer is recorded as coming from that survey and its date;
  the CRM's field history keeps the earlier value. The null-fill rule still
  governs every outside source.
- **E16. The AI research pass is proven on known clients first** (option 2,
  § 8). It runs against production's existing client companies with their
  known websites hidden, and its answers are compared with the known ones to
  give an accuracy figure. It then switches on for new clients, then for
  leads. The client figure is an upper bound, so the sample of 50 lead runs
  checked by a person is still required before it switches on for leads.
- **E17. Cleveland Business Mentors' service area is Cuyahoga and Lake
  counties** (option 1, build plan phase 1 § 7). `CHAPTER_COUNTIES` is set to
  `OH:Cuyahoga|OH:Lake` at `/setup`. The cost, accepted: a business in a
  neighbouring county is flagged out of area until the list is widened.
- **E18. The AI research pass is proven by staff, not by a separate
  measurement run** (Doug, 10-22-26, on the question of measuring before the
  privacy review). Doug's words: "The system should allow a user to initiate
  the AI enhancement on a client, or lead. This combined with the fact that
  we will have a system setting to enable the feature should allow us to
  test the results by selecting companies that we know and running the
  test, then review the results should be adequate protection. The system
  should also allow the AI enrichment to be run on a Lead List." So: a
  person starts a run on one client, one lead, or a list of leads; the
  feature is behind its own switch; the first runs are on companies staff
  know, reviewed by hand. This replaces E16's automated measurement on
  known clients; E16's order of switching on (clients, then leads) stands.

## 2. What the system does, in one paragraph

Every lead gets the free pass when it is imported or created. The free pass
writes a fit score and the signals behind it. On the Leads grid in Campaign
Management, staff sort by fit score, tick the leads worth more effort, and
send them to an advanced tier. Each tier returns findings. A finding that
passes verification is applied or offered for acceptance (§ 6). Every new
client gets the free pass and the AI research pass automatically, and the
result appears as a business picture in the Client Administration engagement
popup. After the first meeting, the mentor can run an advanced tier again or
send a Client Enrichment Survey from the engagement record.

## 3. Verification is part of every tier (approved, E12)

The research pass on 201 new Ohio filings found a likely website for about
73% of them, but only about 2% were the right business. So no tier writes a
website, email or contact on the evidence of a name match alone. A finding
counts as verified only when at least two independent facts agree, for
example the name and the street address, or the name and the owner's name
from the filing. Every finding stores the facts that agreed and the address
of the page where they were seen.

Three things never count as one of the two facts (E12), each taken from
the research pass:

- **The registered agent's address,** unless the agent is also one of the
  filing's associates. A commercial agent service shares its address with
  thousands of businesses.
- **An exact name in a public registry.** It is still a name match: in the
  research pass, two exact-name matches in a federal carrier registry were
  businesses in New Jersey and Indiana.
- **The owner's other business.** Finding the owner of a new filing running
  a different company tells us about the owner, not about this lead.

The cost, accepted: most true matches on brand-new filings reach only
Likely, because a microbusiness's website rarely shows its street address,
so they wait for a person on the Review grid.

The confidence levels are **Verified** (two facts agree), **Likely** (one
fact agrees and nothing contradicts it) and **Unverified** (a name match
only). Only a Verified finding can be applied without a person accepting it.

## 4. The free pass and the fit score

**The gate first (E13).** The free pass reads the lead's location. A
location confirmed outside the chapter's counties (a chapter setting) gives
a fit score of 0 and the flag "out of area". A lead whose only address is a
registered agent's is "location unknown" and passes the gate.

**Then three signals,** each from 0 to 100, averaged with equal weights
into the fit score. The weights are a chapter setting, stored with the rule
set's version.

- **A real operating business:** a home or commercial address rather than a
  registered-agent service, a name that reads as a trade rather than a
  holding or property company, and the age of the filing. A **serial filer**
  (an associate named on many recent filings) is a deduction: in the research
  pass about 18% of filings came from serial filers, usually investors or
  property holders. The cost, accepted: a founder starting a second or third
  real business scores a little lower.
- **Segment:** the industry the name and any form answers suggest, weighed
  against the chapter's segment list. Until the segment list exists, this
  signal is a fixed 50 for every lead, so the ranking moves only where the
  list says something.
- **Findability:** whether a website or email was found and verified by the
  free pass's own cheap checks (a domain built from the name that answers,
  the filing's own email if it has one).

A lead the free pass finds is already a client or contact goes to the
existing *Already known* side exit and is not scored.

The fit score, its gate result, its three signals and the time it was computed are stored on
the lead, so the Leads grid can sort and filter on them. The rule set has a
version number, and the version is stored with each score. A change to the
weights rescores every lead in a background run under the same plan-then-apply
pattern as the other Operations jobs.

## 5. The advanced tiers (approved)

**The AI research pass.** The input is the business facts allowed by E7.
The AI model searches the web, applies § 3's verification to every
candidate, and returns findings plus a summary of a few sentences: what the
business does, its likely stage, and its public contacts. The summary names
its sources. A sample of runs is checked by a person before staff rely on
it (§ 8, phase 2).

**The mentor's deeper pass** (E11). The input is the website and social
media pages already confirmed on the client's record. The AI model reads
them in full and writes a summary for the mentor. It starts no new search
for the business, so it carries no false-match risk. Estimated at $0.50 to
$1.00 a run (inferred, not measured). The mentor runs it from the
engagement record.

**The paid business-data service.** The input is the company name and
address. It returns firmographics (industry code, employee count, revenue
band) and named contacts with emails. It is built after a trial batch of
about 100 of our own leads measures its hit rate. Which service it is
remains Doug's choice.

**The guided staff research.** A checklist on the record: the places to look,
in order, and a box for each finding with the address where it was seen. It
writes findings exactly as the other tiers do, with the staff member as the
source.

All three run as background jobs on the worker, never inside a page request.
Each run is one row in the application database, with its records, its
estimate, its actual cost and its result.

## 6. Where findings go (approved)

**On a lead (approved, E14),** a Verified website or email is written to
the lead directly, into an empty field only. A finding that differs from a
value the lead already holds, for example one the outside filter supplied on
import, is shown beside it as a difference and never replaces it. A written
website or email makes the lead eligible for Qualified, never Qualified by
itself. The cost, accepted: a wrong website that slips past verification can
reach a campaign before anyone looks at it. The finding record names its
evidence, so it can be traced and rejected afterwards.

**On a client,** nothing is written over existing data. A finding for an
empty field appears beside that field as a suggestion, and a person accepts
or rejects it. A finding that differs from a filled field is shown as a
difference and never applied. This is the null-fill rule the public forms
already follow.

Findings are stored as records in the CRM, one per proposed value, linked to
the lead or the company. Each holds the field, the value, the tier, the
evidence, the confidence, and its state (Proposed, Accepted, Rejected or
Applied).

## 7. The Client Enrichment Surveys (approved)

Four fixed surveys: Business Status, Financial Status, Marketing Status and
Technology Status. Each is a public page reached by an emailed link that
carries a token, so the client needs no sign-in. The mentor sends it from
the engagement's Communications tab with an email template, from the
mentor's own address (the standing rule for mail between mentor and client).
The link stays open for 30 days. A resubmission updates the same survey
response record and keeps the earlier answers in its history.

Each answer either lands in a real CRM field (the important questions,
chosen per survey with Doug) or goes into the survey response record's JSON
answers field. An answer tied to a field replaces the field's value (E15),
recorded as coming from that survey and its date. The survey response record links to the engagement and the
client profile and records which survey, when it was sent and when it was
answered. A sent survey that is never answered stays as a record, so the
mentor sees that it is outstanding.

**The answers field is a `text` field** (verified on crm-test 10-20-26):
the CRM's JSON field types are `notCreatable` and not filterable, while a
`text` field is filterable and full-text searchable. The JSON is stored in
it as text.

Search: the engagement shows its own responses. A mentor's search across
their own clients ("no online payments") is answered by the application
reading those clients' responses. That is quick at hundreds of clients and
slows in the thousands (E6).

## 8. Build order (approved, E16)

1. **The free pass and the fit score** on leads, with the gate, the score
   columns on the Leads grid and the setting for the chapter's counties.
   Dark behind a switch. Includes the one-time scoring of the existing
   leads as an Operations job.
2. **The AI research pass, measured on known clients.** Run against
   production's existing client companies with their known websites
   hidden; compare its answers with the known ones; report an accuracy
   figure. The budget (E8, E9), the estimate and the findings records are
   built here.
3. **Client enrichment on intake:** the automatic free pass and AI research
   pass on a new client, and the business picture in the Client
   Administration popup.
4. **The AI research pass on leads,** from the Leads grid, after a person
   checks a sample of 50 lead runs.
5. **The mentor's deeper pass** (E11) on the engagement record.
6. **The Client Enrichment Surveys**, one at a time, Business Status first.
7. **The paid business-data service**, after its trial batch.
8. **The guided staff research.**

## 9. Open questions

1. ~~The monthly budget's starting figure~~ — **answered: $50 a month
   (E9).**
2. **The segment list** (E2): who writes it, and by when.
3. ~~Should the free pass run on the existing leads?~~ — **decided, no
   ruling needed:** yes, once, as an Operations job at `/setup` that shows
   its plan before it writes.
4. ~~Who may send leads to an advanced tier?~~ — **settled by ruling 56:**
   the Leads grid sits in the Campaign Management tile behind the Marketing
   Admin Team. On clients, E4 names Client Administration and the mentor.
5. ~~The mentor's automated enrichment~~ — **answered: E11.**
6. **Which questions on each survey get real CRM fields.** This is answered
   one survey at a time, starting with Business Status.
7. ~~Which AI model provider?~~ — **decided, no ruling needed:** Claude
   models through Anthropic's application programming interface (API), with
   its web search tool, behind one module so a change of provider rewrites
   that module only. The provider's terms go into the privacy review owed
   under E7.
8. ~~Key contacts on a client~~ — **answered: E10.**

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.3 | 10-22-26 10:50 | Claude (Claude Code) | Ruling E18: staff start the AI research pass and prove it on companies they know; it also runs on a lead list. |
| 1.2 | 10-20-26 17:47 | Claude (Claude Code) | Ruling E17: the service area is Cuyahoga and Lake counties. |
| 1.1 | 10-20-26 17:38 | Claude (Claude Code) | § 7: the answers field is a `text` field, verified on crm-test. Phase 1 build plan written (`build-plan-phase-1.md`). |
| 1.0 | 10-20-26 17:27 | Claude (Claude Code) | Ruling E16 (the AI research pass proven on known clients first); § 8 reordered; design approved section by section, § 9 questions 2 and 6 open. |
| 0.8 | 10-20-26 17:25 | Claude (Claude Code) | Ruling E15 (a survey answer replaces the value in a field it owns); § 7 gains the sender, the 30-day link and resubmission; §§ 6 and 7 approved. |
| 0.7 | 10-20-26 15:54 | Claude (Claude Code) | Ruling E14 (direct write on a lead, empty fields only); § 5 approved; § 6 lead paragraph rewritten. |
| 0.6 | 10-20-26 15:50 | Claude (Claude Code) | Ruling E13 (service area is a gate); § 4 rewritten as a gate plus three equally weighted signals, with the serial-filer deduction. |
| 0.5 | 10-20-26 15:49 | Claude (Claude Code) | § 3 approved as strict with three exclusions (ruling E12). |
| 0.4 | 10-20-26 15:41 | Claude (Claude Code) | Ruling E11 (the mentor's deeper pass), added to § 5 and the build order; § 9 questions 5 and 7 closed. |
| 0.3 | 10-20-26 15:40 | Claude (Claude Code) | Ruling E10 (a key person becomes a Contact only on acceptance, kept off marketing lists); § 9 questions 3, 4 and 8 closed. |
| 0.2 | 10-20-26 15:38 | Claude (Claude Code) | Ruling E9: a $50 monthly budget shared by every paid tier; § 9 question 1 answered. |
| 0.1 | 10-20-26 15:12 | Claude (Claude Code) | Created. Rulings E1 to E8 from the 10-20-26 session; strawman §§ 2 to 9. |
