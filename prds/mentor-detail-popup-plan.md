# Mentor Detail from the Available Mentors List — Plan

**Status:** Approved (Doug, 2026-09-01: "Build it", Assign button included) · **Built as v0.220.0** — live verification owed (`OPEN-ITEMS.md` #31) · rev 2
**Author:** Claude (grounded in a code read of `assignments/`, `directory/`,
`mentoradmin/`; no CRM reads were needed)

## 1. The goal in one sentence

In Client Administration, clicking a mentor's name in the Available Mentors
list opens a read-only detail popup showing **all of that mentor's field
values**, with an Assign button in its footer so a staff member who likes what
they see can complete the assignment without backing out.

**Doug's rulings (2026-09-01):** view-only — editing stays in Mentor
Administration; and yes, include the Assign/Reassign button ("save time for
the user if the mentor is the right fit").

## 2. Where it fits — reuse, not a fourth mentor view

The app already renders a full CRM-arranged mentor detail: the Workspace
Directories pop-up reads `CMentorProfile`'s **own CRM detail layout** live
(`directory/service.detail` → `{entity}/layout/detail`) and renders it with the
shared type-aware renderer `directory/frontend/detail-render.js`
(`window.CBMDirRender`, already used by three pages). That engine is the plan's
core: it auto-syncs when the CRM team rearranges the layout, humanizes labels,
and handles every field type including wysiwyg (sanitized) and composed
addresses.

Two deliberate gaps in that engine get closed for this use, without changing
the directory's behaviour:

- **"All fields" is literally all.** The CRM layout shows only fields an admin
  placed on it. `detail()` gains an opt-in `include_unplaced=True` that appends
  one final **"Other fields"** panel: every *stored scalar* field of the entity
  not already placed (system plumbing — `id`, `deleted`, `versionNumber`,
  attachment-id fields — excluded; `createdAt`/`modifiedAt` included). Default
  stays `False`, so the directory pop-up is untouched.
- **Linked-Contact facts.** The mentor's reachability lives on their Contact,
  which the CMentorProfile layout doesn't carry. The payload adds a
  best-effort **Contact panel** (first/last, email, phone, address, LinkedIn —
  the same fields Mentor Administration merges), rendered like any other
  panel. Unreadable Contact ⇒ the panel is absent, never an error.

## 3. Design

### Backend

- **New endpoint** `GET /api/assignments/mentors/{mentor_id}/detail` in
  `assignments/router.py`, behind the existing Client Administration gate
  (`_require_user`), running **as the signed-in user** so their field ACL
  applies — a field the role can't read simply isn't in the payload
  ([[espo-field-acl-silently-strips-writes]] works both ways; fewer fields than
  an admin sees is correct behaviour, not a bug).
- It calls `directory.service.detail(client, DIRECTORIES["mentors"], id,
  user_id, include_unplaced=True)`. The mentors `DirectoryConfig` already has
  `editable=False`, so every field arrives read-only; the assignments frontend
  additionally ignores `editable`/`editHandoff` outright — this popup never
  edits. Cross-package import is an accepted pattern here (sessions already
  imports from assignments).
- Errors map through the existing `_crm_failure`, so a 403 names the denied
  entity and operation.
- **No new CRM read grant is assumed**: the Client Administration Team already
  reads `CMentorProfile` (the picker), and the layout API is readable by
  ordinary users ([[espo-layout-api-readable]]). What has *never* been
  exercised under that role is the full-field select and the layout read — see
  § 6.

### Frontend (`assignments/frontend/`)

- **Promote `directory/frontend/detail-render.js` → `frontend/shared/
  detail-render.js`** (same `window.CBMDirRender` global), updating the three
  directory HTML pages to the `/shared/` path. This mirrors how
  `conversation.js` became shared. Rejected alternative: loading it cross-app
  from `/directory/mentors/` — couples this page to another app's mount.
- **The name cell becomes a link.** `renderMentorRows` renders the mentor name
  as a button-styled link (the row today has no click handler at all, so
  there's no conflict). Keyboard-reachable, real `<button>`.
- **A second, stacked modal** in the engagement-popup shape (90% of the
  window, resizable, pinned title bar and footer, only the body scrolls — the
  same structure as `#engModal`; no width cap, per the density ruling).
  - **Header strip**: name, status chip, and the app-computed numbers the row
    already holds — Active / Max / Available / Assigned (30d) / Last assigned —
    passed straight from the `reviewMentors` row, so no second backend call
    and the popup always agrees with the grid.
  - **Body**: the CRM layout panels via `CBMDirRender.panelsInto`, then the
    Contact panel, then "Other fields". Empty values render "—" (never
    vanish). Email addresses render as compose links (the renderer already
    prefers `CBMQuickMail` when loaded, which this page loads).
  - Detail-load failure shows a message inside the popup; the picker beneath
    is untouched.

### The Assign button

The Available Mentors modal is engagement-agnostic today (toolbar
`reviewMentorsBtn`); assignment happens in a separate per-engagement select
card (`openMentorPicker`). The button therefore needs engagement context:

- `openMentorReview()` gains an optional `{engagement, mode}` context, and the
  assign/reassign card gains a **"Browse mentors…"** link that opens the
  Available Mentors modal *scoped to that engagement* (title reflects it:
  "Available Mentors — assigning “Acme Corp”"). The toolbar button keeps
  opening it unscoped.
- The detail popup's footer carries **Assign this mentor** (or **Reassign to
  this mentor** in reassign mode). Clicked with context, it runs the existing
  confirm card → `performAssign` / `performReassign` — same guard rails: the
  server-side stale-write re-read, the grid refresh on 400, the quick-compose
  with the `MentorAssignmentNotice` template on success. On success both
  modals close.
- Clicked **without** context (opened from the toolbar), the button is still
  present and enabled — per the buttons-never-disabled convention — and the
  click explains: open the list from an engagement's Assign control to assign.
  In reassign mode the current mentor's own detail shows the same explanatory
  message instead of offering a no-op reassign.
- An ineligible mentor (not accepting, at capacity, wrong status) still shows
  the button; the confirm card states the numbers and the server guard has the
  final word. No client-side eligibility veto — the roster browser
  deliberately lists everyone.

### What is deliberately NOT here

- **No editing, no write path.** Mentor Administration owns `CMentorProfile`
  writes; one write surface per record.
- **No feature flag.** This is a new door onto reads the team already has,
  additive UI in one app; precedent is v0.209/v0.210 (columns, engagement
  popup) which shipped flagless. Rollback is a revert.
- **No new CRM fields or grants**, and no change to the directory pop-up's
  behaviour (the `include_unplaced` default keeps it exactly as it is).

## 4. Implementation steps

1. `directory/service.py` — `include_unplaced` option on `detail()` +
   `_unplaced_panel()` (stored-scalar sweep from live metadata, minus placed
   names and system plumbing); Contact panel assembly for the mentors kind
   behind the same option (or a small wrapper in `assignments/service.py` —
   decide at build time by whichever keeps `detail()`'s signature honest).
2. Move `detail-render.js` to `frontend/shared/`; update
   `directory/frontend/{index,record,mentor}.html` script tags.
3. `assignments/router.py` — the new endpoint + `_crm_failure` mapping;
   `assignments/service.py` — thin pass-through if step 1 chose the wrapper.
4. `assignments/frontend/index.html` — the new modal markup (copy the
   `#engModal` pinned-bar structure) + the shared-renderer script tag (after
   `busy.js`, before `app.js`).
5. `assignments/frontend/app.js` — name-cell link, `openMentorDetail(m)`,
   review-modal engagement context, footer wiring into the existing
   assign/reassign paths. **Grep any new helper name first** — one shared IIFE,
   a duplicate declaration silently wins.
6. `assignments/frontend/styles.css` — stacked-modal z-index, header strip,
   name-link styling.
7. Tests (`tests/test_assignments.py`, `tests/test_directory.py`):
   - endpoint: 401 unauthenticated, team-gate 403, payload shape against fake
     metadata/layout, read-only enforced, Contact-read failure degrades to an
     absent panel;
   - `include_unplaced`: unplaced scalar appears once, placed fields not
     duplicated, system fields excluded; directory default unchanged;
   - fakes keep enforcing `maxSize ≤ 200` (no new list call should need one);
   - the three directory pages still load the renderer (path check).

## 5. Risks / traps to respect while building

- **Field ACL strips reads silently** — the popup rendering must tolerate any
  field being absent. It does by construction (layout-driven, "—" for empty).
- **A 403 buried in best-effort code reads as "empty"** — the Contact panel
  and the detail read must log at debug/warning like the directory does, and
  the *main* detail read is NOT best-effort: it surfaces its error in the
  popup.
- **Stub harnesses don't issue real list/layout requests** — the unit tests
  prove shape, not the live ACL story (§ 6).
- **Second-modal stacking**: `display:flex` beats `[hidden]`
  ([[harness-js-clicks-bypass-overlays]]) — verify close/reopen with a real
  mouse click in the browser pass.

## 6. Verification owed after build

crm-test first, then prod, per the standard lane:

1. As a **real Client Administration Team non-admin** (an admin proves
   nothing): open the picker, click a name, confirm the panels populate and
   match the CRM's own detail view of the same mentor; note any fields the
   role's ACL hides and confirm that's acceptable to Doug.
2. Assign path end-to-end from the detail popup (scoped open → Assign →
   confirm → quick-compose appears; grid row updates), and the unscoped
   toolbar open shows the explanatory message.
3. The three directory pages after the renderer move (grid pop-up, View
   Contact Overview, mentor page) — one open each.
4. Add the pass to `OPEN-ITEMS.md` § live-verification (item 20 family) at
   build time; delete on completion.
