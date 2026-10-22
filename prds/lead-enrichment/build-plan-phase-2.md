# Build plan — lead enrichment phase 2: the AI research pass, started by staff

Last Updated: 10-22-26 10:51 · Revision 0.1 (draft, not approved)

**What it delivers.** A person starts an AI research run on one lead, on a
set of leads, or on one client's company. An AI model searches the web for
the business, decides whether each thing it finds belongs to this business
under the strict rule (ruling E12), and returns findings: a website, an
email, a phone number, an industry, the people who run it, and a short
summary of the business with its sources. Every run shows its estimated cost
against the month's budget before it starts (rulings E8, E9). Findings land
as the design says (§ 6): a Verified website or email goes straight into an
empty field on a lead (E14); everything on a client waits for a person to
accept it (E7, E10).

**How it is proven (ruling E18).** No separate measurement run. Staff switch
the feature on at `/setup`, run it on companies they already know, and read
the results. The feature stays off in production until they are satisfied.

**Not in this phase.** The automatic run on every new client (phase 3), the
mentor's deeper pass (phase 5), the paid business-data service (phase 7),
the guided staff research (phase 8). The *Run AI research* button on a named
campaign list follows when the lists feature is switched on (§ 4.4).

Rulings this plan rests on: design E1, E3, E7–E12, E14, E18; prospect
marketing rulings 42 (a website or email is necessary for Qualified, never
sufficient), 43 (a lead's people stay on the lead until first contact) and
56 (the lead screens live in Campaign Management).

## 1. Decided here, and said so

- **The model is Claude Opus 5.5** (`claude-opus-5-5`), Anthropic's current
  default, with the server-side web search and web fetch tools. A setting,
  `ENRICHMENT_AI_MODEL`, can name another. Estimated $0.10 to $0.25 a run
  (inferred: about 20,000 to 40,000 tokens read, 2,000 written, up to five
  searches at $0.01 each). The first runs measure it.
- **Refusal fallback on.** If the model declines a request, the request is
  re-run on the next model automatically (the API's own fallback). Off by
  setting if you prefer a refused run to simply stop.
- **The application judges "Verified", not the AI model.** The model reports
  which facts it saw on each page (the name, the street address, the postal
  code, an associate's name). The application counts them under E12's rule
  and its three exclusions. A model that calls something verified on one
  fact gets *Likely*, whatever it says.
- **A run reads only what E7 allows.** For a client: the company's name,
  address and website. For a lead: the business name, the mailing address,
  any website, and the associates named on a public filing. Never an email,
  phone, note, survey answer or person's name a client gave us.
- **A client's findings link to the Company (`Account`),** because the Company
  holds the website, email, phone and industry they would fill.

## 2. The CRM change — one new record type

**`CEnrichmentFinding`** (label *Enrichment Finding*), one record per proposed
value. Its own handoff and plan file, crm-test first.

| Field | Type | Holds |
|---|---|---|
| `kind` | enum: Field value, Person, Summary | What the finding is |
| `targetField` | varchar | For a field value: `website`, `emailAddress`, `phoneNumber`, `industry` |
| `proposedValue` | text | The value found |
| `currentValue` | text | What the record held when the finding was made |
| `personName`, `personTitle`, `personEmail` | varchar | For a person (E10) |
| `summary` | text | For a summary: a few sentences on the business |
| `confidence` | enum: Verified, Likely, Unverified | Counted by the application (§ 1) |
| `factsMatched` | text | The facts that agreed, one per line |
| `sourceUrl` | url | Where it was seen |
| `tier` | enum: Free pass, AI research, Paid service, Staff research | Who found it |
| `findingStatus` | enum: Proposed, Accepted, Rejected, Applied | Applied = written without a person (E14) |
| `decidedBy`, `decidedAt` | varchar, datetime | Who accepted or rejected it |
| `runRef` | varchar | The run that made it (the application database's id) |

Links: `prospect` → `CProspect` (many to one, reverse `enrichmentFindings`);
`company` → `Account` (many to one, reverse `cEnrichmentFindings`). Grants:
the API role creates, reads and edits; the Marketing Admin Role and the
Client Assignment Role read and edit. None of the fields Read-only.

## 3. The application database

Migration: `enrichment_run`, one row per run. It holds who started it, what
on (lead ids or a company id), the estimate, the actual cost from the API's
reported usage, its state (queued, running, done, failed), and per-record
results. The month's spend is the sum of the month's runs; the budget check
reads it. Working state, so it lives here, not in the CRM (design § 5).

## 4. Code

### 4.1 The engine — `enrichment/research.py`

- One function researches one business. It builds the request from E7's
  allowed facts, calls the model with web search and web fetch (up to
  `ENRICHMENT_AI_MAX_SEARCHES`, default 5), and asks for the answer as a
  fixed JSON shape (structured output). It counts each candidate's facts under
  E12 and returns findings plus the run's token and search counts.
- A refused or failed call is a failed result for that record, never a crashed
  run. A record whose run costs more than the per-record cap
  (`ENRICHMENT_AI_RECORD_CAP`, default $1.00) is stopped and says so.

### 4.2 Runs and the budget — `enrichment/runs.py`

- **Start:** a set of lead ids, or one company id. The estimate is records ×
  the average cost of the last 50 records researched (or $0.20 before
  there are 50). Refused when it would pass `ENRICHMENT_MONTHLY_BUDGET`
  (default 50, ruling E9), with the amounts named. At most
  `ENRICHMENT_AI_MAX_RECORDS` (default 500) per run.
- **The worker runs the queue,** two records at a time, and writes the
  findings as it goes. A run interrupted by a restart resumes where it was;
  a record already researched is not researched again.
- **Every run is action-logged** with its estimate and actual cost (E8).

### 4.3 Where findings land

- **A lead:** a Verified website or email into an empty field (E14), marked
  Applied. Everything else Proposed. A person found stays a finding (ruling 43).
  The lead's status is never changed.
- **A client:** everything Proposed. Accepting a field value writes it into
  the empty field on the Company; a filled field shows the finding as a
  difference and Accept is refused with the reason. Accepting a person
  creates a Contact linked to the Company, marked found by enrichment and
  kept off every marketing list until they opt in (E10).

### 4.4 Where staff start a run and review it

- **Campaign Management, the lead's window:** *Run AI research* and a
  *Findings* section with Accept / Reject on each Proposed finding.
- **Campaign Management, Leads grid, the bulk bar:** *AI research…* over the
  ticked leads or all matching, with the estimate shown before it starts.
- **Client Administration, the engagement popup:** a *Business picture*
  panel — the summary and its sources, the findings with Accept / Reject,
  and *Run AI research*. It reads the client's Company.
- **Campaign Management, Lists (later):** *Run AI research* on a named list,
  through the same start call, when the lists feature is switched on and the
  session working on it agrees.

### 4.5 Settings

All off or empty by default, editable at `/setup`:
`ENRICHMENT_AI` (the switch), `ENRICHMENT_AI_MODEL`,
`ENRICHMENT_MONTHLY_BUDGET` (50), `ENRICHMENT_AI_MAX_SEARCHES` (5),
`ENRICHMENT_AI_RECORD_CAP` (1.00), `ENRICHMENT_AI_MAX_RECORDS` (500),
`ENRICHMENT_AI_FALLBACK` (on). It needs `ANTHROPIC_API_KEY`, which the
conversation summaries already use; the readiness panel says when it is
missing.

## 5. Tests

The engine with a fake model: the E12 counting (two facts, the three
exclusions, a model that overclaims), E7's inputs (no email, phone or notes
ever in the request), a refusal, a cost over the per-record cap. Runs: the
budget refusal, the estimate, resume after a restart, no record researched
twice. Landing: E14 on a lead, a refused Accept on a filled client field, a
person accepted as a Contact with the marketing exclusion.

## 6. Rollout

1. The CRM change on crm-test, then the release, dark.
2. On crm-test: `ENRICHMENT_AI` on; staff run it on companies they know and
   read the findings (E18). crm-test's clients are mostly made-up
   companies, so the test adds leads for real businesses staff know, as the
   phase 1 pass did with Great Lakes Brewing Company.
3. Production's CRM change at a Sunday slot; `ENRICHMENT_AI` on in
   production when staff are satisfied with crm-test's results — Doug's call.

## 7. Open questions, for Doug in this order

1. Who may accept a finding on a client: Client Administration only, or the
   assigned mentor too.

(Where findings live is not open: design § 6, approved 10-20-26, puts them
in the CRM, one record per proposed value.)

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.1 | 10-22-26 10:51 | Claude (Claude Code) | Created from design § 5, § 6 and ruling E18. |
