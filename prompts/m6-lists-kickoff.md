# Kickoff — M6: lists

Last Updated: 10-26-26 00:40 · Revision 1.0 — change log at the end.

Operating mode: DETAIL. **The plan below is a draft, not yet approved.**
Doug is running the M5 live pass on crm-test while this session starts, so
the session's **first reply** states the operating mode and the loaded
`CLAUDE.md` files as usual, then presents the four stopping points below
and any decision that passes the two-part test and is not settled here, and
**waits for Doug's approval before building anything**. Once he approves
(he may say "run all four stops" as he did for M4 and M5), work through
stops A, B, C and D without pausing, then stop and report. Pause only for a
decision that passes the two-part test and is not settled below.

**Do not push during this session.** Doug's M5 pass runs on crm-test, which
builds from `main`; a push would redeploy under him and the Lists tab he
may open is the one this step rewrites. Commit; Doug pushes when his pass
is done (`OPEN-ITEMS.md` #57 names the state).

## 1. Read first

1. `CLAUDE.md` (loads itself), then `campaigns/CLAUDE.md` — the bullets
   *Campaign lists*, *L2*, *One page, six tabs*, *The qualification ladder
   and the Leads tab*, and *Personal outreach from the lead's page* (for
   how M5 recorded itself).
2. `prds/prospect-marketing/build-plan.md` § 7e.8 (the step), § 7c (what
   lists are today: the recipe of steps, the five tables, the engine, the
   screens), § 7e.9 *Lists only* (the five ready-made system lists, which
   are **M7's**, not this step's — but the recipe shape built here is what
   they will be written in), § 7e.11 (storage: the plan's "migration 0034"
   for lists was never cut — 0034 became the ladder's snapshot and 0035 the
   import templates — so this step cuts **migration 0037**), § 7e.12
   Draft 9, § 7e.13 (where M6 sits), and the M2 to M5 entries under
   § 7e.13 for how a step records itself.
3. `prds/prospect-marketing/rulings.md` rulings 90 (Include and Leave out,
   not steps), 91 (static and dynamic mean what the words say), 92 (a
   dynamic list is a pure search; exceptions live in static lists; the
   Exclude button), 93 (the kind is fixed; copy to a new static list), 94
   (a static list is filled inside the list), 98 (the list page layout),
   and the ones they change: 58–65, 68 (the lists as built), 112 (no
   screen cites a ruling number), 114 and 89 (the page and its tabs).
4. The code: `campaigns/audience.py` (the whole module — `ACTIONS`,
   `normalise_recipe`, `check_recipe`, `condition_where`, `step_where`,
   `describe_step`, `run_recipe`, `reaches`, `apply_hand`, `apply_entries`,
   `current_members`, `used_fields`, `describe_members`,
   `resolve_targets`, `audience_for_build`); `campaigns/audience_store.py`
   (the five tables and `AudienceStoreMixin`: `create_list`, `save_list`,
   `replace_recipe_members`, `hand_mark`, `hand_clear`, `member_rows`,
   the entry methods, `delete_list`, the campaign ↔ list rows);
   `campaigns/lists_router.py` (every route: catalogue, the list CRUD,
   preview, run, members, mark / unmark, `search/records`, retire /
   reactivate / delete, the campaign audience pair);
   `campaigns/frontend/lists.js` and `lists.css` (the whole tab: it reaches
   the page only through `window.CBMMarketing`, ids `ls_`); the Lists
   panel in `campaigns/frontend/index.html` (`id="listsPanel"` to
   `id="callsPanel"`); `alembic/versions/0032_campaign_audience_lists.py`
   and `0036_import_write_lease.py` (the shape of a migration here);
   `core/sandbox_reset.py` (`RESET_TABLES`) and `scripts/sandbox/` (a new
   table is emptied nightly on crm-test; the seeder pattern);
   `setup/verify._probe_campaign_list_fields` and `audience.DEFAULT_FIELDS`
   (the curated step fields stay as they are — ruling 63 is unchanged).
5. The tests: `tests/test_campaign_lists.py` (the whole file; § 7e.8 names
   the five tests that go and says the import, lists-of-lists and cycle
   tests stay, adapted), `tests/test_campaigns_one_page.py` (the id and
   ruling-number guards; `lists.js` must keep `var M = window.CBMMarketing;`
   / `if (!M) return;` and `M.register("lists", { onShow: onShow, onLeave:
   leaveUnsaved })` — the guard test asserts those strings), and the
   campaign build tests that pass `audience=` (`grep -rn audience_for_build
   tests/`).

## 2. What M6 builds (build plan § 7e.8)

Lists become what rulings 90–94 say: **a dynamic list is a search —
Include groups minus Leave out groups — and nothing else; a static list is
people added by hand inside the list and nothing else.** No steps, no step
order, no *Keep only*, no standing entries, no kind switch. Rides the
existing **`CAMPAIGN_LISTS`** switch (no new switch: the tab is the same
feature, reshaped). One migration, **0037**. The curated field list,
`resolve_targets` and every send-time check are untouched; a campaign that
names a list still builds from it through `audience_for_build`.

**Routine choices, to be announced in the first reply and built as
written unless Doug says otherwise:**

- **The recipe shape** (ruling 90): `audience_list.recipe` becomes
  `{"include": [group, …], "exclude": [group, …]}`. A group is one of
  `{"kind": "match", "type": <one of the five>, "conditions": [...]}` (the
  same conditions, fields and operators as today's steps, all of which
  must match), `{"kind": "list", "listId": ...}` or `{"kind": "import",
  "type": ..., "values": [...]}`. `run_recipe` is the union of the includes
  minus the union of the excludes; Leave out always wins. The run report
  carries one count per group. Groups have no order. A static list's
  `recipe` is empty and never run; `last_run_at` stays null on it.
- **The migration converts what it can** (§ 7e.8): an *Add* step becomes
  an Include group, a *Remove* / *Remove list* step a Leave out group, an
  *Add list* step an Include list group, an *import* step an Include
  import group; a recipe with a *Keep only* step, or whose step order
  changed the result, is converted as far as it goes and the list is
  marked **`needs_rebuild`** (a new boolean column) and shown so on its
  page ("This list was built with steps the new builder does not have;
  check who is on it and save it again"). Each dynamic list's standing
  entries become one static list named "<list> — exceptions" (its
  *always exclude* entries as hand rows) which the dynamic list leaves out,
  and its *always include* entries are dropped with a log line naming
  them — ruling 92 has no place for an always-include. `audience_list_entry`
  is dropped **after** the conversion, in the same migration. Only
  crm-test test lists exist and the sandbox truncates the tables nightly,
  so the conversion is written for correctness, not for scale.
- **Static lists** (rulings 91, 94): members are `audience_list_member`
  rows with state *in*, written by *Add people* — the dynamic builder's
  one condition panel (one type, its conditions) **plus a name or email
  box over the five target types** (`GET /lists/search/records` extended
  to take `q` across types), with tick, select all and Add, copied once,
  no search saved. *Remove* takes the hand row away. A static list has no
  *Run again*, no "never run" guard, no versions of a recipe (its versions
  table keeps recording name and notes changes only).
- **Dynamic lists** (rulings 91, 92): `mark` / `unmark` are refused on a
  dynamic list in words. The member grid's **Exclude** asks which static
  list to add the person to — offering every active static list, with
  "+ New list" that creates one named "<this list> — do not include" — adds
  the hand row there, and relates it as a Leave out list group on this
  list when it is not one already. Creating a dynamic list offers "Leave
  out an exclusion list" with the same picker.
- **The kind is fixed** (ruling 93): the Static / Dynamic switch goes from
  the editor; `PUT /lists/{id}` refuses a kind change in words.
  `POST /lists/{id}/copy` copies the current members to a new static list
  (name required; the members as hand rows; the campaigns stay on the
  original).
- **The list page** (ruling 98): the top line names the list, the kind,
  and the member count per channel — Email / Text / Postcard — each count
  `resolve_targets` run for that kind and read as its count only
  (`GET /lists/{id}/counts`, computed on demand, never stored; the
  Constant Contact status is M7's and is left off). A dynamic list states
  *who is on it* in one sentence per group (`describe_group`, the
  successor of `describe_step`), with *Edit* opening the builder: an
  **Include** panel and a **Leave out** panel, each with *+ group* offering
  the three kinds. A static list shows *Add people* and *Remove*. The
  member grid has search, sort and export (CSV, the existing
  `leads.export` shape), and on a dynamic list a **Brought in by** column
  naming the Include group (the first group that matched; the run records
  the group index per member in `audience_list_member.step`, renamed
  **`group_index`** by the migration) and the **Exclude** button. **Used
  by** lists each campaign with its date and reach (the existing campaign
  ↔ list rows plus the campaign's `pieceCount` / status).
- **The index** (ruling 98): name, kind, members, last used (the newest
  campaign date); the Constant Contact tick arrives with M7.
- **The run report** on a dynamic list: one count per group, the total,
  and the per-channel counts; the per-step table goes.
- **Names, never numbers, on the screen** (ruling 112): the guard test
  fails on `ruling \d` in any served campaigns file.
- **The sandbox**: `audience_list` gains two columns (`needs_rebuild`,
  and nothing else this step); `audience_list_member.step` is renamed; the
  entry table goes. `RESET_TABLES` keeps the four remaining tables; the
  seeder, if one exists for lists, is updated to the new recipe shape.
- **Every number is `campaigns/reporting.py`** where it is a campaign
  number; the per-channel counts here are list numbers and live in
  `audience.py` beside `resolve_targets`.

**Decisions that may pass the two-part test — put them to Doug in the
first reply with the plan, using the consequential decision template, or
state that none does:**

1. **What the converted test lists on crm-test look like the morning after
   the migration.** The sandbox truncates the list tables nightly, so the
   conversion is exercised once at most; the seeders rebuild from scratch.
   Likely routine (announce: the seeder writes the new shape; no
   conversion is needed on production, which has no lists).
2. **Whether *Brought in by* names only the first matching group or every
   matching group.** One group is simpler and is what § 7e.8 says; every
   group costs a second column or a tooltip. Likely routine (announce: the
   first group).

### Stop A — the model and the store

- Migration 0037: the recipe reshape with conversion, `needs_rebuild`,
  `step` → `group_index`, the exceptions lists, the entry table dropped.
- `audience.py`: `normalise_recipe`, `check_recipe`, `referenced_lists`,
  `run_recipe`, `reaches`, `current_members`, `used_fields`,
  `describe_members` reworked for groups; `describe_group`; `apply_entries`
  and the step vocabulary removed; `copy_to_static`; the per-channel
  counts. `audience_store.py`: the entry methods removed, `save_list`
  refuses a kind change, `copy_list`, `hand_mark` for static lists only.
- Tests: `tests/test_campaign_lists.py` rewritten as § 7e.8 says (the five
  named tests go; the import, lists-of-lists and cycle tests adapted; new
  ones for Include minus Leave out, Leave out wins, a static list with no
  recipe, Exclude into an exclusion list, the copy, the kind refusal, the
  conversion of each old step kind and the `needs_rebuild` mark); the
  campaign build tests that pass `audience=` stay green.

### Stop B — the API

- `lists_router.py`: `preview` answers per-group counts; `run` refuses a
  static list in words; `members` carries `broughtInBy`; `mark` / `unmark`
  refuse a dynamic list; `POST /lists/{id}/exclude` (member key, target
  list id or a new name); `POST /lists/{id}/add-people` (keys); `POST
  /lists/{id}/copy`; `GET /lists/{id}/counts`; `GET /lists/search/records`
  with `q` across the five types; `GET /lists/{id}/used-by`; every
  mutation action-logged at the router as today.
- Tests through `build()` for each new route and each refusal in words.

### Stop C — the screens

- `lists.js` / `lists.css` / the Lists panel: the index, the list page, the
  builder with Include and Leave out, the sentences, Add people with the
  name-or-email box, the member grid with search / sort / export / Brought
  in by / Exclude, the create dialog's exclusion-list offer, Copy to a new
  static list, the `needs_rebuild` notice; ids `ls_`; buttons never hidden
  or disabled; the page's own dialog for every question, never
  `confirm()`.
- The browser check against the stub harness
  ([[sessions-frontend-stub-harness]]; `javascript_tool` scripts under a
  second of awaits, one mutating action per call).

### Stop D — documents and release

- `CHANGELOG.md` (read HEAD's `pyproject.toml` first; expected 0.289.0),
  `pyproject.toml` and `uv.lock`, `campaigns/CLAUDE.md` (the *Campaign
  lists* and *L2* bullets rewritten to the new model, one revision), the
  root `CLAUDE.md` (the status window: one block, keep four), the build
  plan (§ 7e.8 marked built, § 7e.13 M6 with the routine choices, the
  header revision, a change-log row), `OPEN-ITEMS.md` #57,
  `SANDBOX-RESET.md` if the seeder changed. Commit; **never push** (see
  the top of this prompt).
- Then the live-pass step page, published as an artifact, following the
  Step-by-Step Instructions standard and the memory notes
  [[runbook-never-leave-the-surface-mid-section]] and
  [[steps-name-the-app-and-the-tab]]: every value pre-filled from a read
  of crm-test (parse `.env` in Python, never `source` it); the pass runs
  as Mark Marketing and builds one dynamic list (leads at Contactable with
  a phone), one exclusion list through Exclude, one static list through
  Add people, a copy, and a campaign that names the dynamic list.

## 3. Things this session must know

- **Parallel sessions share this clone and its git index.** Doug's M5 pass
  may lead him, or a session he opens, to commit a fix meanwhile. Stage
  files by name, never `git add -A`; audit `git show --stat HEAD` after
  each commit; read `git log --oneline -5` before writing `pyproject.toml`,
  `CHANGELOG.md` or `OPEN-ITEMS.md`, and re-read a file right before each
  edit. Never open a file for writing before you have read it.
- `uv run pytest -q` is the suite (about 4 minutes; run it in the
  background). `tests/test_comms_endpoints.py::test_disabled_returns_503`
  fails in the full run and passes alone — order-dependent, known, not
  yours.
- The web process's requests are cut off after about a minute; a list run
  over thousands of records already pages and caps (`STEP_CAP`); keep it
  so.
- A CRM id is 17 alphanumerics; the test fakes' hyphenated ids are refused
  by `_CRM_ID` — give test records explicit ids where an endpoint checks
  them.
- Memory notes to honour: [[buttons-never-disabled-validate-on-click]],
  [[no-page-width-caps-density-by-packing]],
  [[sessions-appjs-single-scope-collisions]] (one IIFE per page script;
  grep a name before declaring it), [[steps-name-the-app-and-the-tab]],
  [[runbook-never-leave-the-surface-mid-section]], [[lists-one-item-per-line]],
  [[patch-scripts-read-before-open-for-write]].

## 4. The report at the end

Review list: what changed, where, what to look at, what to test; what the
live pass needs on crm-test that is not there yet. Then **What next**: the
step page's address, the push Doug owes, M7 (Constant Contact per list and
the email campaign, § 7e.9 first half) as the recommended next step, and
the handoff's § 7 layout question still open.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 10-26-26 00:40 | Claude (Claude Code) | Written at the end of the M5 session, at Doug's request, for a session that runs while he does the M5 live pass; the plan is a draft for his approval in that session's first reply. |
