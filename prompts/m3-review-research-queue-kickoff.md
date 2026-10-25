# Kickoff — M3: Review as the research queue

Last Updated: 10-25-26 12:18 · Revision 1.0 — change log at the end.

Operating mode: DETAIL. **The plan below is approved by Doug (10-25-26) with
its three stopping points, and he has asked for all three to be run in one
session**: work through stops A, B and C without pausing, then stop and
report. Pause only for a decision that passes the two-part test and is not
settled below.

## 1. Read first

1. `CLAUDE.md` (loads itself), then `campaigns/CLAUDE.md` — the bullets *The
   lead model*, *The qualification ladder and the Leads tab* and *One page,
   six tabs* are the ones this step touches.
2. `prds/prospect-marketing/build-plan.md` § 7e.6 (the step), § 7e.3 (the
   ladder), § 7e.13 (where M3 sits), and the M2 entry under § 7e.13 for how
   the last step recorded itself.
3. `prds/prospect-marketing/rulings.md` rulings 110, 112, 113, 121 and 43.
4. The code: `campaigns/ladder.py` (the whole module docstring),
   `campaigns/leads.py` (`LeadQuery.from_params`, `review_queue`,
   `search`, `changed_since`, `facts_payload`, `FACT_FIELDS`),
   `campaigns/router.py` (`review_prospect`, `edit_prospect_facts`,
   `_lead_select`, `_lead_or_404`), `campaigns/review.py`
   (`contact_changes`), `enrichment/runs.py` (`decide`, `_create_person`,
   `existing_findings`, `present`, `KIND_PERSON`, `FINDING_SELECT`),
   `enrichment/router.py` (`decide`, the `status` route),
   `frontend/shared/enrichment.js` (`panel`, `startRun`), and in
   `campaigns/frontend/app.js` the Review queue (`renderReview`,
   `qualifyRow`, `disqualifyRow`, `dropReviewRow`, `focusRow`,
   `webSearchUrl`) and the grid machinery (`GRID_FILTERS`, `gridQuery`,
   `readHash`, `writeHash`, `loadGrid`, `wireGrid`).
5. The tests those touch: `tests/test_campaign_leads.py`,
   `tests/test_campaign_lead_page.py`, `tests/test_enrichment_research.py`,
   `tests/test_campaigns_one_page.py`. `tests/test_campaigns.py` holds the
   shared `FakeCrm`, `FakeStore`, `MARKETING` and `build(monkeypatch, …)`;
   the ladder tests carry their own fakes whose `metadata` answers the
   ladder's fields and links (`tests/test_campaign_leads_ladder.py`).

## 2. What M3 builds (build plan § 7e.6; rulings 110, 121)

Review becomes the research queue, in two modes. It rides `LEAD_LADDER`
(the contacts mode needs the ladder's fields) and adds no switch of its own.

**Routine choices, already made and announced to Doug** — build them as
written:

- The Review tab's mode rides the address, `#review?mode=contacts`, the way
  the filters do today (`GRID_FILTERS` / `readHash` / `writeHash`).
- In the contacts mode, Enter writes whatever was typed. If the lead is
  still Identified afterwards (a name with no phone or email), the row
  stays and the notice says what is still needed. It leaves the queue only
  when placement moves it to Contactable or Referred.
- The contacts-mode write is guarded like every review decision: the row
  sends what the reviewer saw (`seenStatus`, `seenExit`, and a new
  `seenLevel`), and a change since answers 409 naming who
  (`leads.changed_since`, extended to the level).
- The row's *AI research* button does two things by state: with no
  Proposed findings on the lead it starts a research run for that one lead
  (`CBMEnrichment.startRun` with one id); with findings it fills the row's
  boxes from them, and Enter then writes the values and marks those
  findings Accepted. The button is always shown; when AI research is dark
  (`GET /enrichment/api/status?targetType=lead` not `available`/`ready`) it
  says so on click. Buttons are never hidden or disabled.
- Accepting a Person finding on a lead fills the lead's own `firstName`,
  `lastName`, `email` and `phone` where they are empty and creates no
  Contact (ruling 121; ruling 43 stands), under the org-wide key, then
  `ladder.after_write`. A Person finding whose every field is already held
  on the lead closes as Accepted with nothing written. Split `personName`
  into first and last the way `_create_person` does.

### Stop A — the queue and the writes

- `LeadQuery.from_params(…, review_queue=True, mode=…)`: `judge` (the
  default) is today's queue unchanged — Unqualified, no exit, oldest first.
  `contacts` is Qualified at `qualificationLevel` Identified, no exit,
  oldest first. On a CRM without the ladder (`leads.ladder_available`
  false) the contacts mode is refused with a plain sentence (400), never
  silently turned into the judge queue.
- `POST /campaigns/api/prospects/{id}/contacts` — body `firstName`,
  `lastName`, `phone`, `email` (each optional), `seenStatus`, `seenExit`,
  `seenLevel`, `findingIds` (optional). Reads the lead with the guard
  select, 409s on a change, writes the typed values as the user through
  `leads.facts_payload` (so the same normalisation as the lead page),
  runs `ladder.after_write` under the org-wide key, marks the named
  findings Accepted (org-wide key, `decidedBy` the user's name), records
  one action-log row (`CAT_RECORD_EDIT`, action `Lead Contact Found`), and
  answers `{prospect, written, level, stays}` where `stays` is true when
  the lead is still Identified.
- `GET /campaigns/api/prospects/{id}/suggestions` — the lead's Proposed
  findings mapped to boxes: `{website, email, phone, firstName, lastName,
  findingIds, researching}` where `researching` says a run is queued or
  running for the lead (read the enrichment store the way
  `enrichment/router.py`'s status route does). Org-wide key for the
  findings read (the Marketing Admin Role has no `CEnrichmentFinding`
  grant — check `migrate_outreach_roles.py` / the role read rather than
  assuming).
- `enrichment.runs.decide`: a Person finding on a lead is accepted per
  ruling 121 (above). Update the refusal test in
  `tests/test_enrichment_research.py` to the new behaviour and add the
  nothing-to-write case.
- Tests: `test_campaign_leads.py` gains the two modes and the ladder
  refusal; a new `tests/test_campaign_review_contacts.py` covers the
  contacts write (normalisation, the guard, `stays`, the findings
  acceptance, the action-log call) and the suggestions mapping, through
  `build()` where an endpoint is involved.

### Stop B — the Review tab

- A two-way mode switch above the queue (two buttons, `rf_mode_judge` /
  `rf_mode_contacts`, prefixed ids as every Review control is), each mode
  with its own hint sentence. The contacts switch is shown only when the
  grid answer says `ladder`; with the ladder off, Review is exactly today's
  tab.
- The contacts row: Business (a link to `/campaigns/lead/{id}` in a named
  tab, as the Leads grid opens it), Fit (when the CRM has it), City,
  *Look it up* (the web search link), First name, Last name, Phone, Email,
  *AI research*, *Save*, Batch. Enter in any box saves the row and moves
  the cursor to the next lead (`dropReviewRow` / `focusRow` when it leaves;
  stay on the row and refocus when `stays`).
- The judge row keeps today's columns and gains the same *AI research*
  button, filling Website and Email from the suggestions.
- The thead for Review is drawn by script from the mode (the Leads grid's
  `renderProspectHead` is the pattern), so the two layouts never fight.
- A browser check against the stub harness
  ([[sessions-frontend-stub-harness]] in memory; `tests/` has no browser
  test). The one-page guard (`tests/test_campaigns_one_page.py`) fails on
  any `ruling \d` or `CM-\d` in a served file — write hints in plain words.

### Stop C — documents and release

- `CHANGELOG.md`: a new entry at the top. **Read HEAD's `pyproject.toml`
  version and the changelog's top heading before numbering** — other
  sessions release in parallel (see § 3); the next number is one minor
  above whatever HEAD holds, expected 0.285.0.
- `pyproject.toml` and `uv.lock` (the `[[package]] name = "cbm-client-intake"`
  entry) to that version.
- `campaigns/CLAUDE.md`: one bullet on the research queue under the ladder
  bullet, revision and change-log row.
- `prds/prospect-marketing/build-plan.md`: § 7e.13 step M3 marked built,
  with the routine choices recorded under it as M2's entry does; header
  revision, the Revision control table and a change-log row.
- `OPEN-ITEMS.md` item 57: M3 built, live pass owed, then M4.
- Root `CLAUDE.md`, the *Current status* rolling window: one block for the
  release, and drop the oldest block if the window has grown past four.
- Commit in this clone; **never push** (Doug pushes).
- Then the live-pass step page, published as an artifact, following the
  Step-by-Step Instructions standard in `~/.claude/CLAUDE.md` (one action
  per step, done boxes that collapse and scroll the next step to the top,
  ticks saved in the browser, a progress count, a reset button, every
  value in a copy box, every location exact, a report-back line per
  section). **Pre-fill every value from a read of crm-test first** — the
  M2 page's source is `/tmp/claude-1000/-home-doug-Dropbox-Projects-cbm-client-intake/97fb72c6-245a-4fb2-afae-7cc2be2f0c32/scratchpad/m2-live-pass.html`
  if that folder still exists, else start fresh; the leads on crm-test as
  of 10-25-26 12:00: Collinwood Records and Detroit Shoreway Signs are
  Unqualified (the judge mode); Marigold Pet Grooming, Northcoast Drone
  Services and Ohio City Bike Works are Identified (the contacts mode);
  Gordon Square Florist was converted in the M2 pass. The nightly reset
  (04:00 UTC) puts the demo leads back; re-read before writing the page.
  Read the CRM with the org-wide key by parsing `.env` in Python — never
  `source` it in a shell ([[never-read-env-with-a-shell]]). Put the page's
  address in `OPEN-ITEMS.md` #57 and commit.

## 3. Things this session must know

- **Parallel sessions share this clone and its git index.** Stage files by
  name, never `git add -A`; audit `git show --stat HEAD` after each commit;
  read `git log --oneline -5` before writing `pyproject.toml`,
  `CHANGELOG.md` or `OPEN-ITEMS.md`, and re-read the file's current text
  right before each edit. On 10-25-26 one session's edit helper emptied
  `pyproject.toml` and deleted `event-administration.md`; both were
  restored. Never open a file for writing before you have read it.
- `uv run pytest -q` is the suite (about 3.5 minutes; run it in the
  background). `tests/test_comms_endpoints.py::test_disabled_returns_503`
  fails in the full run and passes alone — order-dependent, known, not
  yours.
- The ladder's level is empty at any status but Qualified; `ladder.
  after_write(lead_id, client=…)` after any application write to a lead;
  every placement write is the org-wide key's. The Marketing Admin Role
  edits `CProspect` but holds a read-only field rule on `leadCode`; it has
  no `CEnrichmentFinding` grant that you may assume — read the role or use
  the org-wide key for findings.
- The lead page's inline save had a double-save bug (Enter, redraw, blur):
  `gap()` in `app.js` now remembers what it saved. The contacts row's
  Enter-then-redraw path has the same shape — reuse the guard.
- Memory notes to honour: [[buttons-never-disabled-validate-on-click]],
  [[no-page-width-caps-density-by-packing]],
  [[sessions-appjs-single-scope-collisions]] (one IIFE in `app.js`; grep a
  name before declaring it), [[steps-name-the-app-and-the-tab]],
  [[runbook-steps-prefilled-values]], [[lists-one-item-per-line]].

## 4. The report at the end

Review list: what changed, where, what to look at, what to test. Then
**What next**: the step page's address and the push Doug owes, M4 (the
import tool, § 7e.7) as the recommended next step, and the handoff's § 7
layout question still open.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 10-25-26 12:18 | Claude (Claude Code) | Written at the end of the M2 session from the M3 plan Doug approved for a one-session run of all three stops. |
