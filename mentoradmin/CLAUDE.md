# mentoradmin/ — Mentor Administration

Last Updated: 11-06-26 02:16 · Revision 1.6

Detail for the Mentor Administration application (`/mentoradmin`): the roster, the editable mentor record, completeness, provisioning and the status sweep.

Claude Code loads this file only when a session reads or edits files in this
folder. The rules other packages depend on stay in the root `CLAUDE.md`, which
also points here. Moved word for word from the root file on 10-20-26, when it
outgrew Claude Code's size limit; edit it here from now on.

## Mentor Administration — `/mentoradmin`

Staff-only, page title "Mentor Administration". The full mentor roster plus a
detail screen that edits any whitelisted field on `CMentorProfile`.

- **`EDITABLE_FIELDS` in `mentoradmin/service.py`** is the single source for the
  tabbed layout and the update whitelist. Fields marked `entity: "Contact"`
  route to the mentor's **linked Contact** (no linked Contact ⇒ a readable 400
  *before any write*).
- **Save sends only changed fields** (diffed against a render-time snapshot).
  Re-sending an unchanged value that has since drifted out of its CRM enum would
  400 the whole update.
- **Completeness badge** — a mentor is Complete when a Contact is linked and
  ethics/training/terms are all true (**background check is optional**); plus,
  if Active, a CBM email and a User assigned to *both* the member and its
  Contact. `publicProfile` is deliberately not part of completeness. The
  computed value persists to `recordStatus` on save **and on view** when it
  changed, so the grid self-heals; a manual `Duplicate` is never overwritten.
- **`reconcile_user_links` runs on every save** (best-effort), assigning the
  mentor's User to both the member and its Contact — this is what self-heals
  one-sided assignments.
- **Provisioning happens in TWO stages, keyed on `mentorStatus`** (Doug's ruling
  2026-08-17). `Accepted-Provisional` is a **signal** status, not a resting one:
  it means *accepted, still needs a Google account*.
  - **`Accepted-Provisional` → the Google Workspace account** (+ the All Members
    group), then the app **advances the record to `Provisional`** — so CBM can
    reach them during the provisional period. No EspoCRM login.
    `provision_mentor_email_steps`.
  - **`Approved` / `Active` → the EspoCRM login**, unchanged, on top of the same
    mailbox stage — so a mentor who jumps straight here still gets everything.
    It **never writes the status**: that would demote them.
  - The status advance requires a **confirmed** account (created and live, or
    already there). An UNKNOWN Directory check fails open for the *login* but must
    never advance the status — we don't record "has an account" on a guess. A
    stuck `Accepted-Provisional` is therefore the "account still owed" signal, and
    the sweep flags it.
  - Which stage runs is decided **server-side in the router** from the mentor's
    status; the frontend only asks. Both run in the SSE status window and never in
    `update_mentor`, because a mailbox create yields a **temp password a human
    must relay** (also why the sweep reports but never creates).
  - The group add is **non-fatal** (a distribution list is not the account), and
    an empty `GOOGLE_MEMBERS_GROUP` / Email-Setup address skips it — the address is
    its own switch. It needs a **third** DWD scope, `admin.directory.group`.
  - `_reserve_cbm_email` is what keeps the login-reuse guard sound now that every
    mentor reaches approval carrying a `cbmEmail`: an address is only stored if no
    User holds it as a userName and no *other* mentor profile holds it. A merely
    *existing* mailbox is not "taken" — a pre-created mailbox is the normal case.
  - The login half creates an EspoCRM User (`firstname.lastname@` the
    `MENTOR_EMAIL_DOMAIN` setting, default `cbmentors.org` — v0.217.0,
    welcome email via `sendAccessInfo`), places it in `MENTOR_TEAM_NAME`, links it
    as `assignedUser`, back-fills `cbmEmail`, and stamps the User onto the linked
    Contact. **Privilege split — EspoCRM makes User creation admin-only; API keys
    and `api`-type users cannot do it and a *regular* user with roles 403s.** So
    this runs as a **dedicated admin service account** (`ESPO_PROVISION_*`,
    Type=Admin) via `core/admin_client.py` — Mentor Admin staff stay non-admin.
  - Best-effort: a failure returns `provision:{ok:false,error}` and never rolls
    back the saved status. Every run is action-logged (it changes a status on the
    app's own initiative), with the temp password stripped.
- **Permission teams** on the Status tab write the linked **User's** `teamsIds`
  (teams live on the User, not the profile), also under the admin account.
  Always clickable; a login-less mentor gets an explanatory message.
- **"Update Mentor Status"** sweeps the roster: verifies each login User, checks
  the mailbox and its members-group membership, flags anyone stranded at
  `Accepted-Provisional`, runs `reconcile_user_links`, and bulk re-syncs
  `recordStatus`. This is the staff-facing repair button for stamp drift. It
  **reports, never creates** — see the temp-password reason above.
- **The three grids use the shared grid** (v0.297.0,
  `prds/shared-grid-plan.md` § 9): the roster's rows are drawn by
  `renderTable` after the search and filters and ordered by
  `CBMGrid.sortBy` with `sortVal` (the grid only holds the keys,
  `mentoradmin.roster`); the sweep's results and Documents sort in the
  browser.
- **Every change is in the action history** (v0.304.0, mentor login
  integrity step 1): the save, teams, documents and each mentor the status
  sweep changed. The stream note on the profile names what changed, never
  the values or a file name — a mentor reads their own profile's stream;
  before and after go only to `CActionLog`. `reconcile_user_links` returns
  what it wrote so the login links it changes are visible.
- **`LOGIN_REPAIR_GUARDS`** (v0.305.0, step 2, off by default): every path
  that copies a login between a mentor profile and its Contact goes
  through `core/login_guard.py` — `reconcile_user_links`, provisioning's
  login reuse, the nightly clean-up's Phase A and My Mentor Profile's
  heal-on-access. A new path that copies a login must use it too.
- **`CBM_EMAIL_LOCK`** (v0.306.0, step 3, off by default): with a login the
  CBM email field shows the login's user name, read-only; the server refuses
  a change before any write. Before a login, `_check_cbm_email_change`
  accepts only a free address on the chapter's domain, in lower case.
- **Login faults** (v0.307.0–v0.309.0, step 4): the daily check lives in
  `integrity/` (the worker runs it; `scripts/integrity_report.py` reads
  it). With `INTEGRITY_DIGEST` on, this app shows the **Login faults**
  list (`/integrity/faults`, Acknowledge with a required note, recorded
  in `CActionLog` only — never a stream note) and answers the digest's
  deep links `?mentor=<id>` and `?faults=1`. Do not repair a fault here
  that the plan's § 6 says to repair in the CRM.
- **The History tab** (v0.311.0, step 5a, `RECORD_HISTORY_TAB`): the
  engine is `core/history.py`, the panel `frontend/shared/history.js`,
  shared by every History-tab application and the activity page. It merges
  `CActionLog` (read under the key) with the CRM's Create, Update and
  Assign notes (as the user, never Post), folding a note into the action
  row with the same person (by name — `CActionLog` keeps no actor id), the
  same minute and only fields that row moved. **For a note to fold, record
  the fields an action moves in `details["fields"]`** — a new action that
  writes tracked fields without them shows its CRM note as "In the CRM
  directly". `_same_value` is `history.same_value`.
- Functional reference for staff: `mentor-administration.md`.

## Change log

| Rev | Date (MM-DD-YY HH:MM) | Author | Change |
|---|---|---|---|
| 1.6 | 11-06-26 02:16 | Claude (Claude Code) | The History tab (v0.311.0). |
| 1.5 | 11-05-26 22:49 | Claude (Claude Code) | The login fault list (v0.308.0). |
| 1.4 | 11-05-26 18:05 | Claude (Claude Code) | The CBM email lock (v0.306.0). |
| 1.3 | 11-05-26 17:41 | Claude (Claude Code) | The login repair guards (v0.305.0). |
| 1.2 | 11-05-26 17:24 | Claude (Claude Code) | Every change in the action history (v0.304.0). |
| 1.1 | 10-28-26 20:45 | Claude (Claude Code) | The three grids on the shared grid (v0.297.0). |
| 1.0 | 10-20-26 17:30 | Claude (Claude Code) | Created from the root `CLAUDE.md` section, word for word (Doug's approval 10-20-26). |
