# The applications

Split out of `CLAUDE.md` on 2026-09-25 to keep that file loadable in every
Claude Code session. `CLAUDE.md` keeps a one-paragraph pointer per application;
the full detail for each one lives here.

Every staff/mentor tool follows the same shape: a package with `service.py`
(the CRM logic and the **field whitelist**), `router.py` (endpoints, gate, the
`_crm_failure` mapping), and `frontend/` (vanilla JS, no build). A recurring
pattern worth knowing before adding a field anywhere: **one declared field spec
serves as BOTH the form layout and the server-side update whitelist**, and
enum options + required flags are read **live from CRM metadata** so the CRM
stays the source of truth.

### Client Administration — `/assignments`

Staff-only. Page title is "Client Administration"; the package and route stay
`assignments`. Lists `CEngagement` records in a sortable, searchable,
full-height grid with a status multi-select, and assigns each to a mentor.

- **Mentor dropdown** = `CMentorProfile` where `acceptingNewClients=true` AND
  `mentorStatus="Active"` AND `assignedUser` set. An empty dropdown means no
  mentor passes all three.
- **A mentor's name in the Available Mentors list opens a read-only detail
  popup** (v0.220.0): the CRM's own `CMentorProfile` detail layout rendered by
  the shared `/shared/detail-render.js`, plus a Contact panel and an "Other
  fields" sweep (`directory.service.detail(..., include_unplaced=True)` via
  `service.mentor_detail`), read as the signed-in user. Its footer
  Assign/Reassign button completes the assignment when the roster was opened
  from an engagement's Assign/Reassign card ("Browse the full mentor list…");
  unscoped it explains itself on click. View-only by ruling — editing stays in
  Mentor Administration.
- **Assign** (`service.assign_engagement`) sets `mentorProfile` +
  `engagementStatus="Pending Acceptance"`, stamps `engagementAssignedDate`, and
  re-homes assigned users across every related Contact, the CClientProfile and
  the Account. **Merge, never overwrite** (`_merged_assignment_payload`) — an
  overwrite silently revokes co-mentor access.
- **The mentor gets a stamp too** — `CMentorProfile.lastClientAssignedDate`, the
  last date that mentor was given a NEW client. Written by Assign and by
  Reassign (the **new** mentor only; the field records gaining a client, not
  losing one), never by a repair. Advance-only, feature-detected, and
  best-effort — a role without `CMentorProfile` edit logs a warning rather than
  losing an assignment already written. It is a sortable **Last Assigned**
  column in the Available Mentors picker (ascending = who is most overdue), and
  the roster query asks for the field only when the CRM has it. Spec:
  `cmentorprofile-last-client-assigned-field.md`.
- **Assign needs `User: read` on the acting role.** The assignedUsers stamp is
  a link write, and EspoCRM refuses it (403 `cannotRelateForbidden`, identical
  in 9.3.4 and 10.0.6) unless the user can read every User being linked. The
  Client Assignment Role carried no User grant until 2026-09-07; Cleveland's
  client admins only ever passed through a second team seat (Mentor Team).
  Ruling: `User: read all, edit own` on the role itself —
  `scripts/migrate_client_assignment_role.py`, Lakeside done, crm-test and
  prod owed (`OPEN-ITEMS.md` #28).
- **Stale-write guard**: the engagement is re-read before any write and the call
  is rejected (400, nothing written) if it already has a mentor or is no longer
  `Submitted`. The frontend reloads the grid on any Assign 400.
- **Assigning the SAME mentor again is a repair run**, not an error — it
  re-executes the idempotent re-homing. Reachable from the row's right-click
  menu ("Repair assignment…"), which is the only door to it since assigned rows
  have no Assign control.
- **Reassign Mentor** swaps `mentorProfile`, re-stamps the date, re-homes
  everything including every CSession (swap-merge: the old mentor is removed
  unless a co-mentor shares the user or they personally own the session),
  and deliberately **leaves `engagementStatus` untouched**.
- A successful Assign/Reassign opens the quick-compose with the mentor's
  `cbmEmail` and the EspoCRM `MentorAssignmentNotice` template pre-applied.
- Every row function is also on the **right-click context menu**. The Notes
  column edits `CEngagement.description` inline — staff-internal by design, and
  excluded from the session tools' Details tab for that reason. **Whether it
  is a rich editor or a plain textarea is feature-detected per load** from the
  field's live CRM type (`service.live_wysiwyg_fields`): wysiwyg ⇒ the shared
  editor with images, text ⇒ the textarea, because only a wysiwyg field binds
  its inline attachments (an unbound one is collected by EspoCRM's cleanup).
  crm-test is converted; production's conversion is a tracked CRM
  prerequisite (`cengagement-description-wysiwyg-crm-handoff.md`). The popup's
  Engagement-notes and Mentoring-needs fields are wysiwyg on both CRMs and take
  images now.
- **The View-details popup is editable** (v0.210.0). It opens at 90% of the
  window, resizable, with the title bar and the Save/Cancel bar pinned around a
  scrolling body. `service.ENGAGEMENT_EDIT_FIELDS` is **one spec serving as both
  the form layout and the update whitelist**; enum options come from live CRM
  metadata, link-picker options are **paged at 200** (an oversized page is a 403,
  not a truncation), a forbidden list degrades the field to read-only, a stored
  value outside the option list keeps its place, and Save sends only what
  changed. **The assigned mentor is deliberately not an editable field** —
  swapping `mentorProfile` re-homes contacts, client profile, company and
  sessions, so the row hands off to Assign/Reassign instead.

### Mentor Administration — `/mentoradmin`

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
- Functional reference for staff: `mentor-administration.md`.

### My Mentor Profile — `/mentorprofile`

Mentor self-service (Mentor Team, not staff-only): a mentor edits their OWN
profile + linked Contact, with a live preview that is an **exact reproduction of
the public website mentor page** — the Elementor HTML and CSS were copied
verbatim from the live site into `mentorprofile/frontend/`. **Keep the marked
block in styles.css in sync if the website template changes.** Rendered at the
site's 1200px desktop width and scaled to fit; the mobile media block is
deliberately omitted.

- **Always "me"** — no record id from the client. Every endpoint resolves the
  caller's own profile server-side via `resolve_manager_profile`.
- **`PROFILE_FIELDS`** is the layout + whitelist and is deliberately
  **non-administrative**: status/type, compliance, dues, cbmEmail and departure
  are NOT in it, and smuggled changes are dropped. The page has no width cap.
- Photo upload is base64 JSON → Attachment → `profilePhotoId`; display proxies
  through the app (`GET /photo`) because the browser can't reach the CRM.
- Also hosts the **email-signature editor** (EspoCRM `Preferences.signature`),
  whose toolbar carries the Insert-logo button (`ORGANIZATION_LOGO_URL` — see
  the CBMRichText convention); uploaded/pasted images stay refused because
  recipients can't reach them.
- The `description` field is surfaced here as **"Personal interests"** — it is
  what the directory's mentor profile page shows to fellow members, and this is
  the single edit surface for it.
- The page-slot ↔ CRM-field mapping for the WordPress feed is in
  `cmentorprofile-summary-field.md`.

### Session Management — `/mentorsessions`, `/partnersessions`, `/sponsorsessions`

User-facing titles: **Client Management**, **Partner Management**, **Funder
Management**. Packages, routes, slugs and team gates are unchanged. "Funder" is
display wording only — the CRM entities stay `CSponsorProfile` etc.

**One configurable engine, three team-gated routes.** Managers review the
records they own and record meetings as **`CSession`** records — one entity with
the parent link swapped. The domains differ only by a per-domain
`sessions/config.py:DomainConfig`; the whole feature is one engine
(`sessions/service.py`), one router factory (`sessions/router.make_router`), and
one shared frontend that derives its domain from the first segment of its URL.

| slug | parent | owned-records link on the user's `CMentorProfile` | co-mentors |
|---|---|---|---|
| `mentorsessions` | `CEngagement` | `engagements1` (+ `engagements` for co-mentored) | yes |
| `partnersessions` | `CPartnerProfile` | `managedPartners` | no |
| `sponsorsessions` | `CSponsorProfile` | `managedSponsors` | no |

- **Managers are `CMentorProfile` records** — the one whose `assignedUser` is
  their login. `resolve_manager_profile` matches `assignedUser` **in Python,
  never a `where` on `assignedUserId`** (prod's field ACL forbids it). A record
  assigned to a *duplicate unlinked* profile is invisible here — a recurring
  data trap ([[crm-test-duplicate-mentor-profiles]],
  [[sessions-manager-profile-must-be-assigned]]).
- **Partner and Funder grids list ALL records** (`DomainConfig.list_all`), not
  just owned ones — the user's CRM ACL is the gate. This also means those
  domains never read `CMentorProfile` for the list, which is what fixed the
  sponsor-team 403.
- **Detail tabs**: Overview · Details · Sessions · Communications · Documents,
  plus Contributions (funder only), Referred Clients (partner only), and
  Analytics (when enabled). Each optional tab is gated by a `DomainConfig` field
  that controls **both the tab and the endpoint registration** — a router that
  doesn't own the feature never registers its routes.
- **Overview** is a facts rail + notes feed with drag splitters, an aggregated
  Company peek, a Next-session callout with a Start/Open button, and (partner +
  funder) a **Discussion pane** — an app-only, append-only, attributed comment
  stream in the `record_comment` Postgres table, **never written to the CRM or
  shown to the partner/funder**. Record notes edit in place from the Overview.
  Every scalar rail fact renders "—" when empty rather than vanishing (an empty
  slot that disappears reads as a missing feature).
- **Details** renders from live CRM metadata (editable scalars, humanized
  labels) in curated, packed, full-width group panels. Curated lists control
  what appears: `DETAILS_LAYOUTS`, `DETAILS_REMOVED_FIELDS`, and
  `_ENTITY_LINK_FIELDS` (belongsTo links render **only** if curated there — the
  metadata sweep covers scalars only). Permission-aware down to per-record
  ownership. The PUT is entity-allowlisted (`cfg.details_entities` + Contact,
  else 404).
- **Re-assigning a record's manager happens on the Details tab**, through those
  curated link pickers — `CPartnerProfile.partnerManager` on the Partnership
  panel and `CSponsorProfile.cBMSponsorManager` on the Funding panel (v0.197.x).
  Each is the belongsTo behind the `manager_owned_link` reverse
  (`managedPartners` / `managedSponsors`), so it decides **whose** record this
  is — which is why it went unnoticed for so long that the grid displayed it and
  nothing could change it. Options are the mentor profiles the signed-in user
  can read; a forbidden list degrades the picker to read-only rather than
  breaking the tab, and a stored manager outside the list stays selected so a
  save can never silently drop them. **Mentor has no equivalent** — an
  engagement's mentor is re-assigned in Client Administration, deliberately
  (`DETAILS_LAYOUTS` keeps `mentorProfileName` read-only there).
- **The record's COMPANY is set on the Details tab too** (v0.198.0), the same
  way: `partnerCompany` / `sponsorCompany` as curated link pickers leading the
  Partnership and Funding panels, gated per domain by
  `DomainConfig.company_link_editable` (mentor has none — an engagement's
  company resolves through the client profile via `company_fallback`). These
  pickers also **create** the company, because a partner/funder the CRM holds no
  Account for cannot be repaired by picking: "+ New company" find-or-creates it
  (`details.create_company` → `service._find_or_create_company`, so a same-named
  company is reused and `cCompanyType` merged in), and the panel's **Save**
  writes the link — creating and linking stay separate so there is exactly one
  write path to the link. `POST /records/{id}/company` is **not** gated by
  `RECORD_QUICK_ADD`: it repairs records that already exist.
- **A company can carry MANY partner profiles.**
  `Account.cCompanyPartnerProfile` was `hasOne` until 2026-08-14, so linking a
  company to a second partner profile silently *moved* it off the first — that
  is how a live partner record lost its company to a duplicate entered nine
  hours later. Doug's ruling: a partnership is with a programme inside an
  organisation as often as with the organisation itself, so one company, many
  partner records. Recreated as many-to-one on prod 2026-08-14 and crm-test
  2026-08-15, verified in both; no application code was involved.
  **Funders followed on 2026-08-16** — `sponsorCompany` ↔
  `Account.cSponsorProfiles`, both environments, all links intact, proven by a
  two-funders-one-company test on crm-test.
- **Clients are the exception, and it is deliberate.** Doug's ruling
  (2026-08-16): **a client never has two client business profiles**, so
  `CClientProfile.linkedCompany` staying `hasOne` is *correct* — do not "fix" it
  to match partners and funders. The guard that makes the model safe lives in
  the app: `forms/client_intake/orchestrator._find_or_create_client_profile`
  find-or-creates the profile **matched on `linkedCompanyId`**, because an
  unconditional create silently moved the Account and contact off the existing
  hub (twice in production, 2026-07-17 and 2026-07-27). Verified clean
  2026-08-16: all 73 prod client profiles have a company and none share one.
- **Grants (funder only, `grants_link`)** — the Grants tab: awards, their
  deliverables, and later their funder reports. The **grant is the hub**:
  `CContribution` rows become its payments and deliverables its obligations, and
  the two are **siblings under it, never a chain**. Client attribution lives on
  the grant (`fundedEngagements`), so a renewal starts clean. Deliverable
  progress math lives in ONE place (`service.deliverable_progress`) — a stored
  status always beats the arithmetic, and a Narrative deliverable has no
  percentage at all. Gated by `GRANTS_ENABLED` **and** CRM feature detection,
  which fails closed. Plan + rulings: `prds/grant-management-plan.md`.
- **Partner and Funder can be CREATED here** (`RECORD_QUICK_ADD`, off by
  default): the grid's "+ Add partner" / "+ Add funder" runs the same
  Account → Contact → profile sequence the public intake forms do, as the
  signed-in user. `DomainConfig.create_spec` gates both the button and the
  routes (mentor has none — engagements arrive through intake), and the spec is
  BOTH the form layout and the write whitelist. Same dedupe policy as intake:
  a same-named company / same-email contact is reused and null-filled, never
  duplicated; a reused company gains the type value merge-only.
- **Contacts tables are per-domain**: mentor shows Role chips and an Agreements
  badge; partner/funder show neither (every contact has the same relationship to
  CBM, and the consent bools are a client-intake concept) but offer **Make
  primary**.
- **First completed session activates the engagement** — a session saved
  Completed on an `Assigned`/`Assignment Dormant` engagement moves it to
  `Active`. The status guard *is* the "first session" rule. Best-effort.
- **Closing a session with a future "Next session" date books the follow-up**
  automatically (Scheduled, 1h, contacts invited). The grid's Next Session
  column derives **only from real sessions** — the stored
  `CEngagement.nextSessionDateTime` is deliberately discarded because staff can
  hand-edit it in the CRM and a stale value showed as a ghost session.
- **`touch_last_contact`** advances `CEngagement.lastContactDate` /
  `lastContacted` (advance-only, never backward or future) on a recorded session
  and an outbound email from the record.
- **Editor**: `SESSION_FIELDS` is layout + whitelist. `duration` is EspoCRM's
  *virtual* type — the frontend translates the Duration select into a recomputed
  `dateEnd`. The time picker **shades slots that conflict** with the user's own
  Google calendar (advisory only — a shaded slot stays selectable).
- **Co-mentor visibility** requires two things, both in the app: reading the
  `engagements` reverse link *and* stamping the co-mentor's User into the
  engagement's `assignedUsers` (Mentor Role reads CEngagement at "own", which
  with `assignedUser` disabled means `assignedUsers` membership). `add_comentor`
  also stamps the client records and backfills existing sessions;
  `remove_comentor` un-stamps symmetrically unless the user is shared.
- **New sessions are owner-stamped** so a read-own role can see its own create —
  without this the create itself 403s, because EspoCRM ACL-checks the read-back.

Watch for these when touching this package:

- **`sessionAttendees` and `additionalMentors` are RELATIONSHIPS, not fields** —
  read via `list_related`, write via relate/unrelate. Reading `<field>Ids` always
  returns empty and setting it on an update is silently ignored
  ([[espo-custom-linkmultiple-is-a-relationship]]). `unrelate` sends the id in
  the DELETE **body**; the path-suffix form 404s.
- **Relate/unrelate checks BOTH sides** — adding a co-mentor needs edit on the
  *other* mentor's profile. `_link_or_escalate` runs as the user first and only
  escalates a `noAccessToForeignRecord` denial to the admin account
  ([[espo-link-checks-both-sides]]).
- **Enum drift is handled in two layers**: the frontend sends only changed
  fields, and `_sanitize_enum_payload` drops values outside the live options
  before the CRM call (fails open).
- Required fields come from CRM metadata, not hard-coding.
- The `CSession` **name formula must be keep-if-present**
  (`ifThen(name == null || name == '', …)`) or it clobbers the supplied title.
- **One record, one tab** — records open in a stable per-record window and a
  `BroadcastChannel` elects one owner tab ([[single-tab-record-guard]]).

### Submission Admin — `/ops`

Marketing Admin Team. A multi-admin review-and-respond workspace over the
durable store. Staff reference: `submission-admin.md`.

- **Two status axes, deliberately separate**: **Intake status** (what happened
  to this arrival — Received / Completed / Held-Spam / Held-Email / Error /
  Discarded, the CRM receipt vocabulary) and **Response status** (where the
  reply conversation stands — New → In progress → Reply owed / Waiting on them →
  Responded → Closed). Machine words like `pending`/`needs_attention` never
  render. Count chips are one-click filters; filtering is client-side.
- **No owner — coordination by visibility**: an attributed comment stream, an
  automatic activity feed, and presence ("viewed 4 min ago").
- **Close requires a reason**; discard requires one too (422 without) and stamps
  who/when/why on the CRM receipt. A submitter replying on an anchored thread
  after close **auto-reopens** it.
- **Record-creating submissions auto-close** on successful delivery ("Process
  completed") — they are owned by the downstream admin team from that point, so
  the open queue is only info-request and info-email items needing a reply.
- **Email is thread-anchored**, not an address search: every send records its
  Gmail thread on the submission, and the conversation view reads only anchored
  threads. Sends go as **`OPS_MAILBOX`** (info@, display name "CBM Info") so
  every admin sees the same conversation.
- **Inbound info@ capture**: the worker polls the shared inbox and captures each
  new thread as a **held `info-email` submission** for triage. Approve = redrive
  (creates CRM records via the info-request orchestrator); Discard = spam with
  zero CRM residue. Layered stateless dedup means replies to anchored threads
  never double-capture. **Only ONE poller may run** — setting `OPS_MAILBOX` on
  both environments double-captures.
- **Other correspondence** surfaces inbound info@ threads not tied to a
  submission (replies to notices staff sent), read and replied to in-app,
  nothing stored.
- `?submission=<id>` deep-links a row even when filtered out; alert emails use
  it via `APP_BASE_URL`.

### Workspace Directories — `/directory`

Browsable grids over Companies, Contacts, Mentors and Partners, gated by
`WORKSPACE_ALLOWED_TEAMS`. **Grid columns and the detail pop-up arrangement are
read LIVE from the CRM's own layouts** (`{entity}/layout/list` and
`/layout/detail`) so they match the CRM and auto-sync — nothing hardcoded
([[espo-layout-api-readable]]). Toolbar is Filter · Search · View/Edit.

- **Contacts get a full record page** (`/directory/contacts/record/{id}`) with
  Overview + Communications, the latter scoped to **only the signed-in user's own
  conversations** (filtered server-side).
- **Mentors get a rich read-only profile page**
  (`/directory/mentors/record/{id}`) — a warm internal "get to know your
  colleague" view, deliberately not the CRM pop-up and not the public website
  look: hero, professional lane, "Get to know them" (interests, birthday
  month+day, spouse, city), mentoring availability with a slot bar, and
  reach-out links. Editing lives in My Mentor Profile. Guide:
  `mentor-directory.md`.
- Availability is computed under the **org-wide API key** (a peer mentor can't
  read another's engagements as themselves; it's a non-sensitive aggregate).
- Composite `address` fields must be composed from sub-fields — reading them as
  one attribute returns empty.

### My Email — `/myemail`

One inbox across every record the manager handles — scope is the
`CMentorProfile` reverse links (owned + co-mentored, all three domains),
deliberately NOT ACL-wide. Rows carry record chips, unread state, and
awaiting-reply / delivery-failed chips. The thread modal's reply path is "Open
in record — reply there"; full compose lives on the record page.

### Analytics — `/analytics`

A **metric library → panels → pages** engine, gated by `ANALYTICS_ENABLED`.
Live on both environments. User guide: `analytics-guide.md`; activation runbook:
`ANALYTICS-SETUP.md`; design record: `prds/analytics-app-plan.md`.

- Four result shapes — `scalar` / `series` / `breakdown` / `rows` — each tied to
  one panel renderer. Charts are **hand-rolled SVG/HTML** in
  `frontend/shared/charts.js` (Doug's decision: no charting library).
- **Hybrid caching**: cheap counts run live off the EspoCRM list `total`
  envelope; sweeps are cached in `analytics_cache`. A metric error degrades to
  an "unavailable" panel, never a 500.
- System metrics compute under the **org-wide API key** (the team gate and
  per-panel visibility are the boundary). **Record-scoped metrics always run
  live as the user, never cached** — a shared per-record cache would leak scope.
- **Authoring is self-serve** — admins build metrics (entity + filters +
  aggregation, with live preview) and compose pages in-app, no deploy.
- **Built-ins are defaults**: a DB page or metric with the same key overrides
  the built-in, and deleting a built-in writes a `source='suppressed'` marker.
  The three operational metrics read the app's own data and so aren't
  builder-editable.
- **A dashboard's `scope` IS its location**, one dashboard per record type,
  enforced at save. **All seven record views host one** — Mentor / Engagement /
  Partner / Funder / Contact / Company / Client, each with a starter dashboard.
  Company got a real record page of its own
  (`/directory/companies/record/{id}`, sharing `record.html` with View Contact
  but without Communications); Client has no screen by ruling — its dashboard
  renders as a second section on the **engagement** Analytics tab, keyed off
  `clientProfileId` in the session-detail payload.

### System Settings — `/setup`

**EspoCRM admins only** (not a team gate — this page can reconfigure the
platform). Changes this deployment's runtime settings from the browser instead
of an overlay edit plus `doctl`, which is what makes the flag-based promotion
gate practical. Gated by `SETUP_ENABLED` + a database. **Live on both
environments** — prod since 2026-08-12; before that the flag was only ever in
the crm-test overlay, so every prod flag change needed `doctl`. Runbook:
`SYSTEM-SETTINGS-SETUP.md`; rulings: `prds/system-settings-plan.md`.

- **Env is the default, the DB row is the override, and both are shown when they
  disagree** — `app_setting` holds only overridden keys and
  `core/settings_store.py` merges them over the env baseline behind the same
  `get_settings()` every package already calls. An empty table is exactly the
  old behaviour.
- **Degrade to the overlay, never to the code default.** If the override lookup
  fails (no DB, Postgres down, a bad value) the accessor returns the env value
  and logs. A database incident must not silently reconfigure the app — which is
  also why the overlays keep their flags permanently.
- **Every setting is editable unless a change is genuinely impossible** (Doug's
  ruling, 2026-08-28: *"All settings should be editable, unless a change would
  make the system unusable. Then there must be a verification that the system is
  still functional."*). The denylist is down to **three** keys — `DATABASE_URL`
  (the override table lives inside the database it names, so a move would be
  left behind in the database being abandoned), `APP_ENCRYPTION_KEY` (rotating
  it makes every stored secret permanently unreadable — data loss, not lockout)
  and `RELEASE_TAG` (the release stamp travels in the image's own
  `release-tag.txt`; a stored override would survive a restart and make the
  deployment misreport which promotion it is). All three are **visible and read-only**,
  each refusal naming its reason. Everything else that used to be hidden — the
  CRM address and key, dry-run, the provisioning account, every integration
  credential, the session secret, `SETUP_ENABLED`, `SETTINGS_OVERRIDES` — is
  editable through the **verified path** (`setup/verify.py`):
  - **Pre-flight**: the value is tried before it is stored. A CRM key the CRM
    rejects, or an address that answers but holds none of this app's entities,
    is refused with the CRM's own error. A probe that cannot *reach* its target
    returns `unknown`, never `ok`, and `unknown` does **not** block the save —
    an admin fixing configuration during an outage must not be blocked by it.
  - **Post-apply**: a `VERIFIED_KEYS` change that leaves the system non-functional
    is **reverted automatically**.
  - **Confirm-or-revert**: `LOCKOUT_KEYS` (the two switches guarding this page,
    the session secret, the cookie flag, allowed origins) apply with a
    **10-minute countdown** and undo themselves unless an admin confirms. No
    probe can detect a lockout — the app is working perfectly and simply will not
    let anyone back in — so this is the only mechanism that survives it. The
    sweep runs in **both** processes on the settings timer, and works directly
    against the database so it still fires when the change under test was
    `settings_overrides=false`.
  - **Secrets are editable but never readable** — set a new one, never read the
    old one back. Stored **encrypted** with `APP_ENCRYPTION_KEY`; without a
    cipher a secret is **refused**, never written in plain text. `DATABASE_URL`
    counts as a secret because the password is inside the URL. History stores
    `(secret set)`, never the value.
  `SETTINGS_OVERRIDES=false` is still the env-only break-glass.
- **Every setting is on the page — including the ones that need a restart**
  (Doug's ruling, 2026-08-28: a setting hidden where it cannot be viewed or
  edited is unacceptable). `BOOT_READ_KEYS` are curated into a **Restart
  required** group that explains itself, and each row shows the value **in
  force** beside the stored one, badged *Waiting for restart* when they differ.
  Two things make that honest rather than a repeat of v0.190.1, when these were
  offered with a "takes effect on next deploy" badge and toggling
  `events_enabled` produced a portal tile whose routes did not exist:
  - **`core/boot_overrides.load_at_boot` installs the override layer at the very
    top of `create_app`**, before routers are mounted, middleware built or
    logging configured. Previously the layer loaded afterwards, so such an
    override never applied *at all* — a redeploy re-ran the mounting first. It
    never raises, and on a database failure it degrades to the **deployment's**
    values, never the code defaults.
  - **The live `Settings` object is not the truth for these keys.** The periodic
    refresh installs a newer value into it while the already-built routers keep
    the old one, so reading it back would report a change as taken effect when it
    had not. `boot_overrides.state().snapshot` is the only honest source and is
    what the page reports as `inForce`.
  `DENYLIST` now holds only secrets, infrastructure and the break-glass pair —
  plus **`release_tag`**, which is curated **read-only**: it is stamped into the
  image, so a stored override would survive a restart and make the deployment
  misreport which image it is running. **The denylist is still filtered on READ
  as well as write**, so a row that outlives its rule goes inert with no cleanup.
- **Web and worker refresh independently** (`SETUP_REFRESH_SECONDS`, default 45).
  `/healthz` reports `settingsVersion` per component so you can see the worker
  catch up.
- **Overrides never auto-revert**; a change can be marked temporary with a review
  date, and overdue ones are flagged on the page and logged hourly by the worker.
- **Scoped rollout is web-only** — a per-team/per-user scope needs a signed-in
  user to evaluate, so worker-side settings refuse it. A scoped override is
  deliberately excluded from the process-wide config.
- Also on the page: a **feature-readiness** panel (flag · required secrets · CRM
  fields detected · which component · worker heartbeat), an **environment diff**
  against the peer deployment (token-authorised snapshot, no secret values ever
  crossing the wire), and an **operations** tab whose mutating jobs are
  **dry-run → apply that exact plan**, refusing if the plan moved.

### Events & Webinars — `/events`

Replaces the data layer behind `clevelandbusinessmentors.org/webinars/`, which
today runs on a Google Apps Script plus a browser-side YouTube API call with
**EspoCRM involved at no point** — so every registrant is an invisible lead.
Staff guide: `event-administration.md`; activation + test script:
`EVENTS-SETUP.md`; schema: `cevent-entities-crm-handoff.md`.

**Live on BOTH deployments since 2026-09-14; the website still runs on the Apps
Script.** `EVENTS_ENABLED` + `EVENTS_PUBLIC_API` are on for crm-test and
production; `ZOOM_EVENTS`, `EVENTS_REMINDERS` and the attendance pull are off
everywhere. Production's overlay also carries `YOUTUBE_API_KEY` and
`YOUTUBE_PLAYLIST_ID` (five playlists, comma separated) on the **web** component
only — the worker needs neither until attendance is switched on.

**Production holds a real programme now**: 10 recorded webinars imported from the
playlists on 2026-09-14 and published with topics, plus one internal
`CRM Training Webinar` that is **published** and dated in the future, so it is
currently the only thing on the public calendar — check whether that is intended
before the redirect. Zero registrations so far; the end-to-end test registration
is still owed.

**The only thing between here and the lead leak stopping is the redirect
itself** — one rule on the marketing site, and removing it is the rollback. Phases 1, 2, 3, 5
and **6** are built. **Phase 4 — the WordPress plugin — was STRUCK on
2026-09-11**: Doug ruled that the marketing site should **redirect** to a page
this app serves rather than embed or reimplement one. What stops the lead leak
now is one redirect, plus two things owed before it (`OPEN-ITEMS.md` 19d
consent, 19f the per-event duplicate hold).

### The PUBLIC pages — `/webinars/` and `/webinars/{slug}` (v0.222.0)

`events/pages.py` + `events/public_frontend/`. Gated on `events_public_active`,
so an unconfigured deploy serves nothing. Assets ride `/webinars-assets` — a
separate top-level path, because `/webinars/{slug}` is a route and "assets"
would be indistinguishable from a slug.

- **They are ROUTES, not static files, for two reasons.** A social crawler runs
  no JavaScript, so each event's `<head>` is filled **server-side** or a shared
  link renders as a blank card. And an unpublished event must **404** — `CEvent`
  doubles as the internal calendar, so a page that merely rendered empty would
  still confirm the record exists.
- **The body is the SAME renderer the staff preview drives**
  (`/events-plugin/cbm-events.js`) under the site's own stylesheet, so the
  preview and the live page are one code path rather than two kept in step.
- **The site's stylesheet has TWO wrapper scopes, and they are not
  interchangeable**: `.cbm-wb` for the calendar, `.cbm-yt` for the recorded
  library, each carrying its own CSS variables, every rule written as
  `.cbm-wb .panel …`. The wrapper must be an **ancestor** of `.panel`, never the
  same element. Getting this wrong unstyles a whole panel and raises no error —
  it shipped that way for an hour on 2026-09-11 and is now in the class contract
  (`HOST_CLASSES` in `tests/test_events_graphic.py`).
- **Branding renders first, page values second**, every value HTML-escaped, so
  CRM-authored content is never rescanned for a `{{token}}`.
- **Both public doors send `consent: false`** — the calendar modal and the event
  page's own form — so a registration records **no opt-in at all**. That is
  deliberate and blocking: see `OPEN-ITEMS.md` 19d.
- **`EVENTS_PUBLIC_BASE_URL` empty means "this app"** (derived from
  `APP_BASE_URL` + `/webinars`). It used to default to the marketing site's
  `/webinars`, which **404s**, so every shared event link pointed at nothing.
- **The marketing page's whole opening came across, not just its panels** — the
  navy hero, the gold strapline band and the organisation's own top-level menu.
  All of it is content on a page that redirects away, and the first side-by-side
  (2026-09-12) is what found it missing, exactly as it found the presenting
  invitation. Settings: `EVENTS_HERO_TAGLINE`, `EVENTS_HERO_PILLARS`,
  `EVENTS_HERO_BAND` (each emptiable) and `ORGANIZATION_SITE_NAV`
  (`Label|path` pairs; a leading `/` resolves against
  `ORGANIZATION_WEBSITE_URL`, so a chapter changes one setting, not seven).
  The menu is built **server-side** for the same reason the name is substituted
  there: a menu that appears a moment late is worse than none, and it is the
  visitor's only way on to the rest of the site.
- **The recorded library has a TOPIC filter** (v0.230.x). It offers only
  subjects that actually have a recording — a filter listing an empty one is a
  dead end — computed from the whole library rather than the current results so
  the options do not shift as a visitor searches, and hidden below two topics.
  The selector sits **above** the search box because the search runs *inside*
  the chosen topic, and the placeholder names it. Clearing the search box
  reloads on its own (`input`, not the `search` event, which Firefox does not
  raise). One CRM read serves the results, the topic list and the count:
  `published_recordings` plus the pure `filter_recordings` / `recording_topics`.
  Order comes from `cfg.TOPIC_ORDER`; a value that has drifted out of the enum
  still appears.
- **Panel wording is the SITE's, not ours** — "Calendar of Upcoming Webinars"
  and "Find a Recorded Webinar". Inventing better names put our page out of step
  with the one it replaces; don't re-invent them.
- **⚠️ The recorded library is empty and that blocks the redirect**
  (`OPEN-ITEMS.md` 19i). The live page's library comes straight from the YouTube
  playlist; ours comes from `CEvent` rows with a `recordingUrl`, and there are
  none on either CRM. `scripts/import_youtube_events.py` fixes it and has never
  been run — it needs `YOUTUBE_API_KEY` and `YOUTUBE_PLAYLIST_ID`, neither of
  which is configured anywhere, and the playlist id is not in the live page's
  source.
- New settings: `ORGANIZATION_WEBSITE_URL` (the back-link and the menu's base,
  per-chapter like `DOCS_SITE_URL`) and `EVENTS_CONTACT_EMAIL` (the
  presenting invitation's address; empty falls back to `OPS_MAILBOX`).
- The portal's bottom section is **"Public pages"** and leads with Workshops and
  Webinars, beside the five intake forms.
- Redirect runbook: `EVENTS-SETUP.md` § 6b. **The rollback is removing the
  redirect** — under a minute, no deploy.

- **The staff Overview tab is the whole record, read-only** (v0.231.0, Doug's
  rule): facts left, driven by `EVENT_FIELDS` so a new spec field shows without
  a second edit; graphic + Summary + Full description + Syllabus right, rich
  text through the shared sanitizer. Every slot renders even when empty.
- **Phase 6a attendance** (`events/attendance.py`, worker): pulls each finished
  online event's Zoom participant report and matches by email. An empty report
  means "not published yet", never "nobody came"; a `Manual`/`Check-in` source
  is never overwritten; an attendee matching no registration is recorded flagged
  rather than dropped. **Never run against real Zoom.**
- **Phase 6b follow-ups** (`events/notify.py`): five sends as the shared info@
  identity, from EspoCRM templates. Once per registrant/event/kind, ledgered on
  `followUpsSent` **after** a successful send and enum-checked first. Preview is
  the default. **Needs five templates** — `EventReminder`,
  `EventRecordingAvailable`, `EventNoShow`, `EventMentorCTA`, `EventSurvey` —
  and has no frontend yet.
- **Phase 6c reporting** (`events/reporting.py`): the engagement **Events tab**
  (attendance rolled up across all of a client's contacts, deduplicated by
  event), the contact **Events tab** in the directory, and programme + conversion
  reports in `/events`. Conversion counts an attendee only when their engagement
  postdates their first attended event.
- **Registration recognition is designed, not built** —
  `prds/events/CBM_Events_Registration_Recognition_Plan.md` (Doug's rulings
  2026-08-17): recognise a returning registrant by a signed device token, else
  by an email-first lookup that **registers them and echoes nothing** (a public
  page that returns what we know is a harvester), else the normal form; a
  signed-in member is recognised through a **redirect handoff**, never by
  loosening the staff session cookie. CBM sends its own confirmation email.
  Prerequisite and live defect: the near-duplicate hold holds a person's *second
  webinar of the day* (`OPEN-ITEMS.md` 19f).
- **Phase 6d** `scripts/import_youtube_events.py` — playlist backfill, dry-run by
  default, importing **unpublished** because an upload date is not an event date.
  Never run against the real playlist.

- **⚠️ `CEvent` doubles as CBM's org calendar** — most rows are internal team
  meetings and mentoring-session mirrors. That is true **on crm-test (94 rows)**;
  **prod's `CEvent` is empty** because it was never connected to Google
  (verified 2026-08-08), so the first published event there will be a real one.
  Workshops share the entity, gated by
  **`publishToWebsite`** (default false). **That flag is the entire boundary to
  the public site** — every public read goes through
  `events/service._public_where`, and an unpublished event's page 404s rather
  than merely hiding. Never hand-roll a public CEvent query
  ([[events-publish-gate]]).
- **Zoom here is the explicit exception** to the mentor-sessions "user-supplied
  links only" ruling: the public webinar programme uses the CBM Zoom account via
  Server-to-Server OAuth (host `zweb@cbmentors.org`). Ask which world you're in
  before applying either ruling ([[zoom-user-supplied-only]]).
- **Vocabulary trap**: in the public payload `topic` means the event **TITLE**
  (Zoom/Apps-Script vocabulary); the category rides as `category`. Aligning the
  names would blank every title on the live site.
- **The live page restricts images** — it sends `content-security-policy:
  img-src 'self' data: https://drive.google.com https://*.googleusercontent.com`
  (measured 2026-09-11). Anything rendered INSIDE that page would have needed
  every event graphic and YouTube thumbnail proxied through the WordPress
  domain; hotlinked `i.ytimg.com` thumbnails also returned 503 there. Serving
  our own page sidesteps both, because our document carries no such policy —
  one of the reasons the plugin was struck.
- **`wp-plugin/cbm-events/` holds the two files the public pages run**: the
  renderer (`cbm-events.js`) and the site's **own stylesheet** (`cbm-events.css`,
  copied verbatim from the live page's Elementor widgets — keep it in sync, do
  not restyle it). The directory name is now historical; the plugin was struck,
  but these two files are how our pages look like the website, so they stay
  where they are. `/webinars/` and `/events/preview.html` both load them from
  this shipping location, which is what makes either a real check. **Neither
  `events/frontend/preview.css` nor `events/public_frontend/public.css` may
  style a contract class** — an approximation in one hid a live class-name drift
  for three weeks. Guard tests assert every class the renderer emits has a rule
  in the stylesheet, and that neither of our own sheets styles one. Both guards
  strip CSS comments first, since a comment naming a class is the opposite of
  styling it.
- **A per-event link comes from `CBMEvents.config.eventUrlBase`**, which the
  public programme page sets to `/webinars/`. The payload's `url` is now this
  app's own address for the event (derived from `APP_BASE_URL`), so it is
  usable rather than a 404 — but the renderer still takes the base from config,
  because a host serving these panels somewhere else needs its own. **Sign-up
  stays a modal on the calendar** (Doug, 2026-08-16); the event page is for
  reading, and carries its own form rather than the modal.
