# Changelog

All notable changes to **cbm-client-intake**. Versions are the value reported by
`/healthz` and the page footer (sourced from `pyproject.toml`), and double as the
deploy marker on App Platform.

## [0.31.0] — 2026-07-08

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
