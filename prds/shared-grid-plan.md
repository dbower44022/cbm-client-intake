# Shared grid, divider and loading spinner — plan

Last Updated: 10-28-26 20:57 · Revision 1.0 — change log at the end.

**Status: approved 10-27-26; stops 1–3 built as v0.294.0; live-passed on crm-test 10-28-26 00:23**
(https://claude.ai/artifact/AWjNEvmyq7mrwLVyDd2yJF).
Made on the way: the *Loading…* pill appears only after 400 ms, so a fast
page never flashes it; widths are set as outer widths and the last column
takes the remaining room, so a dragged column moves by exactly the drag.

## 1. The ruling

Doug, 10-27-26 21:30, word for word: "All grids must have resizable
columns, alternating colored rows, multi-column sorting, a divider bar to
resize the preview pane, and Should always show a spinning icon while
another page or function is loading."

Doug, 10-27-26 21:41, on scope: option B. The behaviour is built once, as
shared parts every page loads, and fitted to the three Lists grids first.
The other applications follow one per release. The standard goes into the
root `CLAUDE.md` when the shared parts exist, so every new or changed grid
must use them. Standing cost, accepted: for some weeks the older screens
behave differently from the Lists screens.

## 2. What the user gets

- **Resizable columns.** Every grid column has a handle on its right edge.
  Dragging it changes the column's width. A double-click on the handle fits
  the column to its widest cell. A keyboard user tabs to the handle and
  presses the left and right arrow keys. Each grid remembers its widths in
  that browser; *Reset columns* in the grid's footer restores them.
- **Alternating row colours.** Every second row is shaded, from the page's
  colour tokens, in both themes. The selected row and a hovered row stay
  distinct from the shading.
- **Multi-column sorting.** A click on a heading sorts by that column alone;
  a second click reverses it. Shift-click adds the column as the next sort
  key, and the heading shows its position: ▲1, ▼2. A plain click starts
  again from one column. The grid's footer says what it is sorted by, in
  words, with *Clear sort*.
- **A divider for the preview pane.** On a screen with a preview panel, a
  bar between the grid and the panel drags to resize both. Arrow keys move
  it when it has focus; a double-click restores the default. The width is
  remembered in that browser.
- **A spinner while anything loads.** Three cases, all one shared look:
  1. a grid or panel waiting on the server shows a spinner over itself,
     with its old content dimmed, until the answer arrives;
  2. a page opening shows a spinner until its first data has arrived;
  3. a link or button that opens another page shows a spinner on itself
     until the browser leaves or the new tab has opened.
  The pressed-button spinner `busy.js` already gives stays as it is.

## 3. How it is built

- **`frontend/shared/grid.js` and `grid.css`** — `CBMGrid.enhance(table,
  options)` adds the handles, the shading and the sorting to an existing
  `<table>`, so a screen keeps drawing its own rows. Two sort modes:
  - **in the browser** (the grid holds every row): the component sorts the
    rows on any column, numbers as numbers, dates as dates;
  - **on the server** (the grid holds one page): the component calls the
    screen back with the list of sort keys, and only columns the server can
    sort are sortable. The others say so in the heading's tooltip.
- **`frontend/shared/splitpane.js` and `.css`** — `CBMSplit.attach(left,
  right, options)` puts the divider between two panes.
- **The spinner** — `busy.js` gains `CBMBusy.loading(element, promise)`,
  the overlay spinner, and the page-opening and link cases. Like the rest
  of `busy.js` it never disables anything.
- **Widths, sort and divider position** are stored per grid in the
  browser's own storage, wrapped so a blocked store changes nothing but the
  memory.

## 4. Fitted first: the Lists screens

- **The list view**: every column resizable and sortable in the browser,
  multi-column; shading; the divider between the grid and Preview; the
  spinner over the grid while the lists load and over Preview while a list
  is read.
- **View** (`list-members.html`): resizing and shading on every column.
  Sorting on the server, multi-column, over the columns the server can
  sort: name, type, the group that brought each person in, and the three
  reach columns. The extra columns (company, status, email address, phone,
  city, last changed) are read one page at a time and cannot be sorted
  without reading the whole list; they are not sortable. The members route
  gains a `sort` list (`name:asc,type:desc`). Sorting by name still reads
  every name, so it keeps its 2,000-member limit.
- **Edit**: the static list's member grid and the *Who this change moves*
  table get the same treatment.

## 5. Stops

Work pauses after each stop for Doug's go-ahead, unless he says to run
several together.

1. **Stop 1 — the shared parts** (about two days): `grid.js`, `splitpane.js`,
   the spinner in `busy.js`, their stylesheets, and a test page under the
   preview harness. Tests for the sort order, the stored widths and the
   keyboard handles.
2. **Stop 2 — the Lists screens** (about a day and a half): the list view,
   Preview's divider, Edit's grids, View with server-side multi-column sort
   and the route's `sort` list. Checked in a headless browser against the
   application over the test fakes.
3. **Stop 3 — the standard, the documents and the live pass** (about half a
   day): the convention in the root `CLAUDE.md`, a guard test that the
   Lists screens load the shared parts, the changelog and version, the
   rollout list in `OPEN-ITEMS.md`, then a live pass on crm-test as Mark
   Marketing with a results page.

## 6. The rollout after this plan

One application per release, each a small item in `OPEN-ITEMS.md`: Client
Administration, Mentor Administration, the three Management screens,
Submission Admin, the Directories, My Email, Events, System Settings, and
the rest of Marketing Management (Leads, Campaigns, Review, Calls,
Imports). Each server-paged grid needs its own server sort work, and the
item says which columns it can sort.

## 7. Cost

- About four days for this plan.
- About two to three weeks for the whole rollout, one application at a
  time.
- A server-paged grid sorts only on columns its server can sort.
- Mixed behaviour between the Lists screens and the rest until the rollout
  finishes.

## 8. Rollout 1 — the rest of Marketing Management (drafted 10-28-26)

Doug, 10-28-26: "Let's roll out the grid to all of the Marketing Management
apps first. Then we will expand from there."

**The grids, and how each can sort.**

| Grid | Where | Its rows | Multi-column sort |
|---|---|---|---|
| Campaigns | Campaigns tab | all, in the browser | yes, in the browser |
| Call list | Calls tab | all, in the browser | yes, in the browser |
| Imports, templates, history | Imports tab | all, in the browser | yes, in the browser |
| Links, Responses, Touches | the campaign's page | all, in the browser | yes, in the browser |
| Recipients | the campaign's page | the application pages them from rows it already holds | yes, on the server (a `sort` list, as View's) |
| Leads | Leads tab | **the CRM pages them** | **one column** — the CRM sorts a page by one field |
| Review | Review tab | **the CRM pages them** | **one column** — same |

Every grid gets resizable columns, the shading, and a spinner over it while
it loads. None of these tabs has a preview pane, so no divider.

**The decision this needs** (put to Doug 10-28-26): Leads and Review. The
CRM sorts a page of records by one field only, and the Leads grid was built
to read one page at a time because reading every lead stopped silently at
2,000 and timed out (v0.267.0). Multi-column sorting there means either one
column only, or reading up to 2,000 matching leads on every sort to order
them in the application.

**Decided 10-28-26.** Doug asked whether the slowness was the grid or the
database, and named three alternatives: two writes to keep a copy in step, a
change to EspoCRM itself, or our own API in front of it. Measured on
crm-test: the CRM's web API sorts by one field (a list is refused) and
returns 200 rows a request; the database underneath is not the limit. Doug
chose to try changing the CRM: a custom endpoint, `GET /api/v1/SortedList/{type}`
(`crm/extensions/sorted-list/`, `sorted-list-crm-handoff.md`), installed on
crm-test 10-28-26 — two-column sort correct, as fast as the standard
one-column list (150–190 ms), the standard list's access control. Leads,
Review and Recipients sort through it; a CRM without it sorts by one column.

**Stops.** Work pauses after each for Doug's go-ahead.

1. **The browser-sorted grids** (built 10-28-26, commit b3e8edf) — Campaigns, Call list, the three Imports
   grids, and the campaign page's Links, Responses and Touches (about a
   day).
2. **The server-sorted grids** (built 10-28-26 as v0.296.0) — Recipients with a `sort` list, and Leads
   and Review as decided (about a day).
3. **Documents and the live pass** on crm-test as Mark Marketing, with a
   results page (about half a day). Documents done; pushed and live-passed
   10-28-26 16:33 (https://claude.ai/artifact/Gf8B5gXMmDLgUwZZ1dAjTS), as an
   administrator and as Mark Marketing.

## 9. Rollout 2 — Mentor Administration (drafted 10-28-26)

Doug, 10-28-26: option 1, Mentor Administration next.

**The grids.** Mentor Administration loads the whole roster into the
browser, so every grid sorts in the browser; no route changes and no CRM
change.

- **The roster** (`mentorTable`, the list screen) — 11 columns, one-column
  sort today. It gets resizable columns, shaded rows and a sort on several
  columns. The page's search and three filters stay as they are; the sort
  is applied after them, through `CBMGrid.sortBy` with the page's own
  values, so *Unlimited* still sorts above every number in Available and a
  blank count still sorts last. The default sort stays Mentor A–Z.
- **The Update Mentor Status results** (the table in its window) — 6
  columns, no sort today; it gets the shared grid.
- **A mentor's Documents tab** (`mdocTable`) — File, Type, Uploaded by,
  Uploaded; the action column never sorts.

**Spinners.** The roster, the mentor's record and the Documents list show
the spinner over themselves while they load (`CBMBusy.loading`).

**No divider.** No screen has a preview pane; a row opens the mentor's
record in place, as today.

**Stops.** Work pauses after each for Doug's go-ahead.

1. **Build** (built 10-28-26) — the three grids and the spinners, the old sort code
   removed, tests, and a check in the local harness.
2. **Documents, version and the live pass** on crm-test as a member of the
   Mentor Administration Team, with a results page. v0.297.0; also makes
   *Open in Drive* clickable with a reason (Doug's go, 10-28-26). Pushed
   and live-passed 10-28-26 20:55 (https://claude.ai/artifact/W2EsernSeTqMqSbtjXWYdP).

## Revision control

| Field | Value |
|---|---|
| Document | Shared grid, divider and loading spinner — plan |
| Version | 1.0 |
| Last Updated | 10-28-26 20:57 |
| Prepared by | Claude (Claude Code), for D. Bower |

### Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.0 | 10-28-26 20:57 | Claude (Claude Code) | § 9: rollout 2 live-passed on crm-test. |
| 0.9 | 10-28-26 20:45 | Claude (Claude Code) | § 9: stop 1 built; v0.297.0. |
| 0.8 | 10-28-26 20:33 | Claude (Claude Code) | § 9 rollout 2, Mentor Administration, drafted for approval. |
| 0.7 | 10-28-26 16:36 | Claude (Claude Code) | § 8: rollout 1 live-passed on crm-test. |
| 0.6 | 10-28-26 16:12 | Claude (Claude Code) | § 8: stop 2 built (v0.296.0); stop 3's documents done, the live pass owed. |
| 0.5 | 10-28-26 13:20 | Claude (Claude Code) | § 8: the decision for Leads and Review — the CRM sorted-list endpoint, measured on crm-test; stop 1 built. |
| 0.4 | 10-28-26 10:46 | Claude (Claude Code) | § 8 rollout 1, the rest of Marketing Management, drafted for approval with one decision. |
| 0.3 | 10-28-26 00:24 | Claude (Claude Code) | Live-passed on crm-test; nothing to fix. |
| 0.2 | 10-27-26 22:04 | Claude (Claude Code) | Approved; stops 1–3 built as v0.294.0; the two choices made on the way. |
| 0.1 | 10-27-26 21:41 | Claude (Claude Code) | Drafted from Doug's ruling of 10-27-26 21:30 and his choice of option B. |
