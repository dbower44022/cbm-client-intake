# CLAUDE.md

Guidance for Claude Code working in the **cbm-client-intake** repository.
This file is read automatically at session start — it is the recovery anchor
if a session is lost. Keep the "Current status" section up to date.

## What this is

A custom web application for **Cleveland Business Mentors (CBM)**. It hosts
branded, multi-step wizard **intake forms**; a completed submission creates
linked records in EspoCRM (the system of record). Five forms ship today:

- **client-intake** — SCORE Mentor Request (FormAssembly form 111), reconciled
  to the CBM model. Creates Account → Contact → CClientProfile → CEngagement.
- **volunteer** — SCORE volunteer/become-a-mentor (form 6 / MR-APPLY). Creates
  a single Contact (Mentor) with an optional in-memory resume upload.
  **Form-required (v0.21.2, frontend only — deliberately NOT enforced in the
  Pydantic schema):** "How should we contact you?" (`contact_preference`), "Are you
  currently employed?" (`currently_employed`), and "How did you hear about CBM?"
  (`how_did_you_hear`) carry the `required` attribute + a required-asterisk; the
  wizard's `checkValidity()` blocks the step until they're chosen. Required in the
  form regardless of the CRM's own optionality; a direct API call may still omit them.
- **info-request** — generic request-for-information (single step). Creates a
  Contact (`cContactType=["Prospect"]`) with the message in `description`,
  plus an Account (`cClientStatus="Prospect"`) only when a company name is
  given. Repeat email = APPEND to the existing contact's description (uses
  *edit* on Contact — the API user's grant was VERIFIED live 2026-06-12).
  Verified end-to-end against crm-test 2026-06-12 (create + append + Account,
  all GET-verified); left 1 `ZZTEST-INFOREQ` Contact + 1 Account in crm-test
  to clean up in the UI alongside the older ZZTEST records.
  Also creates a dedicated **`CInformationRequest`** record (self-contained:
  name/first/last/email/phone/company/message/source/`requestStatus="New"`, plus
  `form`/`submitterEmail`/`description` mirroring the intake submission) linked to
  the Contact via `contact` and the Account via `infoRequestCompany` (FK
  `infoRequestCompanyId`), best-effort, on top of the description stamp + the
  CIntakeSubmission log (added 2026-06-20). **Built + VERIFIED LIVE against
  crm-test 2026-06-20** (create + both links + fields GET-verified, with and
  without company). Spec: `cinformation-request-entity.md`; crmbuilder program:
  `ClevelandBusinessMentors/programs/MN-InformationRequest.yaml`. Left ZZTEST
  records to clean up in the UI (see commit / chat).
- **partner** — Become-a-Partner (3-step). Creates Account
  (`cAccountType=["Partner"]`) → Contact (`cContactType=["Partner"]`) →
  CPartnerProfile (`partnershipStatus="Candidate"`, with `partnershipType` +
  `partnershipValue` from the form). Profile links: `partnerCompanyId` (Account),
  `primaryPartnercontactId` (Contact), + applicant added to the `contacts`
  hasMany. Added 2026-06-17.
- **sponsor** — Become-a-Sponsor (3-step). Creates Account
  (`cAccountType=["Donor/Sponsor"]`) → Contact (`cContactType=["Donor"]` — the
  enum has no "Sponsor" option) → CSponsorProfile (message in `description`).
  Profile links: `sponsorCompanyId`, `sponsorContactId`, + applicant added to
  the `sponsorContacts` hasMany. Added 2026-06-17.

**partner + sponsor status (2026-06-17): VERIFIED LIVE end-to-end against
crm-test.** Both orchestrators were run live (real `EspoClient`, not dry-run)
and the created records GET-verified: Account (`cAccountType` `["Partner"]` /
`["Donor/Sponsor"]`) → Contact (`cContactType` `["Partner"]` / `["Donor"]`) →
CPartnerProfile (`partnershipStatus="Candidate"`, `partnershipType` +
`partnershipValue` set) / CSponsorProfile (message in `description`), all link
FKs + the `contacts`/`sponsorContacts` hasMany relate confirmed. Tests green
(59 total). Orchestrators are the source-of-truth mapping. (One-off live check:
`scripts/verify_partner_sponsor_live.py`, untracked — writes real records.)
  1. ✅ **DONE** — `create` grant on `CPartnerProfile` + `CSponsorProfile` added
     to the intake API user's role (read + create now granted; verified live
     2026-06-17).
  2. ✅ **DONE** — `"Sponsor"` option added to `cContactType` (CRM, 2026-06-22);
     the sponsor orchestrator now writes `cContactType=["Sponsor"]`.
  3. ✅ **DONE** — `CIntakeSubmission.form` lists `Partner`/`Sponsor` (CRM,
     2026-06-22, **Title-case**). CRM is the source of truth, so the app conforms:
     `core/submission_log._FORM_VALUES` maps the partner/sponsor slug to
     `Partner`/`Sponsor` (the original three use the lowercase slug).
  4. ✅ **RESOLVED** — canonical Account link on `CPartnerProfile` is
     `partnerCompany` (populated bidirectionally; the alternate `account` link
     stays null). The orchestrator writes `partnerCompany` — correct.

  **Cleanup:** the live check left 6 `ZZTEST … GrantCheck` records in crm-test
  to delete in the EspoCRM UI (create-only API user can't): Partner set —
  Account `6a331a2de469f5cdb` + Contact `6a331a2e579820e91` + CPartnerProfile
  `6a331a2ea07850bb3`; Sponsor set — Account `6a331a2fa4d5d75fb` + Contact
  `6a331a300793cedba` + CSponsorProfile `6a331a3042ecfc111`.

This repo owns the *application*, not the business definition of the process.
The Client Intake process is defined by **MN-INTAKE** in the
`dbower44022/ClevelandBusinessMentoring` repo; the Requirements Spec here is
kept aligned to it by carry-forward.

## V2 (reliability) — `prds/v2/`

V2 makes the forms dependable: never lose a submission, keep working when the CRM
is down, deliver into the CRM exactly once with retries, alert on trouble. Specs:
`prds/v2/README.md` (executive), `CBM_Intake_V2_Requirements.md` (6 requirements),
`CBM_Intake_V2_Technical_Design.md` (durable-capture + async-worker architecture),
`CBM_Intake_V2_Operations_Guide.md` (activation runbook + day-to-day ops).

**LIVE in production since 2026-06-22 (against crm-test).** Both stages activated
end-to-end: `/healthz` → `durableStore:true`; the **`delivery-worker`** App
Platform component runs `python -m worker` (`async_delivery=True`); a submission
returns `received`+`reference` instantly and the worker delivers it (verified:
capture → idempotent replay → async deliver → `completed`; schema-drift check ran
on startup, 5 enums aligned). Infra: a DO **managed Postgres** (`cbm-db`, dev
tier) attached via the gitignored `.do/app.prod.yaml` overlay, which now also
carries the PRE_DEPLOY `migrate` job (`alembic upgrade head`), the worker, and
`DATABASE_URL`/`ASYNC_DELIVERY=true` on web + worker. **Gotcha:** DO's
`DATABASE_URL` ends in `?sslmode=require`, which asyncpg rejects — `core/store.py`
`make_async_engine` strips `sslmode`/`channel_binding` and sets SSL via
`connect_args` (this broke the first Stage A deploy; fixed in commit 75ef018).
Rollback is instant via the overlay (`ASYNC_DELIVERY=false` → sync; drop
`DATABASE_URL` → V1). Optional: set `ALERT_WEBHOOK_URL` on the worker for Slack
alerts (else WARNING logs). Cleanup: Stage A/B verification left ZZTEST records in
crm-test (Contacts/CInformationRequests/CIntakeSubmissions, ids `6a38c48f…`,
`6a38c636…`, `6a38c6d8…`).

**Phase 0 — durable capture, scaffolded 2026-06-21 (gated, no-op until a DB is
attached).** `core/store.py` (`PostgresStore`/`make_store`, the `submission`
table), wired into `core/app.py`: when `DATABASE_URL` is set, every submission is
captured to Postgres BEFORE any CRM call and idempotency is enforced durably (the
`uq_submission_form_token` unique key replaces the in-memory dict); still
processes synchronously. Empty `DATABASE_URL` ⇒ exact V1 behavior, so prod is
unchanged until the DB is provisioned. Alembic migration in `alembic/`
(`0001_create_submission`); local Postgres via `docker-compose.yml`. `/healthz`
reports `durableStore`. Verified end-to-end against a local Postgres (capture →
complete, idempotent replay = one row, honeypot captured `held_honeypot`).
**To activate:** attach DO Managed Postgres, set `DATABASE_URL`, run
`alembic upgrade head` (pre-deploy).

**Phase 1 — asynchronous delivery, scaffolded 2026-06-21 (gated by
`ASYNC_DELIVERY`, default false).** With the flag on (and a store), the accept
endpoint returns `received`+`reference` as soon as the submission is captured;
the **worker** (`worker.py`, run as `python -m worker`) claims due rows
(`claim_batch` = `FOR UPDATE SKIP LOCKED`, with a **lease**: a claimed row gets
`locked_until = now + worker_lease_seconds`, default 900s; a `processing` row
whose lease has expired — i.e. a worker that died mid-delivery — is reclaimed on
the next claim, so a crash/redeploy can't strand a submission in `processing`
forever. Safe because delivery is resumable. Added 2026-06-23, Alembic migration
`0002_processing_lease`), delivers them via the orchestrators,
and retries transient failures with backoff (1m/5m/30m/2h/6h, `MAX_DELIVERY_ATTEMPTS`,
then `needs_attention`); 4xx = permanent. Delivery is **resumable**
(`core/resumable.py` `ResumableClient` records each create/upload in the
`progress` column and skips it on retry) so a half-finished chain converges to
one complete set — no orchestrator changes needed. The `CIntakeSubmission`
Normal/Error log moves to the worker in async mode. Flag off = Phase 0
(synchronous). Form registry: `forms.ALL_SPECS`/`SPECS_BY_SLUG`. Worker component
+ pre-deploy migration documented (commented) in `.do/app.yaml`. Verified
end-to-end against local Postgres (async accept → pending → worker delivers →
completed).

**Phase 2 — operations console, scaffolded 2026-06-22; retitled **Submission
Admin** + own gate v0.30.0.** A staff-only view of the
durable store at **`/ops`** (`ops/` package), using the shared staff session
(sign in at the portal `/`) with a per-request gate on **`OPS_ALLOWED_TEAMS`**
(default `Marketing Admin Team`; admins pass) and
mounted only when `assignments_active`. `GET /ops/api/submissions` (filter by
status/form) + counts; `GET /ops/api/submissions/{id}` (payload/progress/error);
`POST /ops/api/submissions/{id}/redrive` (→ pending, due now, attempts reset — the
worker re-runs it resumably). Store gains `list_submissions`/`get_submission`/
`counts_by_status`/`redrive`; the store is exposed via `app.state.submission_store`.
Endpoints 503 if no store. Linked from the portal for Marketing-Admin members.
Verified
against local Postgres (list/counts/redrive) + console wiring (serves, 401 unauth).
Phase 3 (alerting + schema-drift) is next.

**Phase 3 — monitoring + alerting, scaffolded 2026-06-22.** The worker runs two
periodic checks (own timers, no cron dependency): (1) **alerting** —
`core/monitoring.run_alert_check` reads `store.metrics()` (counts, backlog,
oldest-pending age, avg latency) and alerts when `needs_attention` ≥ threshold or
the oldest pending exceeds `ALERT_PENDING_AGE_MINUTES`, with a per-alert cooldown;
(2) **schema-drift** — `run_schema_drift_check` fetches live enum options
(`EspoClient.metadata_enum_options`) and compares against `core/schema_contract.py`
`EXPECTED_ENUMS`, alerting when a value the forms rely on has gone missing.
Alerts post to `ALERT_WEBHOOK_URL` (Slack-compatible) or log at WARNING. The ops
console gains `GET /ops/api/metrics` + a backlog/needs-attention summary line.
Verified: alert thresholds + cooldown + drift diff (unit), and the drift check
run **live against crm-test** (all 5 contract entries aligned, no false alerts).
**This completed the V2 build (Phases 0–3) — now ACTIVATED LIVE (see the LIVE
block at the top of this section).**

## Mentor Admin tool — `/mentoradmin` (added 2026-06-22)

**User-facing page title: "Mentor Administration"** (the package/route stay
`mentoradmin`/`/mentoradmin`; retitled 2026-06-22 — pairs with `/assignments`'s
"Client Administration").

A second **staff-only** tool (NOT a public form), in the same FastAPI app
(`mentoradmin/` package), mounted only when `SESSION_SECRET` is set (shares the
`assignments_active` gate + SessionMiddleware). **Sign-in is the portal's
(v0.30.0)** — one shared staff session (`assignments.auth.SESSION_KEY =
"staff_user"`); this app enforces the **Mentor Administration Team** gate **per
request** (`_require_user` → `is_member`; 403 names the team, admins pass).
It lists the **full mentor roster** (reuses
`assignments.service.list_all_mentors` — same searchable/filterable/sortable grid
as "Available Mentors", any status), and lets staff **open any mentor** to a
detail screen that reviews all info (read-only computed totals on top) and
**edits status + any editable field**, saving back to `CMentorProfile`.

- **Auth = per-user, acts as the logged-in user**: the portal login (EspoCRM
  `App/user`) put the user's token in the shared signed session cookie; all
  reads/writes run as that user so EspoCRM enforces their ACL on CMentorProfile.
  Gate is **Team-only, per request** (`MENTOR_ADMIN_ALLOWED_TEAMS`, default
  `Mentor Administration Team`); admins always pass; 401 → the frontend
  redirects to `/?next=/mentoradmin/`. Session-expired (CRM 401) →
  clears session + 401 (same `auth.session_expired` handling).
- **Editable-field set is declared in `mentoradmin/service.py:EDITABLE_FIELDS`**
  (the single source for both the form layout — grouped Profile/Contact/Status/
  Capacity/Expertise/Compliance/Departure/Bio — and the server-side update
  **whitelist**: `update_mentor` drops anything not in `EDITABLE_NAMES`).
  **Contact tab (v0.29.0):** fields marked `entity: "Contact"` (firstName/
  lastName/emailAddress/phoneNumber/addressStreet/City/State/PostalCode) live on
  the mentor's **linked Contact record** — `get_mentor` merges them into the
  detail response and `update_mentor` routes their changes to the Contact
  (phone normalized to E.164 via `core.phone.to_e164`; no linked Contact ⇒
  `MentorAdminError` raised **before any write** → a 400 with the exact reason).
  Enum/multi-enum
  **options are pulled live** from EspoCRM metadata (`GET /Metadata?key=
  entityDefs.CMentorProfile.fields`, via `EspoClient.metadata`) so the CRM stays
  the source of truth — see `service.field_options`. Computed totals
  (`availableCapacity`, `currentActiveClients`, `total*`) are read-only context.
- **Endpoints** (`/mentoradmin/api`): `login`/`logout`/`session`; `GET /mentors`
  (roster); `GET /fields` (EDITABLE_FIELDS + live options); `GET /mentors/{id}`
  (full record); `PUT /mentors/{id}` `{changes:{...}}` (whitelisted update);
  `POST /mentors/status-check` (the "Update Mentor Status" sweep, v0.26.0 —
  see the Current-status bullet: verifies each mentor's login User exists/is
  active + the `@cbmentors.org` mailbox exists, and bulk re-syncs
  `recordStatus`; `service.verify_all_mentor_statuses`).
  Frontend: `mentoradmin/frontend/` (vanilla JS, no build step). Detail view =
  a compact read-only summary card (status, accepting, email/phone/address,
  capacity/session metrics) + a tabbed editor (one tab per field `group`;
  optional `row` sub-groups fields, e.g. Compliance checks vs dates). Generic
  type-driven renderer: enum→select (static `options` allowed, e.g. how-heard),
  multiEnum→checkbox grid, bool→checkbox, int/date, text→textarea,
  wysiwyg→contenteditable rich-text editor (toolbar + `sanitizeHtml` on load).
  **Save sends only the fields the user actually changed** (diffed against a
  per-field snapshot taken at render): re-sending an *unchanged* value that has
  since drifted out of its CRM enum options would make EspoCRM 400 the whole
  update. (This was the cause of a live approval failure 2026-06-22 — crm-test's
  `mentorStatus`/`industrySector` enums had drifted, so a mentor's stale stored
  values 400'd on re-save; see [[crm-test-schema-drift]].) `_crm_failure` logs
  the full CRM error body so such rejections are diagnosable from the run logs.
  The frontend re-baselines the snapshots after each save (so reverting a field
  to its render-time value is still detected), and **always submits on Save**
  (even with no field changes) so the server-side reconciliation below runs.
  On Save, a **client-side pre-check** (`pendingCompletenessIssues`, mirroring the
  server rules from the form values) pops a **styled confirm modal** ("Save
  anyway?" / Cancel) listing what's still missing; it **omits the User/login
  assignment checks** (the save auto-creates/reconciles those, so warning about
  them would be a false alarm). Cancel = stay in edit, no save.
- **Data-completeness badge + save-time user-link reconciliation (added
  2026-06-22).** The detail header shows a **Complete/Incomplete** badge
  (`service.check_completeness`, attached to the detail GET + save response by the
  router; click it for the reasons). A mentor is Complete when: a Contact is
  linked (the `CMentorProfile` *is* the "CBM member" record), and ethics /
  training / terms are all true (**background check is optional — not required**);
  plus, **if Active**, a CBM email address + a User assigned to the member AND the
  same User to its Contact. **`publicProfile` is not part of completeness** (v0.23.1
  — removed the publicProfile-gated About/expertise checks; the field stays an
  editable bool on the Status tab). On **every save**,
  `service.reconcile_user_links` (best-effort) assigns the mentor's User
  (`CMentorProfile.assignedUser`, or the Contact's if only that side has one) to
  **both** the member and its Contact — filling the gap provisioning leaves (it
  sets the member's User only) and self-healing one-sided assignments, so the
  "no User assigned to the Contact" completeness issue auto-resolves on save.
  The computed status is **persisted** to the CRM `recordStatus` enum
  (`Complete`/`Incomplete`; a manual `Duplicate` is preserved, never overwritten)
  **on save AND on view** when it changes (`service.sync_record_status`), so the
  stored value self-heals whenever it drifts (v0.22.1 — previously persisted only
  on save, so a record made complete outside a save-through-this-tool stayed stale
  in the grid; e.g. prod's Douglas Bower read Incomplete in the grid but Complete
  on the detail badge). `sync_record_status` writes **only when the value actually
  changed**, so a view corrects a drifted record once then is a no-op (one
  modifiedAt/modifiedBy bump on the correction, not on every view). The detail GET
  returns the reconciled status, and the frontend reloads the roster on return when
  it changed. The **roster grid** shows a **Record** column + filter (read from the
  stored field) to spot who needs work without recomputing per row. `recordStatus`
  is in the shared `assignments` mentor row.
- **Approval → user provisioning (added 2026-06-22; privilege model fixed
  2026-06-22).** When a save leaves `mentorStatus` at **`Approved` or `Active`**
  (a mentor set straight to Active skips Approved but still needs a login) with
  **no
  linked login user yet** **and `MENTOR_PROVISION_USERS` is on** (recovery-
  friendly: fires whether this save flips the status to Approved OR the mentor
  was already Approved but a prior attempt failed to create the user),
  `service.update_mentor` provisions a login: creates an EspoCRM **User**
  (`userName` = `emailAddress` = `firstname.lastname@cbmentors.org` — the CBM
  email, reusing the profile's `cbmEmail` if already set; `type=regular`,
  `isActive=true`, `sendAccessInfo=true` for the welcome email), places it in the
  **`MENTOR_TEAM_NAME`** team (default `Mentor Team`), links it to the profile as
  `assignedUser` (the same link the assignment tool reads), and back-fills
  `cbmEmail` when blank. **Privilege split (the key design point):** EspoCRM makes
  **User creation admin-only — API keys/`api`-type users CANNOT create Users (no
  role grants it)**, confirmed against EspoCRM docs. So User read/create + Team
  lookup run as a **DEDICATED ADMIN service account** — the router builds an async
  `admin_client_factory` (`_provision_factory`) that logs that account in via the
  `App/user` token flow (`auth.login_token`, no ACL gating) and yields a client
  via `EspoClient.for_user_token`. This is **NOT the staff user's token and NOT
  the create-only `customapps` API key** — so **Mentor Admin staff stay non-admin
  and need no user-create rights**; only the profile read + `assignedUser`-link
  write use the staff token (which they already can do). The factory is awaited
  lazily (login only happens on an actual approval transition). **Off by default**
  (`mentor_provision_users=False`): with it off, approval just saves the status
  (no provisioning, no error) — this is what fixed the original 504 when a
  non-admin staffer approved. Best-effort: failures (login rejected, missing
  permission, team not found → reports available team names) return a
  `provision:{ok:false,error}` summary shown in the UI without rolling back the
  saved status. userName collisions get a numeric suffix (`…2@…`). Re-saving an
  already-Approved mentor, or one with a user, does nothing.
  **ENABLED + VERIFIED LIVE 2026-06-22** against crm-test: a dedicated admin
  EspoCRM user (`mentoradminuser@cbmentors.org`, **Type=Admin**) was created, its
  username/password set in the gitignored overlay (`ESPO_PROVISION_USERNAME`/
  `ESPO_PROVISION_PASSWORD` + `MENTOR_PROVISION_USERS=true`, on the **web**
  component), and approving a mentor in `/mentoradmin` provisioned a User
  end-to-end (verified in the run logs: status PUT → `App/user` login
  `type=admin` → `Team?name=Mentor Team` → `POST /User 200` → `assignedUser`
  link). **Gotcha that cost time:** an `api`-type user can't create Users, and a
  *regular* user (even with roles) 403s — the service account's **Type must be
  Admin** (not just a role). Still worth a real check: the `sendAccessInfo`
  welcome-email actually *delivering* (POST returned 200, SMTP delivery not
  confirmed) and the CBM-email mailbox existing. The live script's `MA_APPROVE`
  path provisions via the admin's own token (run it as an admin).
  **Cleanup:** the live verification created real test User accounts in crm-test
  (e.g. for mentor `6a2f137fa58eea5a3` with `cbmEmail=jb@gmail.com`, and
  `6a3616686904f6449`) + left those mentors Approved — delete in the EspoCRM UI.
- **Status (2026-06-22): built; 119 tests green (10 new); TestClient sanity OK
  (serves, 401 unauth, index link).** NOT yet deployed/verified live — needs the
  `MENTOR_ADMIN_ALLOWED_TEAMS` default to match a real crm-test Team (defaults to
  `Mentor Administration Team`; confirm it exists / users are members) and a live
  edit check. No new deploy secret strictly required (web+worker already carry
  `SESSION_SECRET`); set `MENTOR_ADMIN_ALLOWED_TEAMS` in the overlay only to
  override the default.

## Mentor Assignment tool — `/assignments` (added 2026-06-19)

**User-facing page title: "Client Administration"** (the package/route stay
`assignments`/`/assignments`; retitled 2026-06-22 — it's gated by the
`Client Administration Team`, hence the name).

A **staff-only** dashboard (NOT a public intake form) that lives in the same
FastAPI app (`assignments/` package, mounted only when `SESSION_SECRET` is set —
see `Settings.assignments_active`). It lists `CEngagement` records with
`engagementStatus="Submitted"` in a grid; each **unassigned** row has a dropdown
of mentors **accepting new clients** and, on confirm, assigns the engagement to the
chosen mentor. A row whose engagement **already has a mentor**
(`CEngagement.mentorProfile`) shows the **assigned mentor's name** instead of the
picker/Assign button (so filtering to Active/Pending Acceptance etc. shows the
mentor, not a redundant control); `list_engagements` returns `mentorId`/`mentorName`
(v0.23.0).

- **Auth = per-user, acts as the logged-in user.** Staff sign in **once at the
  portal `/`** (v0.30.0 — `POST /api/portal/login` → EspoCRM `App/user` with the
  `Espo-Authorization` header; the per-app login endpoints are gone). The
  returned auth token is kept in the shared signed session cookie and replayed
  (`Espo-Authorization` + by-token header) so
  **all reads/writes run as that user** — EspoCRM enforces their ACL and records
  them as modifier. This app's gate runs **per request** (`_require_user`):
  admin, an allowed **Team** (`ASSIGN_ALLOWED_TEAMS`, the primary gate — set to
  `Client Administration Team`), OR an allowed Role (`ASSIGN_ALLOWED_ROLES`);
  403 names the required team, 401 → the frontend redirects to
  `/?next=/assignments/`.
  **Gate by Team, not Role:** a regular user's own token can read its `teamsNames`
  but NOT its `rolesNames` (EspoCRM strips role names for users without Role-scope
  read — verified live: a valid non-admin login returned `roles=[]`). (The shared
  `customapps` API user is NOT used here — create-only, and it can't even read
  Teams/Users/Roles.)
- **Mentor dropdown** = `CMentorProfile` where `acceptingNewClients=true` AND
  `mentorStatus="Active"` AND `assignedUser` set. The mentor's login User =
  `CMentorProfile.assignedUser`. (An empty dropdown = no mentor passes all
  three — diagnosed live 2026-07-06: crm-test had 0 eligible, prod 4.)
- **"Review Mentors" (Available Mentors) grid** (reworked v0.24.0; analytics
  v0.27.0): columns Mentor/Status/Type/Accepting/Active Clients/Max Clients/
  Available/Assigned (30d)/Lifetime/Industry Experience/Areas of Expertise.
  Client counts are app-computed from CEngagement (see the v0.27.0 bullet in
  Current status); the "Has capacity" checkbox + the assign dropdown's
  "(capacity N)" label use the computed Available (= max − active). Filters:
  Industry Experience + Areas of Expertise (match any of the mentor's values).
  Dialog defaults to ~96vw.
- **Status filter** — the grid has a multi-select (the full `engagementStatus`
  enum, `service.ENGAGEMENT_STATUSES`); `GET /assignments/api/engagements` takes
  repeated `?status=` params (`in` filter), defaulting to `Submitted`.
- **Assign action** (`assignments/service.py:assign_engagement`): set the
  engagement's `assignedUser` + `mentorProfile` (the "assigned mentor" field) and
  `engagementStatus="Pending Acceptance"`; then set `assignedUser` to the mentor's
  user on every related Contact (`primaryEngagementContact` + `engagementContacts`),
  the `engagementClient` (CClientProfile), and `clientOrganization` (Account, when
  present). Source-of-truth mapping is the service module.
- **CRM schema** (read live from crm-test 2026-06-19): `engagementStatus` enum has
  `Submitted`/`Pending Acceptance`; `CEngagement.mentorProfile` belongsTo
  CMentorProfile; `CMentorProfile.acceptingNewClients` (bool) +
  `availableCapacity`/`currentActiveClients`/`maximumClientCapacity` (int).
- **Status (2026-06-19): built; 72 tests green; DEPLOYED LIVE on App Platform
  against crm-test; full path VERIFIED end-to-end.** Login (admin + non-admin
  `kitty.cat` via `Client Administration Team`), read path (7 Submitted
  engagements; eligible mentors), AND a real assignment all confirmed live: the
  mentor lands in the engagement's `assignedUsers`, status → Pending Acceptance,
  `mentorProfile` set, related contacts/CClientProfile/Account reassigned. One-off
  live checker: `scripts/verify_assignment_live.py`.
- **Deploy-time secrets** (encrypted App Platform env, gitignored
  `.do/app.prod.yaml`, applied with `doctl apps update <app-id> --spec ...`):
  `SESSION_SECRET` (required to enable), `ASSIGN_ALLOWED_TEAMS`
  (`Client Administration Team`), optionally `ASSIGN_ALLOWED_ROLES`, keep
  `SESSION_COOKIE_SECURE=true` in prod. See `.env.example`. (NOTE: crm-test DOES
  have Teams — the create-only API user just can't see them, so an earlier
  `Team` API list returned 0.)
- **Assignment field differs by entity** (verified live, the source of a fixed
  bug): Contact/Account use the single `assignedUser`; **CEngagement and
  CClientProfile have `assignedUser` DISABLED and use the multi-user
  `assignedUsers` (collaborators) field** — so the service writes
  `assignedUsersIds=[userId]` to those two and `assignedUserId` to Contact/Account
  (`assignments/service.py:_assigned_user_payload`). Writing `assignedUserId` to a
  disabled-field entity is silently ignored.

## Session Management tools — `/mentorsessions`, `/partnersessions`, `/sponsorsessions` (added 2026-07-08)

**One configurable engine, three team-gated routes.** Mentors, Partner Managers,
and Sponsor Managers each review the records they own and record **meetings**
against them as **`CSession`** records. It is **one `CSession` entity with the
parent link swapped** — the domains differ only by a per-domain
`sessions/config.py:DomainConfig` (the `sessionType` discriminator + the parent FK
distinguish them). The whole feature is one engine (`sessions/service.py`) + one
router factory (`sessions/router.make_router`) + one shared frontend
(`sessions/frontend/`, vanilla JS that derives its domain/API base from the first
segment of its own URL). Mounted only when `assignments_active` (needs
`SESSION_SECRET`), linked from the portal per team.

- **The three domains** (source of truth: `sessions/config.py`, `DOMAINS`):
  | slug | parent | "records I own" reverse link on the user's `CMentorProfile` | co-mentor? |
  |------|--------|-------------------------------------------------------------|------------|
  | `mentorsessions` | `CEngagement` | `engagements1` (reverse of `CEngagement.mentorProfile`) | yes |
  | `partnersessions` | `CPartnerProfile` | `managedPartners` (reverse of `CPartnerProfile.partnerManager`) | no |
  | `sponsorsessions` | `CSponsorProfile` | `managedSponsors` (reverse of `CSponsorProfile.cBMSponsorManager`) | no |
  Mentor sessions restrict the owned list to active engagement statuses
  (`Active`/`Assigned`/`Pending Acceptance`/`On-Hold`, filtered in Python).
- **All three managers are `CMentorProfile` records** — the one whose
  `assignedUser` is their login. `service.resolve_manager_profile` scans the
  `CMentorProfile` rows readable by this user and **matches `assignedUser` in
  Python — never a `where` on `assignedUserId`** (prod's field ACL forbids it; see
  [[crm-test-assignment-acl-fields]]). Then it reads the owned parents through the
  domain's reverse link (`list_related` on the profile), so a regular user whose
  ACL scopes `CMentorProfile`/the parents to "own" simply gets their own rows.
  `list_records` returns `{"records":[...], "profileFound": bool}` —
  `profileFound=false` means the user has no linked profile.
- **Auth = per-user, acts as the logged-in user.** Portal SSO (shared staff
  session `staff_user`); each route enforces **its own team per request**
  (`_require_user` → `is_member`; 401 → frontend sends the user to the portal, 403
  names the team, admins pass). Teams: `SESSION_MENTOR_ALLOWED_TEAMS` (default
  `Mentor Team`), `SESSION_PARTNER_ALLOWED_TEAMS` (default `Partner Management
  Team`), `SESSION_SPONSOR_ALLOWED_TEAMS` (default `Sponsor Management Team`).
- **Endpoints** (`/{slug}/api`): `GET /session` (identity + domain UI config, incl.
  `detailTabs` + `emptyMessage`); `POST /logout`; `GET /records` (owned parents as
  grid rows); `GET /fields` (`SESSION_FIELDS` spec + live enum options + required);
  `GET /records/{parent_id}` (the tabbed **detail** payload — Overview facts +
  aggregated note feed + overall notes + next session + contacts + sessions,
  +co-mentors on mentor); `GET /details/{parent_id}` + `PUT /details/{entity}/{id}`
  (the **Details** tab — summary strip + editable company/profile sections +
  contact tables); `GET /contacts?q=` (add-contact picker search) +
  `POST /records/{parent_id}/contacts` (link an existing contact or
  create-and-link a new one — the + Add flows);
  `GET /peek/{entity}/{record_id}` (pop-up detail, entity-allowlisted);
  `GET /sessions/{id}`; `POST /records/{parent_id}/sessions` (create);
  `PUT /sessions/{id}` (whitelisted update + attendee sync). Mentor-only:
  `GET /mentors` (co-mentor picker) + `POST /records/{parent_id}/comentors` (attach
  a `CMentorProfile` via `additionalMentors`).
- **Editable-field set = `sessions/config.py:SESSION_FIELDS`** — the single source
  for both the type-driven editor layout (grouped Session/Notes, optional `row`
  sub-groups) and the server-side update **whitelist** (`SESSION_EDIT_NAMES`;
  `_session_payload` drops anything else). Enum/multiEnum **options are pulled live**
  from CRM metadata (`service.field_options`). **Editor layout (v0.32.3):** the two
  most important fields — `sessionNotes` + `nextSteps` — carry `big: True` and share
  a `row`, rendering as large side-by-side rich-text editors (`.cbm-field--big`);
  the meeting **End date was removed**; Status/Session type/Start share one line.
  **Duration (v0.34.1):** `CSession.duration` is EspoCRM's *virtual* duration type
  (notStorable, = `dateEnd − dateStart`, preset choices 5m–3h read from metadata,
  default 1h) — the editor's **Duration** select (Status/Type/Start/Duration on one
  line) is translated by the frontend into a recomputed `dateEnd` on save (moving
  Start preserves the duration); `SESSION_EDIT_NAMES` excludes `duration` and
  whitelists `dateEnd` instead. Duration displays on the Overview session-summary
  cards (next to the date), the Sessions-tab table (own column), and the read-only
  session view (KV grid); a session without `dateEnd` shows none. Verified in the
  stub harness, not yet live.
- **Attendees are a RELATIONSHIP, not a select-field (the v0.32.2 fix; see
  [[espo-custom-linkmultiple-is-a-relationship]]).** `sessionAttendees` (→ Contact)
  is read via the link (`service._attendees` → `list_related`) and written via
  **relate/unrelate** (`service._sync_attendees` diffs current vs. submitted) —
  exactly like co-mentors' `additionalMentors`. Reading `sessionAttendeesIds` off
  the record ALWAYS returns empty and setting it on an update is silently ignored,
  which is why attendees "didn't save" (write) and "didn't show" (read) until this
  fix; both the editor and the note feed now use the link read. The editor picker is
  over the parent's related contacts; `attendees=None` on edit = leave untouched,
  `[]` = clear. `EspoClient.unrelate` (relationship DELETE) was added for this.
- **Owner-stamping so a read-own role can see its own new session (the fix
  2026-07-08).** These tools run under roles whose `CSession` read/edit scope is
  `own`, so an **unassigned** new session would be invisible to its own author
  right after create. `create_session` stamps the creating user
  (`owner_user_id=user["userId"]` passed from the router) as **both**
  `assignedUserId` **and** `assignedUsersIds` (CSession has both, like CEngagement)
  so it sticks whichever the instance uses. `setdefault`, so an explicit assignment
  in `changes` wins. **Live-testing caveat (2026-07-08):** the fix only makes
  *newly-created* sessions visible to their author. Under read-own, a **pre-existing**
  session (from seed/migration, or created by staff/a co-mentor) stays invisible
  until its `assignedUser`/`assignedUsers` includes the viewer — so a mentor does
  **not** automatically see every session on their engagement. If that's the desired
  UX, the gate role's `CSession` read needs to be broader than plain `own`
  (parent-based ACL) — a CRM-side decision, not an app change.
- **Enum-drift resilience on save (2026-07-08, two layers; [[non-required-enums-never-block]]).**
  A session's stored enum value can fall outside the field's live options (seed data
  put meeting-modality strings like `In-Person`/`Video Call` into `sessionType`,
  whose real options are `Client Session`/`Partner Session`/`Sponsor Session`/`Other
  Session`); re-sending it would make EspoCRM 400 the whole update
  (`validationFailure`, `sessionType:valid`). (1) **Frontend** (`app.js`): the editor
  snapshots each field at render (`snapshotForm`) and `saveSession` sends only the
  fields the user actually changed, so an untouched drifted enum never enters the
  payload. (2) **Server** (`service._sanitize_enum_payload`, on create + update):
  drops enum/multiEnum values not in the live options before the CRM call — single
  enum omitted (preserves the stored value on update), multiEnum keeps only the valid
  members; **fails open** if options can't be fetched. The domain `default_session_type`
  values are all valid options, so new sessions get a valid type.
- **Required fields enforced from CRM metadata (2026-07-08).** `CSession.dateStart`
  is required; the editor reads which fields the CRM marks required
  (`service.field_required` → `/fields` → the frontend), renders a `*`, and blocks
  Save with a readable "Please complete: …" message instead of surfacing a raw CRM
  400 (`validationFailure`, `dateStart:required`). Metadata-driven, not hard-coded,
  so any required field is caught.
- **Session name: default pre-filled, user value wins (2026-07-08).** `CSession`
  has a before-save **name formula**; left unconditional it overwrites whatever the
  app sends. The editor pre-fills a default title (`YYYY-MM-DD - <parent name>`,
  `defaultSessionName` in `app.js`) so the user sees what will be stored, and
  **create sends every field** (name verbatim; update still diffs). **CRM
  prerequisite:** the name formula must be *keep-if-present* —
  `ifThen(name == null || name == '', name = <expr>)` — so a supplied/edited name
  survives; otherwise the formula clobbers it.
- **CRM ACL prerequisite — `CSession` must have a working owner field (2026-07-08,
  live).** With the gate role's `CSession` read = `own`, EspoCRM ACL-checks the
  **read-back** that a create does to return the new record: if the record isn't
  owned by the creator, the **create itself returns 403** (and it's invisible in
  lists). Fix is CRM-side: enable an assignment field `read-own` credits — **enable
  `assignedUsers` (collaborators) on `CSession`, as `CEngagement` has** (its single
  `assignedUser` is disabled — the app's `assignedUserId` write is ignored, but
  `assignedUsersIds` sticks). With assignment enabled, the owner-stamp makes the
  creator the owner → create 200 + the session shows. This was the "created but
  doesn't show" + "403 on create" chain in live testing — resolved CRM-side.
- **Detail view — tabbed & information-dense (redesigned v0.32.0–.3).** Opening a
  record shows a tab bar common to all three domains (`/session` → `detailTabs`,
  `router.COMMON_DETAIL_TABS`): **Overview · Details · Sessions · Communications ·
  Documents**. Overview + Details + Sessions are built; **Communications** has a
  built email-inbox UI (scaffold only — no CRM email data yet; see the
  Communications bullet below for the wiring contract); **Documents** is still a
  "coming soon" placeholder. The tab bar is built by the frontend from config
  (placeholder tabs get a generic panel); the standalone Contacts tab folded into
  Overview / Details.
  - **Overview** (`get_detail` → `_overview_items`, `sessions/config.py:OverviewItem`):
    a full-width **facts-rail-left / note-feed-right** layout with a drag **splitter**.
    Rail: key facts (status badge, a single aggregated **Company** link, primary
    contact, meeting cadence, referring partner), session activity + focus areas,
    **Other contacts + CBM Contacts** (co-mentors relabelled), then the mentoring
    need. The **Company** link aggregates the Account **and** its profile
    (client/partnership/sponsor) into ONE `/peek` pop-up (`OverviewItem.aggregate`);
    contact / referring-partner links open their own. **Overall notes**
    (Engagement/Partner/Sponsor Notes, `overall_notes_*`) sit above an aggregated
    **session-notes feed** — every session's notes + next steps, most-recent-first,
    stamped with date/time + **attendees**. A bold **Next session** callout
    (soonest upcoming session, derived) with a **Start / Open Session** button:
    launches `videoMeetingLink` in a new tab when present, then opens the session
    for editing.
  - **Details** (`sessions/details.py`, `DomainConfig.details_entities`;
    **rebuilt to the approved mockup v4, v0.33.0** — design target:
    `prds/Details Screen files2/engagement-details-mockup-v4.html`, prompt
    `edit-engagement-details-ui-prompt-v0.2.md`): single column, top to bottom —
    (1) a slim **summary strip** for the parent record (Status navy pill +
    Started / Mentor / Cadence / Sessions + every other informative scalar field;
    long-form text stays on Overview/edit; the strip's Edit opens the full form);
    (2) **Company** + **Client Business Profile** cards as a **two-column labeled
    row grid** — Company: directory block + Business / Shipping-when-different
    rows, Account / Cadence / Announcements-"Not allowed" badge right; profile:
    Entity / Revenue / Sells / On-file rows + Certifications / Funding chips +
    the quoted Client goal; uncurated informative fields still render as generic
    labeled rows (columns balanced); (3) **Client Contacts** — ALL related
    contacts in one table (Name / Role chips / Phone / Email / City / Contact via
    / **one Agreements badge** — green "Complete" or red "N pending" across the
    three acceptance bools); (4) **CBM Contacts** table (mentor domain) — the
    assigned mentor (`CEngagement.mentorProfile`) + co-mentors
    (`additionalMentors`), each resolved through the profile's `contactRecord`
    Contact for phone/email (schema verified live 2026-07-10: no other
    staff/person link exists on CEngagement). **No page-global edit bar** — the
    strip, each card, and each contact row edit independently (per-row Edit
    expands the full contact form inline under the row). **+ Add** on Client
    Contacts = *Select existing* (live `GET /contacts?q=` search; relates via the
    domain's contacts link — `engagementContacts`/`contacts`/`sponsorContacts` —
    and backfills `Contact.account` only when the contact has no company) or
    *Create new* (full contact form; `POST /records/{id}/contacts` creates +
    links in one compound write, company stamped at create); CBM + Add = pick an
    existing mentor profile (via `additionalMentors`; new CBM people are
    onboarded through `/mentoradmin`, so no create-new there). **Remove
    (v0.39.0):** every client-contact row and every co-mentor row gets a
    two-step-confirm Remove ("Remove" → "Really remove?") that detaches the
    relation only — `DELETE /records/{id}/contacts/{contactId}` /
    `DELETE /records/{id}/comentors/{profileId}` (mentor-only, like the add);
    the contact/profile record stays in the CRM. The assigned Mentor row is
    never removable (that link is Client Administration's); Remove shows only
    when the user can edit the PARENT record (the unrelate is a parent write —
    gated on the parent section's per-record `editable`). Fields are read
    **live from CRM metadata** (filtered to editable scalars; humanized labels —
    `cBMValueProvided` → "CBM Value Provided"); view hides empties/"No" (except
    meaningful negatives), edit exposes every editable field.
    **Permission-aware:** reads the user's ACL (`EspoClient.app_user` →
    `acl.table`) and, for `edit:own`, checks **per-record ownership**
    (assignedUser/assignedUsers) — read-only records show no Edit, saves are
    per-entity with a plain-language 403 message (enum drift dropped).
  - **Peek** (`service.peek`, `PEEK_FIELDS` allowlist: Contact/Account/CClientProfile/
    CPartnerProfile/CSponsorProfile): a read-only pop-up; the aggregated Company link
    fetches each member and renders titled sections.
  - **Friendlier empty grid** (`DomainConfig.empty_message`): "No client engagements
    / partners / sponsors found" — no "ask an administrator" alarm (past the team
    gate = you have permission); a Refresh picks up newly-assigned records (the
    manager profile is re-resolved each `/records` call).
  - **Communications tab — Gmail conversation integration (BUILT v0.35.0,
    2026-07-10; gated OFF by `GMAIL_SYNC` until activated).** Plan:
    **`prds/communications-gmail-integration.md`**; CRM build handoff:
    **`cconversation-entity.md`**. The app side is complete: `core/gmail.py`
    (delegated per-mailbox Gmail client — subject ALWAYS derived server-side,
    never from request input), `core/email_clean.py` (the CRM_Extender
    stripping pipeline ported, two-zone output — quoted reply demoted into
    `blockquote.quoted-reply`, signatures/boilerplate deleted; raw stays in
    Gmail), `comms/` (sync engine: historyId cursors + expired-cursor and
    new-address backfills, active-records-only scope, RFC Message-ID dedup
    across co-mentor mailboxes, triage, CConversation/CCommunication upsert +
    parent/contact links + assignedUsers owner-stamp; Postgres state via
    Alembic `0004_comms_sync`; runs in the worker on `gmail_sync_seconds`),
    `comms/summarize.py` (OPTIONAL Claude summaries — `COMMS_AI_SUMMARY`,
    default off, `messages.parse` structured outputs, degrades to Uncertain),
    per-domain endpoints (list/thread read as the user; exclude; mailsearch +
    include; add-contact-address; send/reply **as the manager's own
    @cbmentors.org**, In-Reply-To threading, write-through ingest, unknown
    recipients need an explicit confirm), and the frontend (real conversation
    list + thread view + curation + compose when `commsEnabled`; the
    sample-data scaffold remains when off). 25 new tests; full UI loop
    verified in the stub harness. **Activation prerequisites (NOT done):**
    (1) build the CRM entities/links/grants per `cconversation-entity.md`
    (crm-test first); (2) authorize `gmail.readonly` + `gmail.send` for the
    service account's domain-wide delegation in Google Admin; (3) set
    `GMAIL_SYNC=true` (web + worker) — and optionally `COMMS_AI_SUMMARY=true`
    + `ANTHROPIC_API_KEY` (worker) after the privacy sign-off; (4) run the
    pre-deploy migrate (0004). Then drive the §6 verification in
    `cconversation-entity.md` live.
    The superseded scaffold wiring notes below describe the pre-0.35.0 stub
    (kept for context): scaffold code was in `sessions/frontend/` (`app.js` "Communications tab"
    section, `index.html` `data-dpanel="communications"` panel + `#commModal`,
    `styles.css` `.sx__inbox`/`.sx__msg-*`); the router just un-flagged the tab as a
    placeholder (`router.COMMON_DETAIL_TABS`) so the static panel is used. A muted
    banner tells the user the rows are examples. **To wire it to the CRM later:**
    1. **Design the CRM side** — decide where email lives (likely an `Email`/custom
       entity related to the parent `CEngagement`/`CPartnerProfile`/`CSponsorProfile`,
       or EspoCRM's built-in `Email` with a parent link + inbound/outbound flag).
    2. **Add backend endpoints** in `sessions/router.py` + `sessions/service.py`,
       all running as the logged-in user (ACL-enforced, like every other read):
       `GET /{slug}/api/records/{parent_id}/messages` (list, newest-first),
       optionally `GET /{slug}/api/messages/{id}` (full body if the list omits it),
       and `POST /{slug}/api/records/{parent_id}/messages` (send/reply). Follow the
       existing `_crm_failure` 401/403/502 handling.
    3. **Frontend swap** (`sessions/frontend/app.js`): replace the `SAMPLE_MESSAGES`
       array with a fetch in `renderComms()` (`await api("/records/" + id +
       "/messages")`), and point the compose modal's **Send** handler (currently a
       "not available yet" stub) at the `POST` endpoint.
    4. **Message contract the UI already expects** (produce this shape from the
       backend, or adjust the tiny render fns `renderComms`/`viewMessage`): each
       message = `{ id, direction: "sent"|"received", from, to, subject, date
       ("YYYY-MM-DD HH:MM:SS"), unread: bool, body }`. `from`/`to` may be
       `"Name <email>"` (the UI extracts the display name via `partyName`); `body`
       is plain text rendered pre-wrapped; `date` is formatted with `fmtSessionDate`
       (abbreviated weekday). Compose sends To/Subject/Message from `#commTo`/
       `#commSubject`/`#commBody`.
- **Google Calendar events + Meet links (v0.40.0, 2026-07-13 — BUILT, gated
  OFF by `GCAL_EVENTS`; NOT yet activated).** Saving a **Scheduled** session
  (create or edit, any domain) reconciles a Google Calendar event on the
  signed-in manager's OWN calendar: `core/gcalendar.py` (delegated Calendar
  REST client — same service-account + DWD stack as Gmail, impersonating the
  manager's `cbmEmail` via `sessions.service.resolve_user_mailbox`) +
  `sessions/gcal.py` (`sync_session_calendar`, called from
  `create_session`/`update_session` when the router passes `settings`).
  Decision matrix: Scheduled + no stored event → **create** (with a Meet
  conference when `videoMeetingLink` is blank — the URL is written back to
  `videoMeetingLink` + the event id to the **feature-detected CRM field
  `CSession.googleCalendarEventId`** (`csession-calendar-field.md`, NOT
  BUILT — the hook is inert until it exists); a hand-typed link means no
  Meet, link carried in the event location); Scheduled + event + a
  time/title/status/attendee change → **patch** (notes-only edits never
  touch the calendar); status → Cancelled → **cancel** (clears the event id
  + a generated Meet link, never a hand-typed one); Completed/No Show →
  skipped (Doug: only Scheduled sessions get events). Attendee contacts are
  invited (`sendUpdates=all` — Google emails invitations; organizer
  excluded, blanks skipped). **Best-effort** (mentoradmin-provision
  precedent): never raises; the save response carries `calendar:{ok,…}`
  and `saveSession` shows it as a notice. **Activation:** Calendar API on in
  GCP "CBM Integrations"; `calendar.events` added to the SA's DWD grant;
  the CRM field built (crm-test → prod); **disable EspoCRM's own Google
  Calendar sync on crm-test first** (double events otherwise; prod never
  had it — the app owns all email + calendar operations); `GCAL_EVENTS=true`
  (web component only — the worker is not involved).
- **Phase 1 (CRUD + review UI).** The **Start/Open Session** button uses
  `videoMeetingLink` when set. Google Calendar/Meet *scheduling* shipped
  v0.40.0 (the bullet above; gated). Meet *transcription* (a new
  `sessionTranscription` wysiwyg field) is still a later phase, not built. **The UI side of the transcript is now ready
  and feature-gated (v0.37.0):** the session view's Transcript zone (own scroll
  allotment + Find-in-transcript) and the editor's Transcript box both appear
  automatically once the `sessionTranscription` field exists in the CRM —
  `/fields` and `GET /sessions/{id}` detect it live from metadata, so shipping
  Phase 3 needs only the CRM field + the transcription feed, no frontend change.
  The v0.37.0 session view also applied Doug's session-details design rulings:
  time range in the band, video link as the band's Start/Open action, and the
  ATTENDEES grid (name/role/company/email/phone/status, contact & Account peeks,
  per-cell copy + Copy grid TSV + Copy emails). Per-person invited-vs-attended
  state is deliberately derived from session status pending a CRM modeling
  ruling (planning prompt: `cbm-mentoring-app/prompts/invitee-attendee-modeling-session.md`).
  The **Communications** tab now has a built
  email-inbox UI scaffold (no CRM data yet — wiring contract in the Communications
  bullet above); the **Documents** (uploads) tab is still a placeholder.
- **Status (2026-07-12, second session of the day: v0.38.2; 375 tests green;
  main pushed and DEPLOYED — prod + crm-test `/healthz` verified at each
  release).** This session (ran PARALLEL to the v0.37.x one below — version
  numbers interleave; a v0.36.6 commit landed after the v0.37.2 commits with
  pyproject already at 0.37.2, so the changelog holds both orderings):
  - **v0.36.x — comms compose/curation fixes after Doug's live testing** (see
    the Communications bullet + CHANGELOG): CBM members get the Add checkbox
    (matched via mentor-profile `cbmEmail`, v0.36.3) and are added as
    **co-mentors, never client contacts** (v0.36.4); `EspoClient.unrelate`
    sends the id in the DELETE **body** — the path-suffix form 404s
    (v0.36.5, [[espo-custom-linkmultiple-is-a-relationship]]).
  - **v0.36.6 — grid: company column links to the standard aggregated
    company/client pop-up** (ACL-restricted sections omitted) **+ records open
    in a new browser tab**; column-header sorting confirmed already present.
  - **v0.38.0 — records are a dedicated page `/{slug}/record/{id}`** (Doug's
    ruling: a record in another tab must be a real page): the route serves the
    shared frontend with `<base href="/{slug}/">` + no-store; the JS boots
    straight into the record (no list fetch, tab titled with the record name);
    "← Back to list" and the `?record=` deep-link mode removed. The revalidate
    middleware now respects any route-set Cache-Control.
  - **v0.38.1 — company shows for intake-created engagements** (prod report:
    Agape — James Koran had a blank Company). Root cause: the tools read
    `CEngagement.clientOrganization` but the client-intake orchestrator never
    wrote it (intake links the Account to `CClientProfile.linkedCompany`
    only). Fix: the orchestrator now sets `clientOrganizationId` on create,
    AND the session tools fall back through the client profile's
    `linkedCompany` (`DomainConfig.company_fallback`) for legacy records —
    feeds the grid column/pop-up, Overview Company aggregate, Details company
    card, and contact company stamping. Best-effort (unreadable profile ⇒
    blank). No CRM backfill needed.
  - **v0.38.2 — Assigned mentor on the Overview rail** (key facts, right above
    Meeting cadence — it appeared nowhere on the page), linked to a
    `CMentorProfile` pop-up (entity added to the peek allowlist: type/status/
    CBM email/expertise/industry).
- **Status (2026-07-12 end of session): v0.37.2; 370 tests green; main pushed
  and DEPLOYED to test (App Platform ACTIVE, `/healthz` = 0.37.2).** Session
  scope — Doug's session-details design rulings, three releases:
  - **v0.37.0** — session view per the approved design: band carries the
    start–end time range; ATTENDEES grid (name/role/company/email/phone/
    status, contact + Account peeks, per-cell copy, Copy grid TSV, Copy
    emails); §12.5 transcript zone + editor box FEATURE-GATED on the CRM
    gaining `sessionTranscription` (find-in-transcript, educate copy when
    empty; nothing renders until the field exists — Phase 3 needs only the
    CRM field + feed, no frontend change). Fixed: the view read `s.notes`
    but the payload speaks `sessionNotes` — notes never rendered.
  - **v0.37.1** — CBM contacts invited by default on new sessions; "Client
    Session" type chip only when non-default; status badge centered + large.
  - **v0.37.2** — the default-invitee fix after Doug's live test came up
    empty: the invitee set is server-resolved (`cbmContacts` on the detail
    read) from the ASSIGNED MENTOR (`CEngagement.mentorProfile`) + any
    co-mentors, via `contactRecordId` with a Contact-by-`cbmEmail` fallback
    (comms precedent). Live data facts behind it: engagements almost never
    carry `additionalMentors`, and 5 of 42 mentor profiles have no linked
    contactRecord (ANITA KHAYAT / Milt Sierra / David Schwieterman also lack
    `cbmEmail` — they stay uninvitable until linked in the CRM).
  - Open: per-person invited-vs-attended modeling is deliberately a
    session-status derivation pending a CRM ruling (planning prompt:
    `cbm-mentoring-app/prompts/invitee-attendee-modeling-session.md`).
- **Prior status (2026-07-10 end of session): v0.34.0; 315 tests green; branch
  `feat/session-view` (**NOT pushed**), five commits today (a4aa147..bb32ed4).**
  Shipped this session:
  - **v0.33.0 — Details tab rebuilt to mockup v4** (summary strip + row-grid
    cards + contact tables + add-contact flows; see the Details bullet above).
    Verified against a **stubbed-API preview harness** in the browser
    (strip/cards/tables render, per-row edit expansion, + Add menu, search-link
    flow, create-new form, strip edit — all exercised; no console errors) —
    **NOT yet driven against the live CRM** (still to check live: the contacts
    search `where contains name` under a non-admin ACL, link/backfill/create
    writes, and the CBM card's per-profile `contactRecord` reads under
    read-own).
  - **v0.33.2 — US phone display format `(216)-555-1234` product-wide**
    (`frontend/shared/phone-format.js` + `core.phone.format_us`; display-only,
    CRM keeps E.164, edit inputs/tel: keep raw).
  - **v0.33.3 — website links normalized** (`externalHref()` — a stored bare
    domain no longer resolves relative to the app path; all external links
    new-tab + noopener).
  - **v0.34.0 — portal reviews ALL current teams** (membership re-read from the
    CRM on every session restore + `ASSIGN_ALLOWED_TEAMS` real default; see the
    portal section). Verified live on crm-test.
  - Live diagnosis (no code change): "partner app shows no partners for
    doug.bower" was **data** — crm-test has a DUPLICATE unlinked mentor profile
    ("Doug Bower" `6a4425f4c82d3f2ec`, no Assigned User) alongside the real
    linked "Douglas Bower" (`6a1e5f2ab841b5c9c`), and the partner had been
    assigned to the duplicate. Records assigned to an unlinked profile are
    invisible in the session tools — **merge/delete the duplicate in the CRM**
    (also spotted: two "Acme Inc" CPartnerProfiles). Possible follow-up guard:
    flag manager profiles with no linked login user in the admin tools.
  Earlier (v0.32.x, live-diagnosed on crm-test as admin): tabbed detail;
  information-dense **Overview** (aggregated Company peek, notes feed with
  attendees, splitter, Next-session Start/Open button); friendlier empty states
  (+ v0.33.1 distinct no-linked-profile message); bigger session-notes editors;
  the **attendee relationship** read/write fix (`sessionAttendees` is a link,
  not a field — [[espo-custom-linkmultiple-is-a-relationship]]) and
  **per-record edit-permission** gating in Details.
  **Still NOT driven live as a non-admin team member, nor for the partner/sponsor
  domains.** Communications has an email-inbox UI scaffold (no CRM data — wiring
  contract documented above); Documents is a placeholder. Open polish items:
  trimming generic Contact/Account fields in the edit forms (metadata-driven, so
  `acceptanceStatus`/`doNotCall` etc. appear), and whether to drop the editor's
  Session/Notes tab split for one scrolling form. **Deploy note:** all three App
  Platform apps build from `main`, so a push deploys crm-test **and** prod — and
  prod lacks the partner/sponsor CRM prereqs below.
  **CRM prerequisites** (done on crm-test during testing; **replicate on prod**):
  1. Create `Partner Management Team` + `Sponsor Management Team` (`Mentor Team`
     exists); add staff.
  2. Grant the gate roles `CSession` **create + read-own/edit-own** (+ the parent /
     reverse links).
  3. **Enable `assignedUsers` (collaborators) on `CSession`** so read-own credits
     the owner-stamp — else create 403s / sessions invisible (see the ACL bullet).
  4. Make the `CSession` **name formula keep-if-present** (see the name bullet).
  5. Decide the read-own-vs-broader ACL question (whether a mentor should see
     pre-existing / others' sessions on their engagement).
  Note: crm-test seed sessions carry out-of-enum `sessionType` values (harmless; a
  data-hygiene cleanup). **UI polish is the next work item** (a follow-up session).

## Current status (updated 2026-07-13, later session)

**Main is at v0.41.1** (407 tests green) — **v0.41.1 density pass** after
Doug's live review of 0.41.0: forms cap at 1080px (span-8 street ≈ 40 chars,
not 100+), billing/shipping addresses side by side on one panel, Country
inside the address block (was orphaned in Additional details), the three
industry fields on one Identity row, "Same as billing" restores the original
shipping values on uncheck, and LinkedIn labels no longer split into
"Linked In" (`details.py:_label`). Base feature — **v0.41.0 section edit
screens** (`prompts/section-edit-screens-prompt-v0.1.md`, design target
`prompts/section-edit-screens-mockup-v2.html`): the session tools'
Details-tab edit forms are now curated grouped 12-column layouts (Edit
Engagement / Company / Client Business Profile / Contact + the
create-new-contact flow — `DETAILS_LAYOUTS`/`layoutForm` in
`sessions/frontend/app.js`), with a **reusable postal address block**
("Same as billing" = copied values mirrored client-side; the CRM has no
flag — investigated live 2026-07-13), a **time-picker standard** replacing
every `datetime-local` (half-hour slot popover + free-entry escape; UTC
round-trip + duration→dateEnd unchanged), and **chip selectors for all
multiEnums** (a stored value drifted out of the options renders selected so
a save can't drop it). Doug's scoping rulings (2026-07-13): the Company
form's partnership/account-group removal is **mentor-domain only** —
partner/sponsor domains keep a curated group of their own relationship
fields; the system discriminators (`cAccountType`/`cClientStatus`/
`cCompanyType`/`type`) are edited nowhere; the Engagement form's **Mentor
field is read-only** (reassignment stays in Client Administration — a bare
`mentorProfile` write would skip `/assignments`' side-effect chain). The
mentor-domain Company VIEW card dropped its Account/Cadence/Announcements
rows (right column now carries Business + Shipping; excluded fields never
render as leftovers). Backend: `sessions/details.py` now exposes `name` in
the field spec (Company name editable; Contact's personName still composed
from first/last; views suppress the redundant Name row/cell). Client-vs-CBM
contacts confirmed the SAME `Contact` entity (via `contactRecord`), so one
contact form serves both. Verified in the stubbed-browser harness (mentor +
partner domains: groups/exclusions, same-as-billing dim + live mirror,
street line-1/2 split + rejoin in the save payload, chip toggles, slot
select → correct UTC dateStart/dateEnd, required-Start message,
create-new-contact grouped form posting only filled fields). **NOT yet
driven against the live CRM.** Before that: **v0.40.1** — **pushed and DEPLOYED 2026-07-13**
(`/healthz` = 0.40.1 verified on crm-test AND prod) — **the calendar
integration is ACTIVATED and VERIFIED LIVE on crm-test**: Doug created a
Scheduled session and the Google Calendar event was created end-to-end
(so the CRM field `googleCalendarEventId` IS built on crm-test), and after
v0.40.1 he confirmed the Meet link renders + works in the UI. **v0.40.1**
made the meeting link **visible + copyable** (his follow-up report: it only
existed behind the Start Session button): a truncating clickable URL with a
⧉ copy button in the Overview Next-session callout and a "Meeting link" row
in the session view's facts grid (`linkWithCopy`, `addKV` type `copylink`).
**Still to drive live:** the edit→patch and Cancel→cancel event paths, and
attendee-invitation delivery. **Prod activation remains:** build
`googleCalendarEventId` on the prod CRM + set `GCAL_EVENTS=true` in
`.do/app.prod-crm.yaml` (prod has the 0.40.1 code, hook inert until then).
Base feature (v0.40.0):
**sessions create Google Calendar events + Meet links** (gated by
`GCAL_EVENTS`; see the "Google Calendar events" bullet in the Session
Management section, `csession-calendar-field.md` for the CRM field build,
`GCAL-GOOGLE-SETUP.md` for the Google side + troubleshooting, and the
runbook note in DEPLOYMENT.md). Saving a **Scheduled** session
creates an event on the manager's own calendar (delegated as their
`cbmEmail`, reusing the comms service-account stack) with a Meet link
written to `videoMeetingLink` and attendees invited; edits patch the event;
Cancelled cancels it. Best-effort — Google failures never fail the save
(`calendar:{ok,...}` on the save response → UI notice; a disabled hook
shows a plain "Session saved.", by design). **Activation state
(2026-07-13):** Google side DONE by Doug (Calendar API enabled +
`calendar.events` added to the DWD row); `GCAL_EVENTS=true` set on the
crm-test **web** component (overlay applied via doctl; verified in the
live spec). **Remaining:** confirm/build `CSession.googleCalendarEventId`
on crm-test (UNVERIFIED — the intake API key has no CSession grant, so it
can't be checked from the app side; a plain "Session saved." with no event
means the field is still missing); then the live
create→invite→edit→cancel verification. The EspoCRM-side calendar sync is
RESOLVED (2026-07-13): there never was an org-level EspoCRM↔Google
integration — only per-user personal-account connections, which Doug
deleted — so the double-event risk is gone and nothing needed disabling
(Doug's ruling stands: the app owns all email + calendar operations). Prod has the 0.40.0 code but no
flag — inert until its own field build + `GCAL_EVENTS`. First live test
attempt (before the push) failed simply because the code wasn't deployed
— crm-test was still 0.39.1. Before that: **v0.39.2** — **session
timezone fix** (Doug's live report: Google Calendar meetings created for
sessions didn't match the app's time). Root cause: the app created no
calendar events pre-0.40.0 — crm-test's **EspoCRM server-side Google
Calendar sync** did, from
`CSession.dateStart`/`dateEnd`, and the EspoCRM API treats datetimes as
**UTC** — but the sessions frontend sent/displayed local wall-clock digits
verbatim (3:30 PM Cleveland stored as 3:30 UTC → calendar event 4–5h off).
Fix is frontend-only (`sessions/frontend/app.js`): `parseNaive` parses
stamps as UTC (date-only values stay local calendar dates — no day shift),
`toLocalInput`/`fromLocalInput` convert the datetime-local editor value
local ↔ UTC, `stampPlusSeconds` emits UTC for the derived `dateEnd`,
`fmtWhen` displays local. Backend untouched (it already assumed UTC —
`_next_session` now actually correct). **Pre-fix sessions stored local
digits as UTC and stay offset until manually re-saved** (Doug's ruling: no
backfill — a script can't distinguish app-created sessions from ones
entered correctly via the CRM UI). Ops note: set EspoCRM default/user
timezone to America/New_York so the CRM UI display matches too. Before
that: **v0.39.1** (379 tests green, 4 new), **pushed and DEPLOYED**
(prod + crm-test; `/healthz` verified at 0.39.1 on both, 2026-07-13) —
**Details-tab contact removal (v0.39.0)**: two-step-confirm Remove on every
client-contact and co-mentor row (relation detach only; assigned Mentor row
excluded; gated on parent-record editability), completing the add/remove pair
for both tables. New `DELETE /records/{id}/contacts/{contactId}` +
`/comentors/{profileId}` endpoints. **v0.39.1 fixed Doug's live report "CBM
+ Add is broken"** — a `repaintDetails` key collision (any key starting with
"c" was treated as a client-row key, and `cbmContacts` starts with "c", so
the CBM card never repainted and its + Add menu never opened; latent since
the v0.33.0 Details rebuild). **CBM add + remove VERIFIED LIVE on crm-test
2026-07-13** (as the signed-in admin, in-browser): + Add → 42-mentor picker →
Brad Swimmer added to the Agape engagement → two-step Remove → row gone —
clean round-trip, no residue. Client-contact remove not separately driven
live (same unrelate-on-parent machinery). Details in the Session Management
**Details** bullet above + CHANGELOG. Before that: **v0.38.2** (375 tests green), pushed and
DEPLOYED (prod + crm-test; `/healthz` verified at 0.38.1 on both, 0.38.2
pending push at the time of that update — check `/healthz`). The 2026-07-11..12 work — comms
activation + live fixes (v0.35.x–0.36.x), session-view design rulings
(v0.37.x, a parallel session), the dedicated record page (v0.38.0), the
intake-engagement company-link fix (v0.38.1), and the Overview Assigned-mentor
fact (v0.38.2) — is summarized in the Session Management tools **Status**
bullets above and in CHANGELOG. Prod answers on the
**custom domain `https://apps.clevelandbusinessmentors.org`** (added to the DO
app as PRIMARY, Cloudflare CNAME grey-cloud → the app's default hostname; the
`…ondigitalocean.app` URL still works). Shipped 2026-07-05..10 (see CHANGELOG):

- **Communications: Gmail conversation integration — ACTIVATED LIVE on
  crm-test 2026-07-11 (read path verified end-to-end).** Built v0.35.0; docs:
  plan `prds/communications-gmail-integration.md`, CRM handoff
  `cconversation-entity.md`, activation runbook `GMAIL-INTEGRATION-GUIDE.md`,
  user-facing functional reference `communications-tab.md`.
  Activation record: CRM entities built by Doug in the Entity Manager UI +
  probe-verified (fields/links/Collaborators/grants all green; note the CRM's
  varchars are 100 chars — the app clamps, spec updated); Google service
  account **created from scratch** (project `espcrm-498315`, SA
  `espocrm@…iam.gserviceaccount.com`, client_id 109317126943210877831 —
  delegation row + gmail.readonly/send authorized by Doug; the v0.11.0 "SA
  exists" assumption was FALSE); key wired into the crm-test overlay
  (`GOOGLE_SERVICE_ACCOUNT_JSON` SECRET on web+worker) + `GMAIL_SYNC=true`;
  migration 0004 applied. Two live bugs fixed during activation:
  `requests` was a missing dependency of google-auth's token transport
  (c655bf2, latent since v0.11.0), and CCommunication creates 400'd on
  snippet maxLength → all varchar writes clamped to the as-built 100-char
  fields (d6d48cd). **`GMAIL_RESYNC=true`** (worker env, one shot) is the
  re-drive lever: clears cursors at startup so the backfill re-runs
  idempotently (2e00a9e) — used to recover the dropped messages; the 5 empty
  conversation shells from the bugged first pass were deleted via the admin
  account. Verified in the CRM: 3 conversations, 5 cleaned messages,
  References-merged threads, linked to the real engagement "Agape W8 Loss
  2026-05-15", owner-stamped. Steady state: sync every 300s; the two fake
  test mailboxes (partner.manager@/matt.mentor@ have no real Workspace
  mailbox) log an expected invalid_grant warning each pass. **Non-contact-recipient design (v0.35.2, from Doug's scenario
  review):** thread-following ingest (replies to any stored conversation
  ingest even from unknown addresses), confirmed sends write a durable
  include override, the compose dialog routes unknown recipients to
  add-address-to-contact / create-contact / explicit one-off, and
  `@cbmentors.org` recipients never trip the guard. **Remaining:**
  eyeball the Communications tab as a signed-in manager; exercise SEND
  (first gmail.send use) + curation live; prod rollout per the runbook
  (prod CRM entities + prod overlay; same SA/delegation covers prod); AI
  summaries need privacy sign-off + `ANTHROPIC_API_KEY` +
  `COMMS_AI_SUMMARY=true`.

- **Session Management tools — v0.34.0** (built 2026-07-08..10, branch
  `feat/session-view`, **NOT yet pushed/deployed**; mentor domain CRUD **driven
  live end-to-end on crm-test** 2026-07-08..09) — `/mentorsessions`
  `/partnersessions` `/sponsorsessions`: one engine, three team-gated routes,
  recording `CSession` meetings against the records each manager owns. Since the
  v0.31.0 CRUD baseline the **record detail was redesigned** into a tabbed
  (Overview · Details · Sessions · Communications · Documents), information-dense
  review UI: a full-width Overview (aggregated Company peek, session-notes feed
  with attendees, Next-session Start/Open button), friendlier empty states, bigger
  notes editors. **v0.33.0 (2026-07-10) rebuilt the Details tab to the approved
  mockup v4** (`prds/Details Screen files2/`): engagement **summary strip** +
  Company / Client-Business-Profile cards as two-column labeled row grids +
  **Client Contacts / CBM Contacts tables** (one Agreements badge per contact,
  per-row inline editing) + **+ Add contact** flows (select-existing via live
  search, create-and-link, CBM mentor-profile pick) — new endpoints
  `GET /{slug}/api/contacts` + `POST /{slug}/api/records/{id}/contacts`; verified
  in a stubbed-API browser harness, NOT yet against the live CRM. **Follow-ups
  2026-07-10 (same branch):** v0.33.1 distinct no-linked-profile empty state;
  v0.33.2 US phone display format product-wide; v0.33.3 website links normalized
  (no more relative bare-domain hrefs); **v0.34.0 portal membership refresh**
  (teams re-read from the CRM on every session restore + `ASSIGN_ALLOWED_TEAMS`
  real default — fixed "only shows mentor admin despite other teams"). Earlier
  live-diagnosed fixes: the **attendee relationship** read/write
  (`sessionAttendees` is a link, not a field —
  [[espo-custom-linkmultiple-is-a-relationship]]) and per-record edit-permission
  gating. Full detail in the **Session Management tools** section above.
  **Data-hygiene gotcha found while driving live (2026-07-10):** crm-test has a
  DUPLICATE mentor profile "Doug Bower" with no Assigned User next to the real
  linked "Douglas Bower" — a partner assigned to the duplicate is invisible in
  the session tools (the apps resolve ownership through the login-linked
  profile). Merge/delete the duplicate (+ the two "Acme Inc" CPartnerProfiles)
  in the CRM UI.
  **Remaining:** drive the Details redesign + contact-add writes live; drive live
  for partner/sponsor + as a non-admin; wire the Communications inbox (UI scaffold
  built; CRM email structure + endpoints still to do — wiring contract documented
  in the Session Management section); Documents tab; edit-form field trimming.
  (Deploy = push `main` ⇒ crm-test **and** prod; prod needs the partner/sponsor
  CRM prereqs first.)
- **v0.30.0** (built 2026-07-07, NOT yet pushed) — **authenticated portal at
  `/` + single sign-on**: root becomes a CRM login; team-based links (Mentor
  Team → CRM + public forms; the three admin teams → their apps; admins → all;
  everyone signed-in → public form links); staff apps share ONE session
  (`staff_user`) with **per-request team gates** (401 → `/?next=<app>` redirect,
  403 names the team); per-app login screens/endpoints removed; `/ops` retitled
  **Submission Admin** and gated by its own `OPS_ALLOWED_TEAMS` (default
  `Marketing Admin Team` — **create this team in both CRMs**); dev app keeps
  the public form index. See the Deployment-URLs section. NOT yet verified live.
- **v0.29.0** — `/mentoradmin` detail editor
  gains a **Contact tab**: view/edit the mentor's first/last name, email, phone,
  and street/city/state/ZIP. The fields live on the linked **Contact** record —
  see the Contact-tab note in the `/mentoradmin` section (routing, E.164 phone,
  no-Contact 400). Not yet verified live.
- **v0.28.0** — `/assignments` engagement status filter gains an **"All"**
  master checkbox (one click = every status; indeterminate when partial;
  summary reads "Status: All").
- **v0.24.0** — `/assignments` Available Mentors grid reworked: Focus Areas
  column dropped; Industry column → multi-value `industryExperience` (chips);
  filters → Industry Experience + Areas of Expertise; **Capacity column shows
  the stored `maximumClientCapacity`** (not the CRM-computed
  `availableCapacity`); dialog defaults to ~96vw. (NOTE: crm-test's
  `currentActiveClients` formula computes 1 for every mentor — CRM-side bug,
  feeds the Assigned column + availableCapacity.)
- **v0.24.1** — volunteer consent now also sets
  `CMentorProfile.ethicsAgreementAccepted` (the completeness flag — was never
  set by the form; verified live); volunteer form's "Code of Conduct" links to
  the **mentor code of ethics**
  (`https://clevelandbusinessmentors.org/mentor-code-of-ethics/`, scoped to
  `/volunteer/` in `frontend/shared/legal-links.js`); Mentoring-skills editor
  removed from `/mentoradmin` Bio tab. Pre-existing mentors may still lack the
  ethics flag (offered backfill — not requested yet).
- **v0.25.0/1** — **friendly URL aliases**: any single-segment path is
  normalized (lowercase, alphanumerics) and 307-redirects to the matching
  form/staff tool (`/clientintake` → `/client-intake/`; `core/app.py`
  `form_alias`); the landing page shows each entry's shortcut as a code chip.
- **v0.25.2** — **partner form 422 fix + exact-error policy.** The CRM's
  `partnershipType` gained "other" (later corrected to "Other"); the schema's
  hard-coded `Literal` 422'd those submissions with a generic message. ALL
  CRM-synced dropdown fields are now free strings in the schemas (orchestrators'
  `EnumSanitizer` = the gate; see the [[non-required-enums-never-block]] policy:
  a non-required field must never block a save over enum drift). Validation
  failures now return a **readable string `detail`** (field: reason; structured
  list under `errors`) and log at WARNING; both frontends show it verbatim.
- **v0.26.0** — `/mentoradmin` **"Update Mentor Status"** roster action
  (`POST /mentoradmin/api/mentors/status-check`): sweeps all mentors, verifies
  the linked login User exists/is active (via the provisioning admin account
  when configured), checks the `@cbmentors.org` mailbox (reports "n/a" until
  Email Setup is configured — still true in prod), and bulk re-syncs
  `recordStatus`. Results in a modal; roster reloads.
- **v0.27.0** (built 2026-07-06, NOT yet pushed/deployed) — **mentor client-count
  analytics** in both staff mentor grids (`/mentoradmin` roster + `/assignments`
  Review Mentors): Active Clients / Max Clients / Assigned (30d) / Available /
  Lifetime, all sortable. App-computed from `CEngagement` in one paginated sweep
  (`assignments/service.py:mentor_engagement_metrics`, grouped by
  `mentorProfileId`; active set = Active/Assigned/Pending Acceptance; Available
  = max − active, -1 max = Unlimited) — the CRM's buggy computed
  `currentActiveClients`/`availableCapacity` are no longer read. The Assign
  action now **stamps `engagementAssignedDate`** (nothing CRM-side fills it;
  pre-0.27.0 assignments have a null date, so Assigned-(30d) undercounts until
  backfilled CRM-side). `list_all_mentors`/`list_eligible_mentors` now return
  `{"mentors": [...], "metricsAvailable": bool}`; a staffer whose role can't
  read CEngagement still gets the roster, with blank counts + a notice (grant
  CEngagement read to the staff-gate Teams' role for full data). Both
  frontends' Has-capacity filter + "(capacity N)" label use the computed
  Available. 226 tests green.

Before that, the 2026-07-02 push (v0.21.3 → v0.23.1): volunteer how-heard also
writes `Contact.cHowDidYouHear`; `/mentoradmin` roster/editor refinements +
self-healing Record status on view; `/assignments` shows the assigned mentor on
assigned rows; completeness dropped the publicProfile + background-check
requirements. Earlier, the big 2026-06-30/07-01 push
(v0.12.0 → v0.21.2; v0.21.2 = three mentor-form fields made **required on the
form**, frontend only — see the volunteer bullet up top):

- **Field-mapping effort COMPLETE + code-reviewed.** Every input collected across all
  five forms now writes to its intended CRM field — nothing is silently dropped.
  Shipped: Pass A previously-dropped fields + **null-fill on repeat Contacts**
  (`core/crm_upsert.find_create_or_fill`); mentor **industry experience** →
  `industryExperience` (all selections); **consent** (one checkbox → three Contact
  bools + `mentorCodeAccepted`) across all four consent-collecting forms (added the
  checkbox to partner + sponsor); **notification + meeting preference**; **areas of
  expertise** → `areaOfExpertise` (skills, distinct from industry experience). The CRM
  team built/reconciled all the needed fields on **both** CRMs during this push (prod
  parity closed). A high-effort multi-agent code review (v0.13.0→v0.21.0) found **no
  runtime bugs**; only doc-accuracy + one sync-alignment fix (v0.21.1). Detailed
  per-field record: the blocks below + `field-mapping-completion-plan.md` +
  `crm-field-handoff.md`.
- **Environment shown in the footer** (v0.19.0): `v0.21.1 (Production/Test/Dev)` after
  the version — replaced the old corner badge.
- **Form keyboard UX** (v0.20.0): cursor starts in the first field on load/step-change;
  Tab moves field-to-field (consent policy links pulled out of the tab order).
- **crm-test ZZTEST cleanup DONE** (verified 0 remain, 2026-06-30).

**Open (all on the CRM/ops side, no app work):** add real non-admin staff to the two
staff-gate Teams in prod (tools are admin-only until then — see the staff-Teams note
below); the `CIntakeSubmission` `reason != Normal` alert workflow (CRM-owned, spec
ready); enabling Google Workspace mailbox creation (built + deployed, gated OFF).

### Deployment URLs (three App Platform apps, all from `dbower44022/cbm-client-intake`, branch `main`, deploy-on-push)

The **root `/` is the authenticated PORTAL** on the two staff-stack apps
(v0.30.0, `portal/` package): a CRM login (single sign-on for all staff apps —
`POST /api/portal/login`, ungated `authenticate(gate=False)`, shared session
key `staff_user`), then exactly the links the user's teams entitle them to:
every signed-in user → the five public form links; **Mentor Team** → a CRM
link; **Client Administration Team** → `/assignments/`; **Mentor Administration
Team** → `/mentoradmin/`; **Marketing Admin Team** → `/ops/` (**Submission
Admin**, retitled v0.30.0); admins → everything. Each staff app enforces its
own team **per request** (`auth.is_member`; 401 → redirect to `/?next=<app>`,
403 names the required team) — the portal listing is convenience, not the
security boundary. **Membership is re-read from the CRM on every portal
session restore** (v0.34.0, `auth.refresh_membership` — `GET /api/portal/
session` re-reads teams/roles/admin flag as the user and re-saves the session),
so a team granted after sign-in shows without a re-login; an expired token now
401s instead of serving stale entitlements. (Fixed alongside:
`ASSIGN_ALLOWED_TEAMS` now defaults to `Client Administration Team` — it
defaulted EMPTY, so an unset deploy hid `/assignments` from every non-admin.)
The **dev app** (no `SESSION_SECRET`) keeps the old public
form index at `/`. The forms themselves stay public by direct URL everywhere.
Friendly aliases (v0.25.0): any single-segment path, lowercased with
punctuation stripped, 307-redirects to the matching form/tool
(`/clientintake`, `/MentorAdmin`, …).
**CRM prerequisite: create the `Marketing Admin Team` in prod + crm-test** (the
`/ops` gate; the other three teams already exist) and add staff to the teams.

| Env | Root URL (portal / form index on dev) | CRM | `dryRun` | Staff tools | App ID |
|-----|-------------------------------|-----|----------|-------------|--------|
| **prod** | **https://apps.clevelandbusinessmentors.org/** (custom domain, PRIMARY; also https://cbm-client-intake-prod-a9li7.ondigitalocean.app/) | production (`crm.clevelandbusinessmentors.org`) | false | yes | `aa1ddf69-f359-4b53-91ba-035cbed7bd53` |
| **crm-test** (staging) | https://cbm-client-intake-svxs3.ondigitalocean.app/ | crm-test | false | yes | `509b4370-b9ca-42c7-b251-04d6820fe88e` |
| **dev** (`lobster-app`) | https://lobster-app-w6h5m.ondigitalocean.app/ | none — dry-run | true | no | `b3b28113-6113-4ba7-ae99-efd5ea633fcd` |

The **dev app** (DO default name `lobster-app`, no spec in
`.do/`) is dry-run only — submissions are logged, never written; no Postgres, no
staff tools — for exercising the form UIs. Local dev = `localhost:8000`.

**Field-mapping — areas-of-expertise retargeted (v0.21.0, 2026-06-30).** Volunteer
"Areas of Expertise" now writes to `CMentorProfile.areaOfExpertise` (31 *skill* values,
identical both CRMs) instead of `mentoringFocusAreas` (42 industries) — a clean split
now that "Industry Experience" maps to `industryExperience`. `mentoringFocusAreas` is
no longer set by the volunteer form (it stays the CEngagement client-request field).
Revises the earlier Pass B "keep mentoringFocusAreas" call. Live-verified.

**Field-mapping effort COMPLETE (v0.18.0, 2026-06-30).** Meeting + notification
preference now write to `Contact.cMeetingPreference` / `cNotificationPreference`
(options reconciled to identical, typo-free sets on both CRMs; forms re-synced;
live-verified). **Every input collected across all five forms now maps to its
intended CRM field — nothing is silently dropped.** Full record:
`field-mapping-completion-plan.md` (Passes A–E all done) + `crm-field-handoff.md`
(all CRM builds complete).

**Field-mapping completion — consent capture DONE across ALL FOUR forms (v0.16.0,
2026-06-30).** The single consent checkbox records all three acceptances: Contact
`cTermsOfUseAccepted` + `cPrivacyPolicyAccepted` + `cCodeOfConductAccepted` on every
form + `CMentorProfile.mentorCodeAccepted` (volunteer). client-intake & volunteer
already had the checkbox; **partner & sponsor got it added (v0.16.0)** — a public form
change (HTML + app.js + schema submit-gate + `legal-links.js`). All four bools exist
on both CRMs (CRM team built them 2026-06-30). Live-verified crm-test; checkbox +
linkified policies confirmed in-browser. **Also note: the Pass A prod-parity gap is
now CLOSED** — the CRM team added
all 7 missing fields to prod (2026-06-30, verified), so v0.13.0 Pass A now stores on
production too.

**Field-mapping completion — mentor industry experience DONE (v0.14.0,
2026-06-30).** Mentor "Industry Experience" (multi-select) now stores ALL selections
to the multiEnum `CMentorProfile.industryExperience` (was first-value-only →
`industrySector`); the CRM team made that field a multiEnum with a canonical 28-value
list on **both** CRMs (verified identical → works on prod), and the volunteer form's
industry dropdown is re-synced to it. Live-verified on crm-test. Pass B resolved
(no other retargets). See `field-mapping-completion-plan.md`.

**Field-mapping completion — Pass A DONE (v0.13.0, 2026-06-30, live-verified on
crm-test).** Previously-dropped form inputs now write to their intended CRM
fields: client-intake → Contact `cHowDidYouHear`/`cMarketingOptIn`/
`cTermsOfUseAccepted` + CClientProfile `numberOfEmployees`/`formationDate` (year →
`YYYY-01-01`); volunteer → Contact `cPreferredContactMethod`/`cEmploymentStatus`;
partner+sponsor → Contact `cHowDidYouHear`. Repeat submitters **null-fill** the
Contact (`core/crm_upsert.find_create_or_fill` — reuse + backfill empties, never
overwrite; needs the Contact edit grant, confirmed on crm-test). How-heard/contact-
method/employment dropdowns are now CRM-backed (Contact enums, via the options
sync). Full plan + remaining passes (B retargets, C CRM-field builds, D/E consent):
`field-mapping-completion-plan.md`. **Prod parity (checked 2026-06-30): the Pass A
fields are NOT on the prod CRM yet** (all the new Contact fields + CClientProfile
`numberOfEmployees` are MISSING; only `formationDate` exists). v0.13.0 is **safe on
prod regardless** — the writes are no-ops until the fields exist (find_one tolerates
the unknown select, the EnumSanitizer fails open, EspoCRM ignores unknown
attributes), and will start storing automatically once the CRM team builds the 7
fields on prod (MN-INTAKE hand-off; then re-sync options against prod). ZZTEST-PARITY
check left no prod records (write was sandbox-blocked).

**crm-test ZZTEST cleanup — ✅ DONE (verified 2026-06-30).** All 59 ZZTEST test
records (this session's field-mapping live checks — `ZZTEST-PASSA`/`ZZTEST-IE`/
`ZZTEST-CONSENT`/`ZZTEST-PC`/`PCS` — plus older accumulated `StageA/B`/`GrantCheck`/
`InfoReq`/`SMOKE`/`RebuildCheck` records) were deleted in the EspoCRM UI; a
`contains ZZTEST` sweep across all 9 entities now returns **0**. crm-test holds no
leftover test data from the field-mapping work.

**(historical — current version is v0.21.1, see the top of this section.)** The Google Workspace
**mailbox creation** + **live status window** + admin **Email Setup** code (v0.11.0)
IS deployed to prod but **gated OFF** (`GOOGLE_CREATE_MAILBOX` unset, no
`APP_ENCRYPTION_KEY`) — a dormant no-op until enabled (see the `/mentoradmin`
"Mailbox check + CREATION" block for the design, deploy secrets, and the
read-write Directory scope it needs).

**Fixed 2026-06-26 (v0.11.2), all verified live on the prod CRM:**
- **Mentor login now actually links on prod — the "approved mentor isn't
  selectable" bug.** Prod's `CMentorProfile` has the single `assignedUser`
  **disabled** and uses the multi-user `assignedUsers` (collaborators) field (like
  `CEngagement`/`CClientProfile`); writing `assignedUserId` returned 200 but stored
  nothing, so provisioned mentors stayed userless (never Active-eligible, always
  "Incomplete: no User assigned"). The mentor's User link is now written as BOTH
  `assignedUserId` + `assignedUsersIds` and read via `assigned_user_id`/
  `assigned_user_name` (resolve either shape) across both staff tools. See
  [[crm-test-assignment-acl-fields]]. `assignments/service.py`
  (`USES_ASSIGNED_USERS` now includes `CMentorProfile`) + `mentoradmin/service.py`.
- **Approval no longer creates duplicate login Users.** When the link silently
  failed, each re-save created `firstname.lastname`, then `…2`, then `…3`.
  Provisioning now **reuses** the existing CBM login (when the profile already has a
  `cbmEmail`) instead of duplicating; the suffix path remains only for a genuinely
  new email clashing with a different person. (Cleaned up the 2 prod duplicates
  `doug.bower2`/`doug.bower3` via the admin API; `doug.bower` is the linked login.)
- **"Couldn't load mentors" (504) on Client Administration.** The eligible-mentor
  query filtered `CMentorProfile` by `assignedUserId` in a `where` clause, which
  prod forbids ("Forbidden attribute 'assignedUserId' in where" → 400 → 502/504);
  the clause was dropped (userless rows filtered in Python — the field is still
  readable in `select`).
- **Static form dropdowns ← live CRM enums.** New `scripts/sync_form_options.py`
  refreshes the marker-wrapped CRM-backed arrays in `forms/*/frontend/options.js`
  from the live enums (dry-run by default, `--write` applies); see the "Form
  dropdown lists" subsection in Architecture. First sync realigned the volunteer
  industry list (it had drifted to the NAICS taxonomy on both crm-test and prod, so
  volunteer industry was being dropped on submit).

Changes shipped since the v0.9.0 go-live, all live + verified against the prod CRM:
- **Mentor-login provisioning ENABLED in prod** (v0.9.1) — admin service account
  `mentoradmin@cbmentors.org` (Type=Admin); approving a mentor creates their
  EspoCRM login + welcome email (delivered to the CBM address). v0.9.1 also added a
  UI signal so an approval saved while provisioning is OFF says "no login created"
  instead of a silent "Saved".
- **Google Workspace mailbox gate** (v0.10.0) — provisioning can hard-gate on
  whether the mentor's `@cbmentors.org` mailbox exists (built, **OFF** pending a GCP
  service account; see the `/mentoradmin` section).
- **Form index** opens links in a new tab (v0.10.1) + is served `Cache-Control:
  no-store` so a redeploy never shows a stale landing page (v0.10.2).
- **`CIntakeSubmission.submitterEmail` now stores** (v0.10.3→0.10.4) — root cause
  was the CRM field being type `email` (stores nothing on a non-primary email
  field); recreated as `varchar` in dev + prod, verified live (see the
  CIntakeSubmission follow-up below).

**PRODUCTION IS LIVE (2026-06-24).** A **separate prod app** —
`cbm-client-intake-prod` (App ID `aa1ddf69-f359-4b53-91ba-035cbed7bd53`,
`https://cbm-client-intake-prod-a9li7.ondigitalocean.app`) — runs against the
**production CRM** `https://crm.clevelandbusinessmentors.org` with its own managed
Postgres (`cbm-db-prod`) + `delivery-worker`. Config in the gitignored
`.do/app.prod-crm.yaml` (separate from the crm-test overlay `.do/app.prod.yaml`).
Go-live **verified end-to-end (v0.9.0)**: one labelled `ZZTEST-PROD-GOLIVE`
submission per form delivered through capture → worker → CRM, all entity
create-grants proven (Account, Contact, CClientProfile, CEngagement,
CMentorProfile, CPartnerProfile, CSponsorProfile, CInformationRequest +
CIntakeSubmission Normal/Processed log). **Prep that made it work:** the prod
intake API user (`customappsproduction`) needed the role `CustomAppAPIRole`
(create/read/edit on the 9 entities) — the migration didn't copy it; and prod is a
**stock** instance where CEngagement/CClientProfile use the single `assignedUser`
(crm-test used the `assignedUsers` collaborators field) — the assignment tool now
writes BOTH so it works on either (commit a0d95f2). Read-only readiness checker:
`scripts/preflight_crm.py` (went green pre-go-live). **Mentor-login provisioning
is LIVE in prod (2026-06-24, v0.9.1):** `MENTOR_PROVISION_USERS=true` in
`.do/app.prod-crm.yaml` with a dedicated prod admin service account
(`ESPO_PROVISION_USERNAME=mentoradmin@cbmentors.org`, **Type=Admin** — User
creation is admin-only) + `MENTOR_TEAM_NAME="Mentor Team"`. **VERIFIED LIVE
end-to-end:** approving `doug@dougbower.com` in `/mentoradmin` provisioned his
login (logs showed `App/user` admin login `type=admin` → `Team?name=Mentor Team`
→ `POST /User 200` → `assignedUser` link on profile + Contact). The
`sendAccessInfo` welcome email **does deliver** — confirmed: it arrived at the
mentor's **CBM address** (`doug.bower@cbmentors.org`, = the User's userName/email),
which is correct. (Outbound email works despite `/Settings` reporting
`smtpServer=None` — it routes via a group/alternate account, not the system SMTP.)
Any mentor approved during the earlier off-window self-heals on the next Save.
**Mailbox check + CREATION + live status window (v0.11.0, built 2026-06-24 — NOT
yet deployed/verified live).** Approval provisioning now has a Google-Workspace
mailbox stage with a **streaming status modal** (SSE). `core/google_directory.py`
(`GoogleDirectory.mailbox_status` read-only check; **`create_user`** read-write
create; `resolve_google_directory` picks DB config over env);
`mentoradmin/service.py` `provision_mentor_user_steps` is an async generator that
yields a human-readable event per step (check → create-if-missing → poll ≤60s for
the new mailbox to go live → create EspoCRM login). The endpoint is the SSE
**`POST /mentoradmin/api/mentors/{id}/provision`**; the frontend Save sends the
field PUT with `provision:false`, then opens the status window and streams. On a
new mailbox the modal shows the **temp password** to relay (Google has no
email-the-credentials API; the mentor's personal email is set as the Workspace
**recovery email** so they can also self-reset). Behavior modes (effective config
= in-app Email Setup first, else `GOOGLE_*` env): check off ⇒ no Google stage;
check on + `create_mailbox` off ⇒ a confirmed-missing mailbox **blocks**
(pre-existing gate; inconclusive fails open); `create_mailbox` on ⇒ a missing
mailbox is **created** then provisioned; if it doesn't verify within ~60s the
mentor stays Approved and the next Save self-heals. **Creating** needs the service
account's **read-write** Directory scope (`admin.directory.user`) authorized for
domain-wide delegation, on top of the read-only scope. The inline (JS-off /
redrive) `update_mentor` path never creates — that long-running flow is the SSE
window's job.
**Admin-only "Email Setup" screen** (`GET/PUT/POST /mentoradmin/api/setup/google`,
gated on `isAdmin`) configures the Google auth at runtime: service-account JSON +
delegated admin + check/create toggles + a **Test connection** button (looks up
the delegated admin's own mailbox). The key is stored **encrypted** in Postgres
(`core/crypto.py` Fernet keyed by **`APP_ENCRYPTION_KEY`**; `core/app_config.py`
`AppConfigStore` + the `app_config` table, Alembic **`0003_app_config`**) and
takes precedence over the env vars. Disabled (shows "unavailable") without both
`DATABASE_URL` and `APP_ENCRYPTION_KEY`. To enable live: authorize both Directory
scopes for the service account in Google Admin, set `APP_ENCRYPTION_KEY` (web +
worker) + `GOOGLE_CREATE_MAILBOX=true`, then paste creds in Email Setup (or set
`GOOGLE_*` in the overlay) and run the pre-deploy migrate. 190 tests green.
Also note: v0.9.1 added a UI signal so an approval saved while provisioning is
disabled shows "no login was created" instead of a silent "Saved"
(`mentoradmin/service.py` `provision={disabled:true}`; was the original
"failed to properly update doug" report). **Staff-tool Teams — created, membership still to assign (verified 2026-06-26):**
all three exist in prod with the exact names the overlay expects —
`Client Administration Team` (gates `/assignments`), `Mentor Administration Team`
(gates `/mentoradmin`), `Mentor Team` (provisioned mentor logins land here, and it
correctly holds `doug.bower@cbmentors.org`). **But the two staff-gate teams have no
non-admin members yet** — Client Administration Team = 0 members, Mentor
Administration Team = 1 (only the `mentoradmin@cbmentors.org` admin service
account). So today the tools are usable **only by admins** (admins always pass the
gate). To hand them to CBM staff, add the real (non-admin) staff EspoCRM users to
those two teams in the CRM UI — that is the remaining gate for full parity. **Cleanup: DONE (verified 2026-06-26)** — the
`ZZTEST-PROD-GOLIVE` go-live records (5 Contacts, 3 Accounts,
CClientProfile+CEngagement, CMentorProfile, CInformationRequest, CPartnerProfile,
CSponsorProfile, + 5 CIntakeSubmission logs) are all gone. A full sweep of prod
(name/lastName `contains ZZTEST`/`GOLIVE` across all 9 entities → 0 matches; every
record listed) found no test records remaining — what's left is real intake data,
so nothing was deleted.

**As of 2026-06-22 — also live on App Platform against `crm-test`:** all **five**
intake forms (client-intake, volunteer, info-request, partner, sponsor), the
**V2** reliability platform (durable Postgres capture + async `delivery-worker` +
`/ops` console + alerting/schema-drift, Phases 0–3 activated), and all three
**staff tools** — **Client Administration** (`/assignments`), **Submission
Operations** (`/ops`), and **Mentor Administration** (`/mentoradmin`, incl.
approval → EspoCRM login provisioning, enabled + verified live). Each feature's
live-verification record is in its section above. The detailed go-live history
for the original two forms is preserved below.

**Goal (original, 2026-05-28):** publish the app on DigitalOcean for user
feedback. As of 2026-05-28 it was **deployed and live on App Platform against
crm-test** (go-live verified — see the LIVE block below). The original "feedback
first in dry-run, wire CRM later" plan was overtaken by Doug's decision to verify
and keep go-live live.

**Chosen path:** **DigitalOcean App Platform**, building the `Dockerfile`
straight from this GitHub repo (`dbower44022/cbm-client-intake`, branch `main`).
The method was evaluated against a droplet / co-hosting / other PaaS and
confirmed (decision record in `DEPLOYMENT.md`). It can run dry-run
(`ESPO_DRY_RUN=true`, committed `.do/app.yaml`) or live (`ESPO_DRY_RUN=false`
+ CRM secrets via the gitignored `.do/app.prod.yaml` overlay).

**Done:**
- Both forms build and serve (locally: `uv run uvicorn main:app --reload --port 8000`).
- Tests green (17 passing).
- Deploy glue committed at `12791d9` and **verified by a local Docker build+run**
  (`/healthz` → `{"status":"ok","dryRun":true,...}`, both forms 200):
  `Dockerfile`, `.dockerignore`, `.do/app.yaml`.

**Deployment method confirmed (2026-05-28): DigitalOcean App Platform.** The
method was re-evaluated against a droplet, co-hosting on the CRM box, and other
PaaS, and App Platform was confirmed (decision record + full comparison in
`DEPLOYMENT.md`). The prod-like container (the exact image App Platform builds)
was **tested locally and verified**: `docker build`/`run` → `/healthz` is
`dryRun:true`, both forms + index + shared assets 200, a dry-run
`POST /api/volunteer/intake` returns synthetic ids (no CRM call) and is
idempotent on token re-submit, `pytest` 17 passing.

**LIVE on App Platform, writing to crm-test (`dryRun:false`) — 2026-05-28.**
`./scripts/deploy.sh` created the app (dry-run), then it was flipped live against
crm-test and **go-live was verified end-to-end through the deployed app**: a
valid volunteer submission matched/created the Contact and created a
CMentorProfile in crm-test, edge returned **200 in ~0.4s** (`volunteer ok`
in the run logs). Per Doug's call, the app is **left live against crm-test**
(not reverted to dry-run).
- **App ID:** `509b4370-b9ca-42c7-b251-04d6820fe88e`
- **URL:** https://cbm-client-intake-svxs3.ondigitalocean.app
  (`/client-intake/`, `/volunteer/`); `/healthz` → `dryRun:false`
- **DO account:** `admin@cbmentors.org`. `doctl` installed (`~/.local/bin`,
  v1.160.0); GitHub repo connected to App Platform.
- **Live spec:** the gitignored `.do/app.prod.yaml` overlay (`ESPO_DRY_RUN=false`,
  `ESPO_BASE_URL=https://crm-test.clevelandbusinessmentors.org`, `ESPO_API_KEY`
  as encrypted `SECRET`). Applied with
  `doctl apps update <app-id> --spec .do/app.prod.yaml --wait`.
- Manage: `doctl apps logs 509b4370-b9ca-42c7-b251-04d6820fe88e --type run -f`;
  `git push` auto-redeploys (preserves env). `./scripts/deploy.sh` now **refuses**
  to update this app (its guard sees `ESPO_DRY_RUN=false`); use
  `ALLOW_LIVE_UPDATE=1` only to deliberately revert to dry-run.
- **Note:** real submissions must use the form's dropdown values (`options.js`,
  aligned to the CRM enums). Ad-hoc test data with an invalid enum value 400s
  on the profile create *after* the Contact is already created (find-or-create),
  leaving an orphan Contact — see `DEPLOYMENT.md` troubleshooting.

**Resume point — production go-live + cleanup.** `DEPLOYMENT.md` is the full
runbook: deploy, going-live, **custom domain**, **reproduce in production from
scratch**, verification, rollback, troubleshooting.
1. **Clean up** the 3 `ZZTEST-GOLIVE DeployCheck` records left in crm-test by
   the go-live verification (1 CMentorProfile + 2 Contacts) — in the EspoCRM UI
   (the create-only API user can't delete).
2. **Production go-live:** copy the approach to a production app or point
   `ESPO_BASE_URL` at the production CRM (re-key `ESPO_API_KEY` in the overlay).
   See `DEPLOYMENT.md` "Reproduce the deployment in production".

**EspoCRM wiring — BOTH forms VERIFIED end-to-end against crm-test (2026-05-28).**
- **client-intake**: created/linked Account → Contact → CClientProfile →
  CEngagement (all GET-verified 200).
- **volunteer**: created/linked Contact (`cContactType=["Mentor"]`) → CMentorProfile
  (`contactRecord` link), data verified on the records. The orchestrator was
  rewritten (commit 95765e4) from its wrong flat-Contact model to the deployed
  Contact+CMentorProfile model — mentor data lives on CMentorProfile, not flat
  Contact fields. Mapping decisions: mentorStatus=`Candidate`, mentorType=`Mentor`,
  multi-select industry → first `industrySector` only (single enum; multi-store
  deferred), terms_accepted → `termsAccepted`. The form's industry/expertise/
  language dropdowns are aligned to the deployed CRM enum options — a value
  outside the enum 400s the create (`forms/volunteer/frontend/options.js`).
  **Deferred:** resume upload (no
  attachment field deployed), `currently_employed`/`contact_preference`/`phone_type`
  (no target field). The volunteer mapping doc `score-volunteer-form-6-mapping.md`
  is now STALE (describes the old flat-Contact model) — orchestrator is the truth.

Local `.env` stays `ESPO_DRY_RUN=true`; live tests use an inline
`ESPO_DRY_RUN=false` override on a throwaway port. Findings while wiring:
- **Phone must be E.164** — crm-test rejects other formats with a phone "valid"
  failure; `core/phone.to_e164` normalizes at the CRM boundary (commit 95f841c).
- **API-user role** must grant *create* on CEngagement (was read-only until
  granted 2026-05-28); it already had create on Account/Contact/CClientProfile.
- **Account duplicate detection** — EspoCRM returns 409 on a same-named Account.
  RESOLVED (commit befa2cc): `_find_or_create_account` reuses a same-named match
  (exact, case-insensitive) instead of creating, so repeat submitters dedupe and
  the 409 path is avoided. Distinct businesses sharing a name collapse to one
  Account by design — split downstream if ever needed.
- Mapping source of truth: `forms/client_intake/orchestrator.py`; see also
  Technical Design §3.4 and the §11.1 pending-carry-forward set.

**Open follow-ups:**
- **CIntakeSubmission — log every submission** (spec in
  `cintake-submission-entity.md`). The app now writes a record for every
  submission (Normal/Honeypot/OrchestratorError), not just honeypot holds —
  `core/submission_log.py`. V1.0 entity is live in crm-test + create grant
  verified (2026-06-14). **Remaining CRM-side:**
  1. ✅ **DONE (verified live 2026-06-22)** — the `source` field, the `Normal`
     reason option, and the `contact → Contact` link all exist in crm-test, so
     Normal audit logs work for the three original forms. (Partner/Sponsor still
     pending the form-enum casing fix — see the partner/sponsor item above.)
  2. **OPEN (CRM build) — spec ready** — the **`reason != Normal`** alert-on-create
     workflow. Full, reason-aware spec (Email Template + Workflow + conditions +
     actions + gotchas) in `cintake-submission-entity.md` → "Alerting (CRM-owned)";
     CRM-owned, not yet built. Distinct from V2's worker alerting (CRM-delivery
     failures/backlog) — this fires on honeypot/orchestrator holds.
  3. ✅ **DONE (verified live 2026-06-24)** — `submitterEmail` now stores. It had
     been built as EspoCRM type `email`, which binds to the entity's primary
     `emailAddress` field, so a custom-named email-type field silently stored
     NOTHING — every record had a null `submitterEmail` despite the address being in
     `name`/`description` (the value stayed null whether the app sent a plain string
     OR a `submitterEmailData` array; 0.10.3 tried the array, reverted in 0.10.4).
     Fixed CRM-side: the field was deleted + recreated as **`varchar`** in dev +
     prod; the app's plain-string write now populates it (verified live via a test
     submission — `submitterEmail` stored). No code change beyond the 0.10.4 revert.
  4. Clean up the `ZZTEST-INTAKE GrantCheck` probe record
     (id `6a2eec00c83e44628`) in the EspoCRM UI. (The `ZZTEST EmailFix` records from
     the 2026-06-24 submitterEmail diagnosis were already cleaned up.)
- Make the *deployed* app write to EspoCRM: set `ESPO_DRY_RUN=false` plus
  `ESPO_BASE_URL` + `ESPO_API_KEY` as **encrypted** App Platform env vars.
- Clean up the `ZZTEST` test records left in crm-test by the wiring tests
  (must be done in the EspoCRM UI — the intake API user is create-only and
  cannot delete; verified by 403s).
- ~~Evaluate an alternative deployment method~~ **Done (2026-05-28).** App
  Platform was re-evaluated and confirmed; see the decision record in
  `DEPLOYMENT.md`. The kickoff that drove it is
  `prompts/CLAUDE-CODE-PROMPT-deployment-method.md`.

## Commands

```bash
uv sync                                  # install deps (uv-managed; package = false)
uv run uvicorn main:app --reload --port 8000   # run locally -> http://localhost:8000/
uv run pytest -q                         # tests
docker build -t cbm-intake . && docker run --rm -p 8099:8080 cbm-intake  # prod-like run
./scripts/deploy.sh                      # deploy to DO App Platform (see DEPLOYMENT.md)
uv run python scripts/sync_form_options.py          # dry-run: form dropdowns vs live CRM enums
uv run python scripts/sync_form_options.py --write  # apply the sync (review the git diff)
```

## Architecture

A shared core hosts any number of per-form packages.

- `main.py` — composition root: `create_app([client_intake.SPEC, volunteer.SPEC])`.
- `core/` — the only place that holds EspoCRM credentials.
  - `app.py` — FastAPI factory. Per form it exposes `POST /api/{slug}/intake`
    and serves `/{slug}/`. Also `GET /` (form index), `GET /healthz`, and
    `/shared/` for the design tokens / wizard assets. Honeypot (`company_url`)
    and a `submission_token` idempotency cache live here.
  - `submission_log.py` — writes a `CIntakeSubmission` CRM record for **every**
    submission (`core.submission_log`): `reason=Normal`/`status=Processed` on
    success (linked to the Contact via `contactId`), `OrchestratorError`/`New`
    on a CRM failure, `Honeypot`/`New` on a honeypot hit. Gives an audit trail
    (raw input vs. the transformed records) + inbound analytics (by `form`,
    `source`, native `createdAt`; conversion via the `contact` link). The review
    queue is `status=New`; `Normal` is the log. `description` carries the raw
    JSON (honeypot field cleared; reprocess steps for held records; large base64
    redacted). Create-only (write happens after the outcome — no edit grant).
    All writes are **best-effort**: a CRM-write failure logs the payload at
    WARNING and never breaks the submission, so the app deploys safely ahead of
    the CRM build. **CRM dependency** (see `cintake-submission-entity.md`): the
    `CIntakeSubmission` entity/fields/`contact` link, the create grant, and a
    `reason != Normal` alert-on-create workflow (CRM-owned alerting, not in the app).
  - `espo.py` — `EspoClient` (real) and `DryRunEspoClient` (logs + synthetic ids).
  - `config.py` — `pydantic-settings`. **All settings default**, and
    `espo_dry_run` defaults to `True`, so the app boots with zero env vars.
  - `forms.py` — the `FormSpec` + `BaseSubmission` registry contract.
- `forms/<name>/` — one form per package: `schemas.py` (submission model),
  `orchestrator.py` (EspoCRM mapping), `frontend/` (static wizard), and `SPEC`.
- `frontend/shared/` — `tokens.css` (CBM design tokens extracted from the
  staging site), `wizard.css`, `wizard.js` (shared step controller).

The frontend is plain HTML/CSS/vanilla JS — **no build step**. The wizard posts
to its own origin, so CORS is not in the form's request path; `ALLOWED_ORIGINS`
only matters if a separate frontend origin is ever introduced.

### Environment indicator — which deploy am I looking at? (added v0.12.0; moved to footer v0.19.0)

Every page names the deploy target in the **footer, right after the version** —
`v0.19.0 (Production)` / `(Test)` / `(Dev)` — so a tester or staffer can tell whether
a form writes to the production CRM, crm-test, or nothing (dry-run). The label is
**derived server-side**, not configured per deploy: `core/config.Settings.environment`
returns `dev` when `espo_dry_run` is on, `test` when `espo_base_url` contains
`crm-test`, else `production` (an explicit `ENV_LABEL` env var overrides the wording).
It auto-resolves for all three App Platform apps (dev/lobster, crm-test, prod) with
**no overlay changes**. Surfaced on `/healthz` as `environment`. Rendered two ways:
- **Forms** — the shared `frontend/shared/footer.js` reads `/healthz` and appends the
  env name to the `[data-cbm-version]` text; one change covers all five forms.
- **Landing page** (`GET /`) — server-rendered, so `core/app.py:_env_name` appends it
  to the footer version string directly.

(Until v0.19.0 this was a color-coded corner badge; replaced by the inline footer
label per request. The old `.cbm-env-badge` CSS + `_env_badge_html` were removed.)

### Form dropdown lists — static, synced from the CRM on demand

Each form's `frontend/options.js` ships **hand-curated, static** value lists (the
forms stay fast/stateless — no CRM call at page load). The lists that are backed
by a CRM enum **must match the live options verbatim** or a value outside the
enum 400s the record create (the orchestrators' `EnumSanitizer` then drops the
drifted value, so the field silently stores nothing). To keep them aligned
**without** going live-fetch, each CRM-backed array is wrapped in sentinel
comments and refreshed by a script:

```js
// >>> crm-enum key=industryExperience field=CMentorProfile.industrySector — generated; do not hand-edit between the markers.
industryExperience: [ ... ],
// <<< crm-enum
```

`scripts/sync_form_options.py` scans `forms/*/frontend/options.js` for those
markers, fetches each `Entity.field`'s live options
(`EspoClient.metadata_enum_options`), and rewrites **only** the marked arrays —
presentational lists (how-did-you-hear, phone type) and all comments are left
untouched. The marker is self-describing (no mapping duplicated in the script);
it supports `exclude="A|B"` for CRM values the form deliberately omits (e.g.
partner `partnershipValue` excludes `"None"`), and blank/whitespace-only enum
options are auto-dropped. Default run is a **non-destructive dry-run** (value-level
summary + unified diff, exits non-zero on drift so it doubles as a CI check);
`--write` applies, then **review the git diff and commit** (per the push
convention). 8 lists are managed today: volunteer `industryExperience`/
`areasOfExpertise`/`fluentLanguages`; client-intake `businessStage`/
`industrySector`/`mentoringFocusAreas` (it warns if a synced `industrySector`
orphans an `industrySubsector` key); partner `partnershipType`/`partnershipValue`.

The script reads `ESPO_BASE_URL`/`ESPO_API_KEY` from the env/`.env` (defaults to
crm-test). To check **prod**, override them for one run (read-only — metadata
GETs only); the prod key lives in the gitignored `.do/app.prod-crm.yaml`:

```bash
ESPO_BASE_URL=https://crm.clevelandbusinessmentors.org \
ESPO_API_KEY=$(grep -m1 'key: ESPO_API_KEY' .do/app.prod-crm.yaml \
  | grep -oE 'value: "[^"]+"' | sed -E 's/value: "([^"]+)"/\1/') \
uv run python scripts/sync_form_options.py
```

Since the static file serves **both** deploys, the synced values must be valid on
crm-test *and* prod — the dry-run is also how you'd catch the two CRMs diverging.
First sync (2026-06-25): volunteer `industryExperience` was 100% stale (the live
`CMentorProfile.industrySector` is now the 20-value NAICS taxonomy on both
crm-test and prod, so volunteer industry was being dropped on real submissions);
the synced lists were verified identical on crm-test and prod.

## Gotchas / things learned

- **Enum drift is tolerated on record creates (2026-06-23, v0.6.0 volunteer →
  v0.7.0 all forms).** `core/enum_filter.py` `EnumSanitizer` validates
  enum/multiEnum payload values against the live CRM options
  (`EspoApi.metadata_enum_options`, now on the protocol + dry-run +
  `ResumableClient`) and **drops** unrecognized ones instead of letting a single
  drifted value 400 the whole create. Applied to the **user-supplied** enum
  fields (NOT the system discriminators `cAccountType`/`cContactType`/status,
  which are required/monitored): volunteer → `industrySector`/`mentoringFocusAreas`/
  `fluentLanguages` (note on `CMentorProfile.description`); client-intake →
  `cBusinessStage`/`cIndustrySector` (Account) + `mentoringFocusAreas` (CEngagement,
  aggregated note on `CEngagement.description`); partner → `partnershipType`/
  `partnershipValue` (note on `CPartnerProfile.description`). Sponsor writes no
  user enum (just a free-text message), so nothing to sanitize. One `EnumSanitizer`
  per delivery spans the whole chain (entity passed per call) and aggregates a
  single note. Fails open (keeps the value if options can't be fetched, e.g.
  dry-run). This is why re-driving a drift-failed submission now succeeds.
- **Implausible phone numbers are dropped, not fatal (2026-06-23, v0.8.0).**
  `core/phone.e164_or_none` returns None for a value that can't be a real phone
  (<10 or >15 digits, e.g. a user typing "12345" → EspoCRM 400 `phoneNumber`
  "valid"). All orchestrators now use it and **omit** `phoneNumber` when invalid
  rather than failing the Contact create — email stays the contact channel and
  the raw value is preserved in the CIntakeSubmission audit log. (This was the
  one stuck volunteer re-drive that still failed after enum resilience: phone
  "12345".)
- **`.dockerignore` must exclude `.venv`** — `COPY . .` otherwise copies the
  host virtualenv over the container's, whose interpreter paths are wrong
  (`sh: .venv/bin/uvicorn: not found`, exit 127). It also keeps `.env` out of
  the image.
- The app is **stateless**: no DB, no disk writes (resume upload is base64
  in-memory). On App Platform the filesystem is ephemeral and the idempotency
  cache resets on redeploy — fine for a dry-run feedback build, but **dry-run
  submissions are logged only, not stored**, so there is no record of what
  testers submitted beyond runtime logs.
- The EspoCRM integration was reconciled against the `crm-test` instance
  (Technical Design v0.3): the Engagement links to a **CClientProfile** hub,
  not directly to the Account.
- Canonical SCORE field inventory / mapping lives here
  (`score-*-form*.md`, `score-mentor-request-form.yaml`). Copies may appear as
  scratch under the separate `crmbuilder` repo root — those are not canonical.

## Documentation

- `README.md` — repo overview: the forms, the staff tools, the V2 platform, how
  to run locally / add a form.
- `CHANGELOG.md` — notable changes by version (the value `/healthz`/footer report,
  which is also the App Platform deploy marker).
- `prds/CBM_Client_Intake_Requirements_Specification.md` — what it must do.
- `prds/CBM_Client_Intake_Technical_Design.md` — how it's built (deployment in
  §6, open issues in §7, EspoCRM mapping in §3). NOTE: the formal prds focus on
  the **client-intake** form/process; the other forms + staff tools + V2 are
  documented here in CLAUDE.md and in `prds/v2/` (V2 specs).
- `DEPLOYMENT.md` — engineer deploy runbook (App Platform), incl. the staff-tool
  + mentor-provisioning env vars. `STAFF-DEPLOYMENT-GUIDE.md` — plain-language
  console-only companion for CBM staff.
- `mentor-administration.md` — functional reference for the `/mentoradmin` tool:
  overall functionality + the **complete-record requirements** (the completeness
  rules, in plain language).
- `communications-tab.md` — plain-language functional reference for the session
  tools' Communications tab (where conversations come from, cleaning, curation,
  compose rules, who-sees-what, "why don't I see…" answers).
- `prds/v2/` — the V2 reliability platform specs (durable capture + async worker
  + ops + alerting).

## Conventions

- **Push convention:** Claude commits in this local clone; **Doug reviews and
  pushes**. Do not push without being asked.
- Never commit `.env` or any secret. Secrets are injected as environment
  variables at deploy time (App Platform encrypted env vars).
- Commit messages follow Conventional Commits (`feat:`, `build:`, `docs:`, …).
