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
  name/email/phone/company/message/source/`requestStatus="New"`) linked to the
  Contact (and Account), best-effort, on top of the description stamp + the
  CIntakeSubmission log (added 2026-06-20). **CRM-team build pending** — the
  entity + fields/links + create grant don't exist in crm-test yet (GET → 403),
  so the write currently no-ops at WARNING and the submission still succeeds.
  Spec: `cinformation-request-entity.md`.
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
  2. **OPEN** — sponsor contact typing uses existing `"Donor"` on `cContactType`
     (no "Sponsor" option) — add a real "Sponsor" option if preferred.
  3. **OPEN** — add `partner` + `sponsor` options to the `CIntakeSubmission.form`
     enum so per-submission logging doesn't fall back to a WARNING (best-effort
     either way; the create still succeeds for the main records).
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

## Mentor Assignment tool — `/assignments` (added 2026-06-19)

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

## Current status (2026-05-28)

**Goal:** publish the app on DigitalOcean for user feedback. As of 2026-05-28
it is **deployed and live on App Platform against crm-test** (go-live verified —
see the LIVE block below). The original "feedback first in dry-run, wire CRM
later" plan was overtaken by Doug's decision to verify and keep go-live live.

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
  1. **Re-run the v1 deploy** of `MN-IntakeSubmission.yaml` (v1.1) to add the
     `source` field, the `Normal` reason option, and the `contact` link to
     crm-test. Until then, `Normal` logs fail on the missing `source`/`contact`
     and fall back to WARNING logs (held records still write fine).
  2. Add the **`reason != Normal`** alert-on-create workflow (so only review
     items ping; spec in the doc).
  3. Clean up the `ZZTEST-INTAKE GrantCheck` probe record
     (id `6a2eec00c83e44628`) in the EspoCRM UI.
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

## Gotchas / things learned

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

- `prds/CBM_Client_Intake_Requirements_Specification.md` — what it must do.
- `prds/CBM_Client_Intake_Technical_Design.md` — how it's built (deployment in
  §6, open issues in §7, EspoCRM mapping in §3).

## Conventions

- **Push convention:** Claude commits in this local clone; **Doug reviews and
  pushes**. Do not push without being asked.
- Never commit `.env` or any secret. Secrets are injected as environment
  variables at deploy time (App Platform encrypted env vars).
- Commit messages follow Conventional Commits (`feat:`, `build:`, `docs:`, …).
