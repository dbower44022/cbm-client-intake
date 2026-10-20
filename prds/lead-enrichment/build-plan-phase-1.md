# Build plan — lead enrichment phase 1: the free pass and the fit score

Last Updated: 10-20-26 17:47 · Revision 0.2 (draft, not approved)

**What it delivers.** Every open lead gets a fit score from 0 to 100,
computed by the free pass at no cost per record. The service-area gate comes
first (ruling E13), then three signals averaged (design § 4). The Leads grid
in Campaign Management sorts and filters on the score. Leads confirmed out
of area are flagged on the Review grid, where staff disqualify them in one
step. A Verified website found by the free pass is written to an empty
website field (rulings E12, E14).

**What it does not deliver.** No paid tier, no AI model, no findings
records, nothing on clients. Those are phases 2 to 8 (design § 8).

Rulings this plan rests on: design E1, E2, E12, E13, E14; prospect
marketing rulings 10 (what fit means), 42 (a website or email is necessary
for Qualified, never sufficient), 53 (how a filing enters) and 56 (the lead
screens stay in the Campaign Management tile).

## 1. The CRM change

Nine fields on `CProspect`: `lead-fit-score-crm-handoff.md`, plan file
`scripts/plans/cprospect-fit-score.json`, fingerprint `8e57af53eef5`. No role
grant changes. The code feature-detects the fields, so the CRM change can
land before or after the release.

## 2. Code

A new package, `enrichment/`, because the arc covers clients as well as
leads. It follows the house shape: the CRM logic in plain modules, the worker
job beside them, no router in this phase.

- **`enrichment/fit.py`** — the scoring, as pure functions with no CRM
  calls: the gate, the three signals, the average, the reasons. One constant,
  `RULE_VERSION`, starting at `1`. Every reason is one plain sentence, for
  example "Postal code 44113 is in Cuyahoga County".
- **`enrichment/geo.py`** — postal code to county, from a data file
  shipped in the image: `enrichment/data/zcta_county.csv`, built once from
  the United States Census Bureau's 2020 ZIP Code Tabulation Area to county
  relationship file (public, no account). **Decided:** a postal code that
  spans several counties passes the gate if any part of it is in a chapter
  county. A border business should not be gated out by the shape of a postal
  code. The cost: a few leads just outside the area pass the gate.
- **`enrichment/terms.py`** + `enrichment/data/name_terms.json` — the
  name-reading rules for the operating-business signal: words that read as a
  holding or property company (Holdings, Properties, Investments, Realty,
  Capital, Rentals), words that read as a trade (Plumbing, Bakery, Salon,
  Consulting), and known commercial registered-agent services. A chapter can
  override the file with its own, published at an address named in a
  setting (the `CHAPTER_TOKENS_URL` precedent); the default is the shipped
  file.
- **`enrichment/findability.py`** — the free web check. From the business
  name, it guesses a small number of domains (the name without its legal
  suffix, `.com` and `.net`), fetches each home page with a short timeout and
  a named user agent, and applies ruling E12: the page must show the name
  **and** either the street address or postal code, or an associate's name.
  A page that passes is a Verified website. Behind its own switch,
  `ENRICHMENT_WEB_CHECKS`, so the score can run without any outbound
  request.
- **`enrichment/sweep.py`** — the worker job, under the org-wide API key.
  Each pass reads up to `ENRICHMENT_BATCH` (200, the CRM's page limit) open
  leads (`cfg.LEAD_OPEN_STATUSES`, no side exit) whose `fitScoredAt` is empty
  or whose `fitRuleVersion` is older than `RULE_VERSION`, scores them, and
  writes the nine fields. A Verified website goes to `website` only when it
  is empty (E14); a different stored website is named in `fitReasons` as a
  difference. A per-lead failure is logged and skipped, never fatal.
  Summary line: `fit sweep: scored=N out_of_area=N unknown=N websites=N
  failed=N`.
- **The worker** runs the sweep every `ENRICHMENT_SWEEP_SECONDS` (900) when
  `ENRICHMENT_FREE_PASS` is on, the CRM is not dry-run, and the nine fields
  exist (feature detection, failing closed). At 200 a pass, a backlog of
  10,000 leads clears in under a day.
- **`/setup` → Operations → *Lead fit scores*** — the dry run counts the
  leads that would be scored and shows the score spread of the first 50; the
  apply runs the whole set now, under the plan-then-apply pattern with a
  fingerprint free of any clock. This is the one-time scoring of the
  existing leads (design § 9 question 3), and the way to rescore after a
  weight change.
- **The Leads grid** (`campaigns/leads.py`, its frontend):
  - `fitScore` joins `SORT_FIELDS`.
  - Two filters: the gate, and a minimum score.
  - Three columns: Fit score, Service area, County. Clicking the score
    opens the reasons.
  - All shown only when the fields exist, read from live metadata.
  - The CSV export gains the score, the gate and the county.
- **The Review grid** gains the filter *Out of area*. The existing bulk
  Disqualify, with its guard against changes since seen, is the one-step
  action E13 asks for. Nothing is disqualified automatically.

## 3. Settings

All default so the application boots unchanged. All editable at `/setup`.

| Setting | Default | Component | Meaning |
|---|---|---|---|
| `ENRICHMENT_FREE_PASS` | off | worker | Runs the sweep. |
| `ENRICHMENT_WEB_CHECKS` | off | worker | Lets the free pass fetch guessed web addresses. |
| `ENRICHMENT_SWEEP_SECONDS` | 900 | worker | Time between passes. 0 stops the sweep. |
| `ENRICHMENT_BATCH` | 200 | worker | Leads per pass, never above 200. |
| `CHAPTER_COUNTIES` | empty | both | The service area, as `State:County` pairs, for example `OH:Cuyahoga\|OH:Lake`. |
| `FIT_WEIGHTS` | `1,1,1` | worker | Operating business, segment, findability. |
| `CHAPTER_SEGMENTS_URL` | empty | worker | The segment list, when it exists (design § 9 question 2). |
| `ENRICHMENT_TERMS_URL` | empty | worker | A chapter's override of the name-reading rules. |

**Decided:** with `CHAPTER_COUNTIES` empty the gate is not applied, every
lead reads *Passed*, and its reasons say "No service area is set". Under the
alternative, every lead would read *Location unknown*, which would look like
a data problem rather than a missing setting.

## 4. Two dependencies on the import

The operating-business signal is only as good as what the import carries.
Today the import's contract has the business name, the mailing address and
`importRow`, which holds any column the import does not know. It has no
associates and no separate registered-agent address. Prospect marketing
question 2 (how the raw state filing arrives) was deferred by Doug on
10-18-26.

- **The registered-agent check** matches the mailing address against the
  known agent services in `name_terms.json`. That works today, but less
  well than a separate agent address would.
- **The serial-filer deduction** reads an `associates` column from
  `importRow` when the filter supplies one, and is inert otherwise. The
  reasons say which.

Neither blocks the build. Both improve the day question 2 is answered.

## 5. Tests

Unit tests with fakes:

- `fit.py` across every gate state and each signal's edges.
- `geo.py`, with a split postal code and an unknown one.
- `findability.py`, with page fixtures: name and street address, name only,
  a different business with the same name, and a timeout.
- The sweep's selection: open leads only, rescored on a rule version
  change, the website written only into an empty field.
- The Operations job's fingerprint stability.

Tests for the grid and the switch:

- The grid's new sort and filters, with the CRM fake refusing a page above
  200.
- Feature detection: no columns and no sweep when the fields are absent.
- The switch-off path.

## 6. Rollout

1. The CRM change on crm-test (handoff § 2), then the release, dark.
2. On crm-test at `/setup`: set `CHAPTER_COUNTIES`, switch on
   `ENRICHMENT_FREE_PASS`, run the Operations job's dry run, then apply.
3. **Live pass**, as a real non-admin member of the Marketing Admin Team: the
   Leads grid sorted by score, the reasons on one lead, the out-of-area
   filter on the Review grid, one bulk Disqualify. Then
   `ENRICHMENT_WEB_CHECKS` on, and one lead whose website gets written.
4. Production's CRM change at a Sunday slot; the switches on at `/setup` by
   Doug.

Rollback: switch `ENRICHMENT_FREE_PASS` off. The scores stay on the leads
and stop changing. Nothing else reads them.

## 7. Owed by Doug before the live pass

- ~~The chapter's counties~~ — **answered (design E17):** Cuyahoga and
  Lake. `CHAPTER_COUNTIES` = `OH:Cuyahoga|OH:Lake`, set at `/setup` in
  rollout step 2.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 0.2 | 10-20-26 17:47 | Claude (Claude Code) | § 7: the counties answered (E17). |
| 0.1 | 10-20-26 17:38 | Claude (Claude Code) | Created from design § 4 and § 8 phase 1. |
