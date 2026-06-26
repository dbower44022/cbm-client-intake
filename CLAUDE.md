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

**Phase 2 — operations console, scaffolded 2026-06-22.** A staff-only view of the
durable store at **`/ops`** (`ops/` package), gated by the same EspoCRM team-auth
as `/assignments` (reuses `assignments.auth`; one staff session covers both) and
mounted only when `assignments_active`. `GET /ops/api/submissions` (filter by
status/form) + counts; `GET /ops/api/submissions/{id}` (payload/progress/error);
`POST /ops/api/submissions/{id}/redrive` (→ pending, due now, attempts reset — the
worker re-runs it resumably). Store gains `list_submissions`/`get_submission`/
`counts_by_status`/`redrive`; the store is exposed via `app.state.submission_store`.
Endpoints 503 if no store. Linked from the form index under "Staff". Verified
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
`assignments_active` gate + SessionMiddleware). It reuses the assignment tool's
EspoCRM team-auth but is gated to the **Mentor Administration Team** and kept in
its **own session key** (`mentoradmin_user`), so a Mentor-Admin login is separate
from `/assignments`. It lists the **full mentor roster** (reuses
`assignments.service.list_all_mentors` — same searchable/filterable/sortable grid
as "Available Mentors", any status), and lets staff **open any mentor** to a
detail screen that reviews all info (read-only computed totals on top) and
**edits status + any editable field**, saving back to `CMentorProfile`.

- **Auth = per-user, acts as the logged-in user** (same model as `/assignments`):
  login via `authenticate(..., allowed_teams=mentor_admin_allowed_teams_list,
  allowed_roles=[])` → EspoCRM `App/user`; token in a signed session cookie;
  all reads/writes run as that user so EspoCRM enforces their ACL on
  CMentorProfile. Gate is **Team-only** (`MENTOR_ADMIN_ALLOWED_TEAMS`, default
  `Mentor Administration Team`); admins always pass. Session-expired (CRM 401) →
  clears session + 401 (same `auth.session_expired` handling).
- **Editable-field set is declared in `mentoradmin/service.py:EDITABLE_FIELDS`**
  (the single source for both the form layout — grouped Status/Capacity/Expertise/
  Compliance/Dates/Profile/Bio — and the server-side update **whitelist**:
  `update_mentor` drops anything not in `EDITABLE_NAMES`). Enum/multi-enum
  **options are pulled live** from EspoCRM metadata (`GET /Metadata?key=
  entityDefs.CMentorProfile.fields`, via `EspoClient.metadata`) so the CRM stays
  the source of truth — see `service.field_options`. Computed totals
  (`availableCapacity`, `currentActiveClients`, `total*`) are read-only context.
- **Endpoints** (`/mentoradmin/api`): `login`/`logout`/`session`; `GET /mentors`
  (roster); `GET /fields` (EDITABLE_FIELDS + live options); `GET /mentors/{id}`
  (full record); `PUT /mentors/{id}` `{changes:{...}}` (whitelisted update).
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
  linked (the `CMentorProfile` *is* the "CBM member" record), and background
  check / ethics / training / terms are all true; plus, **if Active**, a CBM
  email address + a User assigned to the member AND the same User to its Contact;
  plus, if **`publicProfile`** is set (editable bool on the Status tab),
  About-the-mentor text + ≥1 mentoring focus area + ≥1 area of expertise + an
  industry sector. On **every save**,
  `service.reconcile_user_links` (best-effort) assigns the mentor's User
  (`CMentorProfile.assignedUser`, or the Contact's if only that side has one) to
  **both** the member and its Contact — filling the gap provisioning leaves (it
  sets the member's User only) and self-healing one-sided assignments, so the
  "no User assigned to the Contact" completeness issue auto-resolves on save.
  The computed status is **persisted** to the CRM `recordStatus` enum
  (`Complete`/`Incomplete`; a manual `Duplicate` is preserved, never overwritten)
  **on save** when it changes (`service.sync_record_status`; not on view, to
  avoid churning modifiedAt/modifiedBy — the detail GET still computes it for the
  badge), so the
  **roster grid** shows a **Record** column + filter (read from the stored field
  — fresh for any mentor that's been viewed/saved) to spot who needs work without
  recomputing per row. `recordStatus` is in the shared `assignments` mentor row.
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
`engagementStatus="Submitted"` in a grid; each row has a dropdown of mentors
**accepting new clients** and, on confirm, assigns the engagement to the chosen
mentor.

- **Auth = per-user, acts as the logged-in user.** Staff log in with their own
  EspoCRM username/password (`POST /assignments/api/login` → EspoCRM `App/user`
  with the `Espo-Authorization` header). The returned auth token is kept in a
  signed session cookie and replayed (`Espo-Authorization` + by-token header) so
  **all reads/writes run as that user** — EspoCRM enforces their ACL and records
  them as modifier. Access gated to active internal users who are admin, belong
  to an allowed **Team** (`ASSIGN_ALLOWED_TEAMS`, the primary gate — set to
  `Client Administration Team`), OR hold an allowed Role (`ASSIGN_ALLOWED_ROLES`).
  **Gate by Team, not Role:** a regular user's own token can read its `teamsNames`
  but NOT its `rolesNames` (EspoCRM strips role names for users without Role-scope
  read — verified live: a valid non-admin login returned `roles=[]`). (The shared
  `customapps` API user is NOT used here — create-only, and it can't even read
  Teams/Users/Roles.)
- **Mentor dropdown** = `CMentorProfile` where `acceptingNewClients=true` AND
  `mentorStatus="Active"` AND `assignedUser` set. The mentor's login User =
  `CMentorProfile.assignedUser`.
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

## Current status (updated 2026-06-26)

**Prod is on v0.11.2** (`/healthz` confirmed, App `33dbecd`). The Google Workspace
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
"failed to properly update doug" report). **Still pending for full parity:** the
staff-tool Teams (`Client Administration Team`, `Mentor Administration Team`)
must exist in prod with staff users. **Cleanup: DONE (verified 2026-06-26)** — the
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
- `prds/v2/` — the V2 reliability platform specs (durable capture + async worker
  + ops + alerting).

## Conventions

- **Push convention:** Claude commits in this local clone; **Doug reviews and
  pushes**. Do not push without being asked.
- Never commit `.env` or any secret. Secrets are injected as environment
  variables at deploy time (App Platform encrypted env vars).
- Commit messages follow Conventional Commits (`feat:`, `build:`, `docs:`, …).
