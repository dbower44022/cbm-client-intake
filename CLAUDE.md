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
**REBUILT 2026-07-19 (v0.106.0–v0.108.0, Doug's spec)** into a resolution
console — modern grid (sort/resize/search/alt-rows, Open-by-default
resolution filter, awaiting-reply column), sessions-style tabbed detail
(Overview facts + staff `notes` (migration 0011) + submitter conversation;
Details with CRM deep links; Communications with reply-threaded compose +
the `InfoRequestReply` template pre-applied via `OPS_REPLY_TEMPLATE`),
`resolved_at/by` workflow (migration 0012). Conversation was originally a
live Gmail search of the signed-in admin's OWN mailbox (per-admin
visibility) — **superseded in v0.110.0 by the shared info@ mailbox model**
(thread-anchored conversations read/sent as OPS_MAILBOX, inbound info@
capture into the queue as held info-email submissions; see the v0.110.0
Current-status block). Functional reference for staff:
**`submission-admin.md`**; mechanics in CHANGELOG 0.106.0/0.108.0/0.110.0
and the Current-status blocks.

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

## My Mentor Profile tool — `/mentorprofile` (added 2026-07-14)

A **mentor self-service** tool (Mentor Team, not staff-only): a mentor edits
their OWN `CMentorProfile` + linked Contact from one screen, with a live
side-by-side preview that is an **EXACT reproduction of the public website
mentor page** (Doug's ruling 2026-07-14 — the point is editing to look good on
the site, so the page's own HTML + CSS were copied VERBATIM from the Elementor
widget at clevelandbusinessmentors.org/mentor/mike-lawson/ into
`mentorprofile/frontend/` — the marked block in styles.css + the `.cbm-wrap`
markup in index.html; **keep that block in sync if the website template
changes**). Rendered at the site's 1200px desktop width, scaled to fit the
pane (`fitPreview`); the site's mobile @media block is deliberately omitted
(the preview always shows the desktop rendering); static page links are inert,
a real LinkedIn URL opens new-tab. The CRM is the planned feed for the website
pages; the preview fills exactly the feed slots: photo=`profilePhoto` (image
field), name=Contact firstName+lastName, headline (gold hero line) =
`mentorTitle` (varchar, built on crm-test 2026-07-14), left summary paragraph
= **`mentorSummary` (feature-gated — see below)**, Industry Experience box =
`industryExperience` (semicolon-joined), Areas-of-Expertise gold-dot list =
`areaOfExpertise`, About box=`aboutMentor`, LinkedIn button=Contact
`cLinkedInProfile`; first name also flows into "ABOUT {FIRST}" / "About
{first}" / "Ready to Connect with {first}?". The full page-slot ↔ CRM-field
mapping (for the WP feed) is in `cmentorprofile-summary-field.md`. Portal tile
"My Mentor Profile" for Mentor Team members; aliases `/mentorprofile`,
`/myprofile`.

- **`mentorSummary` is feature-gated (NOT built in the CRM yet).** Doug's
  ruling: the website's short left-column summary gets its own CRM field
  (spec + build handoff: `cmentorprofile-summary-field.md`; Text,
  CMentorProfile). The app feature-detects it from metadata
  (`service.gated_fields_present`/`field_spec_live`, the sessionTranscription
  precedent): until it exists the editor omits the box and reads/saves drop
  the field; once built it activates with no app deploy.

- **Always "me" — no record id from the client.** Every endpoint resolves the
  caller's own profile server-side via `sessions.service.resolve_manager_profile`
  (Python-side `assignedUser` match — never a `where` on `assignedUserId`;
  handles both the single-`assignedUser` and collaborators shapes). All
  reads/writes run as the logged-in user (`client_for`), so EspoCRM enforces
  their ACL. Gate: `MENTOR_PROFILE_ALLOWED_TEAMS` (default `Mentor Team`),
  per request; admins pass; 401 → `/?next=/mentorprofile/`. A Mentor Team
  login with **no linked profile** gets a friendly "contact CBM staff" message
  (`profileFound: false`).
- **Editable-field set = `mentorprofile/service.py:PROFILE_FIELDS`** (form
  layout + server-side whitelist, mentoradmin pattern) — deliberately
  **non-administrative** (v0.45.0 layout, Doug's review): a **top bar** with
  the photo and the two PROMINENT status toggles opposite it
  (`publicProfile` + `acceptingNewClients`, `toggle: True` — 18px bold cards,
  green when on / amber when off); Public profile
  (headline/summary/expertise/industries/about/LinkedIn); **Contact
  information side by side with a Personal details panel**
  (`Contact.cBirthday` + `Contact.cSpouseName` — exist on both CRMs — plus
  `yearsOfExperience`); Mentoring preferences (`maximumClientCapacity` left
  of the pause dates — capacity is mentor-editable since v0.45.0,
  `mentorBusinessStagePref`, `fluentLanguages`); More about you
  (`mentorProfessionalBio`, `mentoringWhyInterested`); and **Internal CRM
  description** (`description`, large plain-text box) at the very bottom. A
  read-only **"Mentoring since mm/dd/yyyy"** badge (`mentorStartDate`,
  `READ_ONLY_FIELDS`) sits in the page header. mentorStatus/type, compliance,
  dues, cbmEmail, departure etc. are NOT in the whitelist — smuggled changes
  are dropped. Contact fields route to the linked Contact (E.164 phone; no
  linked Contact ⇒ 400 before any write). Enum options + required flags read
  live from CRM metadata (both entities); drifted enum values sanitized on
  save with plain-language warnings (fails open); the frontend diffs against
  render snapshots and sends only changed fields.
- **Photo** (`CMentorProfile.profilePhoto`, EspoCRM image field): upload =
  base64 JSON (volunteer-resume precedent, no multipart dep) → Attachment
  bound to the field → `profilePhotoId` set; JPEG/PNG/WebP/GIF ≤5 MB; remove
  clears the link. Display goes through the app (`GET /mentorprofile/api/photo`
  streams the bytes via the NEW `EspoClient.download_attachment` under the
  user's token) since the browser can't reach the CRM. Uploads happen
  immediately, outside the Save diff.
- **Endpoints** (`/mentorprofile/api`): `session`/`logout`; `GET /fields`
  (spec + live options + required); `GET /profile`; `PUT /profile`
  `{changes:{...}}`; `POST /photo` `{filename,contentType,dataBase64}`;
  `GET /photo`; `DELETE /photo`. Frontend `mentorprofile/frontend/` (vanilla
  JS): full-width (no page-width cap — Doug's ruling), stacked grouped form
  left, website preview right, drag splitter; preview updates live on every
  input (wysiwyg sanitized before rendering); `publicProfile` off ⇒
  "not shown on the website" banner + dimmed preview.
- **Status (2026-07-14): DEPLOYED (v0.43.0) + driven LIVE on crm-test as a
  real non-admin mentor (doug.bower); 443 tests green.** Live results: portal
  tile shown; own-profile resolution picked the LINKED "Douglas Bower"
  profile (not the unassigned duplicate); the **feature-gated `mentorSummary`
  box appeared on its own** (field built in the CRM that day) and **stored**;
  `mentorTitle` + `industryExperience` + summary GET-verified on the record
  with `modifiedBy` = the mentor; Contact merge (email/LinkedIn) worked; the
  **drifted-enum warning fired on real data** (stored `areaOfExpertise`
  "Business Plan" is no longer a live option — dropped with the plain-language
  note). **Both CRM role gaps found during the test are RESOLVED (same day):**
  the crm-test **"Mentor Role" carried a 59-field field-level lockdown on
  CMentorProfile (every field edit:no, six also read:no)** — EspoCRM
  *silently strips* write-denied attributes from a save (200 OK, value
  unchanged), which is why `areaOfExpertise` wouldn't store and why the photo
  upload 403'd (`profilePhoto` edit:no gates the Attachment POST — never an
  Attachment-scope problem). Diagnosis path: enumerate the login's roles via
  the admin service account and read each Role's `fieldData` (the user had
  SIX team roles; only Mentor Role defined field locks; newer fields —
  mentorTitle/mentorSummary/industryExperience — weren't on the old list,
  which is why they saved: that inconsistency is the signature of field-level
  ACL). Doug's ruling: **delete the entire list** (matches prod, which he
  reports has no field-level locks) — cleared via the admin API 2026-07-14
  (old list backed up in the session scratchpad); note this re-exposes
  dues/felony/rejection fields to mentor READS (Mentor Role has read:all on
  CMentorProfile). After the clear, **expertise save + photo upload + photo
  GET all VERIFIED LIVE as the non-admin mentor** (photo renders in the
  preview hero; record GET-verified; the test photo on Douglas Bower's
  profile is a generated placeholder — replace/Remove in the tool). Also
  fixed: a CRM 403 surfaced as a blank 504 — now a readable "contact CBM
  staff" 403. **Post-verification polish (same day, all deployed):** v0.45.0
  layout/field pass per Doug's review (see the Editable-field-set bullet),
  v0.45.2/.45.4 "Mentoring since" placement (final: a centered line at the
  top of the form section, above the photo/toggles bar), footer parity with
  the other apps ("All rights reserved." + " · vX.Y.Z (Test/Production)" —
  the separator rule lives in this app's own styles.css since it doesn't
  load wizard.css). Earlier the same day: verified in the stubbed-browser harness
  (computed styles match the live page — navy #00205B hero, gold #B58113,
  42px Arial-Rounded name, 1fr/2fr grid, #0077b5 LinkedIn button; live
  updates incl. all four name slots; XSS stripped from the preview;
  publish-toggle banner + dim; photo local-preview→upload→remove; diffed
  saves; required blocks; splitter refit).
- **CRM prerequisites (activation checklist):**
  1. ✅ **DONE — fields exist on BOTH CRMs** (verified live 2026-07-14):
     `mentorTitle` (varchar) + `profilePhoto` (image) + `mentorSummary` (text)
     + `Contact.cLinkedInProfile` (url) confirmed identical on crm-test AND
     prod, so the tool is effectively LIVE on prod for Mentor Team members
     (prod's Mentor Role has no field-level locks per Doug's UI check —
     unverified by API; the crm-test lockdown story is in the Status bullet).
     ✅ **Prod smoke test implicitly PASSED (2026-07-14):** Doug's prod
     profile carries mentorTitle + mentorSummary + a profile photo — fields
     only this tool writes — and opening `/mentorprofile` on prod loaded the
     full record + Contact into the form. Read, save, and photo upload all
     confirmed working on production.
  2. **Mentor Team role**: `CMentorProfile` read-own + edit-own with
     field-level write on the PROFILE_FIELDS set + `profilePhotoId`; Contact
     edit-own (the mentor's Contact must have their User assigned —
     mentoradmin's `reconcile_user_links` self-heals it on staff saves).
  3. **Attachment**: a Mentor Team user must be able to create an Attachment
     for `CMentorProfile.profilePhoto` and read it back
     (`GET /Attachment/file/{id}`) — the key live ACL unknown.
  4. Data: each mentor's profile linked to their login User (watch the
     duplicate-profile gotcha) and to a Contact.
  5. Live verification: sign in as a non-admin mentor → own profile resolves;
     edit `mentorTitle` + a Contact field → GET-verify both records; photo
     upload/fetch; a smuggled `mentorStatus` change is NOT saved; portal tile
     only for Mentor Team.

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
  **Merge, never overwrite, on the client records (v0.76.1; contacts since the
  2026-07-17 Contact collaborators switch):** every collaborators-entity
  re-home (CClientProfile / Account / now Contact too) writes
  `assignedUsersIds` as the record's EXISTING list + the new mentor + the
  engagement's co-mentors' users (`_merged_assignment_payload`) — the old
  `[user_id]` overwrite silently revoked co-mentor access stamped by the
  session tools.
  **Stale-write guard (v0.72.1, 2026-07-16):** before any write the engagement is
  re-read and the call is rejected (AssignError → 400, nothing written) if it
  already has a mentor OR its status is no longer `Submitted` — a second
  browser/tab with an out-of-date grid had silently re-assigned an engagement
  (seen as a double assignment in prod Espo history, eng `6a4955b75f19ff03a`).
  The frontend reloads the grid on any Assign 400 so the stale row corrects.
  **Stream note (v0.74.0):** every app Assign also posts a best-effort Note
  onto the engagement's stream ("Assigned to X via the Client Administration
  app — … re-homed: N/N contact(s), client profile, company") via
  `core/stream.post_stream_note` — app writes are otherwise indistinguishable
  in Espo history from hand edits by the same user. The co-mentor add/remove
  paths post notes too.
- **Grid UX (v0.79.0–v0.80.0, 2026-07-17, Doug's layout pass — all
  frontend-only):** the page is a full-height flex column — the engagement
  grid fills all vertical space under the control line and **scrolls
  internally with a sticky header** (no page width cap; `box-sizing:
  border-box` on `.assign` — width:100% + container padding overflowed
  without it). "Signed in as …" + Sign out live in a **top-right user-profile
  corner**; ONE control line holds the Status filter, a **live full-text
  search** (name/status/client/contact/mentor/notes/created+assigned dates;
  no-match state has its own message), and the Reassign Mentor / Review
  Mentors / Refresh buttons. New sortable **Days Assigned** column (whole
  local-calendar days from `engagementAssignedDate` to today; unassigned "—";
  first click = longest first). **No gating disables** — the Assign button is
  always active and a mentor-less click shows a notice + focuses the dropdown
  ([[buttons-never-disabled-validate-on-click]], product-wide ruling).
- **Post-assign notice email (v0.79.0):** a successful Assign OR Reassign
  opens the shared quick-compose with To = the mentor's `cbmEmail` and the
  EspoCRM **`MentorAssignmentNotice`** template pre-applied
  (`CBMQuickMail.composeIfEnabled(email, {template})` — silent fallbacks:
  missing template / failed parse ⇒ blank compose; sending unavailable ⇒
  nothing opens). Template verified EXISTING on both CRMs 2026-07-17
  (read-only DB query via the droplets; prod copy has a category — irrelevant,
  the record-less quicksend list is context-unfiltered).
- **Reassign Mentor (v0.81.0):** click a row to select it (right-click also
  selects), then the toolbar button or **right-click context menu** (View
  details / Reassign mentor… / Assign mentor… on unassigned rows / Edit
  notes / Refresh — every row function is right-clickable). Mentor-picker
  dialog (current mentor excluded; inline "Select a mentor first." on empty
  confirm). `POST /engagements/{id}/reassign` →
  `service.reassign_engagement`: same eligibility bar as assign; requires an
  existing, DIFFERENT mentor; swaps `mentorProfile` + re-stamps
  `engagementAssignedDate`; **`engagementStatus` deliberately untouched** (no
  re-acceptance round); re-homes assigned users on the engagement + every
  Contact + CClientProfile + Account + **every CSession on the engagement**
  (swap-merge: old mentor's User removed unless a co-mentor shares it or they
  personally own the session; co-mentors always preserved). Downstream
  failures per-record best-effort (`reassignmentErrors` → UI + note); DOC-09
  Drive grants re-synced after. **History** (stream note, Doug's exact
  wording): "Mentor X was replaced with Mentor Y on MM/DD/YYYY by user NAME."
  (Cleveland date) + the re-homing tally. NOT yet driven live — the staff
  role needs CSession read+edit for the session re-stamp (failures surface,
  never fatal) and Note create for the history stamp.
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
- **Assignment field: ALL five entities now use `assignedUsers` (collaborators)**
  — CEngagement/CClientProfile/CMentorProfile/Account since the original builds,
  and **Contact + Account were deliberately switched to Multiple Assigned Users
  on BOTH CRMs 2026-07-16/17** (Doug: co-mentors must be assignable to client
  contacts). A switched entity's single `assignedUser` is `disabled: true`:
  reads return null (hiding previously-stored values) and writes are silently
  ignored. The service dual-writes both attributes everywhere
  (`assignments/service.py:_assigned_user_payload`, `USES_ASSIGNED_USERS` = all
  five), merging into (never overwriting) the multi list on client records +
  contacts so co-mentor stamps survive. The Contact switch was the cause of the
  v0.82.0 "every mentor Incomplete: no User assigned to the Contact" regression
  in `/mentoradmin` (completeness read only `assignedUserId`).

## Session Management tools — `/mentorsessions`, `/partnersessions`, `/sponsorsessions` (added 2026-07-08)

**User-facing app titles (renamed 2026-07-19, v0.104.0 — Doug's ruling):
"Client Management" (/mentorsessions), "Partner Management"
(/partnersessions), "Funder Management" (/sponsorsessions)** — portal tiles,
page headings, and browser-tab titles all read from `DomainConfig.title` /
`portal/router._apps_for`, so the names live in exactly two places. The
packages/routes/slugs/team gates are UNCHANGED (the assignments →
"Client Administration" precedent). Note "Funder" is display wording only —
the CRM entities stay CSponsorProfile etc.; deeper sponsor→funder copy
(grid columns, empty states, "Sponsor Notes") was deliberately NOT swept.

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
  **EXCEPTION — the partner AND sponsor grids list ALL records (partner
  v0.89.0, Doug's ruling 2026-07-18; sponsor v0.113.0, Doug's ruling
  2026-07-20):** `DomainConfig.list_all=True` on those domains replaces
  the reverse-link read with a plain paginated `CPartnerProfile` /
  `CSponsorProfile` list — the user's ACL is the gate (team permissions
  CRM-side), `profileFound` is always true, and the manager profile isn't
  resolved for the list (so the list never reads CMentorProfile — the
  sponsor-team 403 that prompted v0.113.0). New intake-created partners /
  sponsors are stamped with their team (orchestrators; `PARTNER_TEAM_NAME` /
  `SPONSOR_TEAM_NAME`). CRM prereqs for full activation (each domain): the
  team's role reads the profile entity at **team** scope, existing records
  backfilled with the team, and the intake API role granted **Team read**
  (until then the stamp is skipped with a WARNING — never blocks the
  application).
- **All three managers are `CMentorProfile` records** — the one whose
  `assignedUser` is their login. `service.resolve_manager_profile` scans the
  `CMentorProfile` rows readable by this user and **matches `assignedUser` in
  Python — never a `where` on `assignedUserId`** (prod's field ACL forbids it; see
  [[crm-test-assignment-acl-fields]]). Then it reads the owned parents through the
  domain's reverse link (`list_related` on the profile), so a regular user whose
  ACL scopes `CMentorProfile`/the parents to "own" simply gets their own rows.
  `list_records` returns `{"records":[...], "profileFound": bool}` —
  `profileFound=false` means the user has no linked profile.
- **Partner grid: Partner Manager column (v0.89.0).** The partner list's
  far-right column links the assigned `partnerManager` to the standard
  CMentorProfile pop-up (CBM + personal email rows are compose links → the
  quick-compose), mirroring the mentor grid's Assigned Mentor column; both
  now ride `DomainConfig.list_manager_id_attr`. The Overview's record-level
  notes panel (Partner/Engagement/Sponsor Notes) **always renders at the top
  of the notes pane** — an empty field shows a muted "No … recorded yet."
  placeholder (blank wysiwyg markup counts as empty). **Partner notes edit
  path (v0.91.0):** `CPartnerProfile.partnerNotes` is the ONE partner-notes
  field — the partner-domain Company form's Account-level `cPartnerNotes`
  twin is retired (edits there never reached the Overview), the Partnership
  strip edit is a curated `noExtras` layout ending in a full-width Partner
  notes editor, `CPartnerProfile.description` + the partner Company form's
  `description`/`cClientNotes` are hidden, and **every Details save
  refreshes the Overview/Sessions tabs** (`refreshRecordViews`). **Sponsor
  parity (v0.93.0):** same pass — curated `CSponsorProfile` form whose
  full-width "Sponsor notes" box IS `description` (the domain's Overview
  notes field — kept editable, NOT excluded); sponsor Company form/view
  hides `description`/`cClientNotes`/the `cSponsorNotes` Account twin.
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
- **Co-mentor visibility (v0.51.0, 2026-07-15).** A co-mentor added via the
  Details tab (CBM Contacts + Add → `CEngagement.additionalMentors`) must see
  the engagement in their OWN `/mentorsessions` list. Two mechanisms, both in
  the app: (1) `list_records` reads the co-mentor reverse link **`engagements`**
  (reverse of `additionalMentors`; `DomainConfig.manager_comentor_link`, mentor
  domain only) in addition to `engagements1`, merged + deduped by id;
  (2) `service.add_comentor` appends the co-mentor's linked login User to the
  engagement's **`assignedUsers`** — required because the Mentor Role reads
  `CEngagement` at "own", which (assignedUser disabled) means assignedUsers
  membership; without the stamp the reverse-link read is ACL-filtered to
  nothing. Mentor Role `assignmentPermission=team` (read live 2026-07-15)
  permits assigning fellow Mentor Team members; `assignedUsers` maxCount is 10.
  Best-effort: profile without a linked User, or a rejected write, keeps the
  relate and returns `{"warning": ...}` which the Details tab shows.
  **Client-record stamping (v0.74.0, Doug's defect report):** `add_comentor`
  also merges the co-mentor's User into `assignedUsersIds` on the engagement's
  client records — every related contact, the CClientProfile, and the Account
  (`clientOrganization`, falling back to the profile's `linkedCompany`) — via
  `_stamp_client_records`; `remove_comentor` un-stamps symmetrically (unless
  the User is shared with the assigned mentor / a remaining co-mentor). Only
  the multi-user collaborators field is written; the single `assignedUser` is
  never touched. CRM prerequisite: "Multiple Assigned Users" enabled on the
  entity — Contact lacked it on prod until Doug enabled it 2026-07-16 (check
  crm-test parity). Both paths post a stream note on the engagement
  (`core/stream.post_stream_note`) recording what was granted/revoked — and,
  since v0.76.1, **naming the acting user in the note text** ("… via the
  session tools by Jane Staff"; the routers pass `actor=user["name"]`) so
  the history reads "who did this" even outside the stream UI, where the
  Note's author isn't shown.
  `remove_comentor` removes the User again unless the assigned mentor or a
  remaining co-mentor shares it. `assignments.assign_engagement` merges current
  co-mentors' Users into its assignedUsers write so a reassignment doesn't
  revoke them — since v0.76.1 on the client profile/Account writes too (they
  previously overwrote, see the Assign-action bullet). **Sessions (v0.52.0, Doug's ruling: a co-mentor sees ALL
  sessions):** `create_session` stamps the engagement's whole mentor team
  (creator + assigned mentor + co-mentors, `_engagement_mentor_user_ids`)
  into the new session's `assignedUsers`; `add_comentor` backfills the new
  co-mentor onto existing sessions (per-session best-effort — edit=own means
  the acting mentor can only stamp sessions they own, others logged +
  skipped); `remove_comentor` un-stamps except sessions the removed
  co-mentor personally owns (their `assignedUser`).
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
- **First completed session activates the engagement (v0.61.0, 2026-07-16 —
  Doug's rule).** Saving a session with status **Completed** (create, or an
  edit that CHANGES status to Completed) on an engagement whose
  `engagementStatus` is **Assigned** or **Assignment Dormant** moves the
  engagement to **Active**
  (`sessions/service._activate_engagement_on_completed`, called from
  `create_session`/`update_session`; mentor domain only — partner/sponsor
  parents have no engagement lifecycle). The status guard IS the
  "first-session" rule: once Active — or any staffer-set status (On-Hold,
  Dormant, Completed, …) — later saves are no-ops. On update it triggers only
  when `status` is in the diffed payload, so a notes-only edit to an
  already-completed session can't re-activate a parked engagement.
  Best-effort (calendar-hook precedent): a CRM failure never fails the
  session save; the response carries `engagement:{activated,from,to|error}`
  and the save notice tells the user ("The engagement status is now
  Active."). The post-save detail re-fetch refreshes the badge/grid. NOT yet
  driven live (the mentor's engagement edit should pass — mentors are in the
  engagement's `assignedUsers`).
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
  Communications bullet below for the wiring contract); **Documents** is built
  (v0.65.0, DOC-MGMT Phase 1 — see the Documents bullet below; a "coming soon"
  panel until `GDRIVE_DOCS` is on). The tab bar is built by the frontend from
  config (placeholder tabs get a generic panel); the standalone Contacts tab
  folded into Overview / Details. **The Sessions grid and the Communications
  conversation list are sortable + column-resizable (v0.72.0 / v0.75.1)** —
  header click sorts, drag grips resize (`makeColumnsResizable`); the
  Sessions grid carries a Participants (attendee-names) column, widest by
  default.
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
  - **Details EDIT forms — mockup-v4 packed group panels (v0.57.0–0.59.2,
    2026-07-15/16; design target `prompts/company-edit-form-mockup-v4.html`,
    prompt doc `prompts/section-edit-screens-prompt-v0.2.md` at rev 0.3).**
    Every edit form (`.sxf`, shared by Company / Client Business Profile /
    Engagement strip / contact rows / create-contact) renders its groups as
    **packable panels**: each group has `grow`/`basis` in `DETAILS_LAYOUTS`,
    panels flow left-to-right and **every band always fills the window
    width** (no width cap — prompt v0.2's 960px rule was REVERSED by Doug,
    see [[no-page-width-caps-density-by-packing]]; the prompt doc's v0.3
    records it). Each layout row is one flex line (no orphan fields);
    long-text cells cap at 72rem; every single-line control is pinned to
    2.4rem with a 12×16px gap rhythm (v0.59.2). **Field triage complete for
    all three entities** (live-metadata sweep, `noExtras` — the "Additional
    details" dump is gone; unplaced schema fields need an explicit placement
    decision): Account per prompt v0.2 (SIC/LinkedIn/notes placed; pledge
    currency, target population, applicant timestamp, contactRole removed);
    CClientProfile (state of formation, industry sector, employees, fiscal
    year end, social media, local licenses placed; record name + revenue
    Currency/Converted removed); CEngagement (hold/close + outcomes +
    focus/notes placed; record name, engagementAssignedDate, and the
    CRM-maintained session stats excluded from EDIT — the summary strip
    still displays them). Removed lists: `DETAILS_REMOVED_FIELDS` (per
    entity, consumed by the view cards too). Save UX: a **gold dot** marks
    each changed field (driven by the save's own snapshot diff) and a
    **sticky Save bar** narrates "N fields changed" (Save disabled when
    clean). All harness-verified; live save exercised earlier (v0.55.1).
  - **Grid + Overview session flags (v0.62.0–0.64.1, 2026-07-16).** The
    Overview feed's **Upcoming/Past sections always render** when sessions
    exist (empty group ⇒ muted note; the old both-groups-and-3+ heuristic
    hid them — the Randa Jackson report); upcoming cards are clearly blue
    (navy left accent) vs neutral past; a session **scheduled TODAY**
    (viewer-local) gets a red bold-white header band (card + session view)
    and files under Upcoming. The engagements grid: `list_records` attaches
    `upcomingSessions` (ONE ACL-scoped CSession query, dateStart ≥ now−36h,
    soonest first, best-effort) — the **Next Session column derives from it**
    (the stored `CEngagement.nextSessionDateTime` is NEVER populated by the
    CRM — do not read it), a today-session record's name renders red+bold,
    and the far-right **Assigned Mentor column** links to the CMentorProfile
    peek (CBM email → compose/mailto) so co-mentors can reach the primary
    mentor in two clicks.
  - **Grid accept action + mentor personal email (v0.78.0, 2026-07-17).**
    (1) A **Pending Acceptance** engagement's Status cell renders as an amber
    two-step accept pill → `POST /records/{id}/accept` moves it to
    **Assigned** (`DomainConfig.list_status_accept`, mentor domain only —
    the endpoint isn't registered elsewhere; `service.accept_engagement`).
    The server re-reads the status first — a stale row ⇒ readable 400,
    nothing written, the frontend reloads the grid (the v0.72.1 guard
    shape); a best-effort stream note names the acting user (v0.74.0
    convention); written as the signed-in user (mentors are in the
    engagement's assignedUsers, same edit path as the v0.61.0 activation).
    (2) Every **CMentorProfile peek** adds the linked Contact's email as a
    **"Personal email"** compose link right after CBM email
    (`service._mentor_personal_email`, best-effort — no linked Contact or a
    forbidden Contact read just omits the row). NOT yet driven live.
  - **Peek** (`service.peek`, `PEEK_FIELDS` allowlist: Contact/Account/CClientProfile/
    CPartnerProfile/CSponsorProfile/CMentorProfile): a read-only pop-up; the
    aggregated Company link fetches each member and renders titled sections;
    email-typed fields render as compose/mailto links (the mentor peek also
    carries the Personal-email row — the v0.78.0 bullet above).
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
    sample-data scaffold remains when off). **Compose body = the standard
    CBMRichText editor since v0.60.0** (message sent as HTML; `send_message`
    is HTML-native and `build_mime` adds the plain-text alternative — a
    fallback textarea's plain text upconverts server-side). 25 new tests; full UI loop
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
- **Email templates in every compose (ET, v0.67.0, 2026-07-16 — gated by the
  same `GMAIL_SYNC` as compose itself).** PRD:
  `prompts/email templates/email templates prompt/` (crmbuilder-framed;
  adapted into THIS app per Doug's rulings — target = Communications tab +
  every compose surface, write-back BOTH ways, user attachments in v1,
  templates on quick-compose too). **EspoCRM renders, the app sends**
  (ET-D1): `comms/templates.py` (module docstring = the verified integration
  contract) wraps `POST EmailTemplate/{id}/prepare` (EspoCRM 9.x —
  **verified live on crm-test 9.3.6**; `parentType/parentId` feeds
  `{Parent.*}`, `emailAddress` alone resolves `{Person.*}`, attachments come
  back as fresh per-parse clones; unresolved placeholders stay LITERAL
  `{X.y}` tokens → the UI warns, never blocks). Endpoints: sessions routers
  `GET /emailtemplates` (context-aware) +
  `POST /records/{id}/emailtemplates/{tid}/parse`; the quicksend surface
  (assignments/mentoradmin + sessions grid pages) gets record-less
  list/parse + the shared `POST /emailwriteback` retry. Both dialogs:
  type-ahead picker, "Replace current content?" over a non-empty draft
  (ET-113), parse failure leaves the draft untouched (ET-114), removable
  template-attachment chips + local file uploads (20 MB cap), send blocks if
  a template attachment can't be downloaded at send time (ET-131,
  `comms/service.resolve_attachments`; `build_mime` now takes attachments).
  **Write-back:** every app send ALSO creates a native EspoCRM **Email**
  record as the acting user (status Sent, parented to the first recipient
  matching a record contact → Contact History panel; quick-compose looks the
  address up); failure → the dialog swaps to a Retry screen (ET-142), never
  silent. Quickmail's body is now CBMRichText (assignments pages load Jodit;
  textarea = script-load fallback). **Context filter rides the NATIVE
  template category** (a category named Engagement/Partner/Sponsor scopes a
  template to that domain's picker; no/other category = shows everywhere) —
  `EmailTemplate` is `customizable:false`, NOT in Entity Manager, so a custom
  field is impossible through the UI (the original cAppliesTo plan; corrected
  same day on Doug's report). **CRM prereqs:
  `emailtemplate-et-crm-prereqs.md`** — Partner/Sponsor Manager roles need
  EmailTemplate read + Email create (Mentor Role/Standard User already
  carry them, read live 2026-07-16); category filtering needs no build. Verified in the stub harness (both
  dialogs, full flows incl. both failure paths); 23 new tests; **NOT yet
  driven against the live CRM/Gmail.** (Grants DONE on crm-test 2026-07-17
  per Doug.)
- **`{CMentorProfile.*}` template placeholders resolve (v0.76.2,
  2026-07-17 — Doug's first live template hit this).** EspoCRM's parse only
  substitutes entities in its render context (User=sender,
  Person/Contact=recipient, Parent + its own type=the record) — any other
  type stays a literal token. The prepare API takes ONE extra record
  (`relatedType`/`relatedId` → added under its own type), so the parse
  endpoints now pass the **record's manager profile** automatically
  (`comms/templates.related_manager_profile`: the parent's
  `parent_manager_link` FK — now set on all three domains
  (mentorProfile/partnerManager/cBMSponsorManager) — falling back to the
  sender's own linked profile; quick-compose always uses the sender's).
  Best-effort: no resolvable profile = token stays + the leftover warning.
  Placeholder cheat sheet for template authors in communications-tab.md.
  (Side effect of setting partner/sponsor `parent_manager_link`: those
  domains' CBM-contacts list can now also surface the record's manager —
  correct UX, inert unless the detail select carries the FK.) Mechanism
  read from EspoCRM 9.3.6 source (`Processor.prepare`:
  `entityHash[related->getEntityType()] = related`); NOT yet re-verified
  live (admin creds became EV[…]-encrypted when the crm-test overlay was
  regenerated 2026-07-16 — Doug's next template pick in the UI is the
  live check). Note: EspoCRM 9.2+ also supports a metadata
  `app.emailTemplate.entityLinkMapping` for auto-loading linked entities —
  not needed with the app-side fix.
- **Email signatures in every compose (v0.75.0, 2026-07-17).** The user's
  **EspoCRM `Preferences.signature`** (readable/writable with their own
  token — no grant work) seeds into the bottom of every new compose body,
  record compose AND quick-compose; it arrives on the existing
  `GET /mailbox` response (`signature`, sanitized via the template pass;
  `comms/service.user_signature`, best-effort ""). Template application
  re-appends the signature below the rendered draft (so templates must not
  carry sign-offs — noted in communications-tab.md); a body still equal to
  the untouched seed counts as EMPTY (no ET-113 replace-prompt right after
  open; the quick-compose "write a message" guard still fires; tracked as
  `sigSeed` in both frontends). **Editing: /mentorprofile "Email signature"
  panel** (CBMRichText, own Save button, inserted above the
  Internal-CRM-description group — outside the PROFILE_FIELDS whitelist
  diff) → `GET/PUT /mentorprofile/api/signature` (PUT sanitizes, writes
  `Preferences/{ownUserId}`); non-mentor staff use EspoCRM → Preferences →
  Email Signature (same field). Gmail never appends its own signature to
  API-sent raw MIME — that's the gap this closes. Harness-verified on all
  three surfaces; NOT yet driven live.
- **Documents — PRD v1.2 alignment (v0.68.0, 2026-07-16).** Doug's updated
  PRD (v1.1/1.2: D-07 + the §3.2 folder-tree rewrite) + his rulings this
  session (mentor documents live in **Mentor Administration**; partner/
  sponsor tabs stay, under their own labels) reshaped the v0.65.0 build:
  (1) **top-level Drive folders are configurable display labels**
  (`GDRIVE_ENTITY_LABELS`: Contact=Mentors, CEngagement=Clients,
  CPartnerProfile=Partners, CSponsorProfile=Sponsors; unmapped → raw name;
  `docs/service.folder_label`); (2) **engagement folders nest under their
  client** — `Clients/{Client Name} (clientId)/{Engagement Name} (engId)/` —
  the parent client resolved AT UPLOAD TIME from the engagement's
  `clientOrganization` link with the client-profile `linkedCompany` fallback
  (`sessions.service.fill_company_fallback`, the same path the grid/Overview
  use); an unresolvable client nests directly under `Clients/` (browsing
  nicety, never a blocked upload); (3) **`client_record_id`** on
  `app_document` (Alembic **`0006_app_document_client`**, nullable+indexed,
  D-07 cross-engagement reporting; API `clientRecordId`); (4) **`/mentoradmin`
  detail gains a Documents tab** (shown when `GDRIVE_DOCS` on — `/session`
  reports `docsEnabled`): list + upload anchored to the mentor's **linked
  Contact** (`Mentors/{Name} (contactId)/`; no linked Contact ⇒ readable 400
  before any write; endpoints `GET/POST /mentoradmin/api/mentors/{id}/
  documents`, same raw-bytes contract/gates/rollback as the session tools;
  frontend: a non-field "Documents" tab appended in `renderForm`, panel key
  `__documents`, no `data-field` inputs so Save-diffing is untouched).
  Verified: 75 documents tests; migration + `client_record_id` round-trip on
  live local Postgres; both UIs in the stub harness. Uploader-identity note:
  mentoradmin staff need their own linked profile `cbmEmail` (the DWD
  impersonation subject) — a staffer without one gets the readable "no CBM
  email" 400.
- **Documents tab — Google Drive document management (BUILT v0.65.0,
  2026-07-16; gated OFF by `GDRIVE_DOCS` until activated).** DOC-MGMT
  **Phase 1** of Doug's PRD (`prompts/Google Drive Documents/
  CBM-DocMgmt-Implementation-PRD.docx` v1.0 + `prompt-docmgmt-phase1.md`),
  **adapted from the PRD's desktop framing per Doug's rulings this session**:
  built in THIS web app (not crmbuilder), and Drive auth = the existing
  **service-account + DWD stack impersonating the signed-in manager's own
  `cbmEmail`** (`docs/service.drive_for_user`, subject NEVER from request
  input — preserves D-01's audit-trail rationale) instead of desktop
  keyring/loopback OAuth. Pieces: `core/gdrive.py` (`DriveClient`, gcalendar
  pattern — find/create folders, multipart upload ≤5 MB / **resumable
  session >5 MB** (DOC-01), delete-for-rollback, backoff retries on
  rate-limit/5xx per NFR-02, all `supportsAllDrives`); `docs/store.py` (the
  **`app_document`** metadata table, PRD §4, Alembic **`0005_app_document`**,
  + `MemoryDocumentStore` for tests); `docs/service.py` (folder scheme
  `/{Entity Type}/{Record Name} ({recordId})/` under the shared drive with
  folder-id caching off the rows; upload validation — size cap
  `GDRIVE_MAX_FILE_MB`, doc types `GDRIVE_DOC_TYPES`; the **rollback rule**:
  row-write failure ⇒ Drive file deleted, Drive failure ⇒ no row ever
  written). Endpoints on all three session routers (comms `_docs_ready`
  pattern, 503 when off/no DB): `GET/POST /{slug}/api/records/{id}/documents`
  — the POST is **raw bytes** (filename/docType as query params, MIME from
  Content-Type; NOT the base64-JSON photo pattern — documents are much
  bigger), and the parent record is first read AS THE USER (ACL check + the
  folder's record name). Frontend: static Documents panel — upload picker +
  doc-type select, list newest-first (filename/type chip/uploader/date) from
  metadata only (DOC-02). **Phase 2 — viewing — is BUILT (v0.70.0,
  2026-07-16; Doug's two web-adaptation rulings: in-app overlay viewer +
  the BROWSER as the cache):** View streams the file through
  `GET …/documents/{id}/content` (parent read AS THE USER = the ACL gate;
  Drive fetch under the signed-in user's delegated identity) into a
  workspace-sized overlay — PDF/text in an iframe (browser-native PDF
  viewer), images inline, Google Docs/Sheets/Slides via `files.export` to
  PDF (DOC-04, `DriveClient.export_pdf`; over-cap exports surface a
  readable 502 + Open in Drive), unrenderable formats (docx/xlsx) get a
  clear message + Open in Drive button. **Cache (DOC-06): NO server
  cache** — the response is `private, max-age=31536000, immutable` and the
  URL carries `?v=<modifiedTime>`, so each browser holds the bytes and a
  Drive edit invalidates by changing the URL. **Lazy refresh (DOC-02
  completion):** the tab renders from metadata, then
  `POST …/documents/refresh` (ONE `files.list` scoped to the record folder,
  `DriveClient.list_folder_files`) re-syncs modifiedTime/checksum/view-link
  (`DocumentStore.update_file_state`) and flags changed rows with an amber
  "Updated in Drive" tag; best-effort, never blocks the render. Same
  endpoints on `/mentoradmin` (`/mentors/{id}/documents/{docId}/content` +
  `…/refresh`, Contact anchor). `DocumentStore.get_document` is
  record-scoped — a doc id never resolves through another record's route.
  **Archive + CRM write-back stay disabled Phase 3 placeholders** (do not
  build ahead). 57 documents tests; store verified against a real
  local Postgres (Phase 1: migration + insert/list/unique/folder-cache);
  both UIs' full loops verified in the stub harness (Phase 2 viewing NOT
  yet driven against the real shared drive — checklist in
  `GDRIVE-DOCS-SETUP.md` Task 5 item 6). **Activation prerequisites (NOT done —
  step-by-step guide: `GDRIVE-DOCS-SETUP.md`):** (1) enable the Drive API on
  GCP project `espcrm-498315`; (2) Doug creates the "CBM Documents" **shared
  drive** + memberships (Content Manager for every manager — uploads act AS
  the manager, so it's THEIR access, the SA needs no membership); (3) add
  `https://www.googleapis.com/auth/drive` to the SA's DWD row (edit the
  existing four-scope line — the field REPLACES, don't drop the Gmail/
  Calendar scopes); (4) set `GDRIVE_DOCS=true` +
  `GDRIVE_SHARED_DRIVE_ID=<drive id>` on the **web** component (worker not
  involved) and run the pre-deploy migrate; (5) live smoke test — one upload
  as a real mentor → folder auto-creation + metadata row + rollback path.
  Runbook block in DEPLOYMENT.md.
- **Documents — CRM integration and lifecycle (BUILT v0.76.0, 2026-07-17;
  DOC-MGMT Phase 3, PRD v1.3 — closes the PRD's phased plan).** Doug's
  session rulings: archive = **Drive move FIRST, metadata flip after,
  move-back rollback on a mid-failure** (never inconsistent); DOC-08 =
  **self-healing best-effort, no retry queue** (idempotent check on every
  upload + the nightly job); scope = core only (OI-02 link-existing stays a
  fast follow, OI-07 copyRequiresWriterPermission stays off). Pieces:
  (1) **Drive access grants (DOC-09)** — `docs/grants.py`: per-person
  folder-level **Commenter** grants mirroring CRM entitlements
  (CEngagement → assigned mentor + co-mentors via `cbmEmail`;
  CPartnerProfile/CSponsorProfile → their manager; **Contact folders → NO
  ONE**, and the engine strips strays), issued/revoked best-effort
  (`sync_record_grants_safe`) by `assign_engagement`, co-mentor add/remove,
  and every upload (`docs.service.post_upload_hooks`), notification emails
  suppressed; wrong-role grants are downgraded to Commenter; active ONLY
  under `GDRIVE_IDENTITY=service` + real CRM creds (`grants_enabled`).
  (2) **Nightly reconciliation** — `docs/reconcile.py`, run by the worker
  (`GDRIVE_RECONCILE_SECONDS`, default 86400, monitoring-check pattern;
  **the worker now needs the GDRIVE_* envs**): re-derives every folder's
  entitled set from the CRM via the API-key client
  (`store.list_folder_records`), corrects both drift directions, logs
  corrections, ALERTS on removals (`core.monitoring.send_alert`), and
  re-checks the DOC-08 link. Covers manager changes/offboarding done
  directly in the CRM (no in-app action exists for those).
  (3) **Archive/restore (DOC-07)** — `docs.service.archive_document`/
  `restore_document` (`_lifecycle_move`): file moves to the record folder's
  `/_Archived` subfolder (created on demand; source = the file's ACTUAL
  parents, so a human re-file doesn't break it), then `store.set_status`;
  endpoints `POST …/documents/{id}/archive|/restore` +
  `?includeArchived=` on list/refresh (sessions ×3 + `/mentoradmin`); UI:
  two-step-confirm Archive/Restore buttons, "Include archived" toggle,
  dimmed rows with an Archived tag. Viewing/Download of archived rows
  still works (fetch is status-agnostic).
  (4) **CRM link write-back (DOC-08)** — `docs.service.write_back_folder_link`:
  on every upload + nightly, sets `documentsFolderUrl` (CEngagement +
  Contact only, PRD §3.5) to the record FOLDER's webViewLink (via
  `DriveClient.get_file`), written as the API user; **feature-detected
  from metadata** (10-min cache) so it's inert until the CRM team builds
  the field — spec handoff: **`documentsfolderurl-crm-field.md`** (repo
  root, csession-calendar-field.md style). New DriveClient surface:
  `get_file`/`move_file`/`list_permissions`/`create_permission`/
  `delete_permission` (inherited permissions never touched). 649 tests
  green (43 new); both UIs verified in the stub harness. **NOT yet driven
  live** — activation order (SA sole Content Manager membership + human
  removal BEFORE `GDRIVE_IDENTITY=service` on web+worker; then the grants
  verification) is `GDRIVE-DOCS-SETUP.md` Task 6; verified live items to
  check are listed there.
- **Google Calendar events + Meet links (v0.40.0, 2026-07-13 — LIVE on BOTH
  envs: crm-test activated + verified 2026-07-13, prod 2026-07-15; create
  path verified live by Doug on each).** Saving a **Scheduled** session
  (create or edit, any domain) reconciles a Google Calendar event on the
  signed-in manager's OWN calendar: `core/gcalendar.py` (delegated Calendar
  REST client — same service-account + DWD stack as Gmail, impersonating the
  manager's `cbmEmail` via `sessions.service.resolve_user_mailbox`) +
  `sessions/gcal.py` (`sync_session_calendar`, called from
  `create_session`/`update_session` when the router passes `settings`).
  Decision matrix: Scheduled + no stored event → **create** (with a Meet
  conference when `videoMeetingLink` is blank — the URL is written back to
  `videoMeetingLink` + the event id to the **feature-detected CRM field
  `CSession.googleCalendarEventId`** (`csession-calendar-field.md`; built on
  crm-test 2026-07-13 and prod 2026-07-15); a hand-typed link means no
  Meet, link carried in the event location); Scheduled + event + a
  time/title/status/attendee change → **patch** (notes-only edits never
  touch the calendar); status → Cancelled → **cancel** (clears the event id
  + a generated Meet link, never a hand-typed one); Completed/No Show →
  skipped (Doug: only Scheduled sessions get events). Attendee contacts are
  invited (`sendUpdates=all` — Google emails invitations; organizer
  excluded, blanks skipped). **CBM members are invited at their `cbmEmail`
  ONLY (v0.122.0, Doug's ruling 2026-07-20 — see the Current-status block):**
  `service.cbm_member_email_map` classifies the record's members (assigned
  manager + co-mentors, contact id → cbmEmail) and `gcal._attendee_emails`
  substitutes it for the Contact's personal address on create AND re-patch;
  the acting organizer's own contact then matches the organizer mailbox and
  drops out (no self-invitation), and a member with no cbmEmail is skipped,
  never invited personally. **Best-effort** (mentoradmin-provision
  precedent): never raises; the save response carries `calendar:{ok,…}`
  and `saveSession` shows it as a notice. **Pre-save prompt (v0.56.0):**
  saving a NEW Scheduled session (start time set, `gcalEnabled` from
  `/session` config) first pops a confirm — Create & send invite / Save
  without invite / Keep editing — so the user can opt out and schedule the
  meeting manually; the decline reaches the server as `skipCalendar:true`
  on the create POST (`create_session(skip_calendar=True)` skips the hook,
  `calendar:{ok,skipped,declined}`). Edits never prompt. Verified in the
  stub harness; **DEPLOYED 2026-07-15** (prod + crm-test serve the modal +
  skipCalendar code, checked via curl at 0.57.0) — the live Google paths
  (invite actually created vs. actually skipped) still worth one eyeball. **Activation (ALL DONE):** Calendar
  API on in GCP; `calendar.events` on the SA's DWD grant; the CRM field built
  on both CRMs; `GCAL_EVENTS=true` on the **web** component of both overlays
  (worker not involved); EspoCRM-side calendar sync confirmed a non-issue
  (only per-user personal connections ever existed — deleted). **Still to
  drive live:** edit→patch, Cancel→cancel-event, attendee-invitation
  delivery.
- **Phase 1 (CRUD + review UI).** The **Start/Open Session** button uses
  `videoMeetingLink` when set. Google Calendar/Meet *scheduling* shipped
  v0.40.0 (the bullet above; gated). Meet *transcription* is BUILT (v0.83.0,
  gated by `MEET_TRANSCRIPTS` — see the Current-status v0.83.0 block; plan
  `prds/meet-transcript-integration.md`, CRM handoff
  `csession-transcript-fields.md`). **The UI side of the transcript is now ready
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

## Current status (updated 2026-07-22)

**Main is at v0.132.0** (2026-07-22, 982 tests green, committed NOT pushed) —
**Email Quality Phase 1 ("never lose information") is BUILT** — §3 of
`prds/email-quality-improvement-plan.md`, all four pieces (CHANGELOG
0.132.0 has the full mechanics):
1. **Inbound attachments auto-file to the record Documents tab.**
   `parse_message` collects attachment parts (`GmailAttachment`);
   `GmailClient.get_attachment` fetches bytes (gmail.readonly — no new
   scope). REAL attachments only (Content-Disposition: attachment; inline/
   cid images never file — ruling), INBOUND only; filed onto every record
   the conversation links to via `comms/attachments.py` → the docs
   pipeline, service identity, docType "Email attachment", uploaded_by =
   the source mailbox. **Per-record SHA-256 dedup**
   (`app_document.content_sha256` — now computed for ALL uploads) + the
   **`comm_attachment` ledger** (Alembic **0014** — pre-deploy migrate;
   chip render source AND retry ledger: failed rows re-attempt each sync
   pass, 25/pass, give-up WARN at 10 attempts; over-cap = `too_large`, no
   fetch). Gates: GMAIL_SYNC + GDRIVE_DOCS + DATABASE_URL + shared-drive id
   + GDRIVE_IDENTITY=service (all live on both envs already). Thread-view
   chips link filed/duplicate files to the record's document; too_large/
   failed chips point at View original. Historical backfill:
   `scripts/backfill_email_attachments.py` (dry-run default; run per env
   AFTER live verification).
2. **View original in-app** — `GET /{slug}/api/communications/{id}/original`
   (+ `/original/cid/{cid}` for inline images): CCommunication read AS THE
   USER (the thread-read ACL gate), full original fetched from the SOURCE
   mailbox under the service delegation (any record-entitled viewer sees
   it), `sanitize_original_html` (scripts/handlers stripped, formatting
   kept, cid → companion endpoint), rendered in a sandboxed iframe with
   Back; provenance-logged per access; deleted-in-Gmail → readable 404.
   Cleaner placeholder now says "use View original".
3. **Open in Gmail fixed** — viewer's own mailbox +
   `#search/rfc822msgid:<rfc id>` (ids are mailbox-specific; the old
   sourceMailbox link only worked for that mailbox's owner). Tooltip
   points at View original when the message isn't in the viewer's mailbox.
4. **Bounce visibility on record threads** (closes F14) — classified at
   render/enrichment time from stored fields: red "Delivery failed" card in
   the thread (Reply no longer targets mailer-daemon), `bounced` state from
   `enrich_conversation_rows` → red "✕ delivery failed" chip on the
   Communications list AND My Email rows (replaces awaiting-reply).
Verified: 982 tests (24 new); migration 0014 + ledger/dedup round-tripped
on live local Postgres; both frontends driven in the stub harness (chips,
bounce cards/chips, View original + Back, new Gmail href, ?parentId
scoping; no console errors). **NOT yet driven live** — next: deploy (the
PRE_DEPLOY migrate runs 0014), then the plan §3.5 live pass (PDF +
signature-logo email → files once / logo doesn't / duplicate dedups; View
original as mentor AND co-mentor; viewer-mailbox Gmail link; a real
bounce), then the attachment backfill dry-run → --write per env. Still
pending ops from v0.125.0: `scripts/repair_outbound_bodies.py` per env.
Phases 2–3 of the plan not started.

Before that, the **Email Quality Improvement arc was PLANNED 2026-07-21** —
`prds/email-quality-improvement-plan.md`, authored from Doug's priority
rulings after a full email-system gap review (app vs Gmail). Phase 2
server-side Forward-with-attachments (SME use case) + unread awareness on
all four surfaces (grid unread + awaiting-reply chips, portal badge, daily
digest from the shared identity); Phase 3 info@ poller pagination + a
surface for staff-notice replies. B (push), C (gmail.modify state sync),
E (full-text search) explicitly deferred — rulings + rationale in the plan.

**Main is at v0.131.0** (2026-07-21, 967 tests green, committed NOT pushed; shared-identity display name renamed to "Cleveland Business Mentors" in 0.131.0 — prod CRM Outbound From Name still says "Mentoring", Doug to fix) —
**the info@cbmentors.org shared-mailbox rollout: Phases 1–3 of
`prds/info-mailbox-rollout-plan.md` are LIVE/BUILT** (Doug's rulings: all
staff-tool outbound as info@; mentor↔client stays personal; no auto-acks;
alerts keep admin@; Marketing Admin Team owns the queue + info@ inbox).
- **Phase 1 VERIFIED LIVE ON PROD** (Doug: "all inbound and outbound
  replies work"): `OPS_MAILBOX=info@cbmentors.org` on the PROD overlay
  (web+worker; crm-test verified first, then removed — ONE poller only,
  double-capture otherwise). The v0.110.0 machinery all proved out live:
  inbound capture → held rows → Approve → reply as "CBM Info" →
  thread-following reply, no double-capture.
- **The CheckFromAddress gotcha (cost the verification an hour):**
  EspoCRM 403s a non-admin creating an Email record (the send write-back)
  whose `from` isn't their own address — "The message WAS sent, but
  recording it in the CRM failed". Fix is CRM-side, BOTH done on both
  CRMs: system outbound From Address = info@ (shared) AND an Active
  **Group Email Account** for info@ with Use SMTP (getSystem() requires
  the record, not just the setting; smtp.gmail.com/587/login + app
  password). This also moved EspoCRM's own outbound off espo@ (= Phase
  3's core; the old espo@ group account is still Active — deactivate once
  info@ SMTP creds are proven). Diagnosed via the CRM server log — and
  **v0.128.0** now surfaces EspoCRM's `X-Status-Reason` header in every
  EspoError, so such denials name themselves in our own logs.
- **Phase 2 BUILT (v0.129.0):** assignments + mentoradmin quick-compose
  send as the shared identity — `comms.quicksend.shared_staff_mailbox`
  (reads OPS_MAILBOX) passed to `register_quicksend` on both routers
  (/ops imports the same helper); session tools deliberately per-user
  (regression-tested). Compose From line shows "CBM Info (info@…)".
  Live check after deploy: an Assign notice compose + arrival as CBM
  Info. Replies to such notices land in the info@ Gmail INBOX (not /ops,
  not the personal sync) — Marketing Admin watches it.
- **Phase 4 bounce visibility BUILT (v0.130.0):** `core.gmail.
  looks_like_bounce` (mailer-daemon/postmaster sender or DSN subject);
  /ops conversation renders bounces as a red "Delivery failed" card
  (bounces thread with the original send, so the anchored fetch already
  had them — they just read as ordinary replies), and the awaiting-reply
  column shows a red "✕ delivery failed" chip when the newest thread
  message is a bounce (was masquerading as "reply owed"). Closes the
  allen.ingram silent-bounce gap. Live check: reply to a bogus address
  from /ops → red chip + card within a refresh.
- Cleanup: Discard the two no-reply@accounts.google.com rows in the prod
  /ops queue (+ the leftover crm-test copies); crm-test queue is frozen
  (no poller).

Before that: **v0.127.0** (2026-07-21, 960 tests green, committed NOT pushed) —
**the Gmail sweep no longer ingests internal cbmentor↔cbmentor mail**
(Doug's ruling this session: the sync is for mentor↔client correspondence;
staff-to-staff email is useless in the CRM — reported as "a ton" of
internal messages in the repair-script output). Cause: mentors' own
Contact records with @cbmentors.org addresses are linked to engagements as
contacts, putting those addresses into the match scope — every mentor's
sweep then ingested ALL their internal mail with those people. Fix (new
`COMMS_INTERNAL_DOMAINS`, default `cbmentors.org`): internal-domain
addresses never enter the sweep's match scope (`build_scopes`), and
`ingest_message` skips any message whose every participant is internal —
incl. thread-following replies. Explicit actions (record compose
write-through, "Add emails" include) are exempt via their own scopes.
Already-stored internal conversations are NOT auto-removed (API user
can't delete) — EspoCRM UI cleanup if wanted; CHANGELOG 0.127.0. Also
recorded there: `tests/test_comms_sync.py` single-file collection fails
on a PRE-EXISTING latent circular import (full suite unaffected).
This session also shipped **v0.125.0** (the outbound truncation fix —
see its block below) and verified both envs deployed at 0.126.0;
`scripts/repair_outbound_bodies.py` is still to run per env (worker
console) to heal stored truncated sent bodies.

Before that: **v0.126.0** (2026-07-21, 957 tests green, committed NOT pushed) —
**the Fathom note-taker transcript arc is COMPLETE and VERIFIED LIVE on
crm-test** (one session, three releases: v0.124.0 build — ordered-source
seam, Fathom first / Meet fallback, action-items routing; v0.124.1 live
delivery of a real recording via `scripts/probe_fathom.py` + real-API
shape fixes; v0.126.0 invitee-overlap match preference for reused personal
meeting rooms). Full mechanics in the v0.124.0 Current-status block below,
CHANGELOG 0.124.0/0.124.1/0.126.0, and the plan
`prds/fathom-transcript-integration.md` (status header current).
**Remaining, all Doug-side:** the team-key vs per-mentor ruling (an
individual key sees only own + team-shared recordings), setting
`FATHOM_TRANSCRIPTS=true` + `FATHOM_API_KEY` on the crm-test WORKER
overlay, an in-UI eyeball of the AI SUMMARY zone on a parented session,
and deleting the ZZTEST CSession `6a5f011bce8e19a19` in the crm-test UI.

Before that: **v0.125.0** (2026-07-21, 952 tests green, committed NOT pushed) —
**fix: sent emails no longer look cut off in the Communications viewer**
(Doug's report, example Douglas Bower → mindy@mindybower.com 7/17). Root
cause: OUTBOUND messages were cleaned at ingest with the full INBOUND
signature-stripping heuristics — an early "Thanks,"/"Best," line or a
"Name / Title / email" person-introduction deleted every paragraph after
it, and even a normal sign-off + signature was removed (reproduced all
three modes locally). Fix: `clean_email(..., outbound=True)` — messages
our user wrote keep everything authored; ONLY quoted reply history is
still demoted (the new-text-only ruling holds for inbound, unchanged
byte-for-byte). Wired in `comms/sync.py` (covers app-send write-through +
the periodic sync of sent copies) and the /ops conversation view (cleans
per-request → self-heals on deploy). **Stored truncated rows do NOT
self-heal** (rfc-id dedup never re-stores): new
**`scripts/repair_outbound_bodies.py`** re-fetches each Outbound
CCommunication from Gmail and rewrites `bodyCleaned`/`snippet`
(dry-run default, `--write` applies; needs GOOGLE_SERVICE_ACCOUNT_JSON —
run inside the deployed worker via `doctl apps console`, per env).
CHANGELOG 0.125.0. **Doug-side after deploy:** run the repair dry-run on
each env, eyeball the report, then `--write`; re-open the mindy example
to confirm.

Before that: **v0.124.0** (2026-07-21, 944 tests green, committed NOT pushed) —
**Fathom note-taker transcript source: the retrieval pipeline supports
either note taker** (plan `prds/fathom-transcript-integration.md`, drafted +
built this session from Doug's rulings: one team API key; **Fathom first,
Meet-native fallback**; store transcript + AI summary + action items; poll).
New `core/fathom.py` (FathomClient — X-Api-Key, cursor paging, 429/5xx
backoff — + normalize_meeting_url (Meet/Zoom/Teams — the videoMeetingLink ↔
Fathom `meeting_url` correlation key), transcript/summary/action-items HTML
formatters matching the gmeet shape); `sessions/transcripts.py` seam is now
an **ordered source list** (`sources=`, order = precedence;
`FathomTranscriptSource`: ONE listing sweep per cycle indexed by normalized
URL, ±36h window + closest-start match, `needs_mailbox=False` — no DWD;
candidate query widens to any non-empty link only when a wide source is
active; per-source failures fall through to the next source).
**Action-items routing (Doug's 2026-07-21 amendment):** task list → the
EXISTING `nextSteps` when empty (blank markup counts empty,
`richtext_empty`), else appended to the NEW feature-detected
`CSession.sessionAiSummary` (wysiwyg; handoff `csession-ai-summary-field.md`,
NOT built — until it exists the summary/overflow are skipped with a log
line, transcript + nextSteps routing still work); human content never
overwritten. `transcriptDocUrl` now carries the Google Doc OR Fathom share
link (view row relabelled "Transcript / recording link"); session view
gains a read-only AI SUMMARY zone. Gated by `FATHOM_TRANSCRIPTS` +
`FATHOM_API_KEY` (SECRET) + `FATHOM_BASE_URL`, **worker only** (no
schedule-time Fathom hook — Fathom auto-joins from the mentor's calendar;
the Meet auto-enable is untouched); shares the existing poll/give-up
settings; the worker timer runs on either flag. 23 new tests. **NOT
activated — Phase 0 is Doug-side** (the load-bearing unknown: Fathom keys
are USER-level, reading only own + team-SHARED meetings — CBM team sharing
must cover mentors' recordings; plus tier/API check, service-account key,
the read-only listing probe), then the CRM field on crm-test + the flag on
the crm-test worker overlay + plan §Phase 3 live verification. CHANGELOG
0.124.0. (v0.123.2 = the parallel contribution-currency fix session.)
**v0.124.1 — VERIFIED LIVE on crm-test the same day** (946 tests green):
Doug's INDIVIDUAL Fathom API key (in .env; sees own + team-shared
recordings — fine for testing, the team-key/sharing decision stays open)
drove a real recording ("Doug-Racine Meeting", Zoom 2026-03-31) end-to-end
via the new **`scripts/probe_fathom.py`** (read-only listing/--match;
--deliver = explicit one-session write): 70k-char/300-turn transcript +
4 assigned action items → empty nextSteps + 11.5k-char linked summary →
sessionAiSummary (field BUILT + probe-verified on crm-test; prod per Doug)
+ share URL, all GET-verified. Live-probe contract fixes: summary key is
**`default_summary`** (docs' `summary` kept as fallback) and summary
markdown links now render as safe anchors. Cleanup: ZZTEST CSession
`6a5f011bce8e19a19` in crm-test (parentless — delete in the EspoCRM UI).
Next: team key or per-mentor ruling, worker overlay flag, in-UI eyeball
of the AI SUMMARY zone on a parented session.
**v0.126.0 — invitee-overlap match preference** (v0.125.0 = the parallel outbound-email-truncation fix session) (957 tests green): for
reused links (personal Zoom rooms — Doug's question), a window-matched
meeting whose Fathom `calendar_invitees` overlap the session's people
(attendee contacts' emails + assigned users' cbmEmails,
`_session_attendee_emails`) outranks a closer non-overlapping recording;
closest start remains tie-break + fallback; preference never blocks
(resolver failure / missing grant ⇒ plain time match). Also noted: Fathom
emits TWO next-step lists by design — the structured `action_items` (what
we route to nextSteps, has assignees) and the summary template's own
"Next Steps" prose section (stays inside sessionAiSummary); counts will
disagree, not a bug (Doug reviewed, kept as-is).

Before that: **v0.123.1** (2026-07-20, 912 tests green, committed NOT pushed;
v0.123.0 = the parallel action-history session — Conventions bullet +
CHANGELOG 0.123.0) — **calendar invites address CBM members at their
`cbmEmail` ONLY** (v0.122.0 + the v0.123.1 hardening; Doug's
ruling, from the live duplicate-event customer report on engagement
`6a54610ba4b6d1b24`: the mentor was invited to their OWN meeting at their
personal address — the default-invitee set resolves members to Contact
records and the hook used the Contact's primary email; accepting made a
second event copy, and deleting the organizer copy cancelled the client's
too). Fix: `sessions/service.cbm_member_email_map` (record's assigned
manager + co-mentors → contact id → cbmEmail) + substitution in
`gcal._attendee_emails` on create and re-patch — organizer self-invite
eliminated, co-mentors invited once at their CBM address, no-cbmEmail
members skipped (never personal). **v0.123.1 hardening: the ACTING user's
own profile is always classified too** (`acting_user_id` on the map), so
the self-invite can't recur through the side door of the organizer's
Contact being linked to the record as a plain client contact / the
organizer not being the record's manager (partner/sponsor domains).
**PROD AUDIT RUN 2026-07-20: 3 affected sessions total (2 upcoming).
VERIFIED LIVE ON PROD 2026-07-21:** Doug pushed (prod `/healthz` 0.123.1)
and re-saved the tonya hegler 7/22 session — run logs show the PATCH 200
as doug.bower@cbmentors.org with no member-map warnings, and the Google
event's guest list (read via Chrome) now holds ONLY the client
tonya@fuams.design — doug@dougbower.com removed; the hand-typed Zoom link
untouched. The remaining flagged session (Anthony Sacco's Krystal Drake
7/31 — the reported one, its Google event already hand-deleted) is
**handed to Anthony**: Doug emailed him instructions to cancel it in the
app and create a fresh session (re-saving would just patch a dead event).
Note: the audit script infers from CRM data, so it still lists repaired
sessions — proof lives in the Google guest list. Prod API key obtained
via `doctl apps console` printenv (overlay copy is EV-encrypted).** New read-only
`scripts/audit_calendar_invites.py` measures the retroactive blast radius
(crm-test: 1 upcoming session flagged — Douglas Bower invited at
doug@dougbower.com). **Retroactive decision open with Doug** (notify
mentors vs. re-save flagged sessions post-deploy to re-patch their events;
Doug to run the audit against prod for the count). CHANGELOG 0.122.0.

Before that: **v0.121.0** (2026-07-20, 900 tests green; v0.120.0 pushed +
DEPLOYED — **prod's first reconciliation pass ran clean 2026-07-21 01:17
UTC: 41 engagements audited, 0 records needed healing, 0 errors, 1 mentor
own-Contact healed (Andrew Ciszczon — the reported case)**; only the
v0.121.0 provisioning fix awaits push) —
**the ROOT-CAUSE fix (Doug's challenge): provisioning stamps the mentor's
Contact.** Approval created the User + linked the PROFILE only — every new
mentor was BORN with an unstamped Contact (guaranteed /mentorprofile 403
on contact saves until a later staff re-save/sweep). Provisioning now
merges the User onto the linked Contact right after the profile link
(admin credential, merge-only, non-fatal note on failure). **Root-cause
map, complete:** (1) July-16 collaborators switch orphaned old
single-user assignments → the one-time heal IS the migration (audit
--heal or first reconciliation pass); (2) provisioning never stamped the
Contact → FIXED at source (this release); (3) post-assignment contact
adds unstamped → FIXED at source (v0.118.0 layer 2); (4) hand edits/CRM
schema changes → can't fix at source; nightly reconciliation is the
control. CHANGELOG 0.121.0.

Before that: **v0.120.0** (2026-07-20, 897 tests green) —
**the SECOND stamp-drift class** (live report an hour after layers 1–4: a
mentor's /mentorprofile save 403'd because their OWN linked Contact lacked
their User — a different record class from engagement client records;
staff workaround on deployed code = /mentoradmin **Update Mentor Status**).
CHANGELOG 0.120.0: (1) the stamp engine + audit CLI gain a **mentor
personnel phase** (every CMentorProfile with User+Contact → User merged
onto the Contact's assignedUsers); (2) **/mentorprofile heal-on-access**
(`mentorprofile.service.heal_own_contact_stamp` via
`stamps.ensure_user_on_record` under the API-key identity — the mentor
can't fix it themselves; own server-resolved Contact + own user id only,
merge-only, best-effort, on profile GET and before contact-field PUT).
Extended audit re-run on crm-test: all 43 mentor own-Contacts already
stamped there (the v0.82.0 sweep healed them 2026-07-18) — the reported
case is prod data drift; prod heals via the sweep now or the first
reconciliation pass after deploy. **ALERT_EMAIL_TO/FROM=admin@cbmentors.org
applied to both workers' overlays via doctl 2026-07-20** (activates when
the unpushed code deploys).

Before that: **v0.118.0** (2026-07-20, 890 tests green) —
**stamp-drift prevention layers 2+3 — the plan is COMPLETE** (CHANGELOG
0.118.0): **layer 2** — `sessions/details._stamp_mentor_team` merges the
engagement's mentor team onto every contact linked/created via the + Add
flows (mentor domain, merge-only, best-effort); **layer 3** — nightly
merge-only reconciliation in the worker
(`assignments/stamps.run_stamp_reconciliation`,
`ASSIGNMENT_RECONCILE_SECONDS` default 86400, API-key client, DOC-09
pattern; CRM links = truth, never removes anyone — hand-REMOVALS re-added
nightly is the accepted trade-off). The audit CLI now rides the same
shared engine (`assignments/stamps.py`); re-verified read-only on
crm-test (identical findings). 14 new tests. **After the next
push/deploy the reconciliation runs automatically on both envs — its
first pass will heal the drift the audits found (crm-test: 20
engagements; prod: Doug to run the audit first if he wants the report
before the heal happens).** Doug-side still open: ALERT_EMAIL_TO/FROM on
both workers' overlays; the 3 crm-test mentor profiles with no linked
User; the dangling Tom Cook mentorProfile FK.

Before that: **v0.117.0** (2026-07-20, 876 tests green) —
**assignment-stamp prevention layers 1+4** (Doug's ruling; CHANGELOG
0.117.0): **email alerts** — `send_alert` now delivers via the existing
Gmail delegation (`ALERT_EMAIL_TO` any addresses + `ALERT_EMAIL_FROM` a
real @cbmentors.org mailbox, `OPS_MAILBOX` fallback sender; set on the
WORKER; webhook still works; no channel = WARNING log) — and
**`scripts/audit_assignment_stamps.py`** (read-only report of assigned
engagements whose engagement/contacts/client profile/company lack the
mentor+co-mentor `assignedUsers` stamps; `--heal` = merge-only fix; also
flags mentors with no linked User + dangling mentorProfile FKs).
**crm-test audit result: 20 of 29 assigned engagements have missing
stamps** (left unhealed — Doug's call), 3 mentor profiles with no login
User (Fred Flinstone, Anita Khayat ×2, Rick Bosman), 1 dangling
mentorProfile FK (Tom Cook eng `6a203ce8d59eccbeb`). **Next (approved):
layer 2 — stamp the mentor team onto contacts at link/create time — and
layer 3 — a nightly merge-only stamp reconciliation in the worker (DOC-09
pattern; CRM links = source of truth, hand-removals get re-added — Doug
accepted). Doug-side: run the audit against PROD (overlay key one-liner),
decide --heal, set ALERT_EMAIL_TO/FROM on both workers' overlays.**

Before that: **v0.116.0** (2026-07-20, 872 tests green) —
**the Anthony Sacco incident fixes** (his attendee-attach 403 diagnosed from
the prod logs; Doug hand-fixed the contact in the CRM, these close the app
gaps; CHANGELOG 0.116.0): (1) `forbidden_hint` on a relate/unrelate
`noAccessToForeignRecord` 403 names the LINKED record (the denial is on the
foreign side — he was told "edit access to CSession" when the gap was the
client Contact's assignedUsers); (2) session UPDATE attendee failures are
success-with-warning like create (the create-path warning's own recovery
advice — "re-save its attendees" — used to fail the whole save);
(3) Gmail `messages.get` 404 (`core.gmail.MessageGoneError`) = immediate
SKIP, not a P1-5 failure (deleted-pre-fetch / Meet-Chat history artifacts
were churning 5-pass dead-letter alerts in batches — nothing exists to
lose; real errors still hold the cursor); (4) **Client Administration
"Repair assignment…"** on assigned rows' right-click menu — the missing UI
door to the v0.86.0 P1-9 repair run (assigned rows had no Assign control
and Reassign excludes the current mentor, so the repair was unreachable);
confirm modal → idempotent re-homing, status/date untouched, repair stream
note, NO notice-email compose. Harness-verified end-to-end. **Root-cause
class still open (the prevention discussion):** client records that predate
the stamping era / lost stamps to the Contact collaborators switch mean
more engagements like Anthony's exist; options (one-time audit+heal sweep,
stamp-on-contact-link, a nightly CRM-stamp reconciliation like DOC-09, and
setting ALERT_WEBHOOK_URL) are with Doug.

Before that: **v0.115.0** (2026-07-20, 864 tests green) —
**Funder Contributions tab (the funder ledger)** — built to the same-day plan
`prds/funder-contributions-plan.md` (Doug's rulings baked in: Received-only
totals; soft delete = status Cancelled, NO delete surface; effective date =
received → expected → commitment → application; rolling-12-months tile; four
tiles incl. Scheduled-upcoming; period rollups = rolling 6-month/yearly
windows ANCHORED at the last received contribution with empty gap windows
rendered — everything relative to the last contribution). Funder Management's
record detail gains a Contributions tab (sponsor domain only —
`DomainConfig.contributions_link` gates the tab + endpoint registration):
tiles + recency callout + totals-by-period + sortable/resizable grid
(upcoming accent, dimmed not-counted rows) + a grouped modal editor
(`CONTRIBUTION_FIELDS` = layout AND whitelist; live enum options/required;
in-kind pair shown only for In-Kind gifts; auto title; diffed saves;
two-step discard guard). All summary math on the fly, server-side, in
`sessions/service.contribution_summary` (25 new tests). The CRM
`CContribution` entity ALREADY EXISTS on both CRMs (probe-verified crm-test
2026-07-20; prod enum parity to eyeball). Full mechanics: CHANGELOG 0.115.0.
**VERIFIED LIVE on crm-test 2026-07-21** — first attempts 403'd (empty-body
`POST /CContribution` denial in the run logs; read passed, create didn't):
the crm-test sponsor role's CContribution **Create was set wrong** — fixed by
Doug via the Users → Access merged-ACL check ([[espo-403-diagnosis-merged-team-roles]]),
then a contribution saved end-to-end. CRM prereq per instance: sponsor team's
role gets CContribution create/read/edit (Read=All, no delete) — **replicate
on PROD before prod use**. Still worth one eyeball live: future-dated pledge
→ Scheduled tile + upcoming accent, Cancel → excluded-but-visible, period
rollup on real data. Harness gotcha reconfirmed:
`.ctb__line{display:flex}` beat `[hidden]` until the explicit
`[hidden]{display:none !important}` guard ([[harness-js-clicks-bypass-overlays]]).

Before that: **v0.114.0** (2026-07-20, 839 tests green, committed NOT pushed) —
**press feedback + request timeout**, closing the two follow-ups from v0.112.0
(Doug: "immediately after any button press a spinner is displayed so the user
knows the press worked. Then add timeout too"). New shared
**`frontend/shared/busy.js`**, wired into EVERY app page (5 public forms,
portal, sessions ×3 + the record page, assignments, mentoradmin, mentorprofile,
ops, myemail, directory ×4) — self-wiring, one script tag, and it must load
FIRST because it wraps `fetch` + `XMLHttpRequest` (quickmail sends via XHR).
A spinner appears on the clicked button only when that click actually starts a
request (attributed within 150 ms) and clears when every request from that click
settles; a local-only button (wizard Next, tab switch) gets none. **Visual only
— it never touches `disabled`** (apps own their in-flight guards, and
[[buttons-never-disabled-validate-on-click]]). Sessions `api()` now times out at
60 s (AbortController) with a message that reflects idempotent creates: nothing
typed is lost, and saving again is safe. Verified in the stub harness AND
against the running app (portal Sign in spins/clears; volunteer Next doesn't; no
console errors). **Harness gotcha worth remembering:** a fetch stub that ignores
`AbortSignal` silently never times out — the stub must reject on abort like real
fetch, and a stub that REPLACES `window.fetch` after busy.js loads bypasses the
instrumentation entirely (load the stub first). **Follow-ups DONE (v0.119.0,
committed NOT pushed):** the timeout was extended to every OTHER app via a shared
`CBMBusy.fetch(url, opts)` in `busy.js` (AbortController → readable message,
still spinner-wrapped, throws a `.timeout` Error; wired into assignments /
mentoradmin / mentorprofile / myemail / ops / directory / portal as a one-line
swap; the sessions app keeps its own no-duplicate-worded timeout) — full record
in CHANGELOG 0.119.0. And the **v0.112.0 engagement-activation question is
ANSWERED — a one-off, NOT systemic** (memory:
[[engagement-activation-not-systemic]]): prod read as admin shows Mentor Role has
NO field-level lock on `CEngagement`, and **15 of the 16** engagements with a
Completed session are correctly Active — only Christopher Maurer
(`6a5a2c6ab50ca311f`, the triple-duplicate-save one) is stuck; self-heals on the
next Completed save, or set it Active by hand. Do NOT re-open as a field-ACL
hunt. (v0.119.0 committed ONLY its 8 frontend files + changelog; a parallel
session's uncommitted `test_stamps.py`/`stamps.py` work is why a local `pytest`
may show stamp failures — not from this change, which is frontend JS only.)

Before that: **v0.113.0** (2026-07-20, 839 tests green) —
**Funder Management lists ALL sponsors to every sponsor-team member** (Doug's
report: the grid failed with "your CRM role is missing read access to
CMentorProfile records" even though the users are meant to see the funders).
Root cause: the sponsor list resolved the user's own CMentorProfile + the
`managedSponsors` reverse link, so a sponsor-team role without a
CMentorProfile grant 403'd the whole page. Fix = the partner v0.89.0 pattern:
sponsor domain `list_all=True` (plain ACL-gated CSponsorProfile list, no
CMentorProfile read), a new **Sponsor Manager** grid column (rides
`list_manager_id_attr` → mentor-profile pop-up; "—" when unmanaged), and the
sponsor intake form stamps `SPONSOR_TEAM_NAME` (default `Sponsor Management
Team`, best-effort) on new profiles. Mechanics in the Session Management
domain-table EXCEPTION bullet; CRM prereqs in CHANGELOG 0.113.0 (role reads
CSponsorProfile at team scope + backfill existing sponsors with the team +
intake API Team read; the prod team IS named `Sponsor Management Team`, so
no overlay override was needed).
4 new tests. **VERIFIED LIVE on prod 2026-07-20** — after deploy the grid
403'd on `list CSponsorProfile` (run-log diagnosis): prod's Sponsor
Management Team had no role granting CSponsorProfile read (the user's
merged ACL = only team-attached roles; Mentor Team carries Mentor Role,
which doesn't cover sponsors). Doug attached the grant CRM-side and the
funder list loads. Lesson: the 403 message names the exact denied
entity/operation (`forbidden_hint`) — read it precisely, and check a
user's real merged ACL via the Users → Access button.

Before that: **v0.112.0** (2026-07-20, 835 tests green, committed NOT pushed) —
**fix: saving a session twice no longer creates two sessions.** Doug's report
(a mentor made three sessions from one editor) diagnosed against the live prod
record `6a5a2c6ab50ca311f`: three byte-identical CSessions (same name/status
Completed/`dateStart` 13:00/39,866-char notes), created 17:27:20, 17:28:04,
17:28:06 UTC 2026-07-17, never modified. The "no date" recollection is NOT the
cause — `dateStart` is required in CRM metadata and the editor blocks an empty
save client-side (verified live via `/mentorsessions/api/fields`). One editor
was saved three times because the save looked like it failed. Fixes: (1) the
in-flight guard moved off `saveSessionBtn` into `saveSession` itself — it has
THREE entry points (Save button, unsaved-changes dialog's "Save changes", the
calendar prompt) and only the button could be disabled; (2) creates are
idempotent per `(domain, user, parent, token)`, one token per open new-session
editor, per-key `asyncio.Lock` so a concurrent duplicate waits and takes the
first result (in-memory, 15-min TTL — both apps run one web instance, the
`core/app.py` storeless pattern); (3) a failed post-create `get_session` re-read
no longer surfaces as "Could not create session" (it invites the duplicating
retry — the same rule the attendee-relate path already followed). Verified in
the stub harness with a **counterfactual**: save → Back → "Save changes" ×2
produces **3 POSTs with the guard removed, 1 with it** — a faithful
reproduction of the incident. 6 new tests.
**Open, needs a CRM-side decision:** the engagement is STILL `Assigned` despite
three Completed sessions, so `_activate_engagement_on_completed` failed all
three times (best-effort ⇒ swallowed into a log warning). Anthony Sacco IS the
assigned mentor and IS in the engagement's `assignedUsers`, so record-level
edit should pass — meaning it is either a field-level ACL on `engagementStatus`
(which EspoCRM applies by **silently stripping** the attribute on a 200 OK, so
the app would wrongly report "now Active" — see
[[espo-field-acl-silently-strips-writes]]) or a rejected write. The prod run
logs for 2026-07-17 are past DO retention, so it can't be settled from here;
check the Mentor Role's `fieldData` for `CEngagement.engagementStatus`. Also
still open: `api()` in the sessions frontend has no timeout, so a slow save
gives no feedback and nothing to abort — the condition that starts the whole
retry sequence. Cleanup: delete two of the three duplicates in EspoCRM (keep
`6a5a65f843ddcee0b`, the first).

Before that: **v0.111.0** (2026-07-20, 830 tests green, committed NOT pushed) —
**portal Documentation link**: the signed-in portal home page gains a
"Documentation" section linking to the CBM documentation site
(`https://docs.clevelandbusinessmentors.org`, a BookStack instance) so users
can open the user guides for any of the apps. Every signed-in user sees it
(no team gate — the guides span all the apps), new-tab. URL = the new
`DOCS_SITE_URL` setting (`core/config.py`, default = the live site, empty
hides it) → `docsUrl` on the portal payload (`portal/router._home_payload`)
→ rendered by `portal/frontend/` next to the CRM section.

Before that: **v0.110.0** (2026-07-19, 829 tests green) —
**Submission Admin: the shared info@ mailbox model** (Doug's rulings after
his "submissions pick up unrelated emails" report — full mechanics in
CHANGELOG 0.110.0): (1) **thread anchoring** — every /ops send records its
Gmail thread on the submission (migration **0013** `thread_ids`; compose
passes `submissionId`, `register_quicksend` gained `after_send` +
`shared_mailbox` hooks) and the conversation view + Reply column read ONLY
anchored threads, never an address search; (2) **send + read as
`OPS_MAILBOX`** (info@cbmentors.org, display name `OPS_MAILBOX_NAME` = "CBM
Info", no personal signature) — every admin sees the same conversation, the
v0.106.0 per-admin caveat gone; empty OPS_MAILBOX = legacy per-admin mode,
whose address search is now time-boxed to the submission lifetime;
(3) **inbound capture** — the worker polls the info@ inbox
(`ops/inbound.py`, `OPS_INBOUND_SECONDS`) and captures each NEW thread as a
**held_review `info-email`** submission (stateless layered dedup: token =
thread id + known_gmail_threads, so replies to anchored form-conversations
never double-capture; outbound-initiated threads + bounces skipped);
(4) **triage-first delivery** — new delivery-only form kind
`forms/info_email` (NO public endpoint) reusing the info-request
orchestrator (now parameterized: form_slug/via/channel/source) with
`form="info-email"`, `source="Email"`; /ops shows **Approve** ("Create CRM
records?") = redrive, Discard = spam with zero CRM residue; the redrive
guard also now permits `discarded` (fixed a latent undo-discard refusal).
Verified: 829 tests green (31 new); migration 0013 + all new store surface
round-tripped on live local Postgres. **NOT yet live. Activation (Doug):**
make info@ a REAL Workspace mailbox (not a group — DWD then covers it, no
new scopes); set `OPS_MAILBOX` on web AND worker overlays (pre-deploy
migrate runs 0013); CRM: add an **"Email"** option to
`CIntakeSubmission.form` (until then the audit log for approved email
submissions WARNs, best-effort); and — CRM-side, unrelated to this app —
stop CRM-direct sends using the espo@ return address (EspoCRM outbound
SMTP/group-account config; Doug wants it ended). First live pass: send a
real email to info@ → held row appears → Approve → Contact +
CInformationRequest created → reply from the detail → thread shows for a
second admin too.

Before that: **v0.108.0** (2026-07-19, 814 tests green) —
**Submission Admin follow-ups (the four 0.106.0 suggestions, Doug
approved all): Resolved/Open workflow** (migration 0012 resolved_at/by;
Mark resolved/Reopen on the detail; Open/Resolved/All filter DEFAULTS
TO OPEN; ✓ chips + open/resolved counts), **awaiting-reply grid column**
(POST /replystates — 1 Gmail search + 1 headers fetch per OPEN row, cap
30, async after render; "reply owed"/"waiting on them"; new
GmailClient.get_message_headers), **reply threading end-to-end** (an
existing conversation makes the compose a Reply: Re: subject +
threadId/In-Reply-To/References through quickmail → /sendmail →
send_quick_message → build_mime/gmail.send — quickmail opts gained
subject+reply passthrough, QuickSendIn the three fields), and the
**InfoRequestReply template pre-applied** on fresh info-request
composes (OPS_REPLY_TEMPLATE, default InfoRequestReply — Doug already
built the template; silent blank-compose fallback). Verified: 814
tests green (7 new); migration 0012 + set_resolved round-tripped on
live local Postgres; every flow driven in the stub harness (open-only
default + chips, reply column states, resolve/reopen, reply compose
carrying threadId/inReplyTo/references in the send payload, template
pre-applied subject+body; boot null-guard for stale cached
index.html). v0.107.0 = the parallel directory session.

Before that: **v0.106.0** (2026-07-19, 807 tests green) —
**Submission Admin REBUILT** (Doug's spec; CHANGELOG 0.106.0 for the
full list): list page = full-height sticky-header grid with sortable +
drag-resizable columns, alternating rows, center search, top-right user
corner, two-step Re-drive/Discard; detail = sessions-style tabs —
Overview (facts rail left; editable staff NOTES card — new `notes`
column, migration 0011, saved with acted_by; the submitter email
conversation below), Details (payload/progress/result + EspoCRM deep
links for created records), Communications (full history with cleaned
expandable bodies + "Email the submitter" via register_quicksend on the
ops router). Conversation = LIVE Gmail search of the signed-in admin's
OWN mailbox (from:X OR to:X, cap 25, nothing stored; readable
degradation reasons; per-admin visibility — noted in the changelog).
Verified: 807 tests green (5 new ops tests); migration 0011 +
set_notes round-tripped on live local Postgres; the whole UI driven in
the stub harness (grid sort/resize/search/alt-rows, notes edit→PUT,
CRM links, comms expand + quoted-reply demotion, compose prefilled,
two-step redrive, empty states; no console errors). NOT yet driven
live (needs deploy + an ops admin with a linked cbmEmail profile for
the email half). Ops gotcha fixed: display:flex on a section beats
[hidden] — the app CSS now guards `.ops [hidden]`.

Before that: **v0.105.0** (2026-07-19, 804 tests green) —
**Email round two (Doug's picks 1–4 from the compose-functionality review):
My Email + unread/awaiting-reply + Forward + attach-from-Documents.**
- **My Email (`/myemail/`, new `myemail/` package, portal tile, aliases
  `/myemail` `/email`)**: ONE inbox across every record the manager handles —
  scope = the CMentorProfile reverse links (owned + co-mentored, all three
  domains, status-filtered like the grids), deliberately NOT ACL-wide (manager
  roles read CConversation at all). Rows carry record chips
  (`/{slug}/record/{id}` deep links), unread dot/bold, amber "Awaiting reply"
  chip, filter tabs with counts, search, Mark-all-read; the thread modal's
  reply path is "Open in record — reply there" (full compose lives on the
  record page). Gate: member of ANY session-tool team (admins pass); portal
  tile only when `gmail_sync`. All reads as the user.
- **Unread/awaiting enrichment** (`comms/service.enrich_conversation_rows`,
  BOTH My Email and the record Communications tabs): per-user read stamps in
  the new **`conversation_seen`** table (**Alembic 0010 — pre-deploy migrate
  required**; `CommsStore.mark_seen/seen_map/mark_many_seen` + Memory mirror);
  never-opened conversations count unread only within a 30-day window;
  awaiting-reply = last message inbound, derived from ONE batched
  CCommunication `in`-query per page (decoration — fails open). Thread GETs
  (sessions + myemail) stamp seen; the record tab button shows "(N)" unread.
- **Forward** (record compose): thread-view ↪ Forward button → Gmail-style
  forwarded block (headers + message), NOBODY pre-checked (`pre.forward`),
  "Fwd:" subject, title "Forward"; a no-comment forward sends (pristine-body
  guard exempts forwards).
- **Attach from documents** (record compose, `docsOn()`): picker over the
  record's Documents (active, not-yet-attached only); chips send
  `{documentId}` and `sessions/router._resolve_document_attachments` fetches
  ORIGINAL bytes at send time via `docs_service.fetch_document(original=True)`
  (record-scoped — foreign doc ids 404; failure = CommsError, send blocked).
  Doc chips ride the compose draft.
- Verified: 804 tests green (10 new in tests/test_myemail.py); both UIs driven
  in the stub harness (inbox filters/thread/mark-read/full-width, record-tab
  badges + tab count clearing, forward incl. no-comment send + doc chip →
  payload). **NOT yet driven live** — first live pass: open /myemail as a
  real mentor (rows + record links), open a thread (unread clears), forward a
  real message, send with a document attached (Drive fetch under the
  service identity). Migration 0010 rides the pre-deploy migrate job.

Before that: **v0.104.0** (2026-07-19, 794 tests green, committed NOT pushed) —
**session-tool display names renamed** (Doug): Mentor Sessions →
"Client Management", Partner Sessions → "Partner Management", Sponsor
Sessions → "Funder Management" — portal tiles + page headings + tab
titles (DomainConfig.title / portal _apps_for; routes/gates unchanged;
see the note atop the Session Management section). v0.102–0.103 = the
parallel Workspace-Directories session.

Before that: **v0.101.0** (2026-07-19, 789 tests green) —
**edit-loss protection extended to the SESSION editor** (Doug's follow-up
to v0.99.0): field + attendee changes autosave to localStorage
(existing session keyed by id, new session per record with a :new
suffix); reopening offers Restore/Discard; restored fields ride the
sentinel-snapshot so an update-save sends them; restored attendees
re-check boxes without touching the diff baseline; save or the
leave-confirm Discard clears; hidden editor never stashes. beforeunload
now also fires for an open dirty session editor (the in-app
Save/Discard/Keep-editing confirm predates this, unchanged).
Harness-verified: new-session crash->banner->Restore->Save POSTs the
restored notes->cleared+no resurrection; existing-session draft keyed
by id; leave-Discard clears.

Before that: **v0.100.0** (2026-07-19, 789 tests green) —
**Workspace Directories — Phase 1** (the CRM-style workspace Doug requested).
A new **`directory/`** package (one engine + one router per kind, the sessions
pattern) serves browsable grids — **Companies** (Account), **Contacts**
(Contact), **Mentors** (CMentorProfile), **Partners** (CPartnerProfile;
inline-editable, added v0.103.0) — at `/directory/{kind}`, gated by the
new `WORKSPACE_ALLOWED_TEAMS` (default `Mentor Team`); reads/writes run as the
signed-in user (EspoCRM ACL is the data scope — the Mentor Role already reads
all Contacts/Accounts, so those grids are org-wide with no CRM change). **Grid
columns + the detail-pop-up arrangement are read LIVE from the CRM's own
layouts** (new `EspoClient.layout`/`.i18n`: `{entity}/layout/list` +
`/layout/detail`) so they match the CRM and auto-sync — nothing hardcoded (see
[[espo-layout-api-readable]]). Toolbar = **Filter** (left, live options) ·
**Search** (center) · **View/Edit** (right, act on the selected row, never
disabled). Row-select → read-only **preview pane**; **View** → pop-up (all
data, CRM-arranged); **Edit** → inline editor for records the user OWNS (reuses
the sessions Details whitelist/gate; Contacts/Companies only — **Mentors** hand
off to `/mentorprofile/`, own row only). The **portal is now a launcher**: a
**Directories** tile section + app tiles open in **stable named browser tabs**
(`window.open(url,"cbm-…")`) so re-clicking reuses the tab (de-dup); payload
adds `directories` + per-app `target`. Plan:
`prds/workspace-directories-plan.md`. Verified: 789 tests green (12 new); read
path exercised LIVE against crm-test (68 companies / 128 contacts / 43
mentors); full UI loop verified in the stub harness, no console errors. **NOT
yet driven live as a real non-admin mentor** (needs a portal login). Inline
Contact/Company edit (originally Phase 2) is already included; Phase 3
(open-tab badges, saved filters) is future.

The directory arc continued the same day (all committed, push per convention;
CHANGELOG has each entry): **v0.102.0** — fix: the detail-pop-up's `.dir__modal`
overlay (`display:flex`) overrode the `hidden` attribute, so it covered the
grid on load and blocked every directory; fixed with `[hidden]{display:none
!important}` (verified with a REAL mouse click — an attribute check isn't visual
visibility; see [[harness-js-clicks-bypass-overlays]]). **v0.103.0** — the
Partners directory. **v0.107.0** — Company pop-up enhancements (Doug's
requests, Account-only): shows only the **profile panel matching
`cCompanyType`** (a Client hides Partner Profile, etc.); a **Company Contacts**
list at the bottom (name link → nested read-only contact-detail modal, phone/
email as tel/compose links); **composite `address` fields now render** —
`shippingAddress`/`billingAddress` are EspoCRM `address` type, so reading them
as one attribute returned empty; now composed from the sub-fields for display +
expanded into editable Street/City/State/ZIP/Country inputs in edit mode; the
company email already rendered when set (confirmed live). **v0.109.0 — one
record, one tab** (session tools, NOT a directory feature — the session-tools
arc): the same engagement open in two browser tabs invites dirty-data edits, so
Client/Partner/Funder Management now (a) open each grid record in a STABLE
per-record window (`window.open(url,"cbm-rec-<slug>-<id>")`) so re-clicking
reuses the tab, and (b) elect ONE owner tab per record on the dedicated record
page via a `BroadcastChannel` — a second tab shows a "already open in another
tab" block instead of the editor, with owner-close handoff. Slug-scoped, so it
covers all three session domains from the one shared frontend (verified live
two-tab on `/mentorsessions` AND `/partnersessions`). See
[[single-tab-record-guard]].

Before that: **v0.99.0** (2026-07-19, 777 tests green) —
**edit-loss protection** (Doug approved both recommendations): dirty edit
forms (Details sections + Overview notes) two-step "Discard changes?" on
Cancel (notes computes dirtiness at CLICK time, not the debounced flag),
a beforeunload guard warns on page close/refresh, and dirty fields
AUTOSAVE to localStorage (cbmEditDraft: keys, 7-day expiry, quickmail
pattern) — Details forms offer a Restore/Discard banner on reopen
(restored fields count as changes so Save writes them); the notes editor
reopens INTO its draft with a Start-fresh escape; save/discard clears,
late debounce ticks can never resurrect a cleared draft. GOTCHA burned
an hour: the helpers first collided with the v0.88.0 COMPOSE draft fns
(draftKey/clearDraft — later function declaration wins in the shared
IIFE, silently mis-keying drafts) → renamed editDraftKey/saveEditDraft/
readEditDraft/clearEditDraft; and an invisible NUL byte in a sentinel
string made grep treat app.js as binary. Full lifecycle harness-verified
(autosave key/value, two-step cancel, crash→banner→Restore→"2 fields
changed"→Save PUTs restored values→cleared, notes reopen-into-draft +
Start fresh, instant-cancel arming).
**Save/Cancel at the top AND bottom of every edit form** (Details section
forms get a top bar paired with the sticky bottom bar, one shared dirty
state; the Overview notes editor gets header Save/Cancel + the bottom
pair; save errors scroll into view). Harness-verified.
**+ double-click the notes panel opens the full-page View** (0.97.1 — the
fastest route; button/drag-bar double-clicks keep their own jobs).
**Overview notes: 50%-height cap + drag bar + full-page View** (Doug's
request; frontend-only, all three domains): the notes panel body caps at
50vh and scrolls, a drag bar under it resizes the cap (sticks across
re-renders), a View button + right-click menu (View/Edit,
assignments-style) open the complete notes in a freely resizable
92vw×86vh pop-up (no width cap per the ruling; Close/Escape/backdrop
dismiss). Verified in the stub harness with 40-paragraph notes (cap =
half the viewport + inner scroll, drag grows it, menu opens/closes,
pop-up shows all content, resize:both, esc+backdrop close; no console
errors — watch for the browser CACHING styles.css when eyeballing).

Before that: **v0.96.0** (2026-07-19, 777 tests green) —
**Details-tab edit buttons are NEVER hidden** (Doug's ruling, extending
[[buttons-never-disabled-validate-on-click]] to hiding — a missing button
reads as a bug and generates support calls): the parent strip's Edit, the
org-card Edit, contact-row Edit, and row Remove all always render;
clicking without the CRM edit grant shows a readable "You don't have
permission to edit X — ask CBM staff if you need it." notice instead of
opening the form / arming the remove (frontend-only; verified in the stub
harness both ways — read-only sections message without opening, editable
ones still open; design exclusions like the assigned-Mentor row's absent
Remove are unchanged). The memory file records the extension.

Before that: **v0.95.0** (2026-07-18, 777 tests green) —
**record notes edit in place on the Overview** (Doug's ruling: notes are
the most important item on partners/sponsors — save the clicks): the
Overview's notes panel (Partner/Sponsor/Engagement Notes, all three
domains) gains an always-active Edit button → inline editor (CBMRichText
for wysiwyg, textarea for the sponsor's text notes) → Save PUTs through
the same whitelisted `/details/{entity}/{id}` path (readable 403 for
users without the grant), panel re-renders in place, Details-tab cache
invalidated. `overallNotes` now carries `entity`+`attr`. Verified in the
stub harness: partner richtext + sponsor textarea loops (Edit → type →
Save → PUT diffs only the notes attr → panel updates + success notice;
Cancel discards, no PUT; no console errors). ALSO answers Doug's "no
place to edit partner attributes on the Details tab": the edit is the
strip's right-edge Edit button — until v0.96.0 it was hidden when the CRM
denied edit on the record (superseded: it now always shows and messages
on click), and the curated Partnership/Sponsorship forms are in the
UNDEPLOYED v0.91–0.93 — after deploy, a partner manager who gets the
permission message needs their role granted CPartnerProfile edit at team
scope (the same CRM pass as the v0.89.0 read-scope work).

Before that: **v0.94.0** (2026-07-18, 777 tests green) —
**Reliability hardening Phase 6 — infra/ops — COMPLETES THE WHOLE
RELIABILITY ARC** (all six phases of
`prompts/reliability-hardening-prompt-v0.1.md` /
`reliability-review-2026-07-17.md` are implemented: P0-1..4 v0.77.0,
liveness+telemetry v0.84.0, staff write chains v0.86.0, Gmail loss
prevention v0.87.0, Drive+intake residuals v0.92.0, infra/ops v0.94.0).
Doug's decisions this session: **D3 = 2 MB / 30 per IP per 10 min**,
**D4 = production-tier DB upgrade**. Phase 6 highlights (CHANGELOG 0.94.0):
- Web startup banner + **fail-fast** on live-without-API-key and
  async-without-DATABASE_URL; intake body cap (2 MB; volunteer 8 MB for
  its in-JSON resume) + per-IP rate limit (30/10 min, in-memory,
  readable 413/429); worker **SIGTERM graceful stop** (finish current
  item, stop claiming — drilled live, clean exit 0);
  `metrics().recentAvgLatencySeconds` (last 50 completions);
  `GDRIVE_IDENTITY` is a Literal; Docker pins `python:3.12.8-slim` +
  `uv:0.10.6` (tags verified against both registries); **boot-time
  `create_all()` removed — Alembic (the PRE_DEPLOY migrate job) is the
  sole schema authority** (fresh envs must migrate before first boot;
  DEPLOYMENT.md notes it).
- DEPLOYMENT.md gains a **"Reliability operations"** section: the D4
  backup ruling + restore runbook, DO uptime/alert guidance on the
  `/healthz` worker fields, the worker `instance_count: 1` invariant,
  overlay-recovery + unrecoverable-secret list, and the D3 limits.
- **Doug-side actions now open:** (1) console-upgrade `cbm-db` +
  `cbm-db-prod` to a production tier (D4 — until then there are STILL no
  backups); (2) after the next push/deploy, create a DO alert on
  `worker.lastHeartbeatAgeSeconds` (~120s threshold); (3) the arc's
  **live-verification checklist** (prompt §"Live-verification"):
  poisoned-row drill on crm-test, kill-the-worker → healthz age grows →
  alert, one Gmail pass with an over-length subject → failing/dead-letter
  alerts (the known prod message `19f298a147e3ba38` should now surface),
  assign-repair on a half-assigned engagement, details-PUT bypass → 404,
  portal login lines in run logs. NOTE the deploy also runs migrations
  0007–0009 on both managed DBs (heartbeat, acted_by, comms
  loss-prevention) via the PRE_DEPLOY job.

Before that: **v0.93.0** (2026-07-18, 766 tests green) —
**Sponsor editing parity with the v0.91.0 partner fixes** (Doug's follow-up
ruling; frontend-only): curated `CSponsorProfile` edit form — where
`description` IS the sponsor-notes field, kept editable as "Sponsor notes"
(feeds the Overview panel; NOT excluded like the partner's) — with the
record name + total-contribution currency companion excluded; the
sponsor-domain Company form/view hides `description`/`cClientNotes`/the
Account-level `cSponsorNotes` twin. Sponsor loop verified in the stub
harness (view hides the fields, curated groups, notes save → diffed PUT →
Overview updates without reload; no console errors). Mechanics recorded in
the Session Management section's "Partner grid / notes" bullet + the
v0.91.0 block below.

Before that: **v0.92.0** (2026-07-18, 766 tests green) —
**Reliability hardening Phase 5 — Drive + intake-pipeline residuals**
(P1-13 + the P2 Drive/intake items; full list in CHANGELOG 0.92.0):
- **Drive create safety (P1-13, strategy = pre-generated ids,** documented
  in the `docs/service.py` docstring): uploads pre-assign
  `files.generateIds` ids — retries can't duplicate (409 resolves to the
  committed file), lost responses roll back by the known id; creates
  without a pre-set id are never blind-retried; failed folder creates
  re-run find-or-create. Stale cached record folders (deleted in the Drive
  console) self-heal via `clear_folder_cache` + one retry.
- **Grants**: non-inherited group/domain/anyone permissions are revoked
  (never CRM-justified — a console-added org share used to survive
  forever); the nightly reconciliation alerts on a folder erroring two
  consecutive passes, not just on removals.
- **Content proxy**: `?original=true` STREAMS (sessions + /mentoradmin;
  `DriveClient.stream_file` + `docs.service.stream_original`, primed so
  pre-body errors still map to readable responses); the docs LIST endpoint
  gained the per-record ACL read (docs-D6 — metadata was enumerable
  across ACL boundaries).
- **Intake residuals**: capture failure → payload at ERROR + controlled
  503; malformed JSON → 422; the sync-with-store path delivers through
  `ResumableClient` (P1-8 — /ops redrives now RESUME instead of
  duplicating); `Sponsor` added to the `cContactType` drift contract; the
  info-request description append is once-per-delivery
  (`ResumableClient` named steps + `run_step_once`, pipeline-M1).
- Verified: 766 tests green (16 new incl. the "lying Drive" sims —
  committed-then-5xx folder create, lost upload response, rollback-failed
  logging, 409-resolves-to-committed, stale-folder retry, stream path);
  no new migration; `clear_folder_cache` round-tripped on live local
  Postgres. **Remaining: Phase 6 (infra/ops: startup banner, fail-fast
  config, body caps + rate limit, SIGTERM, Docker pins, windowed latency
  + the DEPLOYMENT.md ops handoffs incl. the P1-7 backup decision D3/D4).**

Before that: **v0.91.0** (2026-07-18, 765 tests green at commit) —
**Partner editing fixes** (Doug's report after driving v0.89.0): a Details
save now refreshes the Overview/Sessions tabs (`refreshRecordViews` — the
Partner Notes he typed only appeared after a full reload), the partner
Company form's Account-level `cPartnerNotes` twin is retired (notes typed
there could NEVER reach the Overview, which reads
`CPartnerProfile.partnerNotes` — the root cause of "notes don't show"),
the Partnership edit form is a curated `noExtras` layout (Partnership /
Value & goals / full-width Partner notes; no more Additional-details
dump), `CPartnerProfile.description` is server-excluded from Details
(intake drift-note field, CEngagement precedent + smuggle-drop test),
and the partner-domain Company form/view hides `description` +
`cClientNotes`. Full
loop verified in the stub harness (curated form, hidden fields, richtext
edit → diffed PUT → Overview updates without reload; no console errors).
(v0.90.0 = a parallel session's comms template-font fix.)
**v0.93.0 extends the same pass to the SPONSOR domain** (Doug's follow-up,
frontend-only): curated `CSponsorProfile` edit form — where
`description` IS the sponsor-notes field, kept editable as "Sponsor
notes" (feeds the Overview panel; NOT excluded like the partner's) —
name + the total-contribution currency companion excluded; the sponsor
Company form/view hides `description`/`cClientNotes`/the `cSponsorNotes`
Account twin. Sponsor loop verified in the stub harness (766 tests
green at commit).

Before that: **v0.89.0** (2026-07-18, 746 tests green, deployed) —
**Partner Sessions: all partners + Partner Notes on top + Partner Manager
quick-email** (Doug's three requests; mechanics in the Session Management
section's domain-table EXCEPTION + "Partner grid: Partner Manager column"
bullets, CRM prereqs in CHANGELOG 0.89.0): (1) the partner grid lists ALL
partners the user can read (`DomainConfig.list_all`; team permissions are
the CRM-side gate — role read scope → team + backfill existing records'
Teams + grant the intake API role Team read), and the partner intake form
stamps `Partner Management Team` on new CPartnerProfiles (best-effort,
`PARTNER_TEAM_NAME`); (2) the Overview's record-notes panel (Partner
Notes etc.) always renders at the top above the session summaries (muted
placeholder when empty — why Doug never saw it: nearly all crm-test
partnerNotes are empty, probe-verified live); (3) new Partner Manager grid
column → CMentorProfile pop-up → email compose links. Verified: full suite
green; the stub-harness drove all three flows in-browser (all-partners
grid + "—" for unmanaged, manager link → peek → quick-compose with To
pre-filled, notes placeholder on P1 / rich content on P2; no console
errors). **NOT yet driven live** — needs the CRM-side team work above
before "all partners" actually widens beyond the user's own rows.
(Version-race note: this feature's core/config.py + app.js halves were
swept into 743a3db (v0.87.0); HEAD is coherent at/after this release's
commit. v0.88.0 = the parallel compose-overhaul session, see CHANGELOG.)

Before that: **v0.87.0** (2026-07-18, 740 tests green, committed NOT pushed) —
**Reliability hardening Phase 4 — Gmail sync loss prevention** (P1-5 F1–F6;
Doug's decision this session: **D6 = dead-letter after 5 consecutive
failing passes**). Highlights (full list in CHANGELOG 0.87.0):
- A failed message ingest **holds the mailbox cursor** (re-read next pass,
  dedup makes the replay cheap) and counts in the pass totals ("failed" —
  the robert.cohen incident pass had logged "0 sync errors"); after 5
  consecutive failing passes the id is **dead-lettered** (skipped, ERROR
  log, `/ops/api/metrics` `gmailSync` block, recoverable via GMAIL_RESYNC
  which also resets failure tracking); webhook alerts at persistence
  (2nd pass) + dead-letter.
- `last_synced_at` = last FULLY-successful pass only (the expired-cursor
  backfill window source); truncated history listings resume from the last
  processed entry instead of skipping to the tip; `GmailClient` gains
  429/5xx backoff honoring Retry-After + one shared HTTP connection per
  client (sync closes per mailbox) + a 120s no-retry send timeout (send
  idempotency out of scope — noted).
- **Empty conversation shells reuse** via a local `(mailbox, thread id) →
  conversation` Postgres map (**Alembic 0009** — pre-deploy migrate; NO
  CRM build needed — CConversation has no thread field, cconversation-
  entity.md checked); the send path persists the **include override BEFORE
  the write-through ingest** (one Espo blip used to permanently orphan a
  confirmed-unknown-recipient thread), and a write-through failure now
  surfaces in the compose dialog as a notice.
- Verified: 740 tests green (25 new incl. the DoD sims — cursor-hold →
  dead-letter-after-5, outage window from last success, 21-page history
  no-skip, shell reuse, RESYNC reset, alert transitions, and
  `tests/test_gmail_client.py` for the transport); migration 0009 + the
  new store surface round-tripped on live local Postgres. **NOT driven
  against live Gmail (by design). Live re-verify items for Doug after
  deploy:** one clean sync pass on crm-test (totals now include
  failed/deadLettered), the still-rejecting prod message
  `19f298a147e3ba38` should now show as failing→dead-lettered with alerts
  instead of silent loss ([[prod-ccommunication-field-length-drift]] —
  its real fix is still app-side subject sanitizing, not built), and one
  compose send confirming the roomier send timeout. **Remaining phases
  5–6, one per session.**
- Version-race note: `comms/service.py` + `sessions/frontend/app.js` carry
  a parallel compose-arc's (Cc/Bcc, compose-guard) uncommitted hunks swept
  into this release commit — that session's own release completes it (the
  repo's established pattern; HEAD tests green at commit).

Before that: **v0.86.0** (2026-07-18, 723 tests green) —
**Reliability hardening Phase 3 — staff-tool write chains** (P1-9/11/12 +
six P2 items; Doug's decision this session: **D5 = the hide-conversation
unlink runs as the signed-in user**). Highlights (full list in CHANGELOG
0.86.0):
- **P1-9**: Assign with the SAME mentor the engagement already has = a
  **repair run** (re-executes the idempotent re-homing + posts a
  repair-labelled stream note, response `repaired:true`) instead of the
  stale-guard 400 that made a half-assigned engagement unfixable in-app.
- **P1-11**: `store.redrive` guarded to needs_attention/retry/held; new
  `acted_by` column (Alembic **0008** — pre-deploy migrate) records who
  redrove/discarded from /ops.
- **P1-12**: staff API requests re-read team membership from the CRM when
  the session stamp is older than `MEMBERSHIP_REFRESH_SECONDS` (default
  900; middleware in `core/app.py`, stamp in `auth.set_session`); a dead
  token clears the session → 401.
- P2s: own-profile resolution by membership over ALL assignedUsersIds
  (`assignments.service.is_assigned_to`); calendar **id-before-invite**
  (quiet create → persist id → invite patch; failed persist deletes the
  uninvited event, failed invites report `inviteError`); session-create
  attendee failures = success-with-warning naming the session; provisioning
  writes `cbmEmail` BEFORE User creation + caches the admin token
  (re-login on 401); the status-check sweep computes engagement metrics
  once per roster; exclude_conversation unlinks as the user FIRST and only
  then records the override (failed unlink = readable error, nothing
  recorded).
- Verified: 723 tests green (20+ new incl. `tests/test_membership_ttl.py`);
  PG integration with migration 0008 run live; assign-repair + session-
  create-warning flows driven in the stubbed-browser harness; TTL flows
  (refresh, no-recheck-when-fresh, dead-token 401, portal exemption)
  against real local sessions. **Remaining phases 4–6, one per session**
  (Phase 4 = Gmail sync loss prevention; its D6 dead-letter N — recommend
  5 — still to confirm with Doug).

Before that: **v0.84.0** (2026-07-18, 707 tests green) —
**Reliability hardening Phase 2 — "see the failures"** (worker liveness +
logging/telemetry, per `prompts/reliability-hardening-prompt-v0.1.md`;
Doug confirmed decisions **D1 = keep the DB-down 503** (heartbeat/backlog
reads never 503) and **D2 = metadata-only PII logging** this session):
- **P1-6**: `worker_heartbeat` table (Alembic **0007** — remember the
  pre-deploy migrate) stamped each worker loop; `/healthz` gains a
  best-effort `worker` block (lastHeartbeatAgeSeconds / backlog /
  oldestPendingAgeSeconds / stranded) for an external uptime check;
  `metrics()` counts lease-expired `processing` rows as **stranded** (new
  alert in `run_alert_check`, flows to `/ops/api/metrics`).
- **Logging**: shared `core/logging_setup.py` (name + seconds in BOTH
  processes; new `LOG_LEVEL` setting); async accept logs slug/token/
  reference and the worker logs slug+token on claim/delivered/retry/
  needs_attention — one submission traceable by token end-to-end; actor
  (userName) in every staff `_crm_failure` + INFO on staff write successes
  (changed field names, never values) + portal login success/failure +
  `/ops` redrive/discard actor + server-side provisioning step log (never
  the temp password); the review's eight silent `except: pass` sites now
  WARN (incl. P1-10 co-mentor read naming the may-drop-co-mentors
  consequence, also added to the newer reassign path).
- **D2**: `log_submission` failure WARNING is metadata-only when a durable
  store holds the payload; full dump only in storeless dev mode.
- Verified: 707 tests green (+ PG integration incl. heartbeat/stranded run
  against live local Postgres with migration 0007 applied); local
  two-process drill — accept line → worker claimed/delivered lines by the
  same token, `/healthz` showing the worker block, both processes logging
  names + seconds. **Remaining phases 3–6 of the reliability prompt, one
  per session.** After deploy: point a DO uptime alert at the new
  `/healthz` worker fields (the Phase 6 ops handoff).

Before that (same day): **DOC-MGMT Phase 3 ACTIVATED LIVE ON BOTH
ENVIRONMENTS (2026-07-18)** —
the v0.76.0 build is now operational. Session record: (1) drive membership
verified via the browser and corrected under **Doug's amended ruling (PRD
v1.5): the two designated system administrators (doug.bower@,
allen.ingram@) RETAIN drive membership** for maintenance/review alongside
the service account; `espo@cbmentors.org` was removed in the session
(final list = SA + the two admins, all Manager). (2) Both overlays
regenerated from the live specs and applied via doctl:
`GDRIVE_IDENTITY=service` on **web**, and
`GDRIVE_DOCS`/`GDRIVE_SHARED_DRIVE_ID`/`GDRIVE_IDENTITY` on **worker**
(the nightly reconciliation runs there), both apps healthy after deploy.
(3) **DOC-09 VERIFIED LIVE on prod:** the worker's startup reconciliation
authenticated as the SA, enumerated the 2 real engagement folders, and
issued 2 Commenter grants to the entitled mentor — `+2 grants, 0 errors,
0 CRM links` (correct: `documentsFolderUrl` not built yet). crm-test pass
clean (0 folders — no documents there yet). **Both governing docs bumped
to v1.5** recording the amendment + activation; `prds/` exec-summary copy
synced; GDRIVE-DOCS-SETUP.md Task 6 steps 1–2 marked DONE. **Remaining:**
the `documentsFolderUrl` CRM field build
(`documentsfolderurl-crm-field.md`), and the hand-driven checklist items
(assign/unassign grant flow as a mentor, Mentors/-folder no-grant check,
archive/restore against the real drive, hand-grant removal alert — Task 6
verify list). Side observation from the deploy logs, NOT this feature: a
schema-drift alert fired on both envs — `CMentorProfile.industrySector`
no longer offers the entire expected 28-value list (the CRM team changed
the enum; re-sync `scripts/sync_form_options.py` / `core/schema_contract.py`).

**Main is at v0.83.0** (2026-07-18, 706 tests green, **pushed and DEPLOYED —
prod + crm-test `/healthz` both verified at 0.83.0**) —
**Meeting Transcript integration — Google Meet (Phases 1+2 of
`prds/meet-transcript-integration.md`), gated OFF by `MEET_TRANSCRIPTS`
(default false; set on web AND worker at activation).** Built per Doug's
2026-07-17 rulings (auto-enable always, Meet now / Zoom later behind a
provider seam, store transcript text + the permanent Google Doc link):
- **`core/gmeet.py`** — `MeetClient`, Meet REST v2 via the shared
  service-account + DWD stack (scope `meetings.space.created`), gcalendar
  pattern: space lookup by meeting code, auto-transcription enable,
  conference-record search (meeting code + ±36h start window — handles reused
  codes), paged transcript entries/participants; pure helpers (meeting-code
  regex, speaker-attributed escaped HTML with elapsed [MM:SS] stamps,
  consecutive same-speaker entries merged).
- **Schedule-time** (`sessions/gcal.py` `_enable_transcription`): after the
  hook creates an event with a GENERATED Meet link, the space's
  `autoTranscriptionGeneration` is set ON as the organizer; result rides the
  `calendar:{...}` notice as `transcription:{ok,...}`; best-effort; hand-typed
  links untouched.
- **Worker retrieval** (`sessions/transcripts.py`, timer
  `MEET_TRANSCRIPTS_POLL_SECONDS` default 1800, monitoring-check pattern,
  API-key client — needs the CustomAppAPIRole CSession read+edit grant):
  candidates = past sessions inside `TRANSCRIPT_GIVE_UP_DAYS` (14) with a
  meet.google.com link and null `sessionTranscription` (status deliberately
  not required to be Completed); organizer = session assigned users →
  `CMentorProfile.cbmEmail` map (Python match, never a where on
  assignedUserId), parent-manager-profile fallback; `TranscriptSource` seam
  (Meet only in phase 1); one CSession update writes the clamped transcript
  HTML (+ `transcriptDocUrl` when that field exists). No retry state — a
  session stays a candidate until it resolves or ages out of the window.
- **Feature detection**: both CRM fields detected per read (`get_session`
  selects `transcriptDocUrl` when present; the retrieval cycle no-ops until
  `sessionTranscription` exists). Session view gains a copyable "Transcript
  document" facts-grid row. CRM handoff doc: **`csession-transcript-fields.md`**
  (two fields + the API-role grant + Google prerequisites).
- **NOT yet activated — Phase 0 state as of 2026-07-18 (all but Google DONE):**
  ✅ licensing confirmed by Doug — CBM is on **Business Standard**, so
  transcripts are included; ✅ CRM fields built and probe-verified on crm-test
  (`sessionTranscription` wysiwyg + `transcriptDocUrl` url) and the **API key's
  CSession READ verified live** (56 rows; the EDIT half of the grant is proven
  by the first live write — a miss surfaces as a logged 403, never a crash;
  prod fields unverifiable from here, the overlay's API key is EV-encrypted);
  ✅ v0.83.0 deployed to both envs (flag off ⇒ inert).
  **REMAINING (Doug, in progress): the three Google-side changes** —
  (1) Admin console → Meet video settings → **Transcription = ON** for the OU;
  (2) DWD row: add `meetings.space.created` (edit the existing line — the
  field REPLACES, keep all scopes; client id 109317126943210877831);
  (3) **Meet REST API enabled in GCP `espcrm-498315`** (GCP console, not
  Admin — easy to miss). **Deliberately do NOT set `MEET_TRANSCRIPTS=true`
  before the DWD scope exists** — every Scheduled-session save would show
  mentors a "transcription failed" notice. Once Doug confirms Google is done:
  set the flag on web+worker of the crm-test overlay (doctl), then the live
  verification in the handoff doc §Verification (real short Meet → transcript
  in the tab within a poll cycle, Doc link, give-up path, non-admin mentor
  visibility — this run also proves the edit grant + auto-enable). Prod
  follows crm-test verification. 26 new tests (gmeet helpers, retrieval
  cycle, auto-enable hook).

Before that: **v0.82.0** (2026-07-17, 674 tests green) —
**fix: mentors all read "Incomplete — no User assigned to the Contact"**
(Doug's report). Root cause found by live probe: the CRM team's deliberate
switch of **Contact (and Account) to Multiple Assigned Users on BOTH CRMs**
(2026-07-16/17, so co-mentors can be assigned to client contacts) disabled the
single `assignedUser` — reads return null (hiding every stored assignment),
writes silently ignored — while the apps still used only that field on
Contact. Fixes: `check_completeness` + `reconcile_user_links` accept/write
both shapes (contact write MERGES into `assignedUsers`); `Contact` joined
`USES_ASSIGNED_USERS` so Assign re-homes contacts via the merge payload and
Reassign via the swap-merge (previously silent no-ops under the new schema);
and **"Update Mentor Status" now heals the roster** — the sweep runs
`reconcile_user_links` per mentor before recomputing, so one click re-stamps
every Contact from its member's User and flips the drifted Incomplete records
back. 6 new tests. **DEPLOYED + VERIFIED LIVE 2026-07-18** — Doug pushed,
ran Update Mentor Status per the recovery steps, and confirmed the roster
looks good again ("it looks good now!"). Side finds from the probe: one
crm-test contact (Tommy Tranell) carries a value in a custom `cAssignedUser`
field (manual workaround? — suggested clearing it in the CRM UI), and old
single-assignment values are hidden, not migrated, CRM-side.

Before that: **v0.81.0** (2026-07-17, 668 tests green, committed NOT pushed) —
**Client Administration: Reassign Mentor** (Doug's request): select a grid row
(click; right-click also selects) and invoke via the new toolbar button OR the
new **right-click context menu** (View details / Reassign mentor… / Assign
mentor… on unassigned rows / Edit notes / Refresh — covers every row
function). A mentor-picker dialog (current mentor excluded; inline
"Select a mentor first." on empty confirm, per the no-disabled-buttons ruling)
drives **`POST /engagements/{id}/reassign`** → `service.reassign_engagement`:
same eligibility bar as assign; swaps `mentorProfile`; re-stamps
`engagementAssignedDate`; **re-homes access on engagement + contacts +
client profile + company + every CSession** (swap-merge: old mentor's User
removed unless a co-mentor shares it / they personally own the session;
co-mentors always preserved); `engagementStatus` deliberately untouched;
downstream failures per-record best-effort (`reassignmentErrors`); DOC-09
grant re-sync after. **History stamp** (stream note, Doug's exact wording):
"Mentor X was replaced with Mentor Y on MM/DD/YYYY by user NAME." (Cleveland
date) + re-homing outcome. Successful reassign opens the
MentorAssignmentNotice compose for the new mentor (v0.79.0 behavior). 6 new
service tests; full flow verified in the stub harness (guard messages, picker,
reassign → row re-renders + notice + compose, right-click menu on both row
states, Escape/click-away close, details/notes actions; no console errors).
**NOT yet driven live.** Live-check notes: the staff user's role needs
CSession read+edit for the session re-stamp (per-session failures surface in
the notice and stream note, never fatal — watch `reassignmentErrors` on the
first live reassign); Note create needed for the history stamp (best-effort,
logged if rejected).

Before that: **v0.80.0** (2026-07-17, 662 tests green, committed NOT pushed) —
**Client Administration layout pass** (Doug's review of 0.79.0; frontend-only):
"Signed in as" + Sign out moved to a top-right user-profile corner; Review
Mentors/Refresh share ONE control line with the Status filter and a new
live **full-text search** (name/status/client/contact/mentor/notes/dates;
no-match ⇒ "No engagements match your search."); and the Assign button is
**never disabled** — clicking with no mentor chosen shows a notice naming
the missing input and focuses the dropdown. NEW PRODUCT-WIDE RULING recorded
in memory ([[buttons-never-disabled-validate-on-click]]): action buttons stay
active, validate on click; transient in-flight disables remain OK. Verified
in the stub harness (positions, search hit/miss/clear, no-mentor message,
full assign→compose regression; no console errors). Also this session:
**verified `MentorAssignmentNotice` exists on BOTH CRMs** (read-only DB query
via SSH to the droplets — crm-test id `6a5a3d9b938cebbfb` no category, prod
id `6a5a3d7db88566f66` has a category, irrelevant to the record-less
quicksend list; intake API key can't read EmailTemplate → 403, and prod CRM
droplet is `cbm-espocrm-prod` 147.182.135.50, same docker layout as CBM-TEST).

Before that: **v0.79.0** (2026-07-17, 662 tests green, committed NOT pushed) —
**Client Administration engagement grid: full-window layout + Days Assigned +
post-Assign notice email** (Doug's request; frontend-only). (1) The page is a
full-height flex column — the grid fills all remaining vertical space and
scrolls internally with a sticky header (width cap removed per the
no-page-width-caps ruling; `min-height: 12rem` floor, short windows page-scroll
as before). (2) New sortable **Days Assigned** column (Assigned Date ↔ today,
local whole calendar days; unassigned rows "—"; first click = longest-assigned
first). (3) A successful Assign opens the standard quick-compose with To = the
mentor's `cbmEmail` and the EspoCRM **`MentorAssignmentNotice`** template
pre-applied — the shared `frontend/shared/quickmail.js` gained
`composeIfEnabled(email, {template})` + silent template pre-selection (missing
template or failed parse ⇒ blank compose, no error note; app-sending
unavailable ⇒ nothing opens). All three verified in the stubbed-browser
harness (grid fill + sticky header + h-overflow fix (`box-sizing` on
`.assign`), day values/sort, assign → compose with template/signature/
attachment chip, both silent fallbacks; no console errors). **NOT yet driven
live** — needs an EspoCRM template named exactly `MentorAssignmentNotice`
(any/no category — the record-less quicksend list is unfiltered) on
crm-test/prod; without it staff just get the blank compose.

Before that: **v0.78.0** (2026-07-17, 662 tests green, committed NOT pushed) —
**Mentor Sessions grid: accept-in-place + personal email on the mentor
pop-up** (Doug's request). (1) Every `CMentorProfile` peek (grid Assigned
Mentor column, Overview rail) now shows the linked Contact's email as a
**"Personal email"** compose link right after CBM email — best-effort
(`service.peek` + `_mentor_personal_email`; no Contact / forbidden read ⇒
row omitted). (2) A **Pending Acceptance** engagement's Status cell is an
amber two-step accept pill → `POST /records/{id}/accept` moves it to
**Assigned** (declared via `DomainConfig.list_status_accept`, mentor domain
only; server re-reads status first — stale row ⇒ readable 400, nothing
written, frontend reloads the grid; best-effort stream note names the
acting user, v0.74.0 convention; written as the signed-in user). Both flows
verified in the stub harness; **NOT yet driven live** (mentor edits
CEngagement at own via assignedUsers membership, so the write should pass —
same path as the v0.61.0 activation write).

Before that: **v0.77.0** (2026-07-17, 653 tests green, committed NOT pushed) —
**Reliability hardening Phase 1** (the four P0 findings + worker tracebacks
from the 2026-07-17 reliability review; review = `reliability-review-2026-07-17.md`,
phased kickoff prompt = `prompts/reliability-hardening-prompt-v0.1.md`, both
now committed to the repo — **phases 2–6 remain, one per session, per the
prompt**):
- **P0-1** poison payload: worker validation moved inside the classify net
  (ValidationError → permanent → `needs_attention`); new `worker.run_cycle`
  top-level guard — NO exception (store/claim errors included) can kill the
  delivery loop.
- **P0-2** rollback double-delivery: the worker's claim loop is gated on
  `ASYNC_DELIVERY` (flag off = web delivers synchronously, worker doesn't
  claim; monitoring/comms timers keep running; mode banner logged).
- **P0-3** transport errors: all `EspoClient` calls funnel through
  `_request`, which wraps httpx transport failures as
  `EspoTransportError(EspoError)` (op + host in the message, never creds) —
  every `except EspoError` net (router `_crm_failure`, portal
  `refresh_membership` fail-open, assignments per-target accumulation, the
  intake sync path) now covers CRM outages; `worker._is_transient` treats it
  as retryable.
- **P0-4** sessions Details PUT entity allowlist (`cfg.details_entities` +
  Contact, else 404) — closes the Mentor-Team `CMentorProfile edit=all`
  write-proxy bypass.
- Worker permanent failures store a traceback tail in `last_error` +
  `log.exception` — `needs_attention` rows are diagnosable from `/ops`.
- Verified: 653 tests green (13 new: worker poison/transport/gate/guard,
  espo transport wrap, details-PUT allowlist incl. per-domain); DoD drill
  run live against local docker-compose Postgres — poisoned row →
  `needs_attention` with traceback stored, batch-mates delivered, and a
  sync-mode (`ASYNC_DELIVERY=false`) worker left a `pending` row unclaimed.
  Not deployed yet (push per convention).

Before that: **v0.76.2** (2026-07-17, 640 tests green, committed NOT pushed —
three parallel sessions this day: v0.76.0 Phase 3 below, v0.76.1, and the
v0.76.2 template-placeholder fix in the Email-templates bullet).

**v0.76.1 — co-mentor access-review fixes** (this session; a full review of
the CBM-contact add/remove paths across Engagement / Contact / Client
profile / Company): (1) **Client Administration's Assign no longer strips
co-mentor access from the client profile / company** — the re-home wrote
`assignedUsersIds: [<new mentor>]` (overwrite) to CClientProfile + Account;
it now MERGES the record's existing assigned users with the new mentor +
the engagement's co-mentors (`assignments/service._merged_assignment_payload`;
Contacts were never affected — single `assignedUserId` only). (2) **The
co-mentor add/remove stream notes name the acting user in the text**
("… via the session tools by Jane Staff") on every variant — the Note's
author already shows in the stream UI, but not in API reads/exports.
Mechanics in the Assign-action + Co-mentor-visibility bullets. The review
left two edge cases OPEN by design (best-effort domain, same shape as the
DOC-09 nightly reconciliation if ever needed): removing a co-mentor
un-stamps a Contact/Account/profile SHARED with another engagement where
that user is still entitled (protection only spans the one engagement),
and remove skips session/client-record cleanup when the user was already
off the engagement's assigned users (e.g. hand-cleaned in the CRM). Live
checks open: an assign onto records carrying co-mentor stamps (merge
holds), and one add/remove note posting under a non-admin staff role.

Before that: **v0.76.0** (2026-07-17, committed NOT pushed) — **Documents:
CRM integration and lifecycle (DOC-MGMT Phase 3, PRD v1.3) is BUILT**,
closing the PRD's phased plan: Drive access grants + the nightly
reconciliation (DOC-09), Archive/Restore with the "Include archived" toggle
(DOC-07), and the `documentsFolderUrl` CRM write-back (DOC-08,
feature-gated on the CRM field — spec handoff
`documentsfolderurl-crm-field.md`). Doug's rulings this session: archive =
move-first-then-flip with rollback; DOC-08 = self-healing best-effort (no
retry queue); core scope only (OI-02/OI-05/OI-07 all deferred); build now,
activate later. 649 tests green; both UIs stub-harness-verified; mechanics
in the Session Management section's **"Documents — CRM integration and
lifecycle"** bullet. **NOT yet activated/driven live** — prerequisites are
Doug-side and were NOT yet done at session time (verified live via doctl:
`GDRIVE_IDENTITY` is unset on both apps, i.e. both still run the
impersonation mode; the SA's drive membership / human-member removal
unverifiable locally): (1) SA = the shared drive's ONLY member (Content
Manager), all humans removed; (2) THEN `GDRIVE_IDENTITY=service` +
`GDRIVE_DOCS`/`GDRIVE_SHARED_DRIVE_ID` on **web AND worker** of both
overlays (the worker runs the nightly job — order matters, membership
first); (3) the `documentsFolderUrl` field build (crm-test then prod);
(4) the Phase 3 live checklist — all step-by-step in
**`GDRIVE-DOCS-SETUP.md` Task 6**. The overlays were deliberately NOT
edited (applying identity=service before the membership swap would break
uploads).

Also this day (its own session): **v0.72.0 + v0.75.1 — sortable +
resizable grids on the record detail** (both committed; stub-harness
verified, and **Doug tested both grids live 2026-07-17 — working well**;
arc closed). The **Sessions tab grid** (v0.72.0) and
the **Communications conversation list** (v0.75.1) share one treatment:
every header sorts (Client-Administration interaction — first click sorts,
dates newest-first, second reverses, ▲/▼ + `aria-sort`), columns resize by
dragging a grip on each header's right edge (`makeColumnsResizable` in
`sessions/frontend/app.js` — first drag freezes widths via
`table-layout: fixed`; widths live on the `th`s so they survive re-renders,
and the comms head is now built once per record page so widths + sort
survive tab revisits). The Sessions grid gained a **Participants** column
(widest by default, 28%) — `get_detail` mirrors the note feed's attendee
names onto the session rows (`participants`), zero extra CRM calls; comms
Participants defaults to 26%. Version-race note (both times): the `app.js`
half was swept into the parallel session's release commits (e01d4cd →
completed by d8bb389; 068f44d → completed by 0f0d758) — HEAD is coherent
at/after each completing commit.

Before that: **v0.75.1** (2026-07-17; 0.75.1 = a parallel session's
conversation-grid sortable/resizable columns — the entry above). **This session's arc (v0.67.0 + v0.75.0) is
COMPLETE — the full Email Template integration (ET) + email signatures,
committed NOT pushed:**

**v0.75.0 — email signatures in every compose dialog** (600 tests green at
commit): new messages open with the
user's **EspoCRM `Preferences.signature`** seeded at the bottom of the body
(rides `GET /mailbox`; `comms/service.user_signature`, sanitized,
best-effort); applying a template re-appends it below the rendered draft;
an untouched seeded signature counts as an EMPTY draft (no replace-prompt,
quick-compose's "write a message" guard still fires); **My Mentor Profile
gains an "Email signature" panel** (own Save, above Internal CRM
description; `GET/PUT /mentorprofile/api/signature` — users write their own
Preferences, no grant work; non-mentor staff author theirs in EspoCRM →
Preferences → Email Signature). Doug's rulings 2026-07-16 (source /
auto-insert / re-append / edit-in-profile — all the recommended options).
Verified in the stub harness (all three surfaces); 12 new tests. Doug added
the Partner/Sponsor Manager EmailTemplate + Email grants on crm-test
2026-07-17 (`emailtemplate-et-crm-prereqs.md` §1 ✅; replicate on prod at
prod verification), so the whole ET+signature arc is live-testable now.
**Remaining = one live pass on crm-test** (all harness/test-verified, none
driven against the real CRM/Gmail yet): (1) author a real template in
EspoCRM (crm-test has only "Case-to-Email auto-reply"; ideally one with a
standing attachment) + optionally categories named
Engagement/Partner/Sponsor for the picker filter; (2) set a signature in
/mentorprofile → compose on an engagement → signature seeded → apply the
template → placeholders resolved, signature re-appended below, chips
present; (3) send with an attachment → arrives via Gmail AND a native
EspoCRM Email record lands in the recipient Contact's History panel
attributed to the sender; (4) same quick spot-check from the quick-compose
(assignments grid) and as a partner/sponsor manager.

Before that: **v0.74.0** (2026-07-16/17; 595 tests green;
committed, push per convention) — **the double-assignment forensics session**,
three deliverables:
1. **v0.72.1 — stale-assign guard.** Client Administration's Assign re-reads
   the engagement before any write and 400s (nothing written) if it already
   has a mentor or is no longer `Submitted`; the frontend reloads the grid on
   any Assign 400. (Mechanics in the Assign-action bullet.)
2. **Forensics conclusion (prod eng `6a4955b75f19ff03a`, Laura Wiegand):**
   the Sharon→Robert mentor swap was NOT a second app assignment — Sharon
   Rose edited the record directly in the CRM UI 2026-07-10 (added Robert to
   Assigned Users, no status change/date stamp/re-homing; `additionalMentors`
   empty; `engagementAssignedDate` null). Key lesson: app writes run as the
   signed-in user, so they are INDISTINGUISHABLE in Espo history from hand
   edits by that user, and `mentorProfile` is not audited (no stream entry
   when it changes). Doug manually re-homed the contact as Admin; Sharon may
   still be in the engagement/client-profile assignedUsers if not cleaned up.
3. **v0.74.0 — stream-note audit trail + co-mentor client-record access
   (Doug's defect report).** `core/stream.post_stream_note` (best-effort
   Note type=Post) now stamps every app Assign and co-mentor add/remove into
   the engagement's history, naming the app and the outcome; and
   `add_comentor`/`remove_comentor` stamp/un-stamp the co-mentor's User on
   the engagement's client records (contacts / client profile / company with
   linkedCompany fallback) — previously engagement-only, so the co-mentor
   couldn't see the client's records. Mechanics in the Assign-action and
   Co-mentor-visibility bullets. **Open (live checks):** (a) first live
   assign / co-mentor add should confirm the stream note actually posts
   under a non-admin staff role (Note create + stream access; failure is
   logged, never blocking); (b) crm-test parity: Contact needs "Multiple
   Assigned Users" enabled (Doug enabled it on PROD 2026-07-16 — without it
   the contact stamp is silently ignored).

**The comms/permissions session (2026-07-15/16, ran parallel to the ones
below; its version numbers interleave):** three arcs, all committed (the
first two also deployed + verified along the way):
1. **Conversation participants = everyone on the email (v0.55.0/e46756e),
   BACKFILLED on BOTH CRMs 2026-07-16.** The Gmail sync folds From + To + Cc
   into `CConversation.participants` as `Name <address>` entries **deduped
   by email address** (fixes the name-vs-address duplicate; bare/legacy
   entries self-upgrade); the dedup/replay path also merges, so the one-shot
   `GMAIL_RESYNC=true` re-drive doubles as the backfill — run + GET-verified
   on crm-test (7 conversations, incl. the bare-address-first edge that
   e46756e fixed) and run on prod (1,202 fetched / 0 errors; verified by the
   idempotent second pass needing ZERO participant writes). Flags removed
   from both overlays afterward. **Ops gotcha:** while GMAIL_RESYNC is set,
   EVERY push/deploy re-clears cursors and re-reads all mailboxes — remove it
   immediately; superseded deployments' logs are unretrievable.
   **RESOLVED 2026-07-17:** the 8 skipped robert.cohen prod messages —
   prod's `CCommunication.toAddresses`/`ccAddresses` had been built at 255
   vs crm-test's varchar(500); Doug widened them to 500 and the one-shot
   recovery resync ran clean (8 mailboxes, 1,214 fetched / 1,101 stored /
   0 sync errors — all 7 maxLength failures gone; flag removed after).
   **Remaining, deliberately unfixed:** ONE message (gmail id
   `19f298a147e3ba38`) still rejects — its subject trips
   `CConversation.name`'s `$noBadCharacters` pattern (the pattern exists on
   BOTH CRMs). Fix would be app-side subject sanitizing on conversation
   create, if ever worth it (memory:
   [[prod-ccommunication-field-length-drift]]).
2. **Every email address shown in the staff UIs is a compose link
   (v0.64.0 + v0.64.2 grid-peek fix).** Product rule (Doug's ruling
   2026-07-16): no bare `mailto:` — clicking a shown address opens a compose
   dialog. Session-tool RECORD pages reuse the record-scoped compose
   (pre-filled To; contact add/create routing applies); everywhere else —
   Client/Mentor Administration and the session GRID-page peeks — uses the
   shared **quickmail widget** (`frontend/shared/quickmail.js`) backed by
   `GET /mailbox` + `POST /sendmail` per app (`comms/quicksend.py`,
   registered on assignments/mentoradmin/all three session routers; sends as
   the signed-in user's own `cbmEmail`, no record link — the sync ingests the
   sent copy). Links keep real `mailto:` hrefs and fall back to the browser
   handler when sending isn't available (GMAIL_SYNC off, no CBM mailbox).
   v0.64.2 lesson: a peek from the LIST page has no `currentDetail` — the
   original wiring silently fell back to mailto (= "nothing happens" with no
   desktop mail handler); both paths are stub-harness-verified. The
   email-templates work (v0.67.0, parallel session) builds on this widget.
3. **Permission failures name the exact missing grant (v0.68.1).**
   `core.espo.forbidden_hint` parses the denied operation from the EspoError
   prefix → 403s read "your CRM role is missing read access to
   CClientProfile records — ask CBM staff to grant it" (relate/unrelate
   correctly report as EDIT on the linked records). Wired into sessions,
   mentorprofile, assignments, mentoradmin `_crm_failure` (the staff tools
   previously surfaced CRM 403s as raw 502s). Root cause of Doug's "Could
   not load details: …no permission" reports ALSO fixed: the Details tab's
   Company/profile card reads weren't 403-tolerant, so ONE missing read
   grant killed the whole tab — restricted cards now render with a note
   naming the entity (`sessions/details.py`, matching the peeks' tolerance),
   and a forbidden contacts read degrades the same way.

**The edit-form/UX session (2026-07-15/16, v0.57.0–0.59.2 + 0.62.0–0.64.1,
all pushed/deployed along the way):** the Details EDIT forms were rebuilt to
the mockup-v4 standard — full-width **packed group panels** (Doug REVERSED
prompt v0.2's 960px cap live: "utilize as much of the screen as possible";
the prompt doc is at rev 0.3, and the memory
[[no-page-width-caps-density-by-packing]] now says spec'd width caps must be
flagged before implementing), complete **field triage** for Account /
CClientProfile / CEngagement (`noExtras` — no more "Additional details"
dump; excluded fields in `DETAILS_REMOVED_FIELDS`), gold changed-field dots
+ a sticky Save bar, and uniform 2.4rem control heights (v0.59.2). Then the
session grid/Overview got temporal flags (v0.62.0–0.64.1): Upcoming/Past
sections always render (the Randa Jackson report), red bold TODAY treatment
(cards, session view, grid row), the Next Session column derived from real
sessions (the stored `CEngagement.nextSessionDateTime` is NEVER populated —
don't read it), and the Assigned Mentor column → mentor peek with a
clickable CBM email. Mechanics in the Session Management section's two new
bullets ("Details EDIT forms — mockup-v4" and "Grid + Overview session
flags"). Still worth a live eyeball on crm-test: a past-only record's
Overview split, a real today-session red flag, and Next Session values.

**Main is at v0.73.0** (2026-07-16, committed NOT pushed) — **Documents:
Download action** (Doug's report: the viewer's PDF rendering is what the
browser's PDF-viewer download saves — he expected the xlsx with formulas;
and convert-on-view is slow when the goal is the file itself). Every
document row + the viewer header now offer **Download** / **"Download
original"**: the stored file's exact bytes via `?original=true` on the
content proxy (attachment disposition, no conversion, no delay); the user
opens it in the locally installed app — the closest a browser gets to
"open in Excel" (it cannot launch local apps; `ms-excel:` URI schemes
can't authenticate to our session-cookie proxy). Google-native files
download as their Office equivalent (Sheets→.xlsx, Docs→.docx,
Slides→.pptx; `GOOGLE_NATIVE_DOWNLOADS` + `DriveClient.export_file`).
590 tests green; harness-verified. (v0.72.0/0.72.1 were parallel
sessions: sessions-grid sorting/resizing + the assignments stale-assign
guard.)

**ACCESS MODEL RULED + DOCUMENTED (Doug, 2026-07-16/17 — the former "Open
in Drive fate" ruling is RESOLVED as option 4; AMENDED 2026-07-17, PRD
v1.5: the two designated system administrators — doug.bower@,
allen.ingram@ — retain drive membership for maintenance/review; "no
person" reads with that single named exception):** no OTHER person is
ever a member of the CBM Documents shared drive (service account = the
operational member; all app Drive ops run as it); all Drive ops run
as the SA (`GDRIVE_IDENTITY=service`); Drive-side access = per-person
**folder-level COMMENTER grants** mirroring CRM assignments (engagement
folders → assigned mentor + co-mentors; partner/sponsor folders → their
manager; **`Mentors/` personnel folders → NO ONE, app-only**), revoked by
the same app actions that end the entitlement + a **nightly
reconciliation** re-deriving grants from the CRM; Commenter = read/
download/comment only, so uploads can never bypass the app's index. Open
in Drive STAYS (works for grant-holders). **Both governing docs revised
to v1.3** (`prompts/Google Drive Documents/` PRD — §3.4 rewritten, D-01
superseded, new D-08/D-09, DOC-09 = Drive Access Grants, OI-04
superseded/OI-05 largely closed/OI-07 new copy-hardening question; Exec
Summary — §1.2 "The Access Model, Precisely" + §1.3 Anticipated Questions
for the confidentiality audience). **Both docs bumped to v1.4 2026-07-17**
(Phase 3 implemented; the PRD records the session's decided contracts —
DOC-07 move-first-with-rollback, DOC-08 self-healing/no queue, Phase 3
marked implemented; the Exec Summary notes no contract change), and the
formerly-stale `prds/CBM-DocMgmt-Executive-Summary.docx` copy is now
SYNCED to the prompts/ v1.4. The grants build SHIPPED in v0.76.0 (see
the v0.76.0 Current-status block; activation pending).

Before that: **v0.71.0** — **Documents:
service-account identity + in-app Office viewing** (Doug's rulings: users
must NOT have Drive access — drive membership was never granted broadly,
so the PRD's impersonate-the-manager model only ever worked for actual
members like Doug; and Office files must view in-app). New
**`GDRIVE_IDENTITY=service`** (default `user` = old behavior): the SA
performs all Drive ops as ITSELF — **activation: add the SA's
`client_email` as a Content Manager member of the shared drive, set the
env on web** — managers need zero Drive access, the app's CRM ACL is the
sole gate, `uploaded_by` still records the person, and a missing
`cbmEmail` no longer blocks (it was only the impersonation subject).
Office formats (docx/xlsx/pptx/ODF/CSV) now view in-app via
**convert-on-view** (`DriveClient.export_office_pdf`: copy-as-Google-
format temp → export PDF → temp deleted even on failure; stored file
untouched, D-04 holds; temp briefly visible in the record folder — users
aren't members so nobody sees it). 584 tests green; harness-verified.
**OPEN RULING: Open in Drive's fate** — under service mode the button
only works for drive members (nobody): remove it (option 2, app-only)
vs. per-user ADDITIVE grants on record folders (option 4 — non-members
CAN be granted per-file/folder access, the one direction shared drives
support; costs a permission-sync liability wired to assignment changes).
Note: this pivot reverses PRD D-01/DOC-05/§3.1 — PRD revision needed
once ruled. Doug also wants the viewer proven "fast and reliable" live
before accepting Phase 2.

Before that: **v0.70.1** — **document
upload failure UX hardened** after Doug's live report (a pptx upload
failed with no visible error; unreproducible post-hoc — the v0.70.0 deploy
had rotated the instance/logs, and an in-flight upload dying in that swap
is the probable cause; ALSO plausible: he was uploading as a non-member
identity under the impersonation model, which 403s — see v0.71.0): errors
now show in the notice bar above the table,
XHR upload with live progress %, client-side size gate against the
server's `maxFileMb` (new on the documents list/refresh responses), a
plain-language dropped-connection message, and an INFO receipt log
(who/filename/bytes) on every upload so the next report is diagnosable
from run logs. Probed: the DO edge accepts ≥60 MB bodies (no platform
size wall before the 100 MB app cap). All harness-verified.
v0.70.0 (pushed + deployed, both envs verified at 0.70.0): **Documents:
in-app viewing (DOC-MGMT Phase 2) is BUILT**: View on every document row
(session tools + `/mentoradmin`) opens an in-app overlay streaming the file
through a new ACL-gated proxy endpoint (PDF/image/text render natively;
Google Docs/Sheets/Slides arrive as exported PDF; docx/xlsx fall back to
Open in Drive with a clear message); caching is **browser-side**
(immutable responses on modifiedTime-versioned URLs — Doug's ruling, no
server cache) and the tab lazily re-syncs modifiedTimes from Drive on open,
flagging rows edited in Drive ("Updated in Drive" tag). Mechanics in the
Session Management section's Documents-tab bullet; 580 tests green (17
new); both UIs verified in the stub harness. **NOT yet driven against the
real shared drive** — after deploy, run `GDRIVE-DOCS-SETUP.md` Task 5
item 6 (view a PDF + an image + a Google-native doc, confirm the
Updated-in-Drive flag after editing a file in Drive, and instant re-views
via the browser cache). No new env vars/migration — Phase 2 rides the
Phase 1 flags. Archive + CRM write-back remain Phase 3 (kickoff prompt
drafted: `prompts/Google Drive Documents/prompt-docmgmt-phase3.md`).

Before that: **v0.68.0** (this session; committed, push per convention) —
**Documents: PRD v1.2 alignment**: engagement Drive folders nest under
their client (D-07, client resolved at upload time), top-level folders are
configurable display labels (Mentors/Clients/Partners/Sponsors),
`client_record_id` added to `app_document` (Alembic 0006), and **Mentor
Administration gains a Documents tab** anchored to the mentor's linked
Contact (Doug's ruling; partner/sponsor tabs kept under their own labels).
Full mechanics in the Session Management section's **"Documents — PRD v1.2
alignment"** bullet; activation runbook `GDRIVE-DOCS-SETUP.md` (folder tree
updated there). **ACTIVATION 2026-07-16 — BOTH ENVS FLAGGED:** Doug created
the "CBM Documents" shared drive (`GDRIVE_SHARED_DRIVE_ID=0AE50yNppMh_hUk9PVA`);
`GDRIVE_DOCS=true` + the drive id are on the **web** component of BOTH
overlays (`.do/app.prod.yaml` crm-test, `.do/app.prod-crm.yaml` prod — each
regenerated from its live spec + applied via doctl), and main is pushed at
9009c5b (v0.68.1 — the nested folder scheme + migration 0006 deploy with
it). **FIRST LIVE UPLOAD SUCCEEDED (Doug, prod, 2026-07-16)** — so the
whole chain is proven: Drive API + `auth/drive` DWD scope + shared-drive
membership + delegated upload as the signed-in manager + metadata row.
(Earlier same-day non-failure: he'd uploaded on prod BEFORE it was flagged
→ the app's 503 "integration isn't enabled" surfaced as an edge 504 —
known masking.) Light smoke items still unchecked: the file's Drive
location eyeballed (`Clients/{client}/{engagement}/`), folder REUSE on a
second upload, and a mentor-side upload via `/mentoradmin` → `Mentors/`.
The disabled View/Archive buttons are BY DESIGN (Phase 2/3 — Doug hit
"coming soon" post-upload; Phase 2 = viewing is the next build, kickoff
draft `prompts/Google Drive Documents/prompt-docmgmt-phase2.md`).
**"Open in Drive" went LIVE v0.69.0** (DOC-05 pulled forward, Doug's call —
frontend-only, opens the stored `webViewLink` new-tab/noopener in both the
session tools and `/mentoradmin`; linkless rows stay disabled).
Open UI question: how his flag-off prod page showed an Upload button at
all (served app.js gates correctly; suspect a stale tab).

Before that: **v0.67.0** (549 tests green, committed NOT pushed) — **Email
templates in every compose dialog (ET)**: template picker + EspoCRM
server-side rendering + template/local attachments + native Email-record
write-back with retry, in the record compose AND the shared quick-compose.
Mechanics, verified EspoCRM 9.x parse contract, and the CRM handoff
(Partner/Sponsor Manager role grants; the domain filter rides the NATIVE
template categories — EmailTemplate is not Entity-Manager-customizable) are
in the Session Management section's **"Email templates in every
compose"** bullet + `emailtemplate-et-crm-prereqs.md`. Verified in the stub
harness end-to-end; NOT yet driven live (mentor domain is live-testable
immediately — Mentor Role already has the grants). PRD AC walkthrough in the
session close-out (AC-1..8: all pass in-harness/tests except the live paths).

Before that: **v0.66.0** (526 tests green) —
**Communications: conversation messages show WHO WROTE THEM** (Doug's
report: outbound messages displayed "To: <address>", so a mentor +
co-mentor sending on the same engagement were indistinguishable). Two
parts: (1) frontend — the conversation view leads every message with the
sender's name/address for BOTH directions, outbound keeping recipients
after an arrow ("Doug Bower → james@acme.test"); the data was already in
the payload. (2) `core/gmail.build_mime` gains `sender_name`, passed by
both send paths (record compose = the signed-in user's name; quick-compose
via `comms/quicksend.py`) so app-sent mail's write-through ingest stores a
human-readable `fromName` — previously a bare address, which would have
made app-sent messages show as addresses forever. Pre-existing stored
messages keep their bare address (still identifies the person). NOT yet
eyeballed live. Same session earlier: closed the "first live SEND" open
item (Doug confirmed the Sent copy in the @cbmentors.org mailbox — FAQ row
added to communications-tab.md, since every mentor will ask where their
sent mail went).

Before that, parallel sessions the same day (see CHANGELOG for
0.62.0–0.64.x: Upcoming/Past session sections + today-flags, Next Session
column from real sessions + Assigned Mentor grid column, email-address
click-to-compose): **v0.65.0 — Documents tab: Google Drive
document management, DOC-MGMT Phase 1** (committed, push per
convention): the session tools' Documents placeholder is now a real tab —
upload to the "CBM Documents" shared drive + per-record list from the new
`app_document` Postgres table (Alembic 0005). Gated OFF by `GDRIVE_DOCS`;
mechanics, adaptations from the PRD's desktop framing (Doug's rulings:
this repo, SA+DWD auth), and the activation checklist are in the Session
Management section's **Documents tab** bullet + DEPLOYMENT.md. 523 tests
green. NOT yet driven against real Google Drive (shared drive + `drive`
DWD scope are manual prerequisites). Phase 2 (viewing) not built — kickoff
prompt drafted at `prompts/Google Drive Documents/prompt-docmgmt-phase2.md`.

Before that (a parallel session the same day): **v0.61.0 — Mentor
Sessions: the first completed session activates the engagement** (committed;
push per convention): saving a session as **Completed** (create, or an edit
that changes status to Completed) on an engagement whose `engagementStatus`
is **Assigned** or **Assignment Dormant** moves the engagement to
**Active**. Mechanics, guards, and the best-effort contract are documented
in the Session Management tools section (the "First completed session
activates the engagement" bullet). 483 tests green at commit (8 new). NOT
yet driven live (verify as a mentor: complete a session on an Assigned
engagement → status flips to Active in the grid/badge; the mentor's role
edits CEngagement at own via assignedUsers membership, so the write should
pass). Versions v0.56.0–v0.60.0 (gcal pre-save prompt, edit-panel polish,
comms rich-text compose) also shipped in parallel sessions — see CHANGELOG.

Before that: **Main was at v0.55.1** — two items on top of the parallel session's v0.55.0
(comms participants, committed):
1. **Details-tab live write-through VERIFIED on crm-test as a non-admin
   mentor (matt.mentor)** — closes section-edit-screens acceptance
   criterion 6 / the v0.41.x "drive the Details writes live" open item.
   Engagement strip enum, profile bool, and contact-row edit all saved
   through the UI, GET-verified fresh from the CRM, and reverted. ACL
   gating confirmed live (Account `editable:false` ⇒ no Edit button; Mentor
   field read-only). **CRM gaps found, Doug to decide:** Mentor Role has no
   Contact CREATE grant, and relate-existing needs edit on the foreign
   contact ([[espo-field-acl-silently-strips-writes]] family) — so both
   "+ Add contact" flows 403 for mentors today.
2. **v0.55.1 fix:** those CRM 403s surfaced as blank "Request failed (504)"
   — `sessions/router._crm_failure` now maps CRM 403 → readable HTTP 403
   ("your account doesn't have permission… ask CBM staff"); CRM 5xx still
   → 502. **Pushed and DEPLOYED 2026-07-15** — prod + crm-test `/healthz`
   both verified at 0.55.1.

Before that: **Main was at v0.54.0** (464 tests green, **pushed and DEPLOYED 2026-07-15** —
prod + crm-test `/healthz` both verified at 0.54.0, and both deployed portal
pages serve the new link) — **"Forgot your password?" on the portal sign-in** (the single login for all staff
apps): a link under the login form opens a reset form (username + email);
`POST /api/portal/forgot-password` (`assignments/auth.py:
request_password_reset`) proxies EspoCRM's own unauthenticated
`User/passwordChangeRequest` endpoint — the CRM matches the account,
throttles repeats, and emails its standard recovery link (the CRM's
change-password screen; the app never sees or sets a password). Exact
readable errors (not-found / disabled-or-throttled 403 / CRM unreachable).
Recovery is probe-verified ENABLED on both crm-test and prod (bogus-user
request → 404, not the disabled 403); the 404 path was driven end-to-end
through a local app boot against crm-test. Success-path email delivery not
yet verified live (needs a real user's reset — trivial for Doug to try
post-deploy). Also: portal login error/success styles now local to
`portal/styles.css` (`.form-error` only existed in wizard.css, which the
portal doesn't load — the login error was unstyled).

Before that: **v0.53.0** (458 tests green, **pushed and DEPLOYED 2026-07-15** —
prod + crm-test `/healthz` both verified at 0.53.0; this push also carried
the parallel session's unpushed v0.51.0/v0.52.0 co-mentor-visibility work
live) — **CBMRichText (Jodit) rolled out to ALL wysiwyg
fields** (Doug approved the v0.50.0 POC): `/mentoradmin` Bio tab +
`/mentorprofile` (About/bio/why-mentor, live website preview via the
component's `onInput` hook — Jodit toolbar actions fire no native bubbling
`input`) now use the shared editor; sessions had it since 0.50.0. Legacy
contenteditable kept only as a script-load fallback in each app. Verified in
stubbed-browser harnesses for BOTH apps (editors render with CRM HTML,
snapshots stable, untouched save = no/empty changes, edit sends only the
changed field, preview live-updates; no console errors). Live CRM round-trip
(save → view in EspoCRM UI) still worth an eyeball. Before that: **v0.52.0** (458 tests green) — **co-mentors
see ALL sessions on the engagement** (Doug's follow-up ruling to 0.51.0):
`CSession` read=own means a session is visible only to the users stamped on
it, so (mentor domain only) `create_session` now stamps the engagement's
WHOLE mentor team (creator + assigned mentor + co-mentors) into the session's
`assignedUsers`; `add_comentor` backfills the new co-mentor's User onto the
engagement's existing sessions (per-session best-effort — under edit=own the
acting mentor can only stamp sessions they own, others logged + skipped);
`remove_comentor` un-stamps them except from sessions they personally own.
This supersedes the old "pre-existing sessions stay invisible" caveat for
engagements managed through this tool; sessions created before 0.52.0 by
OTHER mentors get stamped when a co-mentor is next added (to the extent the
acting mentor owns them). NOT yet driven live.

Before that: **v0.51.0** (453 tests green, committed NOT pushed) — **co-mentor
engagement visibility**: a CBM contact added to an engagement (Details tab →
CBM Contacts + Add) now actually sees that engagement in `/mentorsessions`.
Doug's report; root causes verified live against the crm-test CRM (roles read
via the admin service account; prod metadata identical, prod role scope
unverifiable locally — its admin creds are encrypted in the overlay). Three
fixes (mechanics in the "Co-mentor visibility" bullet of the Session
Management section): (1) the mentor list reads BOTH `CMentorProfile` reverse
links — `engagements1` (assigned) + **`engagements`** (reverse of
`additionalMentors`) — merged/deduped (`DomainConfig.manager_comentor_link`);
(2) `add_comentor` also stamps the co-mentor's login User into
`CEngagement.assignedUsers` — Mentor Role reads CEngagement at **own** =
assignedUsers membership (assignedUser is disabled), and its
`assignmentPermission=team` lets a mentor assign a fellow Mentor Team member;
best-effort with a readable warning (no linked User / write rejected), and
`remove_comentor` un-stamps unless the assigned mentor or a remaining
co-mentor shares the User; (3) Client Administration's `assign_engagement`
now MERGES current co-mentors' Users into its `assignedUsersIds` write
(it used to overwrite with just the new mentor, silently revoking co-mentor
access on reassignment). **NOT yet driven live** — verify: as mentor A add
mentor B as CBM contact → the engagement appears in B's list; a session
created by A on that engagement is still invisible to B (CSession read=own,
the documented pre-existing-sessions ACL question — CRM-side decision).

Before that: **v0.50.0** (445 tests green, **pushed and DEPLOYED 2026-07-15** —
prod + crm-test `/healthz` both verified at 0.50.0) — **standard rich-text
editor POC on the session tools**: wysiwyg fields (session editor + Details tab)
now render through the new shared **CBMRichText** component
(`frontend/shared/richtext.js`) wrapping **vendored Jodit 4.13.3** (MIT,
`frontend/shared/vendor/jodit/` — chosen over CKEditor 5/TinyMCE 7, both
GPL-or-commercial; Jodit edits HTML in place so CRM/Summernote content
survives round-trips). Sanitizes on load AND read; getValue() is
snapshot-stable for untouched editors (gesture-gated against Jodit's async
`<b>`→`<strong>` normalization — without this every clean open read as
dirty). Verified in the stubbed-browser harness (formatted CRM HTML loads,
clean back = no unsaved prompt, PUT carries only the changed field with
on* attrs stripped, empty editor saves as `""`); not yet driven against the
live CRM (Doug to eyeball the feel on crm-test/prod).
**New convention (see Conventions): ALL wysiwyg fields product-wide use
CBMRichText**; migrating mentoradmin + mentorprofile (and the EspoCRM-side
save round-trip check) is the follow-up once Doug approves the feel.

Before that: **v0.49.0** (445 tests green, **pushed and DEPLOYED 2026-07-15** —
prod + crm-test `/healthz` both verified at 0.49.0) — **Client
Administration: column sorting on the engagements grid**: all four headers
(Engagement / Assign to mentor / Assigned Date / Notes) clickable, first
click sorts (text A→Z, Assigned Date newest-first), second reverses, ▲/▼ +
`aria-sort` on the active column (same interaction as Review Mentors).
Client-side over the loaded rows, persists across Refresh/post-assign
reloads; verified in the stubbed-browser harness. Doug eyeballed the
v0.48.0 Assigned Date column live and approved. Before that: **v0.48.0** —
**Assigned Date column on the engagements grid**, between
"Assign to mentor" and Notes: when the mentor was assigned
(`CEngagement.engagementAssignedDate`, the stamp the Assign action writes
since v0.27.0; UTC stamp shown as the local calendar date). Unassigned rows
and pre-0.27.0 assignments (no stamp) show "—". `list_engagements` selects +
returns `assignedDate`; no new grant (the metrics sweep already reads the
field as the signed-in user). NOT yet eyeballed live.

Before that: **v0.47.0** — two items:
1. **Mentor Administration: LinkedIn on the Profile tab.** The detail
   editor's Profile tab gains a "LinkedIn profile" input; the value lives on
   the linked Contact's `cLinkedInProfile` (same field `/mentorprofile` + the
   public website use), declared in `EDITABLE_FIELDS` with `group: "Profile"`
   + `entity: "Contact"` so it displays on the Profile tab but routes through
   the existing Contact-save path (no-linked-Contact 400 before any write).
   Standard live-ACL watch: a 200 save that doesn't stick = field-level ACL
   strip on Contact ([[espo-field-acl-silently-strips-writes]]).
2. **Google Calendar events ACTIVATED + VERIFIED LIVE ON PROD.** Doug
   reported "no event created" for a Scheduled mentor session — diagnosis:
   he was testing on prod, where the hook was deliberately inert. Doug built
   `CSession.googleCalendarEventId` on the prod CRM; `GCAL_EVENTS=true` was
   added to the prod overlay's **web** component (`.do/app.prod-crm.yaml`,
   applied via doctl 2026-07-15). Doug then created a Scheduled session on
   prod and **it worked perfectly** (event + Meet link end-to-end). Still to
   drive live (both envs): the edit→patch and Cancel→cancel-event paths, and
   attendee-invitation delivery.

Before that: **v0.46.0–.46.2** (443 tests green, pushed and deployed
2026-07-15; 0.46.1 = compose shows the From address, 0.46.2 = Sessions tab's
CBM Contacts panel removed) — the 0.46.0 headline:
**Communications compose defaults to ALL record contacts as To recipients**:
the session tools' compose dialog now renders every record contact with an
email address as a checked checkbox (uncheck to leave someone off), plus an
"Other recipients" free-entry field that still routes through the existing
unknown-recipient add/create router; Reply pre-checks only the address(es)
being replied to; contacts without an email are omitted; Send requires ≥1
recipient (frontend-only — `sessions/frontend/app.js` `composeMessage` +
`recipientList()`, new `.sx__to-list` CSS). Verified in the stubbed-browser
harness (defaults all-checked, deselect drops from the send payload,
zero-recipient guard, mixed known+unknown send through the create-contact
row, reply pre-check; no console errors). NOT yet driven against live Gmail
send. Before that: **v0.45.5** (pushed + deployed to crm-test AND
prod; **Doug verified v0.45.5 on prod 2026-07-14** — arc closed). The 2026-07-14 **My Mentor Profile** arc is COMPLETE and live on both
environments: v0.42.0 built the tool, v0.42.1 made the preview a verbatim
copy of the live website page + the feature-gated `mentorSummary`, v0.43.0
first deploy + full live verification on crm-test (incl. finding/deleting the
crm-test Mentor Role's 59-field lockdown — see the tool section), v0.45.0
Doug's layout/field pass (prominent green/amber status toggles top-right,
Personal details panel with Contact `cBirthday`/`cSpouseName`, mentor-editable
`maximumClientCapacity`, Internal CRM description at the bottom, "Mentoring
since" badge), v0.45.2–.45.5 badge placement (final: photo, badge, and
toggles share ONE top row, badge top-centered between them) + footer parity ("All rights reserved. · vX (Test)").
Prod smoke test passed (Doug's prod profile carries tool-written data). Full
detail: the "My Mentor Profile tool" section + CHANGELOG. (0.45.1 =
assignments Internal Notes; 0.45.3 skipped — version race between parallel
sessions.)

**Gmail Communications went LIVE IN PRODUCTION 2026-07-14** — first backfill
pass clean (7 mailboxes, 1177 fetched, 1061 stored, 0 errors → 521
conversations / 1063 messages in the prod CRM). Full activation record in the
Communications bullet below. **Owner-stamp fix COMPLETE on both CRMs
2026-07-15** (User Read=all + Assignment Permission=all on the API role —
guide §2.4 steps 5–6; prod 516/542 stamped via one-shot resync, crm-test 6/6;
both CRMs' API user now carries the identically-named **CustomAppAPIRole**).
Security review CLOSED with Doug's rulings (2026-07-15): **Mentor Role keeps
CMentorProfile edit=all — REQUIRED for co-mentor linking (additionalMentors
relate); never re-flag it**; Mentor Role's CConversation/CCommunication
read=all accepted (full tightening would first need app-side message
owner-stamping — offered, not requested); Standard User Email read=all +
export accepted (its Email EDIT was tightened to own). ✅ **First live SEND
from the tab CONFIRMED 2026-07-16** — Doug sent a real message and found the
copy in Gmail's Sent folder. Gotcha that cost the confirmation a detour:
the tab sends as the manager's `@cbmentors.org` mailbox, so the Sent copy
is in THAT account — checking a personal/other account's Sent folder shows
nothing (now a FAQ row in `communications-tab.md`). Still open: deleting
the 4 `ZZTEST-GMAILPROD*` probe records in the prod CRM UI (steps given
2026-07-15: `#CCommunication` then `#CConversation`, search ZZTEST,
Actions → Remove).

**Main is at v0.44.0** (442 tests green, committed NOT pushed) —
**Client Administration gains a click-to-edit Notes column** (new RIGHTMOST
column on the engagements grid — Doug corrected the initial leftmost
placement): clicking a cell opens an inline editor
(Save/Cancel, Escape cancels); notes store in **`CEngagement.description`**
via `PUT /assignments/api/engagements/{id}/notes`
(`assignments/service.update_engagement_notes`), written as the signed-in
user. **Staff-internal by design:** `description` surfaces in NO other UI —
the session tools' metadata-driven Details tab now excludes it for
CEngagement on both render and save (`sessions/details.py:_ENTITY_EXCLUDED`).
Two side facts: the intake orchestrator's enum-drift follow-up note also
lands in `description`, so it shows in the Notes column (by design — triage
material; an edit replaces it); and the v0.43.0 release commit (a PARALLEL
session's `/mentorprofile` deploy marker, pushed mid-session) accidentally
swept this feature's changelog entry into its release — fixed by renumbering
the entry to 0.44.0, where the code actually ships. Verified in the stubbed-
browser harness (column renders for assigned + unassigned rows, edit → PUT →
re-render incl. multi-line, Escape/Cancel revert without a PUT, stubbed-502
save shows the error notice and keeps the editor open with text preserved,
empty save clears back to the "Add notes…" placeholder; no console errors);
service+router covered by tests. NOT yet driven against the live CRM
(standard grant note: the staff user's role needs `description` readable +
writable on CEngagement). Before that: **v0.43.0** — the parallel session's
release marker (first `/mentorprofile` deploy; `mentorSummary` built on
crm-test so the gated summary box activates there; prod still lacks the
three fields). Base: **v0.42.1 — My Mentor Profile
(`/mentorprofile`)**, a Mentor-Team self-service screen: a mentor edits their
own `CMentorProfile` + linked Contact with a live preview that is an **exact
copy of the public website mentor page** (v0.42.1, Doug's ruling — the live
page's Elementor HTML + CSS copied verbatim, rendered at 1200px desktop width
scaled to fit; preview slots = `profilePhoto`/`mentorTitle`/**`mentorSummary`
(feature-gated, CRM field NOT built — spec `cmentorprofile-summary-field.md`)**/
`areaOfExpertise`/`industryExperience`/`aboutMentor`/Contact name +
`cLinkedInProfile`). Photo upload/remove included (new
`EspoClient.download_attachment` proxies the image). Verified in the
stubbed-browser harness incl. computed-style match to the live page; **NOT
yet driven against the live CRM** — see the "My Mentor Profile tool" section
for the CRM-prerequisite checklist (prod needs `mentorTitle` + `profilePhoto`
built, both CRMs need `mentorSummary`; Mentor Team role needs read/edit-own +
Attachment grants). Portal shows the tile to Mentor Team members. Before that: **v0.41.2** (407 tests green) — density passes after Doug's live
review of 0.41.0. **Doug's layout ruling (2026-07-14): NEVER cap the page
width — users are on 4K monitors; density = more data per row on the full
width, not a narrower page.** v0.41.2 implements that: edit-form fields are
content-sized flex items that PACK (each `sxf__cN` class is a sensible width
for its data; a line holds as many fields as fit — the 0.41.1 1080px
max-width was rejected and removed). v0.41.1 (kept): billing/shipping
addresses side by side on one panel, Country inside the address block (was
orphaned in Additional details), the three industry fields together on one
Identity row, "Same as billing" restores the original shipping values on
uncheck (checking copies billing over), and LinkedIn labels no longer split
into "Linked In" (`details.py:_label`). Base feature — **v0.41.0 section edit
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
attendee-invitation delivery. **Prod activation: DONE 2026-07-15** (see
Current status — field built by Doug + `GCAL_EVENTS=true` in
`.do/app.prod-crm.yaml`; create path verified live on prod by Doug).
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

- **Communications: Gmail conversation integration — LIVE IN PRODUCTION
  2026-07-14** (crm-test since 2026-07-11). Built v0.35.0; docs:
  plan `prds/communications-gmail-integration.md`, CRM handoff
  `cconversation-entity.md`, activation runbook `GMAIL-INTEGRATION-GUIDE.md`,
  user-facing functional reference `communications-tab.md`.
  **Prod activation record (2026-07-14):** prod CRM entities built by Doug
  (three schema gaps caught by read-only probes and fixed iteratively —
  missing API-role grants, then all five CConversation relationships +
  Multiple-Assigned-Users, then the 13 CCommunication fields; each guide
  ambiguity that caused one was rewritten: every step block now
  self-contained incl. navigation, and §2.3 names BOTH checkboxes — Multiple
  Assigned Users REQUIRED, Collaborators separate). Final schema diff vs
  crm-test CLEAN (fields/links/types/enum options) + a full-field ZZTEST
  write probe stored every value, rfc-id dedup lookup verified. Prod overlay
  `.do/app.prod-crm.yaml` REGENERATED from the live spec (the old local copy
  had drifted: stale ESPO_PROVISION_PASSWORD placeholder, missing the custom
  domain — regenerating from `doctl apps spec get` preserved the live EV[…]
  secrets) + `GMAIL_SYNC=true` and the SA key on web+worker; applied via
  doctl, migration ran, **first backfill pass: 7 mailboxes, 1177 fetched,
  1061 stored, 0 errors → 521 conversations / 1063 messages in the prod CRM**
  (same SA/delegation as crm-test — no Google-side work). Remaining prod
  items: ~~eyeball the tab as a manager + first live SEND~~ ✅ DONE
  2026-07-16 (Doug sent live from the tab; Sent copy confirmed in the
  `@cbmentors.org` mailbox); ~~the User Read=all grant + one-shot resync~~
  DONE 2026-07-15 (owner-stamp correction below); delete 4
  `ZZTEST-GMAILPROD*` probe records in the prod CRM UI (CConversation
  `6a568a35c1d0b305f`/`6a5694a35a5ea4721`, CCommunication
  `6a568a35e8e563564`/`6a5694a374815fd70`).
  **crm-test activation record (2026-07-11):**
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
  2026-05-15". (CORRECTION 2026-07-14: the "owner-stamped" claim here was
  WRONG — the stamp fails silently everywhere the API role can't read Users
  (`cannotRelateForbidden`; EspoCRM relate requires read on the foreign
  record), and crm-test conversations have empty assignedUsers. Invisible
  because the manager roles read CConversation at "all". Fix = grant the API
  role **User: Read = all** (guide §2.4 Role 1 step 5, added), then a
  one-shot `GMAIL_RESYNC=true` re-stamps on the idempotent replay — the
  dedup path re-runs link_records + stamp_owners. Surfaced during the
  2026-07-14 prod rollout. **RESOLVED on BOTH CRMs 2026-07-15**: the API
  role needs User Read=all AND the top-level **Assignment Permission = all**
  (guide §2.4 Role 1 steps 5–6 — the crm-test role rebuild proved Assignment
  Permission is a separate silent prerequisite; without it stamps 403 with
  "Assignment failure: assigned user or team not allowed"). Prod: 516/542
  conversations stamped via one-shot resync; crm-test: all 6 stamped; both
  one-shot flags removed from the overlays. crm-test's API user now carries
  the single role **CustomAppAPIRole** (matching prod's name;
  ClientMentorIntakeRole detached 2026-07-15 — one role name on both CRMs
  kills that drift class).)
  Steady state: sync every 300s; the two fake
  test mailboxes (partner.manager@/matt.mentor@ have no real Workspace
  mailbox) log an expected invalid_grant warning each pass. **Non-contact-recipient design (v0.35.2, from Doug's scenario
  review):** thread-following ingest (replies to any stored conversation
  ingest even from unknown addresses), confirmed sends write a durable
  include override, the compose dialog routes unknown recipients to
  add-address-to-contact / create-contact / explicit one-off, and
  `@cbmentors.org` recipients never trip the guard. **Remaining:**
  ~~exercise SEND (first gmail.send use)~~ ✅ DONE 2026-07-16 (Doug sent
  live from the tab; the Sent copy is in the sender's `@cbmentors.org`
  mailbox — that's where to look, see communications-tab.md FAQ); curation
  live; ~~prod rollout~~ DONE
  2026-07-14 (record above); AI summaries need privacy sign-off +
  `ANTHROPIC_API_KEY` + `COMMS_AI_SUMMARY=true`.

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
link + `/mentorprofile/` (**My Mentor Profile**, v0.42.0) + `/mentorsessions/`;
**Client Administration Team** → `/assignments/`; **Mentor Administration
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
- `email-management.md` — the UMBRELLA email reference (plain language): the
  whole system end-to-end — sync, the two sending identities (personal
  @cbmentors.org vs the shared info@/"CBM Info"), My Email, the compose
  dialog's full feature set, templates/signatures, **submissions as a subset**
  (Submission Admin email: thread anchoring, reply-owed queue, inbound info@
  capture/triage), who-sees-what, the admin requirements table, FAQ. Links
  down to the two deep-dives below.
- `submission-email-flow.md` — the submission-email DESIGN SUMMARY (Doug's
  2026-07-20 request): the inbound info@→queue lifecycle, the outbound
  respond-to-a-form lifecycle, and the Google Workspace changes that
  activate the v0.110.0 shared mailbox (one: make info@ a real licensed
  user mailbox — DWD/GCP need nothing new) + the app/CRM activation table
  and the 15-minute live verification script.
- `communications-tab.md` — plain-language functional reference for the session
  tools' Communications tab (where conversations come from, cleaning, curation,
  compose rules, who-sees-what, "why don't I see…" answers).
- `submission-admin.md` — plain-language functional reference for the rebuilt
  `/ops` Submission Admin (the work-queue grid, resolution workflow, notes,
  the submitter email conversation, and the intended info-request flow).
- `prds/v2/` — the V2 reliability platform specs (durable capture + async worker
  + ops + alerting).

## Conventions

- **Push convention:** Claude commits in this local clone; **Doug reviews and
  pushes**. Do not push without being asked.
- **Every app page loads `frontend/shared/busy.js`, FIRST** (Doug's ruling
  2026-07-20, v0.114.0): the press-feedback spinner. It is self-wiring — one
  script tag, no per-app code — but it wraps `fetch` + `XMLHttpRequest`, so it
  must come before any other script that can start a request. A NEW app page
  (or any new `index.html`) must include it. It is visual only and never sets
  `disabled`; apps keep their own in-flight guards. Manual control for a wait
  it can't see: `var done = CBMBusy.start(btn); … done();`.
- **Every mutating staff action is recorded via `core/action_log.py`** (Doug's
  ruling 2026-07-20, v0.123.0; plan `prds/action-history-plan.md`): a new
  write path calls `record_action(...)` (posts an on-record Stream note as the
  user AND writes a `CActionLog` reporting row via the API key) — or
  `log_action(...)` when the service already posts the stream note. `actionType`
  is free-text from the vocabulary constants in that module (add new verbs
  there); `category` is the small stable enum. Both writes are best-effort and
  the `CActionLog` half is feature-gated (inert until the CRM entity exists), so
  it's safe to wire ahead of the CRM build. Do the logging at the **router**
  layer (it has the actor, app identity, and the service result).
- **Rich-text (wysiwyg) fields use the shared CBMRichText editor** (Doug's
  ruling 2026-07-15): every wysiwyg field — existing or future, any app —
  renders through `frontend/shared/richtext.js` (`CBMRichText.create`), which
  wraps the **vendored Jodit** build at `frontend/shared/vendor/jodit/`
  (MIT; upgrade notes in that dir's README). Never hand-roll a new
  contenteditable editor. Pages load `jodit.min.css` + `jodit.min.js` +
  `richtext.js` (in that order) before their app.js; the component sanitizes
  CRM HTML on load AND on read, and getValue() is snapshot-stable for
  untouched editors (gesture-gated against Jodit's async normalization) so
  save-diff machinery keeps working. Wired everywhere as of v0.53.0
  (sessions v0.50.0 POC; mentoradmin + mentorprofile v0.53.0 — the
  mentorprofile live preview rides the component's `onInput` hook; the
  Communications compose email body v0.60.0 — sends HTML, the send path
  derives the plain-text MIME alternative server-side). The old
  contenteditable `makeWysiwyg` in each app is only a script-load fallback.
- Never commit `.env` or any secret. Secrets are injected as environment
  variables at deploy time (App Platform encrypted env vars).
- Commit messages follow Conventional Commits (`feat:`, `build:`, `docs:`, …).
