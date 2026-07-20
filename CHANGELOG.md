# Changelog

All notable changes to **cbm-client-intake**. Versions are the value reported by
`/healthz` and the page footer (sourced from `pyproject.toml`), and double as the
deploy marker on App Platform.

## [0.111.0] — 2026-07-20

**feat(portal): Documentation link on the home page.** The portal home page
(the signed-in view) gains a **Documentation** section linking to the CBM
documentation site — `https://docs.clevelandbusinessmentors.org` — so users
can open the user guides for any of the apps. Shown to every signed-in user
(the guides span all the apps; no team gate), opens in a new tab. The URL is
the new `DOCS_SITE_URL` setting (defaults to the live site; empty hides the
section), surfaced on the portal payload as `docsUrl`.

## [0.110.0] — 2026-07-19

**feat(ops): the shared info@ mailbox model — thread-anchored conversations,
send as CBM Info, and inbound info@ email captured into the /ops queue**
(Doug's rulings this session: info@cbmentors.org becomes a real mailbox and
the single identity for the information-request process; the inbound-requests
table + Information Requests are the single source of truth; triage-first —
no CRM records until staff approve; replies use the generic "CBM Info" alias,
never a staffer's name). Fixes his report that submissions — volunteer ones
especially — were "picking up numerous unrelated emails": the conversation
was a `from:X OR to:X` search over the whole mailbox.

- **Thread anchoring** (migration **0013**, `submission.thread_ids` +
  store `add_thread_id`/`existing_tokens`/`known_gmail_threads`): every /ops
  send records the resulting Gmail thread on its submission (the compose
  passes `submissionId`; `register_quicksend` gained an `after_send` hook and
  `send_quick_message` now returns `gmailThreadId`). The conversation view
  and the Reply column read EXACTLY the anchored threads — never an address
  search — so unrelated mail cannot appear.
- **Shared mailbox** (`OPS_MAILBOX`, default empty = old behavior;
  `OPS_MAILBOX_NAME`, default "CBM Info"): /ops sends as info@ under the
  generic name with NO personal signature (`register_quicksend` gained
  `shared_mailbox`; GET /mailbox reports the shared identity; the CRM Email
  write-back stamps info@ as sender), and reads conversations from that one
  mailbox — every admin sees the same conversation (the v0.106.0 per-admin
  caveat is gone in shared mode). Acting user still logged on every send.
- **Inbound capture** (`ops/inbound.py`, worker timer `OPS_INBOUND_SECONDS`,
  default 300): the worker lists the info@ inbox and captures each NEW
  inbound thread as a **held** (`held_review`) **info-email** submission —
  sender name/address, subject, cleaned message text, origin thread id.
  Dedup is stateless and layered: the submission token IS the thread id
  (unique key), and threads anchored to ANY submission are skipped — a
  submitter's reply to a form-submission conversation joins that
  conversation instead of becoming a new item. Outbound-initiated threads
  and mailer-daemon bounces are ignored. Never validated at capture (spam
  must be capturable); per-thread best-effort.
- **Triage-first delivery**: new form kind **info-email**
  (`forms/info_email`, registered for worker delivery only — deliberately NO
  public endpoint), whose orchestrator reuses the info-request mapping with
  email wording: Contact description stamped "[Information request via
  email…]", `CInformationRequest.form="info-email"`, `source="Email"`,
  subject folded into the message. In /ops the row's action reads
  **Approve** ("Create CRM records?") — redrive under the hood — and
  **Discard** removes it with zero CRM residue. `held_review` added to the
  redrive guard; the guard also now allows `discarded` (the UI has offered
  undo-discard since v0.106.0 but the store refused it — latent bug fixed).
- Legacy mode hardening: without OPS_MAILBOX the per-admin search is now
  **time-boxed to the submission's lifetime** (`after:` received, `before:`
  resolved + 2 days).
- Verified: 829 tests green (31 new across test_ops/test_ops_inbound);
  migration 0013 + anchoring/token/thread lookups + held_review/discarded
  redrive round-tripped on live local Postgres.
- **Activation (Doug-side, in order):** (1) make info@cbmentors.org a REAL
  licensed Workspace mailbox (delegation can't impersonate groups/aliases —
  the existing DWD grant then covers it automatically); (2) set
  `OPS_MAILBOX=info@cbmentors.org` on **web AND worker** (+ optionally
  `OPS_MAILBOX_NAME`/`OPS_INBOUND_SECONDS`) in the overlays; the pre-deploy
  migrate runs 0013; (3) CRM build: add an **"Email"** option to
  `CIntakeSubmission.form` (the audit log for approved email submissions
  writes `form="Email"`; until built that best-effort write logs a WARNING);
  (4) separately, stop CRM-direct mail going out with the
  espo@cbmentors.org return address — that is EspoCRM's own outbound SMTP /
  group email account configuration (CRM Admin), not this app.

## [0.109.0] — 2026-07-19

**feat(sessions): one record, one tab** (Doug's request — the same engagement
open in two browser tabs invites dirty-data edits, each tab saving values stale
relative to the other). Client Management / the session tools now guard against
it two ways (frontend-only, all three domains):

- **Reuse the tab**: the grid opens each record in a STABLE per-record window
  (`window.open(url, "cbm-rec-<slug>-<id>")`), so re-clicking the same
  engagement focuses its existing tab instead of spawning a duplicate; different
  records still open side by side. Modifier/middle clicks fall through to the
  browser and are caught by the block below.
- **Block a duplicate**: the dedicated record page (`/{slug}/record/{id}`)
  elects ONE owner tab per record via a `BroadcastChannel` (deterministic
  `(openedAt, tabId)` tiebreak so simultaneous opens still pick one owner). A
  second tab on the same record shows a "This record is already open in another
  browser tab" block INSTEAD of the editor — so no stale save is possible. When
  the owner tab closes, a blocked tab reloads and takes over. Degrades to
  allow-with-named-tab-reuse where `BroadcastChannel` is unavailable.

Verified in a two-tab stub harness: owner renders the record, the second tab is
blocked, the owner leaving hands off to the blocked tab, the grid link opens a
named (not `_blank`) tab; no console errors.

## [0.108.0] — 2026-07-19

**Submission Admin: resolution workflow, awaiting-reply queue, reply
threading, canned-reply template** (the four 0.106.0 follow-ups, Doug's
approval).

### Added
- **Resolved / Open workflow** (migration **0012**: `resolved_at` +
  `resolved_by`): a one-click **Mark resolved / Reopen** button on the
  detail (independent of the delivery status), a Resolved ✓ chip + fact,
  an **Open / Resolved / All** filter defaulting to **Open** (the grid is a
  work queue), and open/resolved count chips.
- **Awaiting-reply column** ("Reply"): who spoke last with each OPEN
  submitter — "↳ reply owed" (their message is newest), "waiting on them"
  (ours is), "—" (no conversation). Loaded asynchronously after the grid
  renders (`POST /ops/api/replystates`, capped at 30 open rows; 1 Gmail
  search + 1 headers-only fetch per row — new
  `GmailClient.get_message_headers`); sortable; empty when email is off.
- **Reply threading**: with an existing conversation, "Email the submitter"
  becomes **"↩ Reply to the submitter"** — the compose opens with the
  "Re:" subject and the send stays on the original Gmail thread
  (`threadId` + In-Reply-To/References through the whole quick-send path:
  quickmail widget → `POST /sendmail` → `send_quick_message` →
  `build_mime`/`gmail.send`). Fresh sends are unchanged.
- **Canned reply pre-applied**: starting a NEW conversation on an
  info-request opens the compose with the **`InfoRequestReply`** EspoCRM
  template already applied (subject + body; `OPS_REPLY_TEMPLATE` overrides
  the name; a missing template silently falls back to a blank compose).
- Boot null-guard so a stale cached index.html can't crash the new app.js.

## [0.107.0] — 2026-07-19

**feat(directory): Company pop-up enhancements** (Doug's requests, all
Account-specific — the engine is unchanged). Records the work from ffbaf90
(which shipped unversioned during a parallel-session version race) plus the
address/email fix:

- **Type-matched profile panel**: the detail pop-up shows only the profile
  panel matching the company's `cCompanyType` — a Client shows *Client
  Profile* and hides *Partner Profile* (and vice versa; Sponsor/Other shows
  neither). Generic: a panel titled "<Type> Profile" appears only when the
  record's type includes that type; ordinary panels are never filtered.
- **Company contacts list** at the bottom of the pop-up (name / phone /
  email), each name a link opening a nested read-only contact-detail modal;
  phone/email are tel/compose links. New `DirectoryConfig.contacts_link` +
  `GET /api/contactdetail/{id}`.
- **Composite address fields now render** (`shippingAddress` / `billingAddress`
  are EspoCRM `address` fields, so reading them as one attribute returned
  empty). They're composed from the sub-fields for display (multi-line) and
  expanded into editable Street/City/State/ZIP/Country inputs in edit mode
  (`DirectoryConfig.type_field` unrelated; see `_address_field`). The company
  **email** already rendered when present — confirmed live.

Verified live against crm-test (Client → Client Profile only + its contacts;
Partner → Partner Profile only; Agape's shipping address now composes) and the
full UI loop in the stub harness (contacts table + nested modal; address
multi-line view + 5 sub-field edit inputs with change-detection). 19
directory tests (7 new); 809 total green.

## [0.106.0] — 2026-07-19

**Submission Admin rebuilt** (Doug's spec: bring /ops up to the other apps'
standard, then make it a place to RESOLVE a request, not just re-drive it).

### Changed — list page
- Full-height grid that fills the window and scrolls internally with a
  sticky header; **sortable columns** (click; Received/Attempts default
  newest/most first), **drag-resizable columns** (grip on each header),
  **alternating row colours**, and whole-row click-through to the detail.
- **Live search box centered in the top bar** (reference/form/status/
  submitter/error/notes/date); "Signed in as … / Sign out" in the top-right
  corner; one control line (status + form filters, counts chips, worker
  metrics, Refresh).
- Re-drive/Discard now use the product's **two-step confirm** (no more
  browser confirm dialogs).

### Added — detail view (replaces the modal; sessions-style tabs)
- **Overview**: submitter + delivery facts on the LEFT (name, email as a
  compose link, phone, company, message, status, received, attempts);
  an editable **Submission notes** card top-center (new `notes` column,
  migration **0011** — staff-only triage notes, saved with `acted_by`);
  the **email conversation with the submitter** listed below the notes
  (latest 5, newest first) so the history is visible at a glance.
- **Details** tab: the payload / progress / result / error view that
  clicking the id used to show — plus **deep links into EspoCRM** for each
  record the delivery created (Contact/Account/CInformationRequest/…).
- **Communications** tab: the full email history with expandable, cleaned
  bodies (quoted replies demoted), Refresh, and **“Email the submitter”**
  opening the shared quick-compose (admin's own @cbmentors.org mailbox,
  templates + signature; `register_quicksend` on the ops router).
- `GET /ops/api/submissions/{id}/messages`: a live Gmail search of the
  signed-in admin's OWN mailbox (`from:X OR to:X`, capped at 25) — nothing
  stored; degrades to a readable reason (Gmail off / no linked CBM mailbox /
  no submitter email). NOTE: each admin sees the thread from their own
  mailbox — a conversation another admin ran lives in THEIR mailbox.

### Activation
- Pre-deploy migrate runs 0011 automatically. Email features light up where
  `GMAIL_SYNC=true` AND the admin's login is linked to a profile with a
  `cbmEmail` (same requirement as every compose surface).

## [0.105.0] — 2026-07-19

**Email, round two** (Doug picked items 1–4 of the functionality review):
the unified **My Email** inbox, unread + awaiting-reply tracking, **Forward**,
and **attach-from-Documents**. Pre-deploy migrate required (Alembic **0010**,
`conversation_seen`).

### Added
- **My Email (`/myemail/`, portal tile, aliases `/myemail` + `/email`)** — one
  inbox across every record the signed-in manager handles (all three domains:
  owned + co-mentored, the same reverse-link scope as the grids — NOT
  "everything the ACL can read"). Filters (All / Unread / Awaiting your
  reply, with counts), live search, thread view with per-message cards, and
  **"Open in record — reply there"** deep links into the session tools'
  record pages. "Mark all as read" clears the backlog. Gated to members of
  any management-tool team; shown on the portal only when the Gmail
  integration is on. New package `myemail/` (router + service + frontend).
- **Unread + "Awaiting reply" flags** on My Email AND every record
  Communications tab: unread = the last message is newer than when this user
  last opened the thread (per-user `conversation_seen` table, Alembic 0010;
  a never-opened conversation counts as unread only within the last 30 days,
  so day one doesn't bold a year of history); awaiting = the conversation's
  last message is inbound — the ball is in your court (derived, one batched
  CCommunication query per page). Unread rows read bold with the inbox dot;
  the record's Communications tab button carries its unread count; opening a
  thread clears both immediately.
- **Forward** (record compose): the thread view gains ↪ Forward — a
  Gmail-style forwarded block (From/Date/Subject/To + the message), nobody
  pre-selected, "Fwd:" subject, and a forward with no added comment sends
  (the forwarded block IS the message — the empty-body guard now knows).
- **Attach from documents** (record compose, when the document integration is
  on): a picker over the record's Documents tab — no download/re-upload
  round-trip. Chips carry ``{documentId}``; the SERVER fetches the original
  bytes at send time through the same record-scoped path as the Download
  action (Google-native files go as their Office equivalent), and a fetch
  failure BLOCKS the send (the ET-131 contract). Archived documents and
  already-attached ones stay out of the picker; document chips persist in
  the compose draft.

## [0.104.0] — 2026-07-19

**Session-tool display names** (Doug's ruling): **Mentor Sessions →
"Client Management"**, **Partner Sessions → "Partner Management"**,
**Sponsor Sessions → "Funder Management"** — on the portal home page, each
app's page heading, and the browser-tab titles (all read from
`DomainConfig.title` / the portal app list). Routes, packages, slugs, and
team gates are unchanged (`/mentorsessions` etc.). Subtitles touched
minimally ("client engagements", "funders you manage"); the CRM entities
keep their sponsor naming, and deeper sponsor→funder copy (grid columns,
Sponsor Notes) was deliberately not swept.

## [0.103.0] — 2026-07-19

**feat(directory): add a Partners directory** (`CPartnerProfile`) as a fourth
Workspace directory — `/directory/partners/`, inline-editable for owned records
(no handoff), filters `partnershipStatus` + `partnershipType`. The engine is
unchanged (columns/detail read live from the CRM layout); routes + the static
mount + the portal launcher tile all derive from the `DIRECTORIES` registry, so
adding the config is all it took. The portal's directory list is now built from
the registry (a new kind appears automatically). Verified live against crm-test
(14 partners; columns Name/CBM Partner Manager/Primary Partner Contact/Last
Contacted; detail panels Overview + Partner Profile). 791 tests green (2 new).

## [0.102.0] — 2026-07-19

**fix(directory): the detail pop-up's overlay covered the whole page on load,
blocking access to every directory grid.** `.dir__modal` (and
`.dir__filterpanel`) set `display: flex` in CSS, which overrides the `hidden`
attribute's UA `display: none` — so the full-screen modal backdrop rendered
immediately and intercepted all clicks. Fixed with `[hidden] { display: none
!important; }` so the attribute is authoritative. Verified with a REAL mouse
click (the prior stub-harness pass used JS `.click()`, which bypasses an
overlay — an attribute check `el.hidden === true` is NOT the same as visually
hidden when CSS sets `display`).

## [0.101.0] — 2026-07-19

**Edit-loss protection extended to the session editor** (Doug's follow-up
to 0.99.0 — the most-typed surface in the app). Frontend-only.

### Added
- **Draft autosave**: as the user works in the session editor, changed
  fields AND a changed attendee selection stash to localStorage — an
  existing session under its id (`cbmEditDraft:…:CSession:<id>`), a new
  session per record (`…:CSession:<recordId>:new`). Reopening offers a
  "You have unsaved changes to this session from earlier" banner
  (Restore them / Discard); restored fields count as changes (sentinel
  snapshot) so an update-save sends exactly what was restored, and
  restored attendees re-check the boxes without touching the diff
  baseline. A successful save — or choosing Discard in the existing
  leave-editor confirm — clears the draft; a hidden editor never stashes
  (no late-debounce resurrection).
- **`beforeunload` coverage**: an open session editor with unsaved changes
  (the existing `editorHasUnsavedChanges` check) now also triggers the
  leave-page warning. (The in-app leave path already had the
  Save / Discard / Keep-editing confirm since v0.31.0 — unchanged.)

## [0.100.0] — 2026-07-19

**Workspace Directories — Phase 1** (the CRM-style workspace Doug asked for:
a central launcher that opens browsable directory grids in de-duplicated
browser tabs). Plan: `prds/workspace-directories-plan.md`.

- **New `directory/` package** (one engine + one router per kind, the
  `sessions/` pattern): three directories — **Companies** (Account),
  **Contacts** (Contact), **Mentors** (CMentorProfile) — at
  `/directory/{kind}`, gated by the new `WORKSPACE_ALLOWED_TEAMS` (default
  `Mentor Team`). Every read/write runs as the signed-in user, so EspoCRM
  ACL is the data scope (the Mentor Role already reads all Contacts/Accounts,
  so those grids are org-wide with no CRM change).
- **Columns + detail arrangement are read LIVE from the CRM's own layouts**
  (`EspoClient.layout` / `.i18n`, both new): the grid columns are exactly the
  CRM list view (`{entity}/layout/list`) and the pop-up shows all data in the
  CRM's own detail arrangement (`{entity}/layout/detail`) — nothing hardcoded,
  auto-syncing when a layout changes. Labels from CRM i18n (humanizer
  fallback); email/phone fields render as compose/tel links even when stored
  as varchar.
- **Grid** (server-side searched / filtered / sorted / paginated) with the
  toolbar Doug specified: **Filter** (top-left, live options from metadata),
  **Search** (top-center), **View / Edit** (top-right, act on the selected
  row; never disabled — they message on empty selection or missing
  permission). Sortable + resizable columns; row-select fills a **preview
  pane** (read-only, CRM-arranged, information-dense).
- **Detail pop-up**: all data in **view mode**, an **Edit** button switches
  to an inline editor for records the user **owns** (reuses the sessions
  Details whitelist/gate — editable scalar fields only, drifted enum values
  dropped, gold changed-dot + "N fields changed"). **Mentors** are inline
  read-only — Edit hands off to **My Mentor Profile** (own row only).
- **Portal → Workspace launcher**: the home page gains a **Directories** tile
  section (above Applications); directory + app tiles open in **stable named
  browser tabs** (`window.open(url, "cbm-…")`) so re-clicking reuses the tab
  instead of opening a duplicate. Payload adds `directories` + a per-app
  `target`.
- Verified: 789 tests green (12 new — live-layout columns, list/search/
  filter/paginate, view+edit payload, owned-record edit gate, save
  whitelist, mentor handoff, router gate); the whole read path exercised
  live against crm-test (68 companies / 128 contacts / 43 mentors); full UI
  loop (grid → preview → view → edit → save, filter, sort, launcher tab
  de-dup) verified in the stubbed-browser harness with no console errors.
  **NOT yet driven live** as a real non-admin mentor (needs a portal login);
  Phase 2 = inline Contact/Company edit is already built here, Phase 3
  (open-tab badges, saved filters) is future.

## [0.99.0] — 2026-07-19

**Edit-loss protection** (Doug approved the two recommendations after the
0.98.0 top/bottom Save bars). Frontend-only, all three session domains.

### Added
- **Discard confirmation**: Cancel on a dirty edit form (Details sections +
  the Overview notes editor) two-steps to "Discard changes?" before
  throwing typed work away; the notes editor computes dirtiness at click
  time (never trusts the debounce). A `beforeunload` guard warns before
  closing/refreshing the page with unsaved edits.
- **Draft autosave**: dirty edit-form fields autosave to localStorage
  (`cbmEditDraft:` keys, 7-day expiry — the v0.88.0 compose pattern).
  Reopening a Details form with a stashed draft shows a banner
  ("You have unsaved changes on this form from earlier" — Restore / Discard);
  restoring merges the values in and counts them as changes, so Save writes
  exactly what was restored. The notes editor reopens straight INTO its
  draft with a "Start fresh" escape. A successful save or confirmed discard
  clears the draft; late debounce ticks can't resurrect it.

### Fixed (during build)
- The new helpers originally collided with the v0.88.0 record-compose
  draft functions (`draftKey`/`clearDraft` — in one shared scope the later
  function declaration wins, silently mis-keying edit drafts) — renamed to
  `editDraftKey`/`saveEditDraft`/`readEditDraft`/`clearEditDraft`.

## [0.98.0] — 2026-07-19

**Save/Cancel at the top AND bottom of every edit form** (Doug's ruling:
saving must never require scrolling). Frontend-only.

### Changed
- The Details-tab section edit forms (strip, org cards, contact rows,
  create-contact) render a second Save/Cancel bar at the TOP of the form,
  paired with the existing sticky bottom bar; both share one state (the
  "N fields changed" narration, the dirty-gated enable, and the in-flight
  disable update together). A save error scrolls into view so it's seen
  from either bar.
- The Overview notes inline editor gets the same treatment: Save/Cancel in
  the panel header (always in reach on a tall editor) plus the bottom pair.

## [0.97.1] — 2026-07-19

### Added
- **Double-click the Overview notes panel to open the full-page View**
  (Doug's follow-up to 0.97.0: the fastest route wins). A double-click on
  a button or the drag bar keeps doing its own job.

## [0.97.0] — 2026-07-19

**Overview notes panel: height cap, drag-resize, and a full-page View**
(Doug's request for long engagement/partner/sponsor notes). Frontend-only.

### Added
- The record-notes panel body caps at **50% of the page height** by default
  and scrolls inside; a **drag bar** under it resizes the cap (min 6rem,
  max 90% of the viewport; the chosen height sticks across re-renders on
  the page).
- A **View** button next to Edit opens the complete notes in a full-page
  pop-up (92vw × 86vh — no width cap, per the ruling) that is **freely
  resizable** (drag the corner) with its own scroll; Close / Escape /
  backdrop-click dismiss it.
- **Right-click** anywhere on the notes panel opens a context menu with
  View / Edit (the assignments every-function-right-clickable convention);
  click-away / Escape closes it.

## [0.96.0] — 2026-07-19

**Edit buttons are never hidden** (Doug's ruling, extending the
never-disabled convention: a hidden button reads as a bug and generates
"the button is missing" support calls).

### Changed
- Every ACL-gated action on the Details tab now always renders and explains
  itself on click when the user lacks the CRM grant, instead of being
  omitted: the parent strip's Edit ("You don't have permission to edit the
  Partnership — ask CBM staff if you need it."), the org-card Edit
  (Company / profile cards), each contact row's Edit (names the contact),
  and each row's Remove ("…to change this record's contacts…" — the
  unrelate is a parent write; the two-step arm never starts without the
  grant). Design exclusions are unchanged (the assigned-Mentor row still
  has no Remove — that link belongs to Client Administration).
- Frontend-only; the server-side ACL verdicts and readable save-time 403s
  are unchanged. Memory updated:
  buttons-never-disabled-validate-on-click now covers hiding.

## [0.95.0] — 2026-07-18

**Record notes edit in place on the Overview** (Doug's ruling: notes are the
most important item on partners/sponsors — no trip to the Details tab).

### Added
- The Overview's record-notes panel (Partner Notes / Sponsor Notes /
  Engagement Notes — all three domains) gains an **Edit** button: the panel
  swaps to an inline editor (CBMRichText for wysiwyg notes, a textarea for
  the sponsor's plain-text notes), Save PUTs through the same whitelisted
  `/details/{entity}/{id}` path the Details tab uses, and the panel
  re-renders with the saved value — no reload, no tab switch. Cancel
  restores the read view untouched. The Details tab's cached copy is
  invalidated so it re-reads on next activation. The Edit button is always
  active — a user without the CRM edit grant gets the readable
  permission message on Save (buttons-never-disabled convention).
- `GET /records/{id}` `overallNotes` now carries `entity` + `attr` (the
  write target) alongside label/value/type.

## [0.94.0] — 2026-07-18

Reliability hardening **Phase 6 — infra/ops** — the FINAL phase of the
2026-07-17 reliability review (`reliability-review-2026-07-17.md`); the
whole P0/P1/P2 plan in `prompts/reliability-hardening-prompt-v0.1.md` is now
implemented. Doug's decisions this session: **D3 = 2 MB body cap + 30
submissions/IP/10 min**, **D4 = production-tier upgrade for both managed
DBs** (runbook written; console action is Doug's). 11 new tests (777 green);
SIGTERM drill run live (clean stop, exit 0); the pinned Docker tags verified
against both registries.

### Added
- **Web-tier startup banner + fail-fast config.** `create_app` logs the
  effective mode (environment, dryRun, store, async, staff stack, feature
  flags — the worker has had one since V2) and now REFUSES to boot two
  contradictory configs that used to fail silently at runtime:
  `ESPO_DRY_RUN=false` without `ESPO_API_KEY` (every CRM call 401'd) and
  `ASYNC_DELIVERY=true` without `DATABASE_URL` (silently fell back to sync).
- **Public intake limits (D3).** `/api/*/intake` rejects bodies over 2 MB
  early (Content-Length, before buffering; the volunteer form keeps an 8 MB
  cap for its in-JSON base64 resume) and rate-limits each IP to 30
  submissions per 10 minutes (in-memory sliding window; readable 413/429
  responses; `INTAKE_MAX_BODY_MB` / `INTAKE_RATE_LIMIT` /
  `INTAKE_RATE_WINDOW_SECONDS`, 0 disables). Previously the edge passed
  ≥60 MB bodies into `request.json()` and a token-varying bot could write
  unbounded rows.
- **Worker graceful shutdown.** SIGTERM/SIGINT finish the current item,
  stop claiming (mid-batch items return via lease expiry), and exit
  cleanly — every deploy used to kill the worker mid-delivery and roll the
  duplicate-create dice.
- **`metrics()` windowed latency**: `recentAvgLatencySeconds` over the last
  50 completions, so a fresh regression is visible next to the lifetime
  average.
- **DEPLOYMENT.md "Reliability operations"**: the D4 backup decision +
  restore runbook (both DBs are dev-tier = NO backups today — the console
  upgrade is the open action); DO uptime/alert guidance for the new
  `/healthz` worker fields (alert when `worker.lastHeartbeatAgeSeconds`
  exceeds ~120s); the worker `instance_count: 1` invariant; the
  overlay-recovery paragraph naming which secret VALUES are unrecoverable
  (ESPO_API_KEY, SESSION_SECRET, SA JSON, APP_ENCRYPTION_KEY,
  ESPO_PROVISION_PASSWORD).

### Changed
- **Schema comes from Alembic only.** The web app and worker no longer run
  `create_all()` at boot — a fresh environment booted before its migrate
  job used to build current tables with no `alembic_version` stamp,
  wedging every later `upgrade head`. Missing tables now surface as
  visible capture 503s / worker cycle errors until the migration runs.
- **Docker base images pinned**: `python:3.12.8-slim` +
  `ghcr.io/astral-sh/uv:0.10.6` (the uv that generated `uv.lock`) — a
  rebuild months later gets the same toolchain; bump the pins deliberately.
- **`GDRIVE_IDENTITY` is a `Literal["user","service"]`** — a typo now fails
  the boot loudly instead of silently meaning "user".

## [0.93.0] — 2026-07-18

**Sponsor editing parity with the 0.91.0 partner fixes** (Doug's follow-up
ruling). Frontend-only.

### Changed
- **Curated Sponsorship edit form** (`DETAILS_LAYOUTS.CSponsorProfile`,
  `noExtras`): Sponsorship (last contribution / last contacted) + a
  full-width **Sponsor notes** editor — `CSponsorProfile.description` IS the
  sponsor-notes field (it feeds the Overview's Sponsor Notes panel), so it
  stays editable under that label instead of being excluded like the
  partner's. The record name and the computed total-contribution's currency
  companion are excluded (the figure itself stays on the strip).
- **Sponsor-domain Company form/view hides `description`, `cClientNotes`,
  and the Account-level `cSponsorNotes` twin** — client-specific notes have
  no place on a sponsor's company, and notes typed into the Account twin
  could never reach the Overview. One notes field, and saves reflect on the
  Overview immediately (the 0.91.0 `refreshRecordViews` covers all domains).

## [0.91.0] — 2026-07-18

**Partner editing fixes** (Doug's report: partner notes typed in the edit
screen never showed on the Overview; the edit screen exposed client
notes/description fields that don't belong on a partner).

### Fixed
- **A Details-tab save now refreshes the Overview** (`refreshRecordViews`
  after every section/contact save): the record payload is re-fetched and
  the Overview + Sessions tabs re-render, so Partner Notes (and any other
  edit) appears immediately instead of only after a full page reload.
- **One Partner Notes field.** The partner domain's Company form carried the
  Account-level `cPartnerNotes` twin — notes typed there could never reach
  the Overview (which reads `CPartnerProfile.partnerNotes`). The twin is
  retired from the partner Company form/view; the Partnership form's Partner
  Notes is the one notes field and feeds the Overview panel.

### Changed
- **Curated Partnership edit form** (`DETAILS_LAYOUTS.CPartnerProfile`,
  `noExtras`): Partnership (status/type/cadence + dates) · Value & goals ·
  a full-width Partner notes editor — replaces the generic "Additional
  details" dump. The record name is excluded (mirrors the company; the
  header shows it).
- **`CPartnerProfile.description` is server-excluded** from the Details view
  (`_ENTITY_EXCLUDED`) — it holds the intake form's enum-drift triage note
  (the CEngagement.description precedent); a smuggled write is dropped.
- **Partner-domain Company form/view hides `description` and `cClientNotes`**
  ("Client notes") — client-specific fields have no place on a partner's
  company. The Account layout's empty "Notes" group collapses. (Sponsor
  domain untouched — its Company form still shows them; flag if unwanted.)

## [0.92.0] — 2026-07-18

Reliability hardening **Phase 5 — Drive + intake-pipeline residuals**
(P1-13 + the P2 Drive/intake items, per
`prompts/reliability-hardening-prompt-v0.1.md`). 16 new tests (766 green,
incl. the "lying Drive" simulations); no new migration; the docs store's new
surface round-tripped on live local Postgres.

### Fixed
- **Drive uploads are create-safe (P1-13; strategy: pre-generated ids,
  documented in `docs/service.py`).** Every upload pre-assigns a
  server-generated id (`files.generateIds`): a retried create can't
  duplicate (a 409 on the duplicate id resolves to the already-committed
  file), and when the upload RESPONSE is lost after Drive committed — the
  orphan-then-user-retry-duplicates window — the rollback target is still
  known and the file is deleted before the error surfaces. Non-idempotent
  creates WITHOUT a pre-set id are never blind-retried; a failed folder
  create re-runs find-or-create instead (a committed-then-5xx'd folder is
  found, not duplicated).
- **A stale cached record folder self-heals.** A folder deleted in the
  Drive console used to 404 every subsequent upload for that record
  forever; the upload now clears the folder cache
  (`DocumentStore.clear_folder_cache`), rebuilds the path, and retries
  once.
- **The grants engine enforces the access model against org-wide shares
  (docs-F9).** Non-inherited `group`/`domain`/`anyone` permissions — never
  justified by the CRM, which entitles individual people only — are revoked
  like any stray grant (previously a console-added domain share survived
  every reconciliation). The nightly reconciliation also alerts when the
  SAME folder keeps erroring on consecutive passes (silent grant drift),
  not just on removals.
- **The document content proxy streams original downloads.** `?original=true`
  now streams the stored bytes in chunks (both the session tools and
  `/mentoradmin`) instead of buffering whole files — a few concurrent large
  downloads could OOM a small instance. Google-native files (no native
  bytes) keep the buffered export path, which Drive itself caps.
- **The docs LIST endpoint gained the per-record ACL read (docs-D6).**
  Upload/content/refresh already read the parent as the user; the list
  didn't — document metadata (filenames, uploaders, Drive links) was
  enumerable across ACL boundaries by anyone past the team gate.
- **Intake residuals:** a DB outage at accept now logs the payload at ERROR
  (its only copy at that moment) and answers a controlled 503 "please
  retry" instead of a raw 500; malformed JSON answers 422; the
  sync-with-store path delivers through `ResumableClient` (P1-8 — a partial
  failure carries progress, so an /ops redrive RESUMES instead of
  duplicating the plain creates); `Sponsor` joined the
  `Contact.cContactType` schema-drift contract (the sponsor orchestrator
  has written it since 2026-06-22); and the info-request description APPEND
  is guarded by a named progress step (`ResumableClient.mark_step` /
  `run_step_once`) so a re-delivery can't double-append staff-visible text
  (pipeline-M1).

## [0.90.0] — 2026-07-18

### Fixed
- **Applied email templates no longer betray themselves through mismatched
  fonts** (Doug's report: EspoCRM fills the placeholder fields in a
  different font color/style than the authored template text — the
  recipient could tell it was a template). Root cause: EspoCRM's template
  editor wraps hand-typed runs in styled spans (font-family/size/color)
  while substituted placeholder values land outside them, and the app kept
  those inline styles verbatim. The template parse
  (`comms/templates.parse_template`, both compose surfaces) now
  **neutralizes all font-identity styling** in the rendered body —
  font-family, font-size, color, background, and legacy `<font>` tags —
  so the authored text, the filled-in values, and whatever the user types
  next all render in the compose's one default font, like a personally
  written email. Structure survives (bold/italic via font-weight/style,
  links, lists, headings, non-font inline styles such as margins).
  The user's own SIGNATURE deliberately keeps its authored styling
  (`sanitize_template_html` is unchanged for that path — a signature's
  look is the sender's own design, not a template tell).

## [0.89.0] — 2026-07-18

**Partner Sessions: all partners, Partner Notes on top, Partner Manager
quick-email** (Doug's three requests).

### Changed
- **The partner grid lists ALL partners** the signed-in user's CRM ACL can
  read (`DomainConfig.list_all` — a plain paginated `CPartnerProfile` list
  replaces the managed-partners reverse-link read; `profileFound` is always
  true, so a team member without a linked CMentorProfile still sees the
  shared list). Visibility is governed CRM-side by team permissions — see
  the CRM prerequisites below.
- **The Overview's record-level notes panel always renders** (all three
  domains): an empty Partner Notes / Engagement Notes / Sponsor Notes field
  now shows the panel with a muted "No … recorded yet." placeholder at the
  top of the notes pane, above the session summaries, instead of omitting
  it (blank wysiwyg markup like `<p><br></p>` counts as empty).

### Added
- **Partner Manager grid column** (partner domain): links to the manager's
  standard CMentorProfile pop-up, whose CBM/personal email rows open the
  quick-compose — a partner manager is two clicks from an email. The
  mentor-domain Assigned Mentor link now shares the same config-driven
  mechanics (`DomainConfig.list_manager_id_attr`).
- **New partner intake submissions stamp the Partner Management Team** onto
  the created CPartnerProfile (`PARTNER_TEAM_NAME`, default
  `Partner Management Team`) so team-scoped roles see new partners.
  Best-effort: an unresolvable team (the intake API role has no Team read
  grant yet) logs a WARNING and never blocks the application.

### CRM prerequisites (to activate the all-partners visibility)
1. Partner Management Team role: `CPartnerProfile` read scope → **team**
   (or all).
2. Backfill existing CPartnerProfile records' Teams field with
   `Partner Management Team` (the app only stamps NEW intake-created ones).
3. Grant the intake API role (`CustomAppAPIRole`) **Team read** so the
   intake form can resolve the team id (until then partners are created
   without the stamp, logged as a WARNING).

Version-race note: this feature's `core/config.py` (`partner_team_name`) and
`sessions/frontend/app.js` (overall-notes placeholder + manager-link comment)
halves were swept into the parallel session's 743a3db (v0.87.0) release
commit — HEAD is coherent at/after this release's commit.

## [0.88.0] — 2026-07-18

**Compose email overhaul** — every finding from the compose-UX review, both
surfaces (the session tools' record compose + the shared quick-compose
widget), per Doug's "do them all" + resizable-at-90% ruling.

### Added
- **Cc/Bcc** end-to-end: reveal links on the recipients line (both dialogs);
  server support through `send_message`/`send_quick_message`/`build_mime`
  (Bcc header — Gmail delivers and strips it), the Espo Email write-back
  (`cc`/`bcc` fields), and both request schemas. An address duplicated
  across lists keeps its strongest slot (To > Cc > Bcc); a Cc-only send
  promotes to To.
- **Draft protection**: closing a compose with real content (Escape, ×,
  backdrop, Cancel) asks "Discard this draft?" first; every draft also
  autosaves to localStorage (debounced, 7-day expiry, keyed by record+reply
  or app+recipient) and restores on reopen with a "Start fresh" escape —
  a crash, tab close, or session expiry never loses a typed message.
- **Reply improvements** (record compose): the original message rides into
  the draft as a quoted block ("On <date>, <name> wrote:"), **Reply all**
  appears when the thread has multiple participants (own mailbox excluded),
  and Cancel/close returns to the conversation view instead of dumping out.
- **Recipient hygiene**: `Name <email>` parsing, comma/semicolon splitting,
  address-shape validation with the bad tokens named; a live "Sending to N
  recipients (2 To, 1 Cc)" summary in the pinned footer; All/None toggles
  when a record has >5 contacts.
- **Send-time guards** (validate-on-click, never disabled): empty body
  blocks with "Write a message first."; a missing subject or unresolved
  `{X.y}` template placeholders turn Send into a one-click-armed
  **"Send anyway"** with an amber explanation.
- **Attachments**: per-file sizes on chips + a running "Total X of 20 MB"
  line; over-cap files are refused with the file named. Upload **progress
  percent** on the Send button for big messages (XHR send path).
- **Keyboard**: autofocus lands on the first empty field, Tab is trapped
  inside the dialog, **Ctrl/Cmd+Enter sends**.
- **Template picker** is a single searchable combobox; picking **"No
  template" restores the pre-template draft** (subject/body/attachment
  chips); the placeholder warning is now amber and re-checked at send time.
- The unknown-recipient step is explicit: the button relabels to
  **"Add & Send"** while the add-to-record panel is open, the panel scrolls
  into view, and any recipient edit resets the panel. The create-contact
  row's company picker is a cached type-ahead (one /companies fetch per
  compose) instead of a full select per row.

### Changed
- **Both dialogs open at 90% of the window and are user-resizable**
  (bottom-right grip; header + Send/Cancel footer pinned, only the body
  scrolls) — the record compose had been capped at 46rem by a later CSS
  rule silently overriding the intended workspace width (styles.css:508,
  now removed), with Send/Cancel below the fold. Footer button order is
  Send-rightmost in both dialogs; validation errors show in the pinned
  footer (always visible). The compose header now names the record; the
  message editor sizes to the workspace.
- The editor-leave "Unsaved changes" prompt was generalized into a shared
  `openConfirm` helper (all labels set per call) used by both flows.

## [0.87.0] — 2026-07-18

Reliability hardening **Phase 4 — Gmail sync loss prevention** (P1-5, findings
F1–F6, per `prompts/reliability-hardening-prompt-v0.1.md`; Doug's decision
**D6 = dead-letter after 5 consecutive failing passes**). 25 new tests (740
green); migration **0009** + the new store surface verified against live local
Postgres. NOT driven against live Gmail (by design this phase) — live
re-verify items listed in CLAUDE.md.

### Fixed
- **The sync cursor can no longer advance past a failed message.** A message
  whose ingest fails (Gmail fetch error, CRM 400 like the robert.cohen
  length rejections) now HOLDS the mailbox cursor: the next pass re-reads it
  (Message-ID dedup makes the replay cheap) instead of silently losing it
  forever. Failures are counted per message (`failed` in the pass totals —
  the incident pass had logged "0 sync errors"); after **5 consecutive
  failing passes (D6)** the id is dead-lettered — skipped, logged at ERROR,
  visible in `/ops/api/metrics` (`gmailSync` block), recoverable via
  `GMAIL_RESYNC` (which also resets the failure tracking). Webhook alerts
  fire when a message keeps failing (2nd pass) and again on dead-letter.
- **`last_synced_at` only advances on a fully-successful pass.** It is the
  expired-cursor backfill window source — the error path used to bump it,
  so a two-week mailbox outage would have re-queried "since yesterday" and
  silently skipped the whole span.
- **History pagination never skips unfetched pages.** When the page cap
  truncates a long history listing, the cursor now saves the last PROCESSED
  entry's id (resuming next pass) instead of the current tip, which
  permanently skipped everything unfetched after a long outage.
- **Gmail transport hardening.** `GmailClient` gets the DriveClient
  treatment: bounded exponential backoff on 429/5xx honoring Retry-After
  (quota bursts during backfills previously surfaced as runs of per-message
  failures); one shared HTTP connection per client lifetime (a sync pass no
  longer re-handshakes TLS per call; the sync closes clients per mailbox);
  and sends get their own 120s timeout sized for ~27 MB bodies with NO
  retries (non-idempotent — a retry could double-send; full send idempotency
  is out of scope, Gmail's API has no dedup token for messages.send).
- **Empty conversation shells are reused, not duplicated.** A conversation
  whose first message create failed was unfindable (CConversation has no
  thread-id field), so the retry minted a duplicate shell — the five
  hand-deleted crm-test shells. A local `(mailbox, thread id) →
  conversation` map (Postgres, migration 0009) now makes shells findable;
  no CRM build needed.
- **A confirmed send to non-contacts can no longer orphan its thread.** The
  include override is persisted BEFORE the best-effort write-through ingest
  (resolving/creating the conversation via the thread map) — previously one
  Espo blip during write-through meant the override was never recorded and
  the sync could never match the thread (unknown recipients match nothing).
  A write-through failure now also surfaces in the compose dialog ("sent,
  but it may not appear here yet") instead of silence.

## [0.86.0] — 2026-07-18

Reliability hardening **Phase 3 — staff-tool write chains** (P1-9/11/12 + six
P2 items, per `prompts/reliability-hardening-prompt-v0.1.md`; Doug's decision
**D5 = the exclude unlink runs as the signed-in user**). 20+ new tests (723
green + PG integration with migration **0008** run live); the assign-repair
flow and the session-create warning verified in the stubbed-browser harness;
the membership TTL verified against real local sessions (TestClient).

### Fixed
- **P1-9 — a half-assigned engagement is repairable in-app.** When Client
  Administration's stale-guard trips but the stored mentor EQUALS the
  requested mentor (a previous assignment died mid re-homing), Assign now
  runs a **repair**: the idempotent re-homing re-executes and a
  repair-labelled stream note posts, instead of the 400 that left the state
  unfixable. The response (and grid notice) say "repair run"; the engagement
  record itself is not rewritten, and a mentor who has since paused new
  clients can still have their own assignment finished.
- **P1-11 — /ops redrive is guarded and audited.** `store.redrive` only
  accepts `needs_attention` / `retry` / `held_honeypot` rows (redriving a
  completed row re-delivered CRM side effects; a processing row raced the
  live worker into duplicate creates); redrive/discard record the acting
  username in the new **`acted_by`** column (Alembic **0008** — pre-deploy
  migrate) so "who discarded this?" is answerable from the row itself.
- **P1-12 — stale cookie entitlements expire.** A new middleware re-reads the
  session's team membership from the CRM (as the user) on staff API requests
  once the stamp is older than **`MEMBERSHIP_REFRESH_SECONDS`** (default
  900); a dead/revoked token clears the session → 401. Closes the hole where
  a staffer removed from a team kept app access by bookmarking an app — /ops
  worst of all, since it makes no CRM calls that would ever catch it.
- **Own-profile resolution tests membership, not the first collaborator.**
  `resolve_manager_profile` (sessions/mentorprofile/comms) matches the user
  against ALL `assignedUsersIds` via the new `is_assigned_to` helper — a
  profile listing someone else first no longer makes the mentor's own profile
  unresolvable on the collaborators shape.
- **Calendar id-before-invite.** The Google Calendar hook now creates the
  event QUIETLY (no attendees, `sendUpdates=none`), persists the event id to
  the CRM, and only then patches the attendees in with `sendUpdates=all`. A
  failed id write-back deletes the never-invited event (no orphan, no
  double-invite on the next save); a failed invite patch reports
  `inviteError` on a successful save (re-save retries). The hook stays
  best-effort throughout.
- **Session-create follow-up failures are warnings, not phantom errors.** A
  failed attendee attach after the CSession exists returns
  success-with-warning ("open the session and re-save its attendees — do not
  create it again") instead of "Could not create session", which invited a
  duplicate. The save notice shows the warning.
- **Provisioning can no longer mint duplicate Users.** `cbmEmail` is written
  onto the profile BEFORE the EspoCRM User is created, so a failed link write
  leaves the reuse guard armed for the next save (previously it minted
  `jane.doe2@…` + a second welcome email). The provisioning admin's auth
  token is now **cached per process** (re-login only on 401) — a rotated
  password no longer turns every sweep into repeated failed password logins
  that could brute-force-lock the service account.
- **The mentor status-check sweep is no longer O(mentors × engagements).**
  `verify_all_mentor_statuses` computes the engagement metrics ONCE for the
  roster and passes them through (`get_mentor(metrics=…)`).
- **Hide-conversation (exclude) is ordered and honest (D5).** The CRM unlink
  runs FIRST, **as the signed-in user** (their ACL, their name in Espo
  history — not the privileged API key), and only a successful unlink records
  the durable exclusion; a failed unlink surfaces a readable 403/502 with
  nothing recorded — the "hidden in the app, still linked in the CRM" split
  state can't happen. A store failure after the unlink reports "hide it again
  to finish".

## [0.85.0] — 2026-07-18

### Changed
- **Client Administration: the engagement grid's "Days Assigned" column is now
  "Days Pending"** — it counts whole calendar days an engagement has been
  waiting in **Pending Acceptance** (from `engagementAssignedDate`, which the
  Assign action stamps at the same moment it sets that status). Rows in any
  other status — and hand-set pending rows with no stamp — show "—"; sorting
  still defaults to longest-waiting-first. Frontend-only.

### Fixed
- The Days Pending value now actually centers under its header: the generic
  `.assign__table td { text-align: left }` rule outranked the cell's
  `text-align: center` (CSS specificity), leaving the value left-aligned.

## [0.84.0] — 2026-07-18

Reliability hardening **Phase 2 — "see the failures"** (worker liveness +
logging/telemetry, per `prompts/reliability-hardening-prompt-v0.1.md`; Doug's
decisions D1 = keep the DB-down 503, D2 = metadata-only PII logging). 54 new
assertions across 8 test files (707 green + PG integration run live); the
end-to-end trace, `/healthz` worker block, and shared log format all verified
in a local two-process run.

### Added
- **Worker liveness is externally visible (P1-6).** The worker upserts a
  one-row `worker_heartbeat` stamp each loop (Alembic **0007**); `/healthz`
  gains a best-effort `worker` block — `lastHeartbeatAgeSeconds`, `backlog`,
  `oldestPendingAgeSeconds`, `stranded` — so an external uptime check can see
  a dead/wedged worker (the in-worker alerter can't alert on its own death).
  Those reads NEVER fail `/healthz`; only the DB ping 503s (decision D1).
  `store.metrics()` counts lease-expired `processing` rows as **stranded**
  (they were invisible to every alert — the P0-1 visibility gap), surfaced in
  `/ops/api/metrics` and a new alert in `run_alert_check`.
- **One shared logging config for both processes** (`core/logging_setup.py`):
  level + logger name + seconds-precision timestamps, level from the new
  **`LOG_LEVEL`** setting (default INFO — DEBUG now reachable without a
  deploy). Kills the divergent `basicConfig`s (worker lines previously had NO
  timestamps at all).
- **Submission correlation by token.** Async accept logs one INFO line
  (slug, token, durable reference); the worker's claim / delivered / retry /
  needs_attention lines carry slug + token alongside the row UUID — one
  submission is now traceable across both processes with a single grep.
- **Actor logging across the staff tools.** Every staff router's
  `_crm_failure` WARNING names the acting user; staff write successes log one
  INFO line (user, entity/id, changed FIELD NAMES — never values): sessions
  details/session saves, assignments notes/assign/reassign, mentoradmin
  mentor saves, mentorprofile own-profile saves. Portal logins log success
  AND failure (username, never the password). `/ops` redrive/discard log the
  actor. The provisioning SSE flow (mailbox + User creation — the
  highest-privilege action in the app) now logs each step server-side at
  INFO (step/status/message only — the temp password never logs).
- **The silent `except: pass` inventory now logs.** One WARNING each at the
  review's eight sites — most critically the assignments co-mentor read
  (P1-10), whose failure means the `assignedUsers` write may silently drop
  co-mentors; plus the same guard on the newer reassign path, mentoradmin's
  `reconcile_user_links` / `recordStatus` persist / status-check admin-login
  downgrade, sessions' linkedCompany fallback, comms' contact-link and
  Uncertain-stamp failures, and the portal membership fallback read.

### Changed
- **PII no longer dumps into the logs when the CRM audit write fails
  (decision D2).** With a durable store active, `log_submission`'s failure
  WARNING is metadata-only (form, token, error) — the payload is already safe
  in Postgres. The full-payload dump remains only in storeless dev mode,
  where the log line is the sole copy.

## [0.83.0] — 2026-07-18

**Meeting Transcript integration — Google Meet (Phases 1+2 of
`prds/meet-transcript-integration.md`), gated OFF by `MEET_TRANSCRIPTS`.**
Every Meet the session tools schedule gets automatic transcription turned on,
and a new worker job retrieves finished transcripts into the CRM — lighting up
the session view's Transcript zone (feature-gated since v0.37.0) and adding a
permanent Google Doc link. Inert until the CRM fields exist
(`csession-transcript-fields.md`) and the flag is set (web + worker).

### Added
- **`core/gmeet.py`** — `MeetClient` (Meet REST v2, the gcalendar
  service-account + DWD pattern, scope `meetings.space.created`): space lookup
  by meeting code, auto-transcription enable (`spaces.patch`), conference
  records filtered by meeting code + start-time window, paged transcript
  entries + participants; pure helpers for meeting-code extraction and
  speaker-attributed, elapsed-timestamped, escaped transcript HTML.
- **Schedule-time auto-enable** (`sessions/gcal.py`): after the calendar hook
  creates an event with a *generated* Meet conference, the Meet space's
  `autoTranscriptionGeneration` is set ON as the organizer (Doug's ruling: no
  per-session opt-in; participants see Google's standard in-meeting notice).
  Best-effort — the result rides the existing `calendar:{...}` save notice as
  `transcription:{ok,...}`; hand-typed links are never configured.
- **Worker retrieval job** (`sessions/transcripts.py`, timer
  `MEET_TRANSCRIPTS_POLL_SECONDS`, default 1800): under the API-key client,
  finds past Meet-linked sessions still missing a transcript (window:
  `TRANSCRIPT_GIVE_UP_DAYS`, default 14 — inside Google's 30-day entries
  retention; status deliberately NOT required to be Completed), resolves the
  organizer (session's assigned users → `CMentorProfile.cbmEmail`, parent
  manager profile fallback), fetches the ended transcript via a provider seam
  (`TranscriptSource` — Meet now, Zoom can slot in later), and writes back
  `sessionTranscription` + `transcriptDocUrl` in one update (oversize
  transcripts clamped at a paragraph boundary with a note pointing to the
  Doc). Best-effort per session; nothing is stored for retries — a session
  simply stays a candidate until it resolves or ages out.
- **Session view**: a copyable "Transcript document" row in the facts grid
  (feature-detected `transcriptDocUrl` selected by `get_session`).
- **CRM handoff**: `csession-transcript-fields.md` — `sessionTranscription`
  (wysiwyg) + `transcriptDocUrl` (url) + the CustomAppAPIRole CSession
  read/edit grant; Google-side prerequisites incl. the **licensing gate**
  (Meet transcripts need Business Standard+ for organizers).
- Settings: `meet_transcripts`, `meet_transcripts_poll_seconds`,
  `transcript_give_up_days`; runbook blocks in `.env.example` +
  `DEPLOYMENT.md`.

## [0.82.0] — 2026-07-17

Fix: **every mentor read "Incomplete — no User assigned to the Contact"** after
the CRM's Contact entity was switched to Multiple Assigned Users (intentional,
2026-07-16, so co-mentors can be assigned to client contacts; Account was
switched too). The switch disables the single `assignedUser` field — reads
return null (hiding every previously-stored assignment) and writes to it are
silently ignored — but the apps still read/wrote only that field on Contact.

### Fixed
- **Mentor Administration completeness** (`check_completeness`): the Contact
  check now accepts either assignment shape — the single `assignedUserId` OR
  membership in the multi-user `assignedUsersIds` — so an assigned Contact no
  longer reads as unassigned (and the "different User" rule is a membership
  test). An unreadable Contact now reports only the read failure, not a bogus
  "no User assigned" on top.
- **Save-time reconciliation** (`reconcile_user_links`): the Contact write
  carries both shapes and MERGES into the contact's existing `assignedUsers`
  (co-mentor stamps survive; the disabled single field is ignored harmlessly).
- **Client Administration re-homing**: `Contact` joined `USES_ASSIGNED_USERS`
  (dual-write everywhere); Assign re-homes contacts via the merge payload and
  Reassign via the swap-merge (old mentor's User out unless a co-mentor shares
  it, co-mentors preserved) — previously the contact write was a silent no-op
  under the new schema, and before that an overwrite.

### Added
- **"Update Mentor Status" heals the roster**: the sweep runs
  `reconcile_user_links` per mentor (best-effort) before recomputing
  completeness, so one click re-stamps every Contact from its member's User
  and flips the drifted Incomplete records back to Complete.

## [0.81.0] — 2026-07-17

Client Administration: **Reassign Mentor** — replace an engagement's primary
mentor from the grid, with full access re-homing and a history stamp.

### Added
- **Row selection + Reassign Mentor button.** Clicking a grid row selects it
  (click again to deselect); the new toolbar button acts on the selected row.
  Never disabled: no row selected, or a row with no mentor yet, gets a notice
  explaining what to do instead.
- **Right-click context menu on every row**, covering all row functions:
  View details, Reassign mentor… (assigned rows) / Assign mentor… (unassigned
  rows, same picker driving the existing assign endpoint), Edit notes, and
  Refresh list. Right-click also selects the row; Escape/click-away closes.
- **Mentor picker dialog** (assign + reassign modes): eligible mentors with
  capacity labels, the current mentor excluded in reassign mode; confirming
  with nothing selected shows an inline "Select a mentor first."
- **`POST /assignments/api/engagements/{id}/reassign`** →
  `service.reassign_engagement`: validates the new mentor to the same bar as
  an initial assignment (Active + accepting + linked User) and requires an
  existing, different mentor; swaps `mentorProfile`; re-stamps
  `engagementAssignedDate`; and re-homes access so the new mentor can edit
  everything — engagement + every related Contact + CClientProfile + Account
  (swap-merge on `assignedUsers`: old mentor's User out unless a co-mentor
  shares it, co-mentors always preserved — the v0.76.1 merge rule) + every
  CSession on the engagement (old User removed except from sessions they
  personally own, the remove_comentor convention). `engagementStatus` is
  deliberately untouched (no re-acceptance round). Downstream failures are
  per-record best-effort (`reassignmentErrors`), reported in the UI and the
  note. DOC-09 Drive grants re-derived after, like assign.
- **History**: a stream note on the engagement with Doug's required wording —
  "Mentor X was replaced with Mentor Y on MM/DD/YYYY by user NAME." (date in
  Cleveland time) — plus the re-homing outcome.
- After a successful reassign, the MentorAssignmentNotice compose opens for
  the NEW mentor (same silent-fallback behavior as assign). 6 new tests.

## [0.80.0] — 2026-07-17

Client Administration layout pass (Doug's review of 0.79.0). Frontend-only.

### Changed
- **User profile corner.** "Signed in as …" + Sign out moved to the upper
  right of the page header, where a typical account chip lives; the old
  toolbar row is gone.
- **One control line.** Review Mentors + Refresh moved down onto the same
  horizontal line as the Status filter, with a new **full-text search** box
  between them: filters the loaded rows live across engagement name, status,
  client, contact, mentor name, notes, and the created/assigned dates. A
  search with no matches shows "No engagements match your search."
- **Buttons are never grayed out** (Doug's ruling, product-wide going
  forward): the Assign button is always active; clicking it without choosing
  a mentor shows a notice naming what's needed and focuses the dropdown
  (replaces the disabled-until-selected gating).

## [0.79.0] — 2026-07-17

Client Administration engagement grid: fill the window, show how long ago each
assignment happened, and offer the assignment-notice email right after an
Assign. Frontend-only (no API/schema change).

### Added
- **Days Assigned column** between Assigned Date and Notes: the number of whole
  calendar days between the engagement's assigned date and today (local
  calendar, matching the Assigned Date display). Unassigned / unstamped rows
  show "—". Sortable like the other columns; the first click puts the
  longest-assigned rows on top.
- **Assignment-notice compose after Assign.** When an assignment succeeds, the
  standard quick-compose dialog opens with the mentor's CBM email address as
  the To: recipient and the EspoCRM **MentorAssignmentNotice** template
  pre-applied (subject/body rendered server-side, `{Person.*}` resolved from
  the To address, signature re-appended, template attachments chipped). Silent
  best-effort: if the template doesn't exist or its parse fails, the blank
  compose opens instead (no error note); if app-sending is unavailable
  (Gmail integration off / no CBM mailbox) nothing opens. The shared
  `quickmail.js` widget gained `composeIfEnabled(email, {template})` +
  template pre-selection for this — available to every quickmail surface.

### Changed
- **The engagement grid fills the window.** The page is a full-height flex
  column: the grid takes all vertical space left under the toolbar/filters and
  scrolls internally with a sticky header, so a large monitor shows more rows;
  the footer stays put. The page's width cap was removed (density ruling: never
  max-width a page). On a short window the grid keeps a 12rem minimum and the
  page scrolls as before.

## [0.78.0] — 2026-07-17

Mentor Sessions grid: accept an engagement in place, and reach the mentor
personally from the pop-up. 9 new tests (662 green); both flows verified in
the stubbed-browser harness (arm → accept → row re-renders Assigned + success
notice; stale 400 → readable error + grid reload; peek shows Personal email
as a compose link right after CBM email). Not yet driven against the live CRM.

### Added
- **Personal (home) email in the mentor pop-up.** The Assigned Mentor peek
  (grid column, Overview rail — every `CMentorProfile` pop-up) now shows the
  mentor's linked Contact's email address as a **"Personal email"** row right
  after the CBM address, rendered as the standard compose/mailto link, so a
  colleague can email them personally in two clicks. Best-effort: no linked
  Contact, or a forbidden Contact read, just omits the row
  (`sessions/service.peek` + `_mentor_personal_email`).
- **Accept an engagement from the grid's Status column.** A mentor-domain
  engagement in **Pending Acceptance** renders its status cell as an amber
  pill button: first click arms it ("Accept — set to Assigned?"), second
  click moves the engagement to **Assigned** via the new
  `POST /{slug}/api/records/{id}/accept` (registered only where the domain
  declares the transition — `DomainConfig.list_status_accept`, mentor only).
  The server re-reads the status first and rejects with a readable 400 when
  the row went stale (nothing written — the v0.72.1 stale-guard shape); the
  frontend then reloads the grid. A best-effort stream note stamps the
  acceptance into the engagement's history naming the acting user (the
  v0.74.0 audit-trail convention). Written as the signed-in user, so the
  mentor's own ACL applies (mentors are in the engagement's assignedUsers).
- The mentor pop-up's kind label now reads "Mentor profile" (was the raw
  entity name `CMENTORPROFILE`).

## [0.77.0] — 2026-07-17

Reliability hardening **Phase 1** — the four P0 findings of the 2026-07-17
reliability review (`reliability-review-2026-07-17.md`; kickoff prompt
`prompts/reliability-hardening-prompt-v0.1.md`) plus the worker-traceback
logging fix. 13 new tests (653 green); poisoned-row drill run live against
local Postgres (worker survives, marks `needs_attention` with a traceback,
delivers the rest; sync-mode worker verified not claiming).

### Fixed
- **P0-1 — a poison payload can no longer crash-loop the worker.** Payload
  validation now runs inside the classify-and-route net: a submission the
  current schema rejects (e.g. a form schema tightened after capture) is a
  permanent failure routed to `needs_attention` instead of an escaping
  `ValidationError` that killed the process (and, via the lease, re-killed it
  every ~15 minutes forever, invisibly). A new top-level guard
  (`worker.run_cycle`) additionally ensures NO exception — store failure,
  claim error, anything — can kill the delivery loop: it logs the traceback
  and continues after the poll interval.
- **P0-2 — the documented rollback no longer double-delivers.** The worker's
  claim loop is gated on `ASYNC_DELIVERY`: with the flag off (sync mode, the
  documented instant rollback) the web tier delivers synchronously and the
  worker no longer also claims the same `pending` rows — previously both
  delivered every submission concurrently, duplicating CRM records. The
  worker stays up (monitoring/comms timers keep running) and logs a mode
  banner naming the disabled claim loop.
- **P0-3 — CRM transport failures now surface as `EspoError`.** Every
  `EspoClient` HTTP call funnels through one `_request` helper that wraps
  httpx transport exceptions (DNS, connect, TLS, timeout) as
  **`EspoTransportError(EspoError)`** — message names the operation + CRM
  host, never credentials. Previously raw `ConnectError`/`ReadTimeout`
  bypassed every `except EspoError` net: the intake sync path 500'd without
  `mark_failed`, staff routers' `_crm_failure` mapping was skipped (blank
  500/edge-504 exactly when the CRM was slow), `refresh_membership`'s
  fail-open didn't fire (the portal went down with the CRM), and assignments'
  per-target error accumulation aborted mid re-homing. All of those nets now
  catch outages too; the worker keeps classifying transport errors as
  transient (retryable).
- **P0-4 — sessions Details PUT gained the missing entity allowlist.**
  `PUT /{slug}/api/details/{entity}/{id}` now rejects any entity outside the
  domain's configured `details_entities` + `Contact` with a 404 (mirroring
  the peek allowlist; 404 so probing can't confirm entity names). It was a
  generic write proxy bounded only by the caller's CRM ACL — and the Mentor
  Role deliberately carries `CMentorProfile edit=all`, so any Mentor Team
  member could set `mentorStatus`/dues/compliance on anyone's profile,
  bypassing the mentorprofile whitelist and the Mentor Administration gate.

### Added
- **Worker `needs_attention` rows are now diagnosable from /ops.** Permanent
  failures log with the full traceback (`log.exception`) and store a
  traceback tail alongside the message in `last_error` — a code bug (e.g.
  `KeyError`) no longer lands as an unusable four-character string.

## [0.76.2] — 2026-07-17

### Fixed
- **`{CMentorProfile.name}` in email templates now resolves** (Doug's live
  report: selecting a template referencing the mentor name warned
  "Some placeholders couldn't be filled: {CMentorProfile.name}"). EspoCRM's
  parse only substitutes entities present in its render context —
  `{User.*}` = the sender, `{Person.*}`/`{Contact.*}` = the recipient,
  `{Parent.*}` + the parent's own type = the record — and CMentorProfile is
  none of those. The parse API accepts ONE extra record
  (`relatedType`/`relatedId`, added to the context under its own type), so
  the app now passes the **record's manager profile** automatically: the
  engagement's assigned mentor / the partner or sponsor manager
  (`parent_manager_link`, now set on all three domains), falling back to
  the **sender's own linked profile** (also what the record-less
  quick-compose uses). `comms/templates.related_manager_profile`;
  best-effort — an unresolvable profile just leaves the token + warning.
  Template-author guidance added to communications-tab.md (placeholder
  cheat sheet: {CMentorProfile.*} = the record's mentor/manager,
  {User.name} = whoever is sending, {Person.*} = the recipient,
  {Parent.*} = the record). 6 new/updated tests (612 green).

## [0.76.1] — 2026-07-17

### Fixed
- **Client Administration: assigning a mentor no longer strips co-mentor
  access from the client profile / company.** The re-home step wrote
  `assignedUsersIds: [<new mentor>]` to CClientProfile and Account — a hard
  overwrite that silently revoked the co-mentor `assignedUsers` stamps the
  session tools maintain on those records (the engagement write already
  merged co-mentors since v0.51.0; the client records didn't). The re-home
  now MERGES: each record's existing assigned users are kept and the new
  mentor + the engagement's co-mentors' users are folded in
  (`assignments/service._merged_assignment_payload`). Contacts were never
  affected (they take only the single `assignedUserId`).

### Added
- **Co-mentor stream notes name the acting user.** The engagement-stream
  notes posted on co-mentor add/remove (v0.74.0) now say who did it
  ("… via the session tools by Jane Staff") on every variant — success,
  no-linked-user, and stamp-failure. The Note's author already identifies
  the actor in the stream UI; naming them in the text keeps the history
  self-contained in API reads, exports, and quotes.

## [0.76.0] — 2026-07-17

### Added
- **Documents: CRM integration and lifecycle (DOC-MGMT Phase 3, PRD v1.3).**
  Three pieces, closing the PRD's phased plan:
  - **Drive access grants (DOC-09, the v1.3 access model):** the app now
    maintains per-person, folder-level **Commenter** grants on record
    folders, mirroring CRM entitlements — engagement folders → the assigned
    mentor + co-mentors, partner/sponsor folders → their manager, and
    `Mentors/` (Contact) folders → **no one** (application-only). Grants are
    issued/revoked best-effort by the same app actions that change the
    entitlement (Client Administration's Assign, the session tools'
    co-mentor add/remove, first upload for a record) with Google's sharing
    emails suppressed, and a **nightly reconciliation job** in the worker
    (`GDRIVE_RECONCILE_SECONDS`, default daily) re-derives the complete
    grant set from the CRM, corrects both directions of drift, logs
    corrections, and alerts on removals. Active only under
    `GDRIVE_IDENTITY=service` (the ruled access model). New:
    `docs/grants.py`, `docs/reconcile.py`, DriveClient permission methods.
  - **Archive / restore (DOC-07):** the Documents tabs' Archive button is
    live (two-step confirm) — the Drive file moves to the record folder's
    `/_Archived` subfolder FIRST, then the row's status flips (a mid-failure
    moves the file back — Doug's ruling: the two are never left
    inconsistent); the row leaves the default list, an **"Include archived"**
    toggle reveals archived rows (dimmed, "Archived" tag), and **Restore**
    reverses both steps. Hard deletion stays out of the app. New endpoints
    `POST …/documents/{id}/archive|restore` + `?includeArchived=` on the
    list/refresh, in the session tools and `/mentoradmin`.
  - **CRM link write-back (DOC-08):** on upload, the record's
    `documentsFolderUrl` field (CEngagement + Contact) is set to the record
    FOLDER's permanent Drive link (one stable link per record, D-05).
    Feature-detected from CRM metadata — inert until the field is built
    (spec handoff: `documentsfolderurl-crm-field.md`); idempotent (no write
    when it already matches); self-healing best-effort per Doug's ruling (a
    failure heals on the next upload or the nightly re-check — no retry
    queue). Written as the app's API user.

  Verified in unit/router tests (43 new; 649 total green) and both UIs in
  the stubbed-browser harness (archive → toggle → restore loops, two-step
  confirm, no console errors). **NOT yet driven against the real shared
  drive/CRM** — activation prerequisites (SA drive membership, human-member
  removal, `GDRIVE_IDENTITY=service` on web + worker, the CRM field build)
  are in `GDRIVE-DOCS-SETUP.md` Task 6.

## [0.75.1] — 2026-07-17

### Added
- **Communications grid: sortable + resizable columns** — the same
  capabilities the Sessions grid gained in v0.72.0, applied to the record
  detail's conversation list. All four headers (Status / Participants /
  Conversation / Last activity) sort (first click sorts — text A→Z, Last
  activity newest-first — second reverses, ▲/▼ + `aria-sort`); columns resize
  via the drag grip on each header's right edge (reuses
  `makeColumnsResizable`; first drag freezes widths via `table-layout:
  fixed`). Default widths give Participants generous room (26%); the head is
  built once and kept across tab revisits, so resized widths and the sort
  choice survive leaving and returning to the tab. Sample-data scaffold
  (comms off) unchanged. Verified in the stubbed-browser harness (sort
  orders + indicator movement, drag widens only the dragged column, grip
  clicks never sort, widths/sort persist across a Sessions↔Communications
  round trip, row click still opens the thread; no console errors). Note:
  the `app.js` half was swept into the parallel session's v0.75.0 release
  commit (068f44d) — this release carries the matching CSS, which HEAD
  needs for the grips/arrows to position correctly.

## [0.75.0] — 2026-07-17

### Added
- **Email signatures in every compose dialog.** The signature is the user's
  **EspoCRM `Preferences.signature`** (Doug's rulings 2026-07-16: EspoCRM
  Preferences as the source; auto-insert on open; re-append after a
  template; editable in My Mentor Profile). Gmail never appends its own
  signature to API-sent raw MIME, so the compose seeds it instead:
  - Both dialogs (record compose + the shared quick-compose) open a new
    message with the signature at the bottom of the rich-text body — plain
    editable text from there. It rides the existing `GET /mailbox` response
    (`signature`, sanitized; `comms/service.user_signature`, best-effort).
  - Applying an **email template** replaces the body with the rendered
    draft and **re-appends the signature below it** (EspoCRM's own compose
    behavior) — templates shouldn't carry their own sign-off.
  - A body still equal to the untouched seeded signature counts as
    **empty**: picking a template right after opening doesn't ask
    "Replace current content?", and the quick-compose's "Write a message
    first" guard still fires.
  - **My Mentor Profile gains an "Email signature" panel** (CBMRichText,
    own Save, placed above Internal CRM description): reads/writes the
    caller's own EspoCRM Preferences via new
    `GET/PUT /mentorprofile/api/signature` (sanitized server-side; users
    can already write their own Preferences — no grant work). Non-mentor
    staff can author theirs in EspoCRM → Preferences → Email Signature;
    the compose reads it wherever it was written.
  - Verified in the stubbed-browser harness (seed on open, no-prompt over
    the seed, re-append after template, prompt over real content, sent
    body carries the signature, quick-compose empty-guard, profile panel
    load/edit/save; no console errors) + 12 new tests (600 green). NOT yet
    driven live.

## [0.74.0] — 2026-07-16

### Added
- **Stream notes: app-side assignment and co-mentor changes now leave a durable
  audit line in the engagement's Espo history.** The staff tools act as the
  signed-in user, so their writes were indistinguishable in the stream from
  hand edits in the CRM UI by the same person — the root of the 2026-07-16
  double-assignment forensics. New `core/stream.post_stream_note` posts a Note
  (`type=Post`) parented to the engagement, best-effort (a rejected note never
  fails the operation). Client Administration's Assign posts "Assigned to X via
  the Client Administration app — status set to Pending Acceptance; re-homed …
  N/N contact(s), client profile, company" (with per-target no-link/FAILED
  detail and an error count); the session tools' co-mentor add/remove post what
  was granted/revoked and to how many records.

### Fixed
- **Adding a co-mentor now grants them access to the client's records, not just
  the engagement** (Doug's defect report): the Details tab's CBM Contacts + Add
  stamped the co-mentor's user into `CEngagement.assignedUsers` only — the
  related contact(s), client profile, and company kept only the original
  mentor, so under read-own roles the co-mentor couldn't see/work them.
  `sessions/service.add_comentor` now also merges the user into
  `assignedUsersIds` on every related contact, the CClientProfile, and the
  Account (resolved via `clientOrganization` with the client profile's
  `linkedCompany` fallback for intake-created engagements); `remove_comentor`
  un-stamps them symmetrically (unless shared with the assigned mentor or a
  remaining co-mentor). Only the multi-user collaborators field is touched —
  the single `assignedUser` (primary owner) is never changed. Per-record
  best-effort; the stream note reports the actual stamped count. CRM
  prerequisite: the entity must have "Multiple Assigned Users" enabled —
  Contact was missing it on prod (Doug enabled it 2026-07-16); crm-test should
  be checked for parity.

## [0.72.1] — 2026-07-16

### Fixed
- **Client Administration: a stale browser can no longer overwrite a saved
  assignment.** The Assign action (`assignments/service.assign_engagement`)
  now re-reads the engagement before writing anything and rejects the call
  with a readable message when it already has a mentor (names the current
  mentor) or its status is no longer `Submitted` (names the current status) —
  previously a second browser/tab whose grid predated another user's
  assignment would silently re-assign the engagement, reset it to Pending
  Acceptance, re-stamp `engagementAssignedDate`, and re-home its
  contacts/client/account to the second mentor (observed live as a
  double-assignment in an engagement's Espo history). Nothing is written on
  rejection; the frontend re-fetches the grid on any 400 from Assign so the
  stale row immediately shows the real state.

## [0.72.0] — 2026-07-16

### Added
- **Sessions grid (record detail → Sessions tab): sortable, resizable, with a
  Participants column.** Every column header sorts (same interaction as the
  Client Administration grids: first click sorts — text A→Z, When
  newest-first, Duration numeric — second click reverses; ▲/▼ + `aria-sort`);
  columns resize by dragging a grip on each header's right edge (first drag
  freezes current widths via `table-layout: fixed` so one column's change
  doesn't reflow the rest; widths live on the `th`s, surviving re-renders and
  sorts; grip clicks never trigger a sort). New **Participants** column lists
  each session's attendees, widest by default (28% vs Session's 22%) — the
  names were already fetched for the Overview note feed, so `get_detail` just
  mirrors them onto the session rows (`participants`), zero extra CRM calls.
  All three domains (shared frontend). Verified in the stubbed-browser
  harness (sort orders incl. numeric duration + blank-participants rows,
  indicator movement, controlled drag → only that column widens, no stuck
  drag state, no console errors). Note: the `app.js` half of this feature was
  accidentally swept into the parallel session's v0.71.0 release commit
  (e01d4cd) — this release carries the matching headers/CSS/backend, which
  HEAD needs for the grid to render correctly.

## [0.73.0] — 2026-07-16

### Added
- **Documents: Download action — the original file, for the locally
  installed application** (Doug's report: downloading from the xlsx viewer
  yielded the PDF *rendering*, not the spreadsheet — the browser PDF
  viewer's own download button saves what's displayed; and the
  convert-on-view round-trip is slow when the goal is working with the
  file, not reading it). A browser can't launch Excel/Word directly
  against a remote file, so the equivalent: every document row (session
  tools + Mentor Administration) gains a **Download** action, and the
  in-app viewer header gains **"Download original"** — both stream the
  stored file's EXACT bytes (`?original=true` on the content proxy,
  `Content-Disposition: attachment`), formulas and all, no conversion, no
  conversion delay; the user opens the download in whatever their machine
  has installed for the type. Google-native files (no native bytes)
  download as their Office equivalent — Sheets → `.xlsx`, Docs → `.docx`,
  Slides → `.pptx` — matching Drive's own Download behavior
  (`GOOGLE_NATIVE_DOWNLOADS`; `DriveClient.export_file` generalizes the
  PDF export). Same immutable browser-cache headers, versioned URL.
  6 new tests (590 green); verified in the stub harness (row + viewer
  buttons, attachment download without page navigation).

## [0.71.0] — 2026-07-16

### Added
- **Documents: service-account identity mode + in-app Office viewing**
  (Doug's rulings: users must NOT have Google Drive access — membership was
  never granted broadly, so the PRD's impersonate-the-manager model only
  ever worked for actual drive members; and Office files must be viewable
  in-app).
  - **`GDRIVE_IDENTITY=service`** (new env, default `user` = the old
    behavior): the service account performs ALL Drive operations as ITSELF
    — managers need no shared-drive membership and no Drive access of any
    kind; the app's CRM ACL check is the sole viewing/upload gate, and the
    app-level `uploaded_by` still records the real person (a missing
    `cbmEmail` no longer blocks anything in this mode — it was only ever
    needed as the impersonation subject). **Activation: add the service
    account's `client_email` as a member (Content Manager) of the "CBM
    Documents" shared drive, then set the env on the web component.**
  - **Office formats (Word/Excel/PowerPoint + OpenDocument + CSV) now view
    in-app**: the server converts on view — `files.copy` with conversion to
    the matching Google editor format (a temp file), `files.export` to PDF,
    temp deleted even on failure — and streams the PDF into the same
    viewer. The stored original is never modified (D-04 holds; this is
    read-time conversion). First view of an Office file costs the
    conversion round-trip (a few seconds for typical files); the browser
    cache makes repeat views instant. Files whose export exceeds Drive's
    cap surface the readable failure message.
  - Frontend: Office MIME types moved from the "can't preview" fallback to
    the viewer frame in both UIs.
  4 new tests (584 green); ruff clean; xlsx-view path verified in the stub
  harness. Open ruling (recorded in CLAUDE.md): whether Open in Drive is
  removed entirely (option 2) or backed by per-user additive grants
  (option 4) — the button currently still opens the webViewLink, which
  only works for actual drive members.

## [0.70.1] — 2026-07-16

### Fixed
- **Document uploads can no longer fail silently** (Doug's report: a
  PowerPoint upload "just stopped" and reset to the Upload button with no
  message — the exact failure couldn't be diagnosed afterward because the
  deploy had rotated the app instance and its logs; probable cause was the
  in-flight upload dying during that instance swap). Hardened on both
  surfaces (session tools + Mentor Administration):
  - Upload failures now display in the **notice bar above the table**
    (styled, scrolled into view) instead of a small line below it that
    could sit out of view; the staged file + type are kept so retry is one
    click.
  - A connection that dies mid-upload shows a plain-language "upload was
    interrupted — check your connection and try again" message (previously
    the browser's cryptic "Failed to fetch", or nothing visible).
  - Uploads switched from fetch to XHR so the button shows **live progress
    ("Uploading… 62%")** — a large file on a slow uplink no longer looks
    frozen.
  - **Client-side size gate:** picking a file over the server cap
    (`GDRIVE_MAX_FILE_MB`, now reported as `maxFileMb` on the documents
    list/refresh responses) is rejected immediately with the size and the
    limit, instead of starting a doomed upload.
  - **Server receipt log:** every upload logs who/filename/bytes at INFO
    the moment the body arrives, so the next report is diagnosable from
    `doctl apps logs` even if later steps fail.
  Verified in the stubbed-browser harness (oversize gate, success, server
  400 with the exact detail shown, dropped-connection message; button and
  staged file recover in every failure). Probe note: the DO edge accepted
  test bodies up to 60 MB, so no platform size wall sits in front of the
  100 MB app cap.

## [0.70.0] — 2026-07-16

### Added
- **Documents: in-app viewing goes live — DOC-MGMT Phase 2** (DOC-03/04/06 +
  the DOC-02 lazy refresh, per the PRD's Phase 2, adapted to the web
  architecture with Doug's rulings: in-app overlay viewer + the browser as
  the cache). In the session tools AND Mentor Administration:
  - **View (DOC-03):** each document row's View button opens a
    workspace-sized overlay rendering the file inside the app, streamed
    through a new proxy endpoint
    (`GET …/documents/{id}/content` — the parent record is read AS THE USER
    first, so their CRM ACL gates viewing; the Drive fetch then runs under
    their own delegated CBM identity, keeping the D-01 audit trail). PDFs
    render in the browser's native PDF viewer (iframe), images inline,
    plain text inline; formats the browser can't render (docx/xlsx/…)
    show a clear message with an Open in Drive button.
  - **Google-native formats (DOC-04):** Docs/Sheets/Slides have no native
    bytes — the proxy serves them via `files.export` to PDF
    (`DriveClient.export_pdf`; an export over Drive's cap surfaces the
    readable 502 + Open in Drive fallback). `checksum_md5` stays null;
    `modified_time` is the sole invalidation key.
  - **Cache (DOC-06, web adaptation — Doug's ruling):** no server-side
    cache (App Platform's disk is ephemeral); the proxy response is
    `Cache-Control: private, max-age=31536000, immutable` and the frontend
    versions the URL with the row's `modifiedTime`, so each browser holds
    the bytes, cache hits are instant with zero network, and a Drive edit
    (new modifiedTime → new URL) invalidates automatically.
  - **Lazy modifiedTime refresh (DOC-02 completion):** opening the
    Documents tab renders from metadata immediately, then fires
    `POST …/documents/refresh` — ONE `files.list` scoped to the record
    folder (`DriveClient.list_folder_files`) re-syncs each row's
    modifiedTime/checksum/view-link (`DocumentStore.update_file_state`);
    rows edited in Drive since last sync come back flagged and show an
    amber **"Updated in Drive"** tag. Best-effort: a refresh failure leaves
    the metadata render standing.
  - New service surface: `docs/service.fetch_document` /
    `refresh_documents` / `content_headers` / `is_google_native`;
    `DocumentStore.get_document` is scoped to the anchor record, so a doc
    id can never be fetched through another record's route.
  Verified: 17 new tests (57 documents tests, 580 total green) + both UIs
  driven end-to-end in the stubbed-browser harness (metadata render → auto
  refresh → flag; PDF/image/Google-native/fallback viewer modes; versioned
  URLs pick up the refreshed modifiedTime; overlay close; no console
  errors). **NOT yet driven against the real shared drive** — needs a
  deploy (see the live checklist in the session close-out). No new env
  vars, no new migration; Archive stays a disabled Phase 3 placeholder.

## [0.69.0] — 2026-07-16

### Added
- **Documents: "Open in Drive" is live** (DOC-05 pulled forward from Phase 2
  — Doug's call after the first successful live upload; the `webViewLink`
  was already stored on every row, so this is frontend-only). The button on
  each document row (session tools + Mentor Administration) now opens the
  file's Drive page in a new tab (noopener; authorization happens at click
  time via the user's Workspace session); a row without a stored link keeps
  the disabled state. View and Archive remain Phase 2/3 placeholders.
  Verified in the stubbed-browser harness (enabled state, window.open
  target/features, View/Archive still disabled).

## [0.68.1] — 2026-07-16

### Fixed
- **The session tools' Details tab no longer dies with "Could not load
  details: your account doesn't have permission…" when ONE card's entity is
  unreadable** (Doug's report — a run of these errors from staff). The
  Company (Account) / Client Business Profile card reads weren't
  403-tolerant, so a role missing a single read grant lost the whole tab.
  A card the user can't read now renders as a titled "restricted" card
  naming the entity ("no read access to Account records — ask CBM staff"),
  and a forbidden contacts read shows the same note on the Client Contacts
  card; everything else loads (`sessions/details.py`, matching the peek
  pop-ups' existing tolerance).

### Changed
- **Permission-denied errors now name the exact missing grant, product-wide.**
  New `core.espo.forbidden_hint` parses the denied CRM operation and the
  messages read "…: your CRM role is missing read access to CClientProfile
  records — ask CBM staff to grant it" instead of the generic "doesn't have
  permission to do this in the CRM". Applied to the session tools, My Mentor
  Profile, Client Administration, and Mentor Administration (the latter two
  previously surfaced CRM 403s as raw 502s; Client Administration's
  engagement-detail endpoint now also gets the 401-on-expired-session
  handling).

## [0.68.0] — 2026-07-16

### Added
- **Documents: PRD v1.2 alignment — engagement folders nest under their
  client, mentor documents anchor to the Contact, top-level display labels**
  (Doug's updated `CBM-DocMgmt-Implementation-PRD.docx` v1.1/1.2 + the revised
  Phase 1 prompt; his rulings this session: mentor documents live in **Mentor
  Administration**, and the partner/sponsor tabs stay functional under their
  own labels).
  - **Folder tree (PRD §3.2, D-07):** top-level Drive folders are now
    configurable **display labels** (`GDRIVE_ENTITY_LABELS`, default
    `Contact=Mentors,CEngagement=Clients,CPartnerProfile=Partners,
    CSponsorProfile=Sponsors`). A client-work upload resolves the
    engagement's parent client at upload time (own `clientOrganization` link
    with the client-profile `linkedCompany` fallback — the same
    `fill_company_fallback` the rest of the tools use) and lands in
    `Clients/{Client Name} (clientId)/{Engagement Name} (engagementId)/`; an
    unresolvable client nests directly under `Clients/` rather than blocking
    the upload. Mentor/partner/sponsor anchors stay single-level under their
    label.
  - **`client_record_id`** added to `app_document` (Alembic
    `0006_app_document_client`, nullable + indexed) — the parent client id,
    denormalized on engagement-anchored rows for cross-engagement client
    reporting; returned as `clientRecordId`.
  - **Mentor Administration gains a Documents tab** (`/mentoradmin` detail,
    shown when `GDRIVE_DOCS` is on): list + upload anchored to the mentor's
    **linked Contact** record (`Mentors/{Name} (contactId)/`); a mentor with
    no linked Contact gets a readable 400 before any write. New endpoints
    `GET/POST /mentoradmin/api/mentors/{id}/documents` (same raw-bytes
    contract, gates, and rollback as the session tools); View / Open in
    Drive / Archive rendered disabled (Phase 2/3).
  - 18 new/updated tests (75 documents tests total, suite green); migration +
    `client_record_id` round-trip verified against a live local Postgres;
    both UIs verified in the stubbed-browser harness. Still NOT driven
    against real Google Drive — activation checklist unchanged
    (GDRIVE-DOCS-SETUP.md; the folder tree there is updated).

## [0.67.0] — 2026-07-16

### Added
- **Email templates in every compose dialog (ET)** — per the Email Template
  Integration PRD (`prompts/email templates/…`), adapted into this app per
  Doug's rulings (target = the Communications tab + everywhere the compose
  UI shows; write-back BOTH ways; user attachments in v1; templates on the
  quick-compose too). EspoCRM renders, the app sends (Decision ET-D1 — the
  app never substitutes placeholders):
  - **Picker** in the record compose (session tools) and the shared
    quick-compose widget (assignments/mentoradmin/grid peeks): the EspoCRM
    email templates the ACTING USER may see (role/team visibility, ET-101),
    name-ordered with type-ahead filtering. New endpoints
    `GET /{slug}/api/emailtemplates` (+ the quicksend surface) backed by
    `comms/templates.py`; `EspoClient.email_template_prepare` wraps the
    EspoCRM 9.x `POST EmailTemplate/{id}/prepare` action (signature verified
    live on crm-test 9.3.6 — closes PRD open issue ET-OI-4).
  - **Rendering**: selection calls parse with the record as `{Parent.*}`
    context and the first recipient's address for `{Person.*}` (an address
    alone resolves the person — closes ET-OI-1, and is how the record-less
    quick-compose personalizes). The rendered subject/HTML body load into
    the editor as a plain editable draft; unresolved placeholders (which
    EspoCRM leaves as literal `{X.y}` tokens) trigger a review-before-send
    notice (the ET-OI-2 warning). Selecting over a non-empty draft asks
    "Replace current content?" first (ET-113); a parse failure shows a
    readable error and leaves the draft untouched (ET-114).
  - **Attachments**: template standing attachments appear as removable
    chips (ids only — bytes stay in the CRM until send, ET-B3), and users
    can attach their own local files (both dialogs; 20 MB total cap, both
    sides). At send time the server downloads retained template attachments
    as the acting user and builds a multipart/mixed message
    (`core/gmail.build_mime` attachments support,
    `comms/service.resolve_attachments`); ANY attachment failure BLOCKS the
    send (ET-131).
  - **Write-back**: on top of the existing CConversation/CCommunication
    write-through ingest, every app send now also creates a native EspoCRM
    **Email** record (status Sent, parented to the recipient's Contact when
    one matches, created as the acting user so History shows them —
    ET-140..143). A write-back failure after a confirmed send switches the
    dialog to a retry screen (`POST …/emailwriteback`) — never silent
    (ET-142).
  - **Quick-compose upgraded**: the widget's body is now the standard
    CBMRichText editor (assignments pages load the Jodit assets; plain
    textarea remains the script-load fallback), so template HTML renders
    and sends as HTML.
  - **Optional context filter via native template categories**: a template
    whose Category is named `Engagement`/`Partner`/`Sponsor` shows only in
    that domain's session-tool picker; no category or any other category
    name shows everywhere. No CRM build — admins just create/assign the
    categories. (EmailTemplate is `customizable:false` — not in Entity
    Manager, so the originally-planned custom field was impossible;
    corrected same day.)
  - Verified in the stubbed-browser harness (both dialogs: picker +
    type-ahead, apply, replace-confirm keep/replace, chip removal, local
    upload, send payload, token warning, parse-failure draft preservation,
    write-back retry loop; no console errors) + 23 new tests (549 green).
    **NOT yet driven against the live CRM/Gmail.** CRM prerequisite: the
    Partner Manager + Sponsor Manager roles need EmailTemplate read (+
    Email create) grants — Mentor Role and Standard User already have them
    (read live 2026-07-16).

## [0.66.0] — 2026-07-16

### Changed
- **Communications: conversation messages are headed by WHO WROTE THEM**
  (Doug's report: outbound showed "To: <address>", inbound the sender — so
  with a mentor and co-mentor both sending on the same engagement, the
  thread never said which of them was talking). The conversation view now
  leads every message with the sender's name (or address) for both
  directions; outbound keeps the recipients after an arrow ("Doug Bower →
  james@acme.test"). The sample-data scaffold (comms off) matches. Backend
  data was already there (`from`/`fromAddress` on every message) —
  frontend-only display change (`sessions/frontend/app.js`
  `viewConversation`).
- **Sends stamp the manager's display name on the From header** ("Doug
  Bower <doug.bower@cbmentors.org>"): `core/gmail.build_mime` gains
  `sender_name`, passed by both the record compose (`send_message`, the
  signed-in user's name) and the grid quick-compose (`send_quick_message`
  via `comms/quicksend.py`). Without it a tab-sent message's write-through
  ingest stored a bare address as the sender, so the new sender-first
  display would have shown addresses instead of names for app-sent mail
  (synced Gmail mail already carried display names). Recipients see the
  name too. Messages stored before this change keep whatever the header
  carried. NOT yet driven against live Gmail; verified by tests
  (526 green).

## [0.65.0] — 2026-07-16

### Added
- **Documents tab goes live — Google Drive document management, DOC-MGMT
  Phase 1** (PRD: `prompts/Google Drive Documents/
  CBM-DocMgmt-Implementation-PRD.docx` v1.0, adapted from its desktop-app
  framing to this web app per Doug's rulings: built into the session tools'
  existing Documents placeholder tab; Drive auth via the existing
  service-account + domain-wide-delegation stack impersonating the signed-in
  manager's own `cbmEmail` — Drive audit logs still attribute every upload to
  the real person — instead of the PRD's desktop keyring/loopback OAuth).
  Gated by **`GDRIVE_DOCS`** (+ `GDRIVE_SHARED_DRIVE_ID`; needs
  `DATABASE_URL`) — off, the tab shows a "coming soon" placeholder and the
  endpoints 503. What shipped:
  - **Upload (DOC-01):** file picker + doc-type select in the tab; raw-bytes
    POST to `/{slug}/api/records/{id}/documents`; the file lands on the
    "CBM Documents" shared drive under
    `/{Entity Type}/{Record Name} ({recordId})/` (both folder levels created
    on first upload, folder id cached via the metadata rows); native MIME
    preserved (never converted, D-04); resumable Drive upload for files over
    5 MB; Drive rate-limit/5xx retried with backoff (NFR-02). Rollback rule
    enforced: a metadata-write failure deletes the Drive file, a Drive
    failure writes no row. Uploader identity + Drive impersonation subject
    both come from the manager's CRM-resolved CBM mailbox, never request
    input. Size cap `GDRIVE_MAX_FILE_MB` (100); doc types `GDRIVE_DOC_TYPES`.
  - **Per-record list (DOC-02, partial):** filename / type chip / uploader /
    upload date, newest first, rendered from the new **`app_document`**
    Postgres table only (no Drive call; Alembic `0005_app_document`, PRD §4
    schema incl. the `(entity_type, record_id, status)` composite index).
    View / Open in Drive / Archive render disabled ("Coming soon") — they are
    Phase 2/3, deliberately not built.
  - New: `core/gdrive.py` (`DriveClient`, gcalendar pattern), `docs/`
    (`store.py` + `service.py`), 40 new tests (metadata layer incl. a live
    local-Postgres pass, folder scheme, rollback both directions,
    impersonation-subject rule, endpoint gates/validation, upload-mode
    selection). Verified in the stubbed-browser harness (list, upload
    round-trip with correct params/bytes/MIME, error + cancel paths,
    flag-off placeholder). NOT yet driven against real Google Drive — needs
    the manual prerequisites (shared drive + memberships, `drive` scope on
    the DWD grant) and a live smoke test; activation runbook in
    DEPLOYMENT.md.

## [0.64.2] — 2026-07-16

### Fixed
- **Clicking an email inside a contact/company pop-up on the GRID page now
  opens a compose dialog** (Doug's live report: contact-name pop-up → email →
  nothing happened). The v0.64.0 session-tools wiring fell back to `mailto:`
  whenever no record was open — which is every peek launched from the list
  page (contact, company, assigned-mentor columns), and a machine without a
  mail handler shows nothing at all. Grid-page peeks now use the shared
  quick-compose dialog: the session routers gained `POST /sendmail`
  (`comms/quicksend.py`, reused) and their `GET /mailbox` reports
  `sendEnabled`; the frontend delegates to the quickmail widget when no
  record is open (in-record peeks keep the full record-scoped compose).
  Verified in the stubbed-browser harness: grid peek → quick dialog →
  send payload posted; record peek → full compose over the pop-up with the
  clicked contact pre-checked.

## [0.64.0] — 2026-07-16

### Added
- **Every email address shown in the staff UIs is now a compose link** —
  clicking it opens the app's own email dialog instead of the browser's
  mailto: handler (Doug's ruling: a quick email from wherever you see an
  address). Three surfaces:
  - **Session tools**: the Details cards/contact tables, the company
    directory block, the session view's attendee grid (address is clickable,
    the ⧉ copy button stays), and the peek pop-ups all open the existing
    record-scoped compose dialog pre-filled with that address (contact
    add/create routing, reply threading, record linking all apply).
  - **Client Administration + Mentor Administration**: a new lightweight
    quick-compose modal (`frontend/shared/quickmail.js`) backed by new
    `GET /mailbox` + `POST /sendmail` endpoints on both apps
    (`comms/quicksend.py`) — sends To/Subject/Message as the signed-in
    user's own `@cbmentors.org` mailbox via the same delegated-Gmail stack
    (`comms/service.send_quick_message`). No record linking; the regular
    Gmail sync ingests the sent copy when it matches a record the sender
    manages, exactly like mail sent from Gmail itself.
  - **Fallback**: links keep a real `mailto:` href (middle-click/copy-link
    unchanged), and a plain click falls back to the browser mail handler
    whenever app-sending isn't available — Gmail integration off (the dev
    app), no CBM mailbox on the user's profile, or (session tools) no open
    record to send from. The static help@cbmentors.org support link on My
    Mentor Profile deliberately stays a plain mailto:.

## [0.64.1] — 2026-07-16

### Changed
- **Assigned Mentor grid column is a pop-up link**: clicking the mentor's
  name opens the standard mentor-profile pop-up (type, status, CBM email,
  expertise, industry), where the CBM email is a compose/mailto link — a
  co-mentor can email the primary mentor in two clicks. `list_records` rows
  carry `mentorId` (`mentorProfileId` added to the mentor-domain select).
  Verified in the stubbed-browser harness (name click → pop-up → mailto
  href present).

## [0.63.0] — 2026-07-16

### Fixed
- **Mentor Sessions grid: the Next Session column actually shows values.**
  It read the stored `CEngagement.nextSessionDateTime`, which nothing in the
  CRM populates — every row showed "—" despite scheduled future sessions.
  The 0.62.0 upcoming-sessions sweep now has no upper bound (all sessions
  from now−36h onward, soonest first, one ACL-scoped query) and the cell
  derives from it: the soonest SCHEDULED session that is today
  (viewer-local) or later. Falls back to the stored value; column sorting
  works on the derived date.

### Added
- **Assigned Mentor column** at the far right of the Mentor Sessions
  engagements grid (`CEngagement.mentorProfileName`) — a co-mentor can see
  who the primary mentor on each engagement is. Verified in the
  stubbed-browser harness (next-session derivation for today/future/none,
  mentor names render, today flag intact; no console errors).

## [0.62.0] — 2026-07-16

### Fixed
- **Overview session feed: the Upcoming / Past sections now ALWAYS render**
  when the record has any sessions (Doug's report: they showed on James
  Koran but not Randa Jackson — the old heuristic only labelled the split
  when both groups existed and one had 3+, so a record with only past
  sessions got no sections). An empty group shows a muted note ("No
  upcoming sessions scheduled." / "No past sessions yet."). A Scheduled
  session dated today files under Upcoming even after its start time
  passes.

### Added
- **Clearer temporal color coding + TODAY flagging in the session tools.**
  Upcoming session cards (and the session-view band) are now clearly blue
  (`#d8e8fc` + a navy left accent) against the neutral-gray past cards.
  A session **scheduled for today** (the viewer's local today) gets a **red
  header band with bold white text** on its Overview card and session view.
  The **engagements grid on the landing page** flags records the same way:
  a record with a session scheduled today renders its name **red + bold**
  (tooltip "Session scheduled today"). Server side, `list_records` attaches
  `sessionsNearNow` (one ACL-scoped CSession query over a ±36h window,
  best-effort) so the frontend can resolve "today" in the viewer's own
  timezone. Verified in the stubbed-browser harness (today/future/past
  cards, past-only feed shows both sections + the empty note, grid row red
  + bold only for the today record; no console errors).

## [0.61.0] — 2026-07-16

### Added
- **Mentor Sessions: the first completed session activates the engagement.**
  Saving a session with status **Completed** (create, or an edit that changes
  the status to Completed) on an engagement whose `engagementStatus` is
  **Assigned** or **Assignment Dormant** moves the engagement to **Active**
  (`sessions/service._activate_engagement_on_completed`). The engagement-status
  guard makes it a first-completed-session rule: once Active (or any other
  status a staffer set — On-Hold, Dormant, Completed, …) later saves are
  no-ops, and a notes-only edit to an already-completed session never
  re-activates a parked engagement (the frontend diffs, so an unchanged status
  isn't in the payload; the server additionally only reacts to a payload
  status of Completed). Mentor domain only — partner/sponsor parents have no
  engagement lifecycle. Best-effort like the calendar hook: a CRM failure
  (e.g. a role that can't edit CEngagement) never fails the session save; the
  save response carries `engagement:{activated,from,to|error}` and the save
  notice tells the user ("The engagement status is now Active." / could-not-
  update note). The detail view re-fetches after save, so the status badge and
  grid refresh on their own.

## [0.60.0] — 2026-07-16

### Changed
- **Communications: the compose email body is the standard rich-text editor
  (CBMRichText/Jodit).** The plain textarea in the session tools' compose
  dialog is replaced by the shared editor — bold/italic/lists/links/color/
  tables, formatted paste — and Send now transmits the message as HTML
  (`sessions/frontend` `commField`/`commBodyValue`; no backend change —
  `comms.service.send_message` was already HTML-native and derives the
  plain-text MIME alternative server-side). The compose modal widens to
  46rem to fit the toolbar and give email-writing room; the plain textarea
  remains only as a script-load fallback (plain text is upconverted
  server-side). Verified in the stubbed-browser harness (editor renders in
  the modal, formatted body arrives at the send endpoint as sanitized HTML,
  reply flow unchanged; no console errors). First live Gmail SEND from the
  tab is still an open item — unchanged by this.

## [0.59.2] — 2026-07-16

### Fixed
- **Uniform control heights + spacing in the Details edit panels** (Doug's
  report: dropdowns rendered a different height than adjacent date/text
  inputs, and some controls touched). Every single-line control (text /
  number / email / tel / date / datetime / select, incl. the time-picker
  input) inside `.sxf` is now pinned to exactly 2.4rem with border-box
  sizing; row/address/checkbox gaps unified to one rhythm (12px vertical ×
  16px horizontal; checkbox grids 8px) so no two controls touch. Applies to
  the Engagement, Company, and Client Business Profile forms alike (shared
  CSS). Verified in the stubbed-browser harness: all 45 single-line
  controls across the three open forms measure 38.4px, minimum gap between
  adjacent controls ≈16px.

## [0.59.1] — 2026-07-16

### Changed
- **Engagement panel edit form gets the mockup-v4 treatment** (completing
  the set: Company 0.57–0.58, profile 0.59.0). Full schema triage against
  live CRM metadata, `noExtras`, packable panels: **Engagement** (status /
  start date / read-only Mentor / cadence; hold-end + close date + close
  reason) | **Outcomes** (the four outcome checkboxes + revenue/employment
  increase %) on the first band, **Mentoring need & focus** (focus-area
  chips + needs description) | **Engagement notes** on the second. Fields
  that used to fall into "Additional details" now have homes. Excluded from
  EDIT (still shown on the summary strip, which composes independently):
  the record name (the page header shows it), the Assign-action date stamp,
  and the CRM/app-maintained session statistics (total sessions/hours,
  last-30-days, last/next session). Verified in the stubbed-browser harness
  (strip keeps the stats, no excluded field renders in the form, Mentor
  read-only, bands fill the window, save PUT carries exactly the edited
  fields; no console errors). NOT yet eyeballed against the live CRM.

## [0.59.0] — 2026-07-16

### Changed
- **Client Business Profile edit form gets the mockup-v4 treatment** (same
  process as the Company form): full schema triage against live CRM metadata
  — every field explicitly placed or excluded, `noExtras` (no more
  "Additional details" dump) — with the groups as packable panels
  (Business structure | Financials, Sales & market | Certifications &
  demographics, Goals; bands always fill the window). Six previously
  dumped fields got homes: State of Formation + Industry Sector + Number of
  Employees + Fiscal Year End Month → Business structure, Social Media
  Presence → Sales & market, Local Licenses and Permits → Business
  structure. The read-only Most Recent Full Year Revenue figure shows
  inside Financials. Excluded from the form (CRM untouched): the record
  `name` (intake-derived; the card title identifies the record) and the
  revenue Currency/Converted companions. `DETAILS_REMOVED_FIELDS` is now a
  per-entity map, and the profile VIEW card consumes the exclude list like
  the Company card does. Verified in the stubbed-browser harness (panels
  band + fill width, excluded fields absent even with values, all six new
  placements render, dirty dots + sticky bar narrate, save PUT carries
  exactly the edited fields incl. int + multiEnum chips; no console
  errors). NOT yet eyeballed against the live CRM.

## [0.58.1] — 2026-07-16

### Changed
- **Edit-form group panels darkened** (Doug's follow-up to 0.58.0): panel
  background `#fbfcfd` → `#f2f5f8` (border `#e7ebef` → `#dfe3e8`) so the
  groups delineate more clearly against the white card; the approved mockup
  (`prompts/company-edit-form-mockup-v4.html`) updated to match.

## [0.58.0] — 2026-07-16

### Changed
- **Details edit forms: full-width packed group panels** (design review with
  Doug; approved mockup `prompts/company-edit-form-mockup-v4.html`). The
  measured problem at ~2580px: single-column groups left ~40% of the form
  area empty (Web presence used 55% of its band), long-text fields spanned
  the whole monitor, packing orphaned fields onto random lines, and the form
  was 1,232px tall. Now each group renders as a light PANEL with a natural
  width (`grow`/`basis` on the layout group) and panels pack left-to-right —
  **every band always fills the full window width** (Doug's ruling: aligned
  right edges, no ragged panels). Wide screens put several groups on one
  band (Identity | Web presence | Addresses, Notes below; everything on one
  band on 4K); laptops stack as before. Each layout row is one flex line
  (no orphan fields); long-text cells cap at a readable 72rem inside their
  panel. Applies to all Details edit forms (Company/profile/engagement
  strip/contact rows/create-contact).

### Added
- **Changed-field dots + sticky save bar** on the Details edit forms: a gold
  dot marks each field whose value differs from what was loaded (reusing the
  save's own snapshot diff, so it exactly predicts the write); Save/Cancel
  ride the bottom of the viewport with a live "N fields changed" narration;
  Save is disabled until something actually changed. Verified in the
  stubbed-browser harness (bands fill width at 2580px and stack narrow, dot
  count rises/falls with edits and reverts, save PUT carries only the
  changed field, same-as-billing mirror + Contact Country intact, no console
  errors). NOT yet eyeballed against the live CRM.

## [0.57.1] — 2026-07-16

### Fixed
- **Edit-form width cap removed** (Doug's ruling on seeing 0.57.0: "the app
  is supposed to utilize as much of the screen as possible" — the 960px
  constraint came from prompt v0.2's standing rule 1, now reversed in the
  prompt doc's v0.3 revision). `.sxf` is full-width again with the v0.41.2
  content-sized PACKING field widths (flex wrap; a row holds as many fields
  as the screen fits). Everything else from 0.57.0 stands: the four Company
  groups in mockup order, the field triage/exclusions, Country inside both
  address blocks, the inline "Same as billing" checkbox, and `noExtras`
  (no "Additional details" dump). Verified in the stubbed-browser harness.

## [0.57.0] — 2026-07-15

### Changed
- **Company edit form rebuilt to mockup v3** (`prompts/
  section-edit-screens-prompt-v0.2.md`, approved; design target
  `prompts/company-edit-form-mockup-v3.html`). The session tools' Edit
  Company form is now the four approved groups in order — **Identity**
  (Company name 6 / Phone 3 / Email 3; Organization type / Business stage /
  Industry / SIC code ×3; Industry sector 6 / subsector 6), **Web presence**
  (Website 6 / LinkedIn page 6), **Addresses** (billing + shipping side by
  side, Country inside each block, "Same as billing" inline in the Shipping
  sub-header), **Notes** (Description + Client notes full width). Four
  fields are removed from the app's form entirely (CRM untouched): Annual
  Pledge Amount Currency, Target Population, Applicant Since Timestamp
  (system-managed), Contact Role. Standing rules (all edit forms, per the
  prompt): **`.sxf` is a centered `max-width: 960px` container** — Doug's
  approved exception to the no-width-cap ruling, which still governs pages
  and grids — with a **true 12-column grid** whose spans match the mockups
  (replaces the v0.41.2 flex packing), max ~4 inputs per row; and **unplaced
  schema fields never auto-render** (the Account layout's `noExtras` flag
  kills the "Additional details" dumping ground — placing a new CRM field is
  an explicit layout decision). Partner/sponsor domains keep their curated
  relationship groups, which now place `cPartnerNotes`/`cSponsorNotes`
  explicitly (previously reached the form via the leftovers group).
  Verified in the stubbed-browser harness: 960px centered, groups/spans per
  mockup, Country in both blocks + inherited by the Contact form, same-as-
  billing dims/mirrors/restores and the save payload carries only genuinely
  changed fields, none of the four excluded fields render even with values,
  no Additional-details group, no raw time inputs, no console errors. NOT
  yet eyeballed against the live CRM. (Race note: the `app.js` side of this
  work was swept into commit 3dc9509 (v0.56.0) by the parallel session; this
  release carries the CSS, so 0.57.0 is the version where the form actually
  renders to spec.)

## [0.56.0] — 2026-07-15

### Added
- **Session tools: pre-save prompt before auto-creating a calendar invite.**
  Saving a NEW Scheduled session (with a start time, calendar integration
  active) now pops a styled confirm — "Create a calendar invite?" — before
  anything is written: **Create & send invite** proceeds as before (Google
  Calendar event + Meet link + emailed invitations), **Save without invite**
  saves the session but skips the event entirely (for meetings the user wants
  to schedule manually; the save notice says so), **Keep editing** (or
  Escape/backdrop) returns to the editor without saving. Edits to existing
  sessions are unchanged (never prompted — the patch/cancel matrix still
  applies). Plumbing: `/session` config exposes `gcalEnabled`; the create
  POST carries `skipCalendar`; `service.create_session(skip_calendar=True)`
  bypasses the gcal hook and reports `calendar:{ok,skipped,declined}`.
  Verified in the stubbed-browser harness (prompt appears before any POST;
  all three buttons + Escape; declined save sends `skipCalendar:true` and
  shows the manual-scheduling notice; Completed sessions and gcal-disabled
  deploys save directly with no prompt; no console errors). Not yet driven
  against live Google.

## [0.55.1] — 2026-07-15

### Fixed
- **Session tools: a CRM permission rejection now surfaces as a readable
  403, never a blank 502/504.** Found during the Details-tab live
  write-through verification (crm-test, as the non-admin mentor
  matt.mentor): "+ Add → Create new contact" hit EspoCRM's `POST /Contact`
  403 (the Mentor Role has no Contact create grant) and "Select existing"
  hit `noAccessToForeignRecord` on the relate (EspoCRM requires edit on the
  contact being linked) — both came back to the browser as "Request failed
  (504)". `sessions/router._crm_failure` now maps a CRM 403 to HTTP 403
  with a plain-language "your account doesn't have permission… ask CBM
  staff" message (covers every session-tools route); real CRM 5xx still
  maps to 502. 3 new tests.

### Verified (no code change)
- **Details-tab section saves VERIFIED LIVE on crm-test as a non-admin
  mentor** — closes the section-edit-screens acceptance criterion 6 (the
  v0.41.x open item): engagement strip (`meetingCadence` enum), Client
  Business Profile (bool), and contact-row edit (`title`) each saved
  through the UI, GET-verified on a fresh CRM read, and reverted; failed
  saves keep the form open with an inline error. ACL gating confirmed on
  real permissions: the Account section came back `editable:false` (no Edit
  button on the Company card) and the engagement form's Mentor field is
  absent (read-only by design). **CRM-side gaps found (Doug to decide):**
  the Mentor Role lacks the Contact *create* grant, and linking an existing
  contact needs edit access on that contact — so both "+ Add" flows are
  unavailable to mentors until granted (staff can use them via roles with
  broader Contact access).

## [0.55.0] — 2026-07-15

### Changed
- **Communications: conversation Participants now list everyone on the
  emails, deduped by address.** Doug's ruling: knowing who was *included* on
  an email matters, not just who wrote — so the sync now folds the sender
  AND all To/Cc recipients of each ingested message into the conversation's
  participants list (previously senders only, so a client CC'd on every
  message but never replying was invisible in the column). Entries are
  stored as `Name <address>` (bare address until a message supplies the
  display name) and deduped by email address, which also fixes the same
  person appearing twice as "Jane Smith" and "jane@acme.com"; a bare-address
  or legacy name-only entry upgrades in place once the name/address is
  learned. The list clamps to whole entries within the CRM's 500-char field.
  Existing conversations backfill naturally as new mail arrives on the
  thread (`comms/sync.py`, `comms/crm.py:merge_participants`,
  `core/gmail.py` now keeps To/Cc display names).

## [0.54.1] — 2026-07-15

### Fixed
- **Details tab: saving a company/contact with a human-formatted phone number
  no longer fails.** Doug's live report on crm-test: a company update was
  rejected with "'Phone Number' has a value the CRM does not accept." EspoCRM
  only accepts E.164 (`+12165551234`), but the session tools' Details-tab
  save sent the typed value verbatim (the field spec mapped the CRM `phone`
  type to a plain varchar, losing the phone-ness). Phone-type fields are now
  normalized via `core.phone.to_e164` on save — same policy as the Mentor
  Administration Contact tab — covering the company/profile/contact edit
  forms and the create-new-contact flow. Blank still clears the field; an
  already-E.164 value passes through unchanged.

## [0.54.0] — 2026-07-15

### Added
- **"Forgot your password?" on the portal sign-in** (the single login screen
  for all the staff apps). The link opens a small reset form (username +
  email); `POST /api/portal/forgot-password` proxies EspoCRM's own
  unauthenticated `User/passwordChangeRequest` endpoint, so the CRM does the
  matching/throttling and sends its standard recovery email — the app never
  sees or sets a password. The user follows the emailed link (the CRM's
  change-password screen), then signs back in at the portal. Errors are
  exact and readable (no matching user/email; recovery disabled or a link
  already sent recently; CRM unreachable). Requires password recovery
  enabled in the CRM — probe-verified ENABLED on both crm-test and prod
  (a bogus-user request returns 404, not the disabled 403). Also styled the
  portal's login error/success messages locally (`.form-error` was only
  defined in wizard.css, which the portal doesn't load).

### Changed
- **CBMRichText (Jodit) rolled out to ALL wysiwyg fields** — completes the
  v0.50.0 POC per Doug's approval. `/mentoradmin` (Bio tab: About the mentor /
  Professional bio / Why interested) and `/mentorprofile` (About you /
  Professional bio / Why you mentor) now render every wysiwyg field through
  the shared `CBMRichText` component; the hand-rolled contenteditable editors
  remain only as a script-load fallback. mentorprofile's live website preview
  is driven by the component's `onInput` hook (Jodit toolbar actions don't
  fire a native bubbling `input`, so the form's delegated listener alone
  would miss them); mentoradmin's jump-to-issue focus handles the new editor.
  Both apps' diffed-save machinery verified intact in the stubbed-browser
  harness (snapshots stable against Jodit's async HTML normalization,
  untouched save sends no/empty changes, an edit sends only the changed
  field, live preview updates on Jodit edits; no console errors). Every
  wysiwyg surface product-wide now uses the standard editor.

## [0.52.0] — 2026-07-15

### Fixed
- **Co-mentors see ALL sessions on the engagement** (follow-up to 0.51.0,
  which made the engagement itself visible). `CSession` is read at "own" by
  the Mentor Role, so a session was visible only to the user stamped on it —
  a co-mentor couldn't see the history, and the assigned mentor couldn't see
  a co-mentor's sessions. Three stamps (mentor domain only):
  - **New sessions** stamp the engagement's whole mentor team into
    `assignedUsers` — the creator + the assigned mentor + every co-mentor —
    so everyone on the engagement sees every new session, whoever writes it.
  - **Adding a co-mentor backfills** their User onto the engagement's
    existing sessions (per-session best-effort: under edit=own the acting
    mentor can only stamp sessions they own; others are logged and skipped).
  - **Removing a co-mentor un-stamps** them from those sessions — except
    sessions they personally own (their `assignedUser`), which stay theirs.

## [0.51.0] — 2026-07-15

### Fixed
- **Co-mentors now see the engagement in their own engagement list.** Adding
  a CBM contact on the Details tab related the mentor profile
  (`CEngagement.additionalMentors`) but the engagement never appeared for
  them, for two independent reasons — both fixed:
  1. **List scope:** `/mentorsessions` read only `engagements1` (reverse of
     `CEngagement.mentorProfile` — engagements they're the ASSIGNED mentor
     of). It now also reads the co-mentor reverse link **`engagements`**
     (reverse of `additionalMentors`; link name verified live on crm-test AND
     prod) and merges the rows, deduped
     (`DomainConfig.manager_comentor_link`, mentor domain only).
  2. **CRM visibility:** the Mentor Role reads `CEngagement` at "own", which
     (with `assignedUser` disabled) means membership in the **`assignedUsers`**
     collaborators field. Adding a co-mentor now also appends their linked
     login User to the engagement's `assignedUsers` (their role's
     `assignmentPermission=team` allows assigning fellow Mentor Team members).
     Best-effort: no linked User / a rejected write keeps the relate and
     returns a readable warning the Details tab shows. Removing a co-mentor
     removes their User again — unless the assigned mentor or a remaining
     co-mentor shares it.
- **Client Administration reassignment no longer strips co-mentor access.**
  `assign_engagement` overwrote `assignedUsersIds` with just the new mentor;
  it now merges the current co-mentors' Users into the write (best-effort).

## [0.50.0] — 2026-07-15

### Added
- **Standard rich-text editor (CBMRichText / Jodit) — proof of concept on the
  session tools.** The hand-rolled contenteditable wysiwyg is replaced by a
  proper editor: **Jodit 4.13.3** (MIT) vendored at
  `frontend/shared/vendor/jodit/` and wrapped by the new shared component
  `frontend/shared/richtext.js` (`CBMRichText.create`) — full toolbar (bold/
  italic/underline/strikethrough, color, paragraph format, lists, link, table,
  hr, clear-format, undo/redo), spellcheck, silent formatted paste. CRM HTML
  is stripped on load AND on read (the app's sanitize pass, independent of
  Jodit's own filtering); an untouched editor reads back the exact
  render-time value (gesture-gated), so Jodit's async HTML normalization
  (`<b>`→`<strong>` etc.) can't fake an unsaved change or widen a save diff.
  Wired into the sessions frontend only for now (`makeInput`/`readField`
  wysiwyg path — session editor + Details tab), with the legacy
  contenteditable kept solely as a script-load fallback. Verified in the
  stubbed-browser harness (loads formatted CRM HTML, clean-back shows no
  unsaved-changes prompt, edit → PUT carries only the changed field with
  event-handler attributes stripped, new-session create sends `""` for an
  empty editor + the typed HTML, no console errors).
  **Convention (Doug's ruling): every future wysiwyg field product-wide uses
  CBMRichText** — mentoradmin/mentorprofile migration is the planned rollout
  after this POC is approved.

## [0.49.0] — 2026-07-15

### Added
- **Client Administration: column sorting on the engagements grid.** All four
  headers (Engagement / Assign to mentor / Assigned Date / Notes) are
  clickable — first click sorts (text A→Z, Assigned Date newest-first),
  second click reverses; ▲/▼ + `aria-sort` mark the active column (the same
  interaction as the Review Mentors grid). Client-side over the loaded rows;
  the sort persists across Refresh and post-assign reloads. Unsorted default
  stays the server order (newest created first).

## [0.48.0] — 2026-07-15

### Added
- **Client Administration: Assigned Date column on the engagements grid**,
  between "Assign to mentor" and Notes — when the mentor was assigned
  (`CEngagement.engagementAssignedDate`, the stamp the Assign action writes;
  shown as the local calendar date). Unassigned rows and pre-0.27.0
  assignments (which have no stamp) show "—".

## [0.47.0] — 2026-07-15

### Added
- **Mentor Administration: LinkedIn field on the Profile tab.** The mentor
  detail editor's Profile tab gains a "LinkedIn profile" input. The value is
  stored on the linked Contact's `cLinkedInProfile` (the same field the My
  Mentor Profile tool and the public-website mentor page use), so saves route
  to the Contact record; a mentor with no linked Contact gets the existing
  clear 400 before any write.

## [0.46.2] — 2026-07-15

### Removed
- **Sessions tab no longer shows the "CBM Contacts" panel** (mentor sessions
  app): the co-mentor list + add picker under the sessions table was the old
  pre-Details duplicate. CBM contacts are viewed and managed on the Details
  tab's CBM Contacts table (add/remove there is unchanged), and co-mentors
  still show on the Overview rail.

## [0.46.1] — 2026-07-15

### Added
- **Communications compose shows the From address** (session tools, all three
  domains): the compose/reply dialog's first row is now "From: <the signed-in
  user's own CBM mailbox>" so the user knows which account the message goes
  out as. New `GET /{slug}/api/mailbox` resolves it via the same
  `cbmEmail` lookup the send path uses (fetched once per page, cached); a
  profile with no CBM email shows "no CBM email on your profile — sending
  won't work" instead of an address.

## [0.46.0] — 2026-07-15

### Changed
- **Communications compose defaults to ALL record contacts as To recipients**
  (session tools, all three domains): the compose dialog now lists every
  contact on the record that has an email address as a checkbox — all checked
  by default — so the user deselects anyone to leave off rather than typing
  addresses. An "Other recipients" field takes addresses not on the record
  (they still route through the existing add-to-record / create-contact
  flow). Reply pre-checks only the address(es) being replied to; contacts
  without an email address are omitted. Send now requires at least one
  recipient (readable message instead of a server 400).

## [0.45.5] — 2026-07-14

### Changed
- **`/mentorprofile`: photo, "Mentoring since" badge, and status toggles share
  ONE horizontal top row** (badge centered between them, top-aligned) — the
  0.45.4 badge-on-its-own-line layout pushed the photo/toggles down, wasting
  vertical space.

## [0.45.4] — 2026-07-14

### Changed
- **`/mentorprofile`: the "Mentoring since" badge is now a centered line at
  the TOP of the form section** (its own row above the photo/toggles bar) —
  it previously floated vertically centered in the bar, looking unanchored.
  (0.45.3 left unused — a version-number race with a parallel session.)

## [0.45.2] — 2026-07-14

### Changed
- **`/mentorprofile`: "Mentoring since mm/dd/yyyy" moved out of the page
  header** into the top bar, centered between the profile photo and the
  status toggles — reclaims header height on smaller screens. Also (unversioned
  in 0.45.x): the footer now matches the other apps ("All rights reserved." +
  the " · " separator before "vX.Y.Z (Test/Production)").

## [0.45.1] — 2026-07-14

### Added
- **Client Administration: Internal Notes in the engagement popup.** The
  engagement detail modal gains a full-width "Internal Notes" section showing
  the grid's internal process notes (`CEngagement.description`), rendered as
  plain text with line breaks preserved (via `textContent` — markup shows
  literally). "—" when empty. The detail read selects `description` and
  returns it as `internalNotes` (distinct from `notes` = `engagementNotes`).

## [0.45.0] — 2026-07-14

### Changed
- **`/mentorprofile` layout + field pass (Doug's review):**
  - **"Show my profile on the website" and "Accepting new clients" moved to a
    prominent top-right status panel** opposite the profile photo — large
    (18px bold) toggle cards with big checkboxes that read GREEN when on and
    AMBER when off, so a mentor can't miss their visibility/availability
    state.
  - **"Mentoring since mm/dd/yyyy"** badge in the page header (read-only
    `mentorStartDate`; hidden when unset).
  - New **Personal details panel** to the right of Contact information:
    Birthday (`Contact.cBirthday`) + Spouse name (`Contact.cSpouseName`) —
    both fields verified existing on crm-test AND prod — plus Years of
    experience (moved from Mentoring preferences).
  - **Max client capacity** (`maximumClientCapacity`) is now mentor-editable,
    placed left of Pause start / Pause end in Mentoring preferences.
  - **Internal CRM description** (`description`) as a large text box at the
    very bottom. (Rendered as plain text, not rich-text: the CRM field is
    type text, so HTML markup would show as raw tags in the CRM UI.)

## [0.44.0] — 2026-07-14

### Added
- **Client Administration: click-to-edit Notes column** on the engagements grid
  (new rightmost column). Clicking a cell opens an inline editor (Save / Cancel,
  Escape cancels); notes are stored in **`CEngagement.description`** via the new
  `PUT /assignments/api/engagements/{id}/notes` endpoint
  (`service.update_engagement_notes`), written as the signed-in user. These are
  staff-internal process notes about the assignment: `description` is surfaced
  in no other user interface — the session tools' metadata-driven Details tab
  now explicitly excludes it for CEngagement (`sessions/details.py`
  `_ENTITY_EXCLUDED`), on both render and save. Note: the intake orchestrator's
  enum-drift follow-up note also lands in `description`, so it shows in the
  Notes column — by design (it is exactly triage material); editing the cell
  replaces it.

## [0.43.0] — 2026-07-14

### Added
- **My Mentor Profile release marker** — first deploy of the `/mentorprofile`
  tool (v0.42.0 + v0.42.1 below). `CMentorProfile.mentorSummary` was built on
  crm-test (Text, verified live 2026-07-14), so the feature-gated summary box
  activates there on this deploy. Prod still lacks
  `mentorTitle`/`profilePhoto`/`mentorSummary` — the tool deploys inert-ish
  there (summary box hidden by the gate; headline/photo need the prod field
  build per `cmentorprofile-summary-field.md` + CLAUDE.md).

## [0.42.1] — 2026-07-14

### Changed
- **The `/mentorprofile` website preview is now an EXACT reproduction of the
  live mentor page** (Doug's ruling: mentors edit to look good on the website,
  so the preview must be what the site renders). The page's own HTML + CSS
  (the Elementor widget on clevelandbusinessmentors.org/mentor/…, fetched
  2026-07-14) are copied verbatim into the preview — navy hero with the
  gold-ringed circular photo (gradient placeholder when no photo, same as the
  site's fallback), name + gold title line, the 1fr/2fr profile grid (gold
  "ABOUT {FIRST}" label + summary + Request-a-Mentor / LinkedIn buttons +
  Industry Experience box left; Areas-of-Expertise gold-dot list + navy-ruled
  About box right), and the navy bottom panel ("Ready to Connect with
  {first}?" / Meet All Our Mentors / Questions). Rendered at the site's
  1200px desktop width and scaled to fit the pane; expertise/industry fill
  logic mirrors the page's own script; static links are inert (a real
  LinkedIn URL opens new-tab); first name flows into all four name slots.

### Added
- **`mentorSummary` — the website's short summary paragraph, feature-gated.**
  Doug's ruling: a new dedicated CRM field feeds the left-column summary
  (distinct from `aboutMentor`). NOT built in the CRM yet — the app
  feature-detects it from metadata (`sessionTranscription` precedent): the
  editor box, reads, and saves activate on their own once the CRM team builds
  it (spec: `cmentorprofile-summary-field.md`, incl. the full page-slot ↔ CRM
  field mapping for the website feed).

## [0.42.0] — 2026-07-14

### Added
- **My Mentor Profile (`/mentorprofile`)** — a self-service tool where a mentor
  edits their OWN `CMentorProfile` + linked Contact from one screen, with a
  **live preview styled like the public website mentor page** (the CRM feeds
  the website, so the pane shows exactly what the site will render: photo =
  `profilePhoto`, name = Contact first/last, headline = `mentorTitle`,
  Areas of Expertise = `areaOfExpertise`, Industries Served =
  `industryExperience`, About = `aboutMentor`, LinkedIn = Contact
  `cLinkedInProfile`). Linked from the portal for **Mentor Team** members
  (`MENTOR_PROFILE_ALLOWED_TEAMS`, default `Mentor Team`; friendly aliases
  `/mentorprofile`, `/myprofile`).
  - **Always "me":** no record id is ever taken from the request — every
    endpoint resolves the caller's own profile server-side
    (`sessions.service.resolve_manager_profile`), and all reads/writes run as
    the logged-in user (EspoCRM enforces their ACL).
  - **Non-administrative field set** (`mentorprofile/service.py:PROFILE_FIELDS`
    — the single source for the form layout AND the server-side whitelist):
    public-profile fields (photo, headline, publish toggle, expertise,
    industries, about, LinkedIn), contact info (name/email/phone/address, on
    the linked Contact), mentoring preferences (accepting, pause window,
    business stages, languages, years), and the internal bios. Status,
    compliance, dues, capacity, departure etc. are absent from the whitelist,
    so a smuggled change is dropped. Same protections as Mentor Admin: diffed
    saves, drifted-enum sanitization with plain-language warnings, E.164
    phone, CRM-required fields enforced from metadata.
  - **Photo upload/remove** — `CMentorProfile.profilePhoto` (image field):
    JPEG/PNG/WebP/GIF ≤5 MB, uploaded immediately as an Attachment; the app
    proxies the image bytes (`GET /mentorprofile/api/photo`, new
    `EspoClient.download_attachment`) since the browser can't reach the CRM.
  - Full-width layout with a drag splitter (form left, preview right); the
    unpublished state shows a banner + dimmed preview.
  - **CRM prerequisites** (crm-test has the fields; see CLAUDE.md): prod needs
    `mentorTitle` + `profilePhoto` built; the Mentor Team role needs
    CMentorProfile read/edit-own, Contact edit-own, and Attachment
    create/read for the photo.

## [0.41.2] — 2026-07-14

### Changed
- **No page-width cap — fields pack instead** (Doug's ruling: users are on 4K
  monitors; density comes from more data per row, not a narrower page). The
  0.41.1 `max-width: 1080px` is gone. Edit-form fields are now CONTENT-SIZED
  flex items that wrap: each width class is a sensible size for that field's
  data, and a line holds as many fields as the screen fits (5+ Identity fields
  per line at ~1700px, more at 4K; graceful wrap on laptops). Checkbox sets
  flow into as many columns as fit. The postal address block keeps its fixed
  internal proportions and packs as one cell (billing/shipping side by side
  whenever they fit).

## [0.41.1] — 2026-07-14

### Changed
- **Edit-form density pass** (Doug's review of 0.41.0): forms cap at 1080px
  wide, so a span-8 street field is ~40 characters instead of 100+; tighter
  group/row rhythm. **Billing and shipping addresses sit side by side** on one
  panel (billing left, shipping right, each with its own heading) — half the
  vertical space; the Contact address block is half-width too. **Country now
  lives inside the address block** (it was orphaned in Additional details).
  Company Identity groups all three industry fields on one row (Industry |
  Industry sector | Industry subsector — subsector was stranded at the bottom)
  and gains Email address. "Same as billing" now restores the original
  shipping values when unchecked (checking still copies billing over them).
- LinkedIn field labels render as "LinkedIn …" — the label generator no
  longer splits the brand into "Linked In" (`sessions/details.py:_label`).

## [0.41.0] — 2026-07-13

### Added
- **Section edit screens (prompt v0.1 / mockup v2)** for the session tools'
  Details tab: every section/contact edit form is now a curated, grouped
  12-column layout instead of a flat auto-fill field dump
  (`sessions/frontend/app.js` `DETAILS_LAYOUTS` + `layoutForm`).
  - **Edit Engagement** — Status | Start date | Mentor (read-only — Doug's
    ruling: reassignment stays in Client Administration) | Session cadence on
    one row; every other editable engagement field in "Additional details".
  - **Edit Company** — Identity (name/website/phone; org type/stage/industry/
    sector) + Billing address + Shipping address. **On the mentor domain the
    Partnership & account group is removed by design** (Account type, Client
    status, Partner/Sponsor fields, Public announcement) and the Company VIEW
    card's Account/Cadence/Announcements rows are gone — the right column now
    carries Business + Shipping. Partner/sponsor domains keep a curated group
    of their own relationship fields (Doug's scoping ruling); the system
    discriminators (`cAccountType`/`cClientStatus`/`cCompanyType`/`type`) are
    edited nowhere.
  - **Edit Client Business Profile** — Business structure / Financials /
    Sales & market / Certifications & owner demographics / Goals, with
    checkbox sets and mockup wording.
  - **Edit Contact** — Name / Contact information / Address / Preferences &
    agreements; used by row edits AND the + Add → Create-new-contact flow
    (same grouped form, empty).
  - Uncurated editable fields always land in an "Additional details" group —
    nothing the CRM exposes becomes uneditable; a missing field skips cleanly.
- **Reusable postal address block** (billing/shipping/contact): Address line
  1 (8) | line 2 (4); City (6) | State (2, US-state select) | ZIP (4). The two
  street lines map to EspoCRM's single multi-line street field (split on
  render, rejoined on save). The shipping instance gets a **"Same as billing
  address"** checkbox — checked dims/disables shipping and mirrors billing
  values live (the CRM models this as copied values; there is no flag).
- **Time-picker standard for every time field app-wide**: datetime fields are
  now a Date input + a time field opening a popover — half-hour slots
  ("Morning" 8:00–11:30 AM, "Afternoon & evening" 12:00–7:30 PM, 4 columns,
  navy selection) with an "Other time" free-entry escape (Enter commits;
  invalid input flags red). Replaces the browser `datetime-local` control
  (and its minute spinner) everywhere in the session tools, including the
  session editor's Start (UTC round-trip and the duration→dateEnd derivation
  unchanged; required-field check still fires when date or time is missing).
- **Multi-value fields are tap-to-toggle chip selectors** (funding sources,
  sales channels, certifications, contact type, meeting type, …) — never
  multi-select list boxes or checkbox grids. Options come from the CRM field
  definitions; a stored value that has drifted out of the options still
  renders selected so a save can't silently drop it.

### Changed
- `sessions/details.py` no longer hides `name` from the field spec, so
  Company name (and other varchar `name` fields) is editable on the forms;
  Contact's `personName`-typed name is still composed from first/last. The
  view suppresses the redundant "Name" row/cell (the card title/page header
  already shows it).

## [0.40.2] — 2026-07-13

### Changed
- **New sessions pre-invite ALL related contacts, not just CBM contacts**
  (Doug's ruling, widening the CBM-only default of v0.37.1): the attendee
  picker on a NEW session starts with every client/partner/sponsor contact
  AND every CBM contact checked (`defaultAttendees()` in the sessions
  frontend). Unchecking stays an explicit choice, and — with the calendar
  integration on — the Google Calendar invitations now reach the client
  contacts by default too. Editing an existing session still shows its
  actual attendee set.

## [0.40.1] — 2026-07-13

### Added
- **The meeting link is now visible and copyable** (Doug's live report after
  the first successful calendar event: the Meet URL existed only behind the
  Start Session button, with no way to copy it). It now shows as a clickable,
  truncating URL with a ⧉ copy-to-clipboard button in two places: the
  Overview's **Next session** callout (under the date, above Start Session)
  and the read-only **session view**'s facts grid (a "Meeting link" row,
  next to Meeting type/Location). New `linkWithCopy` helper reusing the
  attendees-grid copy machinery; `addKV` gains a `copylink` type. Verified in
  the stub harness (render, href, copy-failure notice path).

## [0.40.0] — 2026-07-13

### Added
- **Sessions create Google Calendar events with Meet links.** Saving a
  **Scheduled** session in any session tool now creates a Google Calendar
  event on the manager's OWN calendar (delegated as their
  `CMentorProfile.cbmEmail` via the shared service account — the same
  domain-wide-delegation stack the comms Gmail integration uses), with a
  **Google Meet** conference whose URL is written back to
  `CSession.videoMeetingLink`, and the session's attendee contacts invited
  (Google emails the invitations, `sendUpdates=all`). Later edits to
  time/title/attendees **patch the same event**; setting the status to
  Cancelled **cancels it** (clearing the stored event id and the generated
  Meet link — a hand-typed non-Meet link is never touched, and a session with
  a hand-typed link gets an event without a Meet conference, the link carried
  in the event's location). Logging a Completed past session never creates an
  event, and a notes-only edit never touches the calendar. New:
  `core/gcalendar.py` (delegated Calendar REST client), `sessions/gcal.py`
  (the best-effort sync hook — a Google failure never fails the session save;
  the outcome rides the save response as `calendar:{ok,...}` and shows as a
  notice in the UI). **Gated OFF by `GCAL_EVENTS`** and additionally inert
  until the CRM gains `CSession.googleCalendarEventId`
  (feature-detected via metadata; CRM handoff: `csession-calendar-field.md`).
  Activation also needs the Google Calendar API enabled in the GCP project
  and the `calendar.events` scope added to the service account's
  domain-wide-delegation grant. Replaces the crm-test-only EspoCRM
  server-side calendar sync experiment (personal account) — **disable that
  before enabling this**, or sessions get double events; production never had
  it (the app owns all email + calendar operations). 28 new tests.

## [0.39.2] — 2026-07-13

### Fixed
- **Session times now convert between the viewer's timezone and UTC** (live
  report: Google Calendar meetings didn't match the time shown in the app).
  The app itself creates no calendar events — EspoCRM's server-side Google
  Calendar sync does, from the `CSession.dateStart`/`dateEnd` the app writes,
  and the EspoCRM API treats those datetimes as **UTC**. The sessions frontend
  was sending the user's local wall-clock digits verbatim (and displaying
  stored digits verbatim), so a session entered as 3:30 PM Cleveland was
  stored as 3:30 UTC and the synced calendar event landed hours off. The
  frontend datetime boundary now converts both ways
  (`sessions/frontend/app.js`: `parseNaive` parses stamps as UTC,
  `fromLocalInput`/`toLocalInput` convert the datetime-local editor value
  local ↔ UTC, `stampPlusSeconds` emits UTC for the derived `dateEnd`,
  `fmtWhen` displays local) — the app, the EspoCRM UI, and Google Calendar
  now agree, each rendering in the viewer's own timezone. Date-only values
  (e.g. `formationDate`) still parse as local calendar dates, so they don't
  shift a day. Backend unchanged (it already assumed CRM datetimes are UTC).
  **Note:** sessions saved *before* this fix stored local digits as UTC and
  remain offset until manually re-saved with the correct time (Doug's ruling —
  no backfill, since a script can't distinguish app-created sessions from
  ones entered correctly via the CRM UI).

## [0.39.1] — 2026-07-13

### Fixed
- **CBM Contacts "+ Add" never opened its menu** (Details tab, live report).
  `repaintDetails` mapped any key starting with "c" to the Client Contacts
  card — and the CBM card's own key `cbmContacts` starts with "c", so every
  CBM-card repaint redrew the client card instead and the + Add menu (and the
  pick-a-mentor panel) never appeared. Row-edit keys (`c0…`/`b0…`) are now
  matched exactly. Verified in the stub harness: CBM + Add → menu → picker
  loads; client/CBM row Edit still expand.

## [0.39.0] — 2026-07-12

### Added
- **Session tools Details tab: contacts can now be removed.** Every Client
  Contacts row and every co-mentor row in CBM Contacts gets a **Remove** action
  (two-step inline confirm — "Remove" → "Really remove?" — no browser dialogs).
  Removal detaches the relation only (`engagementContacts`/`contacts`/
  `sponsorContacts`, or `additionalMentors` for co-mentors): the contact /
  mentor profile record itself stays in the CRM. The **assigned Mentor row is
  not removable** — that link is managed in Client Administration. Remove is
  shown only when the signed-in user can edit the parent record (the unrelate
  is a parent-relation write), and is hidden while the row's edit form is open.
  New endpoints: `DELETE /{slug}/api/records/{id}/contacts/{contactId}` and
  (mentor domain) `DELETE /{slug}/api/records/{id}/comentors/{profileId}`.
  Add flows (select existing / create new / pick CBM contact) already existed
  (v0.33.0); this completes the add/remove pair.

## [0.38.2] — 2026-07-12

### Added
- **Assigned mentor on the engagement Overview** (it wasn't displayed anywhere
  on the page): a key fact on the upper-left rail, right above Meeting
  cadence, linked to a pop-up of the mentor's profile (`CMentorProfile` added
  to the peek allowlist — mentor type, status, CBM email, areas of expertise,
  industry experience).

## [0.38.1] — 2026-07-12

### Fixed
- **Company now shows for intake-created engagements** (prod report: the Agape
  — James Koran engagement had a blank Company in the mentor sessions grid
  despite the client and company existing in the CRM). Root cause: the grid —
  and the Overview / Details / contact-company stamping — read
  `CEngagement.clientOrganization`, but the client-intake orchestrator never
  wrote that link; intake puts the Account on the CLIENT PROFILE
  (`CClientProfile.linkedCompany`) only. Two-part fix: (1) the orchestrator now
  links the Account to the engagement itself on create, and (2) for existing
  records the session tools fall back through the client profile's
  `linkedCompany` (`DomainConfig.company_fallback`) — the grid Company column +
  pop-up, the Overview's aggregated Company link, the Details company card, and
  the company stamped onto added/created contacts all resolve it. Best-effort:
  a profile the user can't read just leaves the company blank.

## [0.38.0] — 2026-07-12

### Changed
- **Records open as a dedicated page — `/{slug}/record/{id}` — not a mode of
  the list** (Doug's ruling: a record in another tab must be a real page, and
  "Back to list" goes away). Clicking a record on the grid opens
  `/mentorsessions/record/<id>` (partner/sponsor likewise) in a new tab: the
  server serves the shared frontend with a `<base href="/{slug}/">` so its
  assets resolve, and the JS boots **straight into that record** — no records
  list is fetched at all on a record page, and the browser tab is titled with
  the record's name. The list page is now purely a launcher; the "← Back to
  list" button and the old `?record=` deep-link mode are removed. Session
  editor/view navigation within a record page is unchanged ("Back to record").

## [0.37.2] — 2026-07-12

### Fixed
- **CBM contacts really are invited by default now** (0.37.1's default came up
  empty on live data, found by Doug on first use). Two live-data realities the
  0.37.1 implementation missed: engagements almost never carry
  `additionalMentors` (the CBM person on the record is the **assigned mentor**
  on `CEngagement.mentorProfile`), and several mentor profiles have **no
  linked contactRecord**. The invitee set is now resolved server-side
  (`cbmContacts` on the detail read): the assigned manager's profile plus any
  co-mentors, each resolved to a Contact via `contactRecordId` with a
  fallback Contact lookup by the profile's `cbmEmail` (the comms precedent),
  deduped. Profiles that resolve to no Contact are skipped — the durable fix
  for those is linking the profile's contactRecord (or cbmEmail) in the CRM.

## [0.37.1] — 2026-07-12

### Changed
- **CBM contacts are invited by default on new sessions** (Doug's ruling): the
  attendee picker now lists the engagement's CBM contacts (co-mentors with a
  linked Contact, tagged "(CBM)") alongside the client contacts, and a NEW
  session starts with every CBM contact pre-checked — in the dirty-tracking
  baseline, so unchecking is an explicit choice. Client contacts start
  unchecked as before.
- **Session view band, refined:** the "Client Session" type chip is gone — the
  type renders only when it differs from the domain's default, so it appears
  exactly when it says something. The **status badge (Scheduled/Held/…) moves
  to the center of the band and renders larger** — it is the key value. Date
  range stays left; Start Session / Open Meeting Link stays right.

## [0.37.0] — 2026-07-12

### Changed
- **Session detail View — Doug's session-details design rulings applied
  (Display Standard §12 extended).** Every fact appears exactly once:
  - **The band carries the time RANGE** ("Thursday, July 9 — 2:00 PM–3:00 PM",
    end computed from `dateEnd`); the Duration key-value row is gone.
  - **The video link is the band's action** — "Start Session" on a future
    session, "Open Meeting Link" on a past one — not a grid row.
  - **New ATTENDEES grid** replaces the attendee name-chips: Name / Role /
    Company / Email / Phone / Status. Names open the contact peek, companies
    the Account peek; email and phone carry per-cell ⧉ copy; the zone header
    offers **⧉ Copy grid** (TSV with headers — pastes into Excel/Sheets as
    columns) and **⧉ Copy emails** (comma-separated recipient list). Role
    derives from the open record (related contact → Client, co-mentor's
    contact → CBM); Status derives from the session (Held → Attended,
    No Show → Expected, else Invited) — per-person invited-vs-attended state
    is a pending CRM modeling ruling. §12.4's "Expected attendees" wording
    stays for No Shows. The table scrolls inside its card on narrow windows.
  - **Transcript zone (§12.5 lifted, feature-gated).** When the CRM gains the
    `sessionTranscription` field, the view renders it: attached → the text in
    its own scrolling allotment with **Find in transcript** (honest match
    count, first-match jump, text-node-safe highlighting); empty → "No
    transcript is attached… paste the meeting transcript into the Transcript
    box in Edit" (omitted for Cancelled/No Show per §12.4). The editor gains
    the Transcript box the same way — `/fields` serves it only when the CRM
    field exists, so a save can never send what the CRM must reject. Until
    the field lands, nothing renders (§12.5's no-stub rule stands).
  - Backend: `GET /sessions/{id}` now answers `attendeeDetails` (email/phone/
    company via the richer `sessionAttendees` read) and
    `transcriptFieldExists`; the transcript column is selected only when it
    exists (it will be the record's longest text — it never rides reads that
    don't render it).

### Fixed
- **The session view never showed Session Notes.** It read `s.notes`, but
  `GET /sessions/{id}` serves the raw CRM name `sessionNotes` (only the
  Overview feed maps to `notes`) — so the zone always fell to the empty
  copy. Verified rendering on the stubbed-API preview harness.

## [0.36.6] — 2026-07-12

### Added
- **Records grid (all three session tools):**
  - **Company column is a link** opening the standard aggregated
    company/client pop-up (the same peek the Overview uses: Account + the
    client/partnership/sponsorship profile). Sections the user's ACL can't
    read are now **omitted** — an unassigned user just sees the company
    information, with no permission noise (this also applies to the
    Overview's Company pop-up).
  - **Records open in a separate browser tab**: the name column is a real
    link (`?record=<id>` deep link, target=_blank), so several engagements
    can be worked simultaneously. The URL tracks the open record (refresh
    stays on it; Back to list clears it).
  - Column-header sorting already existed (click to toggle ▲/▼) — verified
    working; no change.

## [0.36.5] — 2026-07-12

### Fixed
- **`EspoClient.unrelate` used a URL form this EspoCRM rejects** (found live
  while unlinking Mindy Bower from the Agape engagement: the path-suffix
  DELETE 404'd; the documented body form succeeded). Now sends the id in the
  request body. This method backs the sessions attendee sync and the
  Communications "Not related — remove" unlink, both of which would have
  silently warn-logged on failure.

## [0.36.4] — 2026-07-12

### Fixed
- **A CBM member added from compose landed under "Other Contacts"** (Doug's
  report). A member reached via the personal address on their Mentor-typed
  Contact had no mentorProfileId in the lookup (the profile scan only ran
  for @cbmentors.org addresses), so the dialog fell back to a client-contact
  link. The lookup now also resolves the profile through its Contact link,
  and a CBM member is NEVER linked as a client contact — with no co-mentor
  path (partner/sponsor domains), their row shows a disabled "Will receive
  the email" instead.

## [0.36.3] — 2026-07-12

### Fixed
- **CBM members now get the "Add" checkbox in compose** (Doug's report: no
  checkbox for a CBM recipient). Two causes: the frontend skipped
  `@cbmentors.org` addresses entirely, and the CRM lookup only searched
  Contact email addresses while a member's work address lives on their
  MENTOR PROFILE (`cbmEmail`). The lookup now matches mentor profiles too,
  and a CBM member's row shows **"Add as CBM contact"** — on the mentor
  domain, checking it adds them as a co-mentor (the record's CBM-contact
  relationship), not a client contact. The server-side send guard still
  never blocks internal addresses.

## [0.36.2] — 2026-07-12

### Changed
- **Compose dialog redesigned to checkbox rows + one Send** (Doug's design):
  every non-record recipient gets an "Add to this record" checkbox (default
  on) — an existing CRM contact of ANY type (client, non-client, CBM member)
  shows who they are and links on Send; a new address shows the
  first/last/phone/company form (existing-Account picker or new company);
  unchecked rows send as a one-off (thread still followed, conversation
  still attached). A single Send click links/creates all checked rows, then
  sends. The compose/view modal is now a workspace-sized dialog
  (min(90rem, 94vw), 16rem message area) instead of a 40rem pop-up.

## [0.36.1] — 2026-07-12

### Changed
- **Compose dialog: CRM-wide lookup before offering to create a contact**
  (Doug's refinement of the non-contact recipient flow). Each unknown
  recipient's address is first searched across the whole CRM
  (`GET /{slug}/api/contactlookup`): an existing contact gets one button —
  "Add to this record & send" (links the existing contact; no duplicate) —
  and a CBM-member match short-circuits to "Send anyway". Only a
  genuinely-new address shows the create form, which now collects first/last
  **+ phone + company** — company picked from existing Accounts
  (`GET /{slug}/api/companies`) or typed as a new name (find-or-create via
  the intake API user, mirroring the intake orchestrators' policy;
  `ContactAddIn.newCompanyName`).

## [0.36.0] — 2026-07-11

### Changed
- **Staff tools: minor CRM rejections no longer stop a save, and what does
  fail speaks plain language — never a raw 502/504.** Two layers (extending
  the non-required-enums-never-block policy to Mentor Administration):
  1. **Mentor Administration saves sanitize enums server-side** (mirroring the
     sessions engine): an enum/multi-enum value the live CRM no longer offers
     is dropped before the write — the rest of the save proceeds, the drop is
     logged, and the save response carries plain-language `warnings` that the
     editor shows in a new amber "Saved, with a note:" notice. Fails open when
     options can't be fetched.
  2. **All three staff routers (mentoradmin / sessions / assignments) translate
     EspoCRM `validationFailure` 400s** into a readable 400 naming the field
     ("The CRM did not accept the save: 'How Did You Hear About CBM' has a
     value the CRM does not accept…") via the new `core.espo.validation_message`
     helper, instead of wrapping the raw CRM body in a 502 (which the edge
     showed as a 504). Genuine server faults still 502; expired sessions
     still 401.

## [0.35.2] — 2026-07-11

### Added / Fixed

*(also folds in the same-day activation fixes originally logged as a duplicate 0.35.1):*

- **Communications live-activation fixes** (found activating on crm-test —
  the CRM entities were built + probe-verified the same day):
  - `requests` was a missing dependency of google-auth's token transport
    (latent since v0.11.0 — first live Gmail call exposed it).
  - All varchar writes clamp to the as-built 100-char CRM fields (the first
    backfill 400'd on `snippet` maxLength, storing conversations but no
    messages); spec updated with as-built lengths.
  - Gmail **drafts are never ingested** (each draft revision is its own
    message — the source of a duplicated "Re:" pair and one never-sent
    "conversation"); SPAM/TRASH skipped too.
  - Quoted chains no longer leak into stored bodies: the "On … wrote:"
    header is matched even when line-wrapped, and `>`-prefixed quoting
    inside HTML bodies is truncated.
  - **Per Doug: `bodyCleaned` is now the author's NEW TEXT ONLY** — the
    demoted quoted-reply zone is no longer stored or rendered; a quote-only/
    image-only message stores a small placeholder instead of raw quoted text.
- **`GMAIL_RESYNC` one-shot ops lever**: set on the worker + deploy to clear
  every mailbox's sync cursor so the backfill re-runs idempotently; unset
  after one pass. Used twice during activation to re-drive dropped messages.

- **Non-contact recipients: the full design** (from Doug's scenario review —
  sending from a record to someone who isn't a record contact):
  - **Thread-following ingest** (correctness fix): a message now qualifies for
    ingest when it involves a record contact's address OR belongs to a Gmail
    thread that is already a stored conversation. Replies to any
    manually-established conversation (confirmed send, "Add emails…") keep
    arriving even when the correspondent is on no contact record — previously
    they were silently skipped.
  - **Durable attachment on confirmed sends**: a send confirmed to non-contact
    recipients now writes the same include override "Add emails…" writes, so
    a resync can never drop the conversation (the Sam-Smith-test lesson).
  - **Guided compose dialog**: instead of a bare "Send anyway", the compose
    modal now routes each non-contact recipient to the right fix — add the
    address to an existing contact (the durable fix; auto-resends as a normal
    matched send), create-and-link a new contact on the record, or an explicit
    one-off "Send anyway — attach this conversation only".
  - **CBM-internal recipients (`@cbmentors.org`) are never "unknown"** —
    emailing a co-mentor/staff about the record no longer trips the guard
    (their copy dedups by Message-ID when their own mailbox syncs).

## [0.35.1] — 2026-07-11

### Fixed
- **Mentor Administration: saving a mentor 400'd (surfaced as 502/504) after
  picking a "How they heard about CBM" value.** The CRM converted
  `CMentorProfile.howDidYouHearAboutCBM` from free-text to a real enum, but the
  editor still offered a hard-coded list from the free-text era (only "Other"
  was still valid), and the frontend prefers a field's static list over live
  options — so a picked value failed EspoCRM validation and blocked the whole
  save (hit live on prod saving Allen Ingram). The static `HOW_HEARD_OPTIONS`
  list is gone; the field's options are now pulled live from CRM metadata like
  every other enum (`service.field_options`), so the dropdown always offers
  exactly what the CRM accepts.

## [0.35.0] — 2026-07-10

### Added
- **Communications: the Gmail conversation integration is BUILT** (app side —
  per `prds/communications-gmail-integration.md`; gated OFF by `GMAIL_SYNC`
  until the CRM entities + Google scopes exist):
  - **Gmail access** (`core/gmail.py`): the existing Google service account
    with domain-wide delegation, extended to `gmail.readonly`/`gmail.send`,
    minting per-mailbox tokens. The impersonation subject is always derived
    server-side (the sync's enumerated managers; the signed-in user's own
    `cbmEmail` for search/send) — never from request input. Every access
    is logged.
  - **Email cleaning** (`core/email_clean.py`): the CRM_Extender pipeline
    ported (dual-track: quotequail + BeautifulSoup structural stripping with
    the tuned edge-case guards, mail-parser-reply + regex fallback), producing
    two-zone output — the author's new content, plus the quoted reply chain
    demoted into `<blockquote class="quoted-reply">`. Signatures, disclaimers,
    and boilerplate are deleted; the raw original stays in Gmail (deep links).
  - **Sync engine** (`comms/`): per-mailbox Gmail `historyId` incremental sync
    with expired-cursor date-window backfill and new-address targeted
    backfill; scope = ACTIVE records' contact addresses only; RFC Message-ID
    dedup across co-mentor mailboxes; conversation formation (thread id +
    cross-mailbox References merge); triage (no-reply/OOO/marketing mail is
    never stored); CRM upsert as `CConversation`/`CCommunication` linked to
    the engagement/partner/sponsor + contacts, owner-stamped via
    `assignedUsers`. Runs in the delivery worker on its own timer. State in
    Postgres (Alembic `0004_comms_sync`: cursors + curation overrides).
  - **Optional AI summaries** (`comms/summarize.py`, `COMMS_AI_SUMMARY`,
    default off): Claude summaries/status/action items per conversation via
    structured outputs, refreshed when new mail arrives; failures degrade to
    `Uncertain`. No Anthropic key or data egress when off.
  - **Endpoints** (per session-tool domain): conversation list + thread read
    (as the user, ACL-enforced), record-level exclude, mailbox search +
    include-thread, add-contact-address, and **send/reply as the manager's own
    @cbmentors.org address** (proper In-Reply-To/References threading, sent
    into their real Sent folder, written through immediately; recipients
    outside the record's contacts require an explicit confirm).
  - **Frontend**: the Communications tab now renders real conversations when
    enabled (status/participants/summary list → thread view with two-zone
    bodies, action-items callout, Open-in-Gmail links, reply/compose wired,
    "Not related — remove" and "Add emails…" curation). With the flag off it
    keeps the sample-data scaffold.
  - **CRM handoff spec**: `cconversation-entity.md` (entities, links, grants,
    layouts) — the CRM-side build is the activation prerequisite, along with
    authorizing the two Gmail scopes on the delegation grant.
  Verified: 25 new unit tests (cleaning corpus, sync engine with fakes,
  endpoint gating) — 342 total green — plus the full UI loop in the stubbed
  browser harness. NOT yet run against a real mailbox or CRM (blocked on the
  CRM entities + scope authorization).

## [0.34.1] — 2026-07-10

### Added
- **Session duration across the session tools.** `CSession.duration` is
  EspoCRM's *virtual* duration type — not stored, computed as
  `dateEnd − dateStart` (presets 5 min–3 hours, default 1 hour) — so the app
  writes `dateEnd` and displays the difference:
  - **Editor (session detail form):** a **Duration** select on the
    Status/Type/Start line, with the preset choices read live from CRM
    metadata (a stored non-preset value is offered as-is so it is never
    lost; new sessions default to 1 hour). On save the frontend recomputes
    and sends `dateEnd` whenever the start or the duration changed — moving
    the start keeps the duration; the virtual `duration` key never reaches
    the CRM (`SESSION_EDIT_NAMES` now excludes it and whitelists `dateEnd`).
  - **Engagement/record view:** the Sessions tab table gains a **Duration**
    column.
  - **Session summary cards** (Overview note feed): the duration is stamped
    next to the session date in the header band.
  - **Read-only session view:** a **Duration** entry in the key-value grid.
  Sessions without a `dateEnd` (recorded before this change) simply show no
  duration. Verified in the stubbed-API browser harness (cards/table/view
  render; update sends only `dateEnd`; create sends start + 1h; moving the
  start preserves the duration) — not yet driven against the live CRM.

## [0.34.0] — 2026-07-10

### Fixed
- **The portal now reviews ALL of a user's current teams — two causes fixed.**
  Reported as "when I log in, it only shows mentor admin, even though I am also
  on other teams."
  1. **Stale cached membership.** Teams/roles were captured into the signed
     session cookie at LOGIN time and never re-checked, so a team granted in
     the CRM after sign-in stayed invisible until a full sign-out/sign-in —
     and revisiting the portal "logs you in" silently from the cookie, so it
     looked like a fresh login was ignoring teams. `GET /api/portal/session`
     now **re-reads the user's teams, roles, and admin flag from the CRM**
     (as the user, via their token — `assignments.auth.refresh_membership`)
     on every session restore and re-saves the session, so the portal links
     AND the staff apps' per-request gates always see current membership.
     Best-effort on CRM blips (keeps cached values); an expired token now
     signs the user out (401) instead of serving stale entitlements.
     Verified live against crm-test (login → session restore → CRM re-read).
  2. **`ASSIGN_ALLOWED_TEAMS` defaulted to empty**, unlike every other gate —
     a deploy (or local run) that didn't set it hid Client Administration from
     every non-admin regardless of their teams. It now defaults to
     `Client Administration Team`, matching the real team name in both CRMs
     (an env override still wins).

## [0.33.3] — 2026-07-10

### Fixed
- **Website links open the actual site in a new tab.** The contact/company
  pop-up (peek) rendered a stored bare-domain website (`agapew8loss.com`) as a
  relative href, so clicking it tried to open
  `/mentorsessions/agapew8loss.com` on the app itself. All external-link
  renders in the sessions frontend now share one `externalHref()` helper
  (prepends `https://` when the stored value has no scheme; trims whitespace):
  the peek Website/LinkedIn fields, the Company card's directory link, the
  session view's video-meeting link, and the Next-session Start button. All
  open with `target="_blank"` + `noopener`.

## [0.33.2] — 2026-07-10

### Changed
- **Phone numbers display in the standard US format `(216)-555-1234`
  everywhere in the product.** One shared formatter serves every frontend
  (`frontend/shared/phone-format.js`, loaded by the sessions / Mentor
  Administration / Client Administration apps) with a Python twin
  (`core.phone.format_us`) for server-composed text. Applied to: the sessions
  Details tab (Client Contacts + CBM Contacts tables, the Company card's
  directory block), the contact/company pop-up peek (now a `tel:` link showing
  the formatted number), the peek's copy-to-clipboard contact card,
  `/mentoradmin`'s detail summary (its local formatter — previously
  `(216) 555-1234` — now delegates to the shared one), and `/assignments`'
  engagement contact panel. Display-only: the CRM keeps storing E.164, edit
  inputs and `tel:` hrefs keep the raw value, and anything that isn't a
  10-digit US number (international, extensions) renders as-is rather than
  being mangled.

## [0.33.1] — 2026-07-10

### Added
- **Sessions apps: distinct empty state when the login has no linked profile.**
  When `/records` returns `profileFound: false` (no `CMentorProfile` has the
  signed-in user as its Assigned User, so nothing can be scoped to them), the
  grid now explains that and says an administrator must link the user — instead
  of the domain's generic "No partners/sponsors/engagements found." The message
  ships in the `/session` config (`noProfileMessage`, `sessions/router.py`).
  Diagnosed live on crm-test: a hand-created "Partner Manager" profile managed
  3 partners but had no Assigned User, so `/partnersessions` looked empty with
  no hint why.

## [0.33.0] — 2026-07-10

### Changed
- **Details tab rebuilt to the approved mockup v4 layout**
  (`prds/Details Screen files2/`): top to bottom, single column —
  1. **Engagement summary strip** (replaces the Engagement panel): a slim labeled
     bar under the tab row — Status as a navy pill, then Started / Mentor / Cadence /
     Sessions and every other engagement field that carries information (long-form
     text stays on the Overview and in the edit form; empties and "No" omitted),
     with the strip's own **Edit** flipping it into the full engagement form.
  2. **Company** and **Client Business Profile** cards: a **two-column labeled row
     grid** (fixed small uppercase labels, composed bold values with light `|`
     separators) — Company leads with a directory block (name, billing address,
     phone · website) then Business / Shipping-when-different rows, with Account /
     Cadence / Announcements (red "Not allowed" badge) on the right; the profile
     composes Entity / Revenue / Sells / On-file rows with Certifications + Funding
     chips and the quoted Client goal. Any informative field the curated rows don't
     cover still renders as a generic labeled row (columns kept balanced); empty /
     false fields are hidden except operationally meaningful negatives.
  3. **Client Contacts** card: ALL related contacts in one true table — Name
     (muted salutation + navy bold), Role chips (contact type + title), Phone,
     Email, City, Contact via, and the three acceptance flags collapsed to **one
     Agreements badge** (green "Complete" / red "N pending"); empty cells stay
     empty. Per-row **Edit** expands the full contact form inline under the row.
  4. **CBM Contacts** card: the same table (no City/Agreements) for the CBM-side
     people, populated from the real CRM relations — the assigned mentor
     (`CEngagement.mentorProfile`) + co-mentors (`additionalMentors`), each
     resolved through the profile's linked Contact (`contactRecord`) for
     phone/email; verified live against crm-test, there is no other staff link on
     the engagement.
- No page-global Edit/Save/Cancel bar remains; every section (strip, card,
  contact row) edits independently with inline errors on failure.

### Added
- **+ Add contact flows** on both contact cards. Client side: a two-option menu —
  **Select existing contact…** (live search over CRM contacts as the signed-in
  user; picking one relates it via the domain's contacts link
  (`engagementContacts` / `contacts` / `sponsorContacts`) and backfills the
  contact's company affiliation (`Contact.account`) only when it has none) and
  **Create new contact…** (the full contact form; create + link is one compound
  operation, with the company stamped at create). CBM side: select an existing
  mentor profile (attached via `additionalMentors` — new CBM people are onboarded
  through Mentor Administration, so no create-new there). New endpoints:
  `GET /{slug}/api/contacts?q=` (picker search) and
  `POST /{slug}/api/records/{id}/contacts` (`contactId` to link, `changes` to
  create-and-link), both running as the user.
- **Grid columns rework (mentor list)** — carried in from the prior session
  (previously uncommitted): Next Session (friendly datetime) + Start Date columns
  inline, Company/Client moved right; `Column.type` drives date/datetime cells.
- **Communications tab email-inbox UI scaffold** — carried in from the prior
  session (previously uncommitted): an inbox grid + view/reply/compose modal,
  **frontend-only** (no CRM email data yet; the wiring contract is documented in
  CLAUDE.md); Overview CBM contacts now link to each co-mentor's Contact pop-up
  (`coMentors[].contactId`).

## [0.32.12] — 2026-07-10

### Changed
- **Details tab redesigned: per-panel editing + summary view (no field grids).**
  The single page-global Edit / Save / Cancel bar is gone; each panel — **Engagement**
  (new, shown first), **Company**, **Client Business Profile**, and each **Contact** —
  now carries its own **Edit** button that flips only that panel into a field-level
  form with its own **Save changes** / **Cancel** (saves write through per entity;
  on a 403/error the edit view stays open and the reason shows inline).
- **View mode composes fields into readable, directory-style blocks** instead of
  label/value grids: a **Contact** reads like a directory entry (salutation + name,
  preferred name in parens, address, phone, `mailto:` email; a secondary line for
  contact type / preferred method / notification, and the privacy/terms/code-of-conduct
  flags surfaced **only when not accepted**); **Company** reads letterhead-style
  (billing address block + phone + website, then a prose line composing
  organization type / stage / industry, account facts, and a shipping line only when
  it differs from billing); **Client Business Profile** as grouped structure/financial
  summary lines, the client's description quoted, with certifications and funding as
  badge rows; **Engagement** as a status-pill header + key dates / mentor / cadence /
  session count. Empty and false fields are hidden in view mode (except the three
  acceptance flags). Edit mode keeps the full field-level form.
- A new **Engagement** panel (mentor domain) / profile-first ordering (partner/sponsor)
  leads the Details tab; the engagement's mentor / assigned users / program are read
  as display-only extras alongside the editable scalar fields.

## [0.32.11] — 2026-07-10

### Added
- **Unsaved-changes guard on the session editor.** Clicking **Back** with unsaved
  edits (any field or the attendee set changed) now opens a dialog — **Save changes**
  (persists, then returns), **Discard** (drops them, returns), or **Keep editing** —
  so you don't have to go back and press Save separately. No prompt when nothing
  changed.

## [0.32.10] — 2026-07-10

### Changed
- **Session detail View redesigned to Display Standard §12.** The page title +
  metadata strip become a **summary header card** — tinted band (per-status, reusing
  the summary card's band/chip tokens) with the humanized date, status & type chips,
  and the engagement line, over an auto-fit **key-value grid** (meeting type,
  location, video link, next session, attendees). **Session Notes** render as a
  full-width reading block (no clamp); **Action items / next steps** as the gold
  callout. Per-status variants per §12.4 (No Show → "Expected attendees", omitted
  action-items/transcript boxes rather than empty ones). The Back / ‹ N of M › /
  Edit navigation row is unchanged. Auto-generated session titles never appear.
- **Transcript zone omitted (§12.5):** `CSession` has no transcript long-text field
  yet (documented as unbuilt `sessionTranscription`), so the transcript section is
  not rendered — no stub — until the CRM field lands.

## [0.32.9] — 2026-07-09

### Changed
- **Next session** panel date now matches the session-summary format —
  "Mon, July 14 — 4:00 PM" (abbreviated weekday), with the year rule and an ISO
  hover tooltip.

## [0.32.7] — 2026-07-09

### Changed
- **Overview "Session notes" — Session Summary Display Standard (v0.2).** Each
  session renders as a two-zone card: a tinted **header band** (pale blue for a
  Scheduled *future* session, neutral gray for past/Completed/Cancelled/No Show)
  carrying the date, type & status chips, and View/Edit; and a body with an
  **attendees** column beside the notes (clamped to 4 lines) with the gold
  **Next steps** callout. Status chips: Scheduled (blue) / Completed (green) /
  Cancelled (gray) / No Show (red) — state is never color-only. Dates read
  "Weekday, Month D — h:mm AM/PM" (year omitted in the current year; ISO in the
  hover tooltip). The feed groups **Upcoming** (soonest first) then **Past** (most
  recent first), with labels when a group has 3+. A Scheduled session shows
  "Scheduled — notes are recorded when the session is held." instead of "no notes."
- New sessions default to status **Scheduled** (the CRM's Scheduled/Completed/
  Cancelled/No Show vocabulary).

## [0.32.6] — 2026-07-09

### Changed
- **Mentor grid shows all engagement statuses** (was restricted to active/pending)
  so the Status filter can offer every status; the user narrows as they like.
- **Compact header:** "Signed in as …" + Sign out moved to the upper-right corner;
  Refresh moved into the filter row — reclaiming a full toolbar row of height.

## [0.32.5] — 2026-07-09

### Added
- **Records grid: filter, sort, and richer columns.** A **Status** filter (the
  statuses present in the grid); **click any column header to sort** (toggles
  asc/desc, arrow indicator); alternating row shading for readability. The
  **Created** column is now **Start Date** (the engagement/partnership start date).
- **Primary contact is a link** — clicking it opens the contact pop-up with the
  email as a `mailto:` link (opens the user's mail client) and a combined address.
- **Copy contact details.** The contact pop-up has a **⧉ Copy** button (top-right)
  that copies a paste-ready block — name, full address, email, phone — to the
  clipboard. `service.peek` returns a `copyText` card + a combined Address field
  for contacts; `get_session`/grid rows carry the needed ids.

## [0.32.4] — 2026-07-09

### Added
- **Read-only Session view.** Clicking a session's name (in the Overview note feed
  or the Sessions tab) or its **View** button opens a view-optimized page showing
  the whole session at a glance — a compact facts grid (status, type, start,
  meeting type, location, video link, next session, topics, **attendees**) plus the
  prominent Session notes / Action items blocks. **‹ / ›** buttons (and ← / →
  keys) walk to the previous / next session so a user can quickly page through the
  record's sessions; **Edit** jumps to the editor. `get_session` now returns
  `attendeeNames` for display.

## [0.32.3] — 2026-07-09

### Changed
- **Session editor layout.** The two most important fields — **Session notes** and
  **Action items / next steps** — are now large, prominent editors side by side
  (stacked on narrow screens). Removed the meeting **End** date; **Status /
  Session type / Start** now share one line. Tighter, more efficient use of space.

## [0.32.2] — 2026-07-09

### Fixed
- **Details tab respects the user's edit permission** — reads the ACL and, for an
  `edit: own` role, checks per-record ownership; sections you can't edit are
  read-only (no doomed edit → 403). Save is per-entity with a plain-language
  permission message.
- **Attendees now read and write correctly.** `sessionAttendees` is a CRM
  *relationship*, not a select-field: reads go through the link (`list_related`,
  like co-mentors) — reading `sessionAttendeesIds` off the record always returned
  empty, which is why attendees never displayed and edits looked lost. Writes sync
  via the relationship endpoints (relate added / unrelate removed). Both the
  session editor and the Overview note feed use the link read.
- **Friendlier empty grid** — "No client engagements / partners / sponsors found"
  instead of the "ask an administrator to link your profile" error.

### Changed
- **Next session** panel: dropped the session name/type line; added a button that
  opens the upcoming session for editing — **Start Session** (also launches the
  call) when it has a video link, else **Open Session**.

## [0.32.0] — 2026-07-09

### Changed
- **Session Management — redesigned record detail into a tabbed, information-
  dense view.** Opening an engagement / partner / sponsor now shows a tab bar
  common to all three domains: **Overview · Details · Sessions · Communications ·
  Documents** (`/session` → `detailTabs`). Phase-one delivery builds **Overview**,
  **Details**, and **Sessions**; **Communications** (email/SMS threads) and
  **Documents** (uploads) ship as placeholders.
- **Details tab** — a **read-optimized** view of the org records behind a record
  (the company Account, the client/partnership/sponsor profile, and each related
  contact), with an **Edit** button that flips the whole page into a field editor
  (Save / Cancel). Fields are read **live from CRM metadata** (filtered to the
  editable scalar fields, humanized labels) so it tracks the schema; the read view
  hides empties for scannability, the edit view exposes every editable field.
  Enum/multiEnum drift is dropped on save (per the non-required-enum policy);
  each changed entity is saved with its own `PUT` as the logged-in user (ACL
  enforced). New endpoints `GET/PUT /{slug}/api/details/…` (`sessions/details.py`).
- **Overview tab** — a full-width, review-oriented screen:
  - **Facts rail** (left, resizable via a drag splitter): key identity (status
    badge, a single aggregated **Company** link, primary contact, meeting
    cadence, referring partner), session activity (start/last/next counts, focus
    areas), **Other contacts** + **CBM Contacts**, and the mentoring need.
  - The **Company** link aggregates the company Account **and** its profile
    (client business / partnership / sponsor) into one pop-up; contact/referring-
    partner links open their own pop-up (read-only `/{slug}/api/peek`, entity
    allowlisted, ACL-enforced).
  - **Overall notes** (Engagement / Partner / Sponsor Notes) above an aggregated
    **session-notes feed** — every session's notes + next steps, most-recent
    first, each stamped with date/time and its **attendees**.
  - A bold **Next session** callout (soonest upcoming session, derived from the
    records).
- Detail tabs are built from config; the standalone Contacts tab folds into
  Overview (Other/CBM Contacts) and the forthcoming Details tab.

## [0.31.0] — 2026-07-09

### Added
- **Session Management tools** — three staff-only, team-gated routes
  (`/mentorsessions`, `/partnersessions`, `/sponsorsessions`) from one
  configurable engine. Each manager (mentor / partner manager / sponsor manager)
  reviews the records they own (engagements / managed partners / managed
  sponsors), opens one to a read-only detail (parent + related contacts +
  existing sessions), and creates/edits **`CSession`** meetings (notes, next
  steps, attendees, status). Mentors can also attach co-mentors. It's one
  `CSession` entity with the parent link swapped, driven by a per-domain
  `DomainConfig`; reuses the portal SSO, per-request team gate, per-user
  EspoClient, and the type-driven field editor. New settings:
  `SESSION_{MENTOR,PARTNER,SPONSOR}_ALLOWED_TEAMS`. Phase 1 (CRUD); Google
  Calendar/Meet + transcription are later phases. On branch, not yet deployed.

### Fixed
- **Sessions are stamped with their creator** (`assignedUser`/`assignedUsers`)
  on create, so a role whose `CSession` scope is read-own can see the session it
  just made.
- **Enum drift can't 400 a session save.** The editor sends only changed fields
  (diffed against a render-time snapshot), and the service drops enum/multiEnum
  values not in the live CRM options before create/update (fails open) — so a
  stored value that has drifted out of its field's options no longer fails the
  whole save.
- **Required fields are enforced in the editor**, read live from CRM metadata
  (e.g. `CSession.dateStart`): required fields show a `*` and Save is blocked
  with a readable message instead of surfacing a raw CRM `validationFailure`.
- **Session name is pre-filled and the user's value wins.** The New Session
  editor pre-fills a default title (`YYYY-MM-DD - <parent name>`) so the user
  sees what will be stored; create now sends the name verbatim. Pairs with the
  CRM name formula being set to keep any value already present (else it would
  overwrite the app's name).

### Changed
- App log lines are timestamped — `LEVEL: YYYY-MM-DD HH:MM - message` — so run
  logs show when each event (session create, CRM error) happened.

### Notes
- Mentor domain driven live end-to-end on crm-test. CRM prerequisites to run
  the tool (per CLAUDE.md): create the Partner/Sponsor Management Teams, grant
  the gate roles CSession create + read-own/edit-own, enable `assignedUsers`
  (collaborators) on `CSession` (so read-own credits the creator — otherwise
  create 403s and sessions are invisible), and make the `CSession` name formula
  keep-if-present.

## [0.30.1] — 2026-07-07

### Changed
- Portal home page: section labels (Applications / CRM / Public intake forms)
  are larger (1.45rem serif with an underline rule) and the links beneath them
  render in the standard link blue — headings and links are now clearly
  distinct.

## [0.30.0] — 2026-07-07

### Added
- **Authenticated portal at `/` with single sign-on for all apps.** The root
  page (on deployments with the staff stack, i.e. `SESSION_SECRET` set) is now
  a CRM login; after signing in, the user sees exactly the links their EspoCRM
  **teams** entitle them to: every signed-in user gets the five public
  intake-form links; **Mentor Team** adds a link to the CRM itself; **Client
  Administration Team** → `/assignments/`; **Mentor Administration Team** →
  `/mentoradmin/`; **Marketing Admin Team** → `/ops/` (**Submission Admin** —
  retitled from "Submission Operations"). CRM admins see everything. New
  `portal/` package (`/api/portal/login|session|logout` + the page); the login
  is **ungated** (any active internal user) — the portal listing is a
  convenience, never the security boundary.

### Changed
- **One login, no second prompts.** All staff apps now share one session
  (sign in once at the portal) and enforce their team gates **per request**
  instead of at login: 401 sends the browser to `/?next=<app>` (and back after
  login); 403 shows exactly which team is required. The per-app login
  screens/endpoints are gone; per-user CRM access (ACL, audit) is unchanged —
  every call still runs under the signed-in user's own token.
- `/ops` is now gated by its own `OPS_ALLOWED_TEAMS` (default **"Marketing
  Admin Team"** — the team must be created in the CRM) instead of sharing the
  assignments gate.
- The public form index at `/` remains only on deployments without the staff
  stack (the dry-run dev app); the forms themselves stay public everywhere by
  direct URL.

## [0.29.0] — 2026-07-07

### Added
- The `/mentoradmin` detail editor gains a **Contact tab** to view and edit the
  mentor's contact information — first/last name, email, phone, and street /
  city / state / ZIP. These fields live on the mentor's linked **Contact**
  record (the profile only mirrors them read-only in the summary card), so the
  save routes them to the Contact while profile fields keep writing to
  `CMentorProfile`. Phone is normalized to E.164 at the CRM boundary (EspoCRM
  rejects other formats). Saving contact fields on a mentor with **no linked
  Contact** fails fast — before anything is written — with a clear message
  (400), instead of half-saving.

## [0.28.0] — 2026-07-07

### Added
- The `/assignments` engagement **status filter now has an "All" option** at the
  top of the dropdown — one click selects (or clears) every status. It shows a
  checked/indeterminate state as individual statuses are toggled, and the
  summary reads "Status: All" when everything is selected.

## [0.27.4] — 2026-07-07

### Fixed
- The `/mentoradmin` **mentor detail summary card now shows the same five
  client counts as the roster grid** (Active clients · Max clients · Available ·
  Assigned (30d) · Lifetime clients), computed from CEngagement via the shared
  `client_counts_for` helper — attached to the detail response as
  `clientCounts` (a save refreshes it, since the save returns through the same
  read). Previously the card showed the CRM's computed
  `currentActiveClients`/`availableCapacity` (known-buggy formula) and omitted
  any null value, so counts were wrong, incomplete, or vanished entirely. The
  five counts are always rendered ("—" when unknown); the CRM-computed fields
  are no longer read.

## [0.27.3] — 2026-07-07

### Fixed
- The mentor-type filter in both staff mentor grids now offers **every**
  `mentorType` enum value (Mentor, Co-Mentor Only, Subject Matter Expert,
  Presenter, Volunteer, Other) — previously it listed only the types present in
  the loaded roster, so types with no current mentor couldn't be selected. The
  roster response carries the live CRM enum (`mentorTypeOptions`, best-effort);
  the frontend unions it with any stored value the enum no longer declares.

## [0.27.2] — 2026-07-06

### Changed
- Client-count column order in both staff mentor grids is now **Active Clients ·
  Max Clients · Available · Assigned (30d) · Lifetime** (Available moved before
  Assigned (30d)).

## [0.27.1] — 2026-07-06

### Changed
- Numeric columns in both staff mentor grids (the five client-count columns)
  are now **centered** under their headings (were right-aligned).

## [0.27.0] — 2026-07-06

### Added (both staff mentor grids)
- **Mentor client-count analytics** in the `/mentoradmin` roster and the
  `/assignments` "Review Mentors" grid — five columns, all sortable:
  **Active Clients** (engagements with status Active / Assigned / Pending
  Acceptance), **Max Clients** (the stored `maximumClientCapacity`),
  **Assigned (30d)** (active-set engagements whose `engagementAssignedDate` is
  within the last 30 days), **Available** (Max − Active, app-computed), and
  **Lifetime** (every engagement ever linked to the mentor, any status).
  Counts are computed by the app from `CEngagement` in one paginated sweep
  (grouped by `mentorProfile`) — the CRM's own computed
  `currentActiveClients`/`availableCapacity` fields are no longer read (the
  crm-test formula computes 1 for every mentor). The "Has capacity" filter and
  the assign dropdown's "(capacity N)" label use the same computed Available,
  so the grid and eligibility can't disagree.
- The **Assign action now stamps `CEngagement.engagementAssignedDate`** (UTC
  now) alongside mentor + Pending Acceptance — nothing CRM-side fills it, and
  the Assigned-(30d) count depends on it. Engagements assigned before 0.27.0
  have no date and won't count until backfilled CRM-side.

### Changed
- `GET /assignments/api/mentors` and `GET /mentoradmin/api/mentors` responses
  gained `metricsAvailable`. If the logged-in staffer's EspoCRM role can't read
  `CEngagement`, the roster still loads with blank count columns and the count
  line says so (grant CEngagement read to the staff Teams' role to fix).

## [0.26.0] — 2026-07-06

### Added (Mentor Administration `/mentoradmin`)
- **"Update Mentor Status"** — a roster-toolbar action that sweeps every mentor
  and reports, per mentor: does the linked EspoCRM **login User actually exist**
  (a dangling link to a deleted User, a deactivated User, and "no User linked"
  are all distinguished) and does the **@cbmentors.org mailbox exist** in Google
  Workspace. The sweep also recomputes completeness and **re-syncs the stored
  Record status** for every mentor (same write rules as the detail view — only
  on change, never over a manual Duplicate), so the whole grid self-heals in one
  click. Results shown in a wide modal table; the roster reloads after.
  Endpoint: `POST /mentoradmin/api/mentors/status-check` (staff session
  required). User reads run as the provisioning admin service account when
  configured (regular staff can't read Users — reported "could not verify"
  instead of failing). The mailbox column reports **"n/a — check not
  configured"** until the Google Directory integration is connected in Email
  Setup; nothing fails when it's absent.

## [0.25.2] — 2026-07-06

### Fixed
- **Partner form failed for anyone choosing partnership type "other".** The CRM's
  `partnershipType` enum gained a (lowercase) `"other"` value; the options sync
  correctly put it in the form dropdown, but the Pydantic schema still hard-coded
  the original six values as a `Literal`, so picking it 422'd the whole submission
  — shown to the user as the generic "Please check your entries and try again."
  All schema fields whose dropdowns are CRM-synced are now free strings
  (partner `partnership_type`; client-intake `business_stage`/
  `meeting_preference`/`notification_preference`; volunteer `contact_preference`/
  `currently_employed`) — the orchestrators already sanitize each against the
  live CRM enum, which is the single source of truth. A future CRM enum change
  can no longer break a form.
- **Follow-up (same day):** the CRM entry was corrected to Title-case **`Other`**
  on both CRMs; the partner dropdown was re-synced (`sync_form_options.py --write`).
  Prod parity checked read-only: all 16 managed lists match prod except a harmless
  ordering difference in volunteer how-did-you-hear (same values). Volunteer
  `phone_type` (static list, no CRM target) was loosened to a free string too —
  policy: **a non-required field must never block a submission over an
  unrecognized enumerated value.**
- **Error messages now state the exact reason — never generic.** Validation
  failures return a human-readable `detail` string naming each failing field and
  why (structured list preserved under `errors`), and are logged at WARNING so
  they're visible in the run logs. The shared wizard and the client-intake form
  display the server's reason verbatim; the only remaining fallback (a bodyless
  response) names the HTTP status.

## [0.25.1] — 2026-07-06

### Changed
- **Landing page shows each entry's shortcut path.** Every form and staff-tool
  link on `GET /` now displays its normalized alias (e.g. `/clientintake`,
  `/mentoradmin`) in a small code chip, so nobody has to remember where the
  dashes or capitals go.

## [0.25.0] — 2026-07-06

### Added
- **Friendly URL aliases.** A single-segment path is normalized (lowercase,
  alphanumerics only) and redirected (307) to the matching form or staff tool —
  so `/clientintake`, `/ClientIntake`, `/client_intake` all land directly on
  `/client-intake/` without showing the index. Works for all five forms and
  (when the staff tools are mounted) `/assignments`, `/ops`, `/mentoradmin`.
  Unknown paths still 404. Built for the upcoming
  `apps.clevelandbusinessmentors.org` custom domain, but live on every deploy.

## [0.24.1] — 2026-07-06

### Fixed
- **Volunteer consent now sets `CMentorProfile.ethicsAgreementAccepted`.** The
  mentor-intake consent checkbox set `termsAccepted` + `mentorCodeAccepted` (and the
  three Contact bools) but NOT the ethics flag `/mentoradmin`'s completeness rule
  requires — so every form-submitted mentor started with an "ethics agreement"
  completeness gap staff had to tick manually. Verified live on crm-test (left
  `ZZTEST-ETHICS LiveCheck` Contact `6a4b2bc43a7dd4681` + CMentorProfile
  `6a4b2bc4c3c1f0d55` to clean up in the UI).

### Changed
- **Mentor code-of-conduct link.** On the volunteer (mentor intake) form, the
  consent checkbox's "Code of Conduct" now links to the mentor code of ethics —
  `https://clevelandbusinessmentors.org/mentor-code-of-ethics/`. The other forms'
  Code of Conduct keeps pointing at the client code (`frontend/shared/legal-links.js`).
- **Mentor Administration: "Mentoring skills" editor removed** from the Bio tab
  (dropped from `EDITABLE_FIELDS`, so it also leaves the server-side update
  whitelist; the CRM field itself is untouched).

## [0.24.0] — 2026-07-05

### Changed (Client Administration `/assignments` — Available Mentors)
- **Focus Areas column removed** from the mentor grid (the engagement's focus areas
  are still shown in the engagement detail popup — that's a client-request field,
  not a mentor attribute).
- **Industry column now shows `CMentorProfile.industryExperience`** (the multi-value
  field the volunteer form writes) instead of the legacy single `industrySector`;
  rendered as chips, header "Industry Experience", sortable.
- **Filters reworked:** the "All industries" (industrySector) and "All focus areas"
  filters are replaced by **Industry Experience** and **Areas of Expertise** filters
  (each matches any of the mentor's values). Search now covers name, type, industry
  experience, and expertise.
- **Capacity column shows the stored value.** It now displays
  `maximumClientCapacity` exactly as on the CRM record (blank = "—"), instead of the
  CRM-computed `availableCapacity` (which showed "Unlimited" for −1 and drifted from
  what staff saw on the record). The "Has capacity" checkbox and the assign
  dropdown's "(capacity N)" label still use the computed available capacity, since
  those express eligibility to take a new client.
- **Available Mentors opens much wider** — the dialog defaults to ~96% of the window
  (the engagement detail popup keeps its previous sizing; both remain drag-resizable).

## [0.23.1] — 2026-07-02

### Changed (Mentor Administration `/mentoradmin` — completeness)
- **`publicProfile` no longer affects completeness.** Removed the publicProfile-gated
  checks (About-the-mentor text + area of expertise) from the completeness rule
  (server + frontend pre-save modal + docs). The Public-profile checkbox stays an
  editable field on the Status tab; it just no longer drives Complete/Incomplete.
- **Background check is optional.** Removed `backgroundCheckCompleted` from the
  required sign-off flags, so a mentor is no longer flagged Incomplete for a missing
  background check. The field (and its date) remain editable on the Compliance tab.
- Completeness now requires: a linked Contact + ethics/training/terms; plus, if
  Active, a CBM email and matching User on the member and its Contact.

## [0.23.0] — 2026-07-02

### Changed (Client Administration `/assignments`)
- **Engagements that already have a mentor no longer show the picker.** The grid's
  "Assign to mentor" column now shows the **assigned mentor's name** for any
  engagement that already has one (`CEngagement.mentorProfile`), instead of the
  Select-a-Mentor dropdown + Assign button. The picker/button appear **only** when
  no mentor is assigned. So filtering to Active (or any status whose engagements are
  already assigned) shows the mentor, not a redundant assign control. `list_engagements`
  now returns `mentorId`/`mentorName`; after an assign the grid reloads and the row
  flips to showing the name.

## [0.22.3] — 2026-07-02

### Changed (Mentor Administration `/mentoradmin`)
- **Mentor Email in the roster is now a `mailto:` link** — clicking it opens the
  staffer's email client addressed to the mentor's CBM email. Blank emails still
  render as "—".

## [0.22.2] — 2026-07-02

### Changed (Mentor Administration `/mentoradmin`)
- **Removed Industry sector from the mentor admin app.** Dropped the Industry column
  and industry filter from the roster grid and the Industry-sector field from the
  Expertise detail tab. (`industrySector` is unchanged in the Client Administration
  tool, which still uses it.)
- **Roster grid gained Mentor Email + Type.** New columns: **Mentor Email** (the CBM
  `@cbmentors.org` login address, `cbmEmail`) and **Type** (`mentorType`), with a
  matching mentor-type filter replacing the old industry filter. Column order is now
  Mentor · Mentor Email · Record · Status · Type · Created · Assigned · Capacity.
- **Completeness: dropped the industry-sector requirement.** A public-profile mentor
  no longer needs an Industry sector to count as Complete (still requires About text +
  ≥1 area of expertise), consistent with removing the field. Server, frontend mirror,
  and docs updated.

## [0.22.1] — 2026-07-02

### Fixed (Mentor Administration `/mentoradmin`)
- **Roster "Record" column no longer goes stale vs. the detail badge.** The grid
  reads the stored `recordStatus`, which was only written on Save; a record made
  complete outside a save-through-this-tool (e.g. the v0.11.2 login-link fix) stayed
  Incomplete in the grid while the detail page computed Complete (reported for prod's
  Douglas Bower). The detail GET now **persists the recomputed status on view** when
  it changed (`sync_record_status`, still a no-op when unchanged and still preserving a
  manual `Duplicate`), so the stored value self-heals; the frontend reloads the roster
  on return when the status changed.

## [0.22.0] — 2026-07-02

### Changed (Mentor Administration `/mentoradmin`)
- **Expertise tab now edits `industryExperience` instead of `mentoringFocusAreas`.**
  The mentoring-focus-areas multi-select was replaced by an Industry experience
  multi-select (the field the mentor intake form now writes). Auto-propagates to the
  detail-select, update whitelist, and live enum-options.
- **Status tab gained a mentor-pause window.** `mentorPauseStartDate` +
  `mentorPauseEndDate` (date) render on their own line directly beneath the
  Status/Type selectors (which now share a row).
- **"Back to list" warns on unsaved edits.** Leaving the detail view with changed,
  unsaved fields now pops a styled "Discard unsaved changes?" modal listing the
  changed fields ("Keep editing" / "Discard changes"). A clean save re-baselines the
  snapshots, so no false warning after saving.
- **Completeness rule: dropped the mentoring-focus-area requirement.** A public-profile
  mentor no longer needs ≥1 mentoring focus area to count as Complete (still requires
  About text + ≥1 area of expertise + an industry sector) — keeps the rule satisfiable
  now that focus areas aren't editable here. Updated server, frontend mirror, and docs.

## [0.21.3] — 2026-07-01

### Fixed
- **Volunteer/mentor form now records "How did you hear" on the Contact too.** It
  was written only to `CMentorProfile.howDidYouHearAboutCBM`, so the person's
  Contact ("client") record showed a blank "How did you hear" while the other three
  forms populate `Contact.cHowDidYouHear`. The volunteer orchestrator now also writes
  `Contact.cHowDidYouHear` (sanitized against the Contact enum, added to the null-fill
  keys) alongside the existing profile field. Not enum drift — the form's dropdown
  values match both fields verbatim on crm-test and prod. Existing records are not
  backfilled; a repeat submission from the same email null-fills the blank Contact field.

## [0.21.2] — 2026-07-01

### Changed
- **Three mentor-form fields are now required on the form:** "How should we contact
  you?", "Are you currently employed?", and "How did you hear about Cleveland Business
  Mentoring?" — each `<select>` got the `required` attribute + a required-asterisk
  label, so the wizard's `checkValidity()` blocks the step until they're chosen
  (required in the form regardless of the CRM's own optionality). Frontend-level
  enforcement; the schema still accepts them as optional for a direct API call.

## [0.21.1] — 2026-06-30

### Fixed (code-review cleanups — no behavior change)
- **Corrected the stale field-coverage docstring** in `client_intake/orchestrator.py`
  (it claimed marketing-consent / how-heard / year-formed / # employees / meeting +
  notification preference / terms were "NOT DEPLOYED / omitted" — they're all written
  now; only industry-subsector + applicant-since remain deferred).
- **Aligned the volunteer how-did-you-hear dropdown to its write target.** It was
  synced to `Contact.cHowDidYouHear` but written to
  `CMentorProfile.howDidYouHearAboutCBM` — identical options today, but two separate
  enums that could drift and silently drop the value. The form now syncs to the field
  it actually writes.
- Fixed a stale `# varchar` comment on `P_HOW_HEARD` (it's an enum, sanitized).

## [0.21.0] — 2026-06-30

### Changed (field-mapping — mentor areas of expertise)
- **Volunteer "Areas of Expertise" now maps to the skills field.** It previously
  wrote 42 *industry* values to `CMentorProfile.mentoringFocusAreas` — redundant with
  the "Industry Experience" question (which maps to `industryExperience`). It now
  writes to the purpose-named **`CMentorProfile.areaOfExpertise`** (31 *skill* values:
  Business Strategy, Digital Marketing, Leadership, Sales, Strategic Planning, …),
  giving a clean split: Industry Experience = industries, Areas of Expertise = skills.
  The form dropdown is re-synced to that field; `areaOfExpertise` is identical on both
  CRMs (31 values). `mentoringFocusAreas` is no longer set by the volunteer form (it
  remains the client-engagement field on CEngagement). Live-verified on crm-test.
  (Revises the earlier Pass B decision to keep it on `mentoringFocusAreas`.)

## [0.20.0] — 2026-06-30

### Changed (form keyboard UX)
- **Cursor starts in the first field, and Tab moves field-to-field.** Every form now
  focuses the first data-entry control of the active step on load (and when moving
  between steps). The consent policy links (Code of Conduct / Terms / Privacy) are
  pulled out of the tab order (`tabindex=-1`, still mouse-clickable) so tabbing flows
  between data fields. Labels were never tabbable; the nav buttons (Back/Next/Submit)
  stay tabbable so keyboard users can still reach them. Implemented in the shared
  `wizard.js` (covers volunteer/info-request/partner/sponsor) and in
  `client_intake/app.js` (it has its own wizard), plus `legal-links.js`. Verified
  in-browser across all five forms.

## [0.19.0] — 2026-06-30

### Changed
- **Environment indicator moved from the corner badge into the footer.** Instead of
  the colored top-right tag, the deploy environment now appears as the server name
  right after the version, e.g. `v0.19.0 (Production)` / `(Test)` / `(Dev)`. Applies
  to both the forms (shared `footer.js`) and the server-rendered landing page; the
  `.cbm-env-badge` styles and the index badge HTML were removed.

## [0.18.0] — 2026-06-30

### Added (field-mapping — meeting preference; mapping effort COMPLETE)
- **Client-intake "Meeting preference" now stores** to `Contact.cMeetingPreference`
  (`Video`/`Phone`/`Email`/`In Person`/`No Preference`) — the field was reconciled to
  an identical, typo-free option set on both CRMs, the form dropdown is CRM-backed and
  re-synced, and the orchestrator writes it via the sanitizer with null-fill.
  Live-verified on crm-test (`In Person` stored; works on prod, same options).
- **This completes the field-mapping effort** (`field-mapping-completion-plan.md`):
  every input collected across all five forms now maps to its intended CRM field. No
  collected field is silently dropped anymore.

## [0.17.0] — 2026-06-30

### Added (field-mapping — notification preference)
- **Client-intake "Notification preference" now stores.** The CRM team added
  `Contact.cNotificationPreference` (enum: `Email`/`Text`) on both CRMs, so the form
  value now writes there (was collected but dropped). The form dropdown is CRM-backed
  and re-synced (`Text Message` → `Text` to match the enum). Live-verified on crm-test;
  works on prod (same field/options). **Meeting preference** (`cMeetingPreference`)
  also now exists but is **not yet mapped** — its CRM options need a cleanup first
  (a `No Preferrence` typo on both CRMs + an `In Person`/`In-Person` divergence
  between them); tracked in `crm-field-handoff.md`.

## [0.16.0] — 2026-06-30

### Added (field-mapping — consent on partner & sponsor)
- **Partner & sponsor forms now collect consent.** Both gained the same single
  required consent checkbox ("I have read and agree to the Code of Conduct, Terms of
  Use, and Privacy Policy", with the policies linkified via `shared/legal-links.js`)
  on their final step. On submit it sets the three Contact bools
  `cTermsOfUseAccepted` + `cPrivacyPolicyAccepted` + `cCodeOfConductAccepted` (like
  client-intake). Submission is gated on it (schema `model_validator`). This
  **completes the consent model across all four forms.** Live-verified on crm-test
  (both forms wrote all three bools) and the checkbox + policy links confirmed
  rendering in the browser. 209 tests green (2 new).

## [0.15.0] — 2026-06-30

### Added (field-mapping — consent capture)
- **The single consent checkbox now records all three acceptances in the CRM.** The
  forms' one checkbox ("I have read and agree to the Code of Conduct, Terms of Use,
  and Privacy Policy") now sets all three Contact bools — `cTermsOfUseAccepted`,
  `cPrivacyPolicyAccepted`, `cCodeOfConductAccepted` — on **client-intake** and
  **volunteer**, plus `CMentorProfile.mentorCodeAccepted` (the mentor-specific
  code-of-conduct) for volunteers. All four bools exist on both CRMs (crm-test +
  prod, verified), so this works on production immediately. Live-verified on crm-test.
  (Consent capture for **partner & sponsor** is pending — those forms need the
  checkbox added; tracked as the next step.)

## [0.14.0] — 2026-06-30

### Changed (field-mapping — mentor industry experience)
- **Mentor "Industry Experience" now captures ALL selections.** The multi-select
  (up to 6) previously stored only the **first** pick into the single-enum
  `CMentorProfile.industrySector`; it now writes every selection to the multiEnum
  **`CMentorProfile.industryExperience`**. The CRM team made that field a multiEnum
  with a canonical 28-value list on both CRMs (crm-test + prod, verified identical),
  so this works on production immediately. The volunteer form's industry dropdown is
  re-synced to that field (28 CBM industry values, replacing the 20 NAICS sectors).
  Live-verified on crm-test (a 3-industry submission stored all three). `industrySector`
  is no longer written for mentors.

## [0.13.0] — 2026-06-30

### Added (field-mapping completion — Pass A)
- **More collected fields now land on the CRM.** Previously-dropped inputs are
  written to the fields the business intends (see `field-mapping-completion-plan.md`):
  - **client-intake** → Contact `cHowDidYouHear` / `cMarketingOptIn` /
    `cTermsOfUseAccepted`; CClientProfile `numberOfEmployees` and `formationDate`
    (the form's year → `YYYY-01-01`).
  - **volunteer** → Contact `cPreferredContactMethod` (from "how should we contact
    you") and `cEmploymentStatus` (from "are you employed").
  - **partner** + **sponsor** → Contact `cHowDidYouHear`.
  The how-did-you-hear / contact-method / employment dropdowns are now **CRM-backed**
  (synced from the live Contact enums via `scripts/sync_form_options.py`) so a value
  outside the enum is dropped by the sanitizer rather than 400-ing the create.
- **Repeat submitters backfill empty fields without clobbering.** New
  `core/crm_upsert.find_create_or_fill`: a Contact matched by email is reused and
  only its **null/empty** fields are filled — a value the CRM already holds (or a
  staffer curated) is never overwritten. Replaces the old "matched → reuse as-is".
  Verified live against crm-test (a second submission backfilled a null phone while
  leaving the existing how-heard untouched).

All four orchestrators share one `EnumSanitizer` across the Contact + profile
steps. 207 tests green (8 new). Live-verified end-to-end on crm-test; ZZTEST-PASSA
records left for UI cleanup (ids in the commit/chat).

## [0.12.1] — 2026-06-29

### Added
- **Environment badge now also on the landing page.** The form index (`GET /`) is
  server-rendered without the shared `footer.js`, so the 0.12.0 badge appeared on
  the forms but not on the home page. The badge is now rendered server-side into
  the index HTML (`_env_badge_html`, self-contained inline styles matching
  `.cbm-env-badge`) using `settings.environment` — so the prod/test/dev home pages
  each show their badge too.

## [0.12.0] — 2026-06-29

### Added
- **Environment badge on every form.** Each form now shows a color-coded badge in
  the top-right corner indicating the deploy target — 🟢 `PRODUCTION`, 🟡 `TEST`,
  🔴 `DEV · DRY-RUN` — so testers and staff can tell at a glance whether a form
  writes to the production CRM, crm-test, or nothing (dry-run). The label is
  derived server-side from the CRM target (`core/config.Settings.environment`:
  dry-run ⇒ `dev`, a `crm-test` base URL ⇒ `test`, any other live CRM ⇒
  `production`), surfaced on `/healthz` as `environment`, and rendered by the
  shared `frontend/shared/footer.js` (one change covers all five forms; no
  per-form HTML edits, no build step). Auto-resolves correctly for all three App
  Platform apps with no overlay changes; set `ENV_LABEL` to override the wording.

## [0.11.2] — 2026-06-26

### Fixed
- **Mentor login now actually links on production (the "approved mentor isn't
  selectable" bug).** Prod's `CMentorProfile` has the single `assignedUser` field
  **disabled** and uses the multi-user `assignedUsers` (collaborators) field — like
  `CEngagement`/`CClientProfile`. The app wrote `assignedUserId`, which prod
  accepts with HTTP 200 but silently stores nothing, so provisioned mentors stayed
  userless: never "truly Active", never eligible for the assignment dropdown,
  always "Incomplete: no User assigned". The mentor's User link is now **written as
  both** `assignedUserId` + `assignedUsersIds` and **read from whichever holds it**
  (`assigned_user_id`/`assigned_user_name` helpers) across both staff tools —
  assignments (`_mentor_row`, `list_eligible_mentors`, `assign_engagement`) and
  mentoradmin (provision link, `reconcile_user_links`, `check_completeness`,
  `update_mentor`, the `/provision` idempotency guard). Verified live on the
  production CRM.
- **Approval no longer creates duplicate login Users.** When the link write
  silently failed, each re-save re-provisioned and created `firstname.lastname`,
  then `…2`, then `…3`. Provisioning now **reuses** the mentor's existing CBM login
  (when the profile already has a `cbmEmail`) instead of creating a suffixed
  duplicate; the suffix path remains only for a genuinely new email that clashes
  with a different person.
- **"Couldn't load mentors" (504) on Client Administration in production.** The
  eligible-mentor query filtered `CMentorProfile` by `assignedUserId` in a `where`
  clause, which prod EspoCRM forbids ("Forbidden attribute 'assignedUserId' in
  where" → 400, surfaced as 502/504). The clause is dropped; userless rows are
  filtered in Python (the field is still readable in `select`). Works on crm-test
  and prod.

### Added
- **`scripts/sync_form_options.py`** — refresh the static form dropdown lists from
  the live EspoCRM enums. Rewrites only the arrays wrapped in `crm-enum` marker
  comments in `forms/*/frontend/options.js` (presentational lists untouched);
  dry-run by default (diff + non-zero exit on drift, so it doubles as a CI check),
  `--write` to apply. First sync aligned the volunteer industry list (it had
  drifted to a different taxonomy on both crm-test and prod).

## [0.11.1] — 2026-06-25

### Added
- **Step-by-step Google Workspace setup guide on the Email Setup page.** The page
  is now a two-column layout: the config form on the left, and a sticky "How to
  set this up" instructions box on the right (Google Cloud Console → service
  account + JSON key; Workspace Admin → domain-wide delegation with both Directory
  scopes, each with a copy button; then the steps back in the app). Per-field
  helper text ties each input to the relevant step. (Version bump doubles as the
  deploy marker for this UI change.)

## [0.11.0] — 2026-06-24

### Added
- **Mentor approval now creates the CBM Google Workspace mailbox when it's
  missing, with a live status window.** Approving a mentor (`/mentoradmin`)
  auto-fills `cbmEmail` (`firstname.lastname@cbmentors.org`) if blank, checks
  Google Workspace for that mailbox, and — when `GOOGLE_CREATE_MAILBOX` is on —
  **creates** the mailbox (temp password + change-at-first-login + the mentor's
  personal email as Google recovery) instead of blocking, polls up to ~60s for it
  to go live, then creates the EspoCRM login + welcome email. The Save button
  opens a **streaming status modal** (Server-Sent Events) that narrates each step
  ("Checking for the mentor email account…", "No account found, creating…",
  "Creating the EspoCRM login…") and shows the temp password to relay.
  (`core/google_directory.py` `create_user`/`resolve_google_directory`,
  `mentoradmin/service.py` `provision_mentor_user_steps`, the SSE
  `POST /mentoradmin/api/mentors/{id}/provision`.)
- **Admin-only "Email Setup" screen** in `/mentoradmin` to configure the Google
  Workspace authentication at runtime (service-account JSON, delegated admin,
  check/create toggles, a **Test connection** button). The service-account key is
  stored **encrypted at rest** in Postgres (Fernet, keyed by the new
  `APP_ENCRYPTION_KEY`) and takes precedence over the `GOOGLE_*` env vars.
  (`core/crypto.py`, `core/app_config.py`, Alembic `0003_app_config`,
  `GET/PUT/POST /mentoradmin/api/setup/google`.)

### Notes
- Creating a mailbox needs the service account's **read-write** Directory scope
  (`admin.directory.user`) authorized for domain-wide delegation, in addition to
  the existing read-only scope. The GCP service account + delegation must still be
  set up in Google Admin (the Email Setup *Test* button verifies it).
- New deploy secret: `APP_ENCRYPTION_KEY` (web + worker). `GOOGLE_CREATE_MAILBOX`
  defaults off. Alembic `0003` adds the `app_config` table (pre-deploy migrate).

## [0.10.5] — 2026-06-24

### Changed
- **The mentor-assignment confirmation is now a styled modal**, matching the
  `modal-card` popups used elsewhere in the app (e.g. Mentor Administration),
  instead of the browser's native `window.confirm()`. Same Assign/Cancel flow,
  Escape/backdrop to dismiss (`assignments/frontend/app.js` + `styles.css`).

## [0.10.4] — 2026-06-24

> **Live in production** (`cbm-client-intake-prod`) — `/healthz` reports `0.10.4`.
> The CRM-side fix is applied: `CIntakeSubmission.submitterEmail` is now `varchar`
> in dev + prod, and a live test submission confirmed the email is stored.

### Changed
- **Reverted 0.10.3's `submitterEmailData` approach — the real fix is CRM-side.**
  Live testing showed `CIntakeSubmission.submitterEmail` stays null whether the app
  sends a plain string **or** the `submitterEmailData` array, because the field was
  built as EspoCRM type **`email`**, which is bound to the entity's single primary
  `emailAddress` field — a custom-named email-type field stores nothing. The fix is
  to change that field's type to **varchar** in the CRM (the sister
  `CInformationRequest.submitterEmail` is varchar and stores fine). The log reverts
  to the simple string write, which works once the field is varchar
  (`core/submission_log.py`). **CRM action required** — see
  `cintake-submission-entity.md`.

## [0.10.3] — 2026-06-24

### Fixed
- *(superseded by 0.10.4 — the `submitterEmailData` array did not work either; the
  field type itself is the problem.)* Attempted to store
  `CIntakeSubmission.submitterEmail` via the `submitterEmailData` array.

## [0.10.2] — 2026-06-24

### Changed
- **The form index is served with `Cache-Control: no-store`**, so a freshly
  deployed landing page is never shown stale from a browser/edge cache (a
  redeploy briefly served the previous index from cache otherwise)
  (`core/app.py` `index`).

## [0.10.1] — 2026-06-24

### Changed
- **The form index opens each form/staff-tool link in a new browser tab**
  (`target="_blank"` + `rel="noopener"`), so the landing page stays put when a
  user opens a form or staff tool (`core/app.py` `_index_html`).

## [0.10.0] — 2026-06-24

### Added
- **Mentor provisioning hard-gates on the Google Workspace mailbox.** Before
  creating an EspoCRM login (and firing its `sendAccessInfo` welcome email) for an
  approved mentor, the app can verify their `firstname.lastname@cbmentors.org`
  mailbox actually exists in Google Workspace — otherwise the credentials email
  bounces and the mentor is stranded with a login they can't receive. A
  *confirmed-missing* mailbox blocks provisioning with a clear error ("create it
  before approving"); an inconclusive check (not configured, API/auth error) fails
  **open** so a Google outage can't freeze approvals. New `core/google_directory.py`
  (`GoogleDirectory.mailbox_status` → `EXISTS`/`MISSING`/`UNKNOWN`, via the Admin
  SDK Directory API with a domain-wide-delegated service account, read-only scope).
  **Off by default** — a no-op until `GOOGLE_DIRECTORY_CHECK=true` +
  `GOOGLE_SERVICE_ACCOUNT_JSON` + `GOOGLE_DELEGATED_ADMIN` are set, so prod is
  unchanged until the Google credentials exist.

## [0.9.1] — 2026-06-24

### Fixed
- **Mentor Admin no longer silently hides "no login created" on approval.** When a
  mentor is saved at `Approved`/`Active` but login provisioning is disabled on the
  server (no admin service account configured — the production state), the save now
  returns `provision={ok:false, disabled:true}` and the UI shows *"Status saved, but
  no login was created — mentor login provisioning is turned off on this server."*
  Previously this case was indistinguishable from a successful approval, so an
  approval in prod silently created no EspoCRM User and no welcome email
  (`mentoradmin/service.py`, `mentoradmin/frontend/app.js`).

## [0.8.0] — 2026-06-23

### Fixed
- **Implausible phone numbers no longer fail the Contact create.** A submission
  with a bogus phone (e.g. `12345` → `+12345`) was 400'ing EspoCRM's `phoneNumber`
  "valid" check and losing the whole lead. `core/phone.e164_or_none` normalizes to
  E.164 but returns `None` when the result can't be a real number (<10 or >15
  digits); every orchestrator (volunteer, client-intake, partner, sponsor,
  info-request — both the Contact and the `CInformationRequest` phone fields) now
  **omits** `phoneNumber` when invalid. Email stays the contact channel and the
  raw value is preserved in the `CIntakeSubmission` audit log.
  *(This was the one stuck volunteer re-drive that still failed after enum
  resilience landed.)*

## [0.7.0] — 2026-06-23

### Added
- **Enum-drift resilience extended to client-intake and partner.** `EnumSanitizer`
  generalized to span a whole create chain (entity passed per call, options cached
  per `(entity, field)`, one aggregated note):
  - **client-intake** — sanitizes `cBusinessStage` + `cIndustrySector` (Account)
    and `mentoringFocusAreas` (CEngagement); drop-note on `CEngagement.description`.
  - **partner** — sanitizes `partnershipType` + `partnershipValue`; drop-note on
    `CPartnerProfile.description`.
  - **sponsor** — no change (writes no user-supplied enum, only system
    discriminators + a free-text message).
- System discriminators (`cAccountType`/`cContactType`/status) are deliberately
  **not** sanitized — they're required/monitored and must fail loudly if they drift.

## [0.6.0] — 2026-06-23

### Added
- **Enum-drift resilience (volunteer).** New `core/enum_filter.py` `EnumSanitizer`
  validates enum/multiEnum payload values against the live CRM options and **drops**
  unrecognized ones instead of letting a single drifted value 400 the whole create.
  The volunteer orchestrator sanitizes `industrySector` / `mentoringFocusAreas` /
  `fluentLanguages`; dropped values are noted on `CMentorProfile.description` for
  staff follow-up. Fails open (keeps the value if options can't be fetched, e.g.
  dry-run). `metadata_enum_options` added to the `EspoApi` protocol +
  `DryRunEspoClient` + `ResumableClient`. **Effect:** re-driving a drift-failed
  submission now creates the record (with the valid data + contact info) instead
  of failing — no discarding needed.

## [0.5.0] — 2026-06-23

### Added
- **`/ops` Discard action.** A stuck submission that can't be delivered (e.g. a bad
  payload that re-driving would just replay) can be moved to a terminal `discarded`
  status, so it leaves the worker queue and stops counting toward the
  needs-attention alert. The row is kept for audit; a completed delivery can never
  be discarded; Re-drive also covers `discarded` so a mistaken discard can be
  undone. (`store.discard()`, `POST /ops/api/submissions/{id}/discard`, Discard
  button on stuck rows.)

## [0.4.0] — 2026-06-23

First version bump of the session — the footer/`/healthz` had been stuck at 0.3.0,
so it gave no signal for whether a new build was live. `core/__init__.__version__`
now reads from `pyproject.toml` (single source) instead of a stale hardcoded value.
Bundles the following work, all shipped under this version:

### Added
- **Client Administration (`/assignments`) — Available Mentors grid:** a **Type**
  column + filter (sortable) and an **Accepting** (new clients) column. `mentorType`
  is normalized so a single enum or multi-enum both render/filter/search.
- **Client Administration — Requested Mentor (DAT-026).** The engagement detail
  popup now shows the `CEngagement.requestedMentor` link (belongsTo CMentorProfile)
  when set, resolving the name defensively (inline accessor → CMentorProfile read;
  a deleted target shows "(no longer in the system)"). Hidden when unset.
- **Worker crash-recovery (lease).** `claim_batch` now leases each claimed row
  (`locked_until = now + worker_lease_seconds`, default 900s) and reclaims
  `processing` rows whose lease expired — a worker killed mid-delivery
  (redeploy/OOM/SIGKILL) no longer strands a submission in `processing` forever
  (safe because delivery is resumable). Alembic migration `0002_processing_lease`
  adds `locked_until` + a claim index.
- **`/healthz` database check.** Pings the durable store and returns `503` +
  `database:"error"` when it's configured but unreachable. The CRM is deliberately
  not pinged (a CRM outage must not take the web tier down — durable capture +
  the async worker exist to ride it out).

### Changed
- **Public intake forms (all five) — UX.** The submission **reference number** is
  now shown on the confirmation screen; a **30s request timeout** (AbortController)
  with a retryable message replaces an indefinite "Submitting…"; validation errors
  are **announced + focused** (`role="alert"`); a double-submit guard; clearer phone
  placeholders + explicit "(optional)" labels. (Applied in both the shared
  `wizard.js` and client-intake's standalone `app.js`.)
- **Staff tools — UX.** All three (`/assignments`, `/ops`, `/mentoradmin`) now
  distinguish a 5xx/network boot failure ("server isn't responding") from "not
  signed in". `/mentoradmin`: cancelling the incomplete-record modal jumps to the
  first unresolved field; a field-spec load failure warns instead of a blank
  editor. `/assignments`: labeled load errors (mentors vs engagements). `/ops`:
  surfaces "metrics unavailable" instead of swallowing the error.

### Fixed
- **Schema drift — volunteer industry/language.** The form's `industryExperience`
  (20 NAICS sectors) had **zero overlap** with the live `CMentorProfile.industrySector`
  enum (28 CBM values), and `fluentLanguages` offered 36 vs the CRM's 2 — so every
  industry pick (and most language picks) 400'd. Aligned both lists to the live
  enums (verbatim, including the CRM's typos). Extended `core/schema_contract.py` to
  cover the volunteer form's enum fields so the Phase-3 drift monitor warns before
  the next such failure (they were previously unmonitored).
- **`session_expired`** now matches the *first* `HTTP <code>` in the EspoError
  message, so a 502 whose body merely contains "HTTP 401" is no longer misread as
  token expiry.
- **`assign_engagement` partial-failure reporting.** The downstream re-homing
  (contacts/client/account) is now best-effort and per-target — a CRM failure on
  one record is captured in `reassignmentErrors` and reported to the staffer,
  instead of raising after the engagement was already assigned. Steps 1–2 (the core
  assignment) stay fail-fast.

---

For per-feature design notes and live-verification records, see `CLAUDE.md`. The
V2 reliability platform (durable capture + async worker + ops + alerting) is
specified in `prds/v2/`.
