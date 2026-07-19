# CBM Workspace + Directories — Plan (v0.1)

_Planning/handoff doc. Status: DESIGN — not yet built. Author-reviewed with
Doug 2026-07-19; the "Decisions (locked)" section records his rulings from the
planning session. Build proceeds in the phases at the end._

## 1. Goal

Give mentors (and, later, other staff) a **CRM-style workspace**: a central
launcher that opens **directories** (Companies, Contacts, Mentors) and the
**tools they're entitled to** (My Mentor Profile, the session apps) as a set of
windows they pick from one home screen — "much like a standard CRM."

The workspace **replaces the current portal at `/`**. It is an evolution of the
existing `portal/` home, not a new auth surface: the single sign-on
(`/api/portal/login`, shared `staff_user` session) is unchanged; the home screen
is redesigned into a launcher, and three new **directory** pages are added.

## 2. Decisions (locked)

From the planning session (Doug's answers):

1. **"Windows" = browser tabs, de-duplicated.** Opening a directory/tool in a
   separate browser tab is acceptable; the requirement is to **prevent duplicate
   tabs** — re-clicking a destination reuses/navigates its existing tab rather
   than opening a second copy. (No in-page floating-window manager.)
2. **Directories = grid + preview pane + detail pop-up.** Each directory is a
   searchable/sortable grid with a quick **preview pane** for at-a-glance review,
   and a **pop-up** for the fuller record view.
3. **Edit is limited to records the user owns.**
   - **Contacts + Companies** — inline edit **in the pop-up window** (reuse the
     existing metadata-driven Details editor).
   - **Mentors** — Edit hands off to **My Mentor Profile** (`/mentorprofile/`);
     a regular mentor only owns their own profile.
4. **Audience: mentors now, extensible.** Build for Mentor Team first; the
   engine is config-driven so other teams/directories can be added later.
5. **Replace the portal.** The workspace becomes the post-login landing screen.

### CRM facts that shape the design

**The Mentor Role already grants READ on all Contacts and all Accounts**
(Doug, 2026-07-19). So the Company and Contact directories are genuinely
**org-wide** with **no CRM role change**. Reads still run as the signed-in user
(ACL stays the boundary) — it simply happens to be permissive for those two
entities. Because the grids can be large, server-side search + `offset`
pagination is the default (not load-everything). **Edit** remains
owned-records-only via the `assignedUsers`-membership gate — a mentor can read
everyone but only edit their own.

**Columns and field arrangement are read LIVE from EspoCRM's own layouts**
(Doug's ruling 2026-07-19: "the exact same columns as defined in the list view
of ESPO"). The EspoCRM layout API is readable with our credentials
(probed live on crm-test 2026-07-19):

- `GET api/v1/{entity}/layout/list` → the **grid columns** (exactly the CRM's
  list view). Verified:
  - **Account** — `name`(link) · `billingAddressCity` · `cCompanyType` · `website`
  - **Contact** — `name`(link) · `account` · `emailAddress` · `phoneNumber` · `addressCity`
  - **CMentorProfile** — `name`(link) · `contactCity` · `mentorStatus` · `mentorType` · `cbmEmail`
- `GET api/v1/{entity}/layout/detail` → the **detail panels** (rows +
  `customLabel`/`tabLabel` grouping) that drive the pop-up's "all data in view
  mode" arrangement — mirrors the CRM's own detail screen.

The directory therefore **hardcodes no columns**; it fetches the layouts at
runtime (cached briefly) and stays in sync when the CRM's layouts change — the
same "CRM is the source of truth" approach already used for enum options and
required flags. Requires a small new `EspoClient.layout(entity, name="list")`
(a `GET {entity}/layout/{name}`). Column **labels** come from the CRM i18n
(`GET api/v1/I18n?scope={entity}`, fetched once/cached) with the existing
`sessions/details.py:_label` humanizer as the fallback; field **types** come
from `metadata(entityDefs.{entity}.fields)` (already used).

## 3. Architecture

Follows the **`sessions/` engine pattern**: one engine + one router factory +
one shared frontend, with a per-kind `DirectoryConfig`. New package
`directory/`.

```
directory/
  __init__.py          # exports api_routers (one per kind) + DIRECTORIES
  config.py            # DirectoryConfig + DIRECTORIES (companies/contacts/mentors)
  service.py           # list/search/preview/edit, all as the signed-in user
  router.py            # make_router(cfg) -> APIRouter, per-kind gate, _crm_failure
  frontend/            # one shared vanilla-JS frontend (index.html, app.js, styles.css)
```

- **Routes:** `/directory/{kind}` for `companies` | `contacts` | `mentors`,
  API under `/directory/{kind}/api/...`. The frontend derives its kind from
  `location.pathname.split("/")[2]` (the `sessions` `SLUG` trick).
- **Mounting** ([core/app.py](../core/app.py)): inside the `assignments_active`
  block, include each directory router and static-mount `/directory/{kind}`
  (guarded by `assignments_active and DIR.is_dir()`), after API routes so routes
  win. Add a `WORKSPACE_FRONTEND_DIR`/`DIRECTORY_FRONTEND_DIR` constant next to
  the existing `*_FRONTEND_DIR` set. Add `form_alias` entries
  (`/directory`, `/companies`, `/contacts`, `/mentors`, `/workspace`).
- **Auth/session:** shared `staff_user` session; the `_membership_ttl`
  middleware already covers `/api/directory/*` (everything except `/api/portal`),
  so team-refresh + dead-token eviction come for free.
- **Config** ([core/config.py](../core/config.py)): new
  `WORKSPACE_ALLOWED_TEAMS` (default `Mentor Team`) → `workspace_allowed_teams_list`.
  Each directory's read gate uses it; **the true data scope is EspoCRM ACL**, so
  the team gate is a coarse "who sees the workspace at all," not the record
  filter.

## 4. The launcher (redesigned portal home)

Redesign `portal/frontend/` from a flat link list into a **grouped launcher**:

- **Directories** — Companies, Contacts, Mentors (shown to workspace-entitled
  users).
- **My tools** — My Mentor Profile, My Sessions (`/mentorsessions/`), and
  Partner/Sponsor Sessions when entitled. Already computed by
  `portal.router._apps_for` via `is_member(...)`; the launcher just re-groups it.
- **Forms** — the public intake links (existing `_forms`).
- **CRM** — the EspoCRM link (mentors/admins only, existing).

Backend: extend `portal.router._apps_for` (and `_home_payload`) to include the
directory destinations so the launcher renders them **and** so the portal's
`?next=` open-redirect guard (`nextTarget`) forwards back to a directory after a
login bounce. Add a `group`/`kind` field to each app entry so the frontend can
section them.

### Tab de-duplication

Each tile opens its destination with a **stable window name**:

```js
function openWindow(url, name) {
  const w = window.open(url, name);   // reuse the named tab if it exists
  try { w && w.focus(); } catch (_) {}
  return w;
}
// names: cbm-companies, cbm-contacts, cbm-mentors,
//        cbm-mentorprofile, cbm-mentorsessions, cbm-partnersessions, ...
```

- **Guaranteed:** re-clicking a tile **reuses/navigates** the existing tab — no
  duplicates.
- **Best-effort:** `.focus()` raising the tab to the foreground is
  browser-dependent (Chrome often won't foreground from a background tab). We do
  not over-promise "jumps you there."
- **Optional nicety (phase 2+):** a `BroadcastChannel('cbm-workspace')` where
  open pages announce presence so the launcher can badge tiles as "open" and post
  a focus request.

## 5. Directory engine

`DirectoryConfig` (per kind):

| field | companies | contacts | mentors |
|-------|-----------|----------|---------|
| `entity` | `Account` | `Contact` | `CMentorProfile` |
| `title` | Companies | Contacts | Mentors |
| `search_attr` | `name` | `name` | `name` |
| `columns` | **read live** from `Account/layout/list` | **read live** from `Contact/layout/list` | **read live** from `CMentorProfile/layout/list` |
| `list_fn` | `service.list_companies` | `service.list_contacts` | reuse `assignments.service.list_all_mentors` |
| `peek_entity` | `Account` | `Contact` | `CMentorProfile` |
| `editable` | inline (owned) | inline (owned) | handoff → `/mentorprofile` |

**Columns are never hardcoded** — `GET /records` resolves them from
`{entity}/layout/list` (see §2 "CRM facts"), maps each item's `name` to a
`select` field + a label (CRM i18n / humanizer) + a type
(`metadata`), and returns `{columns:[...], rows:[...], total}`. The `list_fn`
selects at least every column field plus `id` and the assignment fields needed
for the owned-edit gate. Sorting respects the layout's `notSortable` flags.

### Endpoints (per kind, `/directory/{kind}/api`)

- `GET /session` — identity + kind UI config (columns, filter options, whether
  editing is inline or handoff, the handoff URL for mentors).
- `POST /logout`.
- `GET /records?q=&filters=&page=` — grid feed, ACL-scoped, paginated
  (`max_size=200`, `offset` loop; server-side `where contains {search_attr}`,
  min 2 chars when `q` present).
- `GET /records/{id}` — preview-pane payload (light peek fields).
- `GET /peek/{entity}/{id}` — full detail pop-up (reuse `sessions.service.peek`
  + `PEEK_FIELDS`; a 403 degrades to `{restricted:true}`).
- **Edit (contacts/companies only):**
  - `GET /records/{id}/edit` — editable field spec + values (reuse
    `sessions.details.build_details` shape, single-entity).
  - `PUT /records/{id}` `{changes:{...}}` — whitelisted save (reuse
    `sessions.details.save_details`: field whitelist, owned-record gate,
    enum-drift tolerance). Entity allowlisted; unknown → 404.

### Reuse map (existing code)

- **Layouts (NEW):** add `EspoClient.layout(entity, name="list") -> list` (a
  `GET {entity}/layout/{name}`) for the live grid columns + detail arrangement;
  labels via a new `EspoClient.i18n(scope)` (or reuse metadata language),
  fallback `sessions/details.py:_label`.
- **List/search:** `EspoClient.list` (paginate — default `max_size=50`!),
  `sessions/details.py:search_contacts`, `comms/service.py:search_companies`,
  `assignments/service.py:list_all_mentors`.
- **Preview/detail pop-up:** `sessions/service.py:peek` + `PEEK_FIELDS`;
  frontend `openPeek`/`openAggregatePeek`/`peekFieldsInto`/`renderPeekValue`.
- **Grid UI:** `sessions/frontend/app.js` `renderTable`/`setSort`/`sortRows`,
  `makeColumnsResizable`.
- **Edit:** `sessions/details.py` `build_details`/`save_details`,
  `_acl_edit_levels`/`_editable_for`/`_clean_changes`; wysiwyg via
  `frontend/shared/richtext.js` (`CBMRichText`); phone via
  `frontend/shared/phone-format.js`; email compose via
  `frontend/shared/quickmail.js`.
- **Auth/gate:** `assignments/auth.py` (`is_member`, `current_user`,
  `refresh_membership`), `assignments/espo_user.py:client_for`, the router
  `_require_user` + `_crm_failure` pattern.

## 6. UX per directory

- **Grid toolbar** (one row above every grid, same layout for all three kinds):
  - **top-left — Filter.** A Filter button/panel with the per-kind filters
    (e.g. mentor status/accepting; account type; contact has-email). Active
    filters show as removable chips.
  - **top-center — Search.** The server-side full-text search box (min 2 chars).
  - **top-right — View · Edit buttons.** They act on the **selected row**
    (click a row to select — the Client-Administration selection pattern).
    **View** opens the detail pop-up in view mode; **Edit** opens it in edit
    mode (Contacts/Companies, owned) or hands off to `/mentorprofile` (Mentors,
    own row). Both stay **active + visible**
    ([[buttons-never-disabled-validate-on-click]]): with no row selected they
    prompt "select a record first"; Edit on a non-owned record shows "you can
    only edit records you own." Double-clicking a row = View.
- **Grid** — columns are exactly the CRM list-view layout (§5), sticky-header,
  sortable (honoring `notSortable`) + resizable columns, pagination controls.
  Full-width, no page-width cap (per the density ruling). First column = the
  record name; clicking a row selects it and populates the **preview pane**.
- **Preview pane** (right, drag-splitter like the session Overview) — a
  **read-only, information-dense** view showing **as much as possible**: driven
  by the CRM's `layout/detail`, it renders the record's readable fields
  (non-empty first), type-aware (email→compose link, phone→`tel:`, url→external,
  multiEnum→chips, date/currency/longtext) via the existing peek value
  renderers, plus Copy affordances. A **Details** button opens the full pop-up;
  for editable kinds an **Edit** button.
- **Detail pop-up** — **all data in view mode**, arranged by the CRM's
  `layout/detail` panels (tab/section grouping preserved). A header **Edit**
  button (shown when the user's ACL grants edit — `_acl_edit_levels` /
  `_editable_for`) **switches the pop-up to edit mode**: the same fields become
  the metadata-driven inline editor (grouped, gold changed-dot + sticky Save
  bar like the Details tab), saving via `PUT /records/{id}`; Cancel returns to
  view mode.
- **Edit affordance is always visible** ([[buttons-never-disabled-validate-on-click]]):
  a non-owned record's Edit click shows "you can only edit records you own —
  ask CBM staff if you need to," it doesn't hide the button.
- **Mentors** — the Edit button on the user's **own** row/pop-up opens
  `/mentorprofile/` in the `cbm-mentorprofile` named tab; other mentor rows are
  read-only (view-mode pop-up only).

## 7. Gotchas (enforced by existing code — do not relearn)

1. **Never `where`-filter on `assignedUserId`/link attrs** — prod field-ACL 400s
   it. Scope owned-ness by reading rows + Python `is_assigned_to`
   ([[crm-test-assignment-acl-fields]]).
2. **`assignedUsers` (multi), not `assignedUser`** — single is disabled on
   Account/Contact/CMentorProfile on prod; test membership over the whole
   `assignedUsersIds` list, never `[0]`.
3. **`EspoClient.list` default `max_size=50`** — always pass it and paginate.
4. **ACL by token replay** — build the client with `client_for(...)`; a
   forbidden read comes back 403 → degrade to `{restricted:true}`, never 502.
   Add an **entity allowlist** on the generic read/edit proxy so it can't be
   pointed at arbitrary entities (like `PEEK_FIELDS` / details PUT allowlist).
5. **401 → portal bounce**: on 401 send the user to `/?next=/directory/{kind}/`;
   the destination must be in the user's entitled `apps` or `nextTarget` drops
   it — so add the directories to `_apps_for`.

## 8. Phasing

- **Phase 1 — BUILT (v0.100.0, 2026-07-19).** New `directory/` package
  (config/service/router/frontend) with the three grids (live-layout columns,
  search/sort/resize/filter/paginate), preview pane, and the detail pop-up.
  Portal redesigned into the grouped launcher with named-tab de-dup. Config +
  mounting + aliases + `EspoClient.layout`/`.i18n`. 789 tests green; read path
  exercised live against crm-test; full UI loop verified in the stub harness.
  **Inline edit for owned Contacts/Companies (the originally-Phase-2 work) was
  folded in** — the pop-up's Edit button switches to the metadata-driven
  editor. Mentors' Edit = handoff to `/mentorprofile`. NOT yet driven live as a
  non-admin mentor (needs a portal login).
- **Phase 2 — DONE within Phase 1** (inline Contact/Company edit shipped above).
- **Phase 3 — polish (future).** `BroadcastChannel` open-tab awareness/badges;
  saved filters; column-set memory; live verification as a non-admin mentor;
  any extra directory kinds requested.

## 9. Open questions / to confirm during build

- **Columns — RESOLVED (Doug 2026-07-19):** exactly the CRM list-view layout,
  read live from `{entity}/layout/list` (§2/§5). No hand-picking.
- **Preview vs pop-up — RESOLVED (Doug 2026-07-19):** preview = read-only,
  as-much-as-possible (detail-layout-driven); pop-up = all data in view mode +
  an Edit button to switch to edit mode when permitted (§6).
- **Filters** per directory — still to confirm which filters mentors want on
  each grid (proposal: mentor status/accepting; account type; contact
  has-email). Filters are additive to the live layout columns.
- **Contact/Company inline-edit field set** — reuse the Details editor's live
  metadata-driven whitelist as-is (proposed), or a curated subset. The
  view-mode arrangement follows `layout/detail` regardless.
- **Launcher grouping/labels** — section titles and which tiles appear for
  Mentor Team vs. other teams.
- **Deploy note** — all three App Platform apps build from `main`, so this ships
  to crm-test **and** prod on push; confirm the Mentor-Role read-all
  Contacts/Accounts fact **and** the list/detail layouts are identical on prod
  before relying on org-wide grids there (the layouts are read live per-env, so
  they'll self-match, but the CRM read grant must exist on prod).

## 10. Test plan (per phase)

- Service: list/search/paginate (ACL-scoped, `max_size` respected), preview,
  peek degrade-on-403, edit whitelist + owned-gate + enum-drift drop, unknown
  entity → 404.
- Router: 401 unauth, 403 wrong-team, gate per kind.
- Frontend: stubbed-API harness ([[sessions-frontend-stub-harness]]) — grid
  render/sort/resize/search/filter/paginate, row→preview, Details pop-up,
  edit-in-pop-up round-trip (owned) + non-owned message, mentor Edit→handoff,
  launcher tab de-dup (named-window reuse), no console errors.
