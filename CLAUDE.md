# CLAUDE.md

Guidance for Claude Code working in the **cbm-client-intake** repository.
This file is read automatically at session start — it is the recovery anchor
if a session is lost. Keep the "Current status" section up to date.

## What this is

A custom web application for **Cleveland Business Mentors (CBM)**. It hosts
branded, multi-step wizard **intake forms**; a completed submission creates
linked records in EspoCRM (the system of record). Two forms ship today:

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

This repo owns the *application*, not the business definition of the process.
The Client Intake process is defined by **MN-INTAKE** in the
`dbower44022/ClevelandBusinessMentoring` repo; the Requirements Spec here is
kept aligned to it by carry-forward.

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
- **CRM-side build for honeypot quarantine** (CRM team — spec in
  `cintake-submission-entity.md`): create the `CIntakeSubmission` entity, grant
  the intake API user *create* on it, and add an alert-on-create workflow.
  Until then the app holds honeypot hits by logging the payload at WARNING
  (the CRM write fails gracefully).
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
  - `quarantine.py` — a honeypot hit is held for admin review (written to the
    CRM as a `CIntakeSubmission` record, `core.quarantine`) instead of dropped,
    so a false positive is recoverable without contacting the submitter. The
    record carries the submission as reprocess-ready JSON in `description`
    (honeypot field cleared) — an admin re-POSTs it to `/api/{slug}/intake` to
    create the records (honeypot hits never populate the idempotency cache, so
    the original token still processes). Large base64 (résumés) is redacted.
    **CRM dependency** (CRM team — see `cintake-submission-entity.md`): the
    `CIntakeSubmission` entity, the API user's *create* grant, and an
    alert-on-create workflow. Until they exist the CRM write fails and it
    **falls back to logging the full payload at WARNING**, so the app deploys
    safely ahead of the CRM build. Alerting is CRM-owned (workflow/assignment),
    not in the app.
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
