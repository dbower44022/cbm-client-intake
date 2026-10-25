# Kickoff — M4: the import tool

Last Updated: 10-25-26 18:50 · Revision 1.0 — change log at the end.

Operating mode: DETAIL. **The plan below is approved by Doug (10-25-26 18:44)
with its four stopping points, and he has asked for all four to be run in
one session**: work through stops A, B, C and D without pausing, then stop
and report. Pause only for a decision that passes the two-part test and is
not settled below. The one decision the plan put to him is settled:
**ruling 127 — Undo deletes under the org-wide key, and the API role gains
delete on the lead record** (option 1).

## 1. Read first

1. `CLAUDE.md` (loads itself), then `campaigns/CLAUDE.md` — the bullets
   *The import*, *The import at volume*, *The lead model*, *The
   qualification ladder and the Leads tab*, *One page, six tabs* and
   *Review is the research queue*.
2. `prds/prospect-marketing/build-plan.md` § 7e.7 (the step), § 7e.3 (the
   ladder — the import computes the level into the create), § 7e.11
   (storage: migration 0035 is this step's), § 7e.13 (where M4 sits), and
   the M2 and M3 entries under § 7e.13 for how a step records itself.
3. `prds/prospect-marketing/rulings.md` rulings 79–88 (the import tool),
   111 (the template carries the qualifying judgement), 112 (no screen
   cites a ruling number), 123 (the preview runs in the delivery worker),
   127 (Undo deletes under the org-wide key), and 12, 33, 41, 43, 50, 53
   (what the import may and may not create).
4. The code: `campaigns/imports.py` (the whole module), `campaigns/store.py`
   (the import ledger: `prospect_import_batch`, `prospect_import_row`, the
   batch methods), `alembic/versions/0034_lead_level_manual.py` (the shape
   of a migration here), `campaigns/router.py` (`import_plan`,
   `import_apply`, `recent_imports`, `_store`, `_api_client`),
   `campaigns/ladder.py` (`facts`, `placed`, `after_write`),
   `campaigns/audience_store.py` (`audience_list_member` — list membership
   is one of the touched tests), `enrichment/store.py` and `enrichment/runs.py`
   (`run_research_cycle` — the worker-job pattern the plan job follows),
   `worker.py` (the loop around `run_research_cycle`, lines ~520–560),
   `core/sandbox_reset.py` (`RESET_TABLES` — a new table is emptied nightly
   on crm-test), `scripts/sandbox/seed_outreach_data.py` (the seeder shape),
   `scripts/migrate_outreach_roles.py` (`GRANTS`, the API role's row for
   `CProspect`), and in `campaigns/frontend/app.js` the Imports tab
   (`loadImports`, `openImport`, `fillBatchOptions`) and the Leads grid's
   batch filter (`pf_batch`, `GRID_FILTERS`).
5. The tests: `tests/test_campaigns_phase3.py` (the import),
   `tests/test_campaigns.py` (`FakeCrm`, `FakeStore`, `MARKETING`,
   `build(monkeypatch, …)`; the import tests near line 604),
   `tests/test_campaign_leads.py` (`test_already_known_is_a_few_reads…`,
   `test_apply_in_parts…`), `tests/test_campaigns_one_page.py` (the id and
   ruling-number guards).

## 2. What M4 builds (build plan § 7e.7)

The import tool: templates, Excel, recognition and fixes, the preview as a
rehearsal run in the worker, fills on known leads, the level per row, Undo.
Dark behind **`IMPORT_TEMPLATES`** (a new `Settings` bool, off, read per
request); with it off, the Imports tab and both import endpoints behave
exactly as today. One new dependency, **`openpyxl`** (pin it in
`pyproject.toml`, `uv lock`). **Migration 0035**: the `import_template`
table and the four new columns on `prospect_import_batch`
(`excluded_rows` JSONB, `undone_at`, `undone_by`, `undo_result`) plus the
plan-job columns ruling 123 needs (`plan_status`, `plan_error`,
`plan_progress`); `import_template` joins `RESET_TABLES`.

**Routine choices, already made and announced to Doug** — build them as
written:

- The file travels as **base64 inside the JSON post** (`fileBase64`,
  `fileName`), the way the CSV text does today; never multipart. CSV stays
  text. The size limit stays 5 MB and 5,000 rows.
- A workbook with several sheets answers `{sheets: [...]}` and the page asks
  which, then posts again with `sheet`. `.xls` is refused with "save it as
  .xlsx".
- The **level per row (ruling 111)** uses the ladder's own rule:
  `ladder.placed(ladder.facts(payload))` with the template's referrer
  partner as the referrer fact — Referred with a partner and a phone or
  email, Contactable with a named person and a phone or email, else
  Identified. *Enters at* is Unqualified or Qualified; a Qualified template
  names *Qualified by*.
- The **preview runs in the delivery worker** (ruling 123): `plan` creates
  the batch row at `plan_status = queued` and answers at once; the worker
  (`campaigns/imports.run_plan_cycle`, every `IMPORT_PLAN_POLL_SECONDS`,
  default 5, the research-cycle shape) claims it, runs today's plan with
  the new outcome and the level, writes progress (`rows checked of n`)
  and the plan, and marks it `ready` or `failed` with the reason. The page
  polls `GET /prospects/import/{batchId}` every three seconds and says what
  the worker is doing; after two minutes with no progress it says the
  worker may be down and names the setting. A deployment without a
  running worker therefore never previews; dry-run (dev) runs the plan
  inline so the harness and the tests still work.
- The fourth outcome **`fills`** (ruling 84): the ledger maps `row_hash` to
  the lead it created; a row whose hash is known plans the fields it would
  fill (only the lead's empty ones, read in id batches of 100), and apply
  writes them as the user, then `ladder.after_write`. A row with nothing to
  fill is `known_row` as today. A Company or Contact match keeps today's
  Duplicate lead (ruling 85).
- **Per-row exclude** is stored on the batch (`excluded_rows`, the row
  hashes); apply skips them; the summary counts them.
- **Recognition (ruling 81)** scores every template by the share of its
  mapped source columns present in the file's normalised headers; the best
  score above one half is suggested, never applied without the person's
  confirm. Likely renames pair an unmatched file column with an unmatched
  template column by normalised-name similarity (difflib ratio ≥ 0.8),
  shown as suggestions. A required field (business name; the four address
  parts as a set) unmapped stops the import with the field named.
- **The four fixes (ruling 82)** are mapping entries: `{"column": …,
  "field": …}`, `{"split_name": "<column>"}` (first word(s) / last word, the
  `enrichment.runs.split_name` rule), `{"join": ["<a>", "<b>"], "field": …,
  "with": " "}`, `{"fixed": "<value>", "field": …}`, `{"ignore": "<column>"}`.
  Phone and ZIP normalisation stay automatic in `normalise`.
- **Undo (rulings 87, 127)**: `POST /prospects/import/{batchId}/undo` reads
  the batch's created lead ids from the ledger; a lead is *touched* when it
  has any touch (`COutreachTouch` by `prospectId`), membership of any list
  (`audience_list_member`) or campaign (`campaign_audience`), a status or
  level change after the batch's `applied_at` (`leadStatusChangedAt`,
  `levelSetAt`, `modifiedAt` later than the apply by more than the apply's
  own window — compare to the ledger row's `created_at`), a `sideExit`, or
  a conversation (the `CConversation` ↔ `CProspect` link, feature-detected
  like every other read of it). An untouched lead is **deleted under the
  org-wide key**, one action-log row per batch naming the person who
  pressed Undo and every id deleted; touched leads are listed and left;
  fills stay. The batch is stamped `undone_at`, `undone_by`, `undo_result`.
  **The API role needs delete on `CProspect`**: add the cell to
  `migrate_outreach_roles.py`'s `GRANTS` and to the handoff's § 4, and
  say in the report that Doug runs the script on crm-test before the live
  pass (the classifier blocks a mutating role write from here).
- **Templates are shared** (ruling 79): any team member creates, edits or
  deletes any template; each change is one action-log row
  (`CAT_RECORD_EDIT`, actions *Import Template Created / Changed /
  Deleted*, `parent_type` the lead record type and `parent_id` the first
  lead the template's last batch made, or the campaign-management app's
  own id if none — check how `record_action` is called elsewhere with no
  record and follow that).
- **The tab (ruling 88)**: templates and history on the Imports tab,
  *Import…* its one entry point, the Leads tab keeps no Import button (gone
  since M2). **Show these leads** opens `#prospects?batch=<batch name>`.
- A **sandbox seeder** `scripts/sandbox/seed_import_templates.py` (dry run
  by default, `--apply`) makes one demo template, *State filing — Ohio
  Secretary of State*, from the demo leads' columns, so crm-test has one
  after each nightly reset once the baseline is recaptured (Doug's run).
- Every served file: plain words, no ruling numbers (the guard test).

### Stop A — templates and reading

- Migration 0035; `campaigns/import_templates.py` (the table's CRUD on the
  campaign store, recognition, renames, the fixes applied to a row, the
  required check); `campaigns/imports.read_file(name, data, sheet)` for
  CSV and `.xlsx` (openpyxl, read-only, values only, the first row as
  headers); the template endpoints `GET/POST/PUT/DELETE
  /campaigns/api/import-templates[/{id}]` and `POST
  /prospects/import/recognise` (the file's headers → the suggested
  template, the differences, the renames).
- Tests: a new `tests/test_campaign_import_templates.py` — recognition,
  renames, each fix, the required stop, Excel (write a workbook with
  openpyxl in the test), the sheet question, the `.xls` refusal, the
  endpoints through `build()`.

### Stop B — the preview in the worker and the writes

- The plan job (queued → running → ready/failed) in the store and the
  worker; `GET /prospects/import/{batchId}` for the poll; the `fills`
  outcome, the level per row, `excluded_rows`; apply with fills and
  excludes; Undo with the touched rule and the deletion under the org-wide
  key; the `GRANTS` cell and the handoff § 4 line.
- Tests: the plan job's states, the inline dry-run path, fills (only empty
  fields; never over a value), the level per row for each of the three
  levels, excludes, Undo (each touched test, the deletion, the listing, the
  stamp), through `build()` where an endpoint is involved. Keep
  `test_campaigns_phase3.py` and `test_campaign_leads.py` green with the
  switch off.

### Stop C — the Imports tab

- Templates list and editor (name, Lead Source, list source, Qualified by,
  Enters at, referrer partner from `service.partner_options`, the mapping
  grid with a fix picker beside each column); the import flow: file →
  sheet → template suggested with the differences (new, missing, renamed)
  and the mapping grid for the rest → preview (the counts strip, each a
  filter; the walk-through with the spreadsheet values beside the lead
  fields, the problem rows' reasons, Exclude per row; the progress line
  while the worker plans) → confirm → the summary with *Show these leads*;
  history rows gain *Undo this import* (two presses, as *New code* does)
  and the undone stamp. Ids prefixed `im_`; buttons never hidden or
  disabled; the modal is `openModal` / `ask`, never `confirm()`.
- A browser check against the stub harness
  ([[sessions-frontend-stub-harness]]): the recognition screen, the fix
  picker, the preview polling, exclude, confirm, Undo.

### Stop D — documents and release

- `CHANGELOG.md` (read HEAD's `pyproject.toml` and the changelog's top
  heading first; expected 0.286.0), `pyproject.toml` and `uv.lock` (the
  version and the new dependency), `campaigns/CLAUDE.md` (one bullet on
  the import tool, revision and change-log row), the build plan (§ 7e.7
  marked built, § 7e.13 M4 with the routine choices, header revision, the
  Revision control table, a change-log row), `OPEN-ITEMS.md` #57 (M4
  built, the role script owed on crm-test, the live pass owed, then M5),
  `SANDBOX-RESET.md` (the fifth seeder), the root `CLAUDE.md` status window
  (one block; keep four). Commit; **never push**.
- Then the live-pass step page, published as an artifact, following the
  Step-by-Step Instructions standard in `~/.claude/CLAUDE.md` and the
  memory note [[runbook-never-leave-the-surface-mid-section]]: every step
  of a section on one screen, every box named by the words visible in it,
  every value pre-filled from a read of crm-test (parse `.env` in Python,
  never `source` it). Make the rehearsal file from crm-test's demo leads:
  a small `.xlsx` with renamed columns and a full-name column, written to
  the scratchpad and attached to the report (`SendUserFile`), with two
  rows that fill known leads and one that matches a company. Put the
  page's address in `OPEN-ITEMS.md` #57 and commit.

## 3. Things this session must know

- **Parallel sessions share this clone and its git index.** Stage files by
  name, never `git add -A`; audit `git show --stat HEAD` after each commit;
  read `git log --oneline -5` before writing `pyproject.toml`,
  `CHANGELOG.md` or `OPEN-ITEMS.md`, and re-read a file right before each
  edit. Never open a file for writing before you have read it.
- `uv run pytest -q` is the suite (about 3.5 minutes; run it in the
  background). `tests/test_comms_endpoints.py::test_disabled_returns_503`
  fails in the full run and passes alone — order-dependent, known, not
  yours.
- The web process's requests are cut off after about a minute; never put a
  per-row CRM call back into the plan or the apply (the volume rule in
  `campaigns/CLAUDE.md`); the apply stays in parts of 100.
- A CRM id is 17 alphanumerics; the test fakes' hyphenated ids are refused
  by `_CRM_ID` — give test records explicit ids where an endpoint checks
  them.
- The classifier blocks a mutating role write from a session; Doug runs
  `scripts/migrate_outreach_roles.py --apply` (or its equivalent) on
  crm-test. The handoff is already applied there; this adds one cell.
- Memory notes to honour: [[buttons-never-disabled-validate-on-click]],
  [[no-page-width-caps-density-by-packing]],
  [[sessions-appjs-single-scope-collisions]] (one IIFE in `app.js`; grep a
  name before declaring it), [[steps-name-the-app-and-the-tab]],
  [[runbook-never-leave-the-surface-mid-section]], [[lists-one-item-per-line]],
  [[sandbox-new-tables-truncated-nightly]].

## 4. The report at the end

Review list: what changed, where, what to look at, what to test; the role
script Doug runs on crm-test before the pass. Then **What next**: the step
page's address, the rehearsal file, the push Doug owes, the re-baseline,
M5 (personal outreach, § 7e.5) as the recommended next step, and the
handoff's § 7 layout question still open.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 10-25-26 18:50 | Claude (Claude Code) | Written at the end of the M3 session from the M4 plan Doug approved for a one-session run of all four stops; ruling 127 (option 1) settled the Undo deletion. |
